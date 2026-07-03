"""Text-region detector -- R0 candidate for "where on this frame is there likely glyph-shaped
content" (`reports/2026-07-05-glyph-read-design.md` section 4(a), the routing/foveation half of the
glyph-read design). NOT a recognizer: this never emits a character, never asserts truth on its own --
it is a cheap hint for where the brain should point `read_region` instead of guessing/tiling blind.

Algorithm (R0, per the design doc section 3(a), "per-row edge-density profile ... thresholded +
connected-components over the row-band"):
  1. ROW-BAND edge-density profile: for each `cell`-tall horizontal strip spanning the FULL frame
     width, sum the absolute horizontal+vertical pixel-to-pixel intensity change (edge magnitude),
     normalized per pixel of width. Small, densely-packed glyph rows (letters, digits, punctuation
     packed edge-to-edge) light up this profile; open scenery or a large sprite's interior does not.
  2. Threshold the row profile into a boolean row-band mask (which horizontal strips look
     glyph-textured).
  3. `core.blob.connected_components` (reused, not reimplemented) merges contiguous flagged rows into
     full-frame-width candidate bands.

Measured directly against the hand-labeled fixture (`eval/fixtures/text_regions/labels.json`) before
picking this design -- two alternatives were tried and rejected first:
  * A per-CELL edge/gradient threshold alone (8x8 blocks, scored independently) does not separate
    in-box from out-of-box cells well enough to be useful: glyph texture is a ROW-level phenomenon
    (sustained density across a full text line), not reliably a per-cell one at 8px granularity.
  * Recovering x-extent within a flagged row-band via a second per-cell connected-components pass
    (splitting one row-band into several narrower boxes) fragmented single paragraphs into many
    low-precision candidates without a recall gain.
  Full-frame-width row bands (this module) scored best of the three on the fixture -- but per
  `eval/score_text_regions.py`'s measured result, still well short of the pinned Gate 1 bar. See that
  module for the actual numbers; this is reported as a FAIL, not tuned further to pass.

Output is a bbox list + a confidence per box (mean row edge-density, normalized) -- an EMPTY list on a
frame with no texture spikes (fail-safe: no candidate is a miss, not a phantom). World-agnostic: no
game import, no hardcoded textbox geometry, cell size is a constructor parameter (default 8px, the
common GB/GBA glyph pitch, but not assumed to be Pokemon's specific textbox layout).

GATE: `eval/score_text_regions.py` scores this against `eval/fixtures/text_regions/` (the pre-registered
Gate 1 fixture, ≥30 hand-labeled frames from ≥3 sweep games + distractors). See that module for the
pinned recall/precision/phantom bar and the measured result.
"""
from __future__ import annotations

import numpy as np

from core.blob import connected_components

_DEFAULT_CELL = 8              # common fixed-pitch console glyph size (GB/GBA); not a Pokemon-only assumption
_DEFAULT_ROW_THRESH = 20.0     # per-pixel-width row edge-density threshold -- see row_edge_density() below
_DEFAULT_MIN_ROWS = 2          # drop bands shorter than this many row-cells (denoise)


def _gray(frame) -> np.ndarray:
    a = np.asarray(frame)
    return a[..., :3].mean(axis=2).astype(np.float32) if a.ndim == 3 else a.astype(np.float32)


def row_edge_density(g: np.ndarray, *, cell: int = _DEFAULT_CELL) -> np.ndarray:
    """Per-row-band edge density profile: for each `cell`-tall strip spanning the full frame width,
    the edge-magnitude sum (horizontal + vertical absolute pixel-to-pixel difference) normalized by
    width. One value per row-band (length = H // cell). Pure numpy, Sobel-free simple differencing."""
    H, W = g.shape
    n_rows = H // cell
    profile = np.zeros(n_rows, dtype=np.float32)
    for r in range(n_rows):
        band = g[r * cell:(r + 1) * cell, :]
        gx = np.abs(np.diff(band, axis=1)).sum()
        gy = np.abs(np.diff(band, axis=0)).sum()
        profile[r] = (gx + gy) / W if W else 0.0
    return profile


class TextRegion:
    __slots__ = ("bbox", "confidence")

    def __init__(self, bbox: tuple[int, int, int, int], confidence: float):
        self.bbox = bbox            # (x0, y0, x1, y1) in source-frame pixels
        self.confidence = confidence

    def to_dict(self) -> dict:
        return {"bbox": list(self.bbox), "confidence": round(self.confidence, 3)}

    def __repr__(self):
        return f"TextRegion(bbox={self.bbox} conf={self.confidence:.2f})"


class TextRegionDetector:
    """R0 text-region (routing/foveation) detector -- see module docstring.

    World-agnostic: takes only pixels + a cell size (default 8px). No per-game constants, no textbox
    geometry, no font table. Advisory output only (a routing hint the brain's `read_region` targets),
    never asserted as ground truth (per the design doc's 7-slot contract, slot 2)."""

    def __init__(self, *, cell: int = _DEFAULT_CELL, row_thresh: float = _DEFAULT_ROW_THRESH,
                 min_rows: int = _DEFAULT_MIN_ROWS) -> None:
        self.cell = cell
        self.row_thresh = row_thresh
        self.min_rows = min_rows   # drop bands shorter than this many row-cells (denoise)

    def detect(self, frame) -> list[TextRegion]:
        """Candidate text-bearing bboxes in `frame` (HxW or HxWx3/4, ndarray or PIL Image). Never
        raises on a blank/empty frame -- returns [] (fail-safe: a miss is a miss, never a phantom)."""
        g = _gray(frame)
        H, W = g.shape
        if H < self.cell or W < self.cell:
            return []

        # 1) row-band profile -> which horizontal strips look glyph-textured.
        profile = row_edge_density(g, cell=self.cell)
        flagged_rows = profile >= self.row_thresh
        if not flagged_rows.any():
            return []

        # 2) merge contiguous flagged rows into full-width bands. `core.blob.connected_components`
        # (reused, not reimplemented) on the 1-D row-index set degenerates to run-length grouping.
        row_idx = {(0, int(r)) for r in np.where(flagged_rows)[0]}
        comps = connected_components(row_idx)

        out: list[TextRegion] = []
        for comp in comps:
            rs = sorted(r for _, r in comp)
            if len(rs) < self.min_rows:
                continue
            y0, y1 = rs[0] * self.cell, min(H, (rs[-1] + 1) * self.cell)
            conf = float(profile[rs].mean() / (255.0 * 2 * self.cell))   # normalized to a ~[0, ~1] scale
            out.append(TextRegion((0, y0, W, y1), conf))
        out.sort(key=lambda r: -r.confidence)
        return out
