# Minimum North Star Gate 0 - design and spend boundary (2026-07-13)

Status: **$0 design only.** No paid run is authorized by this document. No
pre-registration, scorer, code, tool-schema, or brain change is included.

## Decision

Stop optimizing isolated capability gates long enough to define the smallest
integrated test of the actual North Star:

> Can one fixed, blank-start reasoning brain complete two natural-language
> human tasks in different world classes from the screen alone, with ordinary
> controls, at bounded wakes and cost?

Gate 0 pairs:

1. `pokemon_red`: from the fresh bedroom start, obtain a first Pokemon from
   Professor Oak and win the first rival battle.
2. `miniwob_click_checkboxes`: complete five fresh click-checkboxes episodes
   from their on-screen instructions.

This is a **minimum integration gate**, not the graduation exam. PASS would be
the first controlled joint lower bound on Capability + Constancy + Generality +
Cheap. It would not establish human-grade competence across the full ladder.

## Why these two worlds

### Pokemon Red

Red is the strongest existing end-to-end 2D embodiment probe. Historical runs
show that navigation, starter acquisition, and the rival win are individually
possible and can be cheap. But the current MCP It1 task has not honestly closed:

- `runs/brain_red_starter/CLAUDE.md` tells the brain that the balls are east of
  it and gives the exact `right` + `a` interaction recipe.
- `reports/2026-07-03-referential-grounding-design.md` correctly identifies
  that text as a human bridge over the missing static-object/named layer.
- The old integrated run17 used the superseded pre-MCP loop, not the current
  `claude -p` brain-as-MCP-client path.

Gate 0 therefore removes every location, button-sequence, and move-choice hint.
The brief may state the task and generic tool semantics only.

### MiniWoB click-checkboxes

MiniWoB is a genuinely different world class: browser pixels, mouse/keyboard,
and no avatar. The existing click-button result is already banked at 5/5,
reward 1.0 each, 33 turns, `$1.3557615`; rerunning it would buy little. The
next registered task, `miniwob_click_checkboxes`, is new evidence while reusing
the already validated screen-only browser harness.

### Why not MKDS now

MKDS is valuable later, but it is not an honest Gate 0 arm today:

- `runs/brain_mkds_armA_default/CLAUDE.md` says perception is broken, tells the
  brain to ignore it, and supplies the solution: hold accelerate; steering is
  not required.
- `reports/2026-07-13-mkds-ab-verdict.md` proves the conditional mechanism but
  does not log the verified progress byte and cannot claim checkpoint/lap
  progress.

An unbridged race task is therefore a predictable perception failure; the
bridged task is not human-grade racing. MKDS returns after a `$0` 3D-perception
and progress-oracle readiness gate.

### Why not Cave Noire now

Cave Noire is a useful entity-grounding instrument candidate, but it is another
GB slice. It buys less decisive cross-world evidence than a browser task and is
not on the Gate 0 critical path. Its source-status probe is paused, not erased.

## What is frozen across both paid arms

The future pre-registration must pin all of these before spend:

- exact `claude` executable version and model ID;
- one common, world-agnostic brain constitution/template;
- identical blank-agent memory wipe and no cross-run lessons;
- the task text as the only task-specific brain instruction;
- no solution hints, coordinates, routes, target locations, or action recipes;
- each world's existing human-control MCP surface, hashed and unchanged from
  pre-registration through verdict;
- all optional skill/claim tools OFF;
- no brain, frozen contract, or MCP tool-schema edits between arms;
- oracle/reward available only in offline logs, never on the agent wire;
- one attempt per world, with artifacts and verdict banked as-is.

The physical controls may differ (Game Boy buttons versus mouse clicks). That
is embodiment configuration, not a brain change. The semantic contract remains
screen state in, human-grade action out.

If the transcript init records different model IDs or the common brief differs
outside task/tool facts, the result is a constancy breach, not a capability
verdict.

## Proposed tasks and success predicates

### Arm R - Pokemon Red

Verbatim task sentence for the eventual brief:

> From the fresh bedroom start, obtain your first Pokemon from Professor Oak
> and win the first rival battle.

Forbidden brief content includes the lab route, ball location, facing rule,
button sequence, starter choice, nickname answer, battle move, or any statement
that distinguishes the correct object from visible alternatives.

Offline success must require both:

1. party count changes `0 -> 1`; and
2. the rival battle is entered and then exited without blackout, with free
   movement after the exit.

The current MCP registry logs party but not the battle-state signal used by the
older runs. The `$0` readiness work must verify and pin that offline signal
before a pre-registration. No paid run launches with manual-only or
model-narrated scoring.

### Arm W - MiniWoB click-checkboxes

Task instruction comes from the environment exactly as shown to a human. The
common brief says only to complete five fresh episodes using screen pixels and
ordinary mouse/keyboard tools.

Offline success requires reward `1.0` on **5/5** episodes. DOM elements and
reward remain scorer-only. Any DOM/reward/status leak onto the agent wire
invalidates the arm.

## `$0` readiness phase

These runs are local emulator/browser/human/scripted probes. They use no paid
LLM brain and prove no reasoning capability.

### R0 - Red source status

- Verify the fresh bedroom state has party `0`.
- Replace the bridged brief with the common template plus the task sentence.
- Replay/inspect the lab frames and record exactly what current `observe` and
  `read_region` expose without the east/right+`a` hint.
- Verify the party and battle-exit offline oracles across a scripted fixture.
- Confirm the task can be scored mechanically from append-only artifacts.
- Record one human baseline from the same state: success, active-control time,
  wall-clock time, button presses, and emulator frames/steps.

### W0 - MiniWoB source status

- Launch `miniwob_click_checkboxes` locally with no LLM.
- Verify five fresh episodes render and are reachable through pixels/clicks.
- Verify reward and DOM remain oracle-only.
- Record one human baseline: success, wall-clock, clicks, region inspections,
  and corrections.
- Confirm an incorrect/empty click is distinguishable offline and the episode
  reset does not leak the target.

### C0 - Constancy and scoring dry run

- Save exact tool-list/schema hashes for both worlds.
- Pin the common brief template and show a text diff containing only task/tool
  facts.
- Pin executable/model/version/memory-wipe receipts.
- Dry-score synthetic PASS, task FAIL, infra death, and constancy-breach
  fixtures before any paid attempt.
- Estimate decision caps from the human baselines and scripted physics rather
  than copying old arbitrary turn caps.

Readiness verdicts are `GO`, `NO_GO`, or `INSUFFICIENT_SOURCE`. Both arms must
be `GO`; otherwise there is no paid Gate 0.

## What `$0` versus paid evidence earns

`$0` work earns **prediction**:

- kills contaminated or unsolvable task definitions;
- verifies that success is scoreable and the oracle does not leak;
- finds infra failures before quota is exposed;
- establishes human and action-budget baselines;
- predicts whether a paid failure would be interpretable.

It cannot show that the fixed LLM brain understands and completes either task.

Paid work earns **proof**:

- capability from a blank brain on the natural-language tasks;
- constancy from matched brain receipts across the two arms;
- cross-world generality from GB embodiment plus browser computer use;
- cost/task and wakes/task under the same accounting.

The history makes the order non-negotiable. The MiniWoB click-button run bought
clean evidence for `$1.3557615` after live seam validation. Entity v2 consumed
about `$80` across 11 runs while its instruments repeatedly starved or tainted
the verdict. Paid runs earn more only after `$0` readiness makes the result
decisive.

## Future paid Gate 0 shape - not authorized here

Only after R0 + W0 + C0 all return `GO`:

1. Write a fresh pre-registration with verbatim briefs, exact scorer, human
   baselines, decision/wall-clock bars, budget, infra carve-out, and escalation
   shelf.
2. Post adversarial review and fix all major design findings before launch.
3. Run one account-B attempt per world, blank memory before each.
4. Target a combined ceiling of **no more than `$10`**. The pre-registration
   must tighten that using the `$0` baselines; `$10` is a ceiling, not a target.
5. If Arm R alone reaches the combined ceiling, do not launch Arm W.
6. Bank PASS/FAIL/INSUFFICIENT_DATA/CONSTANCY_BREACH as printed. Never rescue a
   marginal result with an informal rerun.

The paid verdict must report, per task: success, human baseline, active world
time, wall-clock, primitive actions, LLM wakes, cost, tool-schema hash, model
ID, and brain/config hash.

## Interpretation and escalation shelf

- **Red fails before locating/interacting with a ball:** named/static referential
  grounding is the critical path. Fix only perception/world-side primitives;
  never add the answer to the brain brief.
- **Red reaches a faithful battle state but reasons wrongly:** classify from the
  transcript. A genuinely general reasoning defect belongs in `ai-aria`, never
  as a Pokemon-specific brain patch.
- **MiniWoB cannot identify/check the named targets:** the static-UI named layer
  is the critical path. Prefer one shared referential primitive over a
  MiniWoB-only widget ontology.
- **Both tasks succeed but cost/wakes miss the bar:** inspect repeated decisions.
  Compile only demonstrated within-run routines into System 1; no automatic or
  cross-run promotion, and no hand-written controller per world.
- **One task passes:** bank the partial evidence. Fix the failed seam, then wait
  for a new pre-registration; do not rerun the passing arm.
- **Both pass:** add one held-out task/world at the next phase exit. Do not turn
  Gate 0 into the full ten-task graduation exam midstream.

## Decision

Proceed now with R0 + W0 + C0 only. Do not run Cave Noire, MKDS, or a paid brain
under this design. The next tracked artifact is a `$0` Gate 0 readiness report;
only an all-`GO` result can justify a paid pre-registration.

## Sources

- `HANDOFF.md` (canonical North Star and current paid ledger)
- `reports/2026-07-05-northstar-capability-map.md`
- `reports/2026-07-03-referential-grounding-design.md`
- `reports/2026-07-01-it1-close-status.md`
- `reports/2026-07-13-mkds-ab-verdict.md`
- `reports/_archive/2026-06-20-live-run-13-battle-auto-advance.md`
- `reports/_archive/2026-06-20-live-run-17-affordance-layer-probe-saliency-got-the-starter.md`
- `runs/brain_red_starter/CLAUDE.md`
- `runs/brain_miniwob/{CLAUDE.md,run.sh,transcript.jsonl,world/oracle.jsonl}`
- `runs/brain_mkds_armA_default/{CLAUDE.md,run.sh}`
- `world_mcp.py`
