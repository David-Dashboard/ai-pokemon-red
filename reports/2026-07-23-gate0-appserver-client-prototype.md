# Gate 0 -- `codex app-server` client prototype: what's proven at $0 vs the one remaining paid turn

Implements reports/2026-07-23-gate0-appserver-spike.md's prototype scope. ADDITIVE ONLY: no edits
to any pinned file (`tools/run_gate0_codex.ps1`, `tools/gate0_credit_breaker.py`,
`tools/gate0_credit_accountant.py`, `tools/gate0_codex_credit_rate.py`, the brain, `core/contracts.py`,
any tool schema, the launcher).

## Post-review fix round (2026-07-23, PR #147 adversarial review, REQUEST_CHANGES -> fixed)

The adversarial review found 3 BLOCKING defects, all fixed at $0 (same offline
`codex app-server generate-json-schema` re-run, no new codex invocation of any other kind):

1. **`initialize()` declared no `capabilities`.** `item/tool/requestUserInput` is EXPERIMENTAL in
   0.144.3 and gated by `InitializeCapabilities.experimentalApi` (default `false`); `openai/form`
   elicitations are gated by `mcpServerOpenaiFormElicitation`. Fixed: `initialize()` now sends
   `capabilities: {"experimentalApi": true, "mcpServerOpenaiFormElicitation": true}` (both field
   names confirmed against the committed `InitializeParams.json`), asserted by
   `test_initialize_declares_experimental_and_form_elicitation_capabilities`.
2. **Request side was ungrounded/circular.** Only the 5 `*Response.json` schemas were committed;
   the `_HANDLERS` method names and the param fields the client reads (`permissions`, `questions`,
   question `id`) were hand-matched to the mock, not to any ground-truth `*Params.json`. Fixed:
   committed the request-side schemas (list below) and added tests that fail if the client drifts:
   every `_HANDLERS` method must be a real `ServerRequest.json` branch; `permissions`/`questions`/`id`
   are asserted to be the REAL field names (they were -- no client field-name fix was needed, see
   "field names: before vs after" below). Also made drift fail LOUD instead of silent: a missing
   `permissions` key now raises `ValueError` (previously would have echoed `{}` = deny-all); a
   question missing `id` now raises a descriptive `ValueError` (previously an opaque `KeyError`);
   an unhandled server-request method is now logged (`event=unhandled_server_request`,
   method + request_id, no params/content) instead of a silent no-op.
3. **Report over-claimed "Verified".** Fixed by this rewrite: "Verified" below is now limited to
   what the 27-case test suite actually asserts against the committed schemas.

Non-blocking nit also addressed: the `mcpServer/elicitation/request` decoy test
(`test_elicitation_routes_to_the_originating_request_id_not_a_decoy`) previously set distinct
`threadId`s on the decoy/real requests but never asserted on them. It now asserts the audit
trail's `thread_id` field maps each request id back to its own threadId (`"decoy-id": "thr_decoy"`,
`"real-id": "thr_real"`), so the decoy/real distinction is load-bearing, not decorative.

## Files added
- `tools/gate0_appserver_client.py` -- the JSON-RPC-over-stdio client.
- `tests/test_gate0_appserver_client.py` -- mock-only tests, 27 cases, all passing.
- `tests/fixtures/gate0_appserver/*.json` -- 15 schemas the client is checked against: the 5
  response schemas from the original prototype (`ToolRequestUserInputResponse`,
  `McpServerElicitationRequestResponse`, `PermissionsRequestApprovalResponse`,
  `CommandExecutionRequestApprovalResponse`, `FileChangeRequestApprovalResponse`) plus 10
  request-side schemas added in the post-review fix round (`ServerRequest`, `InitializeParams`,
  `ThreadStartParams`, `ToolRequestUserInputParams`, `PermissionsRequestApprovalParams`,
  `McpServerElicitationRequestParams`, `CommandExecutionRequestApprovalParams`,
  `FileChangeRequestApprovalParams`, `JSONRPCRequest`, `JSONRPCResponse`) -- all copied verbatim
  from `codex app-server generate-json-schema` on codex-cli 0.144.3 (the same offline, $0,
  no-model-turn command the spike report used).

## Request-side field names: ground truth vs what the client used (post-review verification)

| Client reads | Ground-truth schema | Real field name | Client fix needed? |
|---|---|---|---|
| `params["permissions"]` in `build_permissions_response` | `PermissionsRequestApprovalParams.json` | `permissions` (required) | No -- already matched. |
| `params["questions"]` in `build_tool_user_input_response` | `ToolRequestUserInputParams.json` | `questions` (required) | No -- already matched. |
| `question["id"]` in `build_tool_user_input_response` | `ToolRequestUserInputParams.json` -> `ToolRequestUserInputQuestion` | `id` (required) | No -- already matched. |
| `_HANDLERS` method strings (5) | `ServerRequest.json` `oneOf` branches | `item/commandExecution/requestApproval`, `item/fileChange/requestApproval`, `item/tool/requestUserInput`, `mcpServer/elicitation/request`, `item/permissions/requestApproval` | No -- all 5 are real branches (confirmed via `test_all_handler_methods_are_real_server_request_branches`). |
| `initialize()` capabilities | `v1/InitializeParams.json` -> `InitializeCapabilities` | `experimentalApi`, `mcpServerOpenaiFormElicitation` (both booleans) | **Yes** -- `initialize()` sent no `capabilities` at all before this fix. |

The field names the client used were already correct; the review's concern (justified at the
time) was that this had never been checked against ground truth -- it was checked against the mock
only. It now is, and the check is a standing test, not a one-time read.

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

**Post-review re-run (same session's fix round):** re-ran the identical offline
`codex app-server generate-json-schema --out <tmpdir>` command again (still 0.144.3, still the
only codex invocation this round) specifically to pull the request-side files
(`ServerRequest.json`, `v1/InitializeParams.json`, `v2/ThreadStartParams.json`,
`ToolRequestUserInputParams.json`, `PermissionsRequestApprovalParams.json`,
`McpServerElicitationRequestParams.json`, `CommandExecutionRequestApprovalParams.json`,
`FileChangeRequestApprovalParams.json`, `JSONRPCRequest.json`, `JSONRPCResponse.json`) and commit
them verbatim under `tests/fixtures/gate0_appserver/` -- previously these were read once and cited
but never committed, which is what made the client's method/field names ungrounded (checked against
the mock, not the schema) per the review's Blocker 2.

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

## Test results (quoted verbatim, post-review fix round)

New file, from the primary venv:
```
tests/test_gate0_appserver_client.py ...........................  [100%]
27 passed in 0.22s
```

Full suite, same venv:
```
1474 passed, 16 skipped in 52.82s
```
(16 skips are pre-existing and unrelated to this change -- present before this work started; count
is 1468 + 6 new request-side-grounding/capability tests = 1474, consistent.)

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
payloads, using method names and param field names checked against committed ground-truth
`ServerRequest.json`/`*Params.json` (not just the mock); it declares the `experimentalApi`/
`mcpServerOpenaiFormElicitation` capabilities at `initialize()`; it routes each answer to its own
originating request (no cross-thread/turn bleed, now asserted via the audit trail, not just request
ids); it fails loud instead of silently deny-all/no-op on a missing required field or an unhandled
method; it never relies on an auto-accept timer; and it never auto-sends `turn/start`. It does
**not** prove that a real `codex app-server` process, given these exact responses, actually lets a
turn proceed past the #15824-regression approval prompt to a completed Docker MCP tool call. The
one paid turn must confirm, end-to-end, against the real `world_mcp` server: `initialize`
(with `capabilities` set) -> `thread/start` (`approvalsReviewer: "user"`) -> `turn/start` -> this
client answering whatever `item/tool/requestUserInput`/`mcpServer/elicitation/request`/
`item/permissions/requestApproval` prompts actually arrive -> `item/completed` with a real,
non-cancelled MCP tool result. It should also settle:
- whether `mcpServer/elicitation/request` in `mode: "form"` needs non-empty `content` in the
  response (this client currently omits it) for a given MCP server to actually accept the elicitation;
- the exact runtime semantics of `experimentalApi`/`mcpServerOpenaiFormElicitation` gating --
  declared per the schema (confirmed at $0), but whether app-server actually delivers
  `item/tool/requestUserInput` once these are set true, and whether any other undocumented
  precondition exists, is a live-server behavior this offline schema dump cannot confirm.

## Assumptions vs verified facts

- **Verified**: all 5 `_HANDLERS` method names are real `ServerRequest.json` branches; the
  `permissions`/`questions`/question-`id` field names the client reads are the real
  `*Params.json` field names; the `experimentalApi`/`mcpServerOpenaiFormElicitation` capability
  field names and nesting (`InitializeParams.capabilities.InitializeCapabilities.*`); all 5 response
  shapes; the `approvalsReviewer`/`ApprovalsReviewer` enum; JSONL framing with no `jsonrpc` field;
  and `turn/start`'s required fields -- all read directly from the 0.144.3 schema dump or
  `codex-rs/app-server/README.md`, quoted above, and now enforced by a standing test, not just a
  one-time read.
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
- **Must-confirm-at-paid-turn**: the exact runtime effect of declaring `experimentalApi: true` and
  `mcpServerOpenaiFormElicitation: true` -- the schema confirms these are the right field names and
  that they gate the target request/mode, but whether setting them true is *sufficient* (vs some
  other undocumented precondition) can only be confirmed against a live `codex app-server` process.
