# Minimum North Star Gate 0 - design and spend boundary (2026-07-13)

Status: **readiness implementation on feature branch
`codex/gate0-codex-readiness-2026-07-13`.** This work remains `$0`: no Codex
model was invoked and the held-out MiniWoB preflight has not run. No paid run
is authorized by this document, and no brain or frozen tool-schema change is
included.

PR #110's initial adversarial review found three launch blockers that this
design now makes explicit: MiniWoB seed separation/logging, exact Capability
and Cheap bars, and mechanical exclusion of non-world client tools. The current
branch is not yet merged and its first review requested changes. The installed
Codex CLI is not executable from this task, so the harness remains **not launch-ready**. These are R0/W0/C0
prerequisites, not reasons to spend and diagnose later.

PR #111's review added four fail-closed requirements: explicit runtime config
that does not depend on project trust, independently frozen expected pins plus
recomputed artifacts, immutable world-image/code receipts, and a mechanically
enforceable live spend breaker. The review fix deliberately removes paid model
execution from the current launcher. It can perform only a `$0` handshake,
emits `paid_execution_enabled=false`, returns `NO_GO_INSUFFICIENT_WAKES`, and
exits nonzero. A paid launcher must be designed and reviewed later; it does not
exist in this PR.

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

- the literal resolved Codex CLI executable path, exact `codex --version`,
  literal model ID (no `latest` alias), and one `brain_config_sha256` over the
  exact common non-world config block;
- ChatGPT-account authentication only, with no API key present or accepted as
  fallback;
- one common, world-agnostic brain constitution/template inside that config;
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

- Current receipt: `core/miniwob_world.py` starts `_seed_counter` at `0` for
  every new process, while `world_mcp.py:MiniWobSession._log_oracle()` logs no
  seed or episode index. Current MiniWoB is `NO_GO` until seed plumbing lands
  in a separately reviewed readiness PR.
- Pin DEV seeds `0..4` for `$0`/human work and paid-held-out seeds `1000..1004`.
  Never expose screenshots, utterances, labels, DOM, target counts, or
  coordinates from `1000..1004` before the paid arm. The sole exception is the
  sealed reachability check below.
- After the seed manifest and preflight code are frozen, run one sealed offline
  reachability check on exact paid seeds `1000..1004`. It may inspect DOM/task
  fields oracle-side only to answer whether every required checkbox and submit
  control has a valid click point inside the real `160x177` viewport. Its only
  output is one aggregate `all_reachable=true|false` plus the seed-manifest and
  preflight-code hashes;
  no task content, element count, label, bbox, coordinate, image, or solution
  may be written or shown. Any `false` makes W0 `NO_GO` before spend. Do not
  replace the failed seed block under this design; a viewport fix and new gate
  version are required.
- Add a launch-time pinned-seed source, log `episode` + `seed` in every oracle
  row, and enforce one attempt per seed. An early `reset_episode` must abandon
  the current seed and advance; it must never re-roll the same instance.
- Launch `miniwob_click_checkboxes` locally with no LLM on DEV seeds only.
- Verify five fresh episodes render and are reachable through pixels/clicks.
- Verify reward and DOM remain oracle-only.
- Record one human baseline: success, wall-clock, clicks, region inspections,
  and corrections on DEV seeds. This predicts readiness only. The formal
  human-relative score uses the same paid-held-out seeds **after** the agent's
  paid attempt, so no held-out instance is exposed before the agent runs.
- Confirm an incorrect/empty click is distinguishable offline and the episode
  reset does not leak the target.

### C0 - Constancy and scoring dry run

- Save exact tool-list/schema hashes for both worlds.
- Current receipt: `runs/brain_miniwob/transcript.jsonl` init exposes built-in
  `Read`/`Bash`/web tools plus external connectors, and the run called
  `ToolSearch`. Current launch isolation is `NO_GO`.
- Launch from an isolated client configuration with only the target world MCP
  connected. Pin the complete init inventory (`tools`, `mcp_servers`, skills,
  plugins, permission mode), not just the MCP schema. The scorer must return
  `NO_LEAK` on **any** assistant tool call outside that arm's exact world-MCP
  allowlist, including `ToolSearch`, shell/file/web tools, or connectors.
- Prove in a free handshake that every required world tool is directly
  callable without `ToolSearch`; otherwise stop and fix isolation before paid
  work.
- Do not rely on a fresh repository trusting its project config. Pass every
  critical brain/MCP restriction as an explicit CLI override, run Codex's own
  `mcp list --json` from an empty isolated `CODEX_HOME`, and require exactly the
  one frozen server.
- Resolve each mutable Docker tag to an immutable `sha256:` image ID. Hash
  `world_mcp.py` and `core/miniwob_world.py` on both host and image, require
  equality, run the exact image ID, and record the live full `tools/list`
  schemas. Any stale image is `NO_GO`; rebuild after merge, never wave through
  a tag.
- Freeze an expected-pins JSON independently of the observed receipt. The
  checker must compare every security pin exactly, recompute every referenced
  artifact/executable hash, and compare the common-brain fields across arms.
- Pin the common brief template and show a text diff containing only task/tool
  facts.
- Pin executable/model/version/memory-wipe receipts.
- David installed Codex with OpenAI's official PowerShell installer on
  2026-07-13. In this task, command resolution still returns the WindowsApps
  alias and execution is access-denied, so the auth receipt, exact executable
  version, model availability, and free handshake all remain pending. Installation
  alone is not a readiness receipt.
- Official `codex exec --json` documentation exposes aggregate token usage on
  `turn.completed`; it does not document per-model-call wake boundaries. Do not
  substitute tool calls, JSONL events, or turns for wakes. C0 remains
  `NO_GO_INSUFFICIENT_WAKES` until a free handshake or a documented observable
  grounds exact wake accounting. The wake bars below do not loosen.
- Mechanical containment is stronger than a prose promise: the current script
  contains no `codex exec` path and always records `paid_execution_enabled=false`.
  C0 cannot become `GO` until a separate paid launcher has observable wake
  accounting and a live breaker that halts at 250 normalized credits without
  relying on end-of-run arithmetic.
- Dry-score synthetic PASS, task FAIL, infra death, and constancy-breach
  fixtures before any paid attempt.
- Confirm the human baselines and scripted physics fit the bars pinned below;
  the future pre-registration may tighten them but never loosen them.

Readiness verdicts are `GO`, `NO_GO`, or `INSUFFICIENT_SOURCE`. Both arms must
be `GO`; otherwise there is no paid Gate 0.

## Exact Gate 0 bars

Gate 0 is a joint PASS only if every bar below clears. These are design bars;
the future pre-registration may tighten, not loosen, them after R0/W0/C0.

### Capability bar

For **each** world:

1. the task-specific success predicate above passes; and
2. agent wall-clock time is `<= 2.0x` the one-human baseline; and
3. agent primitive control actions are `<= 2.0x` the human baseline.

Wall-clock includes model/provider latency because that latency is part of the
actual agent. R0/W0 must return `NO_GO` without spend if a free latency/physics
ceiling already proves the `2.0x` bar impossible. Gate 0 is still only a
two-task lower bound; the larger graduation battery remains separate.

Red uses the same fixed start for agent and human. For MiniWoB, the agent sees
held-out seeds `1000..1004` first; only after its artifacts are banked does the
human replay those exact seeds for the formal time/action denominator. DEV-seed
human runs are readiness estimates, never the final denominator.

### Cheap bar

Both task success and the wake, dollar, and normalized-credit caps are required:

| Arm | LLM wakes | Cost |
|---|---:|---:|
| Red starter + rival | `<= 90` | `<= $5.00` |
| MiniWoB 5 episodes | `<= 50` | `<= $2.00` |
| **Combined** | `<= 140` | `<= $7.00` |

For ChatGPT-subscription Codex, the matching normalized-credit caps are:

| Arm | Normalized Codex credits |
|---|---:|
| Red starter + rival | `<= 125` |
| MiniWoB 5 episodes | `<= 50` |
| **Combined PASS** | `<= 175` |
| **Hard breaker** | `<= 250` |

At pre-registration, pin the official Codex token-credit rate for the exact
model and confirm the official `25 credits = $1.00` equivalence. Compute credits
from the recorded input, cached-input, and output tokens using that pinned rate;
the dollar figures remain the PASS bars and are not replaced by “included”.
Subscription-included usage may have `$0` incremental cash cost, but it still
consumes quota and must record the same normalized credits. Auto-top-up stays
OFF and no API key may be present, so the gate cannot silently spill into a
different paid channel.

The looser `$10` combined number below is a **hard spend breaker**, not a PASS
bar. A successful run costing `$7.01..$10.00` is `FAIL_CHEAP`.

The caps are grounded in existing receipts, with slack for the harder tasks:
the old Red cold integrated run used 69 wakes and about `$0.6-0.8`; the current
Red MCP brief caps 90 decisions; MiniWoB click-button used 33 turns and
`$1.3557615`. R0/W0 may kill these caps as unreachable; they may not raise them.

### Constancy, generality, and no-leak bars

- exact model ID, executable version, `brain_config_sha256`, memory-wipe receipt,
  and init-inventory policy match across arms; the whole `config_sha256` is
  arm-specific because it includes the world MCP command/tools;
- no brain/contract/tool-schema change between arms;
- only task text, perceiver/world configuration, and human control vocabulary
  differ;
- both world tasks pass; a one-world success is not Generality PASS; and
- every assistant tool call belongs to the pinned world-MCP allowlist.

Verdicts are `PASS`, `FAIL_CAPABILITY`, `FAIL_CHEAP`,
`CONSTANCY_BREACH`, `NO_LEAK`, or `INSUFFICIENT_DATA`. Constancy/no-leak checks
run before task scoring.

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

Only after R0 + W0 + C0 all return `GO` **and** the missing paid launcher with
observable wake accounting/live credit containment has passed its own review:

1. Write a fresh pre-registration with verbatim briefs, exact scorer, human
   baselines, the bars above (tightening allowed; loosening forbidden), budget,
   infra carve-out, and escalation shelf.
2. Post adversarial review and fix all major design findings before launch.
3. Run one ChatGPT-subscription Codex attempt per world, blank memory before
   each, using the same exact executable version, model, and common brain-config
   block. The task and whole arm config retain their separate hashes. This
   replaces the old account-B Claude plan completely.
4. Keep auto-top-up OFF and reject API-key authentication.
5. Hard-stop at a combined ceiling of **no more than `$10` / 250 normalized
   credits**. Cheap PASS still requires `<= $7` / 175 credits; the hard ceiling
   is containment, not a success target.
6. If Arm R alone reaches the combined ceiling, do not launch Arm W.
7. Bank PASS/FAIL/INSUFFICIENT_DATA/CONSTANCY_BREACH as printed. Never rescue a
   marginal result with an informal rerun.

The paid verdict must report, per task: success, human baseline, active world
time, wall-clock, primitive actions, LLM wakes, aggregate token usage,
normalized Codex credits, incremental cash cost, tool-schema hash, exact Codex
resolved path, executable hash, version/model ID, and brain/config hash.

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
- [OpenAI Codex CLI reference](https://developers.openai.com/codex/cli/reference)
- [OpenAI Codex non-interactive mode](https://learn.chatgpt.com/codex/non-interactive-mode)
- [OpenAI Codex configuration reference](https://developers.openai.com/codex/config-reference)
- [OpenAI Codex MCP guide](https://developers.openai.com/codex/mcp)
- [OpenAI Codex rate card](https://help.openai.com/en/articles/20001106)
- [OpenAI: using credits for flexible ChatGPT usage](https://help.openai.com/en/articles/12642688-using-credits-for-flexible-usage-in-chatgpt-free-go-plus-pro-sora)
- [OpenAI Codex credit equivalence receipt](https://help.openai.com/en/articles/20001147-codex-credits-for-students-terms-of-service)
