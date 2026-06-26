"""ScrollingLocalizer -- ego-motion-compensated wrapper for avatar localizers.

For follow-camera (scrolling) games, raw frame diffs are dominated by camera pan, not avatar motion.
This wrapper:
  1. Estimates per-step ego-motion via core.egomotion.best_shift.
  2. Warps the previous frame by (dx, dy) to cancel the camera pan.
  3. Feeds the motion RESIDUAL (after cancellation) to an inner localizer (Bayes or blob).

Research note: for flat pixel art at 160x144 best_shift/phase-correlation beats ORB/homography.
The wrapper stacks on top of any localizer that accepts (frame, commanded_dir).

numpy + PIL only. No cv2.
"""
from __future__ import annotations

from typing import Optional, Protocol

import numpy as np
from PIL import Image

from core.egomotion import best_shift

_NW, _NH = 160, 144
_MAX_SHIFT = 16   # search range for ego-motion (px)
_STEP = 1
_TIE_BREAK = 0.1  # prefer smaller shifts on ties (stationary frames -> (0,0))


def _gray(frame) -> np.ndarray:
    a = np.asarray(frame)
    g = a[..., :3].mean(2) if a.ndim == 3 else a.astype(np.float32)
    if g.shape != (_NH, _NW):
        g = np.asarray(Image.fromarray(g.astype(np.uint8)).resize((_NW, _NH), Image.BILINEAR), np.float32)
    return g.astype(np.float32)


def _shift_frame(frame: np.ndarray, dx: int, dy: int) -> np.ndarray:
    """Shift frame by (dx, dy) with zero fill."""
    H, W = frame.shape
    out = np.zeros_like(frame)
    w, h = W - abs(dx), H - abs(dy)
    out[max(0, dy):max(0, dy) + h, max(0, dx):max(0, dx) + w] = \
        frame[max(0, -dy):max(0, -dy) + h, max(0, -dx):max(0, -dx) + w]
    return out


def _synthesize_residual_frame(prev_aligned: np.ndarray, cur: np.ndarray) -> np.ndarray:
    """Create an RGB frame whose pixel values represent motion residual magnitude.

    We return a 3-channel array (copying residual to all channels) so it passes through
    inner localizers that expect RGB input -- the inner localizer's bg-subtraction then
    sees only the ego-compensated motion.
    """
    residual = np.abs(cur - prev_aligned).astype(np.uint8)
    return np.stack([residual, residual, residual], axis=2)


class _LocalizerProto(Protocol):
    def update(self, frame, commanded_dir=None): ...
    def reset(self): ...


class ScrollingLocalizer:
    """Wraps any avatar localizer; compensates camera ego-motion before passing frames."""

    def __init__(self, inner: _LocalizerProto):
        self.inner = inner
        self._prev_gray: Optional[np.ndarray] = None

    def reset(self):
        self.inner.reset()
        self._prev_gray = None

    def update(self, frame, commanded_dir: Optional[str] = None):
        """Returns whatever the inner localizer returns: (col, row, conf) or None."""
        cur = _gray(frame)

        if self._prev_gray is None:
            self._prev_gray = cur
            return self.inner.update(frame, commanded_dir)

        # 1. Estimate ego-motion
        fd, best_diff, dx, dy = best_shift(
            self._prev_gray, cur,
            max_shift=_MAX_SHIFT, step=_STEP, tie_break=_TIE_BREAK
        )

        # 2. Align previous frame to current viewpoint
        prev_aligned = _shift_frame(self._prev_gray, dx, dy)

        # 3. Build residual frame (ego-compensated motion)
        residual_rgb = _synthesize_residual_frame(prev_aligned, cur)

        self._prev_gray = cur

        # 4. Pass residual to inner localizer
        return self.inner.update(residual_rgb, commanded_dir)
