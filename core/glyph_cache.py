"""Within-run, brain-confirmed glyph cache -- the R1 "recognition" half of the glyph-read design
(`reports/2026-07-05-glyph-read-design.md` section 4(b)). Generalizes the ALREADY-PROVEN
`core.tilemap.TileFunctionMap` hashing/keying mechanism from tile-function to glyph-identity: a glyph
cell hashed once, confirmed by the brain's own `read_region` reading (same mechanism the HUD-grounding
gate already proved works, `reports/2026-07-03-adr002-gate-plan.md`), is recognised for FREE every time
the identical bitmap recurs -- "touch-once-recognise-everywhere", applied to characters instead of tiles.

THIS IS NOT `games/pokemon_red/textbox.py`'s FontTable: that asset is a human-typed, offline-calibrated,
per-game glyph table checked into the repo (the anti-pattern this module generalizes away from, per the
design doc's anti-drift table). This cache is built ONLINE, at runtime, from brain-confirmed reads --
any game, no font asset, no human calibration step, and it is blank at the start of every run
(learning-boundary law, same as `TileFunctionMap` -- a cache surviving to the next run would be silent
cross-run learning, forbidden regardless of how well-grounded it is within one run).

Keying: `TileFunctionMap.fingerprint` REUSED VERBATIM (not reimplemented) -- the exact H+V gradient dHash
+ intensity-bucket perceptual hash, just applied to a caller-supplied glyph-cell size instead of a
world-tile size. Identical rendering is deterministic (same argument `textbox.py`'s docstring already
makes), so the exact-match fast path dominates; the small-Hamming fallback (mirroring `FontTable.lookup`)
absorbs sub-pixel/anti-aliasing noise.

Honesty/invalidation story (the design doc's frontier slot, section 4(b) slot 2): a cache entry is
grounded by exactly ONE brain-confirmed read. If a LATER brain-confirmed read of the same (or
Hamming-near) key reports a DIFFERENT character, that is a collision or a mid-run font/palette change --
the entry does NOT keep silently serving the stale answer. It demotes to contested (tracked via a
`Counter` majority vote, the exact `TileFunctionMap.observe` self-correction pattern) and `lookup()`
returns None (never a fabricated guess) until re-confirmed, exactly mirroring `FontTable.lookup`'s
`'?'`-on-unknown / `TileFunctionMap.classify`'s `None`-on-novel discipline.

GATE: `eval/score_glyph_cache.py` scores this against a simulated within-run confirmation sequence
(`runs/dialog/*` frames, `games/pokemon_red/gen1_font.json` as ground-truth oracle -- see that module's
docstring for why the oracle stand-in is legitimate for what THIS gate measures). See that module for
the pinned fraction-free/mismatch bar and the measured result.
"""
from __future__ import annotations

from collections import Counter
from typing import Optional

import numpy as np

from core.tilemap import _GRAD_BITS, _GRAD_MASK, _INTEN_TOL, TileFunctionMap

_DEFAULT_TOL = 4   # gradient Hamming tolerance for the small-Hamming fallback (mirrors FontTable.lookup)


class GlyphCache:
    """A per-run appearance->character cache keyed by `TileFunctionMap.fingerprint` (reused verbatim).

    `confirm(crop_hash, reading)` records a brain-confirmed reading for one glyph-cell's fingerprint.
    `lookup(crop_hash)` returns the confirmed character for free, or None if never confirmed / no
    longer trusted (post-mismatch). WITHIN-RUN ONLY: this object holds no disk/network state and MUST
    be constructed fresh per run (the learning-boundary law) -- nothing in this module persists."""

    def __init__(self, tol: int = _DEFAULT_TOL) -> None:
        self._tol = tol
        self._tally: dict[int, Counter] = {}    # fingerprint -> {char: confirmation count}
        self._mismatches: dict[int, int] = {}   # fingerprint -> count of contradicting confirmations (telemetry)

    # -- keying (delegates to the exact tile-hashing scheme, not reimplemented) ----
    @staticmethod
    def fingerprint(glyph_cell: np.ndarray) -> int:
        """Perceptual hash of one glyph-sized cell -- `TileFunctionMap.fingerprint`, verbatim, applied
        to a caller-supplied cell (any size: Gen-1's 8x8, a 16x16 GBA glyph, whatever the detector or
        the brain's crop hands in). No glyph-specific logic here; identical pixels hash identically."""
        return TileFunctionMap.fingerprint(glyph_cell)

    # -- online build: brain-confirmed reads ---------------------------------------
    def confirm(self, crop_hash: int, reading: str) -> None:
        """Record ONE brain-confirmed reading for this glyph-cell's fingerprint: the brain looked at
        this exact crop (via `read_region`, or the Gate 2 harness's simulated oracle stand-in) and
        reported `reading`. Repeated confirmations accumulate (Counter, majority vote) -- the same
        self-correcting pattern as `TileFunctionMap.observe`, so a later contradicting confirmation can
        outvote a stale one instead of being silently discarded."""
        tally = self._tally.setdefault(crop_hash, Counter())
        if tally and reading not in tally:
            # A confirmed reading disagreeing with this key's prior confirmed reading(s) -- track it so
            # lookup() can honestly report contested state instead of trusting whichever came first.
            self._mismatches[crop_hash] = self._mismatches.get(crop_hash, 0) + 1
        tally[reading] += 1

    # -- free read ------------------------------------------------------------------
    def lookup(self, crop_hash: int) -> Optional[str]:
        """The free (no-brain-call) reading for this glyph-cell's fingerprint: the majority-confirmed
        character if this key (or a Hamming-near one) has ever been confirmed AND is not contested
        (mixed confirmations with no clear majority), else None -- never a fabricated guess, matching
        `FontTable.lookup`'s '?'-on-unknown / `TileFunctionMap.classify`'s None-on-novel discipline."""
        tally = self._exact_or_near(crop_hash)
        if tally is None or not tally:
            return None
        char, count = tally.most_common(1)[0]
        # A tied top-2 (e.g. one confirmation each of two different readings) is genuinely ambiguous --
        # honesty requires abstaining rather than picking one arbitrarily.
        if len(tally) > 1 and tally.most_common(2)[1][1] == count:
            return None
        return char

    def is_contested(self, crop_hash: int) -> bool:
        """True iff this key has ever received a confirmation that disagreed with an earlier one for
        the same key (telemetry / the invalidation story's audit trail -- a mismatch demotes `lookup()`
        to abstain-on-tie above, but the fact that it happened at all is worth being able to ask)."""
        return self._mismatches.get(crop_hash, 0) > 0

    def from_cache(self, crop_hash: int) -> bool:
        """True iff `lookup(crop_hash)` would serve for free (a confirmed, uncontested hit) -- lets a
        caller distinguish 'free lookup' from 'needs a fresh brain read', the exact distinction the
        design doc's `from_cache` output field and Gate 2's frac_free metric need."""
        return self.lookup(crop_hash) is not None

    # -- matching (mirrors TileFunctionMap._matches: exact fast path + tolerant fallback) --
    def _exact_or_near(self, crop_hash: int) -> Optional[Counter]:
        if crop_hash in self._tally:
            return self._tally[crop_hash]
        qi, qg = crop_hash >> _GRAD_BITS, crop_hash & _GRAD_MASK
        agg: Counter = Counter()
        found = False
        for k, c in self._tally.items():
            ki, kg = k >> _GRAD_BITS, k & _GRAD_MASK
            if abs(ki - qi) <= _INTEN_TOL and bin(kg ^ qg).count("1") <= self._tol:
                agg.update(c)
                found = True
        return agg if found else None

    def __len__(self) -> int:
        """Distinct glyph-cell keys confirmed so far this run (telemetry)."""
        return len(self._tally)
