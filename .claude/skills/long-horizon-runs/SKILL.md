---
name: long-horizon-runs
description: Running the paid brain for task-scale durations (hundreds of decisions, hours of wall-clock) without burning quota, money, or an unrecoverable run. Invoke before planning, launching, or monitoring any paid run beyond ~100 turns — including any ask phrased as "overnight", "beat the game", "clear the stage/dungeon", or "keep it running".
---

# Long-horizon paid runs

North Star claim #1 is task-scale — "clear the game", "get the badge" — thousands of decisions, not
the ~90-turn gate runs the project grew up on. A gate (see **gate-methodology**) measures one
MECHANISM with a frozen scorer; a long-horizon run is an ENDURANCE AUDIT of task capability. Same
discipline (pre-registered, budgeted, banked), different failure modes: session caps, context
growth, unrecoverable state, sunk-cost relaunches. This skill exists so the first $80 mistake
(below) is not repeated.

## Status: exactly ONE long-horizon attempt exists (2026-07-04)

`runs/brain_kirby_longhaul/` (on-disk evidence; `runs/` is gitignored) — the first deliberate
long-horizon run, MONOLITHIC single-session pattern: `run.sh:32` `timeout 17000 claude
--max-turns 600 -p ...` (budget comment at `run.sh:5`: "~$40-50, timeout 17000s (~4.7h, under the
5h account cap)"). Outcome, verified from the artifacts: `run.exit` `EXIT=0`, final transcript
`result` line `subtype: success`, `num_turns` 316 (self-concluded well under the 600 cap),
`total_cost_usd` $42.98, 52.1 min wall-clock, 587 world steps, 72 `skills.jsonl` records. The
brain's closing report: exercised the define/run-skill loop thoroughly, made progress through
Kirby Stage 1, but did NOT clear the stage or beat a boss. No verdict report existed when this
skill was written — check `reports/` for a `*longhaul*` verdict before treating these numbers as
the final word, and read **diagnose-a-run** before drawing conclusions from the artifacts.

Everything in "The segmented-chain design" below is DESIGN — not yet exercised by any run.
Everything else here is verified fact.

## The cost curve (real runs — use this to budget)

| run | turns | wall | cost | note |
|---|---|---|---|---|
| brain_kirby_v3_1 | 74 | 11.7 min | $5.19 | gate-class run |
| brain_skill_ab_armA / armB | 58 / 63 | 28 / 31 min | $7.78 / $8.83 | ARC A/B (NB: "turns" here ≠ the 50/34 "decisions" in **cheapness-skill-compilation**'s table — turns count every LLM message, decisions only `act`/`run_skill` calls) |
| brain_arcagi3/run3 | 121 | 48 min | $20.82 | discovery run |
| brain_kirby_longhaul | 316 | 52 min | $42.98 | first long-horizon |
| brain_gate3d/run3_v_FAIL | 1000 | 68 min | $82.86 | most expensive run ever — and a FAIL |

Two lessons the table teaches: (1) cost/turn GROWS with run length (v3_1 ≈ $0.07/turn; longhaul ≈
$0.14/turn — the longhaul result line shows ~70M cache-read input tokens: the transcript's context
compounds); (2) the $82.86 run bought a FAIL — **a turn cap is not a kill criterion.** run3_v_FAIL
burned 1000 turns because nothing stopped it when progress stopped.

## Hard constraints (verified; these shape everything)

1. **Session windows are the ceiling, and there are TWO.** The 5-hour cap is account-level
   (`HANDOFF.md` "account A hit its 5-hr session cap; the limit is account-level"); transcripts
   carry `rate_limit_event` lines, and the five_hour events show `"overageStatus":"rejected",
   "overageDisabledReason":"out_of_credits"` (`runs/brain_red_starter/transcript.jsonl:1`) — hitting
   the cap mid-run is a HARD STOP, no overage. The SEVEN-DAY window is the real long-run budget:
   utilization was 0.87 with a `surpassedThreshold: 0.75` warning at the longhaul's end. **Check
   weekly utilization BEFORE launch** — read the first `rate_limit_event` line of any fresh
   transcript (a 1-turn probe run is enough). Above ~0.8, a multi-hour run risks dying mid-flight;
   surface to David instead of launching.
2. **There is no mid-session checkpoint.** The MCP server exposes NO savestate tool on the agent
   wire (`save_state` exists world-side at `world_mcp.py:449` but is not in any tool list);
   `--init-state` (`world_mcp.py:2618`) is loaded ONCE at boot (`core/perception_plugin.py:94`);
   every `save_state` caller in the tree is an offline script (`make_state.py`, `human_play.py`,
   `play_*.py`). A monolithic run that dies at turn 500 loses ALL game progress — only logs survive.
3. **Within-run state dies with the process.** Brain-defined skills and lessons are in-memory only
   (`world_mcp.py:866` "within-run self-improvement state (discarded at process end — the
   learning-boundary law)"; skills dict at `:882`). A session boundary kills the brain's memory AND
   the world-side skill library.
4. **Context grows unbounded.** The per-turn preamble re-injects accumulated `remember` notes; no
   compaction handling exists on the `claude -p` path (negative claim — no run script under `runs/`
   uses `--resume`/`--continue`; nothing in `reports/`, `HANDOFF.md`, or `LEARNINGS.md` documents
   long-run compaction behavior). Past a few hundred turns you are in unmeasured territory for
   decision quality, and paying cache-read for the whole history every turn.
5. **`core/cost_guard.py` is NOT wired into `claude -p` runs.** `spend_halt_reason` (`:22`) and
   `wake_stall_halt_reason` (`:42`) are pure predicates built for the retired litellm drivers. On
   the live path your only real guards are `--max-turns`, `timeout`, and the kill criteria you
   pre-register.

## Pre-registration deltas (on top of gate-methodology §1)

A long run is pre-registered like a gate (`reports/<date>-longrun-<task>-prereg.md`), PLUS:

- **Milestone ladder, oracle-observable.** Define milestones scored OFFLINE from `world/oracle.jsonl`
  watch fields (e.g. Red: party count, badge bitfield; Kirby: stage/HP addresses). Milestones are
  the scoreboard — never LLM self-report (the longhaul's "progress through Stage 1" is the brain's
  own claim; an oracle milestone would have settled it).
- **Budget rungs.** Total $ cap, `--max-turns` per session, max session count. Spending past the cap
  is a NEW pre-registration David authorizes — never "one more session" improvised (anti-sunk-cost;
  the $82.86 lesson).
- **Kill criteria.** K consecutive checks with zero new milestones AND zero new area/state coverage
  (define from oracle fields) → stop, bank the verdict as-is. Also: launch-blocked by weekly
  utilization; a perception break named twice in a row.
- **Relaunch carve-out.** Same as **paid-run-harness** law 6: infra death before ~10 decisions →
  relaunch once; anything later = the attempt is spent, score what exists.
- **Verdict + ledger.** Verdict doc per gate-methodology §7, and report the long-horizon
  observables: cost per milestone, decisions per milestone over time — whether the curve bends as
  skills accumulate is the **cheapness-skill-compilation** question at task scale.

## The segmented-chain design (DESIGN — pre-register a pilot before relying on it)

The monolithic pattern (longhaul) collides with constraints 1–4 as tasks grow past one session.
The designed alternative: a long run = a CHAIN of normal **paid-run-harness** launches.

- **Checkpoint at the boundary:** the launcher (not the agent — the wire stays clean per
  **safety-invariants** law 5) saves an emulator state after the session exits, under a NUMBERED
  name (`checkpoint_003.state`, never overwritten; savestates stay gitignored/local). Session k+1
  boots `--init-state` from it. NOTE: this needs a small world-side addition (a `--save-state-on-exit
  <path>` flag or wrapper script) — it does NOT exist yet; building it is a normal **dev-workflow**
  change.
- **Brain continuity — the ferry:** the brief REQUIRES a closing handoff report (the longhaul brief
  already ends with one); the harness appends it VERBATIM into session k+1's `CLAUDE.md` under
  `## Prior-session report (yours)`. Law analysis — UNRESOLVED: this treats the chain as ONE run, so
  carrying the brain's own within-run output forward would be learning-boundary-compliant. But
  everywhere else in the library "a run" = one `claude -p` invocation, and the law's owner
  (**cheapness-skill-compilation** §4) has not ratified the chain-as-one-run reading. The pilot's
  pre-registration MUST put this definitional question to David explicitly. If approved, the ferry
  must be MECHANICAL (verbatim append; a human curating it mid-chain contaminates the run). Skills
  do NOT ferry (constraint 3): the brain re-defines them, which is itself signal about
  re-distillation cost.
- **Blank-agent wipe still runs before EVERY session** (paid-run-harness law 2) — it kills cross-RUN
  client auto-memory; the ferry is the only sanctioned continuity channel inside a chain.
- **`SEGMENTS.md` ledger** in the run dir: one line per session — turns, cost, checkpoint file,
  milestone state, one-line digest of the brain's report. This is what David reads.
- **Alternative not chosen as default:** `claude --resume` to continue the same session across the
  cap. Unverified with MCP servers in this repo; hides the cost boundary. A pilot may test it as a
  comparison arm — David's call.
- **First execution:** a 2-session pilot on an instrumented world (Kirby or Red), trivial task, sole
  purpose to validate checkpoint→boot continuity, the ferry, and the ledger. Pre-registered,
  ~$10–15, David authorizes.

When a human asks for more than the constraints support ("guarantee stage 1–3 overnight"), the
correct response is to COUNTER-PROPOSE the pilot rung with the evidence above (the 316-turn/$43 run
didn't clear stage 1) — not to launch a bigger monolith and hope.

## Monitoring a live long run (all free, from Windows)

Same checks as **paid-run-harness** ("Health mid-run"), on a longer cadence, plus: watch
`rate_limit_event` lines in the growing transcript (`grep rate_limit transcript.jsonl | tail -1`)
for utilization creep; watch cost/turn drift (the `result` line only appears at the end — mid-run,
line count vs elapsed time is the proxy). Do NOT kill a run for looking slow; kill criteria are
what you pre-registered, nothing else.

## Sources

- `runs/brain_kirby_longhaul/{run.sh,run.exit,transcript.jsonl,world/}` — first long-horizon run,
  all facts verified on disk 2026-07-04.
- `runs/brain_gate3d/run3_v_FAIL/`, `runs/brain_arcagi3/run3/`, `runs/brain_kirby_v3_1/`,
  `runs/brain_skill_ab_arm{A,B}/` — cost-table rows (final transcript `result` lines).
- `runs/brain_red_starter/transcript.jsonl:1` — five_hour overage-rejected event shape.
- `world_mcp.py:449` (world-side save_state, not a tool), `:866`/`:882` (within-run state),
  `:2618` (`--init-state`); `core/perception_plugin.py:94` (single boot-time load).
- `core/cost_guard.py:22,:42` — unwired predicates from the litellm era.
- `E:/AI_Personas/10_pokemon_and_chess_and_office/ai-pokemon-red/HANDOFF.md` (account-level 5-hr cap).
- Cross-refs: **paid-run-harness** (launch laws — this skill adds the length dimension),
  **gate-methodology** (pre-registration spine), **diagnose-a-run** (post-mortems),
  **run-brief-authoring** (the closing-report device the ferry builds on),
  **cheapness-skill-compilation** (the curve a long run should bend).
