"""StationaryMovers (P2): mover segmentation for 3D worlds -- "what is here that moves and isn't me".

Design: reports/2026-07-04-vizdoom-3d-floor-design.md S1.2 (7-slot North-Eye contract) + AMENDMENT A1
(S1.2 is unchanged by A1; only the gate SCENARIO was re-pinned, per A1.1's finding that the primitive
itself was honest -- `basic_gate`'s standing monster simply never moved).

Gate honesty (design S1.2 slot 2i, the load-bearing rule): this primitive is computed ONLY on frame
pairs the caller asserts are ego-stationary. It does not re-derive "am I turning" itself -- the caller
passes P1's own YawReading (core.yaw_flow.YawBandFlow) for the pair, and the gate is:

    ego-stationary  <=>  no motion action was issued between the frames
                         AND P1.direction == "none" (confidently NOT turning)

If P1 reports a real direction ("left"/"right") or None (can't tell), the gate is CLOSED and this
returns None with reason "not ego-stationary" -- NEVER a fabricated mover list. This is the anti-drift
guard from the design doc's table: a P2 that ignores the gate and free-runs on turning frames is
exactly the probe's dead RollingBg failure mode reborn (40+ phantom blobs/frame under camera motion).

Threshold derivation (design S1.2 slot 4 -- "pinned from fixture data ... not free parameters"):
this module's pix_t=25 (/255) and min_area=30 are RE-DERIVED here on eval/fixtures/vizdoom_movers/
(curated from runs/vizdoom_precheck/dtc_mixed/ per AMENDMENT A1.5 -- the fresh, action-log-aligned dtc
capture; the 2026-07-02 probe capture has a known one-frame misalignment and is not a valid fixture
source). Derivation (scratch analysis, not committed -- the fixture set + this module's tests ARE the
committed artifact): a pix_t/min_area sweep over dtc_mixed's 110 consecutive frame pairs, split into
IDLE pairs (37) and TURN pairs (73) by the logged action:

    pix_t  min_area | stationary comp-count median | turning comp-count median
    15     30       | 1.0                           | 24.0
    20     30       | 1.0                           | 16.0
    25     30       | 1.0                           | 13.0   <- picked (design's own starting point,
    30     30       | 1.0                           |  3.0      S1.2 slot 4; separation still clean)

pix_t=25/min_area=30 reproduces the design doc's S1.3 finding almost exactly on this independent,
alignment-clean capture (stationary comp-count median ~1 vs turning ~13, a >10x separation -- the
design's own probe measured medians of 4.5 vs 19 on a *different*, since-superseded dtc capture).
Lowering pix_t or min_area narrows the separation (turning medians rise toward stationary as more
transient warp-diff pixels clear the bar); this is the floor at which the gap is still wide open.
ATTACK is deliberately EXCLUDED from the "ego-stationary" fixture pairs used for this derivation (it
does not turn the camera, so it IS ego-stationary by the design's own definition -- A1.3: "ego-
stationary for P2 = simply not turning") -- but ATTACK pairs in dtc_mixed show large diff components
from the weapon's own muzzle-flash brightening the whole lower-frame (frame mean jumps ~75->81),
which is an ego-generated artifact, not a "mover" in any useful sense. P2 does not and cannot know the
difference (meaning-free blob reporting, per the design's anti-drift table); this is recorded as a
known artifact of the ATTACK action, not filtered specially. The committed fixture set therefore
draws its `stationary_movers`/`stationary_empty` categories only from IDLE pairs; `turning` pairs (P1
reports a direction) exercise the None-gate.

R0: numpy + core.blob._label_bfs (reused per the design's explicit instruction: "reuse the labeling
pattern of core/blob.py::_label_bfs; do NOT reuse RollingBg, which is structurally dead in 3D").
"""
from __future__ import annotations

from typing import NamedTuple, Optional

import numpy as np

from core.blob import _label_bfs
from core.yaw_flow import YawReading

PIX_T = 25.0          # 0-255 grayscale abs-diff threshold; derived above on eval/fixtures/vizdoom_movers/
MIN_AREA = 30          # px; components smaller than this are dropped as noise
MAX_MERGE_DIST = 12    # px; centroids closer than this are merged (near-overlapping boxes, design slot 3)
TOP_K = 5              # design S1.2 slot 3: "top-K (K=5) by area"


class Mover(NamedTuple):
    """One reported mover (design S1.2 slot 5). azimuth_px is signed px offset of the bbox centroid
    from screen-center (negative = left of center, positive = right); azimuth_deg is None until a
    caller supplies P1's within-run px-per-degree calibration (core.yaw_flow.calibrate) -- this
    module never invents a scale constant of its own."""
    bbox: tuple[int, int, int, int]     # (x0, y0, x1, y1), inclusive pixel bounds
    centroid: tuple[float, float]       # (cx, cy)
    area: int
    azimuth_px: float
    azimuth_deg: Optional[float]
    confidence: float


def _gray(frame) -> np.ndarray:
    a = np.asarray(frame)
    if a.ndim == 3:
        return a[..., :3].mean(2).astype(np.float32)
    return a.astype(np.float32)


def _merge_overlapping(boxes: list[dict]) -> list[dict]:
    """Merge components whose centroids are within MAX_MERGE_DIST px (design slot 3: "merge near-
    overlapping boxes"). Greedy: repeatedly merge the closest pair until none are close enough."""
    boxes = list(boxes)
    merged = True
    while merged and len(boxes) > 1:
        merged = False
        for i in range(len(boxes)):
            for j in range(i + 1, len(boxes)):
                bi, bj = boxes[i], boxes[j]
                dist = float(np.hypot(bi["cx"] - bj["cx"], bi["cy"] - bj["cy"]))
                if dist <= MAX_MERGE_DIST:
                    x0 = min(bi["x0"], bj["x0"]); y0 = min(bi["y0"], bj["y0"])
                    x1 = max(bi["x1"], bj["x1"]); y1 = max(bi["y1"], bj["y1"])
                    area = bi["area"] + bj["area"]
                    cx = (bi["cx"] * bi["area"] + bj["cx"] * bj["area"]) / area
                    cy = (bi["cy"] * bi["area"] + bj["cy"] * bj["area"]) / area
                    new = {"x0": x0, "y0": y0, "x1": x1, "y1": y1, "area": area, "cx": cx, "cy": cy}
                    boxes = [b for k, b in enumerate(boxes) if k not in (i, j)] + [new]
                    merged = True
                    break
            if merged:
                break
    return boxes


def stationary_movers(
    prev_frame,
    cur_frame,
    yaw_reading: YawReading,
    *,
    pix_t: float = PIX_T,
    min_area: int = MIN_AREA,
    deg_per_px: Optional[float] = None,
) -> Optional[list[Mover]]:
    """R0 StationaryMovers. `prev_frame`/`cur_frame` are RGB or grayscale arrays (same shape).

    `yaw_reading`: the P1 YawBandFlow reading FOR THIS SAME PAIR -- the gate honesty check (design
    slot 2i). Returns None (gate CLOSED, never a fabricated list) unless
    `yaw_reading.direction == "none"` (P1 confidently reports no ego-rotation). A P1 direction of
    "left"/"right" (real turn) or None (can't tell) both close the gate -- three-valued honesty
    upstream propagates to a hard None downstream, exactly the design's point: an ambiguous P1 reading
    must not be silently treated as "safe to assume stationary".

    `deg_per_px`: optional within-run calibration scale (core.yaw_flow.calibrate's output) to convert
    azimuth_px -> azimuth_deg. None (the default) leaves azimuth_deg unset on every Mover -- this
    module never invents its own scale constant (learning-boundary law: calibration is run-local,
    supplied by the caller, never hand-set here).

    Returns:
        None       -- gate closed (yaw_reading says ego-motion is happening or unclear).
        []         -- gate open, confidently nothing moving.
        [Mover...] -- gate open, up to TOP_K movers by area, largest first.
    """
    if yaw_reading.direction != "none":
        return None   # gate CLOSED: real turn, or P1 itself could not tell -- never guess

    ga = _gray(prev_frame)
    gb = _gray(cur_frame)
    if ga.shape != gb.shape:
        return None   # can't diff mismatched frames -- fail closed, not a guess

    diff = np.abs(ga - gb)
    mask = diff > pix_t
    if not mask.any():
        return []   # confidently nothing moving (distinct from the gate-closed None)

    labels, n = _label_bfs(mask, connectivity=4)
    boxes: list[dict] = []
    h, w = ga.shape
    for lbl in range(1, n + 1):
        ys, xs = np.where(labels == lbl)
        area = int(len(xs))
        if area < min_area:
            continue
        boxes.append({
            "x0": int(xs.min()), "y0": int(ys.min()), "x1": int(xs.max()), "y1": int(ys.max()),
            "area": area, "cx": float(xs.mean()), "cy": float(ys.mean()),
        })
    if not boxes:
        return []

    boxes = _merge_overlapping(boxes)
    boxes.sort(key=lambda b: b["area"], reverse=True)
    boxes = boxes[:TOP_K]

    screen_cx = w / 2.0
    movers = []
    for b in boxes:
        azimuth_px = b["cx"] - screen_cx
        azimuth_deg = azimuth_px / deg_per_px if deg_per_px else None
        # confidence: area-based, saturating -- a bigger clean blob is a more trustworthy mover report.
        # R0 sketch (no fixture-pinned confidence floor specified by the design beyond min_area itself).
        confidence = float(min(1.0, b["area"] / 200.0))
        movers.append(Mover(
            bbox=(b["x0"], b["y0"], b["x1"], b["y1"]),
            centroid=(b["cx"], b["cy"]),
            area=b["area"],
            azimuth_px=float(azimuth_px),
            azimuth_deg=azimuth_deg,
            confidence=confidence,
        ))
    return movers
