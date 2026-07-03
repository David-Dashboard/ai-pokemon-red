"""Unit tests for eval/score_text_regions.py -- the Gate 1 scorer. Builds a small SYNTHETIC fixture
(no dependency on the real eval/fixtures/text_regions/ hand-labeled set, so this test is CI-safe and
independent of the actual gate's measured PASS/FAIL) to pin the IoU-matching / recall / precision /
phantom-count arithmetic and the pinned-bar gate check itself."""
from __future__ import annotations

import json
import os
import tempfile

import numpy as np
from PIL import Image

from core.text_regions import TextRegion
from eval.score_text_regions import PRECISION_BAR, RECALL_BAR, _iou, score


def _write_fixture(tmpdir: str, frames: list[dict]) -> None:
    for rec in frames:
        img = Image.new("RGB", (240, 160), (0, 0, 0))
        img.save(os.path.join(tmpdir, rec["file"]))
    with open(os.path.join(tmpdir, "labels.json"), "w", encoding="utf-8") as f:
        json.dump({"frames": frames}, f)


def test_iou_basic_cases():
    assert _iou((0, 0, 10, 10), (0, 0, 10, 10)) == 1.0
    assert _iou((0, 0, 10, 10), (20, 20, 30, 30)) == 0.0
    # half-overlap square
    v = _iou((0, 0, 10, 10), (5, 0, 15, 10))
    assert abs(v - (50 / 150)) < 1e-9


def test_perfect_detector_scores_recall_and_precision_1():
    with tempfile.TemporaryDirectory() as tmp:
        frames = [{"file": "a.png", "targets": [[10, 10, 50, 20]]}]
        _write_fixture(tmp, frames)

        class Det:
            def detect(self, frame):
                return [TextRegion((10, 10, 50, 20), 0.9)]

        result = score(tmp, detector=Det())
        assert result["recall"] == 1.0
        assert result["precision"] == 1.0
        assert result["phantom_count"] == 0


def test_missed_target_hurts_recall_not_precision():
    with tempfile.TemporaryDirectory() as tmp:
        frames = [{"file": "a.png", "targets": [[10, 10, 50, 20]]}]
        _write_fixture(tmp, frames)

        class Det:
            def detect(self, frame):
                return []

        result = score(tmp, detector=Det())
        assert result["recall"] == 0.0
        assert result["precision"] is None   # no candidates at all


def test_phantom_on_distractor_frame_is_counted():
    with tempfile.TemporaryDirectory() as tmp:
        frames = [{"file": "d.png", "targets": []}]
        _write_fixture(tmp, frames)

        class Det:
            def detect(self, frame):
                return [TextRegion((0, 0, 20, 20), 0.5)]

        result = score(tmp, detector=Det())
        assert result["phantom_count"] == 1
        assert result["total_targets"] == 0


def test_low_iou_candidate_does_not_count_as_matched():
    with tempfile.TemporaryDirectory() as tmp:
        frames = [{"file": "a.png", "targets": [[0, 0, 100, 100]]}]
        _write_fixture(tmp, frames)

        class Det:
            def detect(self, frame):
                return [TextRegion((90, 90, 95, 95), 0.5)]   # tiny sliver overlap, IoU well under 0.3

        result = score(tmp, detector=Det(), iou_thresh=0.3)
        assert result["recall"] == 0.0


def test_gate_bar_constants_match_design_doc():
    # Pinned before the detector was scored (reports/2026-07-05-glyph-read-design.md section 5) --
    # regression guard against silently loosening the bar to make a future run pass.
    assert RECALL_BAR == 0.85
    assert PRECISION_BAR == 0.70
