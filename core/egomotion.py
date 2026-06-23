"""Ego-motion (System-1 "how did I move"): the integer 2D pixel translation that best aligns two
consecutive grayscale frames = the camera's self-motion. World-agnostic; numpy only.

Validated direction-recovery in eval/probe_egomotion.py: Pokemon RAM-grounded 98%, and cross-game
79-98% on camera-scrolled steps (gauntlet/kirby/metroid). DIRECTION (sign) is what's reliable; metric
distance is NOT (the camera-model probe showed it; deferred). The estimate is CAMERA motion, which is
the agent's self-motion iff the camera follows the avatar (true for follow-scroll; a follow camera's
dead-zone, or a fixed/flip camera, decouples them).

Single source for what were two copies: eval/probe_camera_model.best_shift (game-agnostic, the probes)
and games/pokemon_red/perceiver._best_shift (the live overworld odometry). tie_break=0 reproduces the
former; tie_break>0 (bias toward the smallest shift) reproduces the latter, so identical frames return
(0,0) = "didn't move", not a phantom corner jump.
"""
from __future__ import annotations

import numpy as np


def best_shift(a, b, *, max_shift, step, min_overlap=0.4, tie_break=0.0):
    """Best integer 2D translation aligning frame `b` back onto `a`. Both are 2D grayscale arrays of
    the same shape (any resolution). Searches dx,dy in [-max_shift, max_shift] with stride `step`,
    requiring the overlap to cover >= min_overlap of the frame.

    Returns (frame_diff, best_diff, dx, dy):
      frame_diff -- whole-frame mean-abs-diff = the zero-shift baseline.
      best_diff  -- residual at the winning shift; LOW => a rigid pan explains the motion (same scene
                    scrolled), HIGH => no shift aligns them (a scene cut / warp).
      dx, dy     -- the winning shift in pixels, ego-oriented (moved east => +dx, south => +dy).
    `tie_break` adds tie_break*(|dx|+|dy|) to the comparison so the SMALLEST aligning shift wins a tie
    (the true ego-motion is minimal; identical frames => (0,0)). Pixels only -- no RAM."""
    H, W = a.shape
    fd = float(np.abs(a - b).mean())
    best_score, best_diff, bdx, bdy = fd, fd, 0, 0   # zero-shift baseline (score == fd at the origin)
    for dy in range(-max_shift, max_shift + 1, step):
        for dx in range(-max_shift, max_shift + 1, step):
            oa = a[max(0, dy):min(H, H + dy), max(0, dx):min(W, W + dx)]
            ob = b[max(0, -dy):min(H, H - dy), max(0, -dx):min(W, W - dx)]
            if oa.size < min_overlap * H * W:
                continue
            d = float(np.abs(oa - ob).mean())
            score = d + tie_break * (abs(dx) + abs(dy))
            if score < best_score:
                best_score, best_diff, bdx, bdy = score, d, dx, dy
    return fd, best_diff, bdx, bdy
