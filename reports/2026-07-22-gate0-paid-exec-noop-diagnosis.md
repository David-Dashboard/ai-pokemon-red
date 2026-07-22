# Gate 0 paid `codex exec` NO-OP — diagnosis (2026-07-22)

**Spend: ~$0 (ChatGPT subscription, no API-key metering).** No `-PaidExec` real-launcher run.
`tools/run_gate0_codex.ps1` was only read, never modified. All repro used standalone scratch
scripts (kept outside the repo) calling `codex exec --json` directly, mirroring
`Get-PaidCodexExecArguments`/`Invoke-BreakerSupervisedExec`, writing to scratch world dirs — never
`runs/gate0_paid/red/world/` (that banked run's empty dir was left untouched). No docker
containers or codex processes remain running.

## What the banked run showed
`runs/gate0_paid/red/paid/accountant-verdict.json`: `result=COMPLETED`,
`events_seen_before_halt=7`, `final_total_normalized_credits=0.0`. Child ran 17s, exit 0,
`ChildKilled=false` (exited on its own). `runs/gate0_paid/red/world/` empty (no oracle/frames).

## Reproduction (trivial 1-observe task, real launcher's exact `-c` overrides + cwd + restored real `CODEX_HOME`)
Captured raw `--json` stdout directly (the real launcher pipes this to the accountant and never
saves it — that's why the original run was a black box). First attempt, task = "call `observe`
once, describe it, stop":
```
{"type":"thread.started",...}
{"type":"turn.started"}
{"type":"item.completed","item":{"id":"item_0","type":"agent_message","text":""}}
{"type":"item.started","item":{"id":"item_1","type":"mcp_tool_call","server":"gate0_world","tool":"observe","arguments":{},"result":null,"error":null,"status":"in_progress"}}
{"type":"item.completed","item":{"id":"item_1","type":"mcp_tool_call","server":"gate0_world","tool":"observe","arguments":{},"result":null,"error":{"message":"user cancelled MCP tool call"},"status":"failed"}}
{"type":"item.completed","item":{"id":"item_2","type":"agent_message","text":"The observation was cancelled, so no screen state was returned."}}
{"type":"turn.completed","usage":{"input_tokens":24024,"cached_input_tokens":11008,"output_tokens":255,"reasoning_output_tokens":162}}
```
**7 lines — matches `events_seen_before_halt=7` exactly.** Scratch `world/` dir stayed empty
(0 files) — the docker MCP container never got a chance to run `world_mcp.py`'s handler at all;
the cancellation happens before the call reaches it.

## Root cause
The **first real `gate0_world` MCP tool call** in headless `codex exec` is auto-cancelled by Codex
itself (`error.message = "user cancelled MCP tool call"`), before dispatch to the MCP subprocess.
The model gets the cancellation back, apologizes, and the turn completes normally (exit 0) — a
structurally clean "no-op", not a crash, which is why the launcher/breaker saw nothing wrong.

Ruled out (identical failure — same 7-event shape, same message — across all variants tested):
- **NOT sandbox_mode**: reran with `sandbox_mode="workspace-write"` instead of `"read-only"` — same cancellation.
- **NOT the two most-likely feature flags**: reran with `features.tool_call_mcp_elicitation=false` and
  `features.guardian_approval=false` added (both `stable`/enabled-by-default per `codex features list`,
  and neither is in the launcher's `$Overrides`) — same cancellation.
- **NOT a bad/unknown `-c` key**: reran with `--strict-config` (errors on any unrecognized config
  field) — exit 0, no schema error, same cancellation. So `mcp_servers.gate0_world.default_tools_approval_mode`
  and every other override key parse as valid fields — they just have **no observed effect** on this gate.
- **NOT the account/model/exec path**: the turn is a real model call (~24k input tokens, real
  reasoning/output tokens each time) — same conclusion as the plain `codex exec ... "trivial shell
  task"` test from earlier the same day. `approval_policy` (`-a`/`--ask-for-approval` per
  `codex exec --help`) is documented as governing **shell command** approval, not MCP tool calls —
  consistent with it having zero effect here.

**Unconfirmed candidate, NOT tested**: `codex exec --help` lists exactly one flag claiming to
"skip all confirmation prompts": `--dangerously-bypass-approvals-and-sandbox`. An attempt to test
it this session was **blocked by the harness's own auto-mode safety classifier** (name matches a
dangerous-action pattern); I did not attempt to route around that block, per safety-invariants §9.
It remains the single best untested lead — but it also drops Codex's own command sandboxing
entirely, a real regression worth a separate call, not a silent trade.

## Recommended fix (do NOT apply — signature-hash-checked launcher; needs plan → PR → review → David)
Top 2 candidates, cheapest-confirming-test first:
1. **Find the real MCP-tool-approval gate.** `default_tools_approval_mode="auto"` had zero
   measurable effect — likely the wrong key name for this Codex CLI version (0.144.3), possibly
   copied from a different tool's vocabulary. Check `codex-cli`'s own docs/changelog/source for
   the field that actually gates MCP tool-call confirmation (distinct from `approval_policy`), or
   an analogous **persisted trust** mechanism like hooks' `[hooks.state]`/`--dangerously-bypass-hook-trust`
   — MCP servers may need one-time persisted trust the same way, not just ephemeral `-c` overrides.
2. **`--dangerously-bypass-approvals-and-sandbox`** (fallback, cheap to test once David explicitly
   authorizes it, since it's classifier-flagged and drops sandboxing) — confirm with the same
   trivial 1-observe task; if it fixes it, the launcher needs an explicit, reviewed decision about
   losing Codex's shell sandbox (the `--network none` + read-only ROM/state mounts still bound the
   MCP subprocess itself, but this flag is broader than that).

## Zero-spend confirmation
Real token usage occurred (4 confirmatory runs, ~24-25k input / ~250-300 output tokens each) but
under ChatGPT subscription auth (not `OPENAI_API_KEY`/metered billing) — same accounting basis the
banked run itself used to report "~$0 spent" (`final_total_normalized_credits=0.0`). No gameplay
turns ever executed (every attempt failed identically at the first tool call); no docker
containers or codex processes remain running; `runs/gate0_paid/red/` was not touched.
