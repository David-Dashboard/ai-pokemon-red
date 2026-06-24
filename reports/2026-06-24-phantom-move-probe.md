# 2026-06-24 — phantom-move probe: the false-MOVE fix is behavioral, not a perception threshold

Follow-up to the Cave Noire false-MOVE asymmetry (closed-loop: corridor 65/70 perceiver-"moves" phantom).
Measure-first, to decide the fix. **Result: no cheap pixel signal separates a real move from a stuck
attempt on a fixed camera — so the fix belongs at the loop/behavior level, not in the move threshold.**

`eval/probe_phantom_move.py`. RAM is the oracle (label only). Two labeled datasets:
- **corridor** — the closed-loop runaway (`runs/cn_explore_live2`); phantom = perceiver "moved" but RAM still.
- **human-recording** — David's hand-played dungeon (`runs/2026-06-23_cavenoire_explore`, n=2108 dir-presses):
  real moves AND natural wall-bumps, RAM-labeled. The general case.

## Signals tested (separation of REAL vs STUCK)

| signal | corridor AUC | human-recording AUC |
|---|--:|--:|
| per-step residual `best_diff` (the current move signal) | — (interleaves; see replay-revalidation report) | ~0.86 ceiling |
| windowed displacement (frame now vs 3 steps ago) | **0.99** | **0.62** |
| temporal-median displacement (vs median of last 6 frames; flicker-robust) | 0.88 | **0.63** |

## Why no threshold generalizes
Median displacement-from-recent, by class and context:

| | corridor | human-recording |
|---|--:|--:|
| REAL move | 4.6 | 2.8 |
| STUCK attempt | 2.3 | 2.2 |

A guard that blocks the corridor's stuck loop needs threshold > ~3.5; that **also blocks the human's real
moves (2.8)**. The two contexts' scales overlap (corridor STUCK 2.3 ≈ human REAL 2.8) because a fixed-camera
move's visual magnitude depends entirely on the dungeon's local texture, which the camera can't normalize.
Windowed/median signals score AUC 0.99 *within* the corridor only because a *sustained* runaway is locally
separable there; on the general case (isolated bumps amid real motion) they fall to ~0.62. **Confirmed: the
foreground residual's AUC-0.86 ceiling is the best per-step pixel signal, and it is not enough.**

## UPDATE — localizing the change (grid-max) recovers most of the signal (corrects the claim below)
The "no cheap pixel signal" conclusion was measured on WHOLE-FRAME magnitude. David's counter — *measure
WHERE the change is, not how much* — was tested in `eval/probe_spatial_move.py` and is largely right:

| signal | corridor AUC | human-recording AUC (n=2106) |
|---|--:|--:|
| whole-frame diff (the current move signal) | (n_real=1) | 0.86 |
| **grid max-cell change** (max per-cell mean-abs diff, 8×8 grid) | (n_real=1) | **0.99** |
| **per-cell SSIM** (1 − min-cell SSIM) | (n_real=1) | **0.99** |
| per-cell SSIM, structure-term only | (n_real=1) | 0.98 |
| sprite-centroid direction (background-subtraction tracking) | 0.84 | 0.75 |

A real move spikes ONE cell (the sprite region, median 91) while idle flicker only musters ~20; whole-frame
averaging dilutes the sprite's strong local change into the static background, grid-max preserves it. So the
information IS there — the earlier probe measured it dilutively. **A CNN is NOT needed** (plain per-cell max
of pixel-diff, ~free in numpy — consistent with this repo's "plain hash beats CLIP on pixel-art"). The
fancier directional sprite-tracking was WORSE (0.75) — flicker drags the centroid.

**Per-cell SSIM was tested (the research said its structure term should ignore intensity flicker) and TIES
grid-max — it does not beat it** (AUC 0.99, same ~33% runaway residual). The corridor's animation changes
*structure*, not just intensity, so SSIM fires on it too. ⇒ use the simpler grid-max; SSIM is not worth the
extra computation.

**No per-step appearance signal is a complete fix.** Threshold tuned on the human set (98% real-moves kept),
applied to the corridor RUNAWAY: grid-max and SSIM both leave **~25–33% residual phantom** (threshold-dependent;
the corridor's flicker spikes cells into the real-move range). At that rate a sustained runaway still drifts,
~3–4× slower. The tail is **irreducible by per-step appearance** — confirmed across pixel-diff, grid-max, and SSIM.

⇒ **Revised fix: grid-max as the per-step move signal (3–4× fewer phantoms, no CNN/deps) PLUS the behavioral
backstop below for the residual runaway.** Not either/or — both, each closed-loop validated.

## Implication — a behavioral backstop is still needed (grid-max alone leaves a 25% tail)
Per-step perception is much better with grid-max but still imperfect under intense flicker, so the perceiver
must NOT confidently dead-reckon a long chain on it. Two non-perception levers, both already in the design:
1. **Progress watchdog (recommended).** The harm is the *runaway*, not the single ambiguous move. The system
   already has `play_loop.py`'s "halt when no real progress for N steps" (LEARNINGS iter-03). The corridor
   runaway IS no-progress: many "moves" in one direction, no new frontier reached, frames staying in a tiny
   visual neighborhood. A watchdog that detects sustained no-progress and forces a re-plan / seals the
   direction caps the damage without needing per-step move/stuck classification. Within-run, harness-owned →
   learning-boundary clean.
2. **Confidence-deferral (ADR-001 inv-6).** On a fixed camera (no corroborating camera scroll), a foreground
   move is low-reliability; the perceiver should mark such pose updates UNCERTAIN / low-confidence so nothing
   downstream trusts a long dead-reckoned chain. (Pairs with the `confidence=0.4` placeholder TODO.)

Both are calibrated-deferral, not "be confidently wrong with a better threshold." A perceiver-only threshold
fix is explicitly NOT pursued — the data says it can't work.

## FIX IMPLEMENTED + CLOSED-LOOP VALIDATED (2026-06-24)
Both parts landed in `core/grid_perceiver.py`:
- **Grid-max move signal** (`ForegroundSignal`, `fg_grid=58`): the per-step move signal is now max per-cell
  change (`grid_max_change()`), not the whole-frame residual. Cave Noire wires it (`_FG_GRID=58`).
- **No-progress backstop** (`_RUN_GUARD=4, _PROG_W=4, _PROG_MIN=4.0`): a sustained same-direction run whose
  screen hasn't changed over the last 4 steps is demoted to a no-move → the existing wall-confirmation seals
  it. Gated on a long run so it never fires on normal play.

Results:
- **Closed loop (the corridor runaway state):** perceiver "moves" 70→**4**, phantom **65→0**, pose ran away
  to `[0,-70]` → stays sane at `[-1,-3]` (4 real moves, 4 walls correctly sealed). **The runaway is gone.**
- **Offline replay (human recording):** drift **0.06→0.02** (far fewer phantom steps accumulate); net-dir
  W=1 99→92%, W=40 85→84% (grid-max is more selective — a little per-step recall for much less drift).
- **Gauntlet: unchanged** (57→83% / 0.02) — backstop inert (camera-scroll = progress); `CameraScrollSignal`
  ignores grid-max. 338 tests green.

## Reproduce
- `uv run python -m eval.probe_phantom_move` · `... probe_spatial_move` (need the two gitignored corpora).
- Fix closed-loop: `uv run python play_cave_noire.py --steps 200 --brain explore --init-state <in-cavern.state>`
  then score `oracle.jsonl` `outcome=="moved"` vs the `watch` x/y delta.
