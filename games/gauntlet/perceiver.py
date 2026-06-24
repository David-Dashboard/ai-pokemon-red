"""GauntletPerceiver — Gauntlet II (Game Boy), the SECOND world: thin config over core.grid_perceiver.

Gauntlet is one continuous top-down maze with a FOLLOW camera, so the move signal is camera scroll
(`best_shift`) and the pose steps by the ego (scrolled) axis — the CameraScrollSignal. The whole
occupancy-grid body (grid/walls/frontiers/wall-confirmation/SymbolicState) is the shared
`core.grid_perceiver.GridPerceiver`; this file is just the per-world move signal + calibration.
Validated two ways on the RAM oracle (both gitignored-corpus, see reports/2026-06-24-part2-replay-revalidation.md):
`eval/probe_pose_drift.py` (windowed net-heading agreement ~87%, drift ~0.02) and the stricter
`eval/replay_gauntlet_pose.py` (net-dir at W=40 = 83%, drift 0.02). The two numbers differ because they
aggregate over different windows/segments, not because the perceiver disagrees with itself. Pixels only;
RAM never touched.
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
