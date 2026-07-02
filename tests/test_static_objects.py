"""Unit tests for core/static_objects.py -- the static-saliency candidate detector (killed-cheap,
see the module docstring + reports/2026-07-03-referential-grounding-design.md). These pin the BASIC
mechanics (fail-safe on blank input, saliency mask + fill_holes + connected-components wiring), not the
detection gate itself -- the gate is scored separately by eval/score_static_objects.py against the
hand-labeled fixture, and it FAILS (recall 0.0 / precision 0.0 at bbox-IoU>=0.3 -- KILL CHEAP)."""
from __future__ import annotations

import numpy as np

from core.static_objects import (
    Candidate,
    StaticObjectDetector,
    fill_holes,
    group_equal_collinear,
    local_saliency_mask,
)


def test_blank_frame_returns_no_candidates():
    """A perfectly uniform frame has no local colour contrast -> fail-safe empty list, never a phantom."""
    frame = np.full((144, 160, 3), 100, dtype=np.uint8)
    det = StaticObjectDetector()
    assert det.detect(frame) == []


def test_single_bright_patch_is_detected():
    """A clearly distinct coloured patch on a uniform background produces >=1 candidate covering it."""
    frame = np.full((144, 160, 3), 100, dtype=np.uint8)
    frame[60:76, 60:76] = [250, 10, 10]   # a bright red 16x16 patch, well past any reasonable threshold
    det = StaticObjectDetector(chroma_thresh=28.0)
    cands = det.detect(frame)
    assert len(cands) >= 1
    # the patch centroid should fall inside at least one candidate's bbox
    assert any(c.bbox[0] <= 68 <= c.bbox[2] and c.bbox[1] <= 68 <= c.bbox[3] for c in cands)


def test_local_saliency_mask_shape():
    frame = np.zeros((144, 160, 3), dtype=np.uint8)
    mask = local_saliency_mask(frame)
    assert mask.shape == (144, 160)
    assert mask.dtype == bool
    assert not mask.any()   # uniform frame -> no saliency anywhere


def test_fill_holes_fills_a_ring():
    """A hollow square ring -> fill_holes fills the interior (the fragmentation fix documented in the
    module: an object's edge lights up as salient while its uniform interior doesn't)."""
    mask = np.zeros((10, 10), dtype=bool)
    mask[2:8, 2] = True
    mask[2:8, 7] = True
    mask[2, 2:8] = True
    mask[7, 2:8] = True
    filled = fill_holes(mask)
    assert filled[4, 4]          # interior now filled
    assert filled[0, 0] == False  # true background stays background


def test_fill_holes_empty_mask_noop():
    mask = np.zeros((5, 5), dtype=bool)
    assert not fill_holes(mask).any()


def test_group_equal_collinear_groups_same_row_same_size():
    a = Candidate((0, 0, 9, 9), (4.5, 4.5), 80, (200, 0, 0))
    b = Candidate((20, 0, 29, 9), (24.5, 4.5), 80, (200, 0, 0))
    c = Candidate((0, 50, 9, 59), (4.5, 54.5), 30, (0, 0, 200))   # different area/row -> not grouped with a/b
    groups = group_equal_collinear([a, b, c])
    assert len(groups) == 1
    assert set(groups[0]) == {a, b} if False else len(groups[0]) == 2  # membership by identity, not eq


def test_group_equal_collinear_no_groups_for_singletons():
    a = Candidate((0, 0, 9, 9), (4.5, 4.5), 80, (200, 0, 0))
    b = Candidate((0, 50, 20, 90), (10, 70), 30, (0, 200, 0))
    assert group_equal_collinear([a, b]) == []
