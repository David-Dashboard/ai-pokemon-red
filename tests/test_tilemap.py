"""TileFunctionMap tests (perception-architecture decision, 2026-06-21) — pure, numpy-only.

Covers the agnostic appearance->function map: the perceptual-hash fingerprint (deterministic,
brightness-invariant), behaviour-labelled observe/predict with confidence, self-correction,
Hamming-tolerant recurrence matching, and the novelty gate. No torch / PIL / network.
"""
from __future__ import annotations

import os

import numpy as np

from core.tilemap import TileFunctionMap


def _tile(seed: int, lo: int = 0, hi: int = 255):
    """A deterministic 16x16x3 tile; values in [lo,hi) so a brightness shift can avoid clipping."""
    return np.random.RandomState(seed).randint(lo, hi, size=(16, 16, 3)).astype(np.uint8)


# -- fingerprint ---------------------------------------------------------------

def test_fingerprint_is_a_deterministic_64bit_int():
    t = _tile(1)
    fp = TileFunctionMap.fingerprint(t)
    assert isinstance(fp, int) and 0 <= fp < (1 << 64)
    assert fp == TileFunctionMap.fingerprint(t.copy())     # same pixels -> same hash


def test_fingerprint_distinguishes_different_tiles():
    assert TileFunctionMap.fingerprint(_tile(1)) != TileFunctionMap.fingerprint(_tile(2))


def test_fingerprint_is_brightness_invariant():
    # A uniform brightness/palette shift (no clipping) preserves the per-cell ordering, so the dHash
    # is unchanged — the robustness that lets one tile-type survive minor animation/palette swaps.
    t = _tile(3, lo=0, hi=180)
    bright = np.clip(t.astype(int) + 30, 0, 255).astype(np.uint8)   # in-range -> no saturation
    assert TileFunctionMap.fingerprint(t) == TileFunctionMap.fingerprint(bright)


def test_fingerprint_accepts_grayscale_2d():
    g = np.random.RandomState(5).randint(0, 255, size=(16, 16)).astype(np.uint8)
    assert isinstance(TileFunctionMap.fingerprint(g), int)


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


# -- Hamming tolerance (recurrence matching) -----------------------------------

def test_predict_matches_within_hamming_tolerance():
    # observe/predict take raw int keys, so tolerance can be tested exactly without crafting pixels.
    t = TileFunctionMap(tol=3)
    t.observe(0, "walkable")
    assert t.predict(0b111) == ("walkable", 1.0)   # hamming 3 == tol -> match
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
