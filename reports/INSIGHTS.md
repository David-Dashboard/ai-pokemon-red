# Insights — the ideas behind ai-pokemon-red

A thematic synthesis of the conceptual insights from building this probe (distinct from
`LEARNINGS.md`, which is the chronological, per-iteration log). The north star: a **simple,
generalizable, cheap** agent that acts from the **screen** (no ROM/privileged state), with a fully
decoupled brain. Pokémon Red is the first probe world. These are the ideas that survived contact with
real runs.

---

## 0. The thesis in one sentence

**The agent reasons fine on *clean state*; almost all the engineering is in producing clean state
cheaply, behind a seam, so the same agent transfers to a new world unchanged.** Every other insight
below is a corollary of that sentence.

---

## 1. The perception seam *is* the generalization mechanism (symbolic representation of perception)

The agent never sees pixels. It sees a **role-named `SymbolicState`** — an abstract belief state:
`pose`, `spatial_memory` (occupancy/places), `affordances` (what I can do here), `context`
(overworld/menu/dialog/battle), `screen_text`, `last_action` + outcome, `confidence`. This is the
robot's-eye abstraction, deliberately game-free: *where am I, what's around me, what can I do, what
did my last action achieve.*

Why this matters:

- **`core/` (the agent) is world-agnostic and runs unchanged.** The brains, the outcome/disconfirm
  loop, the runner/gateway, the memory — none of them know what game it is. They consume the abstract
  shape. (Proven: the same brains run on the synthetic `gateworld` unchanged.)
- **`games/<world>/` is a swappable *perception adapter*** that turns pixels → `SymbolicState`. The
  textbox decoder, the move-menu decoder, `detect_mode` — all live here, not in `core/`. By design.
- So **"generalize" never meant "zero per-world perception."** It means the *hard* part — reasoning,
  memory, acting, learning — transfers, and the perception behind the seam is re-fitted (or upgraded)
  per world without touching the agent. Adding game #2 = a new adapter, never a new agent.

The seam is what makes the rest of the plan possible: because the agent consumes an abstraction, you
can put *anything* behind it.

---

## 2. Generalizing the perception itself: a toolkit of primitives, not bespoke code

The worry: if each game needs its own pile of decoders, did we generalize, or just move the per-game
work from the agent to the perceiver? The answer: **what looks like Pokémon-specific code is actually
*instances of general perceptual primitives*.**

| What we built (Pokémon) | The general primitive it instantiates |
|---|---|
| Gen-1 textbox decoder | read the **text region** of a UI |
| move-menu decoder + cursor | read a **list widget + which item is selected** |
| `detect_mode` | **classify the screen / UI state** |
| translation transitions | **ego-motion vs scene-cut** |
| topological place-graph | **topological SLAM** (places + transitions) |
| odometry / occupancy map | **dead-reckoned spatial memory** |

Every one of those recurs in essentially every game and every desktop app. The Pokémon-specific part
is the **calibration** — *where* the text region is, the font bitmaps, the cursor's cell, the tile
size — not the algorithm. So:

- **The durable, reusable asset is a *toolkit of perceptual primitives* + a thin per-world config.**
- **The discipline** is to *lift* a primitive out of `games/` into a shared perception library the
  second time it's needed, so game #2 **reuses** rather than rewrites.
- **The honest test of generalization is game #2** (a *different real* game): how much of
  {text-reader, list-reader, scene-cut detector, place-graph} reuses with only re-calibration vs.
  needs a rewrite? That number — not any architecture diagram — is the actual measure of whether we
  built a framework or a Pokémon-shaped thing wearing a framework costume.
- **The risk** is letting specifics ossify in the perceiver without lifting primitives or proving on a
  2nd world. **Mitigation:** keep `core/` clean (done), refactor recurring primitives, run a 2nd game
  sooner rather than later.

---

## 3. The endgame: a general perception *model* replaces hand-built decoders

We hand-build decoders **only because the cheap model's vision is weak.** This is the project's
founding finding (Iteration-01: "Haiku confabulates from raw pixels — invents NPCs from furniture")
and it resurfaced in battle (run #9, below). The decoders are a **crutch for that weakness.**

A stronger vision model — or a dedicated perception model, or even a game's accessibility API — reads
*any* screen into structured state with no per-game decoder. And because the agent consumes the
`SymbolicState` seam, you can **swap the hand-built perceiver for a VLM behind the same seam, per
world or globally, without changing the agent.**

Implication: **a lot of per-game perception work is a temporary artifact of cheap-first + 2026 model
capability. It shrinks as models improve.** The *permanent* assets are (1) the seam, (2) the agent,
(3) the toolkit of primitives. We're cheap-first today, so we hand-build; the architecture keeps the
upgrade path open.

---

## 4. Confabulation: weak vision fills gaps with a confident *prior*, not random noise

The sharpest empirical insight of the late sessions. In battle the agent confidently believed the
*wrong* world — it narrated *"I'm Squirtle, I'll use WATER GUN to finish Charmander"* while the screen
plainly showed its own Pokémon was Charmander and the foe was Squirtle.

The clean A/B test (run #9, image OFF): **the confabulation vanished.** So:

- **The source was the image** — Haiku misreading the low-res sprites — not random noise. It
  *constructs an internally-consistent wrong model* ("rival battle → I should have the type advantage
  → I'm the water type") and then **reads the screen *through* that prior.**
- **A soft prompt nudge can't dislodge a coherent prior.** We tried "TRUST THE SCREEN"; it failed.
  You cannot prompt your way out of a confident wrong belief that the model built from bad perception.
- **The cure is clean decoded *state*, not prompt-nudging.** Image off + completed OCR + the move-menu
  decode → correct grounding ("Charmander vs Squirtle, bad matchup") → it fought correctly → it won.

This is the same story as §1–3 from the other direction: **the reasoning was never broken; the
*input* was.** Fix the perception and the agent is fine.

---

## 5. Cheap-first as an architecture: expensive brain sets *intent*, cheap controller *executes*

The cost model isn't "call the LLM less"; it's a **division of labor**:

- **Navigation already embodies it.** The LLM names a target (`GOTO: x y`); a free autopilot
  BFS-pathfinds there; the brain is re-woken only when the autopilot is **stuck**. The expensive model
  sets *intent*; the cheap controller *executes*; routine work never touches the LLM.
- **Dialog already embodies it.** Plain text is auto-advanced for free (press A), accumulated into a
  transcript; the LLM is woken only at real **choices**.
- The general rule: **do the mechanical thing in the harness; wake the expensive model only at genuine
  decisions.** Most of a game is mechanical.

---

## 6. System 2 → System 1: skill compilation (and how the LLM designs a policy)

The biggest forward idea. "Wake at decisions" is currently **static** (wake at every menu). It should
become **adaptive and learned**: the wake rate should *drop as the agent learns the game*, not stay
flat. You don't beat a 10,000-step game with 10,000 LLM calls.

**The pattern (cognitive "production compilation" / System-2 → System-1):**

1. The first few times a situation recurs (e.g., battles), the LLM **deliberates** move-by-move
   (System 2 — slow, expensive, general).
2. From those decisions it **distills a policy** (a strategy).
3. A **cheap executor runs that policy blindly** (System 1 — fast, free, narrow).
4. The brain is **re-woken only on *novelty*** — a new type, low HP, a move that stopped working —
   i.e. when the cheap policy is out of its depth.

**How the LLM "designs a policy" the harness can execute — and why it's now feasible:**

- A policy is a **function of decoded state**: *(my Pokémon, foe type, my HP, my moves, which menu)*.
- This is feasible **only because we decoded the state** (move menu + cursor + names + HP). Before the
  decode, the LLM re-read pixels every battle and could compile nothing reusable. After it, a battle
  situation is a **structured tuple** → a decision can be *cached and replayed*, or written as *rules*.
- Two concrete forms:
  - **Memoize:** cache the LLM's menu decision keyed on the decoded state; on a recurring state,
    replay the action with **no wake**; re-wake on a novel state.
  - **Rules:** the LLM emits an explicit strategy ("pick the highest-damage non-resisted move; potion
    under 30% HP; never a status move unless setting up") that a small harness interpreter runs against
    the decoded state.
- It's the **same decoupling as `GOTO`**, generalized from "name a place" to "name a policy."

**The honest hard parts:** choosing the **state granularity** (too fine → never reuses; too coarse →
wrong action) and the **novelty detector** (when must the brain wake?). Usefully, the existing
`OutcomeMemory`/disconfirm machinery — which already flags "this action did nothing here" — is *most
of* a novelty detector.

---

## 7. The learning-boundary law: where every kind of learning is allowed to live

The organizing constraint that makes "learning" safe and the generalization claim honest:

- **Across-run learning = harness/code updates ONLY.** The agent starts **blank every run** (archive +
  wipe aria's memory before each). The only way knowledge crosses runs is a developer changing the
  harness — perception, brains, detectors, or a *promoted* policy compiled into code.
- **Within-run learning lives in the harness** and is **discarded at run end**: the `LESSON:` buffer
  (English takeaways the LLM authors, re-injected each wake this run), `OutcomeMemory`, the disconfirm
  detector. aria *authors* lessons; the harness *stores + re-injects* them — never aria's persistent
  `lessons.md` (that would bleed across runs and break the law).
- The skill-compilation policy of §6 slots **exactly** here: a learned battle policy is **within-run**,
  harness-owned, discarded at run end → law-compliant. The proven, general parts get **promoted into
  harness code** across runs. **Two timescales, both already in the design.** The `LESSON:` buffer is
  the seed of within-run learning; the learned policy is its powerful evolution (English takeaways →
  executable strategy).

---

## 8. Specific perception techniques worth remembering

- **Decode the state; don't make the LLM read pixels.** The single most reused move (navigation,
  textbox, move menu). The seam lets the agent stay constant while the decode improves.
- **OCR for a fixed tile font: exact bitmap-matching is *optimal*, not a compromise.** A calibrated
  glyph matches 100%; off-the-shelf OCR (Tesseract) is *worse* on 8px glyphs. The `?`s are *missing*
  glyphs (coverage), not flaky matches. The genuine instability was a **Hamming-distance fallback
  misreading uncalibrated glyphs as confident wrong characters** (Squirtle's `Q` → `O`); exact-only
  yields an honest `?`. Complete the table **robustly** by auto-calibrating from *self-verified known
  strings* (match a word at any offset, accept only where ≥2 already-known cells agree — so
  misalignment can't corrupt the table). No ROM.
- **Transition detection = ego-motion vs scene-cut.** Within a map, frame N+1 is frame N *translated*
  (the camera scrolls); a warp aligns under *no* shift. This `best_shift` test is more robust than
  frame-diff magnitude, **catches interior stairs** (which a fade misses), and yields true odometry as
  a bonus. A fade (near-uniform frame) is a complementary backstop for the post-menu case translation
  can't see.
- **Topological place-graph beats dead-reckoned coordinates.** Persistent places + direction-
  independent door edges; a round-trip *restores* a known place instead of minting a new one →
  no map-lumping, no doorway ping-pong.

---

## 9. Methodology — the honest process insights (these cost us time/money)

- **Validate the closed loop, not just the primitives.** Unit tests passing ≠ the agent works. The
  free closed-loop autopilot run caught two bugs every unit test passed (an odometry change that broke
  the controller's motion contract; a door ping-pong). *Test the loop, not just the pieces.*
- **Verify-before-claiming applies to your *own* analysis, not just the agent's.** We over-claimed a
  "win" (a 1-step RAM-read glitch) and "move-selection fixed" (a lucky highlighted-move streak), both
  corrected by reading the per-step truth + the actual reasoning text. A single-frame oracle blip and a
  word-count both lied.
- **Read the actual error, not the symptom.** A run that 400'd ~45 wakes in looked like a "context
  ceiling"; the litellm log said *"credit balance too low."* A wake-count correlation is not a root
  cause.
- **Data-first: look at the data before coding the rule.** Repeatedly decisive — brightness can't
  separate battle sub-states (→ a temporal settle); the fade-vs-translation measurement; measuring the
  move-menu layout before writing the decoder.
- **Run paid jobs unbuffered (`python -u`)** so a crash leaves a traceback instead of vanishing with
  the buffer.
- **External dependencies bite quietly:** aria's Anthropic credits ran dry mid-run more than once;
  `ARIA_DATA_DIR` must point at the seeded dir or the agent runs subtly wrong. Probe before spending.

---

## 10. The arc, compressed

Perception (geometry) → the door-seam/portal fix → scripted gates/menus → **navigation rebuilt**
(translation + place-graph) → **fighting**: and within fighting, the bottleneck moved *cleanly* from
**confabulation** (weak vision, fixed by decoding state) → **move execution** (couldn't read the
cursor, fixed by decoding the move menu) → a **win**. Each step was the same move: **decode the state,
keep the agent constant, wake the expensive model only when it must decide** — and the next frontier
is making *"when it must decide"* something the agent *learns*, not something we hardcode.
