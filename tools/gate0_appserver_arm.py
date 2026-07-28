"""tools/gate0_appserver_arm.py -- the Gate 0 ARM RUNNER: launches the real Gate 0 arms (Pokemon
Red + MiniWoB click-checkboxes) over `codex app-server` instead of the frozen `codex exec` recipe
(tools/run_gate0_codex.ps1), producing artifacts at the exact pinned paths
eval/fixtures/gate0_paid_source_pins.json names, for the FROZEN scorer (eval/score_gate0.py +
tools/check_gate0_codex.py) to read VERBATIM. Builds on the proven M1 unblock
(reports/2026-07-23-gate0-appserver-m1-confirmation.md): `codex app-server` answers the
`#15824`/`#16685` approval prompt `codex exec` cannot, via tools/gate0_appserver_client.py +
tools/gate0_appserver_launch.py (REUSED here, not duplicated -- see imports below).

THIS MODULE BUILDS AND $0-TESTS ONLY. `--dry-run` and `--seam-check` never spawn a real `codex` or
`docker run <real image>` process (the only real-docker call anywhere in this module,
`docker_image_inspect_id`, is a pure metadata query -- allowed per this build's own hard
constraints). A real paid run (`--model` + `--credit-rate-pin`, no `--dry-run`/`--seam-check`) is
built and refuses to run un-priced, but was never invoked by this build/test session -- the
orchestrator runs it.

=====================================================================================================
THIS MODULE'S OWN AUDIT IS NOT THE GATE 0 VERDICT (added 2026-07-25, adversarial review of PR #163)
=====================================================================================================

`_run_real()` writes its own `run-receipt.json:audit_overall`, scored by calling the frozen
`tools/check_gate0_codex.py::audit()` against `resolve_expected_pins()`'s output -- which reads
THIS module's own `eval/fixtures/gate0_expected_pins_{red,miniwob}.appserver.json` fixtures. That
is the ONLY consumer of the `.appserver.json` fixtures anywhere in this repo.

The actual Gate 0 scorer, `eval/score_gate0.py` (frozen, never edited by this module), does NOT
read those fixtures. It resolves `expected_pins` from `eval/fixtures/gate0_paid_source_pins.json`'s
own pre-registered `audit_paths.<arm>.expected_pins`, which points at the EXEC-path fixtures --
`eval/fixtures/gate0_expected_pins_{red,miniwob}.json`, no ".appserver" suffix -- not the ones this
module resolves against. Those exec fixtures still hold the literal
`CONSTRAINT:launch-invocation-dependent-recompute-at-signature` marker for config_sha256/
codex_mcp_list_sha256 (an app-server receipt can never equal that string) and a tool_schema_sha256
computed for the exec path's PowerShell `ConvertTo-Json -Compress` serialization, not this
launcher's `json.dumps(tools) + "\n"` bytes.

**Consequence: merging this PR does NOT unblock the paid Gate 0 verdict.** After this PR,
`run-receipt.json:audit_overall` for a real Arm R app-server run reads clean (`constancy_failures ==
[]`), but `eval/score_gate0.py` run against the SAME artifacts still returns `CONSTANCY_BREACH`/
`NO_GO` -- pinned to the exec fixtures via `gate0_paid_source_pins.json`, unaffected by anything in
this file. Repointing `gate0_paid_source_pins.json`'s `audit_paths.<arm>.expected_pins` at the
`.appserver.json` fixtures (so the app-server transport's own real pins become the pre-registered
source of truth) is a SEPARATE governance decision for David -- not made, and not implied, by this
build. See the PR body for the same caveat.

=====================================================================================================
THE TRANSCRIPT ADAPTER DECISION (flagged loudly, per the build-spec's "honesty > green" instruction)
=====================================================================================================

`tools/check_gate0_codex.py::audit()` (frozen, never edited) expects an EXEC-shaped JSONL transcript:
top-level `{"type": "item.completed", "item": {"type": "mcp_tool_call", "server": ..., "tool": ...}}`
and `{"type": "turn.completed", "usage": {four TOKEN_FIELDS}}` lines (confirmed by reading audit()
itself, plus tests/test_check_gate0_codex.py's own fixtures and tools/gate0_wake_boundary.py's
synthetic transcript -- all agree on this exact vocabulary). `codex app-server` instead speaks
JSON-RPC notifications: `{"method": "item/completed", "params": {"item": {"type": "mcpToolCall",
"server": ..., "tool": ...}}}` and `{"method": "thread/tokenUsage/updated", "params": {"tokenUsage":
{"total": {...camelCase...}}}}`.

`adapt_app_server_notifications_to_exec_shape()` below is a REAL ADAPTER (not a raw-dump fallback),
built because a faithful mapping IS possible for every event kind this build has concrete, captured
evidence for -- INCLUDING a 2026-07-24 fix (adversarial review of PR #157) that closed a real
false-`NO_LEAK` bug this section originally missed:

  * `item/completed` with `item.type == "mcpToolCall"` -> `item.completed` with the item's `type`
    renamed to `mcp_tool_call` -- CONFIRMED (byte-for-byte) against the real captured transcript
    quoted in reports/2026-07-23-gate0-appserver-m1-confirmation.md: `"server": "gate0_stub",
    "tool": "ping", "type": "mcpToolCall"`. The `server`/`tool` field NAMES already match what
    `check_gate0_codex._mcp_identity()` reads (`item.get("server")`/`item.get("tool")`) -- no
    renaming needed there, only the `type` value.
  * `item/completed` with `item.type == "agentMessage"` -> renamed to `agent_message` --
    CONFIRMED both sides: the app-server spelling is captured verbatim at
    reports/2026-07-23-gate0-appserver-m1-confirmation/transcript.jsonl lines 29-30, and the
    exec-side TARGET spelling (`agent_message`) is independently captured in a REAL `codex exec
    --json` transcript, reports/2026-07-22-gate0-paid-exec-noop-diagnosis.md lines 22-25.
  * `item/completed` with `item.type == "reasoning"` needs no rename at all -- the app-server
    capture (same transcript, lines 18-19) already spells it identically to `audit()`'s skip-list
    string.
  * `item/completed` with `item.type == "userMessage"` (the prompt echo, transcript lines 16-17)
    is DROPPED entirely -- no `item.*` line is emitted for it. This is CONFIRMED, not a guess:
    the real exec-shaped target transcript (reports/2026-07-22-gate0-paid-exec-noop-diagnosis.md)
    has NO user-message item of any spelling, so translating this one under ANY name would be a
    structural false-positive leak on every real, fully-compliant run -- proven empirically during
    PR #157's adversarial review (see "2026-07-24 fix" below).
  * `thread/tokenUsage/updated` -> tracked (via `_app_server_total_to_snake`, REUSED from
    tools/gate0_appserver_launch.py, not reimplemented) and, at `turn/completed`, folded into ONE
    `turn.completed.usage` line carrying the four TOKEN_FIELDS from the LATEST cumulative `total` --
    CONFIRMED shape from the same report's quoted `thread/tokenUsage/updated` notification.
  * `turn/completed` -> `turn.completed` (with the usage above, if any valid usage was observed).
    `turn/failed`/`turn/aborted` -> `turn.failed` (closest honest exec-vocabulary bucket for "the
    turn did not complete"; `check_gate0_codex.py` treats both as `run_failures` regardless of the
    precise sub-reason).
  * `item/started` (an in-progress item of any type) is DELIBERATELY DROPPED, never translated:
    `audit()` counts every `item.*` line generically by `item.type`, with no started-vs-completed
    distinction -- forwarding BOTH would double-count `primitive_action_events` for the same real
    tool call. Only the terminal `item/completed` becomes one exec-shaped line.
  * Everything else observed on the wire (`thread/started`, `thread/status/changed`,
    `serverRequest/resolved`, `account/rateLimits/updated`, the approval/elicitation SERVER
    REQUESTS this client answers, and every client-to-server message) is NOT translated. None of
    these carry model-authored task content or a tool-call outcome, so omitting them cannot hide a
    leak -- they are protocol/approval plumbing, not the thing `audit()`'s no-leak check exists to
    police.

**2026-07-24 fix (adversarial review of PR #157 found this BLOCKING, proven empirically, not by
inspection):** running the ORIGINAL version of this adapter (which renamed ONLY `mcpToolCall`,
passing `userMessage`/`agentMessage`/`reasoning` through unmapped) over the real, committed M1
transcript and feeding the result through the frozen, unmodified `audit()` produced
`audit_overall=NO_LEAK`, `leak_failures=['forbidden_item:...:userMessage',
'forbidden_item:...:agentMessage']` -- i.e. the adapter's own "honestly-flagged gap" below was NOT
merely a theoretical risk, it was a GUARANTEED failure on every real turn, confirmed against real
data. The fix above (confirmed `agentMessage`/`reasoning` handling + confirmed `userMessage` drop)
closes it; see `test_adapter_over_the_real_m1_transcript_produces_zero_leak_failures` (runs this
adapter over the actual committed transcript file, not a hand-built fixture, and asserts
`leak_failures == []` against the unmodified `audit()`) for the regression proof.

THE HONESTLY-FLAGGED GAP (now narrower than before the 2026-07-24 fix): for any item type OTHER
than the four now-confirmed ones above (`mcpToolCall`, `agentMessage`, `reasoning`, `userMessage`),
this repo still has **no committed app-server Item/ThreadItem schema dump** (only the four
approval/elicitation/permission schemas + JSONRPCRequest/Response + Initialize/ThreadStart are
committed under tests/fixtures/gate0_appserver/ -- confirmed by listing that directory; there is no
`Item.json`/`ThreadItem.json`). Guessing at any FURTHER item-type spelling (e.g. a shell/web/file
item, which would indicate a genuine leak, or some other content item this build has not observed)
would be exactly the kind of fabricated-mapping the build-spec says never to do ("do NOT fake
events; honesty > green"). This adapter therefore passes any type outside the four confirmed ones
through **verbatim, unmapped** -- `audit()` will then, on its own frozen and unmodified logic,
either skip it (only if the raw wire string happens to literally equal `"reasoning"` or
`"agent_message"` -- already covered above) or flag it `forbidden_item` otherwise. This remains a
deliberate FAIL-CLOSED choice for the genuinely unknown case, not a bug -- but the four item types
actually observed in the one real captured turn this build has evidence for are now all correctly
handled, closing the practical, guaranteed-to-fire gap the review found.

Both the ADAPTED (exec-shaped, what the frozen scorer reads) and the RAW (untouched app-server wire,
full fidelity) streams are written -- nothing is lost. `transcript.jsonl` (the pinned scorer path,
eval/fixtures/gate0_paid_source_pins.json audit_paths.<arm>.transcript) is the ADAPTED stream.
`transcript.raw_appserver.jsonl` (a sibling file, NOT a scorer-pinned path) is the complete raw tee.

ADDITIVE ONLY: this module IMPORTS (never edits) tools/gate0_appserver_client.py,
tools/gate0_appserver_launch.py, tools/gate0_credit_breaker.py, tools/gate0_codex_credit_rate.py,
tools/check_gate0_codex.py. It never touches tools/run_gate0_codex.ps1, world_mcp.py, core/,
games/, the brain, contracts, or any tool schema.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

from tools.check_gate0_codex import SERVER, TOOLS, audit
from tools.gate0_appserver_client import build_turn_start_request, resolve_codex_path
from tools.gate0_appserver_launch import (
    DEFAULT_TURN_END_METHODS,
    LiveCreditGuard,
    ObservingGate0Client,
    _app_server_total_to_snake,
    _extract_thread_id,
    _quote_toml,
    app_server_usage_notification_to_credit_event,
    build_overrides,
    kill_process_tree,
    seed_codex_auth,
)
from tools.gate0_codex_credit_rate import CreditRateNotPinned, load_credit_rate_pin
from tools.gate0_credit_breaker import LIMIT_NORMALIZED_CREDITS, STALL_TIMEOUT_S

REPO_ROOT = Path(__file__).resolve().parent.parent

# ---------------------------------------------------------------------------------------------
# Frozen-by-construction constants. SERVER_NAME/enabled-tools reuse tools/check_gate0_codex.py's
# own SERVER/TOOLS (never re-declared/duplicated -- guarantees this launcher can never silently
# drift from what the frozen audit() checks against).
# ---------------------------------------------------------------------------------------------

SERVER_NAME = SERVER  # "gate0_world"

# Verbatim from tools/run_gate0_codex.ps1 ($DeveloperInstruction) -- a single fixed string shared
# by BOTH arms (not templated per arm), confirmed by reading that script.
DEVELOPER_INSTRUCTION = (
    "Use only gate0_world MCP tools. Never use shell, files, web, tool search, connectors, "
    "or other MCP servers."
)
# Verbatim from tools/run_gate0_codex.ps1 ($CommonTask).
COMMON_TASK_SUFFIX = (
    "Use only the connected world MCP tools and screen-derived state. Do not use shell, files, "
    "web, tool search, or connectors. Begin by observing. Stop when the stated task is complete."
)
# Verbatim task sentences ($TaskSentence per arm, tools/run_gate0_codex.ps1).
ARM_TASK_SENTENCES = {
    "red": ("From the fresh bedroom start, obtain your first Pokemon from Professor Oak and win "
            "the first rival battle."),
    "miniwob": ("Complete five fresh episodes of the browser click-checkboxes task from their "
                "on-screen instructions using screen pixels and ordinary mouse and keyboard "
                "controls."),
}
# Pinned BY IMMUTABLE IMAGE ID (scout build-spec / eval/fixtures/gate0_expected_pins_*.json).
ARM_IMAGE_TAGS = {"red": "gb-mcp-world", "miniwob": "miniwob-world"}
ARM_IMAGE_IDS = {
    "red": "sha256:c889c344bd6442292ab8c8b63c4cbdadfc37b988a969f7629c71a268d6325d3e",
    "miniwob": "sha256:ee12a2f0e54a798458568fea4730f770ede062956dd205afd7bf8290fa091ae4",
}
# Cheap-bar per-arm SOFT caps (reports/2026-07-18-gate0-prereg.md) -- informational warning only.
# The single HARD kill ceiling stays tools/gate0_credit_breaker.LIMIT_NORMALIZED_CREDITS (250),
# imported above, never re-declared.
ARM_SOFT_CREDIT_CAPS = {"red": 125, "miniwob": 50}
HARD_CREDIT_CAP = LIMIT_NORMALIZED_CREDITS
DEFAULT_WALL_CLOCK_S = 3600.0  # matches tools/run_gate0_codex.ps1's Invoke-BreakerSupervisedExec default
TOKEN_FIELDS = ("input_tokens", "cached_input_tokens", "output_tokens", "reasoning_output_tokens")
# The shared Gate0AppServerClient.send_request default (30s) is fine for the mocked/dry-run peers
# (instant), but a real `codex app-server` initialize/thread-start handshake can be slow-but-finite
# (e.g. an auth refresh) -- measured normal response is 0.17-2.0s, so 120s is pure jitter margin,
# not a real expected wait. Applied ONLY at _run_real's run_gate0_arm_turn call below.
REAL_RUN_HANDSHAKE_TIMEOUT_S = 120.0


def task_text_for(arm: str) -> str:
    return ARM_TASK_SENTENCES[arm] + "\n" + COMMON_TASK_SUFFIX + "\n"


# ---------------------------------------------------------------------------------------------
# TOML rendering -- byte-exact reconstruction of tools/run_gate0_codex.ps1's $BrainConfigText/
# $WorldConfigText herestrings. VERIFIED (this build, $0): the render below reproduces the FROZEN
# brain_config_sha256 pin (ab7e54c1785f5d8be4352bbe0f85edb37cda68cf56df2128d61df025c1041fc3, both
# eval/fixtures/gate0_expected_pins_red.json and _miniwob.json) exactly, for
# model="gpt-5.6-sol"/the DEVELOPER_INSTRUCTION above -- confirmed by hand computation during this
# build, not asserted on faith. The critical, easy-to-miss detail: tools/run_gate0_codex.ps1 itself
# is CRLF-line-ended on disk (confirmed via raw byte inspection; no .gitattributes eol=lf override
# for *.ps1), and PowerShell here-strings preserve the SOURCE FILE's literal newline bytes as part
# of the string content -- so every INTERNAL line break in the rendered TOML is "\r\n", with only
# the single trailing newline (from the script's own literal "+ `n"` append) a bare "\n". Getting
# this wrong (e.g. rendering with all-"\n") silently produces a DIFFERENT hash that would never
# match the frozen pin -- this was caught and fixed during this build by direct hash comparison.
# task_sha256 (TASK.md) has no such CRLF subtlety: `$Task = $TaskSentence + "`n" + $CommonTask +
# "`n"` uses a double-quoted backtick-n ESCAPE (always a bare LF, independent of file encoding),
# also independently verified against both frozen task_sha256 pins during this build.
# ---------------------------------------------------------------------------------------------

def render_brain_config_toml(model: str, developer_instructions: str) -> str:
    lines = [
        f"model = {_quote_toml(model)}",
        'forced_login_method = "chatgpt"',
        'approval_policy = "never"',
        'sandbox_mode = "read-only"',
        'web_search = "disabled"',
        f"developer_instructions = {_quote_toml(developer_instructions)}",
        "",
        "[history]",
        'persistence = "none"',
        "",
        "[features]",
        "shell_tool = false",
        "skill_mcp_dependency_install = false",
        "apps = false",
        "goals = false",
        "hooks = false",
        "memories = false",
        "multi_agent = false",
        "",
        "[apps._default]",
        "enabled = false",
    ]
    return "\r\n".join(lines) + "\n"


def render_world_config_toml(server: str, mcp_command: str, mcp_args: list, mcp_cwd: str,
                              enabled_tools: list) -> str:
    args_toml = ", ".join(_quote_toml(a) for a in mcp_args)
    tools_toml = ", ".join(_quote_toml(t) for t in enabled_tools)
    lines = [
        f"[mcp_servers.{server}]",
        f"command = {_quote_toml(mcp_command)}",
        f"args = [{args_toml}]",
        f"cwd = {_quote_toml(mcp_cwd)}",
        "required = true",
        "enabled = true",
        f"enabled_tools = [{tools_toml}]",
        'default_tools_approval_mode = "auto"',
        # app-server-necessary addition (unlike the exec path): gate0_world is a lazy-boot MCP
        # server -- the FIRST real tool call inside the paid turn boots PyBoy+ROM (~30-40s) before
        # it can respond. codex's per-call/startup default is null (unmeasured server default);
        # 90s is confirmed-real config (codex-cli 0.144.3 `mcp_servers.<name>.tool_timeout_sec`/
        # `startup_timeout_sec`, empirically checked via `codex mcp get --json`, not guessed) and
        # covers the boot with margin without touching any other pinned field.
        "tool_timeout_sec = 90",
        "startup_timeout_sec = 90",
    ]
    return "\r\n".join(lines) + "\n"


def render_full_config_toml(brain_text: str, world_text: str) -> str:
    # $ConfigText = $BrainConfigText + "`n" + $WorldConfigText (tools/run_gate0_codex.ps1) -- one
    # more bare LF join between the two already-newline-terminated blocks.
    return brain_text + "\n" + world_text


def build_docker_mcp_args(arm: str, image_id: str, world_dir: Path,
                           repo_root: Path = REPO_ROOT) -> list[str]:
    """Exact per-arm docker invocation from tools/run_gate0_codex.ps1's $McpArgs (BY IMMUTABLE
    IMAGE ID, never a mutable tag)."""
    if arm == "red":
        roms = repo_root / "roms"
        state = repo_root / "runs" / "red_start.state"
        return ["run", "-i", "--rm", "--network", "none",
                "--mount", f"type=bind,source={roms},target=/app/roms,readonly",
                "--mount", f"type=bind,source={state},target=/app/red_start.state,readonly",
                "--mount", f"type=bind,source={world_dir.resolve()},target=/app/world",
                image_id, "--game", "pokemon_red", "--init-state", "/app/red_start.state",
                "--out", "/app/world", "--keep-frames"]
    if arm == "miniwob":
        seeds = repo_root / "eval" / "fixtures" / "gate0_miniwob_paid_seeds.json"
        return ["run", "-i", "--rm", "--network", "none",
                "--mount", f"type=bind,source={seeds},target=/app/seeds.json,readonly",
                "--mount", f"type=bind,source={world_dir.resolve()},target=/app/world",
                image_id, "--game", "miniwob_click_checkboxes", "--seeds-file", "/app/seeds.json",
                "--out", "/app/world"]
    raise ValueError(f"unknown arm: {arm!r}")


# ---------------------------------------------------------------------------------------------
# Git-blob hashing -- SAME CONTRACT as world_mcp.py::code_sha256() (git-blob-at-HEAD, "UNHASHABLE"
# on any dirty working tree), reimplemented (not imported): world_mcp.py redirects the process's
# real stdout to stderr as an IMPORT-TIME side effect (its own module docstring: "stdout is the
# JSON-RPC channel" -- see lines 30-38 of that file), which would corrupt this launcher's own
# stdout/pytest output the instant it was imported. world_mcp.py is on the frozen do-not-edit list
# regardless, so this small, independent reimplementation is the only safe option.
# ---------------------------------------------------------------------------------------------

def git_blob_sha256(repo_root: Path, rel_path: str) -> str:
    target = repo_root / rel_path
    try:
        rel = target.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        return "UNHASHABLE"
    try:
        clean = subprocess.run(["git", "diff", "--quiet", "HEAD", "--", rel],
                                cwd=repo_root, capture_output=True)
        if clean.returncode != 0:
            return "UNHASHABLE"
        blob = subprocess.run(["git", "show", f"HEAD:{rel}"], cwd=repo_root,
                               capture_output=True, check=True)
    except Exception:
        return "UNHASHABLE"
    return hashlib.sha256(blob.stdout).hexdigest()


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# ---------------------------------------------------------------------------------------------
# Real, $0 (free) preflight probes -- docker/codex invocations. `docker_image_inspect_id` is the
# ONE real-image docker call this build's hard constraints allow ("a pure `docker image inspect`
# -- allowed"); the rest are implemented for the orchestrator's real launch and are NEVER invoked
# by this build's own tests (mocked/monkeypatched there) or by any $0 path in this session.
# ---------------------------------------------------------------------------------------------

# Hang-safety backstop for every docker/codex subprocess call below (found and fixed during this
# build's own smoke test: with Docker Desktop's daemon unreachable -- the same state
# tools/gate0_appserver_launch.py's module docstring already documents for this host -- a bare
# `docker image inspect` call hung indefinitely rather than failing fast, leaking an orphaned
# docker.exe process. None of these calls are on the credit-breaker's own kill path (that path's
# timeout discipline is tools/gate0_credit_breaker.STALL_TIMEOUT_S / run_breaker, untouched); this
# is a separate, narrower guard for the free preflight probes themselves.
_SUBPROCESS_TIMEOUT_S = 60.0


def resolve_docker_path() -> str:
    path = shutil.which("docker")
    if not path:
        raise RuntimeError("docker executable not found on PATH")
    return path


def docker_image_inspect_id(docker_path: str, image_ref: str) -> str:
    """Pure metadata query -- no container is started. Returns the immutable `sha256:...` ID."""
    try:
        result = subprocess.run([docker_path, "image", "inspect", "--format", "{{.Id}}", image_ref],
                                 capture_output=True, text=True, timeout=_SUBPROCESS_TIMEOUT_S)
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"docker image inspect timed out for {image_ref!r} (daemon "
                           "unreachable?)") from exc
    image_id = (result.stdout or "").strip()
    if result.returncode != 0 or not image_id.startswith("sha256:"):
        raise RuntimeError(f"docker image inspect failed for {image_ref!r}: {result.stderr!r}")
    return image_id


def docker_image_code_hashes(docker_path: str, image_id: str) -> dict:
    """Runs the frozen world image's own Python to hash world_mcp.py/core/miniwob_world.py INSIDE
    the image -- same $HashProgram as tools/run_gate0_codex.ps1. Spawns a real container from the
    real pinned image: real-mode only, never invoked by this build's own $0 tests."""
    hash_program = (
        "import hashlib,json,sys; print(json.dumps({p: hashlib.sha256(open(p, 'rb').read())"
        ".hexdigest() for p in sys.argv[1:]}, sort_keys=True))"
    )
    try:
        result = subprocess.run(
            [docker_path, "run", "--rm", "--network", "none", "--entrypoint", "python", image_id,
             "-c", hash_program, "/app/world_mcp.py", "/app/core/miniwob_world.py"],
            capture_output=True, text=True, timeout=_SUBPROCESS_TIMEOUT_S)
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"docker run (code-hash probe) timed out for image {image_id}") from exc
    if result.returncode != 0:
        raise RuntimeError(f"could not inspect code inside image {image_id}: {result.stderr!r}")
    return json.loads(result.stdout.strip())


def docker_tools_list(docker_path: str, mcp_args: list[str]) -> list[dict]:
    """The same 3-line JSON-RPC initialize/initialized/tools-list handshake
    tools/run_gate0_codex.ps1 runs directly against the frozen image -- lazy, does not boot the
    emulator/browser. Spawns a real container: real-mode only, never invoked by this build's $0
    tests."""
    rpc = "\n".join([
        json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                    "params": {"protocolVersion": "2024-11-05", "capabilities": {},
                               "clientInfo": {"name": "gate0-appserver-arm", "version": "1"}}}),
        json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}}),
        json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}),
    ]) + "\n"
    try:
        result = subprocess.run([docker_path, *mcp_args], input=rpc, capture_output=True,
                                 text=True, timeout=_SUBPROCESS_TIMEOUT_S)
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("world MCP tools/list handshake timed out") from exc
    if result.returncode != 0:
        raise RuntimeError(f"world MCP tools/list handshake failed: {result.stderr!r}")
    responses = [json.loads(line) for line in result.stdout.splitlines() if line.strip()]
    tools_response = [r for r in responses if r.get("id") == 2]
    if len(tools_response) != 1 or "tools" not in (tools_response[0].get("result") or {}):
        raise RuntimeError("world MCP did not return exactly one tools/list result")
    return tools_response[0]["result"]["tools"]


def codex_mcp_list_json(codex_path: str, codex_home: str, overrides: list[str]) -> str:
    """`codex -c ... mcp list --json` under an isolated CODEX_HOME -- a FREE command (no model
    call, no auth needed; tools/run_gate0_codex.ps1's own comment: "This command does not call a
    model and needs no authentication"). Still a real codex.exe invocation -- real-mode only,
    never invoked by this build's own $0 tests (this build's hard constraints permit only
    `docker image inspect`, not any codex invocation, free or otherwise)."""
    args = [codex_path]
    for override in overrides:
        args += ["-c", override]
    args += ["mcp", "list", "--json"]
    env = {**os.environ, "CODEX_HOME": codex_home}
    try:
        result = subprocess.run(args, capture_output=True, text=True, env=env,
                                 timeout=_SUBPROCESS_TIMEOUT_S)
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("codex mcp list --json timed out") from exc
    if result.returncode != 0:
        raise RuntimeError(f"codex rejected the isolated explicit MCP configuration: {result.stderr!r}")
    return result.stdout.strip()


# ---------------------------------------------------------------------------------------------
# Receipt construction (schema_version 2, the 20 PIN_FIELDS tools/check_gate0_codex.py checks).
# `paid_execution_enabled` stays `False` -- that field's CONTRACT (per its own frozen pin sourcing
# note) is "the launcher contains no `codex exec` path", i.e. it is structural, not "did this run
# spend money": this launcher invokes `codex app-server`, never `codex exec`, so the field's
# literal meaning still holds for the app-server transport. `readiness` stays
# "NO_GO_INSUFFICIENT_WAKES" -- wake accounting is deferred project-wide (2026-07-21 amendment,
# reports/2026-07-21-gate0-wake-grounding.md), unaffected by the transport change.
# ---------------------------------------------------------------------------------------------

def build_handshake_receipt(*, arm: str, model: str, codex_version: str, codex_path: str,
                             codex_executable_sha256: str, mcp_tools_observed: list[str],
                             brain_config_sha256: str, task_sha256: str, config_sha256: str,
                             codex_mcp_list_sha256: str, tool_schema_sha256: str,
                             host_code_sha256: dict, image_code_sha256: dict) -> dict:
    return {
        "schema_version": 2,
        "arm": arm,
        "readiness": "NO_GO_INSUFFICIENT_WAKES",
        "paid_execution_enabled": False,
        "auth_method": "chatgpt",
        "planned_model": model,
        "codex_version": codex_version,
        "codex_path": codex_path,
        "codex_executable_sha256": codex_executable_sha256,
        "critical_config_transport": "explicit_cli_overrides",
        "mcp_servers_observed": [SERVER_NAME],
        "mcp_tools_observed": mcp_tools_observed,
        "brain_config_sha256": brain_config_sha256,
        "task_sha256": task_sha256,
        "config_sha256": config_sha256,
        "codex_mcp_list_sha256": codex_mcp_list_sha256,
        "tool_schema_sha256": tool_schema_sha256,
        "world_image_tag": ARM_IMAGE_TAGS[arm],
        "world_image_id": ARM_IMAGE_IDS[arm],
        "host_code_sha256": host_code_sha256,
        "image_code_sha256": image_code_sha256,
    }


# ---------------------------------------------------------------------------------------------
# Expected-pins resolution -- closes the app-server expected-pins gap: the first real Gate 0 Arm R
# app-server run reported a CONSTANCY_BREACH from `check_gate0_codex.audit()` for exactly the two
# fields eval/fixtures/gate0_expected_pins_{red,miniwob}.appserver.json mark
# `CONSTRAINT:launch-invocation-dependent-recompute-at-signature` (config_sha256,
# codex_mcp_list_sha256): they embed the launch OutputDir's absolute mount paths, so no single
# static fixture value can ever equal a real receipt's value -- `_expected_failures()` (frozen,
# never edited) would report `pin_mismatch:*` for these two fields on EVERY real run, forever.
#
# tools/check_gate0_codex.py is off-limits (frozen) and, on inspection, was never actually fixed
# for this on the exec path either: the exec path's OWN frozen fixture documents the identical
# CONSTRAINT marker for these two fields with the identical "recompute at signature" recipe
# (eval/fixtures/gate0_expected_pins_red.json:_source_config_sha256), and
# reports/2026-07-21-gate0-readiness-final-v2.md Sec.3 shows a REAL exec-path receipt hitting this
# EXACT SAME `pin_mismatch:config_sha256`/`pin_mismatch:codex_mcp_list_sha256` when audited against
# the raw static fixture -- masked only because that receipt had no real transcript (leak_failures
# forced `audit_overall=NO_LEAK` before constancy_failures could surface as the verdict). No exec-path
# code ever taught check_gate0_codex.py to treat the CONSTRAINT marker as anything but a literal
# string to compare against -- so this fix does not either. The resolution below happens one layer
# ABOVE check_gate0_codex.py, in this launcher, exactly where the exec path's own signature
# mechanism (eval/fixtures/gate0_signature.json's `expected_config_sha256`: "this launch's freshly
# computed handshake-receipt.json:config_sha256") was always meant to operate -- but done in code,
# automatically, at $0, since this launcher already renders config.toml/codex-mcp-list.json and
# builds the receipt entirely BEFORE the real paid turn spawns (see _run_real).
# ---------------------------------------------------------------------------------------------

LAUNCH_INVOCATION_DEPENDENT_MARKER = "CONSTRAINT:launch-invocation-dependent-recompute-at-signature"
LAUNCH_INVOCATION_DEPENDENT_FIELDS = ("config_sha256", "codex_mcp_list_sha256")


def resolve_expected_pins(base_expected: dict, *, config_sha256: str, codex_mcp_list_sha256: str) -> dict:
    """Substitutes the two launch-invocation-dependent PIN_FIELDS in `base_expected` (the committed
    eval/fixtures/gate0_expected_pins_{arm}.appserver.json, which holds
    LAUNCH_INVOCATION_DEPENDENT_MARKER for both by documented design -- see the block comment
    above) with THIS run's own real values, so tools/check_gate0_codex.py::_expected_failures()
    compares against a real hash instead of a placeholder it can never match.

    HONEST STATEMENT OF WHAT THIS DOES AND DOES NOT PROVE (rewritten 2026-07-25, adversarial
    review of PR #163 correction 2 -- the previous version of this docstring argued the
    substituted values are "model-independent" as if that made the resulting comparison
    informative; it does not, and that was a non-sequitur):

    config_sha256/codex_mcp_list_sha256 are LAUNCH-INVOCATION-DEPENDENT -- they embed this run's
    absolute out-dir mount paths, so no single static fixture value can ever equal a real receipt's
    value (see the block comment above). Because of that, there is no way to pin them statically,
    and the only value this function CAN compare the post-turn receipt against is the SAME run's
    own pre-turn receipt value for those two fields. That makes the resulting
    `_expected_failures()` check for exactly these two fields a TAUTOLOGY (X compared against X):
    it can never catch a real config/mcp-list drift by itself. It is not a "did this run start from
    the right config" proof for these two fields -- it never was, and this rewrite does not pretend
    otherwise.

    THIS IS NOT A REGRESSION. Before this fix, the fixture held the literal marker string
    "CONSTRAINT:launch-invocation-dependent-recompute-at-signature" verbatim as the expected value,
    so `_expected_failures()` compared a real hash against that literal string and ALWAYS failed --
    on every real run, forever, regardless of whether the config actually drifted. An always-fail
    check and an always-pass (tautological) check both carry the same zero bits of information
    about whether THIS run's config matches what was intended: neither one is capable of catching a
    real drift. Swapping "always wrong" for "always right" on these two fields is a usability fix
    (an honest run no longer reports a false CONSTANCY_BREACH), not a loss of any real coverage that
    existed before.

    WHAT STILL ACTUALLY GUARDS config/mcp-list/tool-schema integrity, independent of this
    substitution: (1) tools/check_gate0_codex.py::_artifact_failures (frozen, never edited) --
    re-hashes the on-disk config.toml/codex-mcp-list.json/mcp-tools.json against the receipt inside
    audit() itself, catching any drift between what the receipt CLAIMS and what is actually on disk
    at audit time; (2) verify_launch_signature_unchanged() (below) -- a narrower, fail-fast
    duplicate of that same re-hash, run immediately after the turn, before this substitution ever
    runs; (3) the 18 other real, independently-frozen PIN_FIELDS in `base_expected`, untouched by
    this function: brain_config_sha256 (covers approval_policy/sandbox_mode/web_search/features/
    history/developer_instructions -- i.e. the BRAIN half of config.toml), task_sha256, world_image_id
    (+world_image_tag), the mcp_servers_observed/mcp_tools_observed inventory, codex_executable_sha256,
    host_code_sha256/image_code_sha256 (host/image code parity), and now a REAL, re-derived
    tool_schema_sha256 (see the block comment above and the fixtures' own `_tool_schema_sha256_note`)
    -- none of these are tautological; each is a real, independently-sourced pinned value a genuine
    drift can still trip.

    WHAT IS NOW UNGUARDED as a direct consequence: the WORLD half of
    render_world_config_toml()/build_docker_mcp_args() that is not covered by any OTHER pin above --
    specifically `default_tools_approval_mode`, `tool_timeout_sec`/`startup_timeout_sec`,
    `required`/`enabled`, the presence of `--network none`, the `readonly` flag on the ROM/state
    mounts, and the exact `--out`/`--init-state` arguments. A change to any of those fields changes
    config_sha256 (so it WOULD have been caught by the frozen exec-path recipe's discipline of
    hand-verifying a real recompute against a static pin), but because config_sha256 is now compared
    tautologically against itself for the app-server path, none of those specific fields has an
    independent pin catching drift in them today. Closing that gap (a real, field-level pin on the
    world half of config.toml, analogous to brain_config_sha256) is future work, not done here.

    Every other PIN_FIELD in `base_expected` (the 18 real, independently-frozen constants: model,
    world_image_id, tool_schema_sha256, etc.) is returned untouched -- this function only ever
    touches the two documented CONSTRAINT fields, and refuses (fail loud, not a silent overwrite)
    if either does not already hold that exact marker, so a future edit that accidentally puts a
    real hash in the fixture is caught immediately rather than silently disabled."""
    for field in LAUNCH_INVOCATION_DEPENDENT_FIELDS:
        if base_expected.get(field) != LAUNCH_INVOCATION_DEPENDENT_MARKER:
            raise ValueError(
                f"resolve_expected_pins: base_expected[{field!r}] is not the documented "
                f"{LAUNCH_INVOCATION_DEPENDENT_MARKER!r} marker (got {base_expected.get(field)!r}) "
                "-- refusing to silently overwrite what looks like an already-real pinned value.")
    resolved = dict(base_expected)
    resolved["config_sha256"] = config_sha256
    resolved["codex_mcp_list_sha256"] = codex_mcp_list_sha256
    return resolved


def verify_launch_signature_unchanged(receipt: dict, out_dir: Path) -> None:
    """Fails loud (SystemExit), before resolve_expected_pins()/audit() ever run, if config.toml or
    codex-mcp-list.json on disk no longer hash to what `receipt` recorded when it was built --
    entirely BEFORE the real codex app-server turn spawned (_run_real builds and writes the receipt
    before calling run_gate0_arm_turn()). A mismatch here means one of these files was touched
    DURING the turn (codex app-server itself, a stray process, a bug) between render and run --
    this is the concrete "proving nothing changed between render and run" check
    resolve_expected_pins()'s substitution depends on for its own honesty.

    tools/check_gate0_codex.py::_artifact_failures (frozen, never edited) performs the identical
    re-hash-and-compare independently, inside audit() itself, and would also catch this as
    `artifact_hash_mismatch:config_sha256`/`codex_mcp_list_sha256` -- this is a narrower, arm-level,
    fail-fast duplicate with an immediate, named error, not a replacement for that frozen check."""
    checks = {
        "config_sha256": out_dir / "launch" / ".codex" / "config.toml",
        "codex_mcp_list_sha256": out_dir / "codex-mcp-list.json",
    }
    for field, path in checks.items():
        observed = _sha256_file(path)
        expected = receipt.get(field)
        if observed != expected:
            raise SystemExit(
                f"launch signature mismatch: {path} changed between render (pre-turn receipt "
                f"recorded {expected}) and now ({observed}) -- refusing to resolve expected pins "
                "against a drifted/tampered launch artifact.")


# ---------------------------------------------------------------------------------------------
# THE TRANSCRIPT ADAPTER (see module docstring for the full decision writeup).
# ---------------------------------------------------------------------------------------------

# CONFIRMED renames -- both sides of evidence, not a guess: the app-server SPELLING is captured
# verbatim in reports/2026-07-23-gate0-appserver-m1-confirmation/transcript.jsonl (mcpToolCall:
# lines 20/26; agentMessage: lines 29/30), and the exec-side TARGET spelling is independently
# captured in reports/2026-07-22-gate0-paid-exec-noop-diagnosis.md (a REAL `codex exec --json`
# transcript, lines 22-25): its item types are exactly `agent_message`/`mcp_tool_call` -- and
# critically, NO user-message item of any spelling at all. "reasoning" needs no entry here: the
# app-server capture (lines 18/19) already spells it identically to audit()'s skip-list string.
_CONFIRMED_ITEM_TYPE_RENAMES = {"mcpToolCall": "mcp_tool_call", "agentMessage": "agent_message"}
# `userMessage` (app-server transcript lines 16/17) is the PROMPT ECHO -- the exec-shaped target
# vocabulary has no user-message item at all (confirmed above), so translating it under ANY
# spelling would be a structural false-positive leak on every real, fully-compliant run. DROPPED
# entirely: unlike a genuinely-unknown type (passed through unmapped, left to audit()'s own
# fail-closed judgment), this one is CONFIRMED to have no exec-shape counterpart, so no item.*
# line is emitted for it at all -- this is a targeted omission, not a guess.
_DROPPED_ITEM_TYPES = frozenset({"userMessage"})


def adapt_app_server_notifications_to_exec_shape(notifications: list[dict]) -> list[dict]:
    events: list[dict] = []
    latest_valid_usage: dict | None = None
    usage_stream_had_a_malformed_event = False
    for note in notifications:
        method = note.get("method")
        params = note.get("params") or {}
        if method == "item/completed":
            item = params.get("item")
            if not isinstance(item, dict):
                continue
            raw_type = item.get("type")
            if raw_type in _DROPPED_ITEM_TYPES:
                continue  # confirmed no exec-shape counterpart -- see the constants above.
            adapted_item = dict(item)
            if raw_type in _CONFIRMED_ITEM_TYPE_RENAMES:
                adapted_item["type"] = _CONFIRMED_ITEM_TYPE_RENAMES[raw_type]
            # else: pass the raw, unmapped type through verbatim -- includes "reasoning" (already
            # matches, no rename needed) and any genuinely unconfirmed type (deliberate fail-closed
            # default, see module docstring's "honestly-flagged gap").
            events.append({"type": "item.completed", "item": adapted_item})
        elif method == "thread/tokenUsage/updated":
            total = (params.get("tokenUsage") or {}).get("total")
            if isinstance(total, dict):
                try:
                    latest_valid_usage = _app_server_total_to_snake(total)
                except ValueError:
                    usage_stream_had_a_malformed_event = True
        elif method == "turn/completed":
            turn_event: dict = {"type": "turn.completed"}
            if latest_valid_usage is not None and not usage_stream_had_a_malformed_event:
                turn_event["usage"] = dict(latest_valid_usage)
            # else: no `usage` key at all -- audit() correctly reports accounting_failures
            # ("missing_usage:...") rather than this adapter fabricating a usage dict from a
            # stream it never validly observed.
            events.append(turn_event)
        elif method in ("turn/failed", "turn/aborted"):
            events.append({"type": "turn.failed"})
        # Everything else (thread/started, item/started, thread/status/changed,
        # serverRequest/resolved, account/rateLimits/updated, the approval/elicitation SERVER
        # REQUESTS, and every client-to-server message) is intentionally NOT translated -- see
        # module docstring.
    return events


def write_jsonl(path: Path, events: list[dict]) -> None:
    path.write_text("".join(json.dumps(e, sort_keys=True) + "\n" for e in events),
                     encoding="utf-8", newline="\n")


# ---------------------------------------------------------------------------------------------
# Soft-cap watcher -- INFORMATIONAL ONLY (Cheap-bar per-arm PASS caps: red<=125, miniwob<=50
# normalized credits, reports/2026-07-18-gate0-prereg.md). Never kills anything; the imported,
# unmodified tools/gate0_credit_breaker.run_breaker (via LiveCreditGuard) remains the SOLE kill
# authority at the single hard 250-credit ceiling. Reuses the SAME pinned conversion function
# (app_server_usage_notification_to_credit_event) -- no separate arithmetic, no reimplemented rate.
# ---------------------------------------------------------------------------------------------

class SoftCapWatcher:
    def __init__(self, soft_cap: float, rate_pin: dict | None):
        from tools.gate0_appserver_launch import AppServerUsageTracker
        self._soft_cap = soft_cap
        self._rate_pin = rate_pin
        self._tracker = AppServerUsageTracker()
        self.total = 0.0
        self.warned = False
        self.warned_at: float | None = None

    def observe(self, raw_message: dict) -> None:
        if self._rate_pin is None or not isinstance(raw_message, dict):
            return
        if raw_message.get("method") != "thread/tokenUsage/updated":
            return
        try:
            event = app_server_usage_notification_to_credit_event(
                raw_message, self._rate_pin, self._tracker)
        except ValueError:
            return  # the HARD guard's job to kill on; this watcher never raises.
        self.total += event["normalized_credits"]
        if not self.warned and self.total >= self._soft_cap:
            self.warned = True
            self.warned_at = self.total


# ---------------------------------------------------------------------------------------------
# $0 in-process multi-call stub peer for --dry-run. Distinct from
# tools/gate0_appserver_launch.StubAppServerPeer (built to score exactly ONE tool call) --
# Red/MiniWoB turns make MANY mcpToolCall calls before the model decides the task is done, so
# --dry-run needs a peer that exercises that shape to prove the adapter/audit/agent_metrics
# pipeline end to end.
# ---------------------------------------------------------------------------------------------

class MultiCallStubAppServerPeer:
    def __init__(self, tool_name: str = "observe", call_count: int = 3,
                 server_name: str = SERVER_NAME, scenario: str = "completes"):
        if scenario not in ("completes", "one_call_denied"):
            raise ValueError(f"invalid scenario: {scenario!r}")
        self.client: ObservingGate0Client | None = None
        self.tool_name = tool_name
        self.call_count = call_count
        self.server_name = server_name
        self.scenario = scenario
        self.thread_id = "thr_dry_run_arm"
        self.turn_id = "turn_dry_run_arm"
        self._next_id = 0
        self._pending: dict[int, tuple[str, str]] = {}
        self._resolved = 0

    def send(self, message: dict) -> None:
        method = message.get("method")
        if method == "initialize":
            self.client.handle_message({"id": message["id"], "result": {}})
        elif method == "thread/start":
            self.client.handle_message({"id": message["id"],
                                         "result": {"thread": {"id": self.thread_id}}})
        elif method == "turn/start":
            self._run_turn(message["id"])
        elif "id" in message and "method" not in message:
            self._on_client_answer(message)

    def _run_turn(self, turn_start_request_id) -> None:
        self.client.handle_message({"id": turn_start_request_id,
                                     "result": {"turn": {"id": self.turn_id}}})
        for i in range(self.call_count):
            approval_id = self._next_id
            self._next_id += 1
            item_id, question_id = f"item_dry_{i}", f"q_dry_{i}"
            self._pending[approval_id] = (item_id, question_id)
            self.client.handle_message({
                "id": approval_id, "method": "item/tool/requestUserInput",
                "params": {"itemId": item_id, "threadId": self.thread_id, "turnId": self.turn_id,
                           "questions": [{
                               "id": question_id, "header": "Approve app tool call?",
                               "question": f"Allow the {self.tool_name!r} MCP tool call?",
                               "options": [{"label": "Approve"}, {"label": "Deny"}]}]},
            })

    def _on_client_answer(self, message: dict) -> None:
        # NOTE (bug found and fixed during this build's own smoke test): Gate0AppServerClient
        # answers each server->client request SYNCHRONOUSLY, reentrantly, inside the very
        # `handle_message()` call that sent it -- so `_run_turn`'s loop below never actually gets
        # to send request i+1 before request i's answer has already come back here. Checking
        # "is `self._pending` empty" after popping one entry is therefore TRUE after every single
        # resolution (the other N-1 entries haven't been inserted into `self._pending` yet), which
        # would fire the turn-ending events N times instead of once -- caught by direct inspection
        # of the produced transcript.jsonl, not assumed correct. `self._resolved ==
        # self.call_count` is immune to the reentrancy: it counts real resolutions monotonically,
        # regardless of insertion order.
        approval_id = message.get("id")
        if approval_id not in self._pending:
            return
        item_id, question_id = self._pending.pop(approval_id)
        self._resolved += 1
        answers = (message.get("result") or {}).get("answers", {})
        approved = answers.get(question_id, {}).get("answers") == ["Approve"]
        deny_this_one = self.scenario == "one_call_denied" and self._resolved == 1
        if approved and not deny_this_one:
            self.client.handle_message({
                "method": "item/completed",
                "params": {"item": {"id": item_id, "type": "mcpToolCall",
                                     "server": self.server_name, "tool": self.tool_name,
                                     "status": "completed", "error": None,
                                     "result": {"content": [{"type": "text", "text": "ok"}]}}},
            })
        else:
            self.client.handle_message({
                "method": "item/completed",
                "params": {"item": {"id": item_id, "type": "mcpToolCall",
                                     "server": self.server_name, "tool": self.tool_name,
                                     "status": "cancelled", "error": "user cancelled MCP tool call"}},
            })
        if self._resolved == self.call_count:
            self.client.handle_message({
                "method": "thread/tokenUsage/updated",
                "params": {"threadId": self.thread_id, "turnId": self.turn_id,
                           "tokenUsage": {"total": {
                               "inputTokens": 500, "cachedInputTokens": 100,
                               "outputTokens": 80, "reasoningOutputTokens": 20,
                               "totalTokens": 700}}}})
            self.client.handle_message({
                "method": "turn/completed",
                "params": {"turn": {"id": self.turn_id, "threadId": self.thread_id,
                                     "status": "completed"}},
            })


# ---------------------------------------------------------------------------------------------
# The turn runner -- unlike gate0_appserver_launch.run_one_tool_call_turn (scores exactly ONE
# tool call), a Gate 0 arm's ONE turn may make many mcpToolCall calls before the model decides
# it is done. `client.notifications` (populated by ObservingGate0Client.handle_message for every
# server->client message across the whole turn) already carries the FULL sequence needed by the
# adapter -- no special multi-call bookkeeping is needed here beyond waiting for the terminal
# notification.
# ---------------------------------------------------------------------------------------------

def run_gate0_arm_turn(client: ObservingGate0Client, *, cwd: str, task_text: str,
                       wall_clock_s: float, handshake_timeout: float = 30.0) -> dict:
    client.initialize(timeout=handshake_timeout)
    thread_result = client.start_thread(cwd=cwd, approvals_reviewer="user",
                                         timeout=handshake_timeout)
    thread_id = _extract_thread_id(thread_result)
    turn_params = build_turn_start_request(thread_id, [{"type": "text", "text": task_text}])
    client.send_request("turn/start", turn_params)
    end_note = client.wait_for_notification(DEFAULT_TURN_END_METHODS, timeout=wall_clock_s)
    return {"thread_id": thread_id, "ended": end_note is not None, "end_note": end_note}


# ---------------------------------------------------------------------------------------------
# agent_metrics.json / wake_boundary.json builders. This launcher has always built its own metrics
# record rather than delegating to check_gate0_codex.py: that module used to carry a
# build_agent_metrics() of its own, gated on a wake-accounting PASS that audit() can never emit
# (permanently unreachable dead code -- deleted 2026-07-28 along with the audit_overall rename).
# primitive_actions is still read from a plain audit() call's `primitive_action_events` (the SAME
# sound counter, reused not reimplemented); everything else is this launcher's own job per the
# build-spec.
# ---------------------------------------------------------------------------------------------

def build_agent_metrics(*, arm: str, mode: str, wall_clock_s: float, primitive_actions: int,
                         cost_usd: float, normalized_credits: float,
                         human_metrics_path: Path | None) -> dict:
    human_wall_clock_s = None
    human_primitive_actions = None
    human_note = "human baseline file not found (see report for the MiniWoB PENDING caveat)"
    if human_metrics_path is not None and human_metrics_path.is_file():
        try:
            human = json.loads(human_metrics_path.read_text(encoding="utf-8"))
            human_wall_clock_s = human.get("wall_clock_s")
            human_primitive_actions = human.get("primitive_actions")
            human_note = f"copied from {human_metrics_path}"
        except Exception:
            human_note = f"human baseline file at {human_metrics_path} was unreadable/malformed"
    return {
        "schema_version": 1,
        "arm": arm,
        "role": "agent",
        "mode": mode,
        "wall_clock_s": wall_clock_s,
        "primitive_actions": primitive_actions,
        "human_wall_clock_s": human_wall_clock_s,
        "human_primitive_actions": human_primitive_actions,
        "human_source_note": human_note,
        "cost_usd": cost_usd,
        "normalized_credits": normalized_credits,
    }


def ensure_wake_boundary_artifact(path: Path) -> dict:
    """Writes runs/gate0_paid/wake_boundary.json (schema_version 1, kind exact_wake_boundary,
    status DEFERRED) if it does not already exist -- shared across BOTH arms, never overwritten by
    the second arm's launch. `status` is "DEFERRED" (reported, never gated -- eval/score_gate0.py
    reads this structurally only), matching the project-wide 2026-07-21 wake-grounding amendment;
    unaffected by the exec->app-server transport change."""
    if path.is_file():
        return json.loads(path.read_text(encoding="utf-8"))
    artifact = {
        "schema_version": 1,
        "kind": "exact_wake_boundary",
        "status": "DEFERRED",
        "reason": "no_per_model_decision_observable_in_codex_app_server_stream",
        "evidence": "reports/2026-07-21-gate0-wake-grounding.md",
        "note": ("Deferred project-wide (2026-07-21 amendment): Codex's stream has no documented "
                 "per-model-decision boundary, exec-shaped or app-server-shaped alike. This is a "
                 "structural artifact, not gated by eval/score_gate0.py -- see that scorer's "
                 "wake_accounting field."),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(artifact, indent=2, sort_keys=False) + "\n",
                     encoding="utf-8", newline="\n")
    return artifact


def refuse_if_already_completed(out_dir: Path) -> None:
    """One-attempt guard: refuse if this out-dir already holds ANY evidence of a prior attempt.

    2026-07-24 fix (adversarial review of PR #157 found this a SHOULD-fix hole): keying this
    guard on `agent_metrics.json` alone left a real gap -- that file is written only at the very
    END of a successful run, so a run that SPENDS then CRASHES mid-turn (real money already
    gone) leaves no marker at all, and a second launch into the same out-dir would silently
    re-spend. `transcript.raw_appserver.jsonl` is written far earlier -- the FIRST message
    `ObservingGate0Client._log_transcript` sees, before any real turn/tool-call spend has even
    begun -- so keying on its mere existence catches a crashed-after-spending attempt that
    `agent_metrics.json` alone would miss. Kept in addition to (not instead of) checking
    `agent_metrics.json`, since a --dry-run attempt's own transcript.raw_appserver.jsonl should
    equally refuse a second --dry-run into the same directory."""
    for marker in (out_dir / "transcript.raw_appserver.jsonl", out_dir / "agent_metrics.json"):
        if marker.exists():
            raise SystemExit(f"one-attempt guard: {marker} already exists -- this out-dir "
                              "already holds evidence of a prior Gate 0 arm attempt; refusing a "
                              "second run.")


# ---------------------------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------------------------

def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--arm", required=True, choices=("red", "miniwob"))
    p.add_argument("--out-dir", required=True)
    p.add_argument("--model", default=None, help="explicit model id; required for a real run.")
    p.add_argument("--dry-run", action="store_true",
                    help="$0: in-process multi-call stub peer, no codex/docker spawned.")
    p.add_argument("--scenario", choices=("completes", "one_call_denied"), default="completes",
                    help="--dry-run only.")
    p.add_argument("--call-count", type=int, default=3, help="--dry-run only.")
    p.add_argument("--seam-check", action="store_true",
                    help="$0: docker image inspect (+ tools/list if --with-tools-list) only, "
                         "no codex spawned.")
    p.add_argument("--with-tools-list", action="store_true",
                    help="--seam-check only: also run the live tools/list handshake against the "
                         "real pinned image (spawns a real container -- never invoked by this "
                         "build's own tests).")
    p.add_argument("--credit-rate-pin", default=None,
                    help="required for a real (non-dry-run, non-seam-check) launch.")
    p.add_argument("--codex-path", default=None)
    p.add_argument("--codex-home", default=None)
    p.add_argument("--codex-auth-source", default=None)
    p.add_argument("--wall-clock-s", type=float, default=DEFAULT_WALL_CLOCK_S)
    p.add_argument("--stall-timeout-s", type=float, default=float(STALL_TIMEOUT_S))
    p.add_argument("--human-metrics-path", default=None,
                    help="override the pinned human-baseline metrics path (mainly for tests).")
    return p


def _validate_args(parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    latest_re = re.compile(r"(?i)(^|[-_.])latest($|[-_.])")
    real_run = not args.dry_run and not args.seam_check
    if real_run and not args.model:
        parser.error("--model is required for a real (non-dry-run, non-seam-check) launch.")
    if args.model and latest_re.search(args.model):
        parser.error("Model must be an explicit model identifier, not a latest alias.")
    if args.stall_timeout_s > STALL_TIMEOUT_S:
        parser.error(f"--stall-timeout-s may only tighten the pinned {STALL_TIMEOUT_S}s backstop, "
                     "never loosen it.")
    if args.wall_clock_s > DEFAULT_WALL_CLOCK_S:
        parser.error(f"--wall-clock-s may only tighten the pinned {DEFAULT_WALL_CLOCK_S}s "
                     "backstop, never loosen it.")
    if args.credit_rate_pin and not real_run:
        parser.error("--credit-rate-pin is only meaningful for a real, turn-running launch.")
    if real_run and not args.credit_rate_pin:
        parser.error("--credit-rate-pin is required for a real paid launch; refusing to launch "
                     "un-priced (pass --dry-run or --seam-check if no spend is intended).")
    # 2026-07-25 fix (adversarial review of PR #163, correction 4): out_dir used to stay whatever
    # string argparse handed back, so build_docker_mcp_args' `world_dir.resolve()` (world_dir is
    # derived from out_dir) resolved against the PROCESS'S CURRENT cwd -- the same launch spec run
    # from a different cwd would silently render a DIFFERENT config.toml (different absolute mount
    # source), the exact bug class the exec path's Confirm-PaidExecSignature guards against and this
    # launcher did not. Force it absolute once, here, before any other code reads args.out_dir.
    args.out_dir = str(Path(args.out_dir).resolve())


def _default_human_metrics_path(arm: str) -> Path:
    if arm == "red":
        return REPO_ROOT / "runs" / "gate0_human_baseline" / "red" / "human_metrics.json"
    return REPO_ROOT / "runs" / "gate0_paid_human_baseline" / "miniwob" / "human_metrics.json"


def _run_seam_check(args: argparse.Namespace, out_dir: Path) -> dict:
    arm = args.arm
    result: dict = {"schema_version": 1, "kind": "gate0_appserver_seam_check", "arm": arm,
                     "pinned_image_id": ARM_IMAGE_IDS[arm], "checks": {}}
    try:
        docker_path = resolve_docker_path()
    except RuntimeError as exc:
        result["checks"]["docker_available"] = {"ok": False, "error": str(exc)}
        result["ok"] = False
        _write_json(out_dir / "seam_check.json", result)
        return result
    result["checks"]["docker_available"] = {"ok": True, "path": docker_path}
    try:
        observed_id = docker_image_inspect_id(docker_path, ARM_IMAGE_IDS[arm])
        matches = observed_id == ARM_IMAGE_IDS[arm]
        result["checks"]["image_id_matches_pin"] = {"ok": matches, "observed": observed_id}
    except RuntimeError as exc:
        result["checks"]["image_id_matches_pin"] = {"ok": False, "error": str(exc)}
    if args.with_tools_list:
        world_dir = out_dir / "world"
        world_dir.mkdir(parents=True, exist_ok=True)
        mcp_args = build_docker_mcp_args(arm, ARM_IMAGE_IDS[arm], world_dir)
        try:
            tools = docker_tools_list(docker_path, mcp_args)
            observed_names = [t.get("name") for t in tools]
            result["checks"]["tools_list_matches_allowlist"] = {
                "ok": observed_names == TOOLS[arm], "observed": observed_names}
            # 2026-07-25 fix (adversarial review of PR #163, correction 1): this used to only
            # report tool NAMES inline and never write an artifact or compute a hash, so the
            # eval/fixtures/gate0_expected_pins_{red,miniwob}.appserver.json provenance notes'
            # claim of a reproducible tool_schema_sha256 recipe via `--seam-check
            # --with-tools-list` was NOT actually true of this code -- confirmed by the one
            # committed seam_check.json (runs/gate0_seam_check/red/seam_check.json) having no
            # tools-list section and no miniwob sibling. Write mcp-tools.json with the EXACT same
            # serialization _run_real writes for a real launch (json.dumps(tools) + "\n") and
            # record its sha256 here, so the recipe those notes describe is now real and
            # independently re-derivable for both arms.
            tools_path = out_dir / "mcp-tools.json"
            tools_path.write_text(json.dumps(tools) + "\n", encoding="utf-8", newline="\n")
            result["tool_schema_sha256"] = _sha256_file(tools_path)
        except RuntimeError as exc:
            result["checks"]["tools_list_matches_allowlist"] = {"ok": False, "error": str(exc)}
    result["ok"] = all(check.get("ok") for check in result["checks"].values())
    _write_json(out_dir / "seam_check.json", result)
    return result


def _write_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, indent=2, sort_keys=False) + "\n",
                     encoding="utf-8", newline="\n")


def _run_dry_run(args: argparse.Namespace, out_dir: Path) -> dict:
    arm = args.arm
    enabled_tools = TOOLS[arm]
    peer = MultiCallStubAppServerPeer(tool_name=enabled_tools[0], call_count=args.call_count,
                                       server_name=SERVER_NAME, scenario=args.scenario)
    raw_transcript_path = out_dir / "transcript.raw_appserver.jsonl"
    audit_log_path = out_dir / "audit.jsonl"
    client = ObservingGate0Client(send=peer.send, transcript_path=raw_transcript_path,
                                   audit_log_path=audit_log_path)
    peer.client = client
    task_text = task_text_for(arm)
    started = time.monotonic()
    run_gate0_arm_turn(client, cwd=str(out_dir), task_text=task_text, wall_clock_s=5.0)
    wall_clock_s = time.monotonic() - started

    adapted = adapt_app_server_notifications_to_exec_shape(client.notifications)
    write_jsonl(out_dir / "transcript.jsonl", adapted)

    # Synthetic (clearly dry-run) receipt/expected-pins pair, same style as
    # tools/gate0_wake_boundary.py's own _build_fixture -- purely so audit() can run against the
    # full pipeline at $0. Never mistaken for a real handshake: mode/notes say "dry_run" throughout.
    artifacts_dir = out_dir
    (artifacts_dir / "launch" / ".codex").mkdir(parents=True, exist_ok=True)
    fake_codex = artifacts_dir / "codex.exe"
    fake_codex.write_bytes(b"dry-run-stub-codex")
    brain_text = render_brain_config_toml("gpt-5.6-sol", DEVELOPER_INSTRUCTION)
    (artifacts_dir / "brain-config.toml").write_text(brain_text, encoding="utf-8", newline="\n")
    (artifacts_dir / "launch" / "TASK.md").write_text(task_text, encoding="utf-8", newline="\n")
    world_text = render_world_config_toml(SERVER_NAME, "docker", ["run", "--rm", "DRY_RUN"],
                                          str(REPO_ROOT), enabled_tools)
    config_text = render_full_config_toml(brain_text, world_text)
    (artifacts_dir / "launch" / ".codex" / "config.toml").write_text(
        config_text, encoding="utf-8", newline="\n")
    mcp_list_json = json.dumps([{"name": SERVER_NAME}]) + "\n"
    (artifacts_dir / "codex-mcp-list.json").write_text(mcp_list_json, encoding="utf-8", newline="\n")
    tool_schema_json = json.dumps([{"name": t} for t in enabled_tools]) + "\n"
    (artifacts_dir / "mcp-tools.json").write_text(tool_schema_json, encoding="utf-8", newline="\n")

    receipt = build_handshake_receipt(
        arm=arm, model="gpt-5.6-sol", codex_version="codex-cli 0.0.0-dry-run",
        codex_path=str(fake_codex), codex_executable_sha256=_sha256_file(fake_codex),
        mcp_tools_observed=enabled_tools,
        brain_config_sha256=_sha256_file(artifacts_dir / "brain-config.toml"),
        task_sha256=_sha256_file(artifacts_dir / "launch" / "TASK.md"),
        config_sha256=_sha256_file(artifacts_dir / "launch" / ".codex" / "config.toml"),
        codex_mcp_list_sha256=_sha256_file(artifacts_dir / "codex-mcp-list.json"),
        tool_schema_sha256=_sha256_file(artifacts_dir / "mcp-tools.json"),
        host_code_sha256={"/app/world_mcp.py": "0" * 64, "/app/core/miniwob_world.py": "1" * 64},
        image_code_sha256={"/app/world_mcp.py": "0" * 64, "/app/core/miniwob_world.py": "1" * 64},
    )
    receipt_path = artifacts_dir / "handshake-receipt.json"
    expected_path = artifacts_dir / "expected-pins.dry-run.json"
    _write_json(receipt_path, receipt)
    _write_json(expected_path, receipt)  # dry-run: receipt IS its own expected pins (self-consistent)

    audit_result = audit(out_dir / "transcript.jsonl", receipt_path, expected_path, artifacts_dir, arm)

    human_path = (Path(args.human_metrics_path) if args.human_metrics_path
                  else _default_human_metrics_path(arm))
    agent_metrics = build_agent_metrics(
        arm=arm, mode="dry_run", wall_clock_s=wall_clock_s,
        primitive_actions=audit_result["primitive_action_events"],
        cost_usd=0.0, normalized_credits=0.0, human_metrics_path=human_path)
    _write_json(out_dir / "agent_metrics.json", agent_metrics)
    wake_boundary = ensure_wake_boundary_artifact(out_dir / "wake_boundary.json")

    verdict = {
        "schema_version": 1, "kind": "gate0_appserver_arm_dry_run_verdict", "arm": arm,
        "mode": "dry_run", "scenario": args.scenario, "call_count": args.call_count,
        "primitive_action_events": audit_result["primitive_action_events"],
        "audit_leak_failures": audit_result["leak_failures"],
        "audit_constancy_failures": audit_result["constancy_failures"],
        "audit_overall": audit_result["audit_overall"],
    }
    _write_json(out_dir / "dry_run_verdict.json", verdict)
    print(json.dumps(verdict, sort_keys=True))
    return {"verdict": verdict, "agent_metrics": agent_metrics, "wake_boundary": wake_boundary}


def resolve_isolated_codex_home(explicit: str | None, out_dir: Path) -> str:
    """CODEX_HOME handed to the codex child MUST be absolute: the child runs with cwd=out_dir, so a
    relative home (e.g. out_dir/'codex-home') resolves against out_dir again and 'does not exist'
    -> codex exits -> initialize times out (observed 2026-07-24). Absolutize the derived home."""
    return explicit or str((out_dir / "codex-home").resolve())


def _finalize_real_run(*, receipt: dict, receipt_path: Path, transcript_path: Path, out_dir: Path,
                        arm: str, wall_clock_s: float, credits_result: dict, rate_pin: dict,
                        watcher: SoftCapWatcher, auth_note: str, model: str,
                        human_path: Path) -> dict:
    """Post-turn scoring + artifact-writing, factored out of _run_real so the ordering fix below is
    independently testable without a real codex/docker launch.

    2026-07-25 fix (adversarial review of PR #163, correction 5): verify_launch_signature_unchanged()
    used to run BEFORE agent_metrics.json/run-receipt.json were written and raised SystemExit
    straight through on a mismatch. A real paid turn that had already spent money would abort right
    there with NO metrics ever written -- and refuse_if_already_completed (keyed in part on
    transcript.raw_appserver.jsonl, already on disk since the start of the turn) would then refuse
    any retry into the same out-dir, leaving a spent run permanently unscorable. Now: catch the
    mismatch, skip resolving expected pins against a drifted/tampered config (that would be
    dishonest -- see verify_launch_signature_unchanged's own docstring for what it proves), still
    write agent_metrics.json/run-receipt.json (honestly marked LAUNCH_SIGNATURE_MISMATCH), THEN
    re-raise so the process still exits non-zero and nothing is silently reported as fine."""
    signature_mismatch: SystemExit | None = None
    try:
        verify_launch_signature_unchanged(receipt, out_dir)
    except SystemExit as exc:
        signature_mismatch = exc

    if signature_mismatch is None:
        # Close the app-server expected-pins gap (see the block comment above
        # resolve_expected_pins): resolve the two launch-invocation-dependent PIN_FIELDS from
        # THIS run's own pre-turn receipt values before calling the frozen audit() against a
        # static fixture that can never match them -- only once the signature check above has
        # proven the on-disk config/mcp-list still match what the receipt recorded pre-turn.
        base_expected = json.loads(
            (REPO_ROOT / "eval" / "fixtures" / f"gate0_expected_pins_{arm}.appserver.json")
            .read_text(encoding="utf-8"))
        resolved_expected = resolve_expected_pins(
            base_expected, config_sha256=receipt["config_sha256"],
            codex_mcp_list_sha256=receipt["codex_mcp_list_sha256"])
        resolved_expected_path = out_dir / "expected-pins.resolved.json"
        _write_json(resolved_expected_path, resolved_expected)
        audit_result = audit(transcript_path, receipt_path, resolved_expected_path, out_dir, arm)
    else:
        audit_result = {"audit_overall": "LAUNCH_SIGNATURE_MISMATCH", "primitive_action_events": 0}

    normalized_credits = (credits_result.get("final_total_normalized_credits")
                          if credits_result.get("final_total_normalized_credits") is not None
                          else credits_result.get("credits_at_trip", 0.0)) or 0.0
    cost_usd = normalized_credits / rate_pin["credits_per_usd"] if rate_pin["credits_per_usd"] else 0.0

    agent_metrics = build_agent_metrics(
        arm=arm, mode="paid_gate0", wall_clock_s=wall_clock_s,
        primitive_actions=audit_result["primitive_action_events"], cost_usd=cost_usd,
        normalized_credits=normalized_credits, human_metrics_path=human_path)
    _write_json(out_dir / "agent_metrics.json", agent_metrics)
    wake_boundary_path = REPO_ROOT / "runs" / "gate0_paid" / "wake_boundary.json"
    ensure_wake_boundary_artifact(wake_boundary_path)

    run_receipt = {
        "schema_version": 1, "kind": "gate0_appserver_arm_run_receipt", "arm": arm,
        "model": model, "credit_breaker_tripped": bool(credits_result.get("tripped", False)),
        "soft_cap_warned": watcher.warned, "soft_cap_warned_at": watcher.warned_at,
        "wall_clock_s": wall_clock_s, "auth_note": auth_note,
        "audit_overall": audit_result["audit_overall"],
        # All launch-time hashes in one place (build-spec deliverable 1): config/mcp-list hashes
        # and the docker-inspected image id are ALSO in handshake-receipt.json (the scorer-pinned
        # artifact); launcher_sha256 (this runner's OWN canonical git-blob-at-HEAD hash, same
        # contract as world_mcp.py::code_sha256/Get-CanonicalCodeSha256) is unique to this receipt.
        "launcher_sha256": git_blob_sha256(REPO_ROOT, "tools/gate0_appserver_arm.py"),
        "config_sha256": receipt["config_sha256"],
        "codex_mcp_list_sha256": receipt["codex_mcp_list_sha256"],
        "world_image_id": receipt["world_image_id"],
    }
    _write_json(out_dir / "run-receipt.json", run_receipt)
    print(json.dumps(run_receipt, sort_keys=True))

    if signature_mismatch is not None:
        raise signature_mismatch
    return {"agent_metrics": agent_metrics, "run_receipt": run_receipt}


def _run_real(args: argparse.Namespace, out_dir: Path) -> dict:
    """Builds and wires the real launch path end to end. NEVER INVOKED BY THIS BUILD'S OWN TESTS
    OR $0 SESSION -- the orchestrator runs this. Left fully implemented (not a stub) per the
    build-spec's deliverable list."""
    arm = args.arm
    rate_pin = load_credit_rate_pin(Path(args.credit_rate_pin), args.model)

    docker_path = resolve_docker_path()
    codex_path = args.codex_path or resolve_codex_path()
    codex_home = resolve_isolated_codex_home(args.codex_home, out_dir)
    Path(codex_home).mkdir(parents=True, exist_ok=True)
    auth_note = seed_codex_auth(Path(codex_home), args.codex_auth_source)

    world_dir = out_dir / "world"
    world_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "launch" / ".codex").mkdir(parents=True, exist_ok=True)

    observed_image_id = docker_image_inspect_id(docker_path, ARM_IMAGE_TAGS[arm])
    if observed_image_id != ARM_IMAGE_IDS[arm]:
        raise SystemExit(f"world image is stale/unpinned: observed {observed_image_id}, "
                          f"pinned {ARM_IMAGE_IDS[arm]}")
    host_code = {"/app/world_mcp.py": git_blob_sha256(REPO_ROOT, "world_mcp.py"),
                 "/app/core/miniwob_world.py": git_blob_sha256(REPO_ROOT, "core/miniwob_world.py")}
    for path, digest in host_code.items():
        if digest == "UNHASHABLE":
            raise SystemExit(f"host code for {path} differs from HEAD or git is unavailable; "
                              "refusing to hash a dirty working tree.")
    image_code = docker_image_code_hashes(docker_path, observed_image_id)
    if host_code != image_code:
        raise SystemExit("world image is stale: host/image code parity check failed.")

    mcp_args = build_docker_mcp_args(arm, observed_image_id, world_dir)
    enabled_tools = TOOLS[arm]
    overrides = build_overrides(model=args.model, mcp_server_name=SERVER_NAME,
                                 mcp_command="docker", mcp_args=mcp_args, mcp_cwd=str(REPO_ROOT),
                                 enabled_tools=enabled_tools,
                                 developer_instructions=DEVELOPER_INSTRUCTION)

    brain_text = render_brain_config_toml(args.model, DEVELOPER_INSTRUCTION)
    (out_dir / "brain-config.toml").write_text(brain_text, encoding="utf-8", newline="\n")
    task_text = task_text_for(arm)
    (out_dir / "launch" / "TASK.md").write_text(task_text, encoding="utf-8", newline="\n")
    world_text = render_world_config_toml(SERVER_NAME, "docker", mcp_args, str(REPO_ROOT),
                                          enabled_tools)
    config_text = render_full_config_toml(brain_text, world_text)
    (out_dir / "launch" / ".codex" / "config.toml").write_text(
        config_text, encoding="utf-8", newline="\n")

    mcp_list_text = codex_mcp_list_json(codex_path, codex_home, overrides)
    (out_dir / "codex-mcp-list.json").write_text(mcp_list_text + "\n", encoding="utf-8", newline="\n")
    tools = docker_tools_list(docker_path, mcp_args)
    observed_names = [t.get("name") for t in tools]
    if observed_names != enabled_tools:
        raise SystemExit("live world MCP tool inventory differs from the frozen allowlist.")
    (out_dir / "mcp-tools.json").write_text(json.dumps(tools) + "\n", encoding="utf-8", newline="\n")

    codex_version_result = subprocess.run([codex_path, "--version"], capture_output=True, text=True,
                                          timeout=_SUBPROCESS_TIMEOUT_S)
    codex_version = codex_version_result.stdout.strip()

    receipt = build_handshake_receipt(
        arm=arm, model=args.model, codex_version=codex_version, codex_path=codex_path,
        codex_executable_sha256=_sha256_file(Path(codex_path)), mcp_tools_observed=observed_names,
        brain_config_sha256=_sha256_file(out_dir / "brain-config.toml"),
        task_sha256=_sha256_file(out_dir / "launch" / "TASK.md"),
        config_sha256=_sha256_file(out_dir / "launch" / ".codex" / "config.toml"),
        codex_mcp_list_sha256=_sha256_file(out_dir / "codex-mcp-list.json"),
        tool_schema_sha256=_sha256_file(out_dir / "mcp-tools.json"),
        host_code_sha256=host_code, image_code_sha256=image_code)
    receipt_path = out_dir / "handshake-receipt.json"
    _write_json(receipt_path, receipt)

    watcher = SoftCapWatcher(ARM_SOFT_CREDIT_CAPS[arm], rate_pin)
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

    guard = LiveCreditGuard(limit=HARD_CREDIT_CAP, stall_timeout_s=args.stall_timeout_s,
                             rate_pin=rate_pin, on_trip=_on_trip)
    guard.start()

    def _combined_observer(message: dict) -> None:
        guard.observe(message)
        watcher.observe(message)

    transcript_path = out_dir / "transcript.jsonl"
    raw_transcript_path = out_dir / "transcript.raw_appserver.jsonl"
    audit_log_path = out_dir / "audit.jsonl"

    env_backup = os.environ.get("CODEX_HOME")
    os.environ["CODEX_HOME"] = codex_home
    started = time.monotonic()
    try:
        client = ObservingGate0Client(codex_path=codex_path, extra_args=[a for o in overrides
                                                                          for a in ("-c", o)],
                                       cwd=str(out_dir.resolve()), transcript_path=raw_transcript_path,
                                       credit_observer=_combined_observer,
                                       audit_log_path=audit_log_path,
                                       stderr_log_path=out_dir / "codex.stderr.log")
        state["client"] = client
        client.connect()
        state["pid"] = client._transport.proc.pid
        try:
            run_gate0_arm_turn(client, cwd=str(out_dir.resolve()), task_text=task_text,
                               wall_clock_s=args.wall_clock_s,
                               handshake_timeout=REAL_RUN_HANDSHAKE_TIMEOUT_S)
        finally:
            guard.finish()
            guard.join(timeout=10.0)
            client.close()
    finally:
        if env_backup is None:
            os.environ.pop("CODEX_HOME", None)
        else:
            os.environ["CODEX_HOME"] = env_backup
    wall_clock_s = time.monotonic() - started

    adapted = adapt_app_server_notifications_to_exec_shape(client.notifications)
    write_jsonl(transcript_path, adapted)

    human_path = (Path(args.human_metrics_path) if args.human_metrics_path
                  else _default_human_metrics_path(arm))
    finalized = _finalize_real_run(
        receipt=receipt, receipt_path=receipt_path, transcript_path=transcript_path,
        out_dir=out_dir, arm=arm, wall_clock_s=wall_clock_s, credits_result=(guard.result or {}),
        rate_pin=rate_pin, watcher=watcher, auth_note=auth_note, model=args.model,
        human_path=human_path)
    return {"receipt": receipt, **finalized}


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    _validate_args(parser, args)

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    if not args.seam_check:
        refuse_if_already_completed(out_dir)

    if args.seam_check:
        result = _run_seam_check(args, out_dir)
        print(json.dumps(result, sort_keys=True))
        return 0 if result.get("ok") else 1
    if args.dry_run:
        _run_dry_run(args, out_dir)
        return 0
    _run_real(args, out_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
