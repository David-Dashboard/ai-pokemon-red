"""CaveNoirePerceiver — Cave Noire (Game Boy), the THIRD world: thin config over core.grid_perceiver.

Cave Noire has a FIXED camera (measured 99% of real moves are camera-static: the screen never scrolls,
the sprite moves on a still board), so `best_shift` (camera motion) is blind and the follow-camera "no
scroll = wall" recipe maps nothing. The move signal is FOREGROUND motion via GRID-MAX (max per-cell
change): a real sprite move spikes one cell where the whole-frame residual gets diluted by the static
background (AUC 0.99 vs 0.86; reports/2026-06-24-phantom-move-probe.md). Direction is the COMMANDED
button (Cave Noire is 4-dir turn-based, command == move). The shared occupancy-grid body lives in
core.grid_perceiver; this is just the per-world move signal + calibration (the ForegroundSignal).

FALSE-MOVE ASYMMETRY (closed-loop FOUND, then FIXED): idle animation (torches/enemies) can spike a cell
above the grid-max threshold while the player is pinned at a wall -> a phantom step (open-corridor run was
65/70 phantom). Grid-max cuts that ~3x but leaves a ~33% tail no per-step pixel signal can separate, so the
base's no-progress backstop (a sustained same-direction run that isn't visually progressing -> demote to
no-move) catches the residual. See reports/2026-06-24-phantom-move-probe.md.
"""
from __future__ import annotations

from core.grid_perceiver import ForegroundSignal, GridPerceiver
from core.grid_perceiver import WALL_CONFIRM as _WALL_CONFIRM  # re-exported for tests

_MOVE_PX = 2.0     # camera-shift magnitude above which we scrolled (rare on Cave Noire's fixed cam)
_FG_GRID = 58.0    # max per-cell change above which the sprite moved (probe: real med 91 / stuck med 20)


class CaveNoirePerceiver(GridPerceiver):
    """The shared grid perceiver wired with Cave Noire's foreground-motion (grid-max) move signal."""

    def __init__(self) -> None:
        super().__init__(ForegroundSignal(move_px=_MOVE_PX, fg_grid=_FG_GRID))


__all__ = ["CaveNoirePerceiver"]
