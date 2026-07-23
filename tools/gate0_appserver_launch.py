"""gate0_appserver_launch.py -- drives tools/gate0_appserver_client.py end to end to CONFIRM the
Gate 0 M1 unblock: that `codex app-server`, unlike `codex exec`, delivers the app-tool approval
request (openai/codex#15824) and -- once this client answers `accept` -- the MCP tool call
COMPLETES, instead of exec's "user cancelled MCP tool call" no-op (openai/codex#16685).

ADDITIVE ONLY. This module IMPORTS (never edits) tools/gate0_appserver_client.py,
tools/gate0_credit_breaker.py, and tools/gate0_codex_credit_rate.py as libraries. It never touches
tools/run_gate0_codex.ps1, the brain, core/contracts.py, or any tool schema.

PRIMARY MCP TARGET IS THE STUB (2026-07-23 orchestrator update: Docker Desktop is down on the
launch host, so the Gate 0 `gb-mcp-world` container is unavailable). `--mcp stub` (the default)
registers tools/gate0_stub_mcp_server.py -- a minimal local stdio MCP server with one trivial
`ping` tool. This is not a lesser substitute for the mechanism under test: the exec MCP-cancel bug
(#15824/#16685) fires for ANY non-`codex_apps` MCP server, codex-side and world-agnostic, so a
stub `ping` call hits the identical `item/tool/requestUserInput` approval prompt the Docker world
would. `--mcp docker` remains available (generic, parameterized -- see `_resolve_mcp_server`) for
whenever the Docker daemon is back up; it is not this build's default and is not exercised by the
$0 dry run.

Two audiences:
  * `--dry-run` (THIS is the $0 mode a builder session may run itself, see reports/2026-07-23-
    gate0-appserver-launch-runbook.md Step 3): drives the SAME scoring path
    (`run_one_tool_call_turn`/`score_turn`) against an in-process `StubAppServerPeer` that extends
    the `fake_send` pattern from tests/test_gate0_appserver_client.py, emitting the exact
    ServerRequest sequence a real one-MCP-tool-call turn produces. No process is spawned, no
    network call, no codex binary needed, no tokens spent.
  * real mode (`--handshake-only` for the $0 handshake smoke, or a full turn for the one bounded
    paid confirmation) -- NOT run by this build; see the runbook for the exact orchestrator
    commands and the two prepared wrapper scripts,
    tools/gate0_appserver_handshake_smoke.ps1 and tools/gate0_appserver_paid_turn.ps1.

Assumptions this module makes that are NOT verified against any committed schema (flagged again,
in detail, in the runbook -- `codex app-server generate-json-schema` was never re-run this
session, per the $0 boundary: no codex invocation of any kind was made building this file):
  * `thread/start`'s RESPONSE shape (only ThreadStartPARAMS was dumped/committed upstream) --
    `_extract_thread_id` tries several plausible shapes and fails loud if none match.
  * `turn/start`'s RESPONSE shape and the terminal notification method names/shapes
    (`item/completed`, `turn/completed`/`turn/failed`/`turn/aborted`) -- `score_turn` and
    `StubAppServerPeer` document this inline. The one real paid turn (script (b)) is exactly what
    must confirm or correct these.
"""
from __future__ import annotations

import argparse
import json
import os
import queue
import re
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

from tools.gate0_appserver_client import (
    Gate0AppServerClient,
    build_turn_start_request,
    resolve_codex_path,
)
from tools.gate0_codex_credit_rate import (
    CreditRateNotPinned,
    codex_event_to_credit_event,
    load_credit_rate_pin,
)
from tools.gate0_credit_breaker import (
    STALL_TIMEOUT_S,
    BreakerTripped,
    MalformedCreditStream,
    run_breaker,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
_LATEST_ALIAS_RE = re.compile(r"(?i)(^|[-_.])latest($|[-_.])")

# ASSUMPTION (see module docstring): the terminal-notification vocabulary this client watches for.
DEFAULT_TURN_END_METHODS = ("turn/completed", "turn/failed", "turn/aborted")
COMPLETED_STATUSES = {"completed", "succeeded", "success"}
CANCELLED_STATUSES = {"cancelled", "canceled", "declined", "denied", "failed", "error"}

DEVELOPER_INSTRUCTIONS_TEMPLATE = (
    "Use only the {name} MCP tools. Never use shell, files, web, tool search, connectors, or "
    "other MCP servers."
)

_SENTINEL = object()


def default_prompt(tool_name: str) -> str:
    return (
        f"Call the connected MCP tool named '{tool_name}' exactly once, then stop.\n"
        "Use only the connected MCP tool. Do not use shell, files, web, tool search, or connectors."
    )


# ---------------------------------------------------------------------------------------------
# Observing client: extends (never edits) Gate0AppServerClient to capture the server->client
# NOTIFICATIONS the base client's handle_message() intentionally drops ("not needed to answer
# approvals/elicitations -- out of scope for this prototype"), and to log a full transcript +
# feed a credit-breaker observer. Same class drives both --dry-run and real mode.
# ---------------------------------------------------------------------------------------------

class ObservingGate0Client(Gate0AppServerClient):
    def __init__(self, *args, transcript_path=None, credit_observer=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.notifications: list[dict] = []
        self._transcript_path = Path(transcript_path) if transcript_path else None
        self._credit_observer = credit_observer
        if self._send is not None:
            self._send = self._wrap_send(self._send)

    def _wrap_send(self, inner_send):
        def _sent(message: dict) -> None:
            self._log_transcript("client_to_server", message)
            inner_send(message)
        return _sent

    def connect(self) -> None:  # real mode only
        super().connect()
        self._send = self._wrap_send(self._send)

    def handle_message(self, message: dict) -> None:
        self._log_transcript("server_to_client", message)
        if self._credit_observer is not None:
            self._credit_observer(message)
        if "method" in message and "id" not in message:
            self.notifications.append(message)
        super().handle_message(message)

    def wait_for_notification(self, methods, timeout: float) -> dict | None:
        deadline = time.monotonic() + timeout
        while True:
            for note in self.notifications:
                if note.get("method") in methods:
                    return note
            if time.monotonic() >= deadline:
                return None
            time.sleep(0.05)

    def _log_transcript(self, direction: str, message: dict) -> None:
        if self._transcript_path is None:
            return
        # Append-only (safety-invariants law 2: raw journals are never rewritten/edited).
        with open(self._transcript_path, "a", encoding="utf-8", newline="\n") as fh:
            fh.write(json.dumps({"direction": direction, "message": message}, sort_keys=True) + "\n")


# ---------------------------------------------------------------------------------------------
# In-process stub app-server peer for --dry-run. Extends the `fake_send` pattern from
# tests/test_gate0_appserver_client.py (e.g. test_initialize_then_start_thread_never_auto_sends_
# turn_start) to also simulate ONE turn making exactly ONE MCP tool call.
# ---------------------------------------------------------------------------------------------

class StubAppServerPeer:
    """No real process, no network call, no codex binary -- pure in-process function calls,
    exactly like the mock test suite this reuses. `scenario="cancelled"` proves the scorer
    correctly reports a NEGATIVE outcome too (mirroring the exact `openai/codex#16685` wording),
    not just a hand-tuned-to-pass positive."""

    def __init__(self, tool_name: str = "ping", scenario: str = "completes"):
        if scenario not in ("completes", "cancelled"):
            raise ValueError(f"invalid scenario: {scenario!r}")
        self.client: ObservingGate0Client | None = None  # back-reference, set by the caller
        self.tool_name = tool_name
        self.scenario = scenario
        self.thread_id = "thr_stub_dry_run"
        self.turn_id = "turn_stub_dry_run"
        self.item_id = "item_stub_dry_run_1"
        self._approval_request_id = "req_approval_1"
        self._question_id = "q_approve_tool_call"

    def send(self, message: dict) -> None:
        method = message.get("method")
        if method == "initialize":
            self.client.handle_message({"id": message["id"], "result": {
                "codexHome": "/stub/.codex", "platformFamily": "stub", "platformOs": "stub",
                "userAgent": "gate0-appserver-launch-stub/1",
            }})
        elif method == "thread/start":
            self.client.handle_message({"id": message["id"], "result": {"thread": {"id": self.thread_id}}})
        elif method == "turn/start":
            self._run_turn(message["id"])
        elif "id" in message and "method" not in message:
            self._on_client_answer(message)
        # else: nothing else is expected from this client in the prototype scope.

    def _run_turn(self, turn_start_request_id) -> None:
        self.client.handle_message({"id": turn_start_request_id, "result": {"turn": {"id": self.turn_id}}})
        # The #15824-regression "Approve app tool call?" prompt -- the exact ServerRequest shape
        # that made `codex exec` EOF-decline (#16685); this client's item/tool/requestUserInput
        # handler answers it.
        self.client.handle_message({
            "id": self._approval_request_id, "method": "item/tool/requestUserInput",
            "params": {
                "itemId": self.item_id, "threadId": self.thread_id, "turnId": self.turn_id,
                "questions": [{
                    "id": self._question_id, "header": "Approve app tool call?",
                    "question": f"Allow the {self.tool_name!r} MCP tool call?",
                    "options": [{"label": "Approve", "description": "Allow the call"},
                                {"label": "Deny", "description": "Refuse the call"}],
                }],
            },
        })

    def _on_client_answer(self, message: dict) -> None:
        if message.get("id") != self._approval_request_id:
            return
        answers = (message.get("result") or {}).get("answers", {})
        approved = answers.get(self._question_id, {}).get("answers") == ["Approve"]
        if approved and self.scenario == "completes":
            self.client.handle_message({
                "method": "item/completed",
                "params": {"item": {"id": self.item_id, "type": "mcp_tool_call", "tool": self.tool_name,
                                     "status": "completed",
                                     "result": {"content": [{"type": "text", "text": "pong"}]}}},
            })
            self.client.handle_message({
                "method": "turn/completed",
                "params": {"turn": {"id": self.turn_id, "threadId": self.thread_id}},
            })
        else:
            self.client.handle_message({
                "method": "item/completed",
                "params": {"item": {"id": self.item_id, "type": "mcp_tool_call", "tool": self.tool_name,
                                     "status": "cancelled", "error": "user cancelled MCP tool call"}},
            })
            self.client.handle_message({
                "method": "turn/failed",
                "params": {"turn": {"id": self.turn_id, "threadId": self.thread_id}},
            })


# ---------------------------------------------------------------------------------------------
# The shared scoring path -- runs unchanged whether `client` is wired to a real `codex app-server`
# subprocess or the in-process StubAppServerPeer.
# ---------------------------------------------------------------------------------------------

def _extract_thread_id(thread_start_result: dict) -> str:
    thread = thread_start_result.get("thread")
    if isinstance(thread, dict) and isinstance(thread.get("id"), str):
        return thread["id"]
    if isinstance(thread_start_result.get("threadId"), str):
        return thread_start_result["threadId"]
    if isinstance(thread_start_result.get("id"), str):
        return thread_start_result["id"]
    raise RuntimeError(f"could not find a thread id in thread/start result: {thread_start_result!r}")


def score_turn(client: ObservingGate0Client, tool_name: str | None = None) -> dict:
    item_notes = [n for n in client.notifications if n.get("method") == "item/completed"]
    turn_end = next((n for n in client.notifications if n.get("method") in DEFAULT_TURN_END_METHODS), None)
    target = None
    for note in item_notes:
        item = (note.get("params") or {}).get("item") or {}
        if tool_name is None or item.get("tool") == tool_name or "tool" in str(item.get("type", "")).lower():
            target = item
    status = str((target or {}).get("status", "")).lower()
    completed = target is not None and status in COMPLETED_STATUSES
    cancelled = target is not None and status in CANCELLED_STATUSES
    if target is None and turn_end is not None and turn_end.get("method") != "turn/completed":
        cancelled = True
    return {
        "mcp_tool_call_completed": completed,
        "cancelled": cancelled,
        "target_item": target,
        "turn_end_notification": turn_end,
        "notes": [],
    }


def run_one_tool_call_turn(client: ObservingGate0Client, *, cwd: str, prompt: str, tool_name: str,
                            turn_timeout_s: float) -> dict:
    """initialize -> thread/start (approvalsReviewer='user') -> turn/start -> (client answers
    whatever approval/elicitation requests arrive) -> wait for the turn to end -> score whether the
    ONE MCP tool call completed or was cancelled."""
    client.initialize()
    thread_result = client.start_thread(cwd=cwd, approvals_reviewer="user")
    thread_id = _extract_thread_id(thread_result)
    turn_params = build_turn_start_request(thread_id, [{"type": "text", "text": prompt}])
    client.send_request("turn/start", turn_params)
    end_note = client.wait_for_notification(DEFAULT_TURN_END_METHODS, timeout=turn_timeout_s)
    result = score_turn(client, tool_name=tool_name)
    if end_note is None:
        result["notes"].append(f"no terminal notification observed within {turn_timeout_s}s")
    return result


# ---------------------------------------------------------------------------------------------
# Credit-breaker wiring -- IMPORTS (never edits) tools/gate0_credit_breaker.run_breaker and
# tools/gate0_codex_credit_rate.codex_event_to_credit_event. NOT the pinned tools/
# run_gate0_codex.ps1 supervised-exec pipeline (that relays a flat `codex exec --json` stdout
# stream through a separate accountant subprocess under a Windows kill-on-close Job Object) --
# this Python launcher drives `codex app-server`'s bidirectional JSON-RPC directly, so it wires
# the SAME breaker/rate-conversion library functions around whatever inbound app-server messages
# arrive, with a best-effort `taskkill /T /F` kill (see kill_process_tree) as its own, WEAKER,
# backstop -- flagged in the runbook as a known gap vs the pinned launcher's Job-Object guarantee.
# ---------------------------------------------------------------------------------------------

def kill_process_tree(pid: int) -> None:
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True)
    else:
        try:
            os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass


class LiveCreditGuard:
    def __init__(self, limit: float, stall_timeout_s: float, rate_pin: dict | None, on_trip):
        self._queue: "queue.Queue[object]" = queue.Queue()
        self._rate_pin = rate_pin
        self._limit = limit
        self._stall_timeout_s = stall_timeout_s
        self._on_trip = on_trip
        self.result: dict = {}
        self._thread = threading.Thread(target=self._run, daemon=True)

    def start(self) -> None:
        self._thread.start()

    def observe(self, raw_message: dict) -> None:
        self._queue.put(raw_message)

    def finish(self) -> None:
        self._queue.put(_SENTINEL)

    def join(self, timeout: float | None = None) -> None:
        self._thread.join(timeout)

    def _events(self):
        while True:
            item = self._queue.get()
            if item is _SENTINEL:
                return
            yield self._to_credit_event(item)

    def _to_credit_event(self, raw_message: dict) -> dict:
        if self._rate_pin is None:
            # No rate pin supplied -- every event passes through at zero KNOWN credit delta,
            # mirroring tools/gate0_codex_credit_rate.py::codex_event_to_credit_event's own
            # zero-credit-passthrough philosophy exactly (never invent a rate, never drop the
            # event -- dropping it would silence the stall clock).
            return {"normalized_credits": 0.0}
        try:
            return codex_event_to_credit_event(raw_message, self._rate_pin)
        except ValueError as exc:
            raise MalformedCreditStream(f"credit_conversion_failed:{exc}") from exc

    def _run(self) -> None:
        try:
            self.result = run_breaker(self._events(), limit=self._limit, raise_on_trip=True,
                                       stall_timeout_s=self._stall_timeout_s)
        except (BreakerTripped, MalformedCreditStream) as exc:
            self.result = {"tripped": True, "error": str(exc)}
            self._on_trip(exc)


# ---------------------------------------------------------------------------------------------
# Real-mode config: mirrors tools/run_gate0_codex.ps1's OWN `$Overrides` recipe (same field
# vocabulary, same `-c key=value` CLI-override transport -- the pinned script's own receipt calls
# this "the effective config", not the on-disk config.toml). Reimplemented here in Python because
# gate0_appserver_client.py spawns `codex app-server` directly rather than going through that
# PowerShell script. Nothing here edits or invokes the pinned .ps1 file.
# ---------------------------------------------------------------------------------------------

def _quote_toml(value: str) -> str:
    return '"' + str(value).replace("\\", "\\\\").replace('"', '\\"') + '"'


def build_overrides(*, model: str, mcp_server_name: str, mcp_command: str, mcp_args: list,
                     mcp_cwd: str, enabled_tools: list, developer_instructions: str) -> list[str]:
    args_toml = ", ".join(_quote_toml(a) for a in mcp_args)
    tools_toml = ", ".join(_quote_toml(t) for t in enabled_tools)
    return [
        f"model={_quote_toml(model)}",
        'forced_login_method="chatgpt"',
        'approval_policy="never"',
        'sandbox_mode="read-only"',
        'web_search="disabled"',
        f"developer_instructions={_quote_toml(developer_instructions)}",
        'history.persistence="none"',
        "features.shell_tool=false",
        "features.skill_mcp_dependency_install=false",
        "features.apps=false",
        "features.goals=false",
        "features.hooks=false",
        "features.memories=false",
        "features.multi_agent=false",
        "apps._default.enabled=false",
        f"mcp_servers.{mcp_server_name}.command={_quote_toml(mcp_command)}",
        f"mcp_servers.{mcp_server_name}.args=[{args_toml}]",
        f"mcp_servers.{mcp_server_name}.cwd={_quote_toml(mcp_cwd)}",
        f"mcp_servers.{mcp_server_name}.required=true",
        f"mcp_servers.{mcp_server_name}.enabled=true",
        f"mcp_servers.{mcp_server_name}.enabled_tools=[{tools_toml}]",
        f'mcp_servers.{mcp_server_name}.default_tools_approval_mode="auto"',
    ]


def _resolve_mcp_server(args: argparse.Namespace):
    """Returns (command, args, cwd, enabled_tools). `--mcp stub` (the default/primary path, see
    module docstring) needs no Docker daemon at all."""
    if args.mcp == "stub":
        script = args.stub_mcp_script or str(REPO_ROOT / "tools" / "gate0_stub_mcp_server.py")
        return sys.executable, [script], str(REPO_ROOT), ["ping"]
    # --mcp docker: generic pass-through, NOT this build's default. Only usable once the Docker
    # daemon is back up; parameters are the orchestrator's responsibility (the safety-critical
    # mount/state/ROM specifics live in the pinned tools/run_gate0_codex.ps1 recipe, which this
    # module intentionally does not duplicate unreviewed).
    if not args.docker_image:
        raise SystemExit("--mcp docker requires --docker-image")
    mounts = []
    for spec in args.docker_mount or []:
        mounts += ["--mount", spec]
    docker_args = ["run", "-i", "--rm", "--network", "none", *mounts, args.docker_image,
                    *(args.docker_extra_arg or [])]
    tools = args.docker_tool or ["observe"]
    return "docker", docker_args, str(REPO_ROOT), tools


# ---------------------------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------------------------

def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--dry-run", action="store_true",
                    help="$0: drive an in-process StubAppServerPeer instead of a real codex process.")
    p.add_argument("--handshake-only", action="store_true",
                    help="real mode only: initialize()+start_thread(), never turn/start. No spend "
                         "beyond the handshake.")
    p.add_argument("--scenario", choices=("completes", "cancelled"), default="completes",
                    help="--dry-run only: which stub outcome to simulate.")
    p.add_argument("--mcp", choices=("stub", "docker"), default="stub",
                    help="real mode only: which MCP server to register. stub is PRIMARY (Docker "
                         "daemon down as of 2026-07-23).")
    p.add_argument("--model", default=None, help="explicit model id; required outside --dry-run.")
    p.add_argument("--out-dir", required=True, help="output directory; must not exist or be empty.")
    p.add_argument("--codex-path", default=None)
    p.add_argument("--codex-home", default=None,
                    help="real mode only: isolated CODEX_HOME (never the user's real ~/.codex). "
                         "Defaults to <out-dir>/codex-home.")
    p.add_argument("--tool-name", default="ping")
    p.add_argument("--prompt", default=None)
    p.add_argument("--credit-cap", type=float, default=10.0,
                    help="low normalized-credit ceiling for THIS launcher's own breaker wiring "
                         "(default well under the pinned 250 combined ceiling).")
    p.add_argument("--credit-rate-pin", default=None,
                    help="a validated rate-pin JSON (tools/gate0_codex_credit_rate.py contract); "
                         "required to convert real token usage into real credits.")
    p.add_argument("--stall-timeout-s", type=float, default=float(STALL_TIMEOUT_S))
    p.add_argument("--turn-timeout-s", type=float, default=120.0,
                    help="real mode only: how long to wait for a terminal turn notification.")
    p.add_argument("--mcp-server-name", default=None)
    p.add_argument("--stub-mcp-script", default=None)
    p.add_argument("--docker-image", default=None)
    p.add_argument("--docker-mount", action="append", default=None)
    p.add_argument("--docker-extra-arg", action="append", default=None)
    p.add_argument("--docker-tool", action="append", default=None)
    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    if not args.dry_run and not args.model:
        parser.error("--model is required outside --dry-run")
    if args.model and _LATEST_ALIAS_RE.search(args.model):
        parser.error("Model must be an explicit model identifier, not a latest alias.")
    if args.stall_timeout_s > STALL_TIMEOUT_S:
        parser.error(f"--stall-timeout-s may only tighten the pinned {STALL_TIMEOUT_S}s backstop, "
                     "never loosen it.")
    if args.credit_rate_pin and (args.dry_run or args.handshake_only):
        parser.error("--credit-rate-pin is only meaningful for a real, turn-running launch.")

    out_dir = Path(args.out_dir)
    if out_dir.exists() and any(out_dir.iterdir()):
        parser.error(f"--out-dir {out_dir} must not exist or must be empty.")
    out_dir.mkdir(parents=True, exist_ok=True)
    transcript_path = out_dir / "transcript.jsonl"
    audit_path = out_dir / "audit.jsonl"

    rate_pin = None
    if args.credit_rate_pin:
        try:
            rate_pin = load_credit_rate_pin(Path(args.credit_rate_pin), args.model)
        except CreditRateNotPinned as exc:
            parser.error(f"credit rate pin refused: {exc}")

    args.prompt = args.prompt or default_prompt(args.tool_name)
    args.mcp_server_name = args.mcp_server_name or ("gate0_stub" if args.mcp == "stub" else "gate0_world")

    state: dict = {"client": None, "pid": None}

    def _on_trip(exc: Exception) -> None:
        client = state.get("client")
        if client is not None:
            try:
                client.close()
            except Exception:
                pass
        pid = state.get("pid")
        if pid is not None:
            kill_process_tree(pid)

    guard = LiveCreditGuard(limit=args.credit_cap, stall_timeout_s=args.stall_timeout_s,
                             rate_pin=rate_pin, on_trip=_on_trip)
    guard.start()

    notes: list[str] = []
    result: dict = {}
    mode = "dry_run" if args.dry_run else ("handshake_only" if args.handshake_only else "real_turn")

    if args.dry_run:
        peer = StubAppServerPeer(tool_name=args.tool_name, scenario=args.scenario)
        client = ObservingGate0Client(send=peer.send, transcript_path=transcript_path,
                                       credit_observer=guard.observe, audit_log_path=audit_path)
        peer.client = client
        state["client"] = client
        notes.append("DRY RUN: in-process StubAppServerPeer, no codex process spawned, $0.")
        result = run_one_tool_call_turn(client, cwd=str(out_dir), prompt=args.prompt,
                                         tool_name=args.tool_name, turn_timeout_s=5.0)
        guard.finish()
        guard.join(timeout=5.0)
    else:
        codex_path = args.codex_path or resolve_codex_path()
        codex_home = args.codex_home or str(out_dir / "codex-home")
        Path(codex_home).mkdir(parents=True, exist_ok=True)
        mcp_command, mcp_args, mcp_cwd, enabled_tools = _resolve_mcp_server(args)
        overrides = build_overrides(
            model=args.model, mcp_server_name=args.mcp_server_name, mcp_command=mcp_command,
            mcp_args=mcp_args, mcp_cwd=mcp_cwd, enabled_tools=enabled_tools,
            developer_instructions=DEVELOPER_INSTRUCTIONS_TEMPLATE.format(name=args.mcp_server_name))
        extra_args: list[str] = []
        for override in overrides:
            extra_args += ["-c", override]

        env_backup = os.environ.get("CODEX_HOME")
        os.environ["CODEX_HOME"] = codex_home
        try:
            client = ObservingGate0Client(codex_path=codex_path, extra_args=extra_args,
                                           cwd=str(out_dir), transcript_path=transcript_path,
                                           credit_observer=guard.observe, audit_log_path=audit_path)
            state["client"] = client
            client.connect()
            state["pid"] = client._transport.proc.pid
            try:
                init_result = client.initialize()
                thread_result = client.start_thread(cwd=str(out_dir), approvals_reviewer="user")
                notes.append(f"initialize() -> {init_result!r}")
                notes.append(f"thread/start() -> {thread_result!r}")
                if args.handshake_only:
                    result = {"mcp_tool_call_completed": False, "cancelled": False,
                              "notes": ["--handshake-only: no turn/start sent, no spend beyond "
                                        "the handshake."]}
                else:
                    thread_id = _extract_thread_id(thread_result)
                    turn_params = build_turn_start_request(thread_id, [{"type": "text", "text": args.prompt}])
                    client.send_request("turn/start", turn_params)
                    end_note = client.wait_for_notification(DEFAULT_TURN_END_METHODS,
                                                             timeout=args.turn_timeout_s)
                    result = score_turn(client, tool_name=args.tool_name)
                    if end_note is None:
                        result.setdefault("notes", []).append(
                            f"no terminal notification observed within {args.turn_timeout_s}s")
            finally:
                guard.finish()
                guard.join(timeout=10.0)
                client.close()
        finally:
            if env_backup is None:
                os.environ.pop("CODEX_HOME", None)
            else:
                os.environ["CODEX_HOME"] = env_backup

    credits_result = guard.result or {}
    verdict = {
        "schema_version": 1,
        "kind": "gate0_appserver_launch_verdict",
        "mode": mode,
        "mcp": args.mcp,
        "mcp_tool_call_completed": bool(result.get("mcp_tool_call_completed", False)),
        "cancelled": bool(result.get("cancelled", False)),
        "normalized_credits": (credits_result.get("final_total_normalized_credits")
                                if credits_result.get("final_total_normalized_credits") is not None
                                else credits_result.get("credits_at_trip", 0.0)) or 0.0,
        "credit_breaker_tripped": bool(credits_result.get("tripped", False)),
        "turns": 0 if (mode == "handshake_only") else 1,
        "transcript_path": str(transcript_path),
        "audit_log_path": str(audit_path),
        "notes": notes + list(result.get("notes", [])),
    }
    verdict_path = out_dir / "verdict.json"
    verdict_path.write_text(json.dumps(verdict, indent=2, sort_keys=False) + "\n",
                             encoding="utf-8", newline="\n")
    print(json.dumps(verdict, sort_keys=True))
    if mode == "handshake_only":
        return 0
    return 0 if verdict["mcp_tool_call_completed"] and not verdict["credit_breaker_tripped"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
