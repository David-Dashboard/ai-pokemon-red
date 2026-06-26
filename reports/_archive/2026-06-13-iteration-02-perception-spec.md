# Iteration 02 — Spec: the perception module (`screen → symbolic_state`)

**Status:** DRAFT for review. No code yet — this is the contract + the self-calibration probe list,
so we can check it holds together before building. Goal: one seam behind which the Phase-1 (template),
Phase-2 (detector), and baseline (VLM) parsers are all drop-in, scored identically by a RAM oracle.

Ties to [iteration 01](2026-06-13-iteration-01.md): Iteration 01 found **perception is the
bottleneck**. This spec inserts an explicit perception stage and demotes RAM to an oracle.

---

## 0. Where it slots in (minimal architectural insertion)
- **Today:** `plugin.observe()` builds `Observation.data` from **RAM** (`memory_map.read_state`) and
  attaches the screenshot path; the brain (aria/Haiku) plans over the *image*.
- **Iteration 02:** build `Observation.data` from a **pixel perceiver** instead. RAM is no longer an
  agent input — it moves to a logged **oracle** (a side Event) used only for scoring.
- The brain plans over `symbolic_state` (compact text), ideally **without the image** — which
  collapses API cost and removes the hallucination source.
- The perceiver lives on the **world/harness side** (world-specific pixel reading). aria stays
  world-agnostic — same decoupling we already have. `SymbolicState` simply becomes the new
  `Observation.data`; it's a swap-in for the RAM reader behind the existing contract.

## 1. The contract
```
perceive(frame, percept_memory) -> SymbolicState
```
- `frame` — the screenshot (pixels only). **No RAM.**
- `percept_memory` — the perceiver's own persisted state (calibration + learned caches). Internal.
- Pure-ish function of pixels + its own memory. Deterministic where possible.

### SymbolicState (ROLE-NAMED — generalizes across games → reality)
Names describe *roles* (a robot's belief state); tile-game specifics live **behind** each role,
so a 3D game or reality slots in under the same names. Implemented in `core/perception.py`.
```
confidence:     0..1                       # low ⇒ attach the raw frame + TELL the planner
context:        <situation label>          # observed, NOT a fixed game-mode enum
pose:           {frame, value, uncertain}  # WHERE am I (estimated). tile game: frame="grid", value=[x,y]
spatial_memory: {kind, ...}                # WHAT I've mapped. tile game: kind="occupancy-grid"
affordances:    [ ... ]                    # where/what I can act from here (frontiers, options)
last_action:    {action, outcome}          # did my last action change anything (from frame-diff)
raw_available:  bool                       # a richer observation (the image) can be attached
raw_ref:        str                        # handle/path to that raw observation, when present
# Tile-game detail (grid cells, entities, text boxes) lives UNDER pose / spatial_memory /
# affordances — not as top-level fields. NO RAM-derived fields: "did I move / hit a wall" comes
# from pixels (frame-diff). See §9 for the role-vs-representation rationale and the earned-not-
# -designed caution.
```
`mode` tells the planner which structural world it's in. `self` (self-location) is a **required**
Phase-1 output, as is `mode` — the agent must always know *where* it is and *what kind of screen*
it's on.

### Planner-input policy (RESOLVED)
- **Default: symbolic text only** (cheap; can use a small text model; no vision).
- **On low `confidence`:** also attach the **raw screenshot**, AND surface an explicit line in the
  prompt — e.g. `PERCEPTION CONFIDENCE: LOW — an image is attached; trust it over the description
  below`. The planner must be *told* it's low-confidence, not left to infer it.
- Attaching the screenshot is **not a leak** — the screen is a legitimate observation. (Leak = RAM.)
- **Earn text-only:** keep the image-fallback until the oracle (§4) shows perception accuracy high
  enough to drop it; don't assume it.

## 2. Self-calibration probes (cheap, CPU, self-gating)
**Principle: the probe succeeding IS the decision.** No "what genre is this" classifier — a non-tile
screen simply fails the grid probe and the parser falls through.

1. **Quantization probe** *(informational)* — unique-color count + blockiness → "low-res quantized
   source." Sanity flag only.
2. **Grid probe** — autocorrelation / FFT / edge-projection on a frame → dominant spatial period →
   `tile_px` + grid origin/size. Succeeds ⇒ grid available; fails ⇒ no grid (battle/menu/non-tile).
3. **Avatar probe** — in camera-follow games the avatar is the sprite that stays put while the
   background scrolls. Detect by invariance under movement / center position. → `self`.
4. **Entity probe** — foreground sprites = regions not in the background tile dictionary, or that move
   independently (background-subtraction across frames). → `entities`.
5. **Text-region probe** — scan for font-glyph statistics; maintain a **recurring-text heatmap** →
   stable text regions (dialogue box, HP). GB uses a **fixed bitmap font**, so "OCR" is glyph
   template-matching: CPU, exact, no engine, no training.
6. **Mode probe** *(self-gating router between sub-parsers)* — grid+avatar ⇒ overworld; no grid +
   dominant text box + HP-bars ⇒ battle; cursor+rows layout ⇒ menu; full-width text, no grid motion ⇒
   dialog. Each is a cheap structural test, re-validated every frame.

## 3. The learning loop ("over time" — no API, no ROM)
1. **Tile dictionary builds itself** — hash distinct `tile_px` cells → cluster → `type_id`. Persisted.
2. **Tile semantics from experience, not a model** — per `type_id`, tally outcomes of moving toward it
   via `hints.changed_since_last` / `self.cell` delta: unchanged ⇒ obstacle; moved ⇒ walkable;
   map/screen changed ⇒ warp/door; battle-triggered ⇒ encounter tile (grass). **Zero API, zero ROM.**
3. **Sparse model fallback** — only for a novel `type_id` whose meaning can't be inferred from behavior
   *and* that matters: ask a VLM/LLM **once** ("what is this tile/sprite?"), then **cache forever**.
4. Caches persist across runs → the agent literally **learns the game**; API spend **decays toward
   zero** after warmup.

## 3a. Spatial memory (per-area occupancy map) — simplest useful form
Fixes the Iteration-01 disease (looping in one room, re-deciding from scratch each turn).
- **Coordinate-indexed local map per area.** No absolute coords (no RAM), so track position by
  **dead-reckoning**: start at (0,0); each move that *actually happened* (`hints.changed_since_last`)
  advances an (x,y) cursor in the moved direction.
- **Each cell stores:** last-seen tile `type_id`, `walkable?` (learned from bumps), `visited?`, and
  `frontier?` (walkable AND adjacent to unknown ⇒ worth exploring).
- **New area** on a detected transition (big frame change / warp tile) → start a fresh local map;
  remember linked areas.
- **Rendered into `symbolic_state`** as a compact local map + the list of frontiers, so the planner
  sees *"west & north explored; only unvisited exit is the SE stairs"* instead of guessing each turn.
- Lives in `percept_memory` (harness side), not in aria's narrative memory.
- **Honest limits:** dead-reckoning **drifts** over long runs and **resets** at area changes — fine
  for "don't loop / head to unexplored." The oracle gives a free **drift metric** (dead-reckoned vs
  RAM `(x,y)`).
- *Absolute-minimal fallback if needed:* a visited-set + last-K-positions trail (no map) to kill the
  tightest loops.

## 4. RAM as oracle (scoring — never an input)
A separate eval path reads RAM (`map_id, x, y, in_battle, party…`), never fed to the agent, and scores
the perceiver each run:
- **position** — perceived `self.cell` / movement vs RAM `(x,y)` deltas.
- **walkability** — perceived `walkable` vs whether RAM `(x,y)` actually changed.
- **mode** — perceived `mode` vs RAM `in_battle`.
- **entities / text** where checkable.
→ a single **perception-accuracy score**. This is how we *earn trust in pixels*, A/B the parsers, and
(Phase 2) **auto-label frames for training without a human**.

## 5. Modes & re-calibration
Calibration (grid size, text regions, tile dict) **persists**; only the **mode** switches per frame.
Each frame cheaply re-validates the active mode's preconditions; on failure, re-run the mode probe and
swap sub-parser (overworld ↔ battle ↔ menu ↔ dialog). Also self-gating — no classifier.

## 6. Pluggable parsers behind the seam
| Parser | Phase | Compute | Training |
|--------|-------|---------|----------|
| **TemplateParser** | 1 (build first) | **CPU** | none |
| **DetectorParser** (YOLO-nano + classifier) | 2 (generality) | CPU inference; GPU one-off fine-tune | auto-labeled via the §4 oracle |
| **VLMParser** (small local VLM) | baseline/control | CPU-ish / small GPU | none |
The planner is unchanged across all three; the oracle scores all three identically → clean A/B.

## 7. Success criteria for Iteration 02
- TemplateParser's position/walkability/mode match the RAM oracle **≥ 95%** over the
  bedroom → Pallet → Route-1 stretch.
- Planner runs on `symbolic_state` **text-only (no image)** and **reliably leaves the house** (the
  Iteration-01 failure) across N seeds + a fresh data dir each run.
- API calls/step **drop** (perception is local; planner vision optional/fallback only).
- The learning loop is demonstrated: tile semantics fill from experience; novel-tile model queries →
  ~0 after warmup.

## 8. Decisions (resolved) + remaining
**Resolved:**
1. **Planner input** → symbolic-text-only by default; **image + explicit "LOW confidence" flag** on
   low confidence; earn text-only via the oracle (§1).
2. **Self-location + mode** → **required** Phase-1 outputs (always know where + what screen).
3. **Schema** → **minimal but stable**: only the fields Phase 1 fills, named generally so we can grow
   it without breaking the planner.
4. **Build order (Phase 1)** → grid + walkability + occupancy map first (gets it out of the house),
   text/font-match second.
5. **Spatial memory** → per-area coordinate-indexed occupancy map, dead-reckoned (§3a).

**Remaining:**
- **Self-location off the overworld:** battle/menu have no camera-follow avatar — confirm frame-diff +
  structural layout is enough, or give those modes their own minimal state.
- **`percept_memory` persistence:** format + location (harness data dir, per-game).

## 9. Known leak, deferred (experimental-validity note)
There is a real leak we are **choosing to defer**: the planner's **pretraining already knows Pokémon
Red** (maps, type chart, "Oak's Lab"), so success may be *recall*, not generalization — and indeed in
Iteration 01 it "knew" to head for Oak's lab / a starter without seeing it. This contaminates the
generalization claim. Future controls (out of scope now): evaluate on a game the model can't have
memorized (obscure/custom), or **reskin/scramble** Pokémon (swap tiles/names) so memorized priors
don't help. Logged here so we don't forget it when we make generalization claims.
