# The North Eye — a perception-primitive constitution (+ the project technology budget)

_Status: design constitution (a discipline for HOW we design perception primitives), **not a build order**.
Gate-first still governs what we actually build. Changes no code. 2026-06-26._

## Context

The perception layer grew ad-hoc: a hand-picked `MoveSignal` per "camera class", a fragile per-game pixel
threshold (`fg_grid=58`), a fresh perceiver per world. That violates the north star — the **brain** is fixed and
constant; the **eye** should be a *small fixed set of primitives the world self-selects*, not bespoke code per
game. This doc pins a **timeless mental model** for designing those primitives — anchored on Marr's three levels,
updated for ~40 years of embodied cognition — plus a **project-specific technology budget** (the Realizer
Ladder: cheap pixel ops by default, climbing to fine-tunable learned models only when measured data complexity
demands it).

It is a constitution, not a plan. It frames the existing `AvatarLocalizer` work (on the `fix/cave-noire-strand`
branch) as its first instance and the `MoveSignal` design as its canonical violation, but it ships no code.

---

## 1. Framework: Marr, updated for embodiment

David Marr's three levels of analysis (1982) remain the right **separation discipline** — keep them, and never
confuse them:
- **Computational** — *what* is computed and *why* (the problem, the decision served, the invariance provided).
- **Algorithmic** — the *representation* and *procedure* that compute it.
- **Implementational** — the *physical realization* (the actual code/model/hardware).

But Marr's *content* was a feed-forward, reconstruct-the-3D-world pipeline. Four decades of embodied/active
cognition revise it on five points:

| # | Marr (1982) | Update | Our consequence |
|---|---|---|---|
| 1 | Feed-forward pipeline (image→primal sketch→2.5D→3D) | **Closed loop** — active vision, sensorimotor contingencies, active inference *(established)* | Primitives are grounded by **action↔sensor correlation**, not asserted. This is *the* binding principle (rule 2 below). |
| 2 | The three levels are independent | The levels are **coupled** — what's cheap on today's hardware flows *up* into algorithm and even problem framing *(established)* | The implementation layer is **first-class and time-bound**; design to swap the realizer (the Realizer Ladder, §3). |
| 3 | Goal = full 3D reconstruction | Goal = the **minimal task-sufficient signal** (the frog's bug-detector; behavior-based vision) *(established)* | A primitive's contract names *the decision it serves*, never "reconstruct the scene". Task-relative and minimal. |
| 4 | Primitives are fixed / innate | The **fixed↔learned boundary is movable**, set at runtime by grounding (ADR-002) *(our synthesis)* | Each primitive declares what is fixed vs world-discovered; the line can move *down* (more learned) over time. |
| 5 | Representations are deterministic | Representations are **probabilistic** (the Bayesian brain) *(established)* | Every primitive emits **value + uncertainty + an explicit "can't tell" (`None`)**. Fabrication is forbidden. |

**Pin the mental model at the computational level — it is the timeless part.** A perceiving agent answers a small
fixed set of questions; the realizers below them churn with technology and world:

> **The six questions.** *What is here?* (entities/segmentation) · *Where am I?* (localization/pose) · *What
> changed — including how did I move?* (change & ego-motion) · *What do my actions do?* (action↔effect) · *What
> followed?* (consequence) · *What mode am I in?* (modality).

And a four-layer stack, meaning flowing upward:
- **L0 — sensors:** raw frame, button stream, audio. The transducers.
- **L1 — signals (meaning-free):** frame-diff, ego-motion shift, change-grid, foreground blob, perceptual hash.
  Numbers, not nouns. ("Here is a moving blob + its fingerprint", never "that is an enemy".)
- **L2 — grounded structures:** pose/occupancy, a tracked entity with a persistent id, a localized avatar.
  Built from L1 + the action↔sensor loop.
- **L3 — semantics:** "that region is my health", "those are enemies" — the brain *hypothesizes*, behaviour
  *grounds* (ADR-002). Never hand-asserted at L1.

The "camera class" was a category error: it baked an L3-ish label ("this game is follow-scroll") into L1 code.
The fix is one L1 ego-motion primitive that just reports its two channels + confidence; the *world* selects.

---

## 2. The primitive contract

Every North Eye primitive declares all seven. If you cannot fill a slot, the primitive is mis-designed.

1. **Computational** — the question it answers, the decision it serves, the invariance it provides. Minimal and
   task-relative (Marr L1 + update #3). Not "what is the scene" — "what does the brain need to decide next".
2. **Grounding (the loop)** — how it is calibrated and validated by **action↔sensor correlation against truth**,
   actively where possible (update #1). No hand-asserted meaning. This is the frontier and the hardest slot.
3. **Algorithmic** — representation + procedure; must be reflexive/cheap if it runs in System 1.
4. **Implementational (swappable, time-bound)** — the realizer, chosen by the fidelity regime via the Realizer
   Ladder (§3). Explicitly allowed to change without changing slots 1–3.
5. **Output contract** — **value + confidence + an explicit `None`/"unlocked"** (update #5). Returning a fabricated
   value when the signal is absent is the cardinal sin (it is what dead-reckoning did).
6. **Layer & composition** — which of L0–L3 it lives at, what it consumes and produces.
7. **Selection** — the world activates it by **grounding payoff**, not a hand-label. If a primitive needs a human
   to declare "use this in fixed-camera games", it is mis-designed (the `MoveSignal` sin).

---

## 3. Addendum — the project technology budget: the Realizer Ladder

This operationalizes update #2 and contract-rule 4 for *this* project. The implementational level is a **ladder**;
**default to the lowest rung and climb only when a cheaper rung fails a pre-stated bar on real data
(measure-first)**, or when fidelity/semantics genuinely demand it. The rung is context- and layer-dependent:
different worlds, and different layers within one world, sit at different rungs at the same time.

- **R0 — cheap pixel ops (numpy/PIL). The default.** Frame-diff, `best_shift`, grid-max change, dHash,
  background-subtract + centroid, histograms, connected-components. Ideal for pixel-art / low-fidelity / clean
  signals. Zero training, CPU, microseconds. Most of `core/` and `eval/` lives here.
- **R1 — classical CV + tiny learned.** Template matching, optical flow (Lucas–Kanade / Farnebäck), a small
  logistic / kNN / MLP over cheap features (already used in the `eval/` probes). Fine-tunable on our recordings,
  still cheap.
- **R2 — lightweight neural nets, FINE-TUNABLE.** A small CNN / MobileNet-class / small pretrained backbone,
  **fine-tuned on our own data**. This is the "advanced model (CNN)" for when cheap ops provably cannot separate
  the signal — clutter, animation, near-photoreal. Commodity hardware, cheap inference.
- **R3 — off-the-shelf zero-shot / VLM.** Heavy pretrained models for genuinely hard L3 semantics (faces,
  arbitrary objects, in-the-wild OCR). Time-bound, swappable, used **sparingly** — cost, plus the
  invariance-machine caveat (an embedding forgives exactly the small changes a game often needs you to notice;
  `reports/2026-06-24-visual-embedding-models-survey.md`).

**Climb triggers (measured, never merely preferred):**
(a) **fidelity rises** — pixel-art → 2D-animated → 3D → photoreal;
(b) **a probe proves the cheap rung can't separate** the signal (cf. the no-static-threshold finding for Cave
Noire move-detection; the CLIP-vs-hash survey);
(c) the question is **inherently semantic** (true L3).

**Project constraints (the "cheap" north-star invariant):** prefer the lowest passing rung; models stay
**lightweight and fine-tunable**; no train-from-scratch heavyweights; fine-tuning small models on our recordings
is *encouraged*; heavy / zero-shot only where it beats cheaper rungs on a *measured* bar. This pairs with the
`CLAUDE.md` laziness ladder (reuse-before-build extended to cheap-before-heavy).

---

## 4. Code impact (described here; not changed in this PR)

- **`MoveSignal` (the camera-class split) is the canonical violation.** It is hand-selected per world (breaks
  rule 7), emits a hard verdict (a `MoveResult`) with no confidence field (breaks rule 5), and its thresholds are
  hand-set rather than grounded (breaks rule 2). The eventual fix: a single ego-motion **L1** primitive that reports *both* channels
  (camera shift + foreground change) as value + confidence and lets the world select by grounding payoff —
  dissolving "camera class" as a concept.
- **The `AvatarLocalizer` work** (on the `fix/cave-noire-strand` branch) is the first **L2 `track`/`localize`**
  primitive written to this contract: action-correlated avatar selection (rule 2), `None` when unlocked (rule 5),
  a numpy realizer at R0/R1 (rule 4). Its open-loop probe — scored against hand-labels — is the ladder's
  measure-first gate in action: whether the cheap R0 rung suffices or must climb is decided on data, not asserted.
- **ADR-002's sensorimotor floor** is exactly the L1/L2 primitive list; this constitution gives each one the
  seven-slot contract and a ladder rung.
- **`confidence=0.4`** (a hard-coded placeholder in `GridPerceiver` + the Pokémon perceiver) is the unfilled
  rule-5 slot — it marks the primitives not yet honest about their own uncertainty.

---

## 5. Discipline

This is the **shape of the toolbox, not a build order.** Build only the primitive the current gate needs, to
this contract; prove it grounds against truth; only then generalize. The frontier is rules 2 + 7 — grounding and
self-selection — which together are the loop-closure / self-calibration problem the project keeps meeting (the
dead-reckoning drift, the no-static-threshold wall). The constitution's job is to make every primitive **honest
about needing that loop**, rather than papering over it with a hand-set constant or a hand-picked class.

---

_See also: `reports/2026-06-25-adr-002-ontology-discovery.md` (the sensorimotor floor + the hypothesize→ground
loop), `reports/2026-06-24-visual-embedding-models-survey.md` (why an embedding is an invariance machine), and
the `AvatarLocalizer` plan in the active fix branch._
