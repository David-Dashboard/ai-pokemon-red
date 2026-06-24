"""GauntletPerceiver — pixels -> SymbolicState for Gauntlet II (Game Boy), the SECOND world.

The constancy test: this emits the SAME role-named `SymbolicState` seam the Pokemon perceiver does, so
the brain (`core/brains.py`) is reused UNCHANGED. It reuses the world-agnostic `core/` primitives and
DROPS everything Pokemon-specific (tile-grid `_PLAYER_CELL`/`_TILE_PX`, place/warp graph, Gen-1 textbox
font, the appearance TileFunctionMap). Gauntlet is one continuous top-down maze with a follow camera and
no dialog boxes, so the perceiver is the pure dead-reckoning core that the pose-drift gate validated
(eval/probe_pose_drift.py: drift ~0.02, net-heading 87% on the RAM oracle).

Pose recipe (the transferable one): a coarse occupancy grid stepped ONE cell per confirmed move in the
COMMANDED direction; a commanded move whose camera did NOT scroll is a wall (blocked). `context` comes
from world-agnostic `core.modality.detect_modality`; `ego_motion` from `core.egomotion`. Magnitude is
deferred (unreliable) -- one press = one cell. Pixels only; RAM never touched (no-leak is structural).
"""
from __future__ import annotations

from typing import Any, Optional

import numpy as np
from PIL import Image

from core.egomotion import best_shift, direction as ego_direction
from core.modality import detect_modality
from core.perception import JSON, PerceptMemory, SymbolicState

# Copied (not imported) from the Pokemon perceiver: a game package may not import a sibling
# (tests/test_import_boundaries.py). These are tiny and pure.
_DIRS = ("up", "down", "left", "right")
_DELTA = {"up": (0, -1), "down": (0, 1), "left": (-1, 0), "right": (1, 0)}
_BACK = {"up": "down", "down": "up", "left": "right", "right": "left"}
_EGO2DIR = {"east": "right", "west": "left", "south": "down", "north": "up"}  # ego token -> grid dir

_NW, _NH = 128, 112        # normalize frames for best_shift (same as eval/probe_camera_model)
_MAX_SHIFT, _STEP = 18, 2  # 2D translation search (px on the normalized frame)
_MOVE_PX = 2.0             # camera-shift magnitude above which we actually scrolled (moved, not bumped)
# Persistent-wall confirmation. A follow camera has a DEAD-ZONE: the hero can move while the camera holds
# (best_shift~0), so a single no-scroll is NOT a wall. Measured cross-game on RAM-grounded recordings:
# 24% (Gauntlet) / 19% (Metroid) / 9% (Kirby) of real moves are camera-static -> live, ~95% of naive
# "blocked" calls were really moves, which sealed phantom walls and boxed the autopilot in. A TRUE wall
# fails to scroll on EVERY attempt; a dead-zone slide is transient (the camera soon catches up = a move,
# which clears the count). So only seal after N persistent no-scroll attempts from the same cell+dir.
# CORE-PROMOTION CANDIDATE: this robustness is general (every non-centered camera) -- lift it to a shared
# core perceiver helper once a 2nd world's perceiver needs it (Pokemon's always-centered camera does not).
_WALL_CONFIRM = 3


def _dominant_dir(action: Optional[str]) -> Optional[str]:
    """Net commanded direction of an action like 'up+up' or 'right+b' -> 'up' / 'right' / None."""
    if not action:
        return None
    toks = [t for t in str(action).replace("+", " ").split() if t in _DIRS]
    return toks[-1] if toks else None


def _grays(frame) -> tuple[Optional[np.ndarray], Optional[np.ndarray]]:
    """(full-res grayscale for detect_modality, normalized 128x112 for best_shift) from a raw frame."""
    if frame is None:
        return None, None
    a = np.asarray(frame)
    g = a[..., :3].mean(axis=2) if a.ndim == 3 else a.astype(np.float32)
    norm = np.asarray(Image.fromarray(g.astype(np.uint8)).resize((_NW, _NH), Image.BILINEAR), np.float32)
    return g.astype(np.float32), norm


class GauntletPerceiver:
    """screen -> SymbolicState via dead-reckoned odometry + a coarse occupancy map. No RAM."""

    def perceive(self, frame: Any, memory: PerceptMemory,
                 context: Optional[JSON] = None) -> SymbolicState:
        m = memory.data
        m.setdefault("cursor", (0, 0))
        cells = m.setdefault("cells", {})
        noscroll = m.setdefault("noscroll", {})   # (cell, dir) -> consecutive no-scroll attempts
        ctx = context or {}
        action = ctx.get("last_action")
        direction = _dominant_dir(action)
        cur_full, cur_norm = _grays(frame)
        first = m.get("prev_norm") is None

        # context: world-agnostic gameplay/menu/static (replaces Pokemon's Gen-1 detect_mode).
        if first or cur_full is None:
            label, conf = "gameplay", 0.3
        else:
            toks = [t for t in str(action or "").replace("+", " ").split() if t]
            label, conf = detect_modality(m["prev_full"], cur_full, toks)

        # ego-motion: best translation aligning prev->cur. A scroll => we moved; ~0 => a bump/idle.
        shift_diff, sdx, sdy = 255.0, 0, 0
        if not first and cur_norm is not None:
            _, shift_diff, sdx, sdy = best_shift(m["prev_norm"], cur_norm,
                                                 max_shift=_MAX_SHIFT, step=_STEP, tie_break=1e-3)
        ego = ego_direction(sdx, sdy)

        x, y = m["cursor"]
        cell = cells.setdefault((x, y), {"visited": True, "walls": set()})
        cell["visited"] = True
        outcome = "unknown"
        if direction and not first:
            if max(abs(sdx), abs(sdy)) >= _MOVE_PX:        # camera scrolled -> the move landed
                noscroll.pop(((x, y), direction), None)    # the COMMANDED dir worked -> clear its no-scroll count
                # Step by the EGO direction (best_shift's dominant axis), not the last-pressed token. Still
                # exactly one cardinal cell -- but on an 8-way diagonal press ego picks the axis that ACTUALLY
                # scrolled (the commanded token picks whichever was pressed last; that mismatch drove the
                # 0.31->0.02 drift). ASSUMPTION: ego's dominant axis == the true displacement (holds at 0.02
                # drift). Keep the WALL bookkeeping in the SAME ego space as the cursor so they can't desync
                # when ego != commanded (clearing a commanded-space wall while stepping in ego would).
                step = _EGO2DIR.get(ego, direction)
                cell["walls"].discard(step)                # the cell we left is open the way we MOVED
                dx, dy = _DELTA[step]
                x, y = x + dx, y + dy                       # one press = one cell (magnitude deferred)
                cell = cells.setdefault((x, y), {"visited": True, "walls": set()})
                cell["visited"] = True
                cell["walls"].discard(_BACK[step])         # the cell we entered is open back the way we came
                m["cursor"] = (x, y)
                outcome = "moved"
            else:                                          # no scroll: a WALL or a dead-zone slide
                key = ((x, y), direction)
                noscroll[key] = noscroll.get(key, 0) + 1
                if noscroll[key] >= _WALL_CONFIRM:         # persistent -> a real wall, seal it
                    cell["walls"].add(direction)
                    outcome = "blocked"
                else:
                    outcome = "unknown"                    # tentative: don't seal a phantom dead-zone wall

        m["prev_full"], m["prev_norm"] = cur_full, cur_norm

        # affordances: open (non-wall) directions, unexplored first.
        open_unexplored, open_all = [], []
        for d in _DIRS:
            if d in cell["walls"]:
                continue
            open_all.append(d)
            ddx, ddy = _DELTA[d]
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
            for d in _DIRS:
                if d in c["walls"]:
                    continue
                ddx, ddy = _DELTA[d]
                nbr = cells.get((cx + ddx, cy + ddy))
                if nbr is None or not nbr.get("visited"):
                    frontiers.append([cx, cy])
                    break

        raw_ref = ctx.get("frame_path", "") if frame is not None else ""
        return SymbolicState(
            confidence=0.4,
            context=label,
            pose={"frame": "grid", "value": [x, y], "uncertain": True, "area": 0},
            spatial_memory={"kind": "occupancy-grid", "area": 0, "visited": visited_n,
                            "walls_here": sorted(cell["walls"]),
                            "map": grid, "frontiers": frontiers, "rois": [],
                            "place_portals": [], "place_frontiers": [], "places_known": 1,
                            "ego_motion": ego},
            affordances=open_unexplored or open_all,
            last_action={"action": action, "outcome": outcome, "diff": round(shift_diff, 2)},
            screen_text="",                       # Gauntlet has no Gen-1 textbox font to decode
            raw_available=bool(raw_ref), raw_ref=raw_ref,
        )
