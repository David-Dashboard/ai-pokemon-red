"""Tile→function map — an ONLINE, behaviour-labelled appearance→function world model.

The unifying idea behind the perception-architecture decision (2026-06-21): the agent learns
what a tile DOES from its OWN behaviour (walk onto it → walkable; bump into it → blocked;
probe+A → interactable), and keys that knowledge by the tile's APPEARANCE so a tile-type
learned once is recognised wherever it recurs — *touch each distinct tile-type once, recognise
it everywhere* (no need to walk every cell to learn a room's layout).

Why a cheap perceptual HASH, not a CLIP embedding (the empirical finding,
`eval/probe_walkability_learn.py`): a behaviour-labelled CLIP store predicts walkability ~98% on
a temporal split but COLLAPSES leave-one-map-out (held-out lab 26.9% < baseline) — the embedding
captures *appearance, not function*, so it generalises walkability to a new tileset no better than
chance. The ONE thing it does well — recognise near-identical RECURRING tiles — a perceptual hash
does deterministically, for free, with no torch/GPU, and CI-testably. So: hash for the recurrence
win; reserve an embedding's *distance* (elsewhere) only as a novelty signal.

This module is WORLD-AGNOSTIC by design (System-1 toolkit, `core/`): it takes a tile's pixels and
a behavioural label and never knows about Pokémon, tile sizes, or screen geometry — the perceiver
(`games/<world>/`) owns the extraction (which pixels are a tile, where the player faces). Behaviour
is ground truth; predictions are ADVISORY (a fresh contradicting observation overrides a stale one,
and the perceiver's occupancy `walls` — from real bumps — remain the authority). Per-run only
(rebuilt each run, never persisted across runs — the learning-boundary law; persistence is the
deferred It4 question). numpy-only: no torch, no PIL, no network.
"""
from __future__ import annotations

from collections import Counter
from typing import Optional

import numpy as np

# Default Hamming tolerance for "the same tile-type": two perceptual hashes within this many bit
# flips are treated as one appearance. Crisp 4-shade GB tiles hash near-identically; a few flips
# absorb animation (water/flowers) / sub-tile noise. CALIBRATED offline (eval/probe_tilemap.py, Q6/Q7,
# 2026-06-21): settled faced-tiles already hash IDENTICALLY ~98% of the time, so exact match alone
# captures most recurrence; same-cell animation spread is p90=5 while genuinely-different content sits
# far away (max ~27). So 6 sits just above the animation band — it recovers the last ~2% of coverage
# without inviting cross-tile collisions (accuracy was flat 92.5% across tol 0..12 on this data, the
# residual being intrinsic tile/function ambiguity, NOT collisions — so a conservative tol is safest
# for richer tilesets). Tunable per world.
_DEFAULT_TOL = 6


def _hamming(a: int, b: int) -> int:
    return bin(a ^ b).count("1")


def _pool(gray: np.ndarray, n: int = 8) -> np.ndarray:
    """Average-pool a 2-D grayscale tile into an n×n grid (deterministic, any input size).

    For a 16×16 tile this is an exact 2×2-block mean; for off-size tiles (e.g. a map-edge crop) the
    linspace boundaries degrade gracefully. Kept loop-simple (n²=64 cells) — cost is negligible and
    it avoids a scipy/PIL dependency, keeping `core/` model-free."""
    h, w = gray.shape
    ys = np.linspace(0, h, n + 1).astype(int)
    xs = np.linspace(0, w, n + 1).astype(int)
    out = np.empty((n, n), dtype=float)
    for i in range(n):
        for j in range(n):
            block = gray[ys[i]:ys[i + 1], xs[j]:xs[j + 1]]
            out[i, j] = float(block.mean()) if block.size else 0.0
    return out


class TileFunctionMap:
    """A per-run appearance→function map keyed by a perceptual hash of a tile's pixels.

    Build it online: `observe(fingerprint(tile), label)` each time behaviour proves a tile's
    function. Read it for free: `classify(fingerprint(tile))` predicts an unseen-but-similar tile's
    function (advisory) and whether it is novel. The keying scheme (the fingerprint + the tolerant
    lookup) is the single seam a future, smarter version would swap without touching callers."""

    def __init__(self, tol: int = _DEFAULT_TOL) -> None:
        self._tol = tol
        self._tally: dict[int, Counter] = {}   # perceptual-hash -> {function: count}

    # -- keying ---------------------------------------------------------------
    @staticmethod
    def fingerprint(tile: np.ndarray) -> int:
        """A 64-bit perceptual hash of a tile (dHash with wrap-around columns).

        Grayscale (mean of RGB if 3-/4-channel), average-pool to 8×8, then set one bit per cell for
        "is this cell brighter than the next column over" (wrap the last column to the first → exactly
        64 bits). The comparison is RELATIVE, so the hash is invariant to a uniform brightness/palette
        shift and tolerant to small animation; identical pixels always hash identically (deterministic)."""
        g = np.asarray(tile)
        g = g[..., :3].mean(axis=2) if g.ndim == 3 else g.astype(float)
        pooled = _pool(g, 8)
        bits = pooled > np.roll(pooled, -1, axis=1)     # 8×8 bool: brighter than the next column
        return int.from_bytes(np.packbits(bits.flatten()).tobytes(), "big")

    # -- online build ---------------------------------------------------------
    def observe(self, fp: int, function: str) -> None:
        """Record one behavioural observation: this appearance was proven to be `function`
        (e.g. 'walkable' / 'blocked' / 'interactable'). Counts accumulate, so a later contradicting
        observation can outvote a stale one (self-correction)."""
        self._tally.setdefault(fp, Counter())[function] += 1

    # -- read (advisory) ------------------------------------------------------
    def _matches(self, fp: int) -> list[Counter]:
        """All stored buckets whose key is within tolerance of `fp` (exact match has distance 0, so
        it is always included). Empty ⇒ this appearance has never been seen ⇒ novel."""
        if fp in self._tally:
            return [self._tally[fp]]            # exact-match fast path
        return [c for k, c in self._tally.items() if _hamming(fp, k) <= self._tol]

    def classify(self, fp: int) -> tuple[Optional[str], float, bool]:
        """One-shot read used by the perceiver: returns (function, confidence, novel).

        `function`/`confidence` are the majority label over all in-tolerance buckets and its share
        (None/0.0 if novel); `novel` is True iff nothing within tolerance has been seen. Combines
        predict + is_novel so the per-cell scan pays the O(N) lookup once."""
        buckets = self._matches(fp)
        if not buckets:
            return None, 0.0, True
        agg: Counter = Counter()
        for b in buckets:
            agg.update(b)
        fn, cnt = agg.most_common(1)[0]
        return fn, cnt / sum(agg.values()), False

    def predict(self, fp: int) -> Optional[tuple[str, float]]:
        """The advised (function, confidence) for an appearance, or None if novel."""
        fn, conf, novel = self.classify(fp)
        return None if novel else (fn, conf)

    def is_novel(self, fp: int) -> bool:
        """True iff no seen tile-type is within tolerance (the novelty gate's 'unknown → explore')."""
        return not self._matches(fp)

    def __len__(self) -> int:
        """Distinct tile-types learned so far (telemetry)."""
        return len(self._tally)
