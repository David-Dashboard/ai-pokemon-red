"""Unit tests for eval/score_glyph_r1.py -- the R1 gate scorer (`reports/2026-07-03-glyph-r1-cache-
driven-detection.md` section 4). Builds a small SYNTHETIC probe-dir + warmup-label list + Gate-1-shaped
fixture (no dependency on the real runs/probe_*/ recordings or eval/fixtures/text_regions/labels.json,
so this test is CI-safe and independent of the actual gate's measured PASS/FAIL/KILL/INCONCLUSIVE
result) to pin the warmup-replay + same-game scoring mechanics."""
from __future__ import annotations

import json
import os
import tempfile

import numpy as np
from PIL import Image

from eval.score_glyph_cache import N_WARMUP_CONFIRMING_FRAMES
from eval.score_glyph_r1 import score_game, warm_cache_from_labels

_CELL = 8
_GAME = "Test Sweep Game"


def _shape(i: int) -> np.ndarray:
    g = np.zeros((_CELL, _CELL), dtype=np.uint8)
    g[:, i % _CELL] = 1
    g[i % _CELL, :] = 1
    return g


def _novel_shape() -> np.ndarray:
    """A shape that never aliases any `_shape(i)` stripe-cross pattern -- a checkerboard, used for
    distractor content that must NEVER match anything the warmup set confirmed."""
    g = np.zeros((_CELL, _CELL), dtype=np.uint8)
    g[::2, ::2] = 1
    g[1::2, 1::2] = 1
    return g


def _paint(frame: np.ndarray, glyph: np.ndarray, x0: int, y0: int) -> None:
    block = np.where(glyph[..., None] == 1, 0, 255).astype(np.uint8)
    frame[y0:y0 + _CELL, x0:x0 + _CELL, :] = block


def _frame(h: int = 64, w: int = 64) -> np.ndarray:
    return np.full((h, w, 3), 255, dtype=np.uint8)


def _write(path: str, frame: np.ndarray) -> None:
    Image.fromarray(frame).save(path)


def _make_warmup_set(probe_dir: str, n_frames: int = N_WARMUP_CONFIRMING_FRAMES) -> list:
    """`n_frames` warmup records, each painting 4 CELLS of a genuinely new shape (>= _MIN_REAL_CELLS,
    each contributing a first-sight confirmation) so every frame counts as confirming -- mirrors
    tests/test_score_glyph_cache.py's warmup-fixture-construction pattern."""
    os.makedirs(probe_dir, exist_ok=True)
    records = []
    for i in range(n_frames):
        frame = _frame()
        for j in range(4):
            _paint(frame, _shape(i), 8 + j * _CELL, 8)   # 4 cells, all the SAME shape this frame
        fname = f"frame_{i:03d}.png"
        _write(os.path.join(probe_dir, fname), frame)
        records.append({"file": fname, "targets": [[8, 8, 8 + 4 * _CELL, 16]]})
    return records


def test_warm_cache_from_labels_reaches_warm_after_five_confirming_frames():
    with tempfile.TemporaryDirectory() as tmp:
        probe_dir = os.path.join(tmp, "probe_test", "world")
        records = _make_warmup_set(probe_dir)
        cache, stats = warm_cache_from_labels(probe_dir, records)
        assert stats["warm"] is True
        assert stats["confirming_frames"] == N_WARMUP_CONFIRMING_FRAMES
        # each warmup frame introduced exactly one distinct shape
        assert stats["distinct_glyphs_confirmed"] == N_WARMUP_CONFIRMING_FRAMES


def test_warm_cache_from_labels_reports_not_warm_when_short():
    with tempfile.TemporaryDirectory() as tmp:
        probe_dir = os.path.join(tmp, "probe_test", "world")
        records = _make_warmup_set(probe_dir, n_frames=2)   # short of the pinned 5
        cache, stats = warm_cache_from_labels(probe_dir, records)
        assert stats["warm"] is False
        assert stats["confirming_frames"] == 2


def test_warm_cache_from_labels_confirms_via_snap_to_grid_not_raw_crop():
    """A target bbox that is itself grid-aligned here, but confirm_region must still route through
    the pinned snap-to-grid slicing (core.text_regions_r1.confirm_region) -- regression guard against
    a future edit bypassing the mitigation."""
    with tempfile.TemporaryDirectory() as tmp:
        probe_dir = os.path.join(tmp, "probe_test", "world")
        os.makedirs(probe_dir, exist_ok=True)
        frame = _frame()
        _paint(frame, _shape(0), 8, 8)
        _write(os.path.join(probe_dir, "f.png"), frame)
        cache, stats = warm_cache_from_labels(
            probe_dir, [{"file": "f.png", "targets": [[9, 9, 15, 15]]}])   # OFF-GRID bbox
        assert stats["distinct_glyphs_confirmed"] == 1   # still found the grid-aligned glyph cell


def test_score_game_recall_precision_on_a_held_out_frame():
    with tempfile.TemporaryDirectory() as tmp:
        probe_dir_rel = "probe_test/world"
        probe_dir = os.path.join(tmp, probe_dir_rel)
        warmup_records = _make_warmup_set(probe_dir)   # confirms shapes 0..4 into the cache

        fixture_dir = os.path.join(tmp, "fixture")
        os.makedirs(fixture_dir, exist_ok=True)
        # held-out scoring frame: reuses CONFIRMED shape 0 in a run of 3 -- must be recalled.
        held_out = _frame()
        for j in range(3):
            _paint(held_out, _shape(0), 8 + j * _CELL, 8)
        _write(os.path.join(fixture_dir, "held_out.png"), held_out)
        # a distractor frame with a NEVER-confirmed shape -- must not phantom.
        distractor = _frame()
        for j in range(3):
            _paint(distractor, _novel_shape(), 8 + j * _CELL, 8)
        _write(os.path.join(fixture_dir, "distractor.png"), distractor)

        labels = {"_comment": "test fixture", "frames": [
            {"file": "held_out.png", "game": _GAME, "targets": [[8, 8, 8 + 3 * _CELL, 16]]},
            {"file": "distractor.png", "game": _GAME, "targets": []},
        ]}
        with open(os.path.join(fixture_dir, "labels.json"), "w", encoding="utf-8") as f:
            json.dump(labels, f)

        warmup_labels = {_GAME: {"probe_dir": probe_dir_rel, "frames": warmup_records}}
        result = score_game(_GAME, tmp, warmup_labels, fixture_dir=fixture_dir)

        assert result["warm"]["warm"] is True
        assert result["recall"] == 1.0
        assert result["phantom_count"] == 0


def test_score_game_scopes_to_its_own_game_only():
    """A fixture containing a DIFFERENT game's frames must not be scored against this game's cache
    (design doc section 4b: same-game warm/held-out pairing only)."""
    with tempfile.TemporaryDirectory() as tmp:
        probe_dir_rel = "probe_test/world"
        probe_dir = os.path.join(tmp, probe_dir_rel)
        warmup_records = _make_warmup_set(probe_dir)

        fixture_dir = os.path.join(tmp, "fixture")
        os.makedirs(fixture_dir, exist_ok=True)
        other_game_frame = _frame()
        _write(os.path.join(fixture_dir, "other.png"), other_game_frame)
        labels = {"frames": [{"file": "other.png", "game": "A Different Game", "targets": []}]}
        with open(os.path.join(fixture_dir, "labels.json"), "w", encoding="utf-8") as f:
            json.dump(labels, f)

        warmup_labels = {_GAME: {"probe_dir": probe_dir_rel, "frames": warmup_records}}
        result = score_game(_GAME, tmp, warmup_labels, fixture_dir=fixture_dir)
        assert result["total_targets"] == 0
        assert result["per_frame"] == []
