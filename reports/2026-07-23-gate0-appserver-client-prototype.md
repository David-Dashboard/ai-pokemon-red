# Gate 0 -- `codex app-server` client prototype: what's proven at $0 vs the one remaining paid turn

Implements reports/2026-07-23-gate0-appserver-spike.md's prototype scope. ADDITIVE ONLY: no edits
to any pinned file (`tools/run_gate0_codex.ps1`, `tools/gate0_credit_breaker.py`,
`tools/gate0_credit_accountant.py`, `tools/gate0_codex_credit_rate.py`, the brain, `core/contracts.py`,
any tool schema, the launcher).

## Files added
- `tools/gate0_appserver_client.py` -- the JSON-RPC-over-stdio client.
- `tests/test_gate0_appserver_client.py` -- mock-only tests, 21 cases, all passing.
- `tests/fixtures/gate0_appserver/*.json` -- the 5 response schemas the client is checked against
  (`ToolRequestUserInputResponse`, `McpServerElicitationRequestResponse`,
  `PermissionsRequestApprovalResponse`, `CommandExecutionRequestApprovalResponse`,
  `FileChangeRequestApprovalResponse`), copied verbatim from `codex app-server generate-json-schema`
  on codex-cli 0.144.3 (the same offline, $0, no-model-turn command the spike report used).

## Ground truth this session re-verified (not re-guessed)

Re-ran `codex app-server generate-json-schema --out <tmpdir>` (0.144.3) -- same file set the spike
report names (`ServerRequest.json`, `ToolRequestUserInputParams/Response.json`,
`McpServerElicitationRequestParams/Response.json`, `PermissionsRequestApprovalParams/Response.json`,
plus `CommandExecutionRequestApprovalParams/Response.json` and `FileChangeRequestApprovalParams/
Response.json` for the two robustness handlers, and `v1/InitializeParams/Response.json`,
`v2/ThreadStartParams/Response.json`, `v2/TurnStartParams.json`, `ClientRequest.json`,
`ClientNotification.json`, `JSONRPCRequest/Notification/Response/Message.json`). No other codex
invocation was made.

**Framing** was the one thing the spike report and `codex app-server --help` didn't nail down
(`--help` documents `--listen stdio://` as the default transport but not its byte framing). Verified
from `codex-rs/app-server/README.md`'s "Protocol" section (fetched via `gh api
repos/openai/codex/contents/codex-rs/app-server/README.md`, an external doc, not a codex call):
> "Similar to MCP, `codex app-server` supports bidirectional communication using JSON-RPC 2.0
> messages (with the `"jsonrpc":"2.0"` header omitted on the wire)."
> "stdio (`--stdio` or `--listen stdio://`, default): newline-delimited JSON (JSONL)"

So: **one JSON-RPC message per line, LF-terminated, no `"jsonrpc"` key** -- NOT Content-Length/LSP
framing. Cross-checked against the generated `JSONRPCRequest`/`JSONRPCNotification`/
`JSONRPCResponse` schemas: none of them declare a `jsonrpc` field, consistent with the README.
`initialize`/`thread/start`/`turn/start` method names were confirmed as literal enum values in
`ClientRequest.json`; the `initialized` client notification was confirmed in `ClientNotification.json`.

## The exact response shape implemented for each of the 4 `ServerRequest` types

| Method | Response (byte-exact) | Schema check |
|---|---|---|
| `mcpServer/elicitation/request` | `{"action": "accept"}` | `action` in `McpServerElicitationAction` enum (`accept`\|`decline`\|`cancel`); `content` deliberately omitted -- optional per schema, and this $0 prototype has no real form data to supply for `mode: "form"`/`"openai/form"`. |
| `item/tool/requestUserInput` | `{"answers": {"<questionId>": {"answers": ["<approve label>"]}}}` | Matches `ToolRequestUserInputResponse`/`ToolRequestUserInputAnswer` exactly (both required-keys and value types checked). Approve label picked case-insensitively from `question.options[].label` via keywords `("approve","yes","allow","accept","ok","confirm")`; falls back to the first offered option, then to a fixed `"Approve"` string if no options are offered at all. |
| `item/permissions/requestApproval` | `{"permissions": <verbatim echo of the requested profile>, "scope": "session"}` | `permissions`/`scope` required-key and `PermissionGrantScope` enum (`turn`\|`session`) checked. Echoes back exactly what was requested (README: "Only the granted subset matters on the wire" -- omitted permissions are denied), so it never grants more than asked. `scope` defaults to `"session"` (the schema's own default is `"turn"`) -- configurable via `permission_scope=` -- because Gate 0's target scenario is one turn making several Docker-MCP tool calls that would otherwise each re-prompt; this is still a scoped, revocable grant of only the requested fileSystem/network entries, never `--dangerously-bypass-approvals-and-sandbox`. |
| `item/commandExecution/requestApproval` (robustness) | `{"decision": "accept"}` | `decision` in `CommandExecutionApprovalDecision`'s plain-string branches. |
| `item/fileChange/requestApproval` (robustness) | `{"decision": "accept"}` | `decision` in `FileChangeApprovalDecision`'s plain-string branches. |

`thread/start` is called with `approvalsReviewer: "user"` (confirmed as a valid `ApprovalsReviewer`
enum value in `ThreadStartParams.json`) so these requests are routed to this client rather than an
auto-resolving reviewer.

## The 4 real-integrator failure modes, each covered by a dedicated test

- **HAPI #287** (`test_tool_user_input_response_shape_is_byte_exact_hapi_287`) -- asserts the exact
  `{"answers": {...}}` shape and validates it against the committed `ToolRequestUserInputResponse.json`.
- **codex-plugin-cc #258** (`test_tool_user_input_routes_to_the_originating_request_not_a_decoy`,
  `test_elicitation_routes_to_the_originating_request_id_not_a_decoy`) -- feeds a "real" and a
  "decoy" request with different ids/threadId/turnId/itemId/question-id and asserts each response
  carries its own JSON-RPC `id` and its own question-id keys, with no cross-contamination.
- **openai/codex #18268** (`test_elicitation_response_matches_schema_openai_codex_18268`) -- asserts
  the literal `{"action": "accept"}` value against the `McpServerElicitationAction` enum (not a
  near-miss like `{"decision": "approve"}` that would silently default to Denied).
- **PR #27256** (`test_tool_user_input_never_relies_on_autoResolutionMs_timer`) -- calls the builder
  with and without a (huge) `autoResolutionMs` value present and asserts identical, immediate
  (`< 1s`) output either way; the implementation never reads that field.

## Test results (quoted verbatim)

New file, from the primary venv:
```
tests/test_gate0_appserver_client.py .....................            [100%]
21 passed in 0.21s
```

Full suite, same venv:
```
1468 passed, 16 skipped in 54.83s
```
(16 skips are pre-existing and unrelated to this change -- present before this work started.)

## $0-compliance statement

- No `codex exec` was run. No real model turn was run. No ChatGPT/Codex-pool spend occurred.
- The only `codex` invocation made this session was the offline, deterministic
  `codex app-server generate-json-schema --out <tmpdir>` (twice: once for the spike, re-confirmed
  once more this session against the same 0.144.3 binary) -- no model call, no network call to
  OpenAI, no `--dangerously-bypass-approvals-and-sandbox`, no sandbox disabling.
- The test suite spawns no subprocess of `codex` at all; it drives `Gate0AppServerClient` through
  an injected `send=` recorder (an in-process fake JSON-RPC peer), so it runs unchanged on Linux CI.
- No pinned Gate 0 file, the brain, `core/contracts.py`, any tool schema, or the launcher was edited
  -- `git status` shows only new, untracked files.

## What the one remaining paid turn must confirm

This prototype proves: the client answers all four request types with schema-correct, byte-exact
payloads; it routes each answer to its own originating request (no cross-thread/turn bleed); it
never relies on an auto-accept timer; and it never auto-sends `turn/start`. It does **not** prove
that a real `codex app-server` process, given these exact responses, actually lets a turn proceed
past the #15824-regression approval prompt to a completed Docker MCP tool call. The one paid turn
must confirm, end-to-end, against the real `world_mcp` server: `initialize` -> `thread/start`
(`approvalsReviewer: "user"`) -> `turn/start` -> this client answering whatever
`item/tool/requestUserInput`/`mcpServer/elicitation/request`/`item/permissions/requestApproval`
prompts actually arrive -> `item/completed` with a real, non-cancelled MCP tool result. It should
also settle the one open design question this prototype could not resolve at $0: whether
`mcpServer/elicitation/request` in `mode: "form"` needs non-empty `content` in the response (this
client currently omits it) for a given MCP server to actually accept the elicitation.

## Assumptions vs verified facts

- **Verified**: all method names, all 4 response shapes, the `approvalsReviewer`/`ApprovalsReviewer`
  enum, JSONL framing with no `jsonrpc` field, and `turn/start`'s required fields -- all read
  directly from the 0.144.3 schema dump or `codex-rs/app-server/README.md`, quoted above.
- **Verified**: codex.exe at `C:\Users\Succe\AppData\Local\Programs\OpenAI\Codex\bin\codex.exe`,
  version 0.144.3 (`codex --version`), matching the spike report's pin.
- **Assumption**: the approve-label keyword heuristic (`approve`/`yes`/`allow`/`accept`/`ok`/
  `confirm`, case-insensitive substring match, else first option, else a fixed `"Approve"` string)
  is a reasonable guess at how a real `item/tool/requestUserInput` "Approve app tool call?" prompt
  labels its options -- the schema constrains the response *shape*, not the specific label text a
  live server will offer, so this is untested against a real prompt and is exactly the kind of thing
  the paid turn's transcript should be inspected for (did it pick the option the run actually needed).
- **Assumption**: omitting `content` on `mcpServer/elicitation/request` accept responses is
  schema-legal (confirmed) but may or may not be sufficient for a specific MCP server's `mode: "form"`
  request in practice (not confirmed -- see "what the paid turn must confirm" above).
