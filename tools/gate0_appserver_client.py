"""Gate 0 `codex app-server` JSON-RPC-over-stdio client -- $0 PROTOTYPE.

Answers the server->client approval/elicitation/user-input requests that `codex exec` cannot
answer (closed stdin -> EOF -> decline -> "user cancelled MCP tool call", openai/codex#16685),
without any `--dangerously-bypass-approvals-and-sandbox` flag. See
reports/2026-07-23-gate0-appserver-spike.md (the spec this implements) and
reports/2026-07-22-codex-mcp-headless-trust-research.md (why `codex exec` can't be fixed
headlessly). This module can spawn `codex app-server` and drive `initialize`/`thread/start`, and
CAN build (but never sends) a `turn/start` request -- running a real turn is the one paid step
left to reports/2026-07-23-gate0-appserver-client-prototype.md.

Framing: newline-delimited JSON (JSONL), one JSON-RPC message per line, the `"jsonrpc":"2.0"`
header OMITTED on the wire. Confirmed from codex-rs/app-server/README.md's "Protocol" section
("Similar to MCP, `codex app-server` supports bidirectional communication using JSON-RPC 2.0
messages (with the `"jsonrpc":"2.0"` header omitted on the wire" / "stdio (--stdio or --listen
stdio://, default): newline-delimited JSON (JSONL)") and developers.openai.com/codex/app-server,
cross-checked against `JSONRPCRequest`/`JSONRPCNotification`/`JSONRPCResponse` in the generated
schema dump (codex-cli 0.144.3, `codex app-server generate-json-schema`) -- none of those declare
a `jsonrpc` field, and none of `codex app-server --help`'s transport docs mention Content-Length
framing (that's LSP, not this). This is NOT guessed.

Request AND response shapes below are copied verbatim from that same schema dump (ServerRequest.json,
ToolRequestUserInputParams/Response.json, McpServerElicitationRequestParams/Response.json,
PermissionsRequestApprovalParams/Response.json, CommandExecutionRequestApprovalParams/
Response.json, FileChangeRequestApprovalParams/Response.json, InitializeParams.json,
ThreadStartParams.json, JSONRPCRequest.json, JSONRPCResponse.json -- ALL of these are committed
under tests/fixtures/gate0_appserver/ for tests/test_gate0_appserver_client.py to check against, so
the `_HANDLERS` method names and the param field names this client reads are grounded against the
same ground truth as the responses, not hand-matched to the mock), not from memory.
"""
from __future__ import annotations

import json
import os
import subprocess
import threading
from pathlib import Path

# Overridable per-machine (this project runs on Windows/Ubuntu/Raspberry Pi -- see
# ~/.claude/CLAUDE.md "Env"); this default is the Windows path used for the 2026-07-23 spike.
DEFAULT_CODEX_PATH = r"C:\Users\Succe\AppData\Local\Programs\OpenAI\Codex\bin\codex.exe"

# Case-insensitive substrings that identify the "approve" option among a request_user_input
# question's offered `options` (spike report: this answers the #15824-regression "Approve app
# tool call?" prompt). First match wins; if none match, the first offered option is used; if no
# options are offered at all, FALLBACK_ANSWER is used (see pick_approve_label).
APPROVE_KEYWORDS = ("approve", "yes", "allow", "accept", "ok", "confirm")
FALLBACK_ANSWER = "Approve"

# PermissionGrantScope enum (PermissionsRequestApprovalResponse.json definitions).
PERMISSION_GRANT_SCOPES = ("turn", "session")

# InitializeCapabilities (v1/InitializeParams.json, definitions.InitializeCapabilities), both plain
# booleans, both default false server-side. `item/tool/requestUserInput` is marked EXPERIMENTAL in
# ServerRequest.json and gated by `experimentalApi`; `openai/form` elicitation mode
# (McpServerElicitationRequestParams.json) is gated by `mcpServerOpenaiFormElicitation`. Without
# declaring both true here, app-server never sends the requests this client exists to answer --
# committed as tests/fixtures/gate0_appserver/InitializeParams.json, asserted in
# test_initialize_declares_experimental_and_form_elicitation_capabilities.
INITIALIZE_CAPABILITIES = {"experimentalApi": True, "mcpServerOpenaiFormElicitation": True}


def resolve_codex_path() -> str:
    return os.environ.get("GATE0_CODEX_PATH", DEFAULT_CODEX_PATH)


def encode_jsonrpc_line(message: dict) -> bytes:
    """One JSON-RPC message -> one JSONL wire line. No `jsonrpc` key (see module docstring)."""
    return (json.dumps(message, separators=(",", ":")) + "\n").encode("utf-8")


def pick_approve_label(question: dict, keywords=APPROVE_KEYWORDS, fallback=FALLBACK_ANSWER) -> str:
    """Selects the approve option's `label` from a ToolRequestUserInputQuestion's `options`
    (HAPI #287 / the #15824-regression "Approve app tool call?" prompt is exactly this shape)."""
    options = question.get("options") or []
    for option in options:
        label = option.get("label", "")
        if any(keyword in label.lower() for keyword in keywords):
            return label
    if options:
        return options[0]["label"]
    return fallback


def build_elicitation_response() -> dict:
    """McpServerElicitationRequestResponse -- `content` is optional (schema: nullable, absent for
    decline/cancel) and omitted here: this $0 prototype has no real form data to fill in for
    `mode: "form"`/`"openai/form"` elicitations. The one paid turn must confirm whether the
    specific MCP server it exercises requires non-empty `content` to proceed past `accept`."""
    return {"action": "accept"}


def build_tool_user_input_response(params: dict, keywords=APPROVE_KEYWORDS,
                                    fallback=FALLBACK_ANSWER) -> dict:
    """ToolRequestUserInputResponse -- MUST be exactly `{"answers": {...}}` (HAPI #287: a
    missing/renamed `answers` field makes codex cancel the tool call). Deliberately does not read
    `params.get("autoResolutionMs")` anywhere -- PR #27256 established that field is
    contract-plumbing only (no built-in auto-accept timer), so this client always answers
    immediately and actively, never by waiting one out."""
    if "questions" not in params:
        # ToolRequestUserInputParams.questions is required (schema-confirmed) -- silently
        # returning {"answers": {}} here would look identical to "zero questions were asked" for
        # what may be a real, non-empty request: a protocol violation must fail loud, not degrade
        # quietly (asymmetric with the permissions/id ValueError guards below/above otherwise).
        raise ValueError("ToolRequestUserInputParams missing required 'questions' field")
    answers = {}
    for question in params["questions"]:
        if "id" not in question:
            # ToolRequestUserInputQuestion.id is required (schema-confirmed) -- a question missing
            # it is a protocol violation, not something to paper over with an empty/KeyError.
            raise ValueError(f"ToolRequestUserInputQuestion missing required 'id' field: {question!r}")
        answers[question["id"]] = {"answers": [pick_approve_label(question, keywords, fallback)]}
    return {"answers": answers}


def build_permissions_response(params: dict, scope: str = "session") -> dict:
    """PermissionsRequestApprovalResponse. Echoes back exactly the requested profile (README:
    "Only the granted subset matters on the wire" -- any permission omitted from the response is
    denied) so the grant is scoped to precisely what was asked, never a blanket bypass. `scope`
    defaults to "session" here (the schema's own default is "turn") because Gate 0's target
    scenario is one turn making several Docker-MCP tool calls that would otherwise each re-prompt
    for the same fileSystem/network access; "session" is still a bounded, revocable, per-request
    grant -- not `--dangerously-bypass-approvals-and-sandbox`. Configurable per call/instance."""
    if scope not in PERMISSION_GRANT_SCOPES:
        raise ValueError(f"invalid permission grant scope: {scope!r}")
    if "permissions" not in params:
        # PermissionsRequestApprovalParams.permissions is required (schema-confirmed) -- silently
        # echoing {} here would grant an empty RequestPermissionProfile (deny-all) for what may be
        # a real, non-empty request: a protocol violation must fail loud, not degrade to deny-all.
        raise ValueError("PermissionsRequestApprovalParams missing required 'permissions' field")
    return {"permissions": params["permissions"], "scope": scope}


def build_command_execution_response() -> dict:
    """CommandExecutionRequestApprovalResponse. Always the plain `accept` decision (not
    `acceptForSession`/an execpolicy or network-policy amendment) -- the narrowest approve that
    still lets the turn proceed."""
    return {"decision": "accept"}


def build_file_change_response() -> dict:
    """FileChangeRequestApprovalResponse. Same rationale as build_command_execution_response."""
    return {"decision": "accept"}


def build_turn_start_request(thread_id: str, input_items: list) -> dict:
    """Builds (does NOT send) a `turn/start` params body. Running a turn is the one paid step out
    of scope for this prototype -- nothing in this module calls send_request('turn/start', ...);
    a caller wanting the real thing must do so explicitly and deliberately, outside any $0 path."""
    return {"threadId": thread_id, "input": input_items}


# method -> (response builder, human-readable action for the audit log). Builders take `params`;
# the elicitation/command/file-change ones ignore it (fixed response) but keep the same signature.
_HANDLERS = {
    "mcpServer/elicitation/request": (lambda params, self: (build_elicitation_response(), "accept")),
    "item/tool/requestUserInput": (lambda params, self: (
        build_tool_user_input_response(params, self._approve_keywords, self._fallback_answer),
        "accept")),
    "item/permissions/requestApproval": (lambda params, self: (
        build_permissions_response(params, self.permission_scope), f"grant:{self.permission_scope}")),
    "item/commandExecution/requestApproval": (lambda params, self: (build_command_execution_response(), "accept")),
    "item/fileChange/requestApproval": (lambda params, self: (build_file_change_response(), "accept")),
}


class _StdioTransport:
    """Owns the real `codex app-server` subprocess and the JSONL stdio read/write loop. Never
    instantiated by the test suite (tests inject `send=` directly into Gate0AppServerClient) --
    except tests/test_gate0_appserver_client.py's stderr-drain tests, which DO spawn a real (stub)
    child to prove the deadlock fix against actual OS pipes, not a mock.

    codex's stderr is piped (stderr=subprocess.PIPE below) but codex is never told to be quiet on
    it, and nothing upstream of this fix ever read it: once codex writes enough stderr to fill the
    OS pipe buffer (~64KB, no reader draining it), codex's own write() call blocks and it stops
    servicing stdio entirely -- indistinguishable from an `initialize` hang. `_drain_stderr` below
    runs in a background daemon thread for the life of the subprocess so that pipe can never fill,
    regardless of whether a log path was supplied."""

    def __init__(self, codex_path: str, extra_args=(), cwd: str | None = None,
                 stderr_log_path: str | Path | None = None):
        self.proc = subprocess.Popen(
            [codex_path, "app-server", "--listen", "stdio://", *extra_args],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            bufsize=0, cwd=cwd,
        )
        self._write_lock = threading.Lock()
        self._stderr_log_path = Path(stderr_log_path) if stderr_log_path else None
        self._stderr_thread = threading.Thread(target=self._drain_stderr, daemon=True)
        self._stderr_thread.start()

    def _drain_stderr(self) -> None:
        # Runs for the whole subprocess lifetime. Tees verbatim to stderr_log_path if given (never
        # parsed/echoed into the transcript/audit -- codex's own diagnostic output is untrusted
        # content as far as this client's logs are concerned), but drains regardless of whether a
        # path was given -- the draining itself, not the logging, is what prevents the deadlock.
        log_file = None
        if self._stderr_log_path is not None:
            self._stderr_log_path.parent.mkdir(parents=True, exist_ok=True)
            log_file = open(self._stderr_log_path, "ab")
        try:
            for raw_line in iter(self.proc.stderr.readline, b""):
                if log_file is not None:
                    log_file.write(raw_line)
                    log_file.flush()
        finally:
            if log_file is not None:
                log_file.close()
            try:
                self.proc.stderr.close()
            except OSError:
                pass

    def send(self, message: dict) -> None:
        with self._write_lock:
            self.proc.stdin.write(encode_jsonrpc_line(message))
            self.proc.stdin.flush()

    def read_line(self) -> str | None:
        raw = self.proc.stdout.readline()
        if not raw:
            return None
        return raw.decode("utf-8").rstrip("\r\n")

    def close(self) -> None:
        try:
            self.proc.stdin.close()
        except OSError:
            pass
        self.proc.terminate()
        self._stderr_thread.join(timeout=5.0)


class Gate0AppServerClient:
    """Drives one `codex app-server` connection: `initialize` handshake, `thread/start`, and
    server->client request handlers for the four approval/elicitation/user-input methods above.

    For tests, pass `send=<recorder callable>` to bypass real process spawning entirely (an
    in-process fake peer then drives the protocol via handle_message()/handle_line()). For real
    use, call connect() (spawns codex app-server and starts the background reader thread)."""

    def __init__(self, *, send=None, codex_path: str | None = None, extra_args=(),
                 cwd: str | None = None, permission_scope: str = "session",
                 approve_keywords=APPROVE_KEYWORDS, fallback_answer: str = FALLBACK_ANSWER,
                 audit_log_path: str | Path | None = None,
                 stderr_log_path: str | Path | None = None):
        if permission_scope not in PERMISSION_GRANT_SCOPES:
            raise ValueError(f"invalid permission grant scope: {permission_scope!r}")
        self._send = send
        self._codex_path = codex_path or resolve_codex_path()
        self._extra_args = extra_args
        self._cwd = cwd
        self.permission_scope = permission_scope
        self._approve_keywords = approve_keywords
        self._fallback_answer = fallback_answer
        self._transport: _StdioTransport | None = None
        self._reader_thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._pending: dict[object, threading.Event] = {}
        self._results: dict[object, dict] = {}
        self._next_id = 1
        self.audit: list[dict] = []
        self._audit_log_path = Path(audit_log_path) if audit_log_path else None
        self._stderr_log_path = Path(stderr_log_path) if stderr_log_path else None

    # -- lifecycle (real subprocess only; not exercised by the mock test suite) --
    def connect(self) -> None:
        self._transport = _StdioTransport(self._codex_path, self._extra_args, self._cwd,
                                           stderr_log_path=self._stderr_log_path)
        self._send = self._transport.send
        self._reader_thread = threading.Thread(target=self._read_loop, daemon=True)
        self._reader_thread.start()

    def close(self) -> None:
        self._stop.set()
        if self._transport is not None:
            self._transport.close()

    def _read_loop(self) -> None:
        while not self._stop.is_set():
            line = self._transport.read_line()
            if line is None:
                return
            if line.strip():
                self.handle_line(line)

    # -- wire-level dispatch (exercised directly by the mock test suite) --
    def handle_line(self, line: str) -> None:
        self.handle_message(json.loads(line))

    def handle_message(self, message: dict) -> None:
        if "method" in message and "id" in message:
            self._handle_server_request(message)
        elif "id" in message and ("result" in message or "error" in message):
            self._handle_client_response(message)
        # Notifications from the server (thread/started, item/started, ...) carry no `id` and are
        # not needed to answer approvals/elicitations -- out of scope for this prototype.

    def _handle_client_response(self, message: dict) -> None:
        request_id = message["id"]
        self._results[request_id] = message
        event = self._pending.pop(request_id, None)
        if event is not None:
            event.set()

    def _handle_server_request(self, message: dict) -> None:
        method = message["method"]
        request_id = message["id"]
        params = message.get("params") or {}
        handler = _HANDLERS.get(method)
        if handler is None:
            # Left unresolved (not one of the request types this prototype answers), but LOGGED --
            # a paid-turn method-name mismatch/drift must be visible in the transcript, not a
            # silent no-op indistinguishable from "nothing happened".
            self._log(event="unhandled_server_request", method=method, request_id=request_id)
            return
        self._log(event="server_request", method=method, request_id=request_id,
                   thread_id=params.get("threadId"), turn_id=params.get("turnId"),
                   item_id=params.get("itemId"))
        result, action = handler(params, self)
        self._send({"id": request_id, "result": result})
        self._log(event="client_response", method=method, request_id=request_id, action=action)

    def _log(self, **fields) -> None:
        # ONLY method/ids/action -- never params/result (which may carry command text, file
        # diffs, or elicitation form content) so no secret value can leak through this audit trail.
        self.audit.append(fields)
        if self._audit_log_path is not None:
            with open(self._audit_log_path, "a", encoding="utf-8", newline="\n") as fh:
                fh.write(json.dumps(fields, sort_keys=True) + "\n")

    # -- client-initiated requests --
    def _next_request_id(self) -> int:
        request_id = self._next_id
        self._next_id += 1
        return request_id

    def send_request(self, method: str, params: dict, timeout: float = 30.0) -> dict:
        """Blocks for a response to a CLIENT-initiated request. This prototype only calls this
        for `initialize`/`thread/start`; sending `method="turn/start"` is the one paid step and is
        never done automatically anywhere in this module (see build_turn_start_request)."""
        if self._send is None:
            raise RuntimeError("not connected -- call connect() or pass send= for tests")
        request_id = self._next_request_id()
        event = threading.Event()
        self._pending[request_id] = event
        self._send({"id": request_id, "method": method, "params": params})
        if not event.wait(timeout):
            self._pending.pop(request_id, None)
            raise TimeoutError(f"{method} timed out waiting for a response")
        message = self._results.pop(request_id)
        if "error" in message:
            raise RuntimeError(f"{method} failed: {message['error']}")
        return message["result"]

    def send_notification(self, method: str, params: dict | None = None) -> None:
        if self._send is None:
            raise RuntimeError("not connected -- call connect() or pass send= for tests")
        message = {"method": method}
        if params is not None:
            message["params"] = params
        self._send(message)

    def initialize(self, client_name: str = "gate0_appserver_client",
                    client_version: str = "0.1.0", timeout: float = 30.0) -> dict:
        result = self.send_request("initialize", {
            "clientInfo": {"name": client_name, "version": client_version},
            "capabilities": dict(INITIALIZE_CAPABILITIES),
        }, timeout=timeout)
        self.send_notification("initialized")
        return result

    def start_thread(self, cwd: str, approvals_reviewer: str = "user", timeout: float = 30.0,
                      **extra_params) -> dict:
        """`approvalsReviewer="user"` is deliberate (spike report): it routes approval requests to
        THIS client instead of an auto-resolving reviewer (`auto_review`/`guardian_subagent`),
        which is the entire point of writing this client."""
        params = {"cwd": cwd, "approvalsReviewer": approvals_reviewer, **extra_params}
        return self.send_request("thread/start", params, timeout=timeout)
