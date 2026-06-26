"""AvatarLocalizer tests -- the control-grounded localizer (numpy only, no ROM).

Covers the output CONTRACT (None until locked, then (col,row,conf), held when stationary) and the
outlier gate that keeps a single animation flash from teleporting the fix. The locked->snap path that
CONSUMES this localizer (and feeds the occupancy map) is tested in test_grid_perceiver.py.
"""
from __future__ import annotations

import numpy as np

from core.localize import AvatarLocalizer, _JUMP


def _block(cx, cy, s=12):
    """A frame with one bright square at (cx,cy) -- a stand-in avatar sprite."""
    f = np.zeros((144, 160, 3), np.uint8)
    f[cy:cy + s, cx:cx + s] = 255
    return f


def test_returns_none_until_first_lock():
    loc = AvatarLocalizer()
    assert loc.update(_block(40, 60), "right") is None    # first frame: no prev -> never fabricates a fix


def test_locks_onto_the_command_consistent_mover():
    loc = AvatarLocalizer()
    loc.update(_block(30, 60), "right")
    out = None
    for cx in (45, 60, 75):
        out = loc.update(_block(cx, 60), "right")          # a block tracking right WITH the command
    assert out is not None
    col, row, conf = out
    assert 55 <= col <= 100 and 50 <= row <= 80           # near the block's path (the thing the buttons move)
    assert 0.0 <= conf <= 1.0                              # graded confidence, in range


def test_holds_the_fix_when_no_command_motion():
    loc = AvatarLocalizer()
    loc.update(_block(30, 60), "right")
    for cx in (45, 60, 75):
        loc.update(_block(cx, 60), "right")
    a = loc.update(_block(75, 60), None)                   # no commanded motion -> avatar stationary -> HOLD
    b = loc.update(_block(75, 60), None)
    assert a is not None and b is not None
    assert a[:2] == b[:2]                                  # the held fix is stable (not recomputed / drifting)


def test_outlier_gate_holds_a_single_far_jump():
    loc = AvatarLocalizer()
    loc.update(_block(20, 70), "right")
    ref = None
    for cx in (32, 44, 56, 68):
        ref = loc.update(_block(cx, 70), "right")          # locked, tracking right near col ~73
    # a far block moves consistently FAR away (an animation that momentarily looks command-explained)
    loc.update(_block(120, 20), "right")                   # establish the far mover's prev
    after = loc.update(_block(132, 20), "right")           # far mover steps -> a far confident peak
    assert after is not None
    assert abs(after[0] - ref[0]) <= _JUMP                 # the gate HELD: the fix did not teleport in 1 frame
