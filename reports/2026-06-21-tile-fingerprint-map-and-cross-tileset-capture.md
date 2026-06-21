# 2026-06-21 — Tile-fingerprint `tile→function` map + cross-tileset data capture

**Type:** free work (no paid LLM run) — build + offline validation + data capture. All on branch
`feat/novelty-signal` (pushed). 269 tests pass.

## ⚠ VERIFICATION UPDATE — headline CORRECTED (5-agent adversarial workflow, reproduced)
The cross-tileset claim in §Results was **overturned** by adversarial verification (`eval/_verify_tileset.py`,
independently reproduced). **Leave-one-MAP-out ≠ leave-one-TILESET-out:** a held-out *indoor* map kept a
sibling indoor map in the store, which HID a failure. Under the honest **leave-one-TILESET-out** (hold ALL
maps of a tileset; no sibling in store):

| held-out tileset | coverage | acc | **wall-recall** | reading |
|---|---|---|---|---|
| town (0,1) | 89.2% | 97.2% | **84.7%** | survives |
| route (12,13) | 81.1% | 95.5% | **99.5%** | survives |
| **indoor (37,38,39,40,41)** | 69.4% | 80.7% | **0.0%** | **449/449 walls miscalled WALKABLE @ conf 0.94** |
| forest (51) | 3.3% | 100% | n/a | correctly NOVEL, but all-walkable so acc vacuous |

**So the hash DOES confidently mispredict cross-tileset for INDOOR — the exact failure I credited it with
avoiding.** Two meta-lessons: (1) **aggregate accuracy lies for navigation — measure WALL-RECALL** (indoor's
80.7% > 67.2% baseline hid a 0% wall-recall because indoor is ~70% walkable); (2) **hold out the whole
TILESET, not one map.** Root cause = an **all-zeros dHash ALIAS** (flat/low-contrast tiles all hash to 0 →
82% of the indoor miscalls, 369 exact collisions to outdoor-walkable tiles). Confounds *cleared*: the (4,4)
edge-crop is negligible (0.5% mis-crop — interiors pin the player centre and pad with void), and labels/split
are clean (98.9% RAM-agreement). **Corrected headline: strong RECURRENCE within a tileset + safe NOVELTY on a
new tileset; NO indoor cross-tileset generalisation.** The hash still beats CLIP on the *same* leave-one-MAP-out
protocol (lab 77.7% vs CLIP 26.9%), but neither was tested cross-tileset apples-to-apples. **Revised NEXT below.**

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
The hash owns the **recurrence** win for free (no torch, CI-testable) and beats CLIP on the same
leave-one-MAP-out protocol — that part is real and verified. But the verification (see top) shows the cheap
path is **not** the whole answer: cross-TILESET, the hash confidently mispredicts indoor walls (wall-recall
0.0%) because flat tiles alias to one hash. So the honest takeaway is narrower than "the correct tool": the
hash is the right tool for *recurrence + novelty*, and a *separate* mechanism (a flatness guard / more bits /
or a dense arm) is needed for *cross-tileset wall discrimination*.

## Caveats (honest)
- **Advisory is noisier than the clean faced-tile recognition** (61% all-cells) due to the (4,4)
  assumption at map borders — advisory-only + behavioural veto is why this is safe; task #8 must respect it.
- **Data is still early-game-weighted.** kanto1 adds Viridian Forest but stops short of Pewter/Mt Moon/
  caves. The cross-map leave-out "win" so far still partly rides shared indoor tilesets.
- **Oracle quirks:** the race index showed transient `badges=1` / `battle=?` — RAM misreads on
  fade/transition frames (the index takes a max), not real progress. Auto-explore cannot beat gyms.

## Next (revised after verification)
The CLIP arm is now SCOPED to the one place the hash measurably fails — cross-tileset wall discrimination —
and gated behind cheaper fixes that may close most of the gap:
1. **Cheap fix first (free, no torch):** (a) a **flatness/void guard** so near-uniform crops read
   novel/low-confidence instead of confidently-walkable (the all-zeros alias is 82% of the indoor miscalls);
   (b) a **more discriminative hash** (e.g. add quantized-intensity bits) to break the 369 cross-tileset
   collisions. Re-measure **indoor wall-recall** on leave-one-TILESET-out (`eval/_verify_tileset.py`).
2. **CLIP arm only if (1) falls short** — David's overlap-window CLIP + hash⊕CLIP hybrid (BM25-style
   sparse+dense). Bar to justify its torch/sidecar cost: raise indoor wall-recall to ≥~50% (ideally toward
   town's 84.7%) WITHOUT hurting town/route wall-recall or the recurrence coverage, AND preserve safe novelty
   on a genuinely-new tileset (don't reintroduce CLIP's confident cross-tileset mispredict).
3. **Task #8** (nav-speedup A/B) — must use wall-recall-safe predictions; the veto stays authoritative.
4. **More data** — only ONE clean new tileset (Forest) exists and it's all-walkable; capture toward
   Pewter/Mt Moon (a new tileset *with walls*) before calling novelty-safety robust.

<!-- Free work, no paid run -> no oracle battle-scorecard. Numbers above are from eval/probe_tilemap.py
     + eval/replay_tilemap.py against recorded oracles; commits 016ca79..2368a7c on feat/novelty-signal. -->
