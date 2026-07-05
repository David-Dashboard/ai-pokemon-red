# North Star capability map — what must exist to get there, with falsifiers and cheap probes

**Status:** strategic perspective, written 2026-07-05 by the retiring lead as the successor's
companion to the **world-lanes-frontier** skill. Lanes say where each WORLD stands; this map says
which CAPABILITIES the North Star still requires, what evidence exists, the cheapest next probe for
each, and — most importantly — what observation would FALSIFY each one. Nothing here is a
pre-registration; every paid spend below still goes through **gate-methodology** and David.

The North Star (HANDOFF §1): one agent — fixed brain + swappable perceiver — completing human-given
tasks at human-grade competence from the screen alone, across increasingly different worlds,
cheaply, without per-world training. Four claims: Capability, Constancy, Generality, Cheap.

---

## The six capabilities

### 1. Real time (acting while the world moves — and while the brain thinks)

- **Why necessary:** every world beaten so far waits for the agent — the harness advances on
  press/tick, so System 2 deliberates against a frozen frame. MKDS ended that: idle change
  12.22%/frame mean with zero input (`runs/nds3d_probe/FINDINGS.md:329`). Live games, computer-use
  under real deadlines, and every robot rung are real-time. Claim 1 at human-grade is unreachable
  without it.
- **What exists:** the continuous-time `stop_when` bridge design
  (`reports/2026-07-04-continuous-time-stopwhen-design.md`, merged) — bounded skills get a
  world-time budget; the MKDS build plan + pre-registration
  (`reports/2026-07-04-mkds-continuous-time-build-plan.md`).
- **The deeper cut this map adds:** the bridge handles *skills* in continuous time; it does not yet
  handle *deliberation* in continuous time. Today the world pauses while the brain thinks. Real
  time eventually removes the pause, which makes the seam asynchronous (state stream up, intent
  stream down, System 1 holding a safe default meanwhile). That is an ADR-level evolution of the
  frozen contract — the one place the contract should be EXPECTED to legitimately bend. Do it as a
  deliberate ADR, never a per-world hack.
- **Cheapest next probe (free):** scripted System-2 latency injection in MKDS — replace the brain
  with a scripted policy that goes silent for N seconds mid-race; measure ruin vs N. The resulting
  "survivable deliberation window" is the requirements spec for how much reflex must be compiled
  (capability 5) before real time is attemptable at all.
- **Falsified if:** no achievable reflex layer can hold a nontrivial world stable across realistic
  LLM latencies — i.e. the survivable window stays below the brain's best-case wake time even with
  compiled skills. Then screen-only + LLM-decisions cannot reach live worlds without a
  fundamentally different System 1, and the thesis needs an amendment, not a bigger brief.

### 2. Spatial reasoning — metric maps, place-graph, and the NAMED layer (the keystone)

- **Why necessary:** goal-directed tasks are referential — "go to Oak's lab", "fetch my mug".
  Three layers (reports/CONTEXT-BRIEFING.md "The frontier"): metric maps within a place (largely
  done in 2D), a topological place-graph across portals (fragile), a named/semantic layer binding
  language to places/objects (not built — the keystone gap). Instruction-following itself is
  trivial objective-injection; referential grounding is the real capability.
- **Sharpened diagnosis:** the missing thing is *addressability*, not reasoning power. The brain
  reasons fine; it has no stable structure to point at across warps. System 1 must own the
  structure; System 2 must only reference it by name (don't leak cognition into the world).
- **Cheapest next probe (free, Pokémon Red):** within ONE run — can the brain coin a name for a
  place ("home", "lab") and can System 1 resolve that name back to a goto target after >=5 portal
  transitions? Warps are already recorded; scoring is oracle map-id vs the resolved target. This is
  the named layer's thin skeleton + riskiest assumption, the 3D-gate move applied to language.
- **Falsified if:** name→place binding cannot survive portals without per-world ontology
  hand-authoring (that would breach "no per-world training" in spirit), or only works with the
  oracle's map ids on the wire (breaches screen-only). Either outcome is a first-class finding.

### 3. Complex perception (free-form fonts, non-tile rendering, 3D projection, photoreal later)

- **Why necessary:** the three banked NDS breaks — free-form non-tile font/HUD, rotating minimap
  killing the tile-grid, continuous camera roll killing discrete facing
  (`runs/nds3d_probe/FINDINGS.md:353-372`) — are the first tier of every harder world's perception.
- **What exists:** the Realizer Ladder discipline (R0→R3, climb only on a measured failed bar —
  **perception-primitives**); glyph R1 designed with a pinned gate; yaw_flow/stationary_movers as
  the first 3D primitives.
- **The honest wager:** every ladder climb erodes claim 4 (Cheap). The bet that must survive is
  that a SMALL set of primitives + RARE VLM escalation beats both a trained monolith and a
  per-world zoo. Track cost-of-perception per world class explicitly.
- **Cheapest next probes:** glyph R1 build against its pinned bar (recall >=0.85 / precision 0.90 /
  0 phantoms); a minimap-agnostic "where am I facing" primitive probed offline on the banked MKDS
  frames before any new paid run.
- **Falsified if:** any world class forces an R3 model on the HOT PATH (every frame, not at stuck
  moments) to meet its capability bar. That world class then costs what everyone else pays, and
  "cheap" is falsified there — bank it as a boundary, don't hide it.

### 4. Within-run long-horizon memory (the quiet killer)

- **Why necessary:** human-grade tasks run hours. The first long-horizon run
  (`runs/brain_kirby_longhaul`, 316 turns, $42.98) showed the failure shape: ~70M cache-read
  tokens, cost/turn ~2x the short-run rate, every remember-note re-injected verbatim forever, no
  compaction anywhere on the `claude -p` path (**long-horizon-runs**). Claim 4 dies of cost and
  claim 1 dies of incoherence at exactly the scale that matters.
- **Law note:** the fix is within-run memory hygiene (the brain summarizing/indexing its own
  history — progressive disclosure applied to its own past), which is learning-boundary-compliant;
  the segmented-chain ferry variant needs David's chain-as-one-run ruling first (flagged in
  **cheapness-skill-compilation** §4).
- **Cheapest next probe:** the pre-registered 2-session segmented pilot (~$10-15) — it
  simultaneously tests checkpoint continuity, the ferry, AND gives the first
  decisions-per-milestone-over-time curve.
- **Falsified if:** the wakes-per-milestone curve NEVER bends within a run as skills/lessons
  accumulate — that would mean System-2→System-1 compilation is decoration and the cost model is
  linear in task length forever. This is the single most falsifiable near-term claim of the whole
  thesis; seek the answer, don't protect the hypothesis.

### 5. Compiled conditional reflexes (the loop half — real time's secret dependency)

- **Why necessary:** batching passed (rung-1 2.94x) but the conditional half — a `stop_when` that
  genuinely branches on world state — has NEVER fired in a paid run (every attempt degenerated:
  `region_changed` at press 1, bare `steps_elapsed` counters — **cheapness-skill-compilation** §5,
  **diagnose-a-run** worked example). Without world-state-branching reflexes, System 1 cannot hold
  the fort at frame rate, so capability 1 is blocked on this one, not just the cost axis.
- **Cheapest next probes:** the doom scan-and-center port (its gate MUST require the loop half —
  already pinned) and the MKDS A/B (whose `stop_when` enum is continuous-time-native, sidestepping
  the converging-enemy degeneracy that killed the Kirby attempts).
- **Falsified if:** across ports with predicates matched to world physics (stationary targets,
  ego-motion-gated predicates), loops still collapse to one-shots or counters. Then the closed-enum
  design is too weak, and the escalation is a richer (still non-learned) predicate algebra — a
  design fork, pre-registered, not a silent widening.

### 6. Continuous action (the forgotten twin of complex perception)

- **Why necessary:** the action side degrades in parallel with the perception side: discrete
  buttons → touch coordinates (the NDS drag gap, `FINDINGS.md:216-219`) → hold-duration steering
  (MKDS) → analog sticks → joint torques (robot rungs). The harness currently speaks buttons and
  single touches; the embodiment ladder's upper half is mostly this capability.
- **Cheapest next probes:** the touch-drag helper the NDS findings already flagged (pure
  world-side, free to build + test offline); steering-by-hold-duration as the first analog
  dimension inside the MKDS lane.
- **Falsified if:** continuous control demands a learned policy (violating no-training) or
  per-world controller code that dwarfs the perceiver (violating the constancy spirit — the
  "falsified if a new hand-written System-1 per genre" clause, HANDOFF §1).

---

## The interlock (why no single capability is "the" blocker)

Real time (1) demands compiled reflexes (5); reflexes demand the loop half; task scale demands
memory hygiene (4); everything referential demands the named layer (2); and both frontier axes
degrade perception (3) and action (6) together. The North Star falls not to one missing piece but
to a failed interlock. Retirement bets, for the record: **the named layer is the keystone**
(hardest, least prior art, most falsifying if it can't be cheap), **real time is the biggest
architectural risk** (the seam must bend by ADR without breaking constancy), and **within-run
memory is the most underestimated** (it fails slowly and expensively instead of loudly).

## Sequencing (unchanged from HANDOFF NEXT — this map only annotates it)

1. Merge PR #101 (skill library) — process substrate.
2. **MKDS build + A/B** — buys evidence on capabilities 1, 3, 5, 6 at once; that density is why it
   is the right next spend.
3. **Segmented pilot** (after the ferry ruling) — capability 4 + the curve-bend measurement.
4. **Glyph R1 build** — capability 3, ladder discipline worked example.
5. **Doom scan-and-center port** — capability 5's cleanest shot at the loop half.
6. **Named-layer probe then design doc** — capability 2, thin-skeleton-first.

Rule this map adds to the process: **every future gate names which of the six capabilities it buys
evidence about**, in its pre-registration. A gate that buys none should not be run.

## Sources

- `HANDOFF.md` §1 (the four claims; "falsified if"), newest blocks (2026-07-04/05).
- `reports/CONTEXT-BRIEFING.md` (the frontier: three spatial layers; instruction-following ≈
  objective injection; probe-first).
- `runs/nds3d_probe/FINDINGS.md` (idle 12.22%/frame :329; the 3 perception breaks :353-372;
  touch-drag gap :216-219) — on-disk, gitignored.
- `runs/brain_kirby_longhaul/` (316 turns / $42.98 / cache-read growth) — on-disk, gitignored.
- `reports/2026-07-03-skill-rung1-ab-verdict.md` (2.94x PASS; batching-only honest bound).
- `reports/2026-07-04-continuous-time-stopwhen-design.md`,
  `reports/2026-07-04-mkds-continuous-time-build-plan.md`.
- `reports/2026-07-03-glyph-r1-cache-driven-detection.md` (pinned R1 gate).
- Skills: **world-lanes-frontier** (per-world status), **cheapness-skill-compilation** (loop-half
  bound, learning-boundary law), **long-horizon-runs** (memory/cost evidence),
  **perception-primitives** (Realizer Ladder), **gate-methodology** (how any of this gets spent).
