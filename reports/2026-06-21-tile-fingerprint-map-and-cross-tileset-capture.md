# 2026-06-21 — Tile-fingerprint `tile→function` map + cross-tileset data capture

**Type:** free work (no paid LLM run) — build + offline validation + data capture. All on branch
`feat/novelty-signal` (pushed). 269 tests pass.

## Goal
Execute the converged perception decision (`reports/2026-06-21-perception-architecture-decision.md`):
give the agent an **online, behaviour-labelled `tile→function` world model keyed by a cheap perceptual
hash** (NOT a CLIP embedding) so a tile-type learned once is recognised wherever it recurs — the
"don't walk every cell" speedup — and a novelty signal for unseen tiles. Then close the **cross-tileset
DATA GAP** (we only had ~5 early maps that *share* a tileset) so the hash-vs-CLIP question can be tested
honestly on genuinely new tilesets.

## Method
- **Build (task #7, map + novelty only — no autopilot change, no paid run):**
  - `core/tilemap.py` — world-agnostic `TileFunctionMap`: a 64-bit **dHash** fingerprint (grayscale →
    8×8 average-pool → wrap-around column gradient), behaviour-labelled `observe`/`predict` with
    confidence, Hamming-tolerant recurrence (default tol=6), and `is_novel`. numpy-only, deterministic,
    CI-testable.
  - Wired into `games/pokemon_red/perceiver.py`: **OBSERVE** the faced tile each move (walk→walkable,
    bump→blocked, cropped from the clean PRE-move frame at screen cell (4,4)+dir), and **SURFACE**
    advisory `tile_predictions` / `novel_tiles` / `tile_types_seen` as **additive `spatial_memory` keys**
    (the frozen `core/contracts.py` is untouched).
- **Validate (free, deterministic):**
  - `eval/probe_tilemap.py` (numpy+PIL, **no torch/CLIP**) — leave-one-map-out + temporal + tolerance
    sweep on recorded oracles.
  - `eval/replay_tilemap.py` — drives the **real wired `perceive()`** over a recorded run (vs the probe,
    which tests the algorithm on re-cropped tiles) and checks the advisory against later-confirmed behaviour.
- **Capture data:** built `play_record.py` (guided windowed play + `Tab` autopilot toggle, WASD keys,
  `C` checkpoints), `eval/auto_race.py` (headless free auto-player), `eval/index_runs.py` (catalog →
  `runs/INDEX.md`). Ran a guided session + a 3-way auto-explore race.

## Results
**The hash beats CLIP exactly where CLIP collapsed** (`probe_tilemap`, behaviour ground truth):
- **Leave-one-MAP-out, held-out lab: 81% coverage @ 84% accuracy** vs the CLIP store's **26.9%**
  (below its 74.8% majority baseline). Gen-1 indoor maps share a literal tileset, so the hash recognises
  tile *identity* where CLIP's lossy embedding blurred lab-floor toward house-walls.
- **Temporal recurrence: 99.7% coverage / 92.6% accuracy-when-known.**
- **Tolerance surprise (Q7):** accuracy is **flat ~92.5% across tol 0..12** — the residual ~7% is
  **intrinsic tile/function ambiguity** (the same pixels seen both walkable and blocked), NOT hash
  collisions. ⇒ appearance alone can't perfectly determine function even within one tileset; the
  behavioural veto (a real bump overrides) and scene-conditioning (Q2) are the levers.

**Wired end-to-end** (`replay_tilemap` on `runs/fix4`, 741 overworld frames):
- **Recurrence curve is textbook:** `novel_tiles` fall **22.4 → 0.5 / frame** while `tile_predictions`
  rise **45 → 52 / frame** as the agent learns the room. 90 tile-types learned.
- **Advisory vs later-confirmed behaviour: 81.2% on clean ADJACENT (faced) cells, but 61.3% across ALL
  visible cells.** The gap is honest: `_predict_visible` fingerprints *every* visible cell using the
  camera-centred player=(4,4) assumption, so peripheral/edge crops are noisier and near map borders
  (player off-centre) the screen→world cell mapping is wrong. ⇒ for the task-#8 autopilot use, trust
  predictions *ahead / near* the player, detect off-centre frames, keep the veto. (This is the Q6
  robustness item, now quantified live.)

**Cross-tileset data captured (the gap, now opening):**
- `runs/kanto1` (guided): **1303 steps, 15 maps** — Pallet, Viridian City + its buildings (41–44, 47),
  Route 1 (12), Route 2 (13), and **Viridian Forest (51, ~204 steps) = a genuinely new tileset**;
  1145 manual / 160 auto; a trainer battle reached; `checkpoint_01.state` saved.
- 3-way auto-race (seeds 1/2/3, identical dumb policy): **race1 trapped** in the start cluster
  (maps 0/37/38/40, 70 tile-types); **race2 & race3 escaped** to Route 1 + Viridian (131 / 177 tile-types).
  Same policy, different fates — the seed divergence worked, and race2/3 generated more Route 1/Viridian data.

## Why it matters
The decisive earlier finding was *CLIP captures appearance, not function*. This session confirms the
flip side empirically: a **deterministic exact-structure hash is strictly better** for the one thing that
works (recurrence) — free, no torch, CI-testable — and it honestly says "novel → explore" instead of
confidently mispredicting. The cheap path wasn't a compromise; it was the correct tool.

## Caveats (honest)
- **Advisory is noisier than the clean faced-tile recognition** (61% all-cells) due to the (4,4)
  assumption at map borders — advisory-only + behavioural veto is why this is safe; task #8 must respect it.
- **Data is still early-game-weighted.** kanto1 adds Viridian Forest but stops short of Pewter/Mt Moon/
  caves. The cross-map leave-out "win" so far still partly rides shared indoor tilesets.
- **Oracle quirks:** the race index showed transient `badges=1` / `battle=?` — RAM misreads on
  fade/transition frames (the index takes a max), not real progress. Auto-explore cannot beat gyms.

## Next
- **Task #9** — re-run leave-one-MAP-out on the NEW tilesets (Route 1/2, Viridian Forest) + David's
  **overlap-window CLIP** + the **hash⊕CLIP hybrid** (BM25-style sparse+dense): does the hash's recurrence
  win HOLD off the shared early tiles? (`.venv-probe4` for the CLIP arm.)
- **Task #8** — the navigation-speedup A/B (use predictions in the autopilot to skip appearance-known
  walls; replay/live), respecting the "trust-ahead + veto" rule from the wired-replay finding.
- More capture toward Pewter/Mt Moon for richer tilesets.

<!-- Free work, no paid run -> no oracle battle-scorecard. Numbers above are from eval/probe_tilemap.py
     + eval/replay_tilemap.py against recorded oracles; commits 016ca79..2368a7c on feat/novelty-signal. -->
