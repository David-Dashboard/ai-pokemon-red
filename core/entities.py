"""EntityDetector — foreground-blob entity detection for the lean worlds.

Produces a list of {bbox, centroid} dicts per frame by subtracting a rolling
background and running connected-component segmentation. Filters out:
  - the blob overlapping the known avatar cell (passed in as pixel coords)
  - blobs entirely inside a HUD region (if supplied)
  - blobs below min_area

General-purpose; no game-specific knowledge. numpy only.
"""
from __future__ import annotations

from typing import Optional

import numpy as np

from core.blob import RollingBg, segment_blobs

# type alias to keep signatures readable
_Box = tuple[int, int, int, int]  # x0, y0, x1, y1


def _overlaps(bx0: int, by0: int, bx1: int, by1: int,
              rx0: float, ry0: float, rx1: float, ry1: float) -> bool:
    """True when the blob bbox has any overlap with region (rx0,ry0,rx1,ry1)."""
    return bx0 <= rx1 and bx1 >= rx0 and by0 <= ry1 and by1 >= ry0


class EntityDetector:
    """Per-run foreground entity detector.

    Parameters
    ----------
    connectivity : int
        4 (default, cardinal) or 8 (diagonal too).
    min_area : int
        Drop blobs smaller than this (pixels).
    avatar_radius : float
        A blob whose centroid is within this many pixels of `avatar_px` is
        treated as the avatar and dropped.
    hud_region : optional (x0, y0, x1, y1)
        Blobs whose bbox is *entirely* inside this region are dropped (HUD strip).
    bg_window : int
        Rolling-median window size for RollingBg.
    thresh : float
        Foreground magnitude threshold.
    """

    def __init__(
        self,
        *,
        connectivity: int = 4,
        min_area: int = 16,
        avatar_radius: float = 20.0,
        hud_region: Optional[_Box] = None,
        bg_window: int = 6,
        thresh: float = 15.0,
    ) -> None:
        self.connectivity = connectivity
        self.min_area = min_area
        self.avatar_radius = avatar_radius
        self.hud_region = hud_region
        self.thresh = thresh
        self._bg = RollingBg(window=bg_window)

    def detect(
        self,
        frame: np.ndarray,
        avatar_px: Optional[tuple[float, float]] = None,
    ) -> list[dict]:
        """Run detection on one frame.

        Parameters
        ----------
        frame : H x W x 3 uint8 array (RGB).
        avatar_px : (cx, cy) pixel coords of the avatar centre, or None.

        Returns list of {"bbox": [x0,y0,x1,y1], "centroid": [cx,cy]}.
        """
        blobs = segment_blobs(
            frame, bg=self._bg,
            thresh=self.thresh,
            min_area=self.min_area,
            connectivity=self.connectivity,
        )
        if not blobs:
            return []

        out = []
        hud = self.hud_region
        r = self.avatar_radius
        for b in blobs:
            # drop if centroid is within avatar_radius of known avatar pixel
            if avatar_px is not None:
                dist = np.hypot(b.cx - avatar_px[0], b.cy - avatar_px[1])
                if dist <= r:
                    continue
            # drop if bbox is entirely inside the HUD region
            if hud is not None and _overlaps(b.x0, b.y0, b.x1, b.y1, *hud):
                # only drop if *fully* inside
                if b.x0 >= hud[0] and b.y0 >= hud[1] and b.x1 <= hud[2] and b.y1 <= hud[3]:
                    continue
            out.append({"bbox": [b.x0, b.y0, b.x1, b.y1], "centroid": [b.cx, b.cy]})
        return out

    def reset(self) -> None:
        """Clear background history (e.g. on scene change)."""
        self._bg = RollingBg(window=self._bg.window)
