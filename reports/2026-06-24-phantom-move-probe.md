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

## Implication — the fix is behavioral (and already has homes in the architecture)
Per-step perception can't reliably tell move from stuck here, so the perceiver must NOT confidently
dead-reckon a long chain on it. Two non-perception levers, both already in the design:
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

## Reproduce
`uv run python -m eval.probe_phantom_move` (needs the two gitignored corpora).
