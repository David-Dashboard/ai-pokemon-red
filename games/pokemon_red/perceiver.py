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
_MOVE_THRESHOLD = 4.0  # mean abs pixel diff above which we count "the screen changed" (a move)


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


class OverworldPerceiver:
    """Frame-diff walkability + a dead-reckoned occupancy map. All state lives in PerceptMemory."""

    def __init__(self, move_threshold: float = _MOVE_THRESHOLD) -> None:
        self.move_threshold = move_threshold

    def perceive(self, frame, memory: PerceptMemory,
                 context: Optional[JSON] = None) -> SymbolicState:
        ctx = context or {}
        m = memory.data
        m.setdefault("cursor", (0, 0))
        m.setdefault("cells", {})          # (x,y) -> {"visited": bool, "walls": set[str]}
        m.setdefault("prev_frame", None)
        m.setdefault("steps", 0)

        action = ctx.get("last_action")
        direction = _dominant_dir(action)
        prev = m["prev_frame"]
        first = prev is None
        diff = _frame_diff(prev, frame)
        moved = None if first else (diff > self.move_threshold)

        x, y = m["cursor"]
        cell = m["cells"].setdefault((x, y), {"visited": True, "walls": set()})
        cell["visited"] = True

        outcome = "unknown"
        if not first and direction:
            if moved:
                dx, dy = _DELTA[direction]
                x, y = x + dx, y + dy
                m["cursor"] = (x, y)
                m["cells"].setdefault((x, y), {"visited": True, "walls": set()})["visited"] = True
                cell = m["cells"][(x, y)]
                outcome = "moved"
            else:
                cell["walls"].add(direction)  # bumped a wall in this direction
                outcome = "blocked"

        m["steps"] += 1
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
        return SymbolicState(
            confidence=0.4,  # Step 2: keep the image attached; text-only is earned in Step 3
            context="overworld",
            pose={"frame": "grid", "value": [x, y], "uncertain": True},
            spatial_memory={"kind": "occupancy-grid", "area": 0,
                            "visited": visited_n, "walls_here": sorted(cell["walls"])},
            affordances=open_unexplored or open_all,
            last_action={"action": action, "outcome": outcome},
            raw_available=True,
            raw_ref=ctx.get("frame_path", ""),
        )
