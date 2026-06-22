"""TileFunctionMap tests (perception-architecture decision, 2026-06-21) — pure, numpy-only.

Covers the agnostic appearance->function map: the perceptual-hash fingerprint (H+V gradient +
brightness bucket; deterministic, brightness-SENSITIVE by design), behaviour-labelled observe/predict
with confidence, self-correction, structured tolerant matching (intensity gate + gradient Hamming),
the novelty gate, and the min_conf / skip_flat abstain knobs. No torch / PIL / network.
"""
from __future__ import annotations

import os

import numpy as np

from core.tilemap import TileFunctionMap


def _tile(seed: int, lo: int = 0, hi: int = 255):
    """A deterministic textured 16x16x3 tile."""
    return np.random.RandomState(seed).randint(lo, hi, size=(16, 16, 3)).astype(np.uint8)


# -- fingerprint ---------------------------------------------------------------

def test_fingerprint_is_a_deterministic_int():
    t = _tile(1)
    fp = TileFunctionMap.fingerprint(t)
    assert isinstance(fp, int) and fp >= 0
    assert fp == TileFunctionMap.fingerprint(t.copy())     # same pixels -> same hash


def test_fingerprint_distinguishes_different_tiles():
    assert TileFunctionMap.fingerprint(_tile(1)) != TileFunctionMap.fingerprint(_tile(2))


def test_fingerprint_distinguishes_flat_dark_from_flat_light():
    # THE all-zeros-alias fix (verified 2026-06-21): both flat tiles have an empty gradient, so the
    # old H-only dHash collapsed them to one key (0) and confidently mislabelled cross-tileset. The
    # brightness bucket now keys them apart, and the intensity gate keeps them from matching.
    dark = np.full((16, 16, 3), 40, dtype=np.uint8)
    light = np.full((16, 16, 3), 200, dtype=np.uint8)
    fd, fl = TileFunctionMap.fingerprint(dark), TileFunctionMap.fingerprint(light)
    assert fd != fl
    t = TileFunctionMap()
    t.observe(fd, "blocked")
    assert t.is_novel(fl)              # different brightness band -> NOT the same tile-type -> novel


def test_fingerprint_captures_vertical_structure():
    # top-half dark / bottom-half light: a vertical gradient with NO horizontal variation. The old
    # H-only key gave both this and its up-down flip the same (all-zero) hash; the V plane separates them.
    t = np.zeros((16, 16, 3), dtype=np.uint8)
    t[8:, :, :] = 255
    flipped = t[::-1].copy()           # same pixels & brightness, reversed up/down structure
    assert TileFunctionMap.fingerprint(t) != TileFunctionMap.fingerprint(flipped)


def test_fingerprint_accepts_grayscale_2d():
    g = np.random.RandomState(5).randint(0, 255, size=(16, 16)).astype(np.uint8)
    assert isinstance(TileFunctionMap.fingerprint(g), int)


def test_is_flat_flags_near_uniform_tiles():
    assert TileFunctionMap.is_flat(TileFunctionMap.fingerprint(np.full((16, 16, 3), 120, np.uint8)))
    assert not TileFunctionMap.is_flat(TileFunctionMap.fingerprint(_tile(6)))   # textured -> not flat


# -- observe / predict ---------------------------------------------------------

def test_observe_and_predict_majority_with_confidence():
    t = TileFunctionMap()
    fp = TileFunctionMap.fingerprint(_tile(10))
    for _ in range(3):
        t.observe(fp, "walkable")
    assert t.predict(fp) == ("walkable", 1.0)
    assert len(t) == 1


def test_self_correction_contradicting_observations_flip_the_label():
    # Behaviour is truth: accumulating 'blocked' evidence outvotes a stale 'walkable' label.
    t = TileFunctionMap()
    fp = TileFunctionMap.fingerprint(_tile(11))
    for _ in range(3):
        t.observe(fp, "walkable")
    for _ in range(5):
        t.observe(fp, "blocked")
    fn, conf = t.predict(fp)
    assert fn == "blocked" and abs(conf - 5 / 8) < 1e-9


def test_predict_on_empty_map_is_none():
    assert TileFunctionMap().predict(12345) is None


# -- abstain knobs (the coverage<->safety dial the navigation A/B sets) ---------

def test_predict_min_conf_abstains_on_mixed_bucket():
    t = TileFunctionMap()
    fp = TileFunctionMap.fingerprint(_tile(30))
    t.observe(fp, "walkable"); t.observe(fp, "walkable"); t.observe(fp, "blocked")   # conf 2/3
    fn, conf = t.predict(fp)
    assert fn == "walkable" and abs(conf - 2 / 3) < 1e-9        # default min_conf=0 -> predicts
    assert t.predict(fp, min_conf=0.8) is None                 # below threshold -> abstain


def test_predict_skip_flat_abstains_on_flat_tile():
    fp = TileFunctionMap.fingerprint(np.full((16, 16, 3), 120, dtype=np.uint8))
    t = TileFunctionMap()
    t.observe(fp, "walkable")
    assert t.predict(fp) == ("walkable", 1.0)                  # default: predicts
    assert t.predict(fp, skip_flat=True) is None               # flat appearance -> abstain


# -- structured tolerant matching (gradient Hamming; raw int keys) -------------

def test_predict_matches_within_hamming_tolerance():
    # observe/predict take raw int keys (intensity bucket 0), so gradient tolerance tests exactly.
    t = TileFunctionMap(tol=3)
    t.observe(0, "walkable")
    assert t.predict(0b111) == ("walkable", 1.0)   # gradient hamming 3 == tol -> match
    assert t.predict(0b1111) is None               # hamming 4 > tol  -> novel


def test_classify_aggregates_near_buckets():
    t = TileFunctionMap(tol=4)
    t.observe(0, "blocked")
    t.observe(0b11, "blocked")     # hamming 2 from a query of 0 -> aggregated
    fn, conf, novel = t.classify(0)
    assert fn == "blocked" and conf == 1.0 and novel is False


# -- novelty gate --------------------------------------------------------------

def test_is_novel_before_and_after_observing():
    t = TileFunctionMap()
    fp = TileFunctionMap.fingerprint(_tile(20))
    assert t.is_novel(fp)
    t.observe(fp, "walkable")
    assert not t.is_novel(fp)
    far = TileFunctionMap.fingerprint(_tile(21))   # an unrelated appearance stays novel
    assert t.is_novel(far)


# -- design constraint: core/ stays model-free ---------------------------------

def test_module_is_numpy_only_no_torch_or_pil():
    src = os.path.join(os.path.dirname(__file__), "..", "core", "tilemap.py")
    text = open(src, encoding="utf-8").read()
    assert "import torch" not in text
    assert "import PIL" not in text and "from PIL" not in text
