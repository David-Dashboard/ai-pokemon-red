"""core.egomotion tests (P2 extraction, 2026-06-23) — pure, numpy-only.

The single source for best_shift (consolidated from the probe + the Pokemon perceiver) is load-bearing
odometry, so lock it directly (not just via its two callers): exact recovery of a known integer shift,
identical frames -> (0,0), the tie_break bias toward the smaller aligning shift, and the direction()
seam token. No PIL / network.
"""
from __future__ import annotations

import numpy as np

from core.egomotion import best_shift, direction


def test_recovers_a_known_integer_shift_exactly():
    # Two 32x32 windows cut from one 48x48 canvas, offset by a known (sx, sy); the aligning shift IS
    # that offset and the residual is exactly zero (random texture => unique minimum).
    canvas = np.random.RandomState(0).randint(0, 255, (48, 48)).astype(np.float32)
    sx, sy = 4, -6
    a = canvas[8:40, 8:40]
    b = canvas[8 + sy:40 + sy, 8 + sx:40 + sx]
    fd, best, dx, dy = best_shift(a, b, max_shift=8, step=2)
    assert (dx, dy) == (sx, sy)
    assert best == 0.0 and fd > 0.0


def test_identical_frames_give_zero_shift():
    a = np.random.RandomState(1).randint(0, 255, (32, 32)).astype(np.float32)
    fd, best, dx, dy = best_shift(a, a, max_shift=8, step=2)
    assert (dx, dy) == (0, 0)
    assert fd == 0.0 and best == 0.0


def test_tie_break_prefers_the_smaller_aligning_shift():
    # period-4 vertical stripes, b anti-phase (shifted half a period) -> equally-good alignments at
    # dx in {-6,-2,2,6}; a strong row gradient pins dy=0. Without a tie-break the first-encountered
    # (most-negative) alignment wins (|dx|=6); the tie-break biases toward the smallest (|dx|=2).
    cols = np.arange(32)
    rowgrad = (np.arange(32) * 3.0)[:, None]
    a = np.tile(np.where(cols % 4 < 2, 200.0, 40.0), (32, 1)) + rowgrad
    b = np.tile(np.where((cols + 2) % 4 < 2, 200.0, 40.0), (32, 1)) + rowgrad
    _, _, dx0, dy0 = best_shift(a, b, max_shift=8, step=2, tie_break=0.0)
    _, _, dxt, dyt = best_shift(a, b, max_shift=8, step=2, tie_break=1e-3)
    assert (dy0, dyt) == (0, 0)
    assert abs(dxt) == 2 and abs(dx0) == 6        # tie_break collapses to the minimal aligning shift


def test_direction_token_is_sign_only_and_magnitude_free():
    assert direction(0, 0) == "none"
    assert direction(5, 0) == "east" and direction(-5, 0) == "west"
    assert direction(0, 5) == "south" and direction(0, -5) == "north"
    assert direction(99, 0) == direction(2, 0)    # magnitude does not change the token
    assert direction(3, -5) == "north"            # dominant axis (vertical) wins
    assert direction(4, 4) == "east"              # horizontal wins an exact tie
