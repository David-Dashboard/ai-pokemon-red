"""Unit tests for core/text_regions_r1.py -- the R1 cache-driven text-region detector
(`reports/2026-07-03-glyph-r1-cache-driven-detection.md`). Covers the snap-to-grid mitigation
(section 4.0), the grid-aligned scan + cluster-size denoise (sections 2a-2c), and the honesty
property that a cold/empty cache detects nothing (section 1). The detector's actual recall/precision
against the same-game warm/held-out fixture split is scored separately by eval/score_glyph_r1.py
(depends on runs/ probe frames, not present in a fresh worktree -- not exercised here)."""
from __future__ import annotations

import numpy as np

from core.glyph_cache import GlyphCache
from core.text_regions_r1 import GlyphRegionDetector, confirm_region, snap_to_grid

_CELL = 8


def _stripe_glyph(i: int) -> np.ndarray:
    """A distinct, deliberately NON-FLAT 8x8 binarized (1=dark) shape per index i -- mirrors
    tests/test_score_glyph_cache.py's `_distinct_glyph` fixture-construction pattern."""
    g = np.zeros((_CELL, _CELL), dtype=np.uint8)
    g[:, i % _CELL] = 1
    g[i % _CELL, :] = 1
    return g


def _paint(frame: np.ndarray, glyph: np.ndarray, x0: int, y0: int) -> None:
    block = np.where(glyph[..., None] == 1, 0, 255).astype(np.uint8)
    frame[y0:y0 + _CELL, x0:x0 + _CELL, :] = block


def _blank_frame(h: int = 64, w: int = 64) -> np.ndarray:
    return np.full((h, w, 3), 255, dtype=np.uint8)


# -- snap_to_grid (design doc section 4.0) ---------------------------------------------------------

def test_snap_to_grid_aligned_rect_is_unchanged():
    assert snap_to_grid((8, 8, 16, 16), cell=8) == (8, 8, 16, 16)


def test_snap_to_grid_expands_outward_to_enclosing_boundaries():
    # x0=5 floors to 0; y0=5 floors to 0; x1=20 ceils to 24; y1=20 ceils to 24.
    assert snap_to_grid((5, 5, 20, 20), cell=8) == (0, 0, 24, 24)


def test_snap_to_grid_never_shrinks_the_rect():
    x0, y0, x1, y1 = snap_to_grid((3, 11, 19, 27), cell=8)
    assert x0 <= 3 and y0 <= 11 and x1 >= 19 and y1 >= 27


# -- confirm_region: full-frame grid slicing, never the crop's own off-grid origin ------------------

def test_confirm_region_confirms_only_nonblank_cells():
    frame = _blank_frame()
    _paint(frame, _stripe_glyph(1), 8, 8)   # one real glyph cell at a grid-aligned position
    cache = GlyphCache()
    n_real, n_new = confirm_region(cache, frame, (8, 8, 16, 16), "#", cell=_CELL)
    assert n_real == 1 and n_new == 1
    fp = GlyphCache.fingerprint(frame[8:16, 8:16])
    assert cache.from_cache(fp)


def test_confirm_region_skips_blank_cells():
    frame = _blank_frame()   # all white -- flat, no glyph
    cache = GlyphCache()
    n_real, n_new = confirm_region(cache, frame, (0, 0, 16, 16), "#", cell=_CELL)
    assert n_real == 0 and n_new == 0
    assert len(cache) == 0


def test_confirm_region_snaps_an_off_grid_rect_before_slicing():
    frame = _blank_frame()
    _paint(frame, _stripe_glyph(2), 8, 8)   # glyph occupies the grid-aligned cell (8,8)-(16,16)
    cache = GlyphCache()
    # an OFF-GRID crop rect that still overlaps the grid-aligned glyph cell once snapped outward
    n_real, n_new = confirm_region(cache, frame, (10, 10, 14, 14), "#", cell=_CELL)
    assert n_real == 1 and n_new == 1
    fp = GlyphCache.fingerprint(frame[8:16, 8:16])
    assert cache.from_cache(fp)


def test_confirm_region_reuses_placeholder_reading_no_mismatch():
    frame = _blank_frame()
    _paint(frame, _stripe_glyph(3), 0, 0)
    cache = GlyphCache()
    confirm_region(cache, frame, (0, 0, 8, 8), "#", cell=_CELL)
    confirm_region(cache, frame, (0, 0, 8, 8), "#", cell=_CELL)   # re-confirm, same placeholder
    fp = GlyphCache.fingerprint(frame[0:8, 0:8])
    assert not cache.is_contested(fp)


# -- GlyphRegionDetector: grid-aligned scan + cluster-size denoise (sections 2a-2c) ------------------

def test_cold_cache_detects_nothing():
    """The design doc's honesty property (section 1): R1 detects NOTHING until the cache holds a
    confirmed glyph -- a blank cache must never phantom a region."""
    frame = _blank_frame()
    for i in range(5):
        _paint(frame, _stripe_glyph(i), 8 + i * _CELL, 8)
    detector = GlyphRegionDetector(GlyphCache())
    assert detector.detect(frame) == []


def test_run_of_three_confirmed_cells_is_detected():
    cache = GlyphCache()
    frame = _blank_frame()
    for i in range(3):
        g = _stripe_glyph(i)
        x0 = 8 + i * _CELL
        _paint(frame, g, x0, 8)
        # confirm the fingerprint of the PAINTED (0/255) pixels, matching what the detector's scan
        # actually hashes -- fingerprinting the raw 0/1 binarized `g` would key a different
        # intensity bucket (a test-construction pitfall, not a detector one).
        cache.confirm(GlyphCache.fingerprint(frame[8:16, x0:x0 + _CELL]), "#")
    regions = GlyphRegionDetector(cache).detect(frame)
    assert len(regions) == 1
    x0, y0, x1, y1 = regions[0].bbox
    assert x0 == 8 and x1 == 8 + 3 * _CELL and y0 == 8 and y1 == 8 + _CELL


def test_run_of_two_confirmed_cells_is_dropped_denoise():
    """Section 2c: a run of 1-2 hit cells is exactly the hash-collision failure mode the >=3
    threshold exists to kill -- must not surface as a candidate."""
    cache = GlyphCache()
    frame = _blank_frame()
    for i in range(2):
        g = _stripe_glyph(i)
        x0 = 8 + i * _CELL
        _paint(frame, g, x0, 8)
        cache.confirm(GlyphCache.fingerprint(frame[8:16, x0:x0 + _CELL]), "#")
    regions = GlyphRegionDetector(cache).detect(frame)
    assert regions == []


def test_unconfirmed_glyph_shapes_never_hit():
    """A glyph shape rendered on screen but never confirmed into the cache is invisible to R1 by
    construction (section 5: novel glyphs are a miss, never a phantom)."""
    cache = GlyphCache()
    unrelated = _blank_frame()
    _paint(unrelated, _stripe_glyph(0), 0, 0)
    cache.confirm(GlyphCache.fingerprint(unrelated[0:8, 0:8]), "#")   # confirm an UNRELATED shape
    frame = _blank_frame()
    for i in range(3, 6):   # paint three DIFFERENT, never-confirmed shapes
        _paint(frame, _stripe_glyph(i), 8 + (i - 3) * _CELL, 8)
    assert GlyphRegionDetector(cache).detect(frame) == []


def test_contested_entries_never_count_as_hits():
    """A cache key with tied/contradicting confirmations abstains (GlyphCache.lookup returns None on
    a tie) -- R1 inherits that honesty discipline for free (design doc section 2b)."""
    cache = GlyphCache()
    frame = _blank_frame()
    for i in range(3):
        g = _stripe_glyph(i)
        x0 = 8 + i * _CELL
        _paint(frame, g, x0, 8)
        fp = GlyphCache.fingerprint(frame[8:16, x0:x0 + _CELL])
        cache.confirm(fp, "p")
        cache.confirm(fp, "q")   # 1-1 tie on every cell in the run -- all abstain
    assert GlyphRegionDetector(cache).detect(frame) == []


def test_detect_returns_empty_list_on_undersized_frame():
    detector = GlyphRegionDetector(GlyphCache())
    tiny = np.full((4, 4, 3), 255, dtype=np.uint8)
    assert detector.detect(tiny) == []
