# Gate 0 `codex app-server` launch runbook -- confirming the M1 unblock end to end

Builds on `reports/2026-07-23-gate0-appserver-spike.md` (viability) and
`reports/2026-07-23-gate0-appserver-client-prototype.md` (the client, merged to `main` PR #147).
This session adds the DRIVER: `tools/gate0_appserver_launch.py` + a stub MCP server + two
ready-to-run wrapper scripts. ADDITIVE ONLY -- no edits to `tools/run_gate0_codex.ps1`,
`tools/gate0_credit_breaker.py`, `tools/gate0_credit_accountant.py`,
`tools/gate0_codex_credit_rate.py`, the brain, `core/contracts.py`, or any tool schema.

**2026-07-23 orchestrator update, folded in during this build:** Docker Desktop is down on the
launch host (`docker version` -> daemon not running), so the Gate 0 `gb-mcp-world` container is
UNAVAILABLE. The stub MCP path is therefore this build's PRIMARY path, not a fallback -- see
"Why the stub proves the same thing" below. Docker remains supported (generic, parameterized) for
whenever the daemon is back up.

**2026-07-23 adversarial-review fix pass (same day, PR #151), still additive-only, still no
pinned-file edits:** hardened `score_turn` against a false-PASS on a `status:"completed"` +
`error`/`isError` item (a cancel-with-error must score cancelled, not completed) and tightened its
tool-match fallback; a real turn now fails closed without `--credit-rate-pin`; the credit cap's
inertness on the app-server transport (B1) is now stated plainly here and in both wrapper scripts'
headers instead of silently assumed away, with `--turn-timeout-s` lowered to 45s as the bound
actually enforced; an isolated `codex-home` now gets its `auth.json` seeded from the real
`~/.codex` (N3); both wrapper scripts' `codex login status` preflight no longer trips Windows
PowerShell 5.1's native-command stderr handling (PS-5.1); `-IUnderstandThisSpendsMoney`'s truth is
now asserted, not just its Mandatory-ness (N1). See "B1", "N3", and "PS 5.1 fix" call-outs below for
the exact mechanics; 9 new tests added to `tests/test_gate0_appserver_launch.py` (19 -> 28).

## Files this session added

| File | What it is |
|---|---|
| `tools/gate0_appserver_launch.py` | The launcher: drives one turn through `Gate0AppServerClient`, scores completion vs cancellation, wires the credit breaker. |
| `tools/gate0_stub_mcp_server.py` | Minimal local stdio MCP server, one tool `ping` -> `"pong"`. No Docker needed. |
| `tests/test_gate0_appserver_launch.py` | 19 $0 mock-only tests (no real codex spawned). |
| `tools/gate0_appserver_handshake_smoke.ps1` | Prepared script (a) -- $0 real handshake smoke. NOT run by this build. |
| `tools/gate0_appserver_paid_turn.ps1` | Prepared script (b) -- the one bounded paid turn. NOT run by this build. |
| `reports/2026-07-23-gate0-appserver-launch-runbook.md` | This file. |

## Why the stub proves the same thing the Docker world would

The exec MCP-cancel bug (`openai/codex#15824` non-`codex_apps` MCP calls wrongly enter the
app-tool approval flow; `#16685` exec then EOF-declines it) fires for **any** non-`codex_apps` MCP
server -- it is triggered by codex's own app-tool approval routing, not by anything
`gb-mcp-world`-specific. A `ping` call through the stub hits the identical
`item/tool/requestUserInput` "Approve app tool call?" `ServerRequest` the Docker world's `observe`
call would. Confirming the stub's tool call completes under app-server (vs cancelling under exec)
confirms the mechanism; swapping in the Docker world later is a `--mcp docker` flag away, not a
different code path.

## Step 1 recipe -- exactly how Gate 0 configures codex against an MCP server (from `tools/run_gate0_codex.ps1`, read-only, verbatim key bits)

**Brain config (`config.toml`, written for inspection; the CLI `-c` overrides below are "the
effective config" -- the pinned script's own receipt field name for this):**
```toml
model = "<Model>"
forced_login_method = "chatgpt"
approval_policy = "never"
sandbox_mode = "read-only"
web_search = "disabled"
developer_instructions = "Use only gate0_world MCP tools. Never use shell, files, web, tool search, connectors, or other MCP servers."

[history]
persistence = "none"

[features]
shell_tool = false
skill_mcp_dependency_install = false
apps = false
goals = false
hooks = false
memories = false
multi_agent = false

[apps._default]
enabled = false
```

**MCP server block (Red arm shown; MiniWoB arm swaps the tool list/task/image):**
```toml
[mcp_servers.gate0_world]
command = "docker"
args = ["run", "-i", "--rm", "--network", "none",
        "--mount", "type=bind,source=<Roms>,target=/app/roms,readonly",
        "--mount", "type=bind,source=<State>,target=/app/red_start.state,readonly",
        "--mount", "type=bind,source=<WorldDir>,target=/app/world",
        "<ImageId>", "--game", "pokemon_red", "--init-state", "/app/red_start.state",
        "--out", "/app/world", "--keep-frames"]
cwd = "<RepoRoot>"
required = true
enabled = true
enabled_tools = ["observe", "explore", "goto", "remember", "press_button", "press_sequence", "wait"]
default_tools_approval_mode = "auto"
```

**How Docker is stood up:** `docker run -i --rm --network none` with three `--mount type=bind,...`
entries (ROM dir read-only, pinned save-state read-only, a fresh per-run world output dir
read-write), the content-addressed `$ImageId` (never a mutable tag -- resolved via
`docker image inspect --format '{{.Id}}'` and cross-checked byte-for-byte against the host's
`world_mcp.py`/`core/miniwob_world.py` git-blob hashes before anything runs), then
`--game <name> --init-state /app/red_start.state --out /app/world [--keep-frames]`.

**How codex auth is provided:** NOT copied anywhere. Codex reads whatever `CODEX_HOME` points at
(default `~/.codex`, holding `auth.json` from a prior `codex login`). The pinned script only ever
sets `CODEX_HOME` to an **isolated, empty** dir for the free `codex mcp list --json` inventory
probe (so that probe proves the override vocabulary in isolation, with no risk of touching the
user's real auth state), then restores the original `CODEX_HOME` before any run that needs real
auth. `tools/gate0_appserver_launch.py`'s real mode does the analogous thing: it sets/restores the
`CODEX_HOME` env var around the child `codex app-server` process pointing at
`<out-dir>/codex-home` -- **but that isolated dir has no `auth.json` of its own**, so a real
handshake will only authenticate if the orchestrator arranges for that dir (or `--codex-home`) to
see the real credential, e.g. by pointing `--codex-home` at (or symlinking to) the orchestrator's
already-`codex login`'d real `CODEX_HOME`. **Never paste a token in cleartext anywhere in this
pipeline** -- `~/.codex/auth.json` already exists; reuse it, don't recreate it.

## `tools/gate0_appserver_client.py` API (from the merged prototype, `main` @ PR #147/#148)

- `Gate0AppServerClient(send=None, codex_path=None, extra_args=(), cwd=None, permission_scope="session", ...)`
- `.connect()` -- spawns `codex app-server --listen stdio://`, starts a background reader thread.
- `.initialize(client_name=..., client_version=...)` -- sends `initialize` with
  `capabilities={"experimentalApi": true, "mcpServerOpenaiFormElicitation": true}` (required for
  `item/tool/requestUserInput` to ever be sent), then the `initialized` notification.
- `.start_thread(cwd, approvals_reviewer="user", **extra)` -- sends `thread/start`;
  `approvalsReviewer="user"` routes approval requests to THIS client.
- `.send_request(method, params, timeout=30.0)` -- generic client-initiated request/response
  (used directly for `turn/start`, which the client deliberately provides no dedicated method for
  -- see `build_turn_start_request`).
- `build_turn_start_request(thread_id, input_items)` -- builds (never sends) `turn/start` params.
- The 5 answer handlers (`_HANDLERS`) answer `mcpServer/elicitation/request`,
  `item/tool/requestUserInput`, `item/permissions/requestApproval`,
  `item/commandExecution/requestApproval`, `item/fileChange/requestApproval` automatically, always
  `accept`.
- `.handle_message(message)` dispatches server->client requests and client-response messages, but
  **silently drops plain notifications** (method + no id) -- by design, "out of scope for this
  prototype." `tools/gate0_appserver_launch.py`'s `ObservingGate0Client` subclass (additive, does
  not edit the client) captures those notifications instead, since the launcher needs them to
  score `item/completed`/`turn/completed`.

## Launcher design (`tools/gate0_appserver_launch.py`)

- `ObservingGate0Client(Gate0AppServerClient)` -- captures notifications, logs a full
  send/receive transcript (append-only JSONL), feeds a credit-breaker observer.
- `StubAppServerPeer` -- in-process fake app-server peer for `--dry-run`, extending the
  `fake_send` pattern from `tests/test_gate0_appserver_client.py`. Drives: `initialize` ->
  `thread/start` -> `turn/start` (acked immediately) -> `item/tool/requestUserInput` (the
  #15824-regression prompt) -> (client answers `accept`) -> `item/completed` + `turn/completed`
  (scenario `"completes"`) or `item/completed{status:"cancelled"}` + `turn/failed` (scenario
  `"cancelled"`, reproducing exec's exact failure wording for a negative-control test).
- `run_one_tool_call_turn(client, ...)` / `score_turn(client, ...)` -- the SAME scoring path for
  both dry-run and real mode: same functions, same code, only the wired `client` differs.
- `LiveCreditGuard` -- imports `tools/gate0_credit_breaker.run_breaker`/`BreakerTripped`/
  `MalformedCreditStream` (never edits them) around a background-thread-fed generator of
  `{"normalized_credits": N}` events, `raise_on_trip=True`. Without a `--credit-rate-pin`, every
  observed message passes through at 0 known credits (never fabricates a rate, matching
  `codex_event_to_credit_event`'s own zero-credit-passthrough philosophy) -- WITH a pin, real
  `token_count`-shaped events are converted via the imported, unmodified
  `gate0_codex_credit_rate.codex_event_to_credit_event`. On trip, calls `client.close()` and a
  best-effort `taskkill /PID <pid> /T /F` (Windows) -- **weaker than the pinned launcher's
  Job-Object-guaranteed kill**; flagged explicitly in the wrapper script's header comment.
- `build_overrides(...)` -- reimplements (does not call) the pinned script's own `$Overrides`
  recipe: identical field vocabulary, identical `-c key=value` CLI-override transport.
- `--mcp stub` (default) registers `tools/gate0_stub_mcp_server.py` directly (`command=<python>`,
  no Docker). `--mcp docker` is generic/parameterized pass-through (`--docker-image`,
  `--docker-mount` repeatable, `--docker-extra-arg` repeatable, `--docker-tool` repeatable) --
  deliberately NOT hardcoding the Red/MiniWoB-specific mount paths inside this new file, so the
  safety-critical specifics stay owned by the one already-reviewed pinned recipe.

## Assumptions vs verified facts (flagged again, explicitly)

- **Verified** (this session, offline reads only, no codex invocation): the config recipe above,
  copied verbatim from `tools/run_gate0_codex.ps1`; the client API surface, copied from
  `tools/gate0_appserver_client.py` and its own committed schema fixtures
  (`tests/fixtures/gate0_appserver/*.json`); `run_breaker`/`codex_event_to_credit_event`'s exact
  signatures and fail-closed behavior, read directly from `tools/gate0_credit_breaker.py` /
  `tools/gate0_codex_credit_rate.py`.
- **Verified** (this session, $0, no codex invocation of any kind): the `--dry-run` path drives
  the stub end to end and scores both scenarios correctly (exact output below); the full existing
  test suite still passes (1493 passed, 16 skipped -- the 16 skips are the same pre-existing skips
  the client prototype report already banked at 1474/16; 1474 + 19 new launcher tests = 1493).
- **NOT verified / ASSUMED** (no `codex app-server generate-json-schema` schema exists for these --
  none was dumped this session; the one paid turn is what must confirm or correct them):
  - `thread/start`'s RESPONSE shape (`_extract_thread_id` tries `{"thread":{"id":...}}`,
    `{"threadId":...}`, `{"id":...}` in that order and fails loud if none match).
  - `turn/start`'s RESPONSE shape (assumed `{"turn":{"id":...}}`-ish; the launcher does not
    actually need to parse it beyond acknowledging the request completed).
  - The terminal notification method names/shapes this launcher watches for:
    `item/completed` (with `params.item.{id,tool,type,status,result}`) and
    `turn/completed`/`turn/failed`/`turn/aborted`. If the real server uses different method names
    or a different `item`/`turn` shape, `score_turn` will see zero matching notifications and
    report `mcp_tool_call_completed: false, cancelled: false` with a note about the timeout --
    NOT a false positive, but also not evidence of a real cancellation; the raw `transcript.jsonl`
    is what settles it by inspection either way.
  - Whether declaring `experimentalApi`/`mcpServerOpenaiFormElicitation` at `initialize()` is
    *sufficient* (vs some other undocumented precondition) for the real server to actually deliver
    `item/tool/requestUserInput` -- carried over unresolved from the prototype report.
  - The isolated-`CODEX_HOME`-with-real-auth arrangement above (real auth requires pointing at, or
    seeding, an `auth.json` -- this was reasoned through, not exercised against a real `codex`
    process this session).

## Step 3 -- $0 stub dry-run result (exact, this session)

```
$ python -m tools.gate0_appserver_launch --dry-run --out-dir runs/_scratch_dryrun
{"audit_log_path": "runs\\_scratch_dryrun\\audit.jsonl", "cancelled": false, "credit_breaker_tripped": false,
 "kind": "gate0_appserver_launch_verdict", "mcp": "stub", "mcp_tool_call_completed": true, "mode": "dry_run",
 "normalized_credits": 0.0, "notes": ["DRY RUN: in-process StubAppServerPeer, no codex process spawned, $0."],
 "schema_version": 1, "transcript_path": "runs\\_scratch_dryrun\\transcript.jsonl", "turns": 1}

$ python -m tools.gate0_appserver_launch --dry-run --scenario cancelled --out-dir runs/_scratch_dryrun2
{... "cancelled": true, "mcp_tool_call_completed": false, ...}
```
The `transcript.jsonl` for the `"completes"` run shows the client answering
`{"answers": {"q_approve_tool_call": {"answers": ["Approve"]}}}` to the
`item/tool/requestUserInput` request, then the stub emitting `item/completed{status:"completed"}` +
`turn/completed` -- the scoring path correctly reports `true`/`false` for the two scenarios (not a
rubber stamp -- `test_dry_run_cancelled_scenario_scores_negative_not_a_rubber_stamp` pins this).

New test file: `tests/test_gate0_appserver_launch.py ...................  [100%]  19 passed`.

Full suite (same reused venv, `.venv-win` from the sibling `ai-pokemon-red` worktree -- this fresh
worktree's own `uv sync` hit a transient TLS/network failure fetching `pysdl2-dll`; the reused venv
already has every dependency this repo needs and is running THIS worktree's files):
```
1493 passed, 16 skipped in 56.18s
```

## Step 4 -- what the orchestrator runs next (NOT run by this build)

### (a) $0 real-handshake smoke -- `tools/gate0_appserver_handshake_smoke.ps1`
```powershell
pwsh tools/gate0_appserver_handshake_smoke.ps1 -Model gpt-5.6-sol -OutputDir runs/gate0_appserver_smoke
```
Spawns real `codex app-server`, does `initialize` + `thread/start` against the stub MCP server,
prints exactly what the real binary returns, exits. **No `turn/start` is ever sent -- no tokens
spent.** Preflight checks: codex resolves + version parses; neither `OPENAI_API_KEY` nor
`CODEX_API_KEY` is set; `codex login status` proves ChatGPT auth. Expected cost: **$0** (local
process handshake only).

**PS 5.1 fix (this session):** the `login status` preflight used `& codex login status 2>&1`,
which under Windows PowerShell 5.1 with `$ErrorActionPreference='Stop'` promotes any stderr line
from a native command to a terminating `NativeCommandError` regardless of exit code -- this threw
before the login text was ever inspected, on PS 5.1 specifically (pwsh 7 does not have this
behavior). Reworked to use `System.Diagnostics.Process` redirection instead (the same pattern
`tools/run_gate0_codex.ps1`'s own `Invoke-RedirectedProcess` already uses), which behaves
identically under `powershell.exe` 5.1 and `pwsh` 7.

**N3 auth seam:** an isolated `-OutputDir\codex-home` has no `auth.json` of its own and will fail
to authenticate. `tools/gate0_appserver_launch.py` now seeds one automatically (copy, never move,
never mutate the source or `~/.codex/config.toml`) from `--codex-auth-source` (default
`~/.codex/auth.json`) whenever the isolated home lacks one. Both wrapper scripts expose
`-CodexHome` and `-CodexAuthSource` pass-throughs if the orchestrator needs to point elsewhere.

### (b) The one bounded paid turn -- `tools/gate0_appserver_paid_turn.ps1`
```powershell
pwsh tools/gate0_appserver_paid_turn.ps1 -Model gpt-5.6-sol `
    -OutputDir runs/gate0_appserver_paid_turn `
    -CreditRatePin path\to\signed_rate_pin.json `
    -IUnderstandThisSpendsMoney
```
(Docker variant, only once the daemon is back up, documented in the script's own header comment.)

Requires a human-signed `-CreditRatePin` (fail-closed, same contract as
`tools/gate0_codex_credit_rate.py`'s `REQUIRED_RATE_FIELDS`, and enforced again by
`tools/gate0_appserver_launch.py` itself: it now refuses to run a real turn at all without one) and
the explicit `-IUnderstandThisSpendsMoney` switch (the script now asserts the switch's value is
true, not just that it was Mandatory -- a mandatory `[switch]` can still be passed `:$false`).
Default `-CreditCap 10` normalized credits; `-StallTimeoutS` may only tighten the pinned 300s
backstop; `-TurnTimeoutS` (new, default 45s) may only tighten its own pinned backstop.

**B1 -- honesty about the credit cap on this transport (this session's finding, not fixed by
guessing):** `-CreditCap` is currently **INERT** when driving `codex app-server`.
`tools/gate0_codex_credit_rate.py::codex_event_to_credit_event` only recognizes the exec-shaped
`{"type": "token_count", ...}` event; `codex app-server` sends JSON-RPC 2.0 notifications instead,
and no committed schema or fixture for a usage/token-count notification exists in this repo
(`tests/fixtures/gate0_appserver/` has no such shape) -- so `LiveCreditGuard` never sees anything
it can price, and the cap can never trip on real spend. **The bound actually enforced today is
`-TurnTimeoutS`** (lowered default 45s, was 120s): the launcher walks away from codex (closes the
client, best-effort `taskkill /PID <pid> /T /F`) once that many seconds pass with no terminal turn
notification, independent of `-CreditCap`. **TODO:** once a real paid turn (or
`codex app-server generate-json-schema`) reveals the actual usage-notification shape, add an
ADDITIVE app-server usage shim feeding the same `LiveCreditGuard`/breaker -- do not guess the shape
before then. `-CreditRatePin` stays mandatory regardless (so a rate is ready the moment the shim
lands, and the script's contract never quietly drops to "no rate needed").

**Expected token cost:** one turn whose entire task is "call one trivial no-argument MCP tool
once, then stop" -- the smallest possible non-trivial turn (prompt + one tool call + turn-end
summary). Expect on the order of a few hundred to low thousands of tokens, a small fraction of the
credit cap at any plausible per-token price -- **an estimate, not a guarantee; per B1 above,
`-TurnTimeoutS`, not `-CreditCap`, is the actual enforced backstop today.**

**Pass/fail verdict definition** (`verdict.json`'s `mcp_tool_call_completed` field):
- **PASS (M1 confirmed):** `mcp_tool_call_completed: true` -- app-server delivered the approval
  request, this client answered `accept`, and the MCP tool call actually completed with a result.
  This is the thing `codex exec` cannot do (`#16685`).
- **FAIL (M1 NOT confirmed as claimed):** `cancelled: true` -- the tool call was cancelled even
  under app-server. Would mean the spike report's "app-server structurally dodges the exec
  MCP-cancel bug" claim needs revisiting.
- **INCONCLUSIVE:** neither flag true and a "no terminal notification observed" note -- most
  likely one of the flagged real-server-shape assumptions above was wrong; read `transcript.jsonl`
  by hand before concluding anything.
- `credit_breaker_tripped: true` overrides all of the above to FAIL regardless of the other flags
  -- the run was killed before it could be trusted to have stayed under budget.

**Blank-agent / one-attempt / oracle-off-the-wire laws:** this is a single Codex app-server turn
against a `ping` tool, not a Pokemon-Red brain run -- there is no aria-memory to wipe and the only
"oracle" here would be RAM/score truth, which does not exist on this wire at all (the tool is
`ping`->`"pong"`, nothing game-related). The ONE-ATTEMPT discipline still applies in spirit: run
script (b) once; a scored `COMPLETED` or `CANCELLED` verdict is banked, not rerun to chase a better
number. Only a crash before `verdict.json` is written (infra death) may be retried once.
