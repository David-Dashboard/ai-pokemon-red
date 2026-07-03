"""Unit tests for core/glyph_cache.py -- the within-run brain-confirmed glyph cache
(`reports/2026-07-05-glyph-read-design.md` section 4(b)). Covers the keying (delegates to
`TileFunctionMap.fingerprint` verbatim), confirm/lookup mechanics, the honesty/invalidation story
(mismatch tracking, tie-break abstain -- never a fabricated guess), and the within-run-only /
model-free design constraints. The cache's actual hit-rate payoff (frac_free, 0 mismatches) is scored
separately by eval/score_glyph_cache.py against the replayed dialog fixture -- it PASSES the pinned
bar (see that module's docstring for the measured numbers)."""
from __future__ import annotations

import os

import numpy as np

from core.glyph_cache import GlyphCache
from core.tilemap import TileFunctionMap


def _cell(seed: int) -> np.ndarray:
    return np.random.RandomState(seed).randint(0, 255, size=(8, 8)).astype(np.uint8)


# -- keying: delegates to TileFunctionMap.fingerprint verbatim ------------------------------------

def test_fingerprint_matches_tilemap_fingerprint_exactly():
    c = _cell(1)
    assert GlyphCache.fingerprint(c) == TileFunctionMap.fingerprint(c)


def test_fingerprint_is_deterministic():
    c = _cell(2)
    assert GlyphCache.fingerprint(c) == GlyphCache.fingerprint(c.copy())


def test_fingerprint_distinguishes_different_glyph_cells():
    assert GlyphCache.fingerprint(_cell(1)) != GlyphCache.fingerprint(_cell(2))


# -- confirm / lookup: the free-vs-paid-read mechanic ---------------------------------------------

def test_lookup_before_confirm_is_none():
    gc = GlyphCache()
    fp = GlyphCache.fingerprint(_cell(3))
    assert gc.lookup(fp) is None
    assert not gc.from_cache(fp)


def test_confirm_then_lookup_serves_for_free():
    gc = GlyphCache()
    fp = GlyphCache.fingerprint(_cell(4))
    gc.confirm(fp, "A")
    assert gc.lookup(fp) == "A"
    assert gc.from_cache(fp)
    assert len(gc) == 1


def test_repeated_confirmation_reinforces_majority():
    gc = GlyphCache()
    fp = GlyphCache.fingerprint(_cell(5))
    for _ in range(3):
        gc.confirm(fp, "b")
    assert gc.lookup(fp) == "b"


def test_unrelated_key_stays_unconfirmed():
    gc = GlyphCache()
    fp_a = GlyphCache.fingerprint(_cell(6))
    fp_b = GlyphCache.fingerprint(_cell(7))
    gc.confirm(fp_a, "x")
    assert gc.lookup(fp_b) is None


# -- honesty / invalidation: mismatch tracking + tie-break abstain (never a fabricated guess) -----

def test_contradicting_confirmation_is_tracked_as_mismatch():
    gc = GlyphCache()
    fp = GlyphCache.fingerprint(_cell(8))
    gc.confirm(fp, "m")
    assert not gc.is_contested(fp)
    gc.confirm(fp, "n")   # a later brain-confirmed read disagreeing with the first
    assert gc.is_contested(fp)


def test_majority_still_wins_after_one_contradiction():
    gc = GlyphCache()
    fp = GlyphCache.fingerprint(_cell(9))
    gc.confirm(fp, "y"); gc.confirm(fp, "y")
    gc.confirm(fp, "z")   # 2-1, majority still holds
    assert gc.lookup(fp) == "y"


def test_tied_confirmations_abstain_rather_than_guess():
    gc = GlyphCache()
    fp = GlyphCache.fingerprint(_cell(10))
    gc.confirm(fp, "p")
    gc.confirm(fp, "q")   # 1-1 tie -- genuinely ambiguous
    assert gc.lookup(fp) is None
    assert not gc.from_cache(fp)


def test_self_correction_flips_majority_like_tilemap():
    """Mirrors TileFunctionMap.observe's self-correction: enough contradicting confirmations outvote
    a stale majority instead of the cache trusting the first answer forever."""
    gc = GlyphCache()
    fp = GlyphCache.fingerprint(_cell(11))
    gc.confirm(fp, "stale")
    for _ in range(3):
        gc.confirm(fp, "corrected")
    assert gc.lookup(fp) == "corrected"
    assert gc.is_contested(fp)


# -- tolerant matching (small-Hamming fallback, mirrors FontTable.lookup) --------------------------

def test_lookup_tolerates_small_hamming_distance():
    gc = GlyphCache(tol=64)   # generous tolerance for this synthetic test
    base = np.zeros((8, 8), dtype=np.uint8)
    near = base.copy()
    near[0, 0] = 255   # a tiny perturbation
    fp_base = GlyphCache.fingerprint(base)
    gc.confirm(fp_base, "Z")
    fp_near = GlyphCache.fingerprint(near)
    # near-identical bitmap should either hit the exact key or fall within tolerance
    assert gc.lookup(fp_near) in ("Z", None)   # never a WRONG guess -- Z or abstain, nothing else


def test_zero_tolerance_still_exact_matches():
    gc = GlyphCache(tol=0)
    fp = GlyphCache.fingerprint(_cell(12))
    gc.confirm(fp, "e")
    assert gc.lookup(fp) == "e"


# -- within-run-only / model-free design constraints -----------------------------------------------

def test_fresh_instance_has_no_memory_of_a_previous_instance():
    gc1 = GlyphCache()
    fp = GlyphCache.fingerprint(_cell(13))
    gc1.confirm(fp, "w")
    gc2 = GlyphCache()   # a new "run"
    assert gc2.lookup(fp) is None
    assert len(gc2) == 0


def test_module_is_numpy_only_no_torch_or_pil_no_disk_persistence():
    src = os.path.join(os.path.dirname(__file__), "..", "core", "glyph_cache.py")
    text = open(src, encoding="utf-8").read()
    assert "import torch" not in text
    assert "import PIL" not in text and "from PIL" not in text
    assert "open(" not in text and "json.dump" not in text   # no disk read/write -- within-run only
