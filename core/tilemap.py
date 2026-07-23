"""Tile→function map — an ONLINE, behaviour-labelled appearance→function world model.

The unifying idea behind the perception-architecture decision (2026-06-21): the agent learns
what a tile DOES from its OWN behaviour (walk onto it → walkable; bump into it → blocked;
probe+A → interactable), and keys that knowledge by the tile's APPEARANCE so a tile-type
learned once is recognised wherever it recurs — *touch each distinct tile-type once, recognise
it everywhere* (no need to walk every cell to learn a room's layout).

Why a cheap perceptual HASH, not a CLIP embedding (the empirical finding,
`eval/probe_walkability_learn.py`): a behaviour-labelled CLIP store predicts walkability ~98% on
a temporal split but COLLAPSES leave-one-map-out — the embedding captures *appearance, not
function*. The ONE thing it does well — recognise near-identical RECURRING tiles — a perceptual
hash does deterministically, for free, no torch/GPU, CI-testably. So: hash for the recurrence win;
reserve an embedding's *distance* (elsewhere) only as a novelty signal. **Hard limit (verified
2026-06-21, leave-one-TILESET-out): NO appearance key — hash OR embedding — can predict a wall in a
GENUINELY NEW tileset; appearance ≠ function across tilesets. So this map is a RECURRENCE +
NOVELTY signal, never a cross-tileset function oracle; behaviour (a real bump) stays the authority.**

The fingerprint (keying scheme; verified-driven, 2026-06-21):
- **Horizontal + Vertical gradient** (8×8 dHash each way, 128 bits): captures left-right AND up-down
  structure (the V plane gave a free wall-recall gain on outdoor tilesets that the H-only key missed).
- **Intensity bucket** (mean brightness, high bits, matched within ±1): so a flat DARK wall and a flat
  LIGHT floor — which the old all-gradient-zero "all-zeros alias" collapsed into one key and confidently
  mislabelled cross-tileset — now key apart. Brightness is INFORMATIVE here (4 fixed GB shades), so the
  hash is deliberately brightness-SENSITIVE, not brightness-invariant.
- `predict()` exposes two abstain knobs the consumer dials (the coverage⇄safety dial, set by the
  navigation A/B): `min_conf` (ignore low-confidence/mixed buckets) and `skip_flat` (abstain on a
  near-uniform low-texture tile — flat appearance genuinely can't be trusted to predict function).

WORLD-AGNOSTIC by design (System-1 toolkit, `core/`): takes a tile's pixels + a behavioural label,
knows nothing about Pokémon/tile-sizes/geometry — the perceiver (`games/<world>/`) owns extraction.
Predictions are ADVISORY (a contradicting observation overrides; the perceiver's bump-derived `walls`
stay authoritative). Per-run only (rebuilt each run; the learning-boundary law). numpy-only.
"""
from __future__ import annotations

from collections import Counter
from typing import Optional

import numpy as np

# Hamming tolerance applied to the 128-bit GRADIENT only (intensity is gated separately, below).
# Two tiles whose gradients differ by ≤ this many bits AND whose brightness buckets are within ±1 are
# treated as one appearance. GB tiles hash near-identically (exact match dominates); the small tol
# absorbs animation (water/flowers) / sub-tile noise. Tunable per world (calibrated via
# eval/probe_tilemap.py Q6/Q7 robustness sweep on the gradient spread).
_DEFAULT_TOL = 8
_GRAD_BITS = 128                       # 64 horizontal + 64 vertical gradient bits
_GRAD_MASK = (1 << _GRAD_BITS) - 1
_INTEN_TOL = 1                         # brightness buckets within ±1 count as the same band
_FLAT_GRAD_BITS = 4                    # gradient popcount below this ⇒ a near-uniform (low-texture) tile


def _hamming(a: int, b: int) -> int:
    return bin(a ^ b).count("1")


def _split(fp: int) -> tuple[int, int]:
    """A fingerprint splits into (intensity_bucket, 128-bit gradient)."""
    return fp >> _GRAD_BITS, fp & _GRAD_MASK


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
        """A perceptual hash: (intensity_bucket << 128) | (64-bit horizontal ⊕ 64-bit vertical dHash).

        Grayscale (mean of RGB if 3-/4-channel) → average-pool to 8×8 → one bit per cell for "brighter
        than the next COLUMN" (64, wrap-around) and "brighter than the next ROW" (64, wrap-around), then
        prepend a 4-bit mean-brightness bucket. Gradient bits are relative (tolerant to small animation);
        the brightness bucket separates flat tiles of different shade (the all-zeros-alias fix). Identical
        pixels always hash identically (deterministic)."""
        g = np.asarray(tile)
        g = g[..., :3].mean(axis=2) if g.ndim == 3 else g.astype(float)
        pooled = _pool(g, 8)
        h = pooled > np.roll(pooled, -1, axis=1)        # horizontal gradient (vs next column)
        v = pooled > np.roll(pooled, -1, axis=0)        # vertical gradient (vs next row)
        grad = int.from_bytes(np.packbits(np.concatenate([h.flatten(), v.flatten()])).tobytes(), "big")
        inten = min(15, int(float(g.mean()) // 16))     # 0..15 brightness bucket (4 bits)
        return (inten << _GRAD_BITS) | grad

    @staticmethod
    def fp_match(fp_a: int, fp_b: int, *, tol: int = _DEFAULT_TOL) -> bool:
        """True iff two fingerprints (tile OR whole-frame; `fingerprint` accepts either) are the same
        appearance at a fixed tolerance: brightness within ±`_INTEN_TOL` AND gradient Hamming ≤ `tol`.
        The same tolerant compare `_matches` uses internally against a tally, exposed here for a caller
        that wants to compare two ad-hoc fingerprints directly rather than build a `TileFunctionMap`
        (e.g. whole-frame place re-identification: 'have I settled on this exact scene before')."""
        if fp_a == fp_b:
            return True
        ia, ga = _split(fp_a)
        ib, gb = _split(fp_b)
        return abs(ia - ib) <= _INTEN_TOL and _hamming(ga, gb) <= tol

    @staticmethod
    def is_flat(fp: int) -> bool:
        """True if the tile is near-uniform / low-texture (gradient carries < `_FLAT_GRAD_BITS` bits) —
        a flat appearance that genuinely can't be trusted to predict function (could be floor or wall)."""
        return bin(fp & _GRAD_MASK).count("1") < _FLAT_GRAD_BITS

    # -- online build ---------------------------------------------------------
    def observe(self, fp: int, function: str) -> None:
        """Record one behavioural observation: this appearance was proven to be `function`
        (e.g. 'walkable' / 'blocked' / 'interactable'). Counts accumulate, so a later contradicting
        observation can outvote a stale one (self-correction)."""
        self._tally.setdefault(fp, Counter())[function] += 1

    # -- read (advisory) ------------------------------------------------------
    def _matches(self, fp: int) -> list[Counter]:
        """Stored buckets that are the same tile-type as `fp`: brightness within ±`_INTEN_TOL` AND
        gradient Hamming ≤ tol (the intensity gate is what stops a flat dark wall matching a flat light
        floor). Exact match short-circuits. Empty ⇒ never seen ⇒ novel."""
        if fp in self._tally:
            return [self._tally[fp]]            # exact-match fast path
        qi, qg = _split(fp)
        return [c for k, c in self._tally.items()
                if abs((k >> _GRAD_BITS) - qi) <= _INTEN_TOL and _hamming(k & _GRAD_MASK, qg) <= self._tol]

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

    def predict(self, fp: int, min_conf: float = 0.0, skip_flat: bool = False) -> Optional[tuple[str, float]]:
        """The advised (function, confidence) for an appearance, or None if novel / abstained.

        Two abstain knobs the consumer dials (the coverage⇄safety dial — set by the navigation A/B):
        `min_conf` returns None when the matched bucket is below that confidence (a mixed/ambiguous
        appearance); `skip_flat` returns None for a near-uniform low-texture tile (whose appearance
        can't be trusted to predict function). Both default OFF so the bare prediction is unchanged."""
        if skip_flat and TileFunctionMap.is_flat(fp):
            return None
        fn, conf, novel = self.classify(fp)
        if novel or conf < min_conf:
            return None
        return (fn, conf)

    def is_novel(self, fp: int) -> bool:
        """True iff no seen tile-type is within tolerance (the novelty gate's 'unknown → explore')."""
        return not self._matches(fp)

    def __len__(self) -> int:
        """Distinct tile-types learned so far (telemetry)."""
        return len(self._tally)
