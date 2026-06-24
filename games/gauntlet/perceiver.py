"""GauntletPerceiver — Gauntlet II (Game Boy), the SECOND world: thin config over core.grid_perceiver.

Gauntlet is one continuous top-down maze with a FOLLOW camera, so the move signal is camera scroll
(`best_shift`) and the pose steps by the ego (scrolled) axis — the CameraScrollSignal. The whole
occupancy-grid body (grid/walls/frontiers/wall-confirmation/SymbolicState) is the shared
`core.grid_perceiver.GridPerceiver`; this file is just the per-world move signal + calibration.
Validated by eval/probe_pose_drift.py (drift ~0.02, net-heading 87% on the RAM oracle) and
eval/replay_gauntlet_pose.py (83% heading / 0.02 drift). Pixels only; RAM never touched.
"""
from __future__ import annotations

from core.grid_perceiver import CameraScrollSignal, GridPerceiver
from core.grid_perceiver import WALL_CONFIRM as _WALL_CONFIRM  # re-exported for tests

_MOVE_PX = 2.0   # camera-shift magnitude above which we actually scrolled (moved, not bumped)


class GauntletPerceiver(GridPerceiver):
    """The shared grid perceiver wired with Gauntlet's camera-scroll move signal."""

    def __init__(self) -> None:
        super().__init__(CameraScrollSignal(move_px=_MOVE_PX))


__all__ = ["GauntletPerceiver"]
