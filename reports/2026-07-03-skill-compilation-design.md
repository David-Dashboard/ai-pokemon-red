# 2026-07-03 — System-2→System-1 skill compilation: rung 1 design + pre-registered gate

Design + gate plan only — **no primitives are built by this pass**. Scope discipline: ADR-002 §11
("build ONLY the primitives the gate needs"), the learning-boundary law (`reports/INSIGHTS.md` §7 —
every run starts blank, across-run learning is harness-code-only), and the house pre-registration style
of `reports/2026-07-03-entity-gate-v2-plan.md` / `reports/2026-07-04-vizdoom-3d-floor-design.md` /
`reports/2026-07-05-p1-clutter-redesign.md`. Evidence base: `HANDOFF.md`'s 2026-07-05 day-close block
(ARC wa30 wall, GATE-3D-A3-PC result), the entity-gate v2 verdict (`reports/2026-07-03-entity-gate-v2-plan.md`,
run 11), and `reports/2026-07-05-glyph-read-design.md`'s validated within-run cache mechanism.

## 1. Problem statement

Three independent frontiers, scored on three different worlds by three different teams of runs, point
at the same missing piece.

**(a) ARC-AGI-3 wa30 — the L2 wall is depth, not perception.** Three brief framings (discovery $6.69,
memory-carrying $8.89, completion-framed $20.82) all end at **levels_completed 1/9**. Ontology
discovery succeeds *every* run — the brain reliably reverse-engineers the sokoban-style tile-delivery
mechanics, its own avatar, the grab/release action, the timer — but level 2 never falls. Spending 3x
more money (the completion-framed run) bought zero additional levels. HANDOFF's own diagnosis: "the
boundary is multi-step spatial planning depth, not perception or framing."

**(b) Entity gate v2 FAIL — the brain lacked an exposure-control skill.** Run 11 (Kirby port, the clean
verdict run, $3.06): arm (a) threat-grounding scored `q_k=0.800` vs the required `b_k+MARGIN=1.112`
(`b_k=0.812`, `MARGIN=0.30` — GROUNDED needs `q_k >= b_k+0.30`; exact numbers and scorer per
`reports/2026-07-03-entity-gate-v2-plan.md`). The finding, in that doc's own language: "a short
session cannot decorrelate 'near' from 'always around'... backward attribution... requires the brain
to actively DESIGN its exposure contrast (be measurably away from the suspect during ordinary time)."
v1 failed on enemy-initiative timing; v2 fails on exposure design. Both point at the same gap: the
brain never *executes a deliberate approach/retreat pattern* — it just plays, and "near" and "always
around" collapse together. That pattern (approach, observe, retreat, repeat) is exactly the shape of a
**routine sub-sequence**, not a one-off decision.

**(c) GATE-3D arm (a-1) FAIL — fire discipline passed, hunt efficiency didn't.** Ammo efficiency (arm
a-2) PASSED (KPS 0.2402 vs bar 0.2375). Kill margin (arm a-1) FAILED (K=4.074 vs bar 5.610 — at spinner
level). The brain wasn't wasting ammo; it just wasn't *finding and centering targets fast enough* per
decision. Each `turn_left`/`turn_right`/`attack` call is one LLM decision; a "scan until a mover
appears, then center it" behavior is exactly the kind of thing a human FPS player does without
thinking about each individual key-press.

**The common shape.** In all three, **each System-2 (LLM) decision is expensive and buys exactly one
primitive action** (one press, one turn, one ACTION1-7). Humans do not replan a multi-step routine from
scratch every time it recurs — they *compile* it into a fast, cheap, narrow habit (a System-1 macro:
walk to the door, dodge-and-weave, approach-check-retreat) and only re-engage deliberate reasoning when
the routine breaks. `reports/INSIGHTS.md` §6 named this pattern over a month ago ("Wake at decisions is
currently static... it should become adaptive and learned") but nothing has been *built* against it —
this doc is the first design pass. The shared lever: **multiplying effective planning depth per paid
decision** is simultaneously the cost claim's biggest remaining lever and, per (a)-(c), a capability
wall in its own right.

## 2. Design space — where can compiled skills live without violating the learning boundary?

Three candidate lifetimes for a "skill," surveyed honestly before picking one.

### (i) Brief-carried macros: brain writes skill definitions THIS RUN, they die at run end

A `define_skill(name, steps, stop_when)` seam tool: the brain composes a named macro out of primitives
it already has, calls `run_skill(name, args)` to execute it, and the definition is discarded when the
process ends — exactly the `remember()` lesson buffer's lifetime (`world_mcp.py::_REMEMBER_TOOL`,
"forgotten when the session ends (that's intentional)"), generalized from *English sentences* to
*executable action sequences*. This is **within-run compilation**: the mechanism-shape the glyph cache
already validated (`reports/2026-07-05-glyph-read-design.md` — Gate 2 PASS, 96.9% free-serve after
warmup, 0 mismatches) — that design generalized `TileFunctionMap`'s dHash-keyed, brain-confirmed,
majority-vote-invalidated cache from *tiles* to *glyphs*; this doc generalizes the same shape one step
further, from *glyphs* (a lookup table) to *action sequences* (a callable routine). Same law
(learning-boundary: within-run, harness-owned, discarded at run end), same proven cache-and-serve
pattern, new payload type.

**Cost:** zero new cross-run state. **Risk:** the compiled skill can only be as good as what the brain
already figured out this run — no cross-run compounding, so every run re-derives its own macros from
scratch (the entity-gate brain must re-invent "approach-observe-retreat" every session). **Verdict:
lowest risk, smallest build, and the only rung with a directly-validated mechanism precedent. Recommend
this as rung 1.**

### (ii) World-side skill library: hand-audited, versioned macros exposed as seam tools

A curated set of parameterized action sequences (e.g. `scan_and_center()`, `approach_observe_retreat()`)
written by a human, versioned like any other harness code, exposed as seam tools the brain can call
across ANY run. This is the *persona/identity law* shape (`hand-curated versioned data, never
LLM-auto-mutated`) applied to behavior instead of memory.

**Cost:** durable, compounds across runs — closer to what an actual capability lift looks like.
**Risk:** it is still cross-run knowledge injection, just written by a person instead of an LLM — legal
under the learning-boundary law (harness/code updates are the *only* permitted across-run channel) but
it means the SKILL, not the brain, is what generalizes; a new game needs a new hand-written macro before
the brain benefits at all, same "per-world adapter" cost as perception (`reports/INSIGHTS.md` §1-2).
**Verdict: the right rung 2, but only once rung 1 has demonstrated WHICH macros are worth curating** —
building this first risks hand-designing macros nobody needed (the over-build tripwire ADR-002 §11
exists to catch).

### (iii) Harness-side compilation: transcripts mined offline, promoted through review + a gate

Offline analysis of run transcripts for repeated decision→action patterns, with a human reviewing
candidates and promoting the ones that generalize into (ii)'s library — never automatic, always a PR +
gate, matching the review-before-merge law that already governs everything else in this repo (plan →
branch → Sonnet → PR → adversarial review → David merges).

**Cost:** the only path that could ever discover a macro the humans didn't think to hand-write.
**Risk:** requires (i) to have run several times first (there is nothing to mine without transcripts),
and requires a promotion gate to avoid smuggling brain-authored behavior into harness code
unaudited — precisely the concern the persona/identity law exists to prevent. **Verdict: real, but
strictly downstream of (i) — it is the promotion path, not a starting point.**

**Decision of record: build (i) first.** It needs no new cross-run channel, its mechanism shape
(within-run cache, keyed lookup, brain-confirmed, discarded at run end) is already validated at 96.9%
free-serve by the glyph cache, and it directly answers all three frontiers in §1 without touching the
learning-boundary law. (ii) and (iii) are the promotion path, revisited only after rung 1 produces
transcripts worth mining.

## 3. Mechanism sketch — rung 1 (within-run skill compilation)

**Seam tool pair**, world-side (lives in `world_mcp.py`, next to `remember`/`observe`, not in `core/`
brain code — no brain edits, ever):

- **`define_skill(name: str, steps: list[str], stop_when: str)`** — `steps` is a list of EXISTING
  primitive action names this world already exposes (e.g. `["press_button:up", "press_button:up",
  "press_button:a"]` for a GB world, or `["turn_left", "turn_left", "attack"]` for GATE-3D), each
  optionally with a repeat count (reuses the `repeat: 1..10` param GATE-3D's action tools already have,
  `world_mcp.py::_doom_action_tool`). `stop_when` is one of a small closed enum of CHEAP, WORLD-SIDE
  predicates evaluable from data already on the wire:
  - `"scrolled"` — the screen/frame changed by more than a noise floor since the skill started (reuses
    the existing translation/frame-diff machinery, `reports/INSIGHTS.md` §8).
  - `"region_changed(x0,y0,x1,y1)"` — a `whats_changed`-shaped region comparison came back "changed"
    (reuses `_WHATS_CHANGED_TOOL`'s exact mechanism, just as a stop condition instead of a query).
  - `"steps_elapsed(N)"` — N world steps have passed (a pure counter).
  - `"blocked"` — the last primitive step's outcome was BLOCKED (reuses the existing move-outcome
    signal already surfaced by `observe()`).

  **Never** an oracle/RAM/score field, and never anything not already exposed by an existing tool —
  `define_skill` composes what's already on the wire; it does not open a new information channel.
  Definitions are logged verbatim to the transcript at creation time (auditable — a human reviewing the
  run sees exactly what macro was compiled and why).

- **`run_skill(name: str, args: dict)`** — executes the named skill's steps against the live world,
  advancing world state exactly as if each primitive had been called individually, checking
  `stop_when` after each step and returning early (with the reason) if it fires. Returns ONE tool
  result (one `observe()`-shaped view of the state after the skill ran, plus a log of which steps
  actually executed and why it stopped) — **one LLM decision, N world steps.**

**Why this is a strict analogy to the glyph cache, not a new mechanism:** the glyph design's
`define`-then-`replay` shape (brain confirms a glyph reading once, cache serves it free thereafter,
majority-vote invalidates on contradiction) maps directly: `define_skill` is the confirm step,
`run_skill` is the free-serve step. The one new discipline this needs that the glyph cache didn't: a
skill can go WRONG mid-execution in a way a cached lookup can't (the world state diverges from what the
brain assumed when it wrote `steps`), which is exactly what `stop_when` exists to catch cheaply,
world-side, without waking the LLM to check.

**Token cost estimate.** A primitive-by-primitive equivalent of a 6-step macro (e.g. GATE-3D's
scan-and-center: turn, turn, observe, turn, attack, observe) costs **6 LLM decisions** — 6 round-trips,
each carrying the full tool-result payload (observation text, lesson buffer, delegation tally) at
roughly 300-600 tokens per result plus the model's reasoning tokens per call. A `run_skill` call
covering the same 6 steps costs **1 LLM decision** — one call, one result. Conservatively, at ~400
input + ~150 output tokens per wake (result payload + brief reasoning), 6 wakes ≈ 3,300 tokens vs 1 wake
≈ 550 tokens — **roughly a 5-6x reduction in tokens-per-macro**, before counting the reasoning-token
overhead LLMs spend re-orienting after every single-step result (which the existing `GOTO`/`explore`
autopilots already demonstrate empirically: `reports/INSIGHTS.md` §5's "one decision walks many tiles
for free" is the same economics one level up).

## 4. Pre-registered gate (gate-first, cheapest decisive test)

**Riskiest claim:** giving the brain `define_skill`/`run_skill` measurably increases task progress per
paid decision, without degrading task correctness, and without being gameable by a degenerate
"skill" that's just primitive-spam wearing a skill-shaped wrapper.

### 4.0 Free instrument first

Before any paid A/B: a **scripted/replay comparison**, free, Docker/CPU only. Take an existing scored
transcript with a known-repeated action pattern (e.g. a GATE-3D episode's turn-then-attack sequences,
or a Cave Noire/Kirby entity-gate transcript's approach-observe-retreat attempts) and replay it through
`run_skill` mechanically to confirm: (a) the stop-conditions fire at the same points a human reading the
transcript would call the macro "done"; (b) the skill log is auditable (a reviewer can read
`define_skill`'s logged definition and `run_skill`'s per-call step log and reconstruct exactly what
happened, same bar as the entity-gate NEAR-corroboration audit). This is a **build-correctness check**,
not the gate itself — it must pass before any paid arm is scheduled, same discipline as GATE-3D-A3-PC
gating PR-H.

### 4.1 The paid A/B (one arm each, same brief, same world, same `--max-turns`)

**Pinned metric:** task progress per paid decision.
- **ARC-AGI-3 instrument:** levels_completed (or, if wa30 stays stuck at 1/9 as expected, a finer
  sub-goal count — e.g. verified HYP/GOAL milestones per the discovery protocol's own logging) per 100
  turns, where a "turn" = one LLM decision (i.e. one `act`/`run_skill` call, NOT one primitive
  world-step — this is the whole point: `run_skill` must not get free extra turns by definition).
- **Kirby entity-gate instrument (alternative/companion):** banked gate events (accepted NEAR coverage
  of drop steps, per `reports/2026-07-03-entity-gate-v2-plan.md`'s `q_k` machinery) per decision.

**Design:** same brief, same world, same pinned `--max-turns` (a hard mechanical budget, per the
GATE-3D protocol-breach lesson: "briefs are not budget enforcement" — `--max-turns` is the actual cap,
not prose asking the brain to be economical). Arm A = brain has ONLY the existing primitive tools. Arm
B = brain additionally has `define_skill`/`run_skill`. Everything else identical (same seeds/game,
same `--max-turns`, same model).

**Recommended first instrument: ARC-AGI-3 wa30**, because (1) it is the cheapest per-run instrument
already in the fleet (~$6-9 per run, vs GATE-3D's $80+ verdict runs), (2) HANDOFF already states "do
not buy more wa30 runs without a new mechanism" — this IS the new mechanism, and (3) it has an external,
un-tunable yardstick (the ARC Prize scorecard) that nobody can accuse of being fitted post hoc.

**Pinned numbers (exact, before any run):**
- **Metric:** `sub_goal_events / (decisions / 100)` — sub_goal_events = levels_completed, OR, if both
  arms stay at 1/9 (plausible given the wall is depth, not breadth), a secondary pinned proxy:
  verified HYP-confirmed ontology milestones logged per the discovery protocol (count of distinct
  `HYP:`-then-confirmed lines) — pinned NOW as the fallback so it can't be picked after seeing which
  arm looks better.
- **PASS bar for skill tools helping:** Arm B's metric `>= 1.3x` Arm A's metric (a 30% lift — chosen to
  be clearly outside run-to-run noise given the existing 3-run spread already shows some variance in
  cost ($6.69/$8.89/$20.82) at flat 1/9 outcome; 30% is a real, visible effect, not a coin-flip margin).
- **Degenerate-strategy guard:** a "skill" that is just `run_skill` wrapping N=1 primitive step (i.e.
  spamming trivial single-action "macros" to make raw decision-count look lower) must NOT count as
  depth. Mechanical guard: only `run_skill` calls whose logged step list has **length >= 3** count
  toward the "used a skill" tally; the pinned metric is computed on ALL decisions regardless (so gaming
  this can't hide cost, only fail to claim credit for it) — and the post-run audit (mandatory, same
  discipline as the entity-gate v2 sparse-burst-NEAR audit) must confirm Arm B's skills are genuinely
  multi-step routines, not renamed single presses.
- **Cost cap:** `<= $15` for the paid arm (both runs combined, ARC being the cheap instrument this is
  built on) — well under GATE-3D's blown budget, in line with ARC's own $6.69-$20.82 range.
- **`--max-turns`:** identical fixed cap for both arms (same value used in the most recent wa30 runs,
  100), enforced mechanically at launch, not left to brief wording.
- **Amendment rule:** stricter-only, per house discipline — the 1.3x bar, the length>=3 guard, and the
  cost cap may be tightened by a future pass but never loosened to rescue a marginal result.

**INSUFFICIENT_DATA condition:** if either arm's run terminates before `--max-turns` for a reason
unrelated to the skill mechanism (MCP/seam failure, credit exhaustion, launcher bug) the run is
discarded and re-launched — not scored as a loss for whichever arm hit the infrastructure failure.

## 5. What this buys each frontier

**ARC L2 (navigation/manipulation macros).** wa30's block-quantized sokoban mechanics reward a
`push_block_to(direction, N)`-shaped macro — walk N tiles, ACTION5 to grab/release, stop on
`region_changed` (the container's cell visibly changed) or `blocked`. Today the brain re-plans every
single ACTION1-4 press; a compiled macro turns "push this block three tiles" from 3+ decisions into 1,
directly multiplying how many multi-step sub-goals fit inside the same `--max-turns` budget — precisely
the depth wall HANDOFF diagnosed.

**Entity v3 (exposure-control macro).** The v2 FAIL's own language calls for "an EXPERIMENT-DESIGN
skill (or a System-1 exposure-control primitive)" — this rung supplies exactly that shape: an
`approach_observe_retreat(entity_region, steps_each)` macro (approach N steps toward a hypothesized
entity's region, `read_region`/`whats_changed`-check it, retreat N steps, stop on `steps_elapsed` or
`blocked`) lets the brain DESIGN its own exposure contrast as a single compiled routine instead of
hoping ordinary play happens to decorrelate "near" from "always around." This is the direct fix v2's
own postmortem asked for.

**GATE-3D (scan-and-center hunt macro).** A `scan_and_center(max_turns)` macro — turn one direction
until a mover azimuth appears in `observe()`'s mover list (or `steps_elapsed` caps out), then turn
toward azimuth-0 — converts arm (a-1)'s hunt-efficiency problem (K=4.07 vs bar 5.61) from "many
individual turn decisions per kill" into "one decision, many turns, then one attack decision," which is
exactly the K-per-decision lever the gate measures.

## 6. Explicit non-goals (rung 1)

- **No cross-run persistence.** Every skill defined this run is gone at run end, same as `remember()`
  lessons and the glyph cache. A macro that seems to generalize is a candidate for hand-curation into
  (ii), never auto-carried forward.
- **No auto-promotion.** Nothing in rung 1 writes to `core/` or `games/`. Promotion to a world-side
  library (design-space (ii)) is a separate, human-reviewed design + PR, not a mechanical consequence of
  a good gate result.
- **No learned policies.** `stop_when` predicates are a fixed closed enum, evaluated exactly, never
  fit/trained/tuned from data. The brain composes existing predicates; it does not invent new scoring
  functions or weights.
- **No reward-driven anything.** No skill is scored, reinforced, or selected by an oracle/score signal
  at runtime — the no-leak law stands unchanged. The gate in §4 evaluates the MECHANISM after the fact,
  offline, from logs; it is not a runtime reward wired into the brain's loop.

## 7. Decided vs open

- **DECIDED (this doc):** rung 1 = within-run skill compilation only (design-space (i)), built as a
  `define_skill`/`run_skill` seam tool pair, `stop_when` restricted to cheap wire-visible predicates,
  skills logged verbatim and discarded at run end; design-spaces (ii)/(iii) are the promotion path,
  not built now; ARC-AGI-3 wa30 is the pinned first gate instrument (cheapest, external yardstick,
  already at "do not spend more without a new mechanism"); the 1.3x metric bar, length>=3 degenerate
  guard, `<=$15` cost cap, and fixed `--max-turns` are pinned before any build.
- **OPEN (flagged, not resolved here):** the exact `stop_when` predicate set may need one more entry
  once a real macro is drafted against wa30's actual action surface (e.g. a "grid cell color changed at
  (x,y)" predicate more specific than whole-frame `region_changed`) — any addition must stay inside the
  "cheap, wire-visible, no oracle" constraint and should be pinned in the build PR, not invented mid-run
  by the brain. Whether the Kirby entity-gate v3 or GATE-3D should be the SECOND gate instrument (after
  ARC) is left open pending rung 1's first result — cheapest-informative-next-step, decided after
  seeing which frontier the mechanism helps most. Whether `run_skill`'s single returned observation is
  sufficient context for the brain to trust a multi-step macro it didn't watch step-by-step (vs
  wanting an optional verbose trace) is a UX question for the build PR's review, not a gate blocker.
