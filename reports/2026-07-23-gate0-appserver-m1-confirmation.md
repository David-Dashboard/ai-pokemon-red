# Gate 0 M1 app-server unblock — CONFIRMED end-to-end (PASS, real paid turn, 2026-07-23)

**VERDICT: PASS.** The one remaining paid turn that
`reports/2026-07-23-gate0-appserver-client-prototype.md` (PR #147) and
`reports/2026-07-23-gate0-appserver-launch-runbook.md` (PR #151) each flagged as
"must confirm at paid turn" has now run, against real `codex-cli 0.144.3`, and the round-trip
completed: the `#15824`/`#16685` approval prompt fired, `tools/gate0_appserver_client.py`
answered it, and the MCP tool call completed with a result. This is the exact failure mode
`codex exec` cannot get past (`reports/2026-07-22-codex-mcp-headless-trust-research.md` Q4) —
confirmed structurally fixed by driving the same approval prompt through `codex app-server` instead.

Scored from the raw transcript by the orchestrator (not from the harness's own boolean, which
independently agreed) per `reports/2026-07-23-gate0-appserver-launch-runbook.md`'s pre-registered
pass/fail definition.

## Hypothesis under test

`codex app-server` (JSON-RPC over stdio) structurally dodges the upstream `codex exec` MCP-cancel
bug: because approval requests arrive as answerable RPC (`mcpServer/elicitation/request` /
`item/tool/requestUserInput`) rather than a stdin-EOF read, a client that answers `accept` lets a
non-`codex_apps` MCP tool call (e.g. `gate0_stub`'s `ping`) complete, where `codex exec` fatally
EOF-declines the identical prompt.

## Method

**$0 gates that preceded this run** (all pre-registered, all re-confirmed by this report's
cross-references, none re-run here):
1. Offline schema dump (`codex app-server generate-json-schema`, 0.144.3) — grounded the client's
   method names and field names against real `*Params.json`/`*Response.json`, not the mock
   (`reports/2026-07-23-gate0-appserver-client-prototype.md`).
2. Mock-only client tests (27 cases) + full suite green, no `codex` process spawned
   (same report).
3. `--dry-run` stub-peer drive of the launcher, both `"completes"` and `"cancelled"` scenarios
   scored correctly (`reports/2026-07-23-gate0-appserver-launch-runbook.md`).
4. Live $0 handshake smoke against the real binary: `initialize` (with `capabilities`) →
   `thread/start` succeeds, no `turn/start` sent, no tokens spent (same report, HANDOFF wave-2
   entry).
5. Stub-seam check: `gate0_stub_mcp_server.py` (`ping` → `"pong"`) reproduces the world-agnostic
   `#15824` approval path without Docker (Docker daemon was down on the launch host).

**The paid turn**, run once, real spend:
```
tools/gate0_appserver_launch.py --mcp stub --model gpt-5.6-sol \
    --codex-home C:\Users\Succe\.codex --turn-timeout-s 45 \
    --tool-name ping --prompt "Call the ping tool exactly once, then stop."
```
against real `codex.exe` 0.144.3. `--codex-home` pointed at the real, already-`codex login`'d
`~/.codex` (not an isolated empty dir — see caveats).

**First attempt (not scored, not spend):** an isolated-empty `CODEX_HOME` (no `auth.json`) died at
`initialize()` — infra death before any turn, $0 spent. Per law 6 (bounded-steps / infra-death
retry) this permitted one relaunch; the relaunch used `--codex-home` pointing at the real home,
which is the run scored below.

## Round-trip evidence (quoted from the raw transcript, `transcript.jsonl` this report banks)

**Turn starts, Sol reasons, emits the tool call** (`item/started` → `mcpToolCall`, `status:
"inProgress"`):
```json
{"method": "item/started", "params": {"item": {"arguments": {}, "id": "exec-ba4a53b9-0302-4269-a530-a594e4af281c", "result": null, "server": "gate0_stub", "status": "inProgress", "tool": "ping", "type": "mcpToolCall"}, ...}}
```

**Thread status flips to `waitingOnApproval`:**
```json
{"method": "thread/status/changed", "params": {"status": {"activeFlags": ["waitingOnApproval"], "type": "active"}, "threadId": "019f90f2-2ca4-7531-a0fe-d65fc3e6797c"}}
```

**Approval prompt FIRES** — the exact `#15824`/`#16685` prompt headless `codex exec` fatally
EOF-declines:
```json
{"id": 0, "method": "mcpServer/elicitation/request", "params": {"_meta": {"codex_approval_kind": "mcp_tool_call", "persist": ["session", "always"], "tool_description": "Trivial no-op tool: takes no required input, always returns the text 'pong'.", "tool_params": {}, "tool_params_display": []}, "message": "Allow the gate0_stub MCP server to run tool \"ping\"?", "mode": "form", "requestedSchema": {"properties": {}, "type": "object"}, "serverName": "gate0_stub", "threadId": "019f90f2-2ca4-7531-a0fe-d65fc3e6797c", "turnId": "019f90f2-3044-7492-8e52-68049ad1c804"}}
```

**Client ANSWERS**, routed to the originating id:
```json
{"id": 0, "result": {"action": "accept"}}
```
```json
{"method": "serverRequest/resolved", "params": {"requestId": 0, "threadId": "019f90f2-2ca4-7531-a0fe-d65fc3e6797c"}}
```

**Tool call COMPLETES** — `error: null`, real result:
```json
{"method": "item/completed", "params": {"item": {"arguments": {}, "durationMs": 4, "error": null, "id": "exec-ba4a53b9-0302-4269-a530-a594e4af281c", "result": {"content": [{"text": "pong", "type": "text"}]}, "server": "gate0_stub", "status": "completed", "tool": "ping", "type": "mcpToolCall"}, ...}}
```

**Turn COMPLETES:**
```json
{"method": "turn/completed", "params": {"turn": {"completedAt": 1784843233, "durationMs": 14447, "error": null, "id": "019f90f2-3044-7492-8e52-68049ad1c804", "status": "completed"}, "threadId": "019f90f2-2ca4-7531-a0fe-d65fc3e6797c"}}
```

No cancel, no error, anywhere on the tool call or the turn.

**Token usage** (`thread/tokenUsage/updated`, final):
```json
{"tokenUsage": {"total": {"cachedInputTokens": 9984, "inputTokens": 21980, "outputTokens": 384, "reasoningOutputTokens": 309, "totalTokens": 22364}}}
```
Est. cost ≈ **$0.08** at the pinned rate. `account/rateLimits/updated` reports `planType: "plus"`,
weekly window `usedPercent: 1`.

## Spend

One real turn, ≈$0.08 estimated, weekly window ~1% used. The dead isolated-`CODEX_HOME` first
attempt spent $0 (died at `initialize`, before any turn).

## Caveats (stated honestly)

- The run used the real `~/.codex` home (not an isolated one), so the user's own `node_repl` MCP
  server tried to start and FAILED harmlessly:
  `"MCP client for node_repl failed to start: MCP startup failed: The directory name is invalid.
  (os error 267)"`. This is irrelevant to the ping confirmation — `gate0_stub` independently reached
  `status: "ready"` and served the tool call. No brain/config edit caused this; it is a side effect
  of pointing `--codex-home` at a real, populated `~/.codex` rather than an isolated one (see
  Follow-up (b)).
- This confirms the **app-server unblock mechanism** — it does not re-run or replace the Docker
  `gb-mcp-world` Gate-0 Red/MiniWoB paired-arms experiment, which is a separate, still-pending step
  now UNBLOCKED by this result (Docker daemon was down on the launch host at spike/runbook time;
  unaffected by this confirmation either way — see Scope).
- Scored by the orchestrator reading the raw transcript directly (the quotes above), not solely by
  trusting `verdict.json`'s boolean — the harness's own scoring agreed:
  `mcp_tool_call_completed: true`, `cancelled: false`.

## Scope

**This confirms:** the app-server unblock MECHANISM — that answering `codex app-server`'s
answerable RPC approval prompt with `accept` lets a non-`codex_apps` MCP tool call complete,
clearing the upstream `codex exec` MCP-cancel blocker (`#15824`/`#16685`) that no-op'd earlier
Gate-0 attempts (`reports/2026-07-22-codex-mcp-headless-trust-research.md`).

**This does NOT confirm:** the full Gate-0 Red/MiniWoB paired arms. That remains a separate,
still-to-be-run step — now unblocked by this result, not completed by it. Swapping the stub for
the real Docker `gb-mcp-world` server is a `--mcp docker` flag away per the launcher's design
(`reports/2026-07-23-gate0-appserver-launch-runbook.md`), not a new code path, but it has not been
exercised.

## Cross-references

- `reports/2026-07-23-gate0-appserver-client-prototype.md` (PR #147) — the JSON-RPC client this
  turn drove, and the "must confirm at paid turn" list this result closes.
- `reports/2026-07-23-gate0-appserver-launch-runbook.md` (PR #151) — the launcher, stub MCP server,
  and pre-registered PASS/FAIL/INCONCLUSIVE verdict definition this report scores against.
- `reports/2026-07-22-codex-mcp-headless-trust-research.md` — the upstream root-cause research
  (`#15824`/`#16685`/`#24135`) this confirmation clears.

## Evidence filed

- `reports/2026-07-23-gate0-appserver-m1-confirmation/transcript.jsonl` — the complete raw
  send/receive JSON-RPC transcript, copied verbatim, append-only (not edited).
- `reports/2026-07-23-gate0-appserver-m1-confirmation/verdict.json` — the harness's own
  `verdict.json` for this run, copied verbatim alongside.

## FOLLOW-UPS

**(a) Make `--credit-cap` live on the app-server transport (B1 from the runbook).** The real
usage-notification shape is now known from this run:
`thread/tokenUsage/updated` with `params.tokenUsage.total.{inputTokens, cachedInputTokens,
outputTokens, reasoningOutputTokens, totalTokens}` (see the quoted notification above). The
launcher's credit converter (`tools/gate0_codex_credit_rate.py::codex_event_to_credit_event`)
currently only recognizes the exec-shaped `{"type": "token_count", ...}` event and never sees
this JSON-RPC notification, so `--credit-cap` stays inert on this transport today
(`LiveCreditGuard` never prices anything real). This can now be extended, additively, to parse the
`thread/tokenUsage/updated` shape into the same credit-event stream, using the pinned
`--credit-rate-pin` rate — not guessed, now grounded against a real observed notification.

**(b) Complete isolation of the isolated `codex-home`, not just `auth.json`.** The first attempt
died at `initialize()` on an isolated-empty `CODEX_HOME` with no `auth.json` (infra death, $0,
permitted one relaunch under law 6). The relaunch used the real `~/.codex` home to get real auth,
which is why the user's own `node_repl` MCP server tried (and harmlessly failed) to start
alongside `gate0_stub` (see Caveats). The isolated-home path currently only seeds `auth.json`
(`reports/2026-07-23-gate0-appserver-launch-runbook.md`'s N3 fix); it should also isolate or strip
the rest of `~/.codex/config.toml`'s `[mcp_servers.*]` block so a run's MCP server set is exactly
what the launcher registers — no unrelated real servers starting (harmlessly or otherwise) inside
a supposedly isolated run.
