"""Tests for core.blob (connected-components + BFS + association) and BayesAvatarLocalizer.

Synthetic frames only -- no ROM, no real recordings. Mirror the style of test_localize.py.
"""
from __future__ import annotations

import numpy as np
import pytest

from core.blob import Blob, RollingBg, _label_bfs, associate_blobs, segment_blobs
from core.localize_bayes import BayesAvatarLocalizer


# ── helpers ──────────────────────────────────────────────────────────────────

def _gray_frame(H=144, W=160):
    return np.zeros((H, W), np.float32)


def _block_frame(cx, cy, s=12, H=144, W=160, val=255):
    """Grayscale frame with one bright square."""
    f = np.zeros((H, W), np.float32)
    f[cy:cy + s, cx:cx + s] = val
    return f


def _rgb_block(cx, cy, s=12):
    f = np.zeros((144, 160, 3), np.uint8)
    f[cy:cy + s, cx:cx + s] = 255
    return f


# ── _label_bfs ────────────────────────────────────────────────────────────────

def test_label_bfs_single_blob():
    mask = np.zeros((10, 10), bool)
    mask[2:5, 2:5] = True
    labels, n = _label_bfs(mask)
    assert n == 1
    assert (labels[2:5, 2:5] == 1).all()
    assert labels[0, 0] == 0


def test_label_bfs_two_separate_blobs():
    mask = np.zeros((10, 20), bool)
    mask[1:4, 1:4] = True   # blob A
    mask[6:9, 14:17] = True  # blob B
    labels, n = _label_bfs(mask)
    assert n == 2
    # the two regions must have different non-zero labels
    la = labels[2, 2]
    lb = labels[7, 15]
    assert la != 0 and lb != 0 and la != lb


def test_label_bfs_empty_mask():
    mask = np.zeros((8, 8), bool)
    labels, n = _label_bfs(mask)
    assert n == 0
    assert (labels == 0).all()


def test_label_bfs_all_fg():
    mask = np.ones((5, 5), bool)
    labels, n = _label_bfs(mask)
    assert n == 1
    assert (labels > 0).all()


# ── RollingBg ─────────────────────────────────────────────────────────────────

def test_rolling_bg_returns_none_until_history():
    bg = RollingBg(window=6)
    for _ in range(2):
        assert bg.update(_gray_frame()) is None   # need at least 3 frames
    result = bg.update(_gray_frame())
    assert result is not None


def test_rolling_bg_detects_foreground():
    bg = RollingBg(window=6)
    for _ in range(5):
        bg.update(_gray_frame())   # build a stable all-zero background
    # now a bright block appears -> large fg magnitude
    bright = _block_frame(20, 20, s=10, val=200)
    fg = bg.update(bright)
    assert fg is not None
    assert fg[22, 22] > 50   # inside the block: high magnitude
    assert fg[0, 0] < 5      # outside: near zero


# ── segment_blobs ─────────────────────────────────────────────────────────────

def test_segment_blobs_empty_when_no_history():
    bg = RollingBg(window=6)
    result = segment_blobs(_rgb_block(10, 10), bg=bg)
    assert result == []   # not enough history yet


def test_segment_blobs_finds_one_block():
    bg = RollingBg(window=6)
    for _ in range(5):
        segment_blobs(np.zeros((144, 160, 3), np.uint8), bg=bg)
    blobs = segment_blobs(_rgb_block(20, 30, s=14), bg=bg, thresh=10.0)
    assert len(blobs) >= 1
    b = blobs[0]
    # centroid should be near the block centre
    assert 20 <= b.cx <= 40 and 30 <= b.cy <= 50


def test_segment_blobs_with_precomputed_fg_mag():
    fg = np.zeros((144, 160), np.float32)
    fg[40:55, 60:75] = 100.0
    blobs = segment_blobs(None, fg_mag=fg, thresh=50.0, min_area=4)
    assert len(blobs) == 1
    b = blobs[0]
    assert 60 <= b.cx <= 75 and 40 <= b.cy <= 55


def test_segment_blobs_drops_small_blobs():
    fg = np.zeros((144, 160), np.float32)
    fg[10, 10] = 200.0     # 1-pixel blob -> below min_area=16
    blobs = segment_blobs(None, fg_mag=fg, thresh=100.0, min_area=16)
    assert blobs == []


def test_segment_blobs_raises_without_bg_or_fg():
    import pytest
    with pytest.raises(ValueError):
        segment_blobs(np.zeros((144, 160, 3), np.uint8))


# ── associate_blobs ────────────────────────────────────────────────────────────

def _blob_at(cx, cy):
    return Blob(cx=cx, cy=cy, x0=int(cx)-5, y0=int(cy)-5, x1=int(cx)+5, y1=int(cy)+5, area=100)


def test_associate_blobs_empty_lists():
    pairs = associate_blobs([], [_blob_at(10, 10)])
    assert pairs == [(None, 0)]

    pairs = associate_blobs([_blob_at(10, 10)], [])
    assert pairs == []


def test_associate_blobs_simple_match():
    prev = [_blob_at(10, 10)]
    cur  = [_blob_at(12, 12)]
    pairs = associate_blobs(prev, cur, max_dist=40)
    assert pairs == [(0, 0)]


def test_associate_blobs_new_blob():
    prev = [_blob_at(10, 10)]
    cur  = [_blob_at(12, 12), _blob_at(100, 80)]
    pairs = associate_blobs(prev, cur, max_dist=40)
    matched = {(pi, ci) for pi, ci in pairs}
    assert (0, 0) in matched          # near one matched
    assert (None, 1) in matched       # far one is new


def test_associate_blobs_max_dist_enforced():
    prev = [_blob_at(10, 10)]
    cur  = [_blob_at(100, 100)]       # distance >> 40
    pairs = associate_blobs(prev, cur, max_dist=40)
    assert pairs == [(None, 0)]       # cur blob is new, not matched


# ── BayesAvatarLocalizer ──────────────────────────────────────────────────────

def test_bayes_returns_none_on_first_frame():
    loc = BayesAvatarLocalizer()
    assert loc.update(_rgb_block(40, 60), "right") is None


def test_bayes_locks_on_command_consistent_mover():
    loc = BayesAvatarLocalizer()
    loc.update(_rgb_block(30, 60), "right")
    out = None
    for cx in (45, 60, 75):
        out = loc.update(_rgb_block(cx, 60), "right")
    assert out is not None
    col, row, conf = out
    assert 40 <= col <= 110 and 50 <= row <= 80
    assert 0.0 <= conf <= 1.0


def test_bayes_holds_when_no_command():
    loc = BayesAvatarLocalizer()
    loc.update(_rgb_block(30, 60), "right")
    for cx in (45, 60, 75):
        loc.update(_rgb_block(cx, 60), "right")
    a = loc.update(_rgb_block(75, 60), None)
    b = loc.update(_rgb_block(75, 60), None)
    assert a is not None and b is not None
    assert a[:2] == b[:2]


def test_bayes_reset_clears_state():
    loc = BayesAvatarLocalizer()
    for cx in (30, 45, 60):
        loc.update(_rgb_block(cx, 60), "right")
    loc.reset()
    assert loc.pos is None
    # after reset: first frame returns None again (no prev)
    assert loc.update(_rgb_block(30, 60), "right") is None


def test_bayes_does_not_teleport_on_weak_observation():
    """When the heatmap is weak (no commanded step), pos should be held, not None."""
    loc = BayesAvatarLocalizer()
    loc.update(_rgb_block(30, 60), "right")
    for cx in (45, 60, 75):
        loc.update(_rgb_block(cx, 60), "right")
    # now several idle frames: must HOLD
    for _ in range(5):
        out = loc.update(_rgb_block(75, 60), None)
        assert out is not None
        assert 40 <= out[0] <= 110
