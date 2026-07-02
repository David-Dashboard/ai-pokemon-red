"""StaticObjectDetector -- static-saliency candidate detection (layer (a) of the referential-grounding
decomposition, `reports/2026-07-03-referential-grounding-design.md`).

Finds discrete on-screen candidates from a SINGLE frame's pixels -- no motion diffing (that's
`core/entities.py`/`core/blob.py`'s RollingBg job, and it is blind to a static object sitting on a table),
no RAM, no hardcoded palette. The saliency signal is GENERAL colour-contrast: a pixel that stands out
chromatically from its local tile neighbourhood is "salient" the same way a red Poke Ball pops off a grey
table OR a blue chest pops off a brown floor -- the direction of the contrast is never assumed.

Pipeline: per-tile local-distinctiveness mask -> `core.blob.connected_components` (reused, not
reimplemented) -> per-blob descriptor (bbox/centroid/area/mean colour). Pure numpy/PIL, R0 realizer,
world-agnostic (no Pokemon/tile-size assumption beyond a configurable tile size, defaulted to the common
GB/GBC 16px metatile but overridable per world).

Candidates are ADVISORY, appearance-only -- naming/identity is layer (b), out of scope here (ADR-002
gated). This module NEVER returns a phantom by construction if it sees nothing salient: an empty frame or
a frame with no local contrast returns []. Fail-safe, no invented detections.

GATE RESULT (verified, `eval/score_static_objects.py` against `eval/fixtures/static_objects_pokeball/`):
KILL CHEAP. This GENERAL local-colour-contrast saliency (no hardcoded palette) does NOT clear the design
doc's gate (recall>=0.9, precision>=0.8, phantoms==0) at bbox-IoU>=0.3: recall 0.0, precision 0.0, 236-341
phantom candidates across 12 distractor frames depending on config. Two concrete, GENERAL, non-Pokemon
failure modes were found (not fixed here, because fixing them the way that works IS the Pokemon-specific
hack the gate report calls out):
  1. A uniformly-coloured object's INTERIOR is not locally distinct from ITS OWN block median once it
     fills a saliency block -- only its EDGE lights up, producing a hollow ring that 4-connected
     components fragments into several small pieces (`fill_holes` -- a generic morphological fix --
     recovers the filled blob, but then adjacent objects merge into one blob through their shared
     connective "aura", collapsing 3 distinct balls into 1 candidate spanning all three).
  2. GB/GBC tile-grid pixel art is FULL of naturally repeating, equal-sized, grid-aligned elements
     (grass tufts, brick courses, dithering blocks) -- `group_equal_collinear` (a general "N equal
     objects in a row" shape prior, deliberately NOT tied to the number 3 or to red) is just as likely to
     fire on a grass patch or a Kirby platform edge as on the actual Poke Ball table, so it does not
     recover precision once distractor frames are diverse (it did on the original 3-frame probe only
     because that probe had no non-lab distractors).
The only heuristic that DOES separate the balls from the noise is hardcoding the saturated-red RGB test
from the design doc's Channel B probe -- which is explicitly Pokemon/palette-specific and was
DELIBERATELY NOT lifted into this module (see the PR / gate report). `group_equal_collinear` is kept
here as a general, documented, honestly-non-sufficient primitive for a future R1 attempt; it is not
wired into `StaticObjectDetector.detect()`'s default output.
"""
from __future__ import annotations

import numpy as np

from core.blob import connected_components

_DEFAULT_TILE = 16


def _gray(frame) -> np.ndarray:
    a = np.asarray(frame)
    return a[..., :3].mean(axis=2).astype(np.float32) if a.ndim == 3 else a.astype(np.float32)


def _rgb(frame) -> np.ndarray:
    a = np.asarray(frame)
    if a.ndim == 2:
        a = np.stack([a, a, a], axis=-1)
    return a[..., :3].astype(np.float32)


def local_saliency_mask(frame, *, tile: int = _DEFAULT_TILE, chroma_thresh: float = 28.0) -> np.ndarray:
    """A GENERAL static saliency mask: pixels whose colour stands out from their local tile's own
    median colour, by more than `chroma_thresh` (Euclidean RGB distance).

    Splits the frame into `tile`x`tile` blocks (a GB/GBC metatile by default, but any world can pass its
    own grid size) and, per block, computes the block's median RGB (the "background" colour of that
    patch of scenery -- floor, wall, grass, whatever it is). A pixel far from ITS OWN block's median is
    locally distinctive: a red ball on a grey table stands out from the table's median grey; a blue chest
    on a brown floor stands out from the floor's median brown. No colour is privileged -- direction and
    hue of the contrast are never assumed, only its MAGNITUDE.

    This is deliberately per-block (not whole-frame) distinctiveness: a whole-frame outlier test would
    also flag an entire differently-coloured ROOM half, which isn't what "a small object on a background"
    means. Local scope keeps it a small-object detector.

    Returns a boolean HxW mask. Pure numpy."""
    rgb = _rgb(frame)
    H, W, _ = rgb.shape
    mask = np.zeros((H, W), dtype=bool)
    for y0 in range(0, H, tile):
        for x0 in range(0, W, tile):
            block = rgb[y0:y0 + tile, x0:x0 + tile]
            if block.size == 0:
                continue
            med = np.median(block.reshape(-1, 3), axis=0)
            dist = np.linalg.norm(block - med, axis=-1)
            mask[y0:y0 + block.shape[0], x0:x0 + block.shape[1]] = dist > chroma_thresh
    return mask


def fill_holes(mask: np.ndarray) -> np.ndarray:
    """Standard GENERAL morphological fill-holes: flood-fill the background from the frame border, then
    any UNREACHED background pixel is an enclosed hole -> fill it in. A locally-distinctive object's
    EDGE often lights up (high contrast against the background) while its uniform-coloured INTERIOR does
    not (it's not distinct from ITS OWN dominant colour once the object fills most of a saliency block) --
    producing a hollow ring rather than a filled blob. This is a standard image-processing primitive
    (not shape- or colour-specific to any one object), used here to turn "an outline was detected" into
    "a solid candidate region", the same way it would for any edge-only detector. Pure numpy BFS (no
    scipy.ndimage.binary_fill_holes, not in the frozen env)."""
    H, W = mask.shape
    if H == 0 or W == 0:
        return mask
    from collections import deque
    reached = np.zeros_like(mask)
    dq: deque = deque()

    def _seed(y, x):
        if not mask[y, x] and not reached[y, x]:
            reached[y, x] = True
            dq.append((y, x))

    for x in range(W):
        _seed(0, x); _seed(H - 1, x)
    for y in range(H):
        _seed(y, 0); _seed(y, W - 1)
    while dq:
        y, x = dq.popleft()
        for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            ny, nx = y + dy, x + dx
            if 0 <= ny < H and 0 <= nx < W and not mask[ny, nx] and not reached[ny, nx]:
                reached[ny, nx] = True
                dq.append((ny, nx))
    return mask | ~reached


class Candidate:
    __slots__ = ("bbox", "centroid", "area", "mean_rgb")

    def __init__(self, bbox: tuple[int, int, int, int], centroid: tuple[float, float],
                 area: int, mean_rgb: tuple[float, float, float]):
        self.bbox = bbox
        self.centroid = centroid
        self.area = area
        self.mean_rgb = mean_rgb

    def to_dict(self) -> dict:
        return {"bbox": list(self.bbox), "centroid": list(self.centroid),
                "area": self.area, "mean_rgb": [round(c, 1) for c in self.mean_rgb]}

    def __repr__(self):
        return f"Candidate(bbox={self.bbox} area={self.area} rgb={self.mean_rgb})"


class StaticObjectDetector:
    """Per-frame static-candidate detector: local colour-saliency -> connected components -> candidates.

    General-purpose; no game-specific palette or shape rule lives here (see the module docstring and the
    gate report for why a Pokemon-specific precision heuristic was deliberately kept OUT of this class).
    """

    def __init__(self, *, tile: int = _DEFAULT_TILE, chroma_thresh: float = 28.0,
                 min_area: int = 6, max_area_frac: float = 0.05) -> None:
        self.tile = tile
        self.chroma_thresh = chroma_thresh
        self.min_area = min_area
        self.max_area_frac = max_area_frac   # drop blobs covering an implausibly large frame fraction

    def detect(self, frame) -> list[Candidate]:
        """Static candidates in `frame` (H x W x 3 uint8, or PIL Image). Never raises on an empty/blank
        frame -- returns [] (fail-safe: no candidate rather than a fabricated one)."""
        rgb = _rgb(frame)
        H, W, _ = rgb.shape
        if H == 0 or W == 0:
            return []
        mask = local_saliency_mask(rgb, tile=self.tile, chroma_thresh=self.chroma_thresh)
        if not mask.any():
            return []
        mask = fill_holes(mask)
        pixel_set = {(int(x), int(y)) for y, x in zip(*np.where(mask))}
        comps = connected_components(pixel_set)
        max_area = int(H * W * self.max_area_frac)
        out: list[Candidate] = []
        for comp in comps:
            area = len(comp)
            if area < self.min_area or area > max_area:
                continue
            xs = np.array([p[0] for p in comp]); ys = np.array([p[1] for p in comp])
            x0, y0, x1, y1 = int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())
            cx, cy = float(xs.mean()), float(ys.mean())
            mean_rgb = tuple(float(c) for c in rgb[ys, xs].mean(axis=0))
            out.append(Candidate((x0, y0, x1, y1), (cx, cy), area, mean_rgb))
        return out


def group_equal_collinear(candidates: list[Candidate], *,
                           area_tol: float = 0.25, row_tol: float = 4.0) -> list[list[Candidate]]:
    """Group candidates that are roughly EQUAL AREA and COLLINEAR (same row or column, within
    `row_tol` px) -- a general "repeated identical objects laid out in a line" shape prior (a row of
    items on a shelf/table, a line of coins, etc.), not tied to any one object's colour or the number
    three. Returns groups of size >= 2; ungrouped candidates are not included in any output group (the
    caller decides what to do with singletons).

    NOTE (gate-relevant, see the score_static_objects.py report): this heuristic recovers precision on
    the Poke-Ball-table frames because the balls happen to be equal-area and row-aligned -- but nothing
    here hardcodes "three" or "red"; it is a general recurring-layout prior. Whether it generalises to
    other games' objects (a single item, an irregular cluster) is exactly the open question the gate
    report evaluates honestly."""
    groups: list[list[Candidate]] = []
    used: set[int] = set()
    for i, a in enumerate(candidates):
        if i in used:
            continue
        group = [a]
        group_idx = [i]
        for j, b in enumerate(candidates):
            if j <= i or j in used:
                continue
            if a.area == 0 or b.area == 0:
                continue
            area_ratio = abs(a.area - b.area) / max(a.area, b.area)
            same_row = abs(a.centroid[1] - b.centroid[1]) <= row_tol
            same_col = abs(a.centroid[0] - b.centroid[0]) <= row_tol
            if area_ratio <= area_tol and (same_row or same_col):
                group.append(b)
                group_idx.append(j)
        if len(group) >= 2:
            groups.append(group)
            used.update(group_idx)
    return groups
