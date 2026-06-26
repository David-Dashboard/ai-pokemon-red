"""AvatarLocalizer -- find/track the player avatar from pixels, grounded by CONTROL.

The avatar is not the brightest or the biggest mover; it is *the thing your buttons move* (the North Eye
binding principle: ground by action<->sensor correlation, not appearance/magnitude). Each commanded step,
accumulate a per-cell heatmap of the motion that is EXPLAINED BY the commanded direction; the peak is the
avatar (enemies/animation move uncommanded -> they wash out). The heatmap DECAYS, so it tracks the avatar's
*recent* position and self-corrects (no unbounded drift, no fragile template tracking). When there is no recent
commanded motion the avatar is stationary -> HOLD the last position. Validated to ~1-15px vs hand labels.

Output contract (North Eye): (col, row, confidence), or None when never localized. Never fabricates.
Realizer rung R0 (numpy only). RAM is never touched -- pixels + the agent's own button stream.
"""
from __future__ import annotations

from typing import Optional

import numpy as np
from PIL import Image

from core.grid import DELTA

_NW, _NH = 160, 144          # native GB resolution (sprites are ~8-16px; don't blur them away)
_CELL = 10                   # heatmap cell size (px) -> a 14x16 grid
_KSHIFTS = (3, 6, 10, 14)    # candidate per-step displacements that could explain a commanded move (px)
_DECAY = 0.7                 # heatmap memory: ~3-5 recent commanded steps (tracks the CURRENT position)
_PEAK = 2.6                  # min peak/mean ratio to treat the heatmap as a confident fix
_JUMP = 30.0                 # px: a confident peak leaping >this from the held pos is suspected animation,
                             # not a real step (1 cell ~16-22px) -> reject unless it REPEATS (room change)


def _gray(frame):
    a = np.asarray(frame)
    g = a[..., :3].mean(2) if a.ndim == 3 else a.astype(np.float32)
    if g.shape != (_NH, _NW):
        g = np.asarray(Image.fromarray(g.astype(np.uint8)).resize((_NW, _NH), Image.BILINEAR), np.float32)
    return g.astype(np.float32)


def _shift(a, dx, dy):
    """Shift `a` by (dx,dy) with zero fill (no wrap)."""
    out = np.zeros_like(a)
    w, h = _NW - abs(dx), _NH - abs(dy)
    out[max(0, dy):max(0, dy) + h, max(0, dx):max(0, dx) + w] = \
        a[max(0, -dy):max(0, -dy) + h, max(0, -dx):max(0, -dx) + w]
    return out


class AvatarLocalizer:
    def __init__(self):
        self.prev = None
        self.pos: Optional[tuple] = None         # (col,row) last fix, held through stationary spells
        self._pending = None                     # a far peak seen once: commit only if it REPEATS (vs a 1-frame outlier)
        self.heat = np.zeros((_NH // _CELL, _NW // _CELL), np.float32)

    def reset(self):                              # call on a room cut (the scene/avatar frame changed)
        self.prev = None
        self.pos = None
        self._pending = None
        self.heat *= 0.0

    def _accumulate(self, cur, commanded_dir):
        self.heat *= _DECAY                       # forget old evidence -> tracks the CURRENT position
        if self.prev is None or commanded_dir not in DELTA:
            return
        dx, dy = DELTA[commanded_dir]
        mot = np.abs(cur - self.prev)
        # residual after explaining the change by a +k*command shift; low where motion matched the command
        resid = np.minimum.reduce([np.abs(cur - _shift(self.prev, k * dx, k * dy)) for k in _KSHIFTS])
        explained = mot * np.clip((mot - resid) / (mot + 1e-3), 0, 1)
        ch, cw = self.heat.shape
        self.heat += explained[:ch * _CELL, :cw * _CELL].reshape(ch, _CELL, cw, _CELL).mean((1, 3))

    def update(self, frame, commanded_dir: Optional[str] = None):
        """Returns (col, row, confidence) or None when the avatar has never been localized."""
        gray = _gray(frame)
        self._accumulate(gray, commanded_dir)
        self.prev = gray
        peak, mean = float(self.heat.max()), float(self.heat.mean()) + 1e-6
        if peak / mean >= _PEAK:                  # a confident fix: move the estimate to the heatmap peak
            r, c = np.unravel_index(int(self.heat.argmax()), self.heat.shape)
            new = ((c + 0.5) * _CELL, (r + 0.5) * _CELL)
            # outlier gate: a confident peak that leaps >1 cell from the held position is usually animation
            # (a torch/enemy that momentarily out-votes the avatar), not a real step -> HOLD unless it REPEATS
            # (a true room change). Within-cell moves commit immediately (no lag). Kills the jitter + gross
            # single-frame jumps that otherwise pollute a snapped occupancy map.
            if self.pos is not None and self._pending != (c, r) \
                    and np.hypot(new[0] - self.pos[0], new[1] - self.pos[1]) > _JUMP:
                self._pending = (c, r)            # first sighting of a far jump -> wait for confirmation
            else:
                self.pos, self._pending = new, None
            return (self.pos[0], self.pos[1], min(1.0, peak / mean / _PEAK))
        if self.pos is not None:                  # no recent commanded motion -> avatar stationary -> HOLD
            return (self.pos[0], self.pos[1], 0.3)
        return None
