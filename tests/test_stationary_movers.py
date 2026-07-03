"""core.stationary_movers tests (P2 StationaryMovers, GATE-3D PR-C).

Fixture-backed: eval/fixtures/vizdoom_movers/ (20 pairs curated from runs/vizdoom_precheck/dtc_mixed/,
categories stationary_movers / stationary_empty / turning — see the module docstring in
core/stationary_movers.py for the pix_t=25/min_area=30 derivation on this same fixture source).

Covers the design's gate-honesty + three-valued-output requirements (design doc S1.2):
  - movers ARE detected on stationary-with-monster pairs (gate open, P1 direction == "none")
  - the gate returns None (never a list) when P1 reports real turning OR can't tell
  - stationary-empty pairs return [] (not None) — "confidently nothing moving"
  - no phantom blobs above threshold on synthetic identical/noise frames
"""
from __future__ import annotations

import json
import os

import numpy as np
import pytest
from PIL import Image

from core.stationary_movers import MIN_AREA, PIX_T, stationary_movers
from core.yaw_flow import YawReading

FIXTURES = os.path.join(os.path.dirname(__file__), "..", "eval", "fixtures", "vizdoom_movers")


def _load_manifest():
    with open(os.path.join(FIXTURES, "manifest.json")) as f:
        return json.load(f)


def _rgb(name):
    return np.asarray(Image.open(os.path.join(FIXTURES, name)).convert("RGB"))


STATIONARY = YawReading(dx_px=0, direction="none", confidence=1.0)
TURNING_LEFT = YawReading(dx_px=42, direction="left", confidence=0.5)
TURNING_RIGHT = YawReading(dx_px=-42, direction="right", confidence=0.5)
UNCERTAIN = YawReading(dx_px=None, direction=None, confidence=None)


# ── gate honesty: movers detected on stationary+monster pairs ───────────────

def test_movers_detected_on_stationary_with_monster_pairs():
    manifest = [m for m in _load_manifest() if m["category"] == "stationary_movers"]
    assert len(manifest) >= 5
    hits = 0
    for m in manifest:
        result = stationary_movers(_rgb(m["frame_a"]), _rgb(m["frame_b"]), STATIONARY)
        assert result is not None, f"{m['src_pair']}: gate must be OPEN on a stationary reading"
        if result:
            hits += 1
    # not every curated pair need clear min_area at this exact threshold, but the large majority must.
    assert hits / len(manifest) >= 0.8, f"only {hits}/{len(manifest)} stationary_movers pairs popped a blob"


def test_mover_output_shape_has_bbox_centroid_area_confidence():
    manifest = [m for m in _load_manifest() if m["category"] == "stationary_movers"]
    m = manifest[0]
    result = stationary_movers(_rgb(m["frame_a"]), _rgb(m["frame_b"]), STATIONARY)
    assert result
    mover = result[0]
    assert len(mover.bbox) == 4
    assert len(mover.centroid) == 2
    assert mover.area >= MIN_AREA
    assert 0.0 <= mover.confidence <= 1.0
    assert mover.azimuth_deg is None   # no deg_per_px supplied -> never invents a scale


def test_movers_sorted_largest_first_and_capped_at_top_k():
    manifest = [m for m in _load_manifest() if m["category"] == "stationary_movers"]
    for m in manifest:
        result = stationary_movers(_rgb(m["frame_a"]), _rgb(m["frame_b"]), STATIONARY)
        if not result:
            continue
        areas = [mv.area for mv in result]
        assert areas == sorted(areas, reverse=True)
        assert len(result) <= 5


def test_azimuth_deg_computed_when_calibration_supplied():
    manifest = [m for m in _load_manifest() if m["category"] == "stationary_movers"]
    m = manifest[0]
    result = stationary_movers(_rgb(m["frame_a"]), _rgb(m["frame_b"]), STATIONARY, deg_per_px=3.0)
    assert result
    mv = result[0]
    assert mv.azimuth_deg == pytest.approx(mv.azimuth_px / 3.0)


# ── gate CLOSED: None while turning (real direction OR can't-tell), never a fabricated list ─────────

def test_gate_returns_none_while_turning_left():
    manifest = [m for m in _load_manifest() if m["category"] == "turning" and m["action"] == "TURN_LEFT"]
    assert manifest
    for m in manifest:
        result = stationary_movers(_rgb(m["frame_a"]), _rgb(m["frame_b"]), TURNING_LEFT)
        assert result is None


def test_gate_returns_none_while_turning_right():
    manifest = [m for m in _load_manifest() if m["category"] == "turning" and m["action"] == "TURN_RIGHT"]
    assert manifest
    for m in manifest:
        result = stationary_movers(_rgb(m["frame_a"]), _rgb(m["frame_b"]), TURNING_RIGHT)
        assert result is None


def test_gate_returns_none_when_p1_cannot_tell():
    """The load-bearing three-valued-honesty propagation: P1 direction=None (ambiguous, NOT "none") must
    also close the gate — an uncertain P1 reading is never silently treated as "safe to assume
    stationary". This is distinct from direction=="none" (P1 confidently says no rotation)."""
    manifest = [m for m in _load_manifest() if m["category"] == "stationary_movers"]
    m = manifest[0]
    result = stationary_movers(_rgb(m["frame_a"]), _rgb(m["frame_b"]), UNCERTAIN)
    assert result is None


# ── stationary-empty: [] not None ("confidently nothing moving") ────────────

def test_stationary_empty_pairs_return_empty_list_not_none():
    manifest = [m for m in _load_manifest() if m["category"] == "stationary_empty"]
    assert len(manifest) >= 4
    for m in manifest:
        result = stationary_movers(_rgb(m["frame_a"]), _rgb(m["frame_b"]), STATIONARY)
        assert result == [], f"{m['src_pair']}: expected [] (confidently empty), got {result!r}"


# ── no phantom blobs on synthetic identical / noise-floor frames ────────────

def test_no_phantom_blobs_on_identical_frames():
    frame = np.full((240, 320, 3), 100, dtype=np.uint8)
    result = stationary_movers(frame, frame, STATIONARY)
    assert result == []


def test_no_phantom_blobs_below_pix_t_noise():
    rng = np.random.RandomState(0)
    base = rng.randint(80, 120, (240, 320, 3)).astype(np.uint8)
    # jitter by less than PIX_T so no pixel crosses the threshold -- pure sub-threshold sensor noise.
    jitter = rng.randint(0, int(PIX_T - 1), (240, 320, 3)).astype(np.uint8)
    noisy = np.clip(base.astype(int) + jitter, 0, 255).astype(np.uint8)
    result = stationary_movers(base, noisy, STATIONARY)
    assert result == []


def test_mismatched_frame_shapes_return_none_not_a_crash():
    a = np.zeros((240, 320, 3), dtype=np.uint8)
    b = np.zeros((240, 200, 3), dtype=np.uint8)
    assert stationary_movers(a, b, STATIONARY) is None
