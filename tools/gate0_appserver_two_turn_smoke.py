"""gate0_appserver_two_turn_smoke.py -- DEV SMOKE, NOT A GATE-0 ATTEMPT. Sends a SECOND
`turn/start` on the SAME `thread_id` after the first turn's `turn/completed`, to settle the two
facts the Gate-0 v2 C5 settle turn depends on and that nothing in this repo currently proves:

  FACT 1 -- does `codex` keep the MCP child ALIVE across a turn boundary on one thread? Signals
  point that way (`mcpServer/startupStatus/updated` is keyed by `threadId`, and the thread goes
  `idle` rather than closed after `turn/completed`) but nothing proves it. If the child RESTARTS
  under `--mcp docker`, the new container reloads the read-only `runs/red_start.state` and appends
  BEDROOM rows into the same bind-mounted `world/oracle.jsonl` -- which would make
  `red_map_changed_during_battle_exit_span` fire and kill the one settle attempt on a garbage FAIL.
  Two independent readings, neither of them "the PID is still alive":
    (a) CODEX-SIDE, works on either MCP target: `mcpServer/startupStatus/updated` is emitted by
        codex exactly when it brings an MCP server up (`starting` -> `ready`). In the banked
        2026-07-24 paid Red arm that pair appears ONCE, immediately after the first `turn/start`.
        A second pair after turn 2 begins means a respawn; no second pair means no respawn.
    (b) WORLD-SIDE, `--mcp docker` only: the world's own `oracle.jsonl` carries a monotonic `step`
        counter that restarts at 1 in a fresh container, and `watch` coordinates that return to
        the bedroom start (x=3, y=7, map=38) when `red_start.state` is reloaded. Turn 1 moves the
        player, so a restart is unmistakable.
  An identity probe (`docker ps`, or the MCP child's pid/start-time) is polled throughout as a
  third, corroborating -- never sole -- signal.

  FACT 2 -- is `thread/tokenUsage/updated`'s `tokenUsage.total` THREAD-cumulative or PER-TURN? Only
  a within-turn cumulative series has ever been observed (runs/gate0_paid/red/
  transcript.raw_appserver.jsonl, 20 updates rising 11593 -> 346742 inside ONE turn). If it resets
  per turn, turn 2's first notification REGRESSES against turn 1's last, and the shipped
  `AppServerUsageTracker` raises `app_server_token_usage_regressed` -> `MalformedCreditStream` ->
  `LiveCreditGuard._on_trip` kills codex and the world MID-TURN. Entirely codex-side accounting:
  the answer does not depend on which MCP server is registered. This script reads the raw numbers
  per turn straight out of the append-only transcript.

SAFETY / SCOPE (deliberate, checked at runtime -- see `_refuse_runs_path`):
  * Arm R shape ONLY. There is no MiniWoB path here at all, so the held-out MiniWoB seeds
    (1000-1004) cannot be touched by this script.
  * `--out-dir` and the world dir it creates are REFUSED if they resolve anywhere under `runs/`.
    Nothing is written, moved or renamed under the append-only `runs/` tree. `runs/red_start.state`
    and `roms/` are consumed exactly as `tools/gate0_appserver_arm.build_docker_mcp_args` mounts
    them: `readonly`.
  * This is NOT scoreable as a Gate-0 attempt: no `--mode` of any kind, no `agent_metrics.json`,
    no `handshake-receipt.json`, no `run-receipt.json`, no write under `runs/gate0_*`. The only
    verdict written is `two-turn-smoke-verdict.json`, whose `kind` no scorer reads.
  * The task texts below are DELIBERATELY NOT the frozen Gate-0 task (`ARM_TASK_SENTENCES`) -- they
    are trivial call-a-tool-and-look instructions, so a transcript from this script can never be
    mistaken for a Gate-0 arm transcript.

ADDITIVE ONLY: imports (never edits) tools/gate0_appserver_launch.py, tools/gate0_appserver_arm.py
(for the frozen docker mount recipe -- reused rather than re-derived), tools/
gate0_appserver_client.py, tools/gate0_codex_credit_rate.py and tools/gate0_credit_breaker.py.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

from tools.check_gate0_codex import TOOLS
from tools.gate0_appserver_arm import (
    DEVELOPER_INSTRUCTION,
    SERVER_NAME,
    build_docker_mcp_args,
    resolve_docker_path,
)
from tools.gate0_appserver_client import build_turn_start_request, resolve_codex_path
from tools.gate0_appserver_launch import (
    DEFAULT_TURN_END_METHODS,
    AppServerUsageTracker,
    LiveCreditGuard,
    ObservingGate0Client,
    _extract_thread_id,
    _extract_turn_id,
    build_overrides,
    kill_process_tree,
    seed_codex_auth,
)
from tools.gate0_codex_credit_rate import CreditRateNotPinned, load_credit_rate_pin
from tools.gate0_credit_breaker import STALL_TIMEOUT_S

REPO_ROOT = Path(__file__).resolve().parent.parent
STARTUP_STATUS_METHOD = "mcpServer/startupStatus/updated"
_COMMON_SUFFIX = ("Use only the connected MCP tools. Do not use shell, files, web, tool search, "
                  "or connectors.\n")

# Turn 1 CHANGES something; turn 2 only LOOKS. Under --mcp docker the Fact-1 discriminator then
# lives entirely in the world's own oracle journal, so neither turn depends on the model reporting
# anything faithfully.
TASK_TEXTS = {
    "docker": (
        "Call observe once. Then walk the player several tiles by pressing a direction button "
        "repeatedly, so the player's x/y position clearly changes. Then call observe once more "
        "and report the player's x, y and map values. Then stop.\n" + _COMMON_SUFFIX,
        "Call observe exactly once. Report the player's x, y and map values verbatim from that "
        "observation, then stop. Do not press any buttons.\n" + _COMMON_SUFFIX,
    ),
    "stub": (
        "Call the connected MCP tool named 'ping' exactly once, report what it returned, then "
        "stop.\n" + _COMMON_SUFFIX,
        "Call the connected MCP tool named 'ping' exactly once more, report what it returned, "
        "then stop.\n" + _COMMON_SUFFIX,
    ),
}


def _refuse_runs_path(label: str, path: Path, repo_root: Path | None = None) -> Path:
    """Checked against BOTH this file's own checkout and the --repo-root one: the docker leg mounts
    roms/ and runs/red_start.state from a different checkout than the worktree this may run from,
    and either tree's runs/ is equally append-only."""
    resolved = Path(path).resolve()
    for root in {REPO_ROOT, repo_root or REPO_ROOT}:
        runs = (Path(root) / "runs").resolve()
        if resolved == runs or runs in resolved.parents:
            raise SystemExit(f"{label} resolves to {resolved}, which is under the append-only "
                              f"{runs} tree. This dev smoke must write everything OUTSIDE runs/.")
    return resolved


class _ObservingUsageTracker(AppServerUsageTracker):
    """SMOKE-ONLY observation shim -- NOT a proposed fix for `AppServerUsageTracker`, and not
    shipped anywhere else.

    The shipped tracker FAILS CLOSED on a regressed cumulative total (that is correct: a regression
    is either stream corruption or an unmodelled reset, and it must not be priced on faith). But a
    per-turn reset is exactly the thing this script exists to MEASURE, and a fail-closed raise here
    would kill codex on turn 2's FIRST token-usage notification -- which lands BEFORE turn 2's first
    tool call (confirmed ordering in runs/gate0_paid/red/transcript.raw_appserver.jsonl) -- and so
    would destroy the Fact-1 evidence before it exists.

    This subclass records the regression and RE-BASELINES, counting the whole new total as fresh
    spend. That OVER-counts (never under-counts), so the live `--credit-cap` stays enforceable and
    can only trip EARLIER than the truth, never later."""

    def __init__(self) -> None:
        super().__init__()
        self.regressions: list[dict] = []

    def delta_for(self, total: dict) -> dict:
        try:
            return super().delta_for(total)
        except ValueError as exc:
            if "app_server_token_usage_regressed" not in str(exc):
                raise
            self.regressions.append({"at": time.time(), "detail": str(exc)})
            self._last_total = None
            return super().delta_for(total)


class IdentityProbePoller:
    """Corroborating (never sole) Fact-1 signal: whatever `probe_argv` prints, sampled through the
    whole run including across the turn boundary. A restart shows up as the identity line
    disappearing and/or a different one appearing."""

    def __init__(self, probe_argv: list[str], interval_s: float = 2.0):
        self._probe_argv = probe_argv
        self._interval_s = interval_s
        self._stop = threading.Event()
        self.samples: list[dict] = []
        self._thread = threading.Thread(target=self._run, daemon=True)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._thread.join(timeout=10.0)

    def sample_now(self, label: str) -> dict:
        sample = {"t": time.time(), "label": label, "lines": self._probe()}
        self.samples.append(sample)
        return sample

    def _probe(self) -> list[str]:
        try:
            proc = subprocess.run(self._probe_argv, capture_output=True, text=True, timeout=30)
        except Exception as exc:  # a probe hiccup must never kill the run
            return [f"identity_probe_failed:{exc}"]
        return [line.strip() for line in proc.stdout.splitlines() if line.strip()]

    def _run(self) -> None:
        while not self._stop.is_set():
            self.samples.append({"t": time.time(), "label": "poll", "lines": self._probe()})
            self._stop.wait(self._interval_s)


def read_oracle_rows(world_dir: Path) -> list[dict]:
    path = world_dir / "oracle.jsonl"
    if not path.is_file():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return rows


def summarize_oracle(rows: list[dict]) -> dict:
    if not rows:
        return {"row_count": 0, "first_step": None, "last_step": None,
                "first_watch": None, "last_watch": None}
    return {"row_count": len(rows),
            "first_step": rows[0].get("step"), "last_step": rows[-1].get("step"),
            "first_watch": rows[0].get("watch"), "last_watch": rows[-1].get("watch")}


def classify_world_continuity(after_turn1: list[dict], after_turn2: list[dict]) -> dict:
    """Fact-1 reading (b), `--mcp docker` only. `step` is the world process's own monotonic
    counter, restarting at 1 in a fresh container; `watch` carries the bedroom start coordinates
    (x=3, y=7, map=38) that a reload of runs/red_start.state reproduces."""
    n1 = len(after_turn1)
    new_rows = after_turn2[n1:] if len(after_turn2) >= n1 else []
    verdict = {
        "rows_after_turn1": n1,
        "rows_after_turn2": len(after_turn2),
        "new_rows_in_turn2": len(new_rows),
        "last_step_turn1": after_turn1[-1].get("step") if after_turn1 else None,
        "last_watch_turn1": after_turn1[-1].get("watch") if after_turn1 else None,
        "first_step_turn2": new_rows[0].get("step") if new_rows else None,
        "first_watch_turn2": new_rows[0].get("watch") if new_rows else None,
        "prefix_intact": after_turn2[:n1] == after_turn1,
    }
    if not after_turn1:
        verdict["world_persisted_across_turns"] = None
        verdict["reason"] = "no oracle journal (not a docker world run) -- not applicable"
    elif len(after_turn2) < n1 or not verdict["prefix_intact"]:
        verdict["world_persisted_across_turns"] = False
        verdict["reason"] = "oracle journal was truncated/rewritten -- a fresh world process wrote it"
    elif not new_rows:
        verdict["world_persisted_across_turns"] = None
        verdict["reason"] = "turn 2 produced no oracle rows at all -- INCONCLUSIVE, no tool call landed"
    elif verdict["first_step_turn2"] == 1:
        verdict["world_persisted_across_turns"] = False
        verdict["reason"] = "turn 2's first oracle row restarts the step counter at 1 -- the MCP child restarted"
    elif verdict["first_step_turn2"] == (verdict["last_step_turn1"] or 0) + 1:
        verdict["world_persisted_across_turns"] = True
        verdict["reason"] = "turn 2 continued the same world process's step counter"
    else:
        verdict["world_persisted_across_turns"] = None
        verdict["reason"] = "step counter neither continued nor reset to 1 -- INCONCLUSIVE, read the rows"
    return verdict


def classify_startup_status(notifications: list[dict], boundary_index: int) -> dict:
    """Fact-1 reading (a), works on either MCP target. `boundary_index` is len(notifications) at the
    moment turn 1's terminal notification was observed, so everything at or after it belongs to
    turn 2. codex emits `mcpServer/startupStatus/updated` exactly when it brings an MCP server up."""
    def _events(slice_):
        return [{"name": (n.get("params") or {}).get("name"),
                 "status": (n.get("params") or {}).get("status")}
                for n in slice_ if n.get("method") == STARTUP_STATUS_METHOD]

    turn1, turn2 = _events(notifications[:boundary_index]), _events(notifications[boundary_index:])
    verdict = {"boundary_notification_index": boundary_index,
               "startup_events_turn1": turn1, "startup_events_turn2": turn2}
    if not turn1:
        verdict["mcp_child_reused_in_turn2"] = None
        verdict["reason"] = ("turn 1 emitted no startupStatus event at all -- INCONCLUSIVE, this "
                              "reading assumes codex announces every MCP server start")
    elif turn2:
        verdict["mcp_child_reused_in_turn2"] = False
        verdict["reason"] = f"codex announced starting the MCP server again in turn 2: {turn2}"
    else:
        verdict["mcp_child_reused_in_turn2"] = True
        verdict["reason"] = "no new MCP startup announcement in turn 2 -- the turn-1 child was reused"
    return verdict


def token_usage_by_turn(transcript_path: Path) -> list[dict]:
    """Every `thread/tokenUsage/updated` in wire order, with its turnId and cumulative totals --
    the raw evidence for Fact 2, read back from the append-only transcript rather than from any
    in-memory bookkeeping."""
    out = []
    if not transcript_path.is_file():
        return out
    for line in transcript_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            message = json.loads(line).get("message") or {}
        except json.JSONDecodeError:
            continue
        if message.get("method") != "thread/tokenUsage/updated":
            continue
        params = message.get("params") or {}
        usage = params.get("tokenUsage") or {}
        out.append({"turn_id": params.get("turnId"),
                    "total": usage.get("total"), "last": usage.get("last")})
    return out


def classify_token_usage(events: list[dict], turn1_id: str, turn2_id: str) -> dict:
    """THE Fact-2 verdict: does turn 2's FIRST cumulative total continue turn 1's series, or reset?"""
    t1 = [e for e in events if e["turn_id"] == turn1_id]
    t2 = [e for e in events if e["turn_id"] == turn2_id]
    verdict = {
        "turn1_event_count": len(t1), "turn2_event_count": len(t2),
        "turn1_last_total": t1[-1]["total"] if t1 else None,
        "turn2_first_total": t2[0]["total"] if t2 else None,
        "turn2_first_last": t2[0]["last"] if t2 else None,
    }
    if not t1 or not t2:
        verdict["thread_cumulative"] = None
        verdict["reason"] = "one of the turns emitted no tokenUsage notification -- INCONCLUSIVE"
        return verdict
    prev, nxt = verdict["turn1_last_total"], verdict["turn2_first_total"]
    fields = [f for f in ("inputTokens", "cachedInputTokens", "outputTokens",
                          "reasoningOutputTokens", "totalTokens") if f in prev and f in nxt]
    regressed = [f for f in fields if nxt[f] < prev[f]]
    verdict["regressed_fields"] = regressed
    verdict["thread_cumulative"] = not regressed
    verdict["reason"] = ("turn 2's first cumulative total is >= turn 1's last in every field"
                          if not regressed else
                          f"turn 2's first total REGRESSED in {regressed} -- totals are PER-TURN")
    return verdict


def _resolve_mcp(args: argparse.Namespace, world_dir: Path):
    """Returns (command, args, cwd, enabled_tools, identity_probe_argv)."""
    if args.mcp == "docker":
        docker_path = resolve_docker_path()
        repo_root = Path(args.repo_root).resolve()
        # Frozen Arm-R mount recipe, REUSED not re-derived. `repo_root` is explicit because this
        # script may run from a git worktree that has no roms/ or runs/red_start.state of its own.
        return ("docker", build_docker_mcp_args("red", args.docker_image, world_dir,
                                                 repo_root=repo_root),
                str(repo_root), TOOLS["red"],
                [docker_path, "ps", "--no-trunc", "--format", "{{.ID}} {{.Image}}"])
    script = str(REPO_ROOT / "tools" / "gate0_stub_mcp_server.py")
    probe = ("Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | "
             "Where-Object { $_.CommandLine -like '*gate0_stub_mcp_server*' } | "
             "ForEach-Object { \"$($_.ProcessId) $($_.CreationDate.ToString('o'))\" }")
    return (sys.executable, [script], str(REPO_ROOT), ["ping"],
            ["powershell.exe", "-NoProfile", "-Command", probe])


def run_smoke(args: argparse.Namespace) -> dict:
    repo_root = Path(args.repo_root).resolve()
    out_dir = _refuse_runs_path("--out-dir", Path(args.out_dir), repo_root)
    if out_dir.exists() and any(out_dir.iterdir()):
        raise SystemExit(f"--out-dir {out_dir} must not exist or must be empty.")
    out_dir.mkdir(parents=True, exist_ok=True)
    world_dir = _refuse_runs_path("world dir", out_dir / "world", repo_root)
    world_dir.mkdir(parents=True, exist_ok=True)

    try:
        rate_pin = load_credit_rate_pin(Path(args.credit_rate_pin), args.model)
    except CreditRateNotPinned as exc:
        raise SystemExit(f"credit rate pin refused: {exc}")

    codex_path = args.codex_path or resolve_codex_path()
    codex_home = Path(args.codex_home) if args.codex_home else (out_dir / "codex-home")
    codex_home.mkdir(parents=True, exist_ok=True)
    auth_note = seed_codex_auth(codex_home, args.codex_auth_source)

    mcp_command, mcp_args, mcp_cwd, enabled_tools, probe_argv = _resolve_mcp(args, world_dir)
    overrides = build_overrides(model=args.model, mcp_server_name=SERVER_NAME,
                                mcp_command=mcp_command, mcp_args=mcp_args, mcp_cwd=mcp_cwd,
                                enabled_tools=enabled_tools,
                                developer_instructions=DEVELOPER_INSTRUCTION)

    transcript_path = out_dir / "transcript.raw_appserver.jsonl"
    tracker = _ObservingUsageTracker()
    state: dict = {"client": None, "pid": None}

    def _on_trip(exc: Exception) -> None:
        client = state.get("client")
        if client is not None:
            try:
                client.close()
            except Exception:
                pass
        if state.get("pid") is not None:
            kill_process_tree(state["pid"])

    guard = LiveCreditGuard(limit=args.credit_cap, stall_timeout_s=args.stall_timeout_s,
                             rate_pin=rate_pin, on_trip=_on_trip)
    # See _ObservingUsageTracker: the guard owns its tracker privately and exposes no seam for
    # swapping it, so the smoke substitutes one here rather than editing the shipped launcher.
    guard._appserver_usage_tracker = tracker
    guard.start()

    poller = IdentityProbePoller(probe_argv)
    poller.start()

    task1, task2 = TASK_TEXTS[args.mcp]
    notes = [n for n in (auth_note,) if n]
    turns: list[dict] = []
    oracle_after_turn1: list[dict] = []
    boundary_index = 0
    notifications: list[dict] = []
    run_error: str | None = None
    env_backup = os.environ.get("CODEX_HOME")
    os.environ["CODEX_HOME"] = str(codex_home)
    started = time.monotonic()
    try:
        client = ObservingGate0Client(codex_path=codex_path,
                                       extra_args=[a for o in overrides for a in ("-c", o)],
                                       cwd=str(out_dir), transcript_path=transcript_path,
                                       credit_observer=guard.observe,
                                       audit_log_path=out_dir / "audit.jsonl",
                                       stderr_log_path=out_dir / "codex.stderr.log")
        state["client"] = client
        notifications = client.notifications
        client.connect()
        state["pid"] = client._transport.proc.pid
        try:
            # Any failure below -- most plausibly the credit guard killing codex, which closes its
            # stdin -- must still leave a written verdict: the raw evidence is already on disk in
            # the append-only transcript, and losing the analysis of it to a traceback would waste
            # the spend.
            client.initialize(timeout=args.handshake_timeout_s)
            thread_result = client.start_thread(cwd=str(out_dir), approvals_reviewer="user",
                                                 timeout=args.handshake_timeout_s)
            thread_id = _extract_thread_id(thread_result)

            for index, (task_text, timeout_s) in enumerate(
                    ((task1, args.turn1_timeout_s), (task2, args.turn2_timeout_s)), start=1):
                poller.sample_now(f"before_turn{index}")
                turn_result = client.send_request(
                    "turn/start",
                    build_turn_start_request(thread_id, [{"type": "text", "text": task_text}]),
                    timeout=args.handshake_timeout_s)
                turn_id = _extract_turn_id(turn_result)
                if turn_id is None:
                    raise SystemExit("turn/start returned no turn id -- the second-turn wait cannot "
                                      "be scoped and would return turn 1's notification instantly.")
                if any(t["turn_id"] == turn_id for t in turns):
                    raise SystemExit(f"turn/start reused turn id {turn_id!r} across turns.")
                end_note = client.wait_for_notification(DEFAULT_TURN_END_METHODS, timeout=timeout_s,
                                                         turn_id=turn_id)
                poller.sample_now(f"after_turn{index}")
                turns.append({
                    "index": index, "turn_id": turn_id,
                    "ended": end_note is not None,
                    "end_method": (end_note or {}).get("method"),
                    "end_status": (((end_note or {}).get("params") or {}).get("turn") or {}).get("status"),
                })
                if index == 1:
                    boundary_index = len(client.notifications)
                    oracle_after_turn1 = read_oracle_rows(world_dir)
                    if oracle_after_turn1:
                        (out_dir / "oracle.after_turn1.jsonl").write_text(
                            "".join(json.dumps(r, sort_keys=True) + "\n" for r in oracle_after_turn1),
                            encoding="utf-8", newline="\n")
                    if end_note is None:
                        notes.append("turn 1 never produced a terminal notification; turn 2 was "
                                      "still attempted so the boundary is exercised.")
        except Exception as exc:
            run_error = f"{type(exc).__name__}: {exc}"
            notes.append(f"run aborted before finishing both turns: {run_error}")
        finally:
            guard.finish()
            guard.join(timeout=10.0)
            client.close()
    finally:
        poller.stop()
        if env_backup is None:
            os.environ.pop("CODEX_HOME", None)
        else:
            os.environ["CODEX_HOME"] = env_backup
    wall_clock_s = round(time.monotonic() - started, 2)

    oracle_after_turn2 = read_oracle_rows(world_dir)
    usage_events = token_usage_by_turn(transcript_path)
    credits_result = guard.result or {}
    normalized_credits = (credits_result.get("final_total_normalized_credits")
                           if credits_result.get("final_total_normalized_credits") is not None
                           else credits_result.get("credits_at_trip", 0.0)) or 0.0

    verdict = {
        "schema_version": 1,
        # Deliberately NOT any kind eval/score_gate0.py or tools/check_gate0_codex.py reads.
        "kind": "gate0_appserver_two_turn_smoke",
        "is_gate0_attempt": False,
        "mcp": args.mcp,
        "model": args.model,
        "wall_clock_s": wall_clock_s,
        "turns": turns,
        "fact1_mcp_child_reused": classify_startup_status(list(notifications), boundary_index),
        "fact1_world_persisted": classify_world_continuity(oracle_after_turn1, oracle_after_turn2),
        "fact2_token_usage": (classify_token_usage(usage_events, turns[0]["turn_id"],
                                                    turns[1]["turn_id"])
                               if len(turns) == 2 else
                               {"thread_cumulative": None, "reason": "fewer than two turns ran"}),
        "token_usage_events": usage_events,
        "usage_tracker_regressions": tracker.regressions,
        "oracle_after_turn1": summarize_oracle(oracle_after_turn1),
        "oracle_after_turn2": summarize_oracle(oracle_after_turn2),
        "identity_probe_samples": poller.samples,
        "normalized_credits": normalized_credits,
        "cost_usd": (normalized_credits / rate_pin["credits_per_usd"]
                      if rate_pin["credits_per_usd"] else 0.0),
        "credit_breaker_tripped": bool(credits_result.get("tripped", False)),
        "credit_breaker_error": credits_result.get("error"),
        "run_error": run_error,
        "transcript_path": str(transcript_path),
        "world_dir": str(world_dir),
        "notes": notes,
    }
    (out_dir / "two-turn-smoke-verdict.json").write_text(
        json.dumps(verdict, indent=2, sort_keys=False) + "\n", encoding="utf-8", newline="\n")
    return verdict


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--model", required=True)
    p.add_argument("--out-dir", required=True,
                    help="throwaway output dir; refused if it resolves under runs/.")
    p.add_argument("--credit-rate-pin", required=True)
    p.add_argument("--mcp", choices=("docker", "stub"), required=True,
                    help="docker = the real Arm-R gb-mcp-world (both Fact-1 readings). stub = the "
                         "local ping server (codex-side reading only; use when the Docker daemon "
                         "is unavailable -- Fact 2 is unaffected either way).")
    p.add_argument("--repo-root", default=str(REPO_ROOT),
                    help="checkout supplying roms/ and runs/red_start.state for the read-only "
                         "docker mounts (a worktree may have neither).")
    p.add_argument("--docker-image", default="gb-mcp-world")
    # A single codex model turn re-sends the whole system prompt: MEASURED 2026-07-28, one trivial
    # `ping` turn cost 2.03 normalized credits, almost all of it input tokens. A cap of 2.0 killed
    # codex mid-turn-1. 25 is roughly 5x a plausible two-turn smoke and still 10x under the pinned
    # 250 combined ceiling.
    p.add_argument("--credit-cap", type=float, default=25.0)
    p.add_argument("--stall-timeout-s", type=float, default=float(STALL_TIMEOUT_S))
    p.add_argument("--turn1-timeout-s", type=float, default=300.0)
    p.add_argument("--turn2-timeout-s", type=float, default=180.0)
    p.add_argument("--handshake-timeout-s", type=float, default=120.0)
    p.add_argument("--codex-path", default=None)
    p.add_argument("--codex-home", default=None)
    p.add_argument("--codex-auth-source", default=None)
    p.add_argument("--i-understand-this-spends-money", action="store_true",
                    help="explicit spend gate, same discipline as "
                         "tools/gate0_appserver_paid_turn.ps1's -IUnderstandThisSpendsMoney.")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    if not args.i_understand_this_spends_money:
        raise SystemExit("--i-understand-this-spends-money is required: this smoke runs two REAL "
                          "paid codex turns.")
    if os.environ.get("OPENAI_API_KEY") or os.environ.get("CODEX_API_KEY"):
        raise SystemExit("OPENAI_API_KEY/CODEX_API_KEY is set; this run must use ChatGPT "
                          "subscription auth.")
    verdict = run_smoke(args)
    print(json.dumps({k: v for k, v in verdict.items()
                      if k not in ("identity_probe_samples", "token_usage_events")}, indent=2))
    fact1 = verdict["fact1_mcp_child_reused"].get("mcp_child_reused_in_turn2")
    fact2 = verdict["fact2_token_usage"].get("thread_cumulative")
    return 0 if (fact1 is True and fact2 is True) else 1


if __name__ == "__main__":
    raise SystemExit(main())
