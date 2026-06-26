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

from typing import Optional

from core.grid_perceiver import ForegroundSignal, GridPerceiver
from core.grid_perceiver import WALL_CONFIRM as _WALL_CONFIRM  # re-exported for tests
from core.localize import AvatarLocalizer

_MOVE_PX = 2.0     # camera-shift magnitude above which we scrolled (rare on Cave Noire's fixed cam)
_FG_GRID = 58.0    # max per-cell change above which the sprite moved (probe: real med 91 / stuck med 20)

# Screen (160x144 px) -> board cell. A FIXED screen-geometry constant (the 9x7 playfield occupies the same
# region in every room), calibrated ONCE against the RAM oracle in eval.probe_avatar_localize on the moving
# frames where RAM is exact: pitch ~18.6 x 24.6 px/cell, residual median 1 / 90th 4 cells. Like camera
# intrinsics: measured with a reference, then the runtime uses pixels only -- RAM never reaches the wire.
# Absolute accuracy stays ~1-2 cells; the strand fix needs only BOUNDED (no drift), which the closed-loop
# confirmed (cn_open.state: 18 distinct RAM tiles vs the dead-reckoned baseline's 7, no livelock).
_CELL_AX, _CELL_BX = 0.053663, 0.3952     # cell_x = round(_CELL_AX * col + _CELL_BX)
_CELL_AY, _CELL_BY = 0.040674, 1.2021     # cell_y = round(_CELL_AY * row + _CELL_BY)


class LocalizedForegroundSignal(ForegroundSignal):
    """Cave Noire's foreground move signal PLUS a control-grounded absolute-pose hook. The AvatarLocalizer
    reads the avatar's on-screen position from pixels each step (grounded by which way our buttons move it);
    quantized to a board cell it lets the base SNAP the cursor (bounded -> no dead-reckoning drift -> no
    strand). When the localizer is unlocked it returns None and the base falls back to the foreground signal.

    ROOM CUTS are deferred (v1 is within-room): the heatmap DECAYS, so it self-heals across a room change in
    a few steps; cross-room cell-key disambiguation is the follow-up, not needed for the single-room loop."""

    def __init__(self, move_px: float = _MOVE_PX, fg_grid: float = _FG_GRID) -> None:
        super().__init__(move_px=move_px, fg_grid=fg_grid)
        self.loc = AvatarLocalizer()

    def absolute_cell(self, frame, *, commanded_dir: Optional[str]) -> Optional[tuple]:
        out = self.loc.update(frame, commanded_dir)
        if out is None:
            return None
        col, row = out[0], out[1]
        return (round(_CELL_AX * col + _CELL_BX), round(_CELL_AY * row + _CELL_BY))


class CaveNoirePerceiver(GridPerceiver):
    """The shared grid perceiver wired with Cave Noire's foreground move signal + control-grounded localizer."""

    def __init__(self) -> None:
        super().__init__(LocalizedForegroundSignal(move_px=_MOVE_PX, fg_grid=_FG_GRID))


class CaveNoireBaselinePerceiver(GridPerceiver):
    """A/B CONTROL: the pre-localizer dead-reckon perceiver (plain ForegroundSignal, no snap). Isolates the
    localizer's effect in the live MCP brain test by holding the world fixed and swapping only the perception."""

    def __init__(self) -> None:
        super().__init__(ForegroundSignal(move_px=_MOVE_PX, fg_grid=_FG_GRID))


__all__ = ["CaveNoirePerceiver", "CaveNoireBaselinePerceiver", "LocalizedForegroundSignal"]
