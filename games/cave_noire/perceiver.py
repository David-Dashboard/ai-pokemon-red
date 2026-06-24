"""CaveNoirePerceiver — Cave Noire (Game Boy), the THIRD world: thin config over core.grid_perceiver.

Cave Noire has a FIXED camera (measured 99% of real moves are camera-static: the screen never scrolls,
the sprite moves on a still board), so `best_shift` (camera motion) is blind and the follow-camera "no
scroll = wall" recipe maps nothing. The move signal is FOREGROUND motion — the camera-compensated
residual (best_shift's best_diff) — which separates a real move from a wall-bump in the camera-static
regime (probe AUC 0.86). Direction is the COMMANDED button (Cave Noire is 4-dir turn-based, command ==
move). The shared occupancy-grid body lives in core.grid_perceiver; this is just the per-world move
signal + calibration (the ForegroundSignal). See reports/2026-06-24-cave-noire-fixed-camera.md.

WATCH-ITEM (false-MOVE asymmetry): a wall needs _WALL_CONFIRM persistent no-moves to seal, but a move is
trusted on a SINGLE foreground frame, so idle animation (torches/enemies, AUC 0.86 -> ~14% confusable)
can false-step the pose into a phantom cell — the inverse of Gauntlet's false-WALL. Offline drift (0.06)
tolerates it; if the live closed loop doesn't, the fix (symmetric move-confirmation / higher fg_move) is
closed-loop validated there, not asserted offline.
"""
from __future__ import annotations

from core.grid_perceiver import ForegroundSignal, GridPerceiver
from core.grid_perceiver import WALL_CONFIRM as _WALL_CONFIRM  # re-exported for tests

_MOVE_PX = 2.0    # camera-shift magnitude above which we scrolled (rare on Cave Noire's fixed cam)
_FG_MOVE = 1.5    # camera-compensated RESIDUAL above which the sprite moved (probe: MOVED~2.9/STUCK~0.7)


class CaveNoirePerceiver(GridPerceiver):
    """The shared grid perceiver wired with Cave Noire's foreground-motion move signal."""

    def __init__(self) -> None:
        super().__init__(ForegroundSignal(move_px=_MOVE_PX, fg_move=_FG_MOVE))


__all__ = ["CaveNoirePerceiver"]
