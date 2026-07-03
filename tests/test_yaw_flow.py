"""core.yaw_flow tests (P1 YawBandFlow, GATE-3D PR-B).

Fixture-backed regression floor: reports/2026-07-04-vizdoom-3d-floor-design.md S1.1 + S2.2 ARM (b)
(sign-agreement >= 0.90, None-rate <= 0.50), validated live by the free pre-check
(runs/vizdoom_precheck/PRECHECK_REPORT.md PC-2: pooled sign-agreement 0.964 / None-rate 0.201 at the
same ncc>=0.2/prom>=0.02 floors pinned as defaults here). This test re-measures those bars on the
small COMMITTED fixture subset (eval/fixtures/vizdoom_yaw/) rather than the full precheck captures, so
it's self-contained from a clean checkout -- no live ViZDoom, no gitignored runs/ directory needed.

Also covers: idle honesty (zero false motion on ego-stationary pairs), None on genuinely ambiguous
input (uniform frames -- the "can't tell" contract, never fabricated as 0.0-meaning-idle), and
calibration determinism.

The main fixture set is CURATED (its turn pairs were sampled from pool pairs that already agree --
see eval/fixtures/vizdoom_yaw/select_fixtures.py, committed), so its numbers are a regression floor
for the implementation, not an unbiased pool measurement (pool-honest numbers: PC-2). The pool's
failing pairs are all committed too, under eval/fixtures/vizdoom_yaw/known_limits/, and pinned by
their own test below: known R0 failure modes, documented rather than hidden.
"""
from __future__ import annotations

import json
import os

import numpy as np
import pytest
from PIL import Image

from core.yaw_flow import BAND, DEFAULT_BANDS, _single_band_reading, calibrate, yaw_band_flow

FIXTURES = os.path.join(os.path.dirname(__file__), "..", "eval", "fixtures", "vizdoom_yaw")
EXPECTED_DIRECTION = {"TURN_LEFT": "left", "TURN_RIGHT": "right"}


def _load_manifest(subdir=""):
    with open(os.path.join(FIXTURES, subdir, "actions.json")) as f:
        return json.load(f)


def _gray(name, subdir=""):
    return np.asarray(Image.open(os.path.join(FIXTURES, subdir, name)).convert("L"), dtype=np.float32)


# ── fixture-backed regression floor (ARM (b) bar) ────────────────────────────

def test_sign_agreement_and_none_rate_meet_arm_b_floor_on_committed_fixtures():
    manifest = _load_manifest()
    turn_pairs = [m for m in manifest if m["action"] in EXPECTED_DIRECTION]
    assert len(turn_pairs) >= 15, "fixture set should carry a meaningful number of turn pairs"

    scored = 0
    agree = 0
    for m in turn_pairs:
        reading = yaw_band_flow(_gray(m["frame_a"]), _gray(m["frame_b"]))
        if reading.direction is None:
            continue
        scored += 1
        if reading.direction == EXPECTED_DIRECTION[m["action"]]:
            agree += 1

    none_rate = 1 - scored / len(turn_pairs)
    sign_agreement = agree / scored if scored else 0.0

    # ARM (b), design doc S2.2, verbatim bar:
    assert sign_agreement >= 0.90
    assert none_rate <= 0.50
    # committed-fixture measured values (regression pin -- see eval/fixtures/vizdoom_yaw/README.md):
    # sign_agreement == 1.0, none_rate == 0.2727 at time of writing.


def test_idle_pairs_never_report_false_motion():
    manifest = _load_manifest()
    idle_pairs = [m for m in manifest if m["action"] == "IDLE"]
    assert len(idle_pairs) >= 1
    for m in idle_pairs:
        reading = yaw_band_flow(_gray(m["frame_a"]), _gray(m["frame_b"]))
        # "confidently stationary" (dx=0, direction="none") is allowed; a real shift is not.
        assert reading.dx_px in (None, 0)
        assert reading.direction in (None, "none")


# ── known R0 limits (every failing pair from the source pool, committed) ─────

def test_known_limits_document_the_r0_failure_modes():
    """eval/fixtures/vizdoom_yaw/known_limits/ holds EVERY pool pair the curated main set excludes:
    4 wrong-sign turn pairs and 2 false-motion idle pairs (out of ~139 turn / 177 idle pool pairs --
    the pool-honest rates are PC-2's 0.964 / 0.201). This test asserts the CURRENT failing behavior
    so the limits stay visible: if R0 ever stops failing here, this test fails and the pair should
    be promoted to the main set, not silently forgotten.

    Failure modes observed:
    - wrong-sign turns: all at near-floor confidence (<= 0.028 vs prom_floor 0.02) -- three are the
      same burst-turn artifact (dx=-46 at confidence 0.0222), a barely-above-floor correlation peak
      on a fast turn. A slightly higher prom_floor would convert these to honest Nones at the cost
      of a higher None-rate; the pinned floors trade 4/139 wrong signs for None-rate 0.201 (PC-2).
    - false-motion idles: dx=+1 single-pixel jitter at moderate confidence on dtc_mixed idle pairs
      (defend_the_center's monsters keep walking while the camera idles, nudging the band profile).
    """
    manifest = _load_manifest("known_limits")
    turn = [m for m in manifest if m["action"] in EXPECTED_DIRECTION]
    idle = [m for m in manifest if m["action"] == "IDLE"]
    assert len(turn) == 4 and len(idle) == 2

    for m in turn:
        reading = yaw_band_flow(_gray(m["frame_a"], "known_limits"), _gray(m["frame_b"], "known_limits"))
        # known limit: a confidently-reported direction that CONTRADICTS the commanded turn...
        assert reading.direction is not None
        assert reading.direction != EXPECTED_DIRECTION[m["action"]]
        # ...but only at near-floor confidence -- the failure lives just above the pinned floors.
        assert reading.confidence <= 0.03

    for m in idle:
        reading = yaw_band_flow(_gray(m["frame_a"], "known_limits"), _gray(m["frame_b"], "known_limits"))
        # known limit: 1px false motion on an idle pair (scene motion, not ego motion).
        assert reading.direction not in (None, "none")
        assert abs(reading.dx_px) == 1


# ── three-valued honesty on synthetic input ──────────────────────────────────

def test_none_on_uniform_frames_not_zero_meaning_idle():
    # A flat gray frame has no texture at all -- the correlation peak is completely ambiguous
    # (every shift scores identically), which must surface as None, not a fabricated (0, "none").
    a = np.full((240, 320), 128.0, dtype=np.float32)
    b = np.full((240, 320), 128.0, dtype=np.float32)
    reading = yaw_band_flow(a, b)
    assert reading.dx_px is None
    assert reading.direction is None
    assert reading.confidence is None


def test_none_on_uncorrelated_noise():
    rng = np.random.RandomState(0)
    a = rng.randint(0, 255, (240, 320)).astype(np.float32)
    b = rng.randint(0, 255, (240, 320)).astype(np.float32)
    reading = yaw_band_flow(a, b)
    assert reading.direction is None
    assert reading.dx_px is None


# ── known synthetic shift recovers sign + rough magnitude ────────────────────

def test_recovers_a_known_synthetic_shift_and_direction():
    # b's window is shifted +10 relative to a's within the same canvas: b[x] == a[x+10], i.e.
    # cur[x] == prev[x - (-10)], so the aligning shift is dx = -10 (yaw_band_flow's dx convention:
    # cur[x] ~ prev[x - dx]) -> direction "right" per the dx<0 mapping.
    rng = np.random.RandomState(3)
    canvas = rng.randint(0, 255, (240, 320 + 40)).astype(np.float32)
    a = canvas[:, 20:340]
    b = canvas[:, 20 + 10:340 + 10]
    reading = yaw_band_flow(a, b)
    assert reading.dx_px == -10
    assert reading.direction == "right"
    assert reading.confidence is not None


# ── calibration hook ──────────────────────────────────────────────────────────

def test_calibrate_is_deterministic_and_within_run_only():
    # deg-per-px should be a plain regression over the given points -- no hidden state, no caching.
    points = [(7.03, 20), (14.06, 40), (14.06, 41), (7.03, 19)]
    result_a = calibrate(points)
    result_b = calibrate(points)
    assert result_a == result_b
    assert result_a is not None and result_a > 0


def test_calibrate_none_with_insufficient_or_degenerate_points():
    assert calibrate([]) is None
    assert calibrate([(7.0, 20)]) is None          # only one usable point
    assert calibrate([(7.0, 20), (7.0, 21)]) is None  # no variation in commanded degrees
    assert calibrate([(0.0, 0), (0.0, 0)]) is None    # all zero-degree turns filtered out


# ── multi-band voting (design reports/2026-07-05-p1-clutter-redesign.md S2(a), PR-F) ────────────────
# Synthetic frames built on NON-OVERLAPPING test bands (unlike DEFAULT_BANDS, whose adjacent 72px
# windows deliberately share rows) so corrupting one band's pixels can never leak into another band's
# reading -- the isolation the voting-rule tests below depend on. Also disjoint from BAND=(84,156)
# itself, so the fallback test can paint BAND without leaking into any of these.
_SYNTH_BANDS = ((0, 60), (160, 200), (200, 240))
_W, _H = 320, 240


def _uniform_pair():
    return (np.full((_H, _W), 128.0, dtype=np.float32), np.full((_H, _W), 128.0, dtype=np.float32))


def _paint_shift(prev, cur, band, rng, shift):
    """Overwrite `band`'s rows in both frames with a fresh textured strip shifted by `shift` px
    (cur[x] == tex[x - shift]) -- same convention as test_recovers_a_known_synthetic_shift_and_direction:
    a +shift paint yields dx=-shift ('right'), a -shift paint yields dx=+shift ('left')."""
    r0, r1 = band
    pad = 40
    tex = rng.randint(0, 255, (r1 - r0, _W + 2 * pad)).astype(np.float32)
    prev[r0:r1, :] = tex[:, pad:pad + _W]
    cur[r0:r1, :] = tex[:, pad + shift:pad + shift + _W]


def test_bands_none_returns_identical_single_band_result():
    # bands=None (the default) must be the byte-identical pre-redesign code path -- no behavior change
    # for any existing caller not opting in (anti-drift table).
    rng = np.random.RandomState(3)
    canvas = rng.randint(0, 255, (240, 320 + 40)).astype(np.float32)
    a = canvas[:, 20:340]
    b = canvas[:, 30:350]
    assert yaw_band_flow(a, b) == yaw_band_flow(a, b, bands=None)


def test_multiband_requires_at_least_3_bands():
    a, b = _uniform_pair()
    with pytest.raises(ValueError):
        yaw_band_flow(a, b, bands=((0, 60), (80, 140)))


def test_multiband_majority_vote_outvotes_one_corrupted_band():
    # 2 of 3 bands see the TRUE +10 shift (dx=-10, "right"); 1 band is corrupted with an independent,
    # oppositely-shifted texture (dx=+10, "left" in isolation). The trimmed-median vote must side with
    # the majority and report the TRUE direction -- a single corrupted band must not flip the reading.
    rng = np.random.RandomState(11)
    prev = np.full((_H, _W), 128.0, dtype=np.float32)
    cur = np.full((_H, _W), 128.0, dtype=np.float32)
    _paint_shift(prev, cur, _SYNTH_BANDS[1], rng, +10)   # true band -> dx=-10 "right"
    _paint_shift(prev, cur, _SYNTH_BANDS[2], rng, +10)   # true band -> dx=-10 "right"
    corrupt_prev = np.random.RandomState(99).randint(0, 255, (_SYNTH_BANDS[0][1] - _SYNTH_BANDS[0][0], _W)).astype(np.float32)
    prev[_SYNTH_BANDS[0][0]:_SYNTH_BANDS[0][1], :] = corrupt_prev
    _paint_shift(prev, cur, _SYNTH_BANDS[0], np.random.RandomState(99), -10)  # corrupted -> dx=+10 "left"

    per_band = [_single_band_reading(prev, cur, b, 64, 0.2, 0.02) for b in _SYNTH_BANDS]
    assert per_band[0].direction == "left"     # the corrupted band, isolated
    assert per_band[1].direction == "right"
    assert per_band[2].direction == "right"

    reading = yaw_band_flow(prev, cur, bands=_SYNTH_BANDS)
    assert reading.direction == "right"
    assert reading.dx_px == -10
    # confidence = min among the surviving bands used in the vote (never overstate the vote's trust).
    assert reading.confidence == min(r.confidence for r in per_band)


def test_multiband_falls_back_to_single_band_when_fewer_than_two_clear_the_floor():
    # All 3 voting bands are ambiguous (uniform, never clear the floor) but the caller's plain `band`
    # (defaults to BAND) carries a real, recoverable shift -- multi-band must fall back to today's
    # single-band result on `band`, never regressing to None (design S2(a): "never regress below
    # current behavior").
    rng = np.random.RandomState(5)
    prev = np.full((_H, _W), 128.0, dtype=np.float32)
    cur = np.full((_H, _W), 128.0, dtype=np.float32)
    _paint_shift(prev, cur, BAND, rng, +10)   # dx=-10 "right", but BAND is disjoint from _SYNTH_BANDS

    for b in _SYNTH_BANDS:
        assert _single_band_reading(prev, cur, b, 64, 0.2, 0.02).direction is None

    vote = yaw_band_flow(prev, cur, bands=_SYNTH_BANDS)
    fallback = _single_band_reading(prev, cur, BAND, 64, 0.2, 0.02)
    assert vote == fallback
    assert vote.direction == "right"
    assert vote.dx_px == -10


def test_multiband_reports_none_on_a_tied_sign_disagreement():
    # Exactly 2 bands clear the floor and disagree in sign (a tie, not a lone-outlier minority) -- the
    # design's outlier rule ("disagree in sign by more than one band") must reject this as None rather
    # than arbitrarily pick a side.
    rng = np.random.RandomState(7)
    prev = np.full((_H, _W), 128.0, dtype=np.float32)
    cur = np.full((_H, _W), 128.0, dtype=np.float32)
    _paint_shift(prev, cur, _SYNTH_BANDS[0], rng, +10)   # dx=-10 "right"
    _paint_shift(prev, cur, _SYNTH_BANDS[2], rng, -10)   # dx=+10 "left"
    # _SYNTH_BANDS[1] stays uniform -> ambiguous, does not clear the floor.

    per_band = [_single_band_reading(prev, cur, b, 64, 0.2, 0.02) for b in _SYNTH_BANDS]
    assert per_band[0].direction == "right"
    assert per_band[1].direction is None
    assert per_band[2].direction == "left"

    reading = yaw_band_flow(prev, cur, bands=_SYNTH_BANDS)
    assert reading.direction is None
    assert reading.dx_px is None
    assert reading.confidence is None


def test_default_bands_constant_is_3_bands_and_reslices_the_curated_fixtures():
    # DEFAULT_BANDS (S2(a): centered 0.40H/0.50H/0.60H, each 0.30H tall) must be usable directly against
    # the committed 240-row fixtures with no shape errors, and the middle band must equal today's BAND
    # exactly (same center/height rule -- the redesign must not silently redefine the original band).
    assert len(DEFAULT_BANDS) == 3
    assert DEFAULT_BANDS[1] == BAND
    manifest = _load_manifest()
    turn_pairs = [m for m in manifest if m["action"] in EXPECTED_DIRECTION]
    m = turn_pairs[0]
    reading = yaw_band_flow(_gray(m["frame_a"]), _gray(m["frame_b"]), bands=DEFAULT_BANDS)
    assert reading.dx_px is None or isinstance(reading.dx_px, int)
