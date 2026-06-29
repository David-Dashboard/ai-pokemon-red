"""Tests for 8-connectivity in blob.py and EntityDetector filters in core/entities.py."""
from __future__ import annotations

import numpy as np
import pytest

from core.blob import _label_bfs, segment_blobs
from core.entities import EntityDetector


# ── 8-connectivity in _label_bfs ─────────────────────────────────────────────

def test_diagonal_touch_8conn_one_blob():
    """A pair touching only diagonally = 1 blob under 8-conn, 2 under 4-conn."""
    mask = np.zeros((5, 5), bool)
    mask[1, 1] = True   # pixel A
    mask[2, 2] = True   # pixel B — diagonally adjacent to A
    _, n8 = _label_bfs(mask, connectivity=8)
    _, n4 = _label_bfs(mask, connectivity=4)
    assert n8 == 1, "8-conn: diagonal pixels should merge into one blob"
    assert n4 == 2, "4-conn: diagonal pixels should remain two blobs"


def test_8conn_larger_diagonal_chain():
    """A diagonal staircase = 1 blob under 8-conn."""
    mask = np.eye(6, dtype=bool)   # main diagonal of 6x6
    _, n8 = _label_bfs(mask, connectivity=8)
    _, n4 = _label_bfs(mask, connectivity=4)
    assert n8 == 1
    assert n4 == 6   # each pixel isolated under 4-conn


def test_segment_blobs_connectivity_param():
    """segment_blobs passes connectivity through to _label_bfs."""
    fg = np.zeros((20, 20), np.float32)
    fg[5, 5] = 100.0
    fg[6, 6] = 100.0   # diagonal touch
    blobs4 = segment_blobs(None, fg_mag=fg, thresh=50.0, min_area=1, connectivity=4)
    blobs8 = segment_blobs(None, fg_mag=fg, thresh=50.0, min_area=1, connectivity=8)
    assert len(blobs4) == 2
    assert len(blobs8) == 1


# ── EntityDetector filters ────────────────────────────────────────────────────

def _stable_bg(detector: EntityDetector, H: int = 144, W: int = 160, n: int = 6) -> None:
    """Feed n blank frames to establish a stable background."""
    blank = np.zeros((H, W, 3), np.uint8)
    for _ in range(n):
        detector.detect(blank)


def _bright_frame(cx: int, cy: int, s: int = 12, H: int = 144, W: int = 160) -> np.ndarray:
    f = np.zeros((H, W, 3), np.uint8)
    f[cy:cy + s, cx:cx + s] = 200
    return f


def test_empty_frame_returns_empty():
    det = EntityDetector()
    _stable_bg(det)
    result = det.detect(np.zeros((144, 160, 3), np.uint8))
    assert result == []


def test_avatar_exclusion_removes_avatar_blob():
    """A blob whose centroid is within avatar_radius of avatar_px is dropped."""
    det = EntityDetector(avatar_radius=20.0)
    _stable_bg(det)
    frame = _bright_frame(30, 30, s=10)
    # centroid of block is ~(35, 35); pass avatar_px at same location
    result = det.detect(frame, avatar_px=(35.0, 35.0))
    assert result == [], "avatar blob should be excluded"


def test_avatar_exclusion_keeps_distant_blob():
    """A blob far from avatar_px is kept."""
    det = EntityDetector(avatar_radius=20.0)
    _stable_bg(det)
    frame = _bright_frame(100, 80, s=12)
    # centroid ~(106, 86); avatar at (20, 20) — well outside radius
    result = det.detect(frame, avatar_px=(20.0, 20.0))
    assert len(result) >= 1


def test_min_area_drops_specks():
    """Blobs below min_area are not returned."""
    fg = np.zeros((144, 160), np.float32)
    fg[10, 10] = 200.0   # 1-pixel speck
    blobs = segment_blobs(None, fg_mag=fg, thresh=100.0, min_area=16)
    assert blobs == []


def test_hud_region_drops_fully_inside_blob():
    """A blob whose bbox is entirely inside hud_region is dropped."""
    det = EntityDetector(hud_region=(0, 128, 160, 144), min_area=4)
    _stable_bg(det)
    # put a bright block in the HUD strip (y=130..138)
    frame = np.zeros((144, 160, 3), np.uint8)
    frame[130:138, 10:18] = 200
    result = det.detect(frame)
    assert result == [], "HUD blob should be dropped"


def test_hud_region_keeps_blob_overlapping_boundary():
    """A blob that crosses the HUD boundary is NOT dropped (only fully-inside ones are)."""
    det = EntityDetector(hud_region=(0, 128, 160, 144), min_area=4)
    _stable_bg(det)
    # block straddles y=128 boundary
    frame = np.zeros((144, 160, 3), np.uint8)
    frame[120:136, 10:22] = 200
    result = det.detect(frame)
    assert len(result) >= 1


def test_detect_returns_correct_keys():
    """Each entity dict has 'bbox' and 'centroid' keys."""
    det = EntityDetector(min_area=4)
    _stable_bg(det)
    frame = _bright_frame(50, 40, s=14)
    result = det.detect(frame)
    if result:
        e = result[0]
        assert "bbox" in e and "centroid" in e
        assert len(e["bbox"]) == 4
        assert len(e["centroid"]) == 2


def test_reset_clears_background():
    """After reset(), the detector needs new frames to re-establish background."""
    det = EntityDetector()
    _stable_bg(det)
    # should detect something after stable bg
    frame = _bright_frame(40, 40, s=12)
    r1 = det.detect(frame)
    # reset: background gone, first few frames return [] due to insufficient history
    det.reset()
    r2 = det.detect(frame)
    assert r2 == [], "no history after reset"
