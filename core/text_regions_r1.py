"""R1 text-region detector -- CACHE-DRIVEN, not texture-driven (`reports/2026-07-03-glyph-r1-cache-
driven-detection.md`). Amends R0 (`core/text_regions.py`, KILLED at Gate 1: 0.27 recall / 0.49
precision / 5 phantoms -- textured backdrops spoof edge-density just as well as real text).

R1 inverts the test: instead of asking "does this region look texturally like text" (a bottom-up
guess any textured surface can spoof), it asks "does this region contain tiles that are BITWISE
IDENTICAL to glyphs the brain has already confirmed this run" (a top-down match against ground truth
via `core.glyph_cache.GlyphCache`, reused unmodified). R1 therefore detects NOTHING NEW -- it can only
ever re-find glyphs the cache already knows (design doc section 1). It is a warm-cache amplifier, not
a cold-start solution (design doc sections 3/5).

Scan design (design doc section 2, pinned):
  - 2a: 8x8 tile-grid-aligned scan (matching `GlyphCache`'s cell size), not a sliding window -- this
    matches how tile-based 2D renderers actually produce the pixels the cache was confirmed against.
  - 2b: a grid cell is a HIT iff `cache.from_cache(fingerprint)` is True (a confirmed, uncontested
    entry; contested/tied entries already abstain via `GlyphCache.lookup`'s tie logic).
  - 2c: a candidate text region requires >= `_DEFAULT_MIN_RUN` (3) hit cells in an UNBROKEN run along
    one row (denoise against a lone hash collision); adjacent hit-rows/cols merge via
    `core.blob.connected_components` (reused, not reimplemented) into a bbox.

Snap-to-grid mitigation (design doc section 4.0, PINNED IMPLEMENTATION REQUIREMENT): live
`read_region` crops are only 31% mod-8-y-aligned (measured on the one live transcript on disk), so
cells fed to `GlyphCache.confirm()` must be sliced from the FULL FRAME at tile-grid boundaries that
enclose the caller's crop rect -- never sliced from the crop's own (possibly off-grid) pixel origin.
`snap_to_grid` + `confirm_region` implement this once, here, for any caller (the offline warmup
harness in `eval/score_glyph_r1.py`, or a future live wiring) -- not duplicated per caller.

World-agnostic: no game import, no font table, no hardcoded textbox geometry. `GlyphCache` and
`core.blob.connected_components` are reused verbatim; `TileFunctionMap.is_flat` (via `GlyphCache`'s
own fingerprint scheme) is reused as the generic "blank cell" gate instead of a game-specific pixel
threshold (`games/pokemon_red/textbox.py`'s `< 140` binarization is exactly the per-game assumption
this module avoids).

GATE: `eval/score_glyph_r1.py` scores this against the same-game warm/held-out split described in the
design doc section 4. See that module for the pinned recall/precision/phantom bar and the measured
result.
"""
from __future__ import annotations

import numpy as np

from core.blob import connected_components
from core.glyph_cache import GlyphCache
from core.tilemap import TileFunctionMap
from core.text_regions import TextRegion

_DEFAULT_CELL = 8          # matches GlyphCache's confirmed cell size (design doc 2a)
_DEFAULT_MIN_RUN = 3       # unbroken same-row hit-cell run required to seed a candidate (design doc 2c)


# -- snap-to-grid mitigation (design doc section 4.0) ------------------------------------------------

def snap_to_grid(rect: tuple[int, int, int, int], cell: int = _DEFAULT_CELL) -> tuple[int, int, int, int]:
    """Expand `rect` (x0, y0, x1, y1) outward to the enclosing mod-`cell` boundaries in frame
    coordinates -- the pinned mitigation for off-grid crop origins (only 31% of live `read_region`
    crops are mod-8-aligned in both axes, design doc section 4.0)."""
    x0, y0, x1, y1 = rect
    return (
        (x0 // cell) * cell,
        (y0 // cell) * cell,
        -(-x1 // cell) * cell,   # ceil division
        -(-y1 // cell) * cell,
    )


def confirm_region(cache: GlyphCache, frame, rect: tuple[int, int, int, int], reading: str, *,
                    cell: int = _DEFAULT_CELL) -> tuple[int, int]:
    """Confirm every non-blank grid cell overlapping `rect`, sliced from the FULL FRAME at
    tile-grid boundaries (never from the crop's own, possibly off-grid, pixel origin -- the pinned
    section-4.0 mitigation). `reading` is whatever the caller confirmed this rect as (a single shared
    placeholder for simulated/offline warmup, per design doc section 4a item 2; a brain's actual
    reported text for a future live caller).

    Returns (n_real_cells, n_new_cells): total non-blank cells confirmed, and how many of those had
    no prior confirmed reading (mirrors `eval/score_glyph_cache.py`'s `frame_confirmed_new` semantics,
    reused here so the warmup harness can apply Gate 2's exact confirming-frame rule unmodified)."""
    g = np.asarray(frame)
    H, W = g.shape[0], g.shape[1]
    x0, y0, x1, y1 = snap_to_grid(rect, cell)
    x0, y0 = max(0, x0), max(0, y0)
    x1, y1 = min(W, x1), min(H, y1)

    n_real = n_new = 0
    for y in range(y0, y1, cell):
        for x in range(x0, x1, cell):
            tile = g[y:y + cell, x:x + cell]
            if tile.shape[0] < cell or tile.shape[1] < cell:
                continue
            fp = GlyphCache.fingerprint(tile)
            if TileFunctionMap.is_flat(fp):
                continue   # blank/near-uniform cell -- not a glyph occurrence (generic, reused gate)
            n_real += 1
            if cache.lookup(fp) is None:
                n_new += 1
            cache.confirm(fp, reading)
    return n_real, n_new


# -- the R1 detector -----------------------------------------------------------------------------

def _row_runs(hit_row: list, min_run: int) -> set:
    """Column indices in `hit_row` (a list of bool) that belong to an unbroken run of >= min_run
    True values -- the section-2c denoise threshold, applied per row before any cross-row merge."""
    qualifying: set = set()
    run_start = None
    n = len(hit_row)
    for c in range(n + 1):
        v = hit_row[c] if c < n else False
        if v:
            if run_start is None:
                run_start = c
        else:
            if run_start is not None:
                if c - run_start >= min_run:
                    qualifying.update(range(run_start, c))
                run_start = None
    return qualifying


class GlyphRegionDetector:
    """R1 text-region (routing/foveation) detector -- see module docstring.

    World-agnostic: takes only pixels + a `GlyphCache` + a cell size (default 8px). No per-game
    constants, no textbox geometry, no font table. Advisory output only (a routing hint), never
    asserted as ground truth (mirrors R0's 7-slot contract, slot 2) -- and, per the design doc's
    section 1 honesty note, detects NOTHING the cache doesn't already know: a blank/cold cache
    detects nothing, by construction."""

    def __init__(self, cache: GlyphCache, *, cell: int = _DEFAULT_CELL, min_run: int = _DEFAULT_MIN_RUN) -> None:
        self.cache = cache
        self.cell = cell
        self.min_run = min_run

    def detect(self, frame) -> list[TextRegion]:
        """Candidate text-bearing bboxes in `frame` (HxW or HxWx3/4, ndarray or PIL Image). Never
        raises on a blank/empty frame -- returns [] (fail-safe: a miss is a miss, never a phantom)."""
        g = np.asarray(frame)
        H, W = g.shape[0], g.shape[1]
        cell = self.cell
        n_rows, n_cols = H // cell, W // cell
        if n_rows == 0 or n_cols == 0:
            return []

        hit_grid = [[False] * n_cols for _ in range(n_rows)]
        for r in range(n_rows):
            for c in range(n_cols):
                tile = g[r * cell:(r + 1) * cell, c * cell:(c + 1) * cell]
                fp = GlyphCache.fingerprint(tile)
                hit_grid[r][c] = self.cache.from_cache(fp)

        qualifying_cells: set = set()
        for r in range(n_rows):
            for c in _row_runs(hit_grid[r], self.min_run):
                qualifying_cells.add((c, r))   # (x, y) grid-cell coords, matches connected_components' convention

        comps = connected_components(qualifying_cells)
        out: list[TextRegion] = []
        for comp in comps:
            xs = [c for c, _ in comp]
            ys = [r for _, r in comp]
            gx0, gx1 = min(xs), max(xs) + 1
            gy0, gy1 = min(ys), max(ys) + 1
            bbox = (gx0 * cell, gy0 * cell, min(W, gx1 * cell), min(H, gy1 * cell))
            conf = len(comp) / ((gx1 - gx0) * (gy1 - gy0))
            out.append(TextRegion(bbox, float(conf)))
        out.sort(key=lambda reg: -reg.confidence)
        return out
