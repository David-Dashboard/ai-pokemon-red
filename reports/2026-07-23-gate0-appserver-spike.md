# Gate 0 — `codex app-server` spike: does it dodge the headless MCP-cancel bug? ($0, no exec run)

Follow-up to `reports/2026-07-22-codex-mcp-headless-trust-research.md` option (c). Method: local
inspection of installed **codex-cli 0.144.3** — `codex app-server --help`, and
`codex app-server generate-json-schema --out <dir>` (offline, deterministic; **no model turn, no
`codex exec`, no bypass flag**) — cross-checked against GitHub issues/PRs. Schema files dumped to
scratchpad; the request/response shapes below are copied from that dump, not from memory.

## Verdict: VIABLE — needs a small custom client (NEEDS-PROTOTYPE), no sandbox bypass

app-server structurally dodges the exec MCP-cancel bug. The bug (#16685) is *"exec has no channel to
answer the approval, stdin EOF → decline → cancel."* app-server IS a bidirectional JSON-RPC server:
it surfaces every approval/elicitation/user-input as a **server→client request with a typed response**,
so a client can answer instead of EOF-declining. Answering requires **no**
`--dangerously-bypass-approvals-and-sandbox`. Caveat: no off-the-shelf headless client answers these
correctly yet (HAPI/plugin-cc both fail) — Gate 0 must write a ~200-line JSON-RPC client. End-to-end
proof (a Docker MCP tool call actually completing) still needs **one paid turn**, out of scope here.

## The mechanism (ground truth from 0.144.3 `ServerRequest`)

Server→client request methods the client must handle (from generated `ServerRequest.json`):
- `mcpServer/elicitation/request` → response `{ action: "accept"|"decline"|"cancel", content? }`
  — an MCP server's own elicitation, forwarded verbatim. Client answers `accept`.
- `item/tool/requestUserInput` → response `{ answers: { <questionId>: { answers: [<label>] } } }`
  — this is the `RequestUserInput` "Approve app tool call?" prompt from the #15824 regression
  (the exact thing that EOF-declines under exec). Client answers by selecting the approve option.
- `item/permissions/requestApproval` → response `{ permissions: <profile>, scope: "turn"|"session" }`
  — grants **scoped** filesystem/network permission for a turn/session. This is the clean,
  non-bypass counterpart to the global dangerous flag: widen the sandbox per-request, not globally.
- (also `item/commandExecution/requestApproval`, `item/fileChange/requestApproval` for shell/patch.)

Transport (`codex app-server --help`): `--listen stdio://` (default), `unix://PATH`, `ws://IP:PORT`;
plus `daemon`/`proxy` subcommands. A custom client drives it over stdio — no network exposure needed.

## Why exec breaks but app-server doesn't

The #15824 regression (non-`codex_apps` MCP calls wrongly enter the app-tool approval flow) still
fires in BOTH modes — app-server does NOT fix it. The difference is the *outcome*: under exec the
prompt hits `RequestUserInput` with closed stdin → EOF → decline → "user cancelled MCP tool call"
(#16685). Under app-server the identical prompt arrives as an `item/tool/requestUserInput` /
`mcpServer/elicitation/request` request the client answers `accept`. If #15824 is later fixed, the
prompt stops firing entirely — app-server is robust either way. `approval_policy="never"` is NOT
relied on (it doesn't suppress the MCP path — the #24135 negative result carries over).

## What Gate 0 must build (prototype scope) + residual risks

Client: spawn `codex app-server`, initialize, `thread/start` with `approvalsReviewer:"user"` (so it
receives the requests — `auto_review`/`guardian` would auto-resolve but need their own trust reasoning),
run one turn, and reply `accept`/answers to the three request types above, echoing `threadId`/`turnId`/
`itemId`. Known sharp edges to test against, from real integrators failing this exact bridge:
- HAPI #287: no handler registered → codex cancels ("missing field `answers`"). Response MUST be the
  exact `ToolRequestUserInputResponse{answers}` shape.
- codex-plugin-cc #258: resolving elicitation against the wrong thread/turn → "elicitation request not
  found". Route the answer to the originating thread/turn.
- #18268 (codex-mcp-server): elicitation response deserialized wrong → silently defaults to Denied.
- PR #27256: `autoResolutionMs` is contract-plumbing only, NOT implemented — no built-in auto-accept
  timer; the client must actively answer each request.

## Citations
- Local: `codex app-server --help`; `codex app-server generate-json-schema` on codex-cli 0.144.3
  (files: `ServerRequest.json`, `ToolRequestUserInputParams/Response.json`,
  `McpServerElicitationRequestResponse.json`, `PermissionsRequestApprovalResponse.json`).
- openai/codex #15824 (open — non-codex_apps MCP calls block on app-tool approval), #16685 (exec
  cancel), #24135 (config-key negatives), PR #27256 (autoResolutionMs contract-only, merged 2026-06-12).
- tiann/hapi #287, openai/codex-plugin-cc #258, openai/codex #18268 (headless clients failing the bridge).
- app-server protocol: developers.openai.com/codex/app-server; codex-rs/app-server/README.md;
  codex-rs/docs/codex_mcp_interface.md.
