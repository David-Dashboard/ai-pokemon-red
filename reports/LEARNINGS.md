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
- **Mode detection — VALIDATED on real pixels (Iteration 03 follow-up, free):** `eval/capture_modes.py` scripts the gated opening (bedroom→1F→Pallet→Oak cutscene→lab→**pick Charmander**→**rival battle**) with a seeded random-walk + A/B mashing, using RAM (`map_id`/`in_battle`/`party_count`) *only* as a navigation aid and scoring oracle — never fed to the perceiver. This finally produced the real battle/dialog frames that were missing, turning the battle/dialog "priors" into measured results:
  - **Real battle frames: 8/8 → `battle`.** Real Oak dialog → `dialog` (eyeballed), real `START` → `menu`.
  - **Overworld (RAM-confirmed moves): 76/78 → `overworld`** (the 2 misses are Pallet frames where the tile moved *and* a sign/cutscene textbox was on screen → read `menu`; waking there is the safe call).
  - **Headline (overworld vs NON-overworld, which is what drives HybridBrain's wake): 84/86 = 97.7%.** This is the property that matters — the exact non-overworld sub-label is secondary.
  - **Bug found + fixed by looking at the pixels:** the structural "bright top AND bottom ⇒ battle" prior also fired on full-screen **white/black fade-flash** frames (an all-white starter-cutscene flash read as `battle`). Measured signature: fades have **std 0.0**, real battles std > 65 (dark sprites/HP-bars/text on the white battlefield — battles are *mostly white too*, so "white ⇒ not battle" would be wrong). Fix: a **near-uniform-frame guard** (std < 6 ⇒ transition ⇒ overworld) — removes the fade false-positives without touching real battles. *Reinforces the Step-3b principle: look at the data before coding the rule.*
  - **Known limitation (honest):** the naming-keyboard / other full-screen bright menus still read as `battle` (std is high, region-white is high — region features can't separate them from battle). Harmless for the wake decision (both are non-overworld); firming up battle-vs-menu needs *structural* detection (HP-bar/sprite templates), deferred.
- **Gating, observed for real:** the autopilot couldn't reach a wild battle because Red **gates Route 1 behind getting the starter** (Oak blocks you). A concrete instance of the dependency/gating problem — the agent literally cannot progress without the menu/dialog capability. (Reinforces the gating-probe as the right test for class-2 reasoning.)
- **Outcome loop (feature #1, free):** `OutcomeMemory` — per (situation, action) record whether the action had an *observable effect*; repeated no-effects mark an action "dead" and it's surfaced to the planner ("these did nothing here, don't repeat"). Generalizes the wall-memory to *any* action; world-agnostic (no game knowledge). The simplest real seed of learn-from-mistakes.
- **goto(target) nav (feature #2, now whole, free):** the autopilot BFS-pathfinds to a *named cell* (reusing its frontier BFS — plain shortest-path on the unweighted grid, not A*), not just the nearest frontier. The **planner→target hookup is now built and unit-tested for $0**: a woken LLM may add a `GOTO: x y` line; `LLMButtonBrain._parse_goto` reads it *only* from that dedicated line (prose like "go to the stairs" is never mistaken for a target); `HybridBrain` **persists** the destination and hands it to the free autopilot on subsequent overworld steps (name a far target *once* → drive there for free, no per-tile LLM calls), then **clears it on arrival** (pose == target). The plugin's symbolic render now lists frontier coords so the planner has concrete cells to name. Proven with a stub planner (3 tests); the only thing still waiting on credits is a *live* LLM choosing the target. *Design note:* goto pathfinds over **visited** cells only, so today it means "go back to a known place / a frontier I can see" — its reach grows the moment perception gains semantic place labels ("the gym"), with no change to this seam. This is the concrete instance of the north-star loop's `decide→act` split: the expensive brain sets intent, the cheap controller executes it.
- **Gating probe — built + free plumbing passing (this session):** a synthetic `GateWorld` (`games/gateworld/`) that isolates **class-2 means-ends reasoning with backtracking** (fetch an item → carry it back → open a gate → reach the goal) and is built to separate **reasoning from recall** — two skins of the identical world (`familiar`: key→door prior; `novel`: fragment→barrier, no prior) under one **neutral prompt**; verdict = the solve-delta. Crucially it runs the **same agent unchanged**: it speaks the GB button contract and emits the same role-named `SymbolicState`, so `HybridBrain(ExploreBrain, reasoner)`, the runner, and the gateway need zero edits. Free result (scripted *oracle* reasoner = plumbing check + upper bound): **both skins solved in 27 decisions, 6 reasoner wakes** (autopilot handled 21/27 free); `test_autopilot_alone_cannot_open_the_gate` confirms exploration alone never opens it, so class-2 reasoning is genuinely required. +10 tests (67 total). The real reasoning-vs-recall measurement (`--brain llm`) is the only credit-gated step. Spec: `reports/2026-06-15-gating-probe-spec.md`.
  - *Fidelity lesson:* a new world must honour the **motion contract** the controller assumes — `ExploreBrain`'s `[d,d]` means "turn, then move" (net 1 tile); a naive move-per-press world made it overshoot and **oscillate forever**. Matching Gen-1 turn-then-move fixed it.
  - *Finding the probe surfaced (generalization TODO):* the outcome loop's `state_signature` is **pose-centric** — picking up the item changes inventory, not pose, so the loop mis-records the `A` press as "no effect" and could mark it "dead" right when it's needed. Friction, not a blocker (the text still says "you picked up the …"), but the effectiveness signal should include inventory/state deltas.
- **Honest blocker still:** LLM-side validation (battle decisions, the live `goto` target, the live Brock slice, and the live gating-probe verdict) waits on Anthropic credits. Everything above is built + unit-tested for $0 and ready.
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
