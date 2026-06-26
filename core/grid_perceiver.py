"""GridPerceiver — the shared occupancy-grid perceiver (pixels -> SymbolicState) for the lean worlds.

The pose backbone that transfers across camera classes: a coarse occupancy grid dead-reckoned ONE cell
per confirmed move, with persistent-wall confirmation (a follow camera's dead-zone or a fixed camera's
idle animation makes a single no-move ambiguous, so only seal a wall after N persistent attempts). The
ONLY per-world parts are injected as a `MoveSignal` strategy: (a) did the commanded action land, (b)
which cardinal to step, (c) what to surface as `ego_motion`. Everything else — the grid, frontiers,
affordances, the wall bookkeeping, the SymbolicState assembly — is shared. Pixels only; RAM never
touched (no-leak is structural). `context` comes from world-agnostic `core.modality.detect_modality`.

Lifted from games/gauntlet/perceiver.py + games/cave_noire/perceiver.py the second time the body was
needed; the two now differ ONLY in their move signal (camera-scroll vs foreground-residual) and step
source (ego token vs commanded button) — both expressed as a MoveSignal below.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional, Protocol

import numpy as np
from PIL import Image

from core.egomotion import best_shift, direction
from core.grid import BACK, DELTA, DIR2EGO, DIRS, EGO2DIR
from core.modality import detect_modality
from core.perception import JSON, PerceptMemory, SymbolicState

WALL_CONFIRM = 3           # seal a wall only after N persistent no-move attempts (dead-zone/idle is transient)
_NW, _NH = 128, 112        # normalize frames for best_shift (same as eval/probe_camera_model)
_MAX_SHIFT, _STEP = 18, 2  # 2D translation search (px on the normalized frame)
_GRID = 8                  # per-cell change grid (eval/probe_spatial_move): a real move spikes ONE cell
# no-progress backstop: a per-step pixel signal can't fully separate a real move from a stuck flicker-loop
# (eval/probe_phantom_move: ~33% of corridor wall-bumps still spike a cell), so a sustained same-direction
# run that isn't VISUALLY progressing is a phantom runaway -> demote to no-move and let wall-confirm seal it.
# Gated on a long same-dir run so it never fires on normal exploration.
_RUN_GUARD, _PROG_W, _PROG_MIN = 4, 4, 4.0
_DELTA_INV = {v: k for k, v in DELTA.items()}    # unit (dx,dy) -> cardinal, for snapping cell deltas to a step


def grid_max_change(prev_norm, cur_norm) -> float:
    """Max per-cell mean-abs change (8x8 grid): localizes a sprite move the whole-frame mean washes out.
    AUC 0.99 vs 0.86 whole-frame for move-vs-stuck (eval/probe_spatial_move)."""
    if prev_norm is None or cur_norm is None:
        return 0.0
    d = np.abs(cur_norm - prev_norm)
    nh, nw = d.shape
    ch, cw = nh // _GRID, nw // _GRID
    return float(d[:ch * _GRID, :cw * _GRID].reshape(_GRID, ch, _GRID, cw).mean(axis=(1, 3)).max())


@dataclass(frozen=True)
class MoveResult:
    """A MoveSignal's verdict for one commanded step."""
    moved: bool                  # did the commanded action land?
    step_dir: Optional[str]      # cardinal to advance the cursor AND clear walls; None if not moved
    ego_motion: str              # value to surface in spatial_memory["ego_motion"] ("east".."north"/"none")


class MoveSignal(Protocol):
    """Decides move/step/ego from the (base-computed) ego-motion primitives. The only per-world part."""
    def __call__(self, *, commanded_dir: Optional[str], ego_token: str,
                 sdx: int, sdy: int, best_diff: float, grid_max: float) -> MoveResult: ...


class CameraScrollSignal:
    """Follow-camera worlds (Gauntlet): the camera scrolled => we moved; step by the ego (scrolled) axis."""

    def __init__(self, move_px: float = 2.0) -> None:
        self.move_px = move_px

    def __call__(self, *, commanded_dir, ego_token, sdx, sdy, best_diff, grid_max=0.0) -> MoveResult:
        # Step by the EGO axis (best_shift's dominant axis), not the last-pressed token: on an 8-way
        # diagonal press ego picks the axis that ACTUALLY scrolled (the 0.31->0.02 drift fix). Surface the
        # raw ego token regardless of whether it cleared the move threshold.
        if max(abs(sdx), abs(sdy)) >= self.move_px:
            return MoveResult(True, EGO2DIR.get(ego_token, commanded_dir), ego_token)
        return MoveResult(False, None, ego_token)


class ForegroundSignal:
    """Fixed-camera worlds (Cave Noire): the screen never scrolls, so the move signal is FOREGROUND motion.
    The per-step signal is GRID-MAX (max per-cell change) -- a real sprite move spikes one cell, where the
    whole-frame residual gets diluted by the static background (AUC 0.99 vs 0.86, eval/probe_spatial_move;
    a CNN/embedding was tested and is no better -- invariance machines forgive the small change we want).
    Direction is the commanded button (turn-based, command == move); camera-scroll is a rarely-firing
    fallback. The residual tail it can't separate is caught by the base's no-progress backstop."""

    def __init__(self, move_px: float = 2.0, fg_grid: float = 58.0) -> None:
        self.move_px = move_px
        self.fg_grid = fg_grid

    def __call__(self, *, commanded_dir, ego_token, sdx, sdy, best_diff, grid_max=0.0) -> MoveResult:
        scrolled = max(abs(sdx), abs(sdy)) >= self.move_px
        if scrolled or grid_max >= self.fg_grid:
            step = EGO2DIR.get(ego_token, commanded_dir) if scrolled else commanded_dir
            return MoveResult(True, step, DIR2EGO.get(step, "none"))
        return MoveResult(False, None, "none")


def _dominant_dir(action: Optional[str]) -> Optional[str]:
    """Net commanded direction of an action like 'up+up' or 'right+b' -> 'up' / 'right' / None."""
    if not action:
        return None
    toks = [t for t in str(action).replace("+", " ").split() if t in DIRS]
    return toks[-1] if toks else None


def _grays(frame, nw: int, nh: int):
    """(full-res grayscale for detect_modality, normalized nw x nh for best_shift) from a raw frame."""
    if frame is None:
        return None, None
    a = np.asarray(frame)
    g = a[..., :3].mean(axis=2) if a.ndim == 3 else a.astype(np.float32)
    norm = np.asarray(Image.fromarray(g.astype(np.uint8)).resize((nw, nh), Image.BILINEAR), np.float32)
    return g.astype(np.float32), norm


class GridPerceiver:
    """screen -> SymbolicState via dead-reckoned odometry + a coarse occupancy map. No RAM.

    `move_signal` is the only per-world part (see CameraScrollSignal / ForegroundSignal)."""

    def __init__(self, move_signal: MoveSignal, *, max_shift: int = _MAX_SHIFT, step: int = _STEP,
                 nw: int = _NW, nh: int = _NH, wall_confirm: int = WALL_CONFIRM) -> None:
        self.move_signal = move_signal
        self.max_shift = max_shift
        self.step = step
        self.nw, self.nh = nw, nh
        self.wall_confirm = wall_confirm

    def perceive(self, frame: Any, memory: PerceptMemory,
                 context: Optional[JSON] = None) -> SymbolicState:
        m = memory.data
        m.setdefault("cursor", (0, 0))
        cells = m.setdefault("cells", {})
        blocked = m.setdefault("blocked_attempts", {})   # (cell, dir) -> consecutive no-move attempts
        ctx = context or {}
        action = ctx.get("last_action")
        commanded_dir = _dominant_dir(action)
        cur_full, cur_norm = _grays(frame, self.nw, self.nh)
        first = m.get("prev_norm") is None

        # context: world-agnostic gameplay/menu/static.
        if first or cur_full is None:
            label = "gameplay"
        else:
            toks = [t for t in str(action or "").replace("+", " ").split() if t]
            label, _ = detect_modality(m["prev_full"], cur_full, toks)
        if label != "gameplay":          # a menu/transition breaks a movement run (no-progress backstop state)
            m["run"] = (None, 0)

        # ego-motion primitives: best translation aligning prev->cur (camera) + the residual (foreground)
        # + the localized per-cell max change (the move signal that beats whole-frame on a fixed camera).
        best_diff, sdx, sdy, grid_max = 0.0, 0, 0, 0.0
        if not first and cur_norm is not None:
            _, best_diff, sdx, sdy = best_shift(m["prev_norm"], cur_norm,
                                                max_shift=self.max_shift, step=self.step, tie_break=1e-3)
            grid_max = grid_max_change(m["prev_norm"], cur_norm)
        ego_token = direction(sdx, sdy)

        # Optional absolute-pose hook (fixed-camera localization): if the move signal can read the avatar's
        # cell from pixels, SNAP the cursor to it -- pose is a function of the CURRENT frame, so there is no
        # dead-reckoning integral to accumulate error (the strand fix). None (unlocked / no frame) -> fall back
        # to the dead-reckon path below, so we are never worse than before. Walls are sealed/cleared only on a
        # clean unit step that AGREES with the command (the avatar moves only where commanded; a disagreeing
        # delta is localizer noise -> snap the position but leave the walls).
        abs_cell = None
        if not first and frame is not None and hasattr(self.move_signal, "absolute_cell"):
            abs_cell = self.move_signal.absolute_cell(frame, commanded_dir=commanded_dir)

        x, y = m["cursor"]
        cell = cells.setdefault((x, y), {"visited": True, "walls": set()})
        cell["visited"] = True
        outcome, ego_motion = "unknown", "none"
        if abs_cell is not None:
            nx, ny = abs_cell
            if not m.get("snapped"):                  # first lock: the pre-lock dead-reckon cells are in the
                cells.clear(); blocked.clear()         # wrong (relative) frame -> drop them, re-anchor on truth
            dx, dy = nx - x, ny - y
            ncell = cells.setdefault((nx, ny), {"visited": True, "walls": set()})
            ncell["visited"] = True
            m["cursor"] = (nx, ny)
            step = _DELTA_INV.get((dx, dy))
            if m.get("snapped") and step is not None and step == commanded_dir:   # confirmed unit step
                cell["walls"].discard(step)                          # left cell open the way we MOVED
                ncell["walls"].discard(BACK[step])                   # entered cell open back the way we came
                blocked.pop(((x, y), commanded_dir), None)
                ego_motion, outcome = DIR2EGO.get(step, "none"), "moved"
            elif m.get("snapped") and dx == 0 and dy == 0 and commanded_dir:       # commanded but pinned -> wall
                key = ((x, y), commanded_dir)
                blocked[key] = blocked.get(key, 0) + 1
                if blocked[key] >= self.wall_confirm:
                    cell["walls"].add(commanded_dir)
                    outcome = "blocked"
            elif dx or dy:                                           # first lock / >1 jump / off-axis noise
                outcome = "moved"
            m["snapped"] = True
            cell, x, y = ncell, nx, ny
        elif not first:
            res = self.move_signal(commanded_dir=commanded_dir, ego_token=ego_token,
                                   sdx=sdx, sdy=sdy, best_diff=best_diff, grid_max=grid_max)
            ego_motion = res.ego_motion
            moved, step_dir = res.moved, res.step_dir
            if moved and step_dir and commanded_dir:
                # no-progress backstop: track the consecutive same-direction run and whether the screen has
                # actually changed over the last _PROG_W steps. A long run that isn't progressing = a phantom
                # runaway (idle flicker faking grid-max moves at a wall) -> demote to no-move; wall-confirm seals it.
                run_dir, run_len = m.get("run", (None, 0))
                run_len = run_len + 1 if step_dir == run_dir else 1
                m["run"] = (step_dir, run_len)
                recent = m.get("recent_norms", [])
                prog = (float(np.abs(cur_norm - recent[-_PROG_W]).mean())
                        if cur_norm is not None and len(recent) >= _PROG_W else None)
                if run_len >= _RUN_GUARD and prog is not None and prog < _PROG_MIN:
                    moved, step_dir = False, None          # not actually getting anywhere -> treat as no-move
            elif not (moved and step_dir):
                m["run"] = (None, 0)
            if commanded_dir:
                if moved and step_dir:                      # the commanded move landed
                    blocked.pop(((x, y), commanded_dir), None)
                    step = step_dir
                    cell["walls"].discard(step)            # the cell we left is open the way we MOVED
                    dx, dy = DELTA[step]
                    x, y = x + dx, y + dy                   # one press = one cell (magnitude deferred)
                    cell = cells.setdefault((x, y), {"visited": True, "walls": set()})
                    cell["visited"] = True
                    cell["walls"].discard(BACK[step])       # the entered cell is open back the way we came
                    m["cursor"] = (x, y)
                    outcome = "moved"
                else:                                       # no move: a WALL or a transient dead-zone/idle
                    key = ((x, y), commanded_dir)
                    blocked[key] = blocked.get(key, 0) + 1
                    if blocked[key] >= self.wall_confirm:   # persistent -> a real wall, seal it
                        cell["walls"].add(commanded_dir)
                        outcome = "blocked"

        m["prev_full"], m["prev_norm"] = cur_full, cur_norm
        if cur_norm is not None:                 # rolling frame buffer for the no-progress backstop
            recent = m.setdefault("recent_norms", [])
            recent.append(cur_norm)
            del recent[:-(_PROG_W + 1)]

        # affordances: open (non-wall) directions, unexplored first.
        open_unexplored, open_all = [], []
        for d in DIRS:
            if d in cell["walls"]:
                continue
            open_all.append(d)
            ddx, ddy = DELTA[d]
            nbr = cells.get((x + ddx, y + ddy))
            if nbr is None or not nbr.get("visited"):
                open_unexplored.append(d)

        # full map + frontier cells (a frontier = visited cell with a non-wall edge into the unknown).
        visited_n = sum(1 for c in cells.values() if c.get("visited"))
        grid, frontiers = [], []
        for (cx, cy), c in cells.items():
            grid.append({"x": cx, "y": cy, "visited": bool(c.get("visited")),
                         "portal": None, "walls": sorted(c["walls"])})
            if not c.get("visited"):
                continue
            for d in DIRS:
                if d in c["walls"]:
                    continue
                ddx, ddy = DELTA[d]
                nbr = cells.get((cx + ddx, cy + ddy))
                if nbr is None or not nbr.get("visited"):
                    frontiers.append([cx, cy])
                    break

        raw_ref = ctx.get("frame_path", "") if frame is not None else ""
        return SymbolicState(
            # FIXED PLACEHOLDER: the lean grid perceivers don't yet compute a calibrated confidence
            # (carried over verbatim from the Gauntlet/Cave Noire perceivers). ADR-001 inv-6 wants this
            # meaningful before `confidence` gates deferral; a per-cell coverage/outcome-derived value is
            # a follow-up. Until then it is a constant and brains must not read it as calibrated.
            confidence=0.4,
            context=label,
            pose={"frame": "grid", "value": [x, y], "uncertain": True, "area": 0},
            spatial_memory={"kind": "occupancy-grid", "area": 0, "visited": visited_n,
                            "walls_here": sorted(cell["walls"]),
                            "map": grid, "frontiers": frontiers, "rois": [],
                            "place_portals": [], "place_frontiers": [], "places_known": 1,
                            "ego_motion": ego_motion},
            affordances=open_unexplored or open_all,
            last_action={"action": action, "outcome": outcome, "diff": round(best_diff, 2)},
            screen_text="",
            raw_available=bool(raw_ref), raw_ref=raw_ref,
        )
