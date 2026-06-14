# Learnings log — Red / ai-aria generalization

Running, per-iteration record (newest insights kept; a consolidated final report is assembled from
this at the end). North star: a **simple, generalizable** agent that acts on the world — generalize
across games → reality, no ROM/privileged state, **cheap** (minimal API). Pokémon Red is the probe.

---

## Iteration 01 — baseline: small LLM on raw pixels
- **What:** decoupled aria as the brain (`--backend aria`), repurposed the companion into "Red", ran Haiku on raw 160×144 frames.
- **Result:** stuck in the first room; **confabulated** (invented NPCs from furniture, mislabeled the bedroom "Oak's Lab", and wrote a *fabricated* "I exited the lab" into long-term memory).
- **Learning:** **Perception is the bottleneck, not planning.** Anything from RAM was correct; anything read from pixels was hallucinated — and a *faithful memory system amplifies bad perception* (it immortalizes the hallucination). ⇒ build a perception module; demote RAM to a scoring oracle.

## Iteration 02 — the perception module
- **What:** a role-named `SymbolicState` seam (`perceive(frame) → state`, RAM → non-leaking `oracle.jsonl`); then odometry + an occupancy map (frame-diff "did my move work?" + dead-reckoned visited/walls/frontiers).
- **Result:** **it left the bedroom** (map 38→37) — the thing baseline never did.
- **Learnings:**
  - A near-vision-free signal (frame-diff + a remembered map) is enough to navigate; you don't need to *recognize* tiles to *not loop*.
  - Role-named schema (pose / spatial_memory / affordances / last_action / confidence) = a robot's belief state ⇒ generalizes; tile-specifics hide *behind* the roles.

## Iteration 03 — measure, make it cheap, make it loop-safe
- **Measurement rig (free):** scores perception vs the oracle with a scripted brain — **no API**. Walkability **100%** (single-tile), then **99.3%** after tuning.
- **Free autopilot:** frontier exploration + BFS, **0 LLM calls** — explored **3 maps / 44 cells for $0**, where baseline burned ~100 calls and never left one room. ⇒ **the cost win: take routine movement off the LLM.**
- **Area-detection + oracle-tuned thresholds:** the tuner *honestly* showed diff-magnitude can't perfectly separate map-transitions from big in-map moves (fade-detection is the proper future signal). Odometry undercounts (~1.7 real tiles/move) under multi-tile actions — coords squashed but relative structure holds.
- **Event-driven hybrid + anti-loop:** `HybridBrain` = autopilot by default, wake the LLM only at decisions; `play_loop.py` adds a **progress watchdog** (halts when no real progress for N steps — *makes mistakes but never infinite-loops*) and a **budget guard** (cap LLM calls). The autopilot is inherently loop-free (visited-map + frontiers); the watchdog bounds the LLM.
- **Mode detection (Step 3b, free):** `detect_mode()` (overworld/menu/dialog/battle). *Methodology learning:* **look at the data before coding** — capturing + inspecting real frames revealed a trivial, reliable signal: **Gen-1 UI panels are pure-white (≥230) and the game world almost never is** (overworld ~0% near-white; START-menu panel 66%), so a near-white-by-region check separates modes for ~free on CPU. General principle: *overlay/UI vs world usually separates on one simple invariant — if you find it, you skip the ML.* Non-overworld now auto-wakes the LLM (HybridBrain). overworld/menu confirmed on pixels; battle/dialog are priors.
- **Gating, observed for real:** the autopilot couldn't reach a wild battle because Red **gates Route 1 behind getting the starter** (Oak blocks you). A concrete instance of the dependency/gating problem — the agent literally cannot progress without the menu/dialog capability. (Reinforces the gating-probe as the right test for class-2 reasoning.)
- **Process learnings (the honest ones):**
  - **Config gotcha:** `ARIA_DATA_DIR` must point at `pokemon-red-data` or aria runs without Red's seed (type chart / mission / curiosity goal) — silently wrong.
  - **Memory contamination:** without a fresh data dir, last run's hallucinations poison the next; evals need a clean dir per run.
  - **Spend so far:** ~7 SEK (~$0.66; 339 turns, 569k in / 18k out). Prompt caching never hit (`cached:0`) — a cheap win left on the table.
  - **Blocker (2026-06-14):** the Anthropic key behind aria ran **out of credits** → all LLM calls 400. Free/local work (perception, autopilot, rig) is unaffected.

## Context-agnostic features ai-aria needs (to become the general framework)
The core gap: **aria is a memory+reasoning system built for conversation; it lacks the "act → observe outcome → learn" spine.** Prioritized, agnostic:
1. **Outcome feedback into memory** (action→result; learn from what *happened*, not narration) — also fixes confabulation.
2. **Working/task memory** (live "current goal + what I've tried") — stops looping, enables retry.
3. **Self-managed plan** (agent decomposes & updates its own subgoals).
4. **Observation-grounded belief check** (generalize the disconfirm gate: don't record a world-state your observation contradicts).
5. **Retry/escalation policy** (on failure: try differently → escalate → mark blocked).
6. **Budget-aware acting** (event-driven; being built in the hybrid).
7. **Usefulness-based forgetting** (keep what was referenced / led to success).

The whole framework is one small loop: `perceive → recall → decide → act → observe outcome → learn → forget`. aria has all but the **outcome loop (#1)** — the single highest-leverage agnostic feature.
