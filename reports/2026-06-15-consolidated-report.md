# Consolidated report — a simple, generalizable agent, probed on Pokémon Red (2026-06-15)

**Thesis:** the agent's hard part is **perception**, not planning; and the way to make it
**cheap** and **generalizable** is to factor the world behind a small, role-named belief state and
take routine action off the expensive brain. Three iterations on Pokémon Red turned that thesis
into running, measured code. This report is the cross-iteration synthesis; the running detail lives
in [`LEARNINGS.md`](LEARNINGS.md), per-iteration write-ups in the dated reports beside it.

---

## 1. What we're actually building (north star)

Not "beat Pokémon." Pokémon Red is the **first probe world** for: *an agent that iteratively
improves and generalizes across games — and eventually reality.* The brain (**ai-aria**, repurposed
into the game agent "Red") is **fully decoupled** from the world (**ai-pokemon-red** harness); they
speak only HTTP. Three constraints are held deliberately, because they're what make the result
transfer:

- **Generalize** — find the *smallest* increments that let the *same* agent act in a *different*
  world. Avoid Pokémon-specific hacks.
- **No ROM / privileged state** — rely on the **screen**, the one thing every world offers. RAM
  won't exist in a new game or in reality, so it's demoted to a crutch / scoring oracle only.
- **Cheap** — minimize API calls and tokens. Prefer local / off-the-shelf compute; wake an
  expensive brain only when genuinely needed.

## 2. Headline results

| Question | Result | Where |
|---|---|---|
| Can a small VLM play from raw pixels? | No — confabulates geography, invents NPCs, writes false "I left the lab" to memory | Iter 01 |
| Does a perception seam fix the core failure? | **Yes — it leaves the bedroom** (the thing baseline never did), planning on a pixels-derived state with **no RAM input** | Iter 02 |
| Can routine play be free? | **Yes — a local autopilot explored 3 maps / 44 cells for $0**, where baseline burned ~100 LLM calls stuck in one room | Iter 03 |
| Is the pixel state accurate? | **Walkability 99.3%** vs the RAM oracle (after tuning); **mode overworld-vs-non-overworld 97.7%** on real frames incl. a real battle (8/8) | Iter 03 |
| Can it avoid infinite loops? | **Yes by construction** — visited-map + frontiers autopilot is loop-free; a watchdog bounds the LLM; an outcome-memory marks dead actions | Iter 03 |
| Cost so far | **~7 SEK (~$0.66)** of API across the whole project (self-reported session telemetry, not repo-reproducible); all perception/autopilot/measurement work is $0 | Iter 03 |
| Tests | **57 passing**, no ROM / no PyBoy required (fake emulator + synthetic frames) | all |

Honest blocker: live LLM-in-the-loop validation (battle *decision-making*, the planner choosing a
`goto` target end-to-end, a full Brock slice) waits on Anthropic credits. Every seam for it is built
and unit-tested for $0; what's gated is exercising it with a paid brain.

## 3. The architecture that emerged

The whole framework is **one small loop**, and each iteration filled in one piece of it:

```
perceive → recall → decide → act → observe outcome → learn → forget
```

- **perceive** — `core/perception.py` defines the seam: `perceive(frame, memory) → SymbolicState`.
  The planner sees a **role-named belief state**, never RAM. Roles: `pose` (where am I),
  `spatial_memory` (what I've mapped), `affordances` (what I can do here), `last_action` (did it
  work), `confidence`, `context` (what kind of screen). The Pokémon-specific reader
  (`games/pokemon_red/perceiver.py`) hides tile details *behind* those roles — a 3D game or reality
  slots in under the same names.
- **decide / act** — split across two brains by cost (`core/brains.py`): a **free local autopilot**
  (`ExploreBrain`: frontier exploration + BFS shortest-path on the unweighted occupancy grid) does
  routine traversal, and
  an **expensive LLM** (`LLMButtonBrain`, talking to decoupled aria) is **woken only at decisions**
  by the router (`HybridBrain`) — when perception reports a non-overworld `context`, or the
  autopilot is stuck.
- **observe outcome → learn** — `core/outcome.py` (`OutcomeMemory`): per `(situation, action)`,
  record whether the action had an **observable effect**; repeated no-effects mark an action "dead"
  and it's surfaced to the planner ("these did nothing here, don't repeat"). This is the agent-
  agnostic seed of *learn-from-mistakes / retry*.
- **the oracle** — RAM is read *only* into a side-log (`oracle.jsonl`) for **scoring**, never into
  the agent's input. The no-leak rule is **structural**: the perceiver is handed pixels and has no
  access to RAM.

Decoupling is real: aria is a separate bearer-authed service; the harness imports none of its code
and talks to it over `/v1/chat/completions`. Swapping the world (a different game, a desktop) means
writing a new plugin + perceiver behind the same contract — the brain is untouched.

## 4. Iteration by iteration

**Iter 01 — baseline (small LLM on raw 160×144 pixels).** Stood up the decoupled stack; ran Haiku on
native frames. It followed the THINK/MOVE contract 100% and reasoned fine over *RAM-grounded* facts —
but everything read from **pixels was confabulated**: it labeled the bedroom "Oak's Lab," invented
NPCs from furniture, and wrote a fabricated *"Lab successfully exited via stairs"* into long-term
memory while never leaving the room. **Finding: perception is the bottleneck, not planning — and a
faithful memory system *amplifies* bad perception** (it immortalizes the hallucination).

**Iter 02 — the perception module.** Built the `SymbolicState` seam and demoted RAM to the oracle,
then added **odometry + an occupancy map**: a frame-diff answers "did my move change the screen?"
and dead-reckoning remembers visited cells, walls, and frontiers. *Odometry* = estimating your
position from your own motion (each move that actually happened advances an (x,y) cursor), the way a
robot dead-reckons from wheel ticks. **Result: it left the bedroom** (map 38→37) — baseline's
signature failure — planning on the symbolic state. **A near-vision-free signal (frame-diff + a
remembered map) is enough to *not loop*; you don't need to *recognize* tiles to navigate.**

**Iter 03 — measure it, make it cheap, make it loop-safe.**
- **Measurement rig (free):** `eval/score_perception.py` scores perception against the oracle with a
  *scripted* brain — **no API**. Walkability **100%** single-tile, **99.3%** after threshold tuning.
- **Free autopilot + event-driven hybrid:** the cost win — **take routine movement off the LLM.**
  The autopilot is inherently loop-free; `play_loop.py` adds a **progress watchdog** (halts when no
  real progress for N steps — *makes mistakes but never infinite-loops*) and a **budget guard** (cap
  LLM calls).
- **Mode detection (free, from looking at the data):** `detect_mode()` separates
  overworld/menu/dialog/battle. The signal is trivial once you *look*: **Gen-1 UI panels are
  pure-white (≥230) and the game world almost never is**, so a near-white-by-region check routes
  modes for ~free on CPU. Non-overworld auto-wakes the LLM.
- **Outcome loop (feature #1, free):** `OutcomeMemory`, above — the learning spine, world-agnostic.
- **goto(target) (feature #2, free, now whole):** the autopilot BFS-pathfinds to a *named* cell, and the
  **planner→target hookup** is built and unit-tested: a woken LLM may emit `GOTO: x y`; `HybridBrain`
  persists it and the free autopilot drives there over subsequent steps, clearing it on arrival.
  This is the `decide→act` split in miniature: expensive brain sets intent, cheap controller
  executes. (A *live* LLM choosing the target is the credit-gated piece.)
- **Mode detection — validated on real pixels (this session, free):** `eval/capture_modes.py`
  scripts the gated opening (bedroom → Pallet → Oak cutscene → lab → **pick Charmander** → **rival
  battle**) using RAM purely as a navigation aid + oracle, to finally produce the real battle/dialog
  frames the autopilot can't reach. **Real battle 8/8 → `battle`; overworld (RAM-confirmed moves)
  76/78; headline overworld-vs-non-overworld 84/86 = 97.7%.** Looking at the frames also *found a
  bug*: a full-screen **white/black fade-flash** tripped the "bright top AND bottom ⇒ battle" prior.
  Measured signature — fades have **std 0.0**, real battles **std > 65** (battles are *mostly white
  too*, so "white ⇒ not battle" would be wrong) — fixed with a near-uniform-frame guard.

## 5. The transferable principles (what survives leaving Pokémon)

1. **Perception is the generalization bottleneck.** Good state → the planner is fine; the leverage is
   in `screen → state`, not in a bigger brain.
2. **Faithful memory amplifies bad perception.** Don't record a belief the observation can't support
   — the outcome loop and the no-leak oracle are both instances of this discipline.
3. **Role-named state generalizes; representations don't.** `pose / spatial_memory / affordances /
   last_action / confidence` is a robot's belief state. The tile grid is just *this world's*
   representation behind those roles.
4. **Take routine action off the expensive brain.** Most steps are mechanical; a free local
   controller handles them and the LLM is woken only at genuine decisions. This is simultaneously the
   cost win and the anti-loop guarantee.
5. **Look at the data before coding the rule.** Both the mode detector (pure-white panels) and its
   fix (std-0 fades) came from *inspecting real frames*, not from a model. Overlay/UI-vs-world and
   transition-vs-state each separated on one cheap invariant — find it and you skip the ML.
6. **A free, RAM-grounded oracle lets you make honest claims.** Every accuracy number here is scored
   against ground truth the agent never sees — including, this session, scripting *into a real
   battle* to validate detectors the autopilot structurally cannot reach.

## 6. Honest limitations & what's gated

- **Odometry drifts** under multi-tile moves (~1.7 real tiles per logged move) and **resets at area
  changes** — fine for "don't loop / head to unexplored," not a metric map. The oracle measures the
  drift; fade-based transition detection is the proper future signal.
- **Mode sub-labels are approximate.** Full-screen bright menus (the naming keyboard) still read
  `battle`; region-white can't separate them from a battle. Harmless for the *wake* decision (both
  non-overworld); firming up battle-vs-menu needs structural HP-bar/sprite detection — deferred.
- **The known leak (deferred):** the planner's pretraining already knows Pokémon Red ("Oak's Lab,"
  the type chart). Success may be *recall*, not generalization. The honest control is a reskinned /
  obscure world (the **gating probe**) — designed, not yet run.
- **Credit-gated:** battle *decision-making*, the live `goto` target selection, and the end-to-end
  Brock slice need a funded brain. Built and $0-tested; not yet exercised live.

## 7. How close to "point it at a new world"?

Closer than Iteration 01, with the boundary now explicit. **World-agnostic and done:** the loop
(`core/perception.py`, `core/brains.py`, `core/outcome.py`), the role-named schema, the
wake-on-decision router, the oracle discipline. **What a second world would force** (and this is the
*point* — let a real second environment drive the abstraction rather than guessing it now): a
non-grid `pose`/`spatial_memory` representation (metric pose or a place-graph), a perception path
that isn't "pure-white panels," and a real test of whether means-ends reasoning (the gating probe)
transfers without the memorized Pokémon prior. The bet the schema makes is that those swaps happen
*behind the roles* and the brain doesn't change.

## 8. Next increments (by leverage × cheapness × generality)

1. **Run the gating probe** in a reskinned world — separate reasoning from Pokémon recall (the
   highest-value generalization test; mostly free).
2. **Live the credit-gated slice:** LLM sets a `goto`, handles the first battle, clears (or
   honestly fails) Brock via `play_loop.py`. Small spend, validates the whole loop end-to-end.
3. **Port the outcome loop into ai-aria** as the agnostic "act → observe → learn" spine it currently
   lacks (it's a conversation/memory system; this is the missing motor loop).
4. **Second probe world** (an obscure/custom tile game) to force the `pose`/`spatial_memory`
   abstraction and retire the recall-leak caveat.

## Appendix — file map & repro

- Loop: `core/perception.py`, `core/brains.py` (`ExploreBrain` / `HybridBrain` / `LLMButtonBrain`),
  `core/outcome.py`.
- World: `games/pokemon_red/{plugin,perceiver,emulator,memory_map,reward}.py`.
- Measurement (all $0): `eval/score_perception.py` (perception vs oracle),
  `eval/tune_threshold.py` (threshold tuning), `eval/capture_modes.py` (real battle/dialog capture +
  detector scorecard).
- Drivers: `play_pokemon.py` (single run; `--brain explore|hybrid --perception`, `--sound`,
  `--watch-delay`), `play_loop.py` (loop-safe iterative play with watchdog + budget guard).
- Watch it play (free, local, real-time + sound):
  `uv run python play_pokemon.py --rom roms/PokemonRed.gb --brain explore --perception
  --load-state start.state --steps 100 --sound --watch-delay 90`.
- Score the detectors against the oracle (free): `uv run python -m eval.capture_modes`.
- Tests: `uv run pytest -q` (57 passing, no ROM needed).
