"""OverworldPerceiver (Iteration 02, Step 2): pixels -> SymbolicState via odometry + an
occupancy map. Near vision-free — it uses a frame-diff ("did my move change the screen?")
plus dead-reckoning to remember where it has been and which directions are walls or
unexplored. That memory is the cure for the Iteration-01 "loop in one room" failure.

RAM is never touched (it's the scoring oracle). Coarse by design: one decision advances the
dead-reckoned cursor by one tile in the action's dominant direction, so the map's geometry is
squashed and drifts — fine for "don't loop / head to unexplored", and the oracle measures the
drift. Single-area for now (area-transition detection is deferred to a later step).
"""
from __future__ import annotations

from typing import Optional

import numpy as np

from core.perception import JSON, PerceptMemory, SymbolicState

_DIRS = ("up", "down", "left", "right")
_DELTA = {"up": (0, -1), "down": (0, 1), "left": (-1, 0), "right": (1, 0)}
_MOVE_THRESHOLD = 4.0   # mean abs pixel diff above which a move happened (tune via eval/tune_threshold.py)
_AREA_THRESHOLD = 60.0  # diff at/above which the WHOLE screen changed => area/map transition (reset frame)


def _dominant_dir(action: Optional[str]) -> Optional[str]:
    """Net direction of an action like 'up+up+up' or 'right+a' -> 'up' / 'right' / None.
    Uses the LAST directional token — the net facing for repeated taps."""
    if not action:
        return None
    toks = [t for t in str(action).replace("+", " ").split() if t in _DIRS]
    return toks[-1] if toks else None


def _frame_diff(a, b) -> float:
    if a is None or b is None:
        return 0.0
    a = np.asarray(a, dtype=np.int16)
    b = np.asarray(b, dtype=np.int16)
    if a.shape != b.shape:
        return 255.0  # totally different (resolution / area change)
    return float(np.abs(a - b).mean())


def _gray(frame):
    g = np.asarray(frame)
    return g[..., :3].mean(axis=2) if g.ndim == 3 else g


def detect_mode(frame, white: int = 230, t: float = 0.15) -> str:
    """Mode from pixels (overworld | menu | dialog | battle). Gen-1 UI panels are PURE white and the
    game world almost never is, so the near-white fraction by region separates them. Measured: an
    overworld frame is ~0% near-white everywhere; the START menu's right panel ~66%. A bottom panel =
    a dialog textbox; bright panels both top AND bottom = a battle (HP boxes + action box). Cheap, CPU,
    no training. Battle/dialog thresholds are structural priors to firm up once we have those frames."""
    if frame is None:
        return "overworld"
    g = _gray(frame)
    # A near-uniform frame (std ~ 0) is a fade/flash TRANSITION, not a UI panel. Measured: white and
    # black fades have std 0.0, while real battle/menu/dialog frames have std > 65 (dark sprites/text
    # on the white). Without this, an all-white flash trips the bright-top-AND-bottom 'battle' rule
    # (a false positive seen during the starter cutscene). Treat it as overworld — it's a one-frame
    # blank the odometry/area-change path already tolerates, and the next frame resolves the state.
    if float(g.std()) < 6.0:
        return "overworld"
    H, W = g.shape
    w = g >= white
    right = float(w[:, int(W * 0.6):].mean())
    bottom = float(w[int(H * 0.66):, :].mean())
    top = float(w[:int(H * 0.4), :].mean())
    if max(right, bottom, top) < t:
        return "overworld"
    if bottom > 0.3 and top > 0.3:
        return "battle"          # HP boxes (top) + action/text box (bottom)
    if right > 0.35 and right >= bottom:
        return "menu"            # right-side panel (START menu / battle action menu)
    if bottom > 0.3:
        return "dialog"          # bottom textbox
    return "menu"                # some other UI box — treat as a menu so the planner is woken


class OverworldPerceiver:
    """Frame-diff walkability + a dead-reckoned occupancy map. All state lives in PerceptMemory."""

    def __init__(self, move_threshold: float = _MOVE_THRESHOLD,
                 area_threshold: float = _AREA_THRESHOLD) -> None:
        self.move_threshold = move_threshold
        self.area_threshold = area_threshold

    def perceive(self, frame, memory: PerceptMemory,
                 context: Optional[JSON] = None) -> SymbolicState:
        ctx = context or {}
        m = memory.data
        m.setdefault("cursor", (0, 0))
        m.setdefault("cells", {})          # (x,y) -> {"visited": bool, "walls": set[str]}
        m.setdefault("prev_frame", None)
        m.setdefault("steps", 0)
        m.setdefault("area", 0)
        m.setdefault("resync", False)
        m["steps"] += 1

        # Mode first: a menu/dialog/battle is NOT the overworld — hand it straight to the planner and
        # do NOT run odometry on it (a menu cursor move isn't walking). Re-baseline when we return.
        mode = detect_mode(frame)
        if mode != "overworld":
            m["prev_frame"] = np.asarray(frame).copy() if frame is not None else None
            m["resync"] = True
            return SymbolicState(
                confidence=0.5, context=mode,
                pose={"frame": "grid", "value": list(m["cursor"]), "uncertain": True, "area": m["area"]},
                spatial_memory={"kind": "occupancy-grid", "area": m["area"]},
                affordances=[],
                last_action={"action": ctx.get("last_action"), "outcome": "n/a"},
                raw_available=True, raw_ref=ctx.get("frame_path", ""))

        action = ctx.get("last_action")
        direction = _dominant_dir(action)
        prev = m["prev_frame"]
        first = prev is None or m["resync"]   # re-baseline after returning from a menu/battle
        m["resync"] = False
        diff = _frame_diff(prev, frame)
        area_change = (not first) and (diff >= self.area_threshold)
        moved = (not first) and (diff > self.move_threshold)

        x, y = m["cursor"]
        cell = m["cells"].setdefault((x, y), {"visited": True, "walls": set()})
        cell["visited"] = True

        outcome = "unknown"
        if not first and direction:
            if area_change:
                # The whole screen changed: we entered a NEW area (map transition). Start a fresh
                # coordinate frame + map, so the old area's geometry isn't smeared into the new one.
                # BUT seal the way back as a PORTAL: the cell behind us links to the (already-seen)
                # previous area, so it must NOT read as an unexplored frontier — otherwise the
                # autopilot immediately walks back through the door and ping-pongs across the seam
                # (the live door-oscillation bug). The portal stays walkable, just isn't a frontier.
                m["area"] += 1
                back = {"up": "down", "down": "up", "left": "right", "right": "left"}[direction]
                bdx, bdy = _DELTA[back]
                m["cells"] = {(0, 0): {"visited": True, "walls": set()},
                              (bdx, bdy): {"visited": True, "walls": set(),
                                           "portal": m["area"] - 1}}
                m["cursor"] = (0, 0)
                x, y = 0, 0
                cell = m["cells"][(0, 0)]
                outcome = "moved"
            elif moved:
                dx, dy = _DELTA[direction]
                x, y = x + dx, y + dy
                m["cursor"] = (x, y)
                m["cells"].setdefault((x, y), {"visited": True, "walls": set()})["visited"] = True
                cell = m["cells"][(x, y)]
                outcome = "moved"
            else:
                cell["walls"].add(direction)  # bumped a wall in this direction
                outcome = "blocked"

        m["prev_frame"] = np.asarray(frame).copy() if frame is not None else None

        # Affordances: directions from HERE that aren't known walls. Prefer those leading to an
        # unvisited cell (frontiers); fall back to any open direction.
        open_unexplored, open_all = [], []
        for d in _DIRS:
            if d in cell["walls"]:
                continue
            open_all.append(d)
            dx, dy = _DELTA[d]
            nbr = m["cells"].get((x + dx, y + dy))
            if nbr is None or not nbr.get("visited"):
                open_unexplored.append(d)

        visited_n = sum(1 for c in m["cells"].values() if c.get("visited"))
        # Full map + frontier cells, so a LOCAL controller can pathfind without the LLM. A frontier
        # is a visited cell with a non-wall direction into an unvisited (unknown) cell.
        grid, frontiers = [], []
        for (cx, cy), c in m["cells"].items():
            grid.append({"x": cx, "y": cy, "visited": bool(c.get("visited")),
                         "portal": c.get("portal"), "walls": sorted(c["walls"])})
            if not c.get("visited") or c.get("portal") is not None:
                continue  # unvisited, or a portal boundary back to a seen area (not a frontier)
            for d in _DIRS:
                if d in c["walls"]:
                    continue
                ddx, ddy = _DELTA[d]
                nbr = m["cells"].get((cx + ddx, cy + ddy))
                if nbr is None or not nbr.get("visited"):
                    frontiers.append([cx, cy])
                    break

        return SymbolicState(
            confidence=0.4,  # Step 2: keep the image attached; text-only is earned later
            context="overworld",
            pose={"frame": "grid", "value": [x, y], "uncertain": True, "area": m["area"]},
            spatial_memory={"kind": "occupancy-grid", "area": m["area"], "visited": visited_n,
                            "walls_here": sorted(cell["walls"]),
                            "map": grid, "frontiers": frontiers},
            affordances=open_unexplored or open_all,
            last_action={"action": action, "outcome": outcome, "diff": round(diff, 2)},
            raw_available=True,
            raw_ref=ctx.get("frame_path", ""),
        )
