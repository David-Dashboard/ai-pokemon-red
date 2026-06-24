"""CaveNoirePerceiver — pixels -> SymbolicState for Cave Noire (Game Boy), the THIRD world.

Same constancy posture as Gauntlet (emit the role-named seam; brain reused unchanged), but Cave Noire has
a FIXED camera: measured 99% of real moves are camera-static (the screen never scrolls; the player sprite
moves on a still board). So `best_shift` (camera motion) is blind here and the Gauntlet "no scroll = wall"
recipe would map nothing. Instead the move signal is FOREGROUND motion: the camera-compensated residual
(best_shift's best_diff) -- on a static step it's the whole-frame diff, which the foreground-motion probe
showed separates a real move from a wall-bump (AUC 0.86: MOVED~2.9 vs STUCK~0.7). Direction comes from the
COMMANDED button (Cave Noire is 4-dir turn-based, so command == move). Camera-scroll is kept as a fallback
(rarely fires here). Pixels only; RAM never touched.
"""
from __future__ import annotations

from typing import Any, Optional

import numpy as np
from PIL import Image

from core.egomotion import best_shift, direction as ego_direction
from core.modality import detect_modality
from core.perception import JSON, PerceptMemory, SymbolicState

# Copied (not imported) from a sibling — the import-boundary wall. Tiny and pure.
_DIRS = ("up", "down", "left", "right")
_DELTA = {"up": (0, -1), "down": (0, 1), "left": (-1, 0), "right": (1, 0)}
_BACK = {"up": "down", "down": "up", "left": "right", "right": "left"}
_EGO2DIR = {"east": "right", "west": "left", "south": "down", "north": "up"}  # ego token -> grid dir
_DIR2EGO = {"right": "east", "left": "west", "down": "south", "up": "north"}  # grid dir -> cardinal

_NW, _NH = 128, 112
_MAX_SHIFT, _STEP = 18, 2
_MOVE_PX = 2.0             # camera-shift magnitude above which we scrolled (rare on Cave Noire's fixed cam)
_FG_MOVE = 1.5            # camera-compensated RESIDUAL above which the sprite moved (probe: MOVED~2.9/STUCK~0.7)
_WALL_CONFIRM = 3         # seal a wall only after N persistent no-move attempts (idle animation is transient)


def _dominant_dir(action: Optional[str]) -> Optional[str]:
    if not action:
        return None
    toks = [t for t in str(action).replace("+", " ").split() if t in _DIRS]
    return toks[-1] if toks else None


def _grays(frame) -> tuple[Optional[np.ndarray], Optional[np.ndarray]]:
    if frame is None:
        return None, None
    a = np.asarray(frame)
    g = a[..., :3].mean(axis=2) if a.ndim == 3 else a.astype(np.float32)
    norm = np.asarray(Image.fromarray(g.astype(np.uint8)).resize((_NW, _NH), Image.BILINEAR), np.float32)
    return g.astype(np.float32), norm


class CaveNoirePerceiver:
    """screen -> SymbolicState via foreground-motion odometry on a fixed-camera board. No RAM."""

    def perceive(self, frame: Any, memory: PerceptMemory,
                 context: Optional[JSON] = None) -> SymbolicState:
        m = memory.data
        m.setdefault("cursor", (0, 0))
        cells = m.setdefault("cells", {})
        nomove = m.setdefault("nomove", {})       # (cell, dir) -> consecutive no-move attempts
        ctx = context or {}
        action = ctx.get("last_action")
        direction = _dominant_dir(action)
        cur_full, cur_norm = _grays(frame)
        first = m.get("prev_norm") is None

        if first or cur_full is None:
            label, conf = "gameplay", 0.3
        else:
            toks = [t for t in str(action or "").replace("+", " ").split() if t]
            label, conf = detect_modality(m["prev_full"], cur_full, toks)

        # camera motion + FOREGROUND residual. best_resid = residual after the best camera shift; on a
        # static step it's the whole-frame diff = the sprite-motion signal.
        fd, best_resid, sdx, sdy = 0.0, 0.0, 0, 0
        if not first and cur_norm is not None:
            fd, best_resid, sdx, sdy = best_shift(m["prev_norm"], cur_norm,
                                                  max_shift=_MAX_SHIFT, step=_STEP, tie_break=1e-3)
        scrolled = max(abs(sdx), abs(sdy)) >= _MOVE_PX
        foreground = best_resid >= _FG_MOVE
        ego = ego_direction(sdx, sdy)

        x, y = m["cursor"]
        cell = cells.setdefault((x, y), {"visited": True, "walls": set()})
        cell["visited"] = True
        outcome, moved_dir = "unknown", "none"
        if direction and not first:
            # ASYMMETRY (live-run watch-item): a wall needs _WALL_CONFIRM persistent no-moves to seal, but a
            # MOVE is trusted on a SINGLE foreground frame. Idle animation (torches/enemies) raises the
            # residual while stuck (AUC 0.86 -> ~14% confusable), so a lone flicker can false-step the pose
            # into a phantom cell -- the inverse of Gauntlet's false-WALL. Offline drift (0.06) tolerates it;
            # the closed loop may not. Candidate fix -- symmetric move-confirmation (persist the foreground
            # 2 frames) or a higher _FG_MOVE -- is deferred to the live run, where it can be closed-loop
            # validated (the offline replay can't surface it; same offline-overstates lesson Gauntlet hit).
            if scrolled or foreground:                 # the move landed (camera scrolled OR sprite moved)
                cell["walls"].discard(direction)
                nomove.pop(((x, y), direction), None)
                step = _EGO2DIR.get(ego, direction) if scrolled else direction  # fixed cam -> commanded dir
                dx, dy = _DELTA[step]
                x, y = x + dx, y + dy
                cell = cells.setdefault((x, y), {"visited": True, "walls": set()})
                cell["visited"] = True
                cell["walls"].discard(_BACK[direction])
                m["cursor"] = (x, y)
                outcome, moved_dir = "moved", _DIR2EGO.get(step, "none")
            else:                                      # no camera scroll AND no sprite motion -> maybe wall
                key = ((x, y), direction)
                nomove[key] = nomove.get(key, 0) + 1
                if nomove[key] >= _WALL_CONFIRM:       # persistent -> a real wall (idle animation is transient)
                    cell["walls"].add(direction)
                    outcome = "blocked"
                else:
                    outcome = "unknown"

        m["prev_full"], m["prev_norm"] = cur_full, cur_norm

        open_unexplored, open_all = [], []
        for d in _DIRS:
            if d in cell["walls"]:
                continue
            open_all.append(d)
            ddx, ddy = _DELTA[d]
            nbr = cells.get((x + ddx, y + ddy))
            if nbr is None or not nbr.get("visited"):
                open_unexplored.append(d)

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
                            "ego_motion": moved_dir},   # foreground-confirmed move direction (or "none")
            affordances=open_unexplored or open_all,
            last_action={"action": action, "outcome": outcome, "diff": round(best_resid, 2)},
            screen_text="",
            raw_available=bool(raw_ref), raw_ref=raw_ref,
        )
