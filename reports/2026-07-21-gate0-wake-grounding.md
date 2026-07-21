# Gate 0 wake grounding: does turn.completed == 1 wake?

Offline, $0. Grounds PR #125's wake definition against one real Codex transcript
(`codex exec --json -s read-only -m gpt-5.6-sol "run 'echo hi', report exactly what
it printed"` — needs >=2 model decisions: call-the-shell-tool, then compose-the-
final-answer). 22 physical lines; only 7 are valid JSON — the rest is PowerShell/
sandbox stderr noise interleaved into the capture (its own finding, see Verdict).
The shell call itself failed (Windows sandbox helper missing); fine, we only need
event shape, not a successful run.

## Event table (valid JSON lines only)

| type | count | item.type breakdown |
|---|---|---|
| thread.started | 1 | - |
| turn.started | 1 | - |
| item.completed | 3 | agent_message x2, command_execution x1 |
| item.started | 1 | command_execution x1 |
| turn.completed | 1 | - |
| non-JSON noise lines | 15 | PowerShell preamble (7) + Rust sandbox error log (8) |

Sole `turn.completed`, verbatim (field names only, no secret values):
```
{"type":"turn.completed","usage":{"input_tokens":28332,"cached_input_tokens":23040,"output_tokens":160,"reasoning_output_tokens":33}}
```

## Actual decision count

`item_0` agent_message ("I'll run the command exactly as given.") -> `item_1`
command_execution (started, then failed) -> `item_2` agent_message ("It printed
nothing; the shell failed..."). That's **>=2** decisions (call-the-tool, then
compose-final-answer after seeing the result) — possibly 3 if the narration
(`item_0`) and the call (`item_1`) came from separate responses. Undecidable from
the schema: item ids are sequential thread-wide, no response/invocation id.

**turn.completed count: 1. Actual decisions: >=2 (up to 3).**

## turn.completed usage semantics

One `turn.completed` line covers a turn holding 2 agent_message items + 1 tool
call, so its usage (28332/23040/160/33) is **cumulative for the whole turn** —
every model round-trip bundled, not per-single-call. No `item.completed` event
carries any usage/token field; usage lives only on `turn.completed`, at turn
granularity. No finer per-decision event exists: `agent_message` items undercount
(a tool-call-only decision emits no message), `item.started` for
`command_execution` undercounts symmetrically (neither agent_message item here
got an `item.started`). Neither is a clean proxy, and no id ties items to one
invocation. Matches the design doc's own caveat (`reports/2026-07-13-minimum-
north-star-gate-0-design.md`, L237-241): "does not document per-model-call wake
boundaries. Do not substitute tool calls, JSONL events, or turns for wakes."

## Verdict

PR #125 sets `wakes = usage_events` (count of `turn.completed` with valid usage) —
exactly "1 turn.completed == 1 wake." This transcript falsifies that: 1
`turn.completed`, >=2 real decisions inside it — a >=2x undercount here (not a
general ratio; one turn only, but enough to prove the definition unsound). No
clean per-decision observable exists in Codex's JSONL as captured, so this is not
"count event X instead" — there is no right event to switch to. (Separately: real
captures mix non-JSON stderr into the stream, which the checker's `json.loads`
per line already flags as `malformed_jsonl` -> `NO_LEAK`, so this never reaches
wake counting in practice — but that's a capture-hygiene issue, not this question.)

## Recommendation for PR #125

Do not merge `wakes = usage_events` as "wakes." Revert `audit()` to the fail-
closed hardcode (`wakes=None`, `wake_accounting="INSUFFICIENT_WAKES"`) until Codex
ships a documented per-model-call boundary event. Keep the PR's other plumbing
(agent_metrics.json, gate0_wake_boundary.py) if wanted, but gate `wakes` itself on
`INSUFFICIENT_WAKES` — same as pre-#125 main — not a turn count under that name.
