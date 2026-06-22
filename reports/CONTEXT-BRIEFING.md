# Context briefing — what this project is

A self-contained briefing you can hand to a person or an LLM to explain the project cold. No insider
shorthand left undefined. (Living doc; for current status see `HANDOFF.md` §2.)

---

## TL;DR
We're building **one cheap AI agent that acts on a world using only what's on the screen** — no access to
internal game state — and that **generalizes**: the *same* brain should work across different games (Pokémon
Red first, then other 2D games, then 3D) and eventually a real robot. The game is a **testbed/probe**, not
the goal. The goal is a *simple, general, cheap* recipe for screen-driven agents.

## The goal (canonical)
> Build **one agent — a fixed reasoning brain + a swappable perception layer — that completes human-given
> tasks at human-grade competence using only the screen and human-grade controls, across increasingly
> different worlds, cheaply, and without per-world training.** *(Source of truth: `HANDOFF.md` §1.)*

Unpacked into testable claims (each separately checkable — that's what makes it a goal, not a vibe):
1. **Capability — human-grade task success from the screen.** Pixels in, human-grade actions out (buttons, or
   mouse/keyboard); **no privileged channel** (no RAM, no DOM, no accessibility tree, no API). Measured as
   task-success-rate vs. a human baseline. ("Could pass for a human" is a *symptom* of clearing the bar, never
   the objective — and we evaluate only on sanctioned/permitted targets.)
2. **Constancy — the brain doesn't change.** A new world swaps only the *perceiver* (+ a per-world config);
   the brain is reused unchanged. Success = how little changes outside the perceiver. (The core claim, and the
   one most likely to be false.)
3. **Generality — across two axes of increasingly-different worlds:**
   - **Embodiment ladder** (one self, locomotion, learns from its own motion): 2D game → 3D game → sim robot
     → physical robot.
   - **Computer-use track** (mouse+keyboard+screen, indirect/many-entity control, no single self):
     strategy/builder games (safe + scored sandbox) → permitted desktop/web tasks.
4. **Cheap.** Free fast System 1 does routine work; the costly System 2 (LLM) wakes only at decisions
   (cost/task + wakes/task held low).

**No across-run training** is an invariant throughout: the agent starts blank each run and learns only
*within* a run (online); we are explicitly **not** doing the big-data / model-training approach (a deliberate
later decision may revisit this). **Falsified if** constancy breaks, pixels-only can't match a privileged
channel, or it only works on the easy slice and collapses on held-out worlds.

## Background (why this, why now)
- **Perception is the bottleneck, not planning.** The strongest comparable system (Cradle, a screen-only
  agent driven by GPT-4o) reports its main failure is *perception* — it can't reliably locate objects on
  screen. That validates our bet: the hard part is cheap, accurate perception, and calling a giant model
  every step is the wrong hammer (slow, expensive, and *still* perception-limited).
- **Everyone who generalizes across games today does it with massive training** (behavior cloning on
  internet-scale gameplay). We bet you can generalize with **structure instead of training**: a swappable
  perceiver + a world model the agent builds from its own behavior.
- **The pieces exist; the combination is open.** Dual-process agents, behavior-grounded traversability
  (robotics), skill libraries — all proven separately. Nobody has combined *cheap + screen-only + no-training
  + behavior-grounded + dual-process + held-out cross-game generalization*. That intersection is our bet.

## The method (how it's built)
**A decoupled dual-process architecture** (loosely, fast reflexes vs. slow deliberation):
- **System 1 (the "world interface")** — fast, free, runs every step: turns pixels into a structured state,
  runs a reflexive autopilot (explore, navigate, simple reflexes), and tracks cheap signals (a map of where
  it's been, what's novel, outcomes of actions).
- **System 2 (the "brain," a separate service called *aria*)** — an LLM woken *only* at decisions. It owns
  reasoning, identity, and memory. It is reused **unchanged** across worlds; that constancy is the whole
  contribution.
- They meet at **one frozen contract** (a structured state goes up to the brain; an intent comes back down).
  The brain never sees raw game internals.

**The core learning idea — "behaviour = truth":** the agent learns the world from its own actions. Walk onto
a tile → it's walkable; bump into one → it's blocked. It then generalizes those labels by appearance
(recognize a similar-looking tile elsewhere) using a *cheap perceptual hash* (we tested learned embeddings
like CLIP and found a plain hash beats them for pixel-art). Behavior is always authoritative; appearance-based
guesses are only advisory and get overridden by what actually happens.

**How we work (the discipline):**
- **Probe-first / cheap-first.** We use cheap offline *probes* as leading indicators of capability, instead
  of paying to run the full game to confirm things we can already predict. A paid end-to-end run is an
  expensive *audit*, invoked only when a probe leaves real uncertainty. (Example: a cheap 3D test in a
  Doom-like maze predicted "3D will work" and greenlit a whole 3D phase without building it.) The slogan:
  **probe = capability prediction; paid run = capability proof; minimize proof, maximize prediction, keep the
  predictor calibrated.** "Beating the game" is therefore not the objective — it's an expensive audit we
  invoke sparingly, only when a probe can't predict the outcome.
- **Adversarial verification.** Good-looking results get attacked before they're trusted. We've reversed our
  *own* headline findings three times this way — a metric that hid a failure, an offline speedup that didn't
  survive real closed-loop control, a logging bug that *understated* a result. Rule: pick the metric that
  matches the real downstream cost, hold out the right unit, measure in closed loop, verify before claiming.

## Where we are
- Foundation done and validated: the cheap loop, cost guardrails, the dual-process seam.
- 2D perception works: the agent perceives, navigates, and plays cold (gets its starter, wins early battles).
- 3D just greenlit via a cheap probe.
- Current phase: **cross-game generalization** — recording raw data from many Game Boy games, holding out
  some for honest testing, and building perception (especially self-localization) that works across them.

## The frontier (what's genuinely unsolved)
The next big pillar is **spatial reasoning for goal-directed tasks** — e.g. "go to Oak's lab," or for a robot
"fetch my mug." That needs three layers:
1. **Metric maps** *within* a place (grids, odometry) — largely done in 2D.
2. A **topological place-graph** connecting places through doorways/warps ("portals") — currently fragile;
   this is where spatial memory breaks across transitions.
3. A **named/semantic layer** so language can point at a place or object ("Oak's lab" → a location) — not
   built yet; this is the keystone gap.
Plus the weakest perception link: recognizing specific objects/entities. Note the split: System 1 (us) *builds
and executes* the spatial structure; System 2 (the brain) *decides where to go and why*. Don't leak the
cognition into the world.

**On instruction-following:** it is *not* a separate hard capability — **instruction-following ≈ objective
injection** (the brain sets System 1's overarching objective; System 1 executes). That control-flow is trivial
and largely already there for objectives whose referents System 1 already perceives (*explore*,
*go-to-coordinate*, *win-this-battle*). The real gap is **grounding *referential* targets** ("Oak's lab", "my
mug") in the named/semantic layer above — the perception/world-model substrate, not the instruction plumbing.

## Methods (how we actually build)
- **Compose small, cheap, off-the-shelf parts — don't train a monolith.** Many commodity tools are already
  good at one thing and run on CPU (perceptual hashes, CLIP/VLM features, OCR, classical CV, small classifiers).
  Weave them together — simply first, complex only when forced — to reach an outcome. **Simplicity is the
  default; added machinery must earn its place with a measured win.**
- **Decompose coupled problems into staged, decoupled sub-problems** (the master principle — the multi-stage
  detection analogy generalizes far beyond ML). Localization + classification fail as one monolith; split them.
  Our tile→function map *is* this: localization solved **behaviorally** (where's the faced tile, via
  odometry/geometry) + classification solved by **appearance** (what function, via a cheap hash) — never one
  end-to-end model doing both. The failed "CLIP predicts walkability end-to-end" was exactly the monolith.
- **Reuse a pretrained model + train a small cheap bridge** is a sanctioned method under the above (e.g. a
  frozen feature extractor + a tiny head, or an online behaviour-labelled lookup on top of fixed features).
  Prefer it over training anything large.
- **Probe-first / cheap-first measurement.** A cheap offline *probe* is a leading indicator of capability; a
  paid end-to-end run is an expensive *audit* invoked only when a probe leaves real uncertainty. Slogan:
  **probe = capability prediction; paid run = capability proof; minimize proof, maximize prediction, keep the
  predictor calibrated.** (How we greenlit 3D without building it.)
- **Progressive disclosure (context economy — provider-agnostic).** Keep the working set tiny: a cheap
  addressable *index* (names / descriptions / summaries) + *load-on-demand* + *tiered detail*. It's
  "cheap-first applied to *information*" — the context twin of the System-1/System-2 *compute* split (escalate
  on relevance, not by default). Already load-bearing here: the seam hands the brain a compact `SymbolicState`
  not raw pixels; the LLM wakes only at decisions; the cheap fingerprint indexes tiles and escalates only on a
  miss; per-wake memory injects only the relevant lessons; and the Skill Library needs it once it grows.
  **Design rule: a cheap index must fail SAFE — a miss means "load more / escalate," never "silently skip."**
  (Claude Skills' `SKILL.md` is *one encoding*; we adopt the pattern, not the product.)
- **Self-authored skills, promoted on proof (Sense B = "distil System 2 → System 1").** The agent compiles a
  repeated System-2 decision into a System-1 reflex *within* a run. A skill that proves **general on held-out
  worlds** is **promoted out of per-run agent memory into the across-run Skill Library (code / Claude-Skills
  format)** — the harness side. This keeps the learning-boundary law intact (agent blank each run, so we *test*
  the re-distillation capability with no leakage) while still banking genuinely general skills. **"Learning to
  learn" = a capability tested by wiping; "what was learned" = an artifact promoted only when proven.**

## Principles
- **Decoupled systems/subsystems** (ADR-001 is the load-bearing instance: brain vs. world; perceiver as the
  only swap point; one frozen seam).
- **Simple over complex** — always; complexity is a cost paid only against measured benefit.
- **Validate on quality data** — ground every claim in the oracle / real data, not model narration. Guard
  against model collapse / data decay: never train or tune on unverified model-generated labels; track data
  provenance; keep a held-out split you *never* tune on.
- **Test at every level** — unit + integration + **end-to-end** (and **closed-loop** when the policy's outputs
  change its inputs; an offline metric on a fixed trajectory is only a ceiling).
- **Log as much as possible** per experiment — every run leaves raw substrate + metrics so a result can be
  re-derived and adversarially re-checked later.
- **Verified honesty** — adversarially check your own findings; pick the metric that matches the downstream
  cost; hold out the right *unit*; reverse a call when evidence says so.
- **Ground at both scales (anti-collapse).** A closed loop feeding on its own outputs drifts (model collapse;
  "living only in your head"). Two grounding loops, same discipline: the **agent** grounds on the
  **environment** (behaviour=truth); the **research process** (David + Claude) grounds on **experiments +
  literature**. When experiments can't yet reach a step, prior-art/analogy can partially ground it. **Grounding
  gates *belief*, not *exploration*:** an ungrounded path may be walked as a *flagged bet* (prune only on
  tested failure, never on "can't test yet"), but it is never *claimed* until grounded — and for large,
  hard-to-test jumps, build a thin end-to-end skeleton + attack the riskiest assumption with the cheapest proxy
  (the 3D-gate move) rather than perfecting step 1.

## Preferences (tooling)
- **Containerize** components (reproducible, decoupled, deployable).
- **Python → use `uv`** (`uv run pytest -q`, `uv run python …`).

## Drift / contract tripwires — how we detect when something above breaks
Each invariant needs a *detector*; a principle without a tripwire silently rots. (✅ = exists, ▶ = to build.)
| Invariant / contract | How it drifts | Tripwire |
|---|---|---|
| **Frozen seam** (`core/contracts.py`) | someone edits the contract | ✅ hash-pinned test fails in CI |
| **Constancy** (brain unchanged per world) | a world "needs" a brain edit / a new System-1 per genre | ▶ brain is a separate repo — its git log should be empty when adding a world; per-world "perceiver-only" checklist; count LOC changed outside the perceiver |
| **No privileged-state leak** (RAM/DOM/a11y) | oracle fields creep into the agent's Observation | ▶ test asserting `Observation`/`SymbolicState` carries no oracle-derived field; log the perception channel per run; pixels-only mode reads no DOM/a11y/API |
| **Cheap** | cost/wakes per task creep up | ✅ cost-breaker + token meter + per-run cost report; threshold alert on cost/task & wakes/task |
| **Behaviour = truth / fail-safe** | confident mis-prediction instead of "novel→explore"; advisory overrides a real bump | ✅/▶ wall-recall (not aggregate accuracy) on held-out; veto test (behaviour overrides appearance); confident-wrong rate threshold |
| **Generalization** (held-out) | tuning leaks onto held-out; overfit | ✅/▶ `eval/cross_game.py` on the never-tuned split; alarm if held-out ≪ dev |
| **Data quality / no model-collapse** | training/tuning on unverified model output | ▶ provenance field in run `meta.json`; refuse model-generated labels not checked vs the oracle |
| **Simplicity** | a subsystem you can't explain in one sentence | ▶ design-review / `/simplify` pass; the "one-sentence rule" |

## Key terms (glossary)
- **Screen-only / no privileged state** — perceives pixels, not internal memory.
- **System 1 / System 2** — fast cheap reflexes vs. slow expensive reasoning (the LLM).
- **behaviour = truth** — learn the world from the consequences of your own actions.
- **perceiver** — the per-game perception module (the only thing we swap per world).
- **oracle** — internal game state used *only* to grade/verify, never fed to the agent.
- **probe** — a cheap experiment that predicts capability without a full paid run.
- **progressive disclosure** — keep the working set small: a cheap index + load-on-demand + tiered detail
  (provider-agnostic; the context twin of System 1/System 2). A miss must fail safe (escalate, not skip).
- **Sense A / Sense B** — A = the System-1/System-2 cost-speed split (the architecture); B = distilling a
  repeated System-2 decision into a System-1 reflex (self-authored skills + promotion to the library).
- **portal** — a warp/doorway between maps; it breaks the coordinate frame, forcing topological (not metric)
  reasoning.

---
*For deeper detail: `HANDOFF.md` (goal + live status), `ARCHITECTURE.md` (the dual-process contract / ADR-001),
`reports/2026-06-22-prior-art-scan.md` (who else is doing this), and
`reports/2026-06-22-research-takeaways-for-experiments.md` (component-by-component lessons).*
