"""Unit tests for core/text_regions.py -- the R0 text-region (routing/foveation) detector
(`reports/2026-07-05-glyph-read-design.md` section 4(a)). These pin the BASIC mechanics (fail-safe on
blank/flat input, row-band profile shape, world-agnostic no-config detection of an obvious synthetic
glyph-like row), not the detection gate itself -- the gate is scored separately by
eval/score_text_regions.py against the hand-labeled fixture, and it FAILS the pinned bar (see that
module's docstring for the measured recall/precision/phantom numbers -- reported honestly as a FAIL,
not tuned to pass)."""
from __future__ import annotations

import os

import numpy as np

from core.text_regions import TextRegion, TextRegionDetector, row_edge_density


def _checkerboard(h: int, w: int, period: int = 2) -> np.ndarray:
    """A high-frequency synthetic 'glyph-like' texture: alternating black/white cells, tightly packed
    -- exactly the kind of dense edge pattern a packed glyph row produces."""
    yy, xx = np.mgrid[0:h, 0:w]
    return (((yy // period) + (xx // period)) % 2 * 255).astype(np.uint8)


def test_blank_frame_returns_no_regions():
    frame = np.full((160, 240), 100, dtype=np.uint8)
    det = TextRegionDetector()
    assert det.detect(frame) == []


def test_flat_frame_below_min_size_returns_no_regions():
    frame = np.full((4, 4), 50, dtype=np.uint8)   # smaller than one cell
    det = TextRegionDetector()
    assert det.detect(frame) == []


def test_dense_checkerboard_row_is_detected():
    """A synthetic high-edge-density TWO-row-cell band embedded in an otherwise flat frame should score
    above the row threshold and produce >=1 candidate spanning it -- the basic wiring the gate then
    stress-tests on real frames. (Two row-cells, not one, to clear the default min_rows=2 denoise --
    see test_min_rows_denoises_single_row_spikes for the single-row-cell case.)"""
    frame = np.full((160, 240), 128, dtype=np.uint8)
    frame[40:56, :] = _checkerboard(16, 240, period=1)
    det = TextRegionDetector()
    regions = det.detect(frame)
    assert len(regions) >= 1
    assert any(r.bbox[1] <= 40 < r.bbox[3] for r in regions)


def test_uniform_frame_has_zero_row_density():
    frame = np.full((160, 240), 100, dtype=np.float32)
    profile = row_edge_density(frame, cell=8)
    assert profile.shape == (20,)
    assert np.allclose(profile, 0.0)


def test_row_edge_density_higher_for_textured_row():
    frame = np.full((32, 240), 100, dtype=np.float32)
    frame[8:16, :] = _checkerboard(8, 240, period=1)
    profile = row_edge_density(frame, cell=8)
    assert profile[1] > profile[0]
    assert profile[1] > profile[2]


def test_accepts_rgb_and_pil_like_ndarray():
    rgb = np.full((160, 240, 3), 100, dtype=np.uint8)
    rgb[40:48, :, :] = 255
    det = TextRegionDetector()
    # a uniform bright band (no internal edges) should NOT trigger -- edge density, not brightness
    assert det.detect(rgb) == []


def test_text_region_to_dict_and_repr():
    r = TextRegion((0, 8, 240, 16), 0.42)
    d = r.to_dict()
    assert d["bbox"] == [0, 8, 240, 16]
    assert d["confidence"] == 0.42
    assert "TextRegion" in repr(r)


def test_min_rows_denoises_single_row_spikes():
    frame = np.full((160, 240), 128, dtype=np.uint8)
    frame[40:48, :] = _checkerboard(8, 240, period=1)   # exactly one row-cell tall
    det = TextRegionDetector(min_rows=2)
    assert det.detect(frame) == []   # single-row band dropped as noise
    det2 = TextRegionDetector(min_rows=1)
    assert len(det2.detect(frame)) >= 1


def test_detect_never_raises_on_degenerate_input():
    det = TextRegionDetector()
    assert det.detect(np.zeros((0, 0), dtype=np.uint8)) == []
    assert det.detect(np.zeros((3, 3), dtype=np.uint8)) == []


# -- design constraint: core/ stays world-agnostic (no game import) + model-free -----------------

def test_module_has_no_game_import_and_no_torch_or_pil():
    src = os.path.join(os.path.dirname(__file__), "..", "core", "text_regions.py")
    text = open(src, encoding="utf-8").read()
    assert "import games" not in text and "from games" not in text
    assert "import torch" not in text
    assert "import PIL" not in text and "from PIL" not in text
