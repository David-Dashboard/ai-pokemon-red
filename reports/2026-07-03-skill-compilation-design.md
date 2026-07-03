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
brain code — no brain edits, ever). **Rung-1 build scope: the `ArcAgi3Session` port ONLY** — one
world, the gate instrument (§4). The formalism below is world-generic, but each additional world
(GB, Kirby, doom, miniwob) is its own later port with its own pinned predicate enum and its own build
PR; rung 1 does not ship four bespoke executors.

- **`define_skill(name: str, steps: list, stop_when: str)`** — `steps` is a list of EXISTING
  primitive actions from this world's action surface (for ARC: `act`-payload entries such as
  `{"action": "ACTION1"}`, including ACTION6's x,y), each with an optional repeat count.

  **Honest accounting (review correction):** executing a heterogeneous step list is NEW world-side
  dispatch logic — a small bounded loop inside the session class — NOT a reuse of GATE-3D's `repeat`
  param (that param repeats one homogeneous action; this is a sequence dispatcher). What IS reused:
  every step resolves to an existing primitive's exact execution path (same validation, same logging,
  same oracle write), so no step can do anything a primitive call couldn't.

  **One bounded loop construct**, part of the formalism: `repeat_until(steps, stop_when, max_iters)`
  — re-run `steps` until `stop_when` fires or `max_iters` iterations complete. `max_iters` is
  schema-capped at **8**, no nesting (`repeat_until` may not contain another `repeat_until`), and an
  absolute ceiling of **50 world steps per `run_skill` call** is enforced world-side regardless.
  Terminates by construction; the executed iteration count is logged. This is what makes `stop_when`
  load-bearing ("push until the target cells change" instead of guessing N exactly), and it is what
  the entity-v3 exposure macro (§5) needs to be expressible at all.

  `stop_when` is drawn from a small closed **PER-WORLD** enum of cheap predicates computable
  WORLD-SIDE from data already on that world's wire. **Pinned now for ARC (the rung-1 build):**
  - `"grid_changed_in_region(x0,y0,x1,y1)"` — any cell in the box differs between consecutive
    post-action grids (a diff of two observations the brain already receives verbatim via `observe`).
  - `"grid_unchanged_for(k)"` — the whole grid identical for k consecutive world steps (stuck/blocked
    detector), `k <= 8`.
  - `"steps_elapsed(n)"` — n world steps executed, `n <= 50`.

  The GB-flavored predicates an earlier draft of this doc listed (`scrolled`, `region_changed`,
  `blocked`) are ILLUSTRATIVE of what a GB port's enum would pin — they are not on ARC's wire and are
  not part of rung 1's build. Each port pins its own enum in its own build PR under the same
  constraint: **never an oracle/RAM/score field, and never anything not already derivable from
  observations the brain already receives.** The no-new-channel claim holds precisely because every
  ARC predicate above is a diff/counter over the same grids `observe` already returns — the world
  computes cheaply what the brain could compute expensively by observing after every step; no new
  information crosses the seam. Definitions are logged verbatim to the transcript at creation time
  (auditable — a human reviewing the run sees exactly what macro was compiled and when).

- **`run_skill(name: str, args: dict)`** — executes the named skill's steps against the live world,
  advancing world state exactly as if each primitive had been called individually, checking
  `stop_when` after each step and returning early (with the reason) if it fires. Returns ONE tool
  result (one `observe()`-shaped view of the state after the skill ran, plus a log of which steps
  actually executed and why it stopped) — **one LLM decision, N world steps.**

**What the glyph-cache precedent does and does not cover (softened per review):** the analogy is the
within-run **compile-then-free-serve SHAPE** — an expensive System-2 event (confirming a glyph /
composing a skill) converts into cheap reuse (cache free-serve / one-decision execution),
harness-owned, dead at run end. The analogy is NOT the glyph cache's honesty mechanism: a cached
glyph is contested against fresh ground-truth observations (majority-vote invalidation on mismatch,
`TileFunctionMap.observe`), while a compiled skill has no ground truth to contest — it can simply be
WRONG for the current world state, with nothing to outvote it. What substitutes, explicitly weaker
and named as such: (1) **`stop_when` divergence abort** — the skill halts world-side the moment its
continuation condition fails, without waking the LLM; (2) **verbatim logging** of the definition and
of every executed step plus the stop reason, so a mis-firing skill is visible in the transcript and
auditable after the run. The 96.9% free-serve number validates the lifetime-and-shape precedent, not
this mechanism's correctness — that is what §4's gate exists to test.

**Token cost estimate.** A primitive-by-primitive equivalent of a 6-step macro (e.g. an ARC
push-block: three ACTION-moves, ACTION5, two more moves) costs **6 LLM decisions** — 6 round-trips,
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

Before any paid A/B: a **scripted/replay comparison**, free (ARC API steps are free; no brain
session). Take the existing wa30 transcripts (three runs in `runs/brain_arcagi3/`) — which contain
known-repeated action patterns (multi-ACTION push/walk sequences) — and drive the same sequences
through `run_skill` mechanically to confirm: (a) the pinned ARC stop-conditions fire at the points a
human reading the transcript would call the macro "done"; (b) the skill log is auditable (a reviewer can read
`define_skill`'s logged definition and `run_skill`'s per-call step log and reconstruct exactly what
happened, same bar as the entity-gate NEAR-corroboration audit). This is a **build-correctness check**,
not the gate itself — it must pass before any paid arm is scheduled, same discipline as GATE-3D-A3-PC
gating PR-H.

### 4.1 The paid A/B (one arm each, same brief, same world, same `--max-turns`)

**Pinned metric:** task progress per paid decision.
- **ARC-AGI-3 instrument:** levels_completed (or, on a levels tie, the pinned M1-M7 milestone count
  defined below) per 100 turns, where a "turn" = one LLM decision (i.e. one `act`/`run_skill` call,
  NOT one primitive world-step — this is the whole point: `run_skill` must not get free extra turns
  by definition).
- **Kirby entity-gate instrument (a LATER port's gate, not rung 1's):** banked gate events (accepted
  NEAR coverage of drop steps, per `reports/2026-07-03-entity-gate-v2-plan.md`'s `q_k` machinery) per
  decision — noted here so the metric shape is on record, but it cannot run until the Kirby port
  exists (§3 build scope).

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
  arms tie on levels (plausible given the wall is depth, not breadth), the pinned fallback below —
  pinned NOW so it can't be picked after seeing which arm looks better.
- **PASS bar for skill tools helping:** Arm B's metric `>= 1.3x` Arm A's metric (a 30% lift — chosen to
  be clearly outside run-to-run noise given the existing 3-run spread already shows some variance in
  cost ($6.69/$8.89/$20.82) at flat 1/9 outcome; 30% is a real, visible effect, not a coin-flip margin).
- **Zero-denominator rule (pinned, non-amendable-looser):** if Arm A's primary metric is **0** (zero
  levels completed), the ratio is undefined and is NOT computed. Arm B then PASSes only by clearing a
  pinned ABSOLUTE floor: **levels_completed >= 2**. Justification: 1 level is the established
  no-mechanism outcome of every wa30 run to date (three runs, three framings, all 1/9), so a single
  level from Arm B over a zero-level Arm A is indistinguishable from ordinary variance; 2 levels is
  the L2 wall itself falling, which no run has done under any framing — the only Arm-B-alone result
  strong enough to stand without a baseline. Anything below the floor with a zero Arm A =
  `INSUFFICIENT_DATA` (NO_COMPARISON), never a ratio PASS. Lowering the floor = loosening; forbidden.
- **Fallback metric (pinned milestone count), with anti-fabrication machinery equivalent to
  entity-gate v2's NEAR channel:**
  - *The milestone list is pinned HERE, before any run — nothing else counts.* For wa30 (each drawn
    from the run-1 transcript's oracle-verified ontology, HANDOFF 2026-07-04, i.e. things the game
    demonstrably contains): **M1** avatar sprite identified (incl. facing marker); **M2** movement
    semantics (ACTION1-4) grounded by experiment; **M3** ACTION5 grab/release toggle grounded;
    **M4** a block delivered to a container (delivery observed as a grid change); **M5** timer
    mechanic identified (row-63 fill); **M6** level 2 entered; **M7** a distinct level-2 manipulation
    attempted with an observed grid change.
  - *Corroboration (scorer checks the wire, not the assertion):* a claimed milestone counts ONLY if
    the transcript's observation content at or before the claiming position actually shows the
    corroborating wire data (e.g. M4 requires an `observe`/diff-summary showing the container's cells
    changing on the delivery action; M3 requires the grid response to ACTION5 visible in a diff).
  - *Watermark (current-position-only):* milestone claims carry no step argument — they count at the
    transcript position where they are logged, and the corroborating observation must appear at or
    before that position. No back-dating; a claim whose corroboration appears only later is excluded
    (same rule shape as v2's retroactive-NEAR guard).
  - *Dedupe:* each of M1-M7 counts at most once per run.
  - *Mandatory post-run audit* (same discipline as v2's sparse-burst-NEAR audit): the reviewer
    confirms each counted milestone's corroborating observation is real, not a verbose restatement.
- **Degenerate-strategy guard, wired into the verdict:** a QUALIFYING skill call = a `run_skill` whose
  logged **EXECUTED** step count is `>= 3` (executed, not defined — a 10-step definition that stops
  after 1 step does not qualify). **If Arm B's qualifying-call count is 0, the A/B is uninformative
  and the verdict is `INSUFFICIENT_DATA`, not PASS/FAIL** — the mechanism under test was never
  exercised, so neither a lift nor its absence says anything about skill compilation. The post-run
  audit additionally confirms qualifying calls are genuine multi-step routines, not padded no-ops.
- **`--max-turns` (the ONLY mechanical budget enforcement): 80 per arm, pinned.** Ledger arithmetic:
  linearly scaling the observed wa30 run costs ($6.69 under a 100-turn cap, $20.82 under a 160-turn
  cap) to 80 turns gives $5.35-$10.41 per arm, i.e. **$10.7-$20.8 for the pair, ~$15 expected**. The
  **$15 figure is a TARGET, not an enforcement mechanism** — per the GATE-3D protocol-breach lesson,
  prose and dollar figures do not enforce anything; the turn cap does. 80 also exceeds the 67
  decisions the L1 completion actually took, so the runway is real. Launch order is pinned: **Arm A
  (baseline) first.** If Arm A's actual spend lands above $10, the operator may tighten (never raise)
  Arm B's cap before its launch — tightening only the SKILL arm's budget can only bias AGAINST a
  PASS, so this stays stricter-only; Arm A's cap is never adjusted after the fact.
- **One attempt per arm (pinned):** each arm gets ONE paid attempt under this pre-registration. A run
  that dies of infrastructure failure (MCP/seam failure, credit exhaustion, launcher bug) before
  **N=10 decisions** may be relaunched ONCE; an infra death at or after 10 decisions, or a second
  infra death, banks that arm as `INSUFFICIENT_DATA`. A completed arm's result is banked — never
  informally re-attempted; a FAIL is a FAIL on the books, exactly as entity-gate v2 and GATE-3D bank
  theirs.
- **Amendment rule:** stricter-only, per house discipline — the 1.3x bar, the >=2-level absolute
  floor, the >=3-executed-step guard, the milestone machinery, the turn caps, and the attempt rule
  may be tightened by a future pass but never loosened to rescue a marginal result.

## 5. What this buys each frontier

**ARC L2 (navigation/manipulation macros) — served by rung 1 directly (the build).** wa30's
block-quantized sokoban mechanics reward a push macro expressible entirely in the pinned ARC enum:
`repeat_until(steps=[{"action":"ACTION1"}], stop_when="grid_changed_in_region(cx0,cy0,cx1,cy1)",
max_iters=8)` — push toward the container until its cells change (delivery) or, via
`grid_unchanged_for(2)`, detect the block is stuck against a wall. Today the brain re-plans every
single ACTION1-4 press; a compiled macro turns "push this block toward that container" from N
decisions into 1, directly multiplying how many multi-step sub-goals fit inside the same
`--max-turns` budget — precisely the depth wall HANDOFF diagnosed.

**Entity v3 (exposure-control macro) — expressible in the formalism, needs the Kirby port (a later
rung) before it runs.** The v2 FAIL's own language calls for "an EXPERIMENT-DESIGN skill (or a
System-1 exposure-control primitive)" — rung 1's formalism supplies exactly that shape via the loop
construct: `repeat_until(steps=[approach k tiles, retreat k tiles], stop_when="steps_elapsed(n)",
max_iters=m)`, an alternation the brain could never express as a flat step list. The predicates named
here are placeholders: the Kirby port's build PR must pin its own enum from the GB wire
(`whats_changed`-shaped region checks and the move-outcome signal are the obvious candidates) before
this macro exists. Rung 1 gives entity v3 its mechanism shape; the port gives it hands.

**GATE-3D (scan-and-center hunt macro) — same status: formalism now, doom port later.** A doom port
would pin its own enum from data already on the doom wire — e.g. `"mover_visible"` (P2's azimuth list
non-empty, already returned by `observe`) plus `steps_elapsed` — and the hunt macro becomes
`repeat_until(steps=[turn_left], stop_when="mover_visible", max_iters=8)`: turn until a mover
appears, then wake for the centering/attack decision. That converts arm (a-1)'s hunt-efficiency
problem (K=4.07 vs bar 5.61) from "many individual turn decisions per kill" into "one decision, many
turns, then one attack decision" — exactly the K-per-decision lever the gate measures.

## 6. Explicit non-goals (rung 1)

- **No multi-world build.** Rung 1 ships exactly ONE executor: the `ArcAgi3Session` port. GB, Kirby,
  doom, and miniwob ports are later rungs, each with its own pinned per-world predicate enum and its
  own build PR — the §5 Kirby/GATE-3D paragraphs are design illustrations of the formalism, not
  rung-1 deliverables.
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
  `define_skill`/`run_skill` seam tool pair + ONE bounded loop construct (`repeat_until`, max_iters
  <= 8, no nesting, 50-world-steps-per-call ceiling); rung-1 build scope = the `ArcAgi3Session` port
  ONLY; `stop_when` enums are pinned PER-WORLD (ARC's three predicates pinned here; other worlds pin
  theirs at their own port PRs); skills logged verbatim and discarded at run end; design-spaces
  (ii)/(iii) are the promotion path, not built now; ARC-AGI-3 wa30 is the pinned first gate
  instrument; pinned before any build: the 1.3x bar, the zero-denominator absolute floor (Arm B >= 2
  levels when Arm A = 0), the M1-M7 milestone fallback with corroboration/watermark/dedupe/audit
  machinery, the >=3-executed-step qualifying-call guard wired into the verdict (0 qualifying calls
  = INSUFFICIENT_DATA), `--max-turns` 80/arm as the only mechanical budget enforcement ($15 = target),
  and one-attempt-per-arm (one relaunch only for an infra death before 10 decisions).
- **OPEN (flagged, not resolved here):** whether ARC's three pinned predicates suffice for the first
  real macros the brain writes — any addition happens at the build PR (never mid-run, never
  brain-invented) and must stay inside the "cheap, wire-visible, no oracle" constraint. Whether the
  Kirby entity-gate v3 or GATE-3D should be the SECOND port (after ARC) is left open pending rung 1's
  first result — cheapest-informative-next-step, decided after seeing which frontier the mechanism
  helps most. Whether `run_skill`'s single returned observation is sufficient context for the brain
  to trust a multi-step macro it didn't watch step-by-step (vs wanting an optional verbose trace) is
  a UX question for the build PR's review, not a gate blocker.
