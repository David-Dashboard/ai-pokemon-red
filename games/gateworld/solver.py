"""ScriptedReasoner — a FREE, deterministic stand-in for the LLM in the gating probe.

It demonstrates that GateWorld is solvable through the *same* HybridBrain loop the Pokémon agent
uses — autopilot explores for free, gets stuck at the gate, and this reasoner is woken to do the
means-ends part (fetch the item, return, apply it). Swapping this for LLMButtonBrain (with a neutral
system prompt) is the ONLY change needed for the real, credit-gated measurement; everything else —
the world, the router, the scoring — is identical.

It is an *oracle* reasoner: it reads the item/gate/goal positions the world surfaces in
Observation.data and plans BFS over the known (visited) map. That makes it a clean plumbing check
and the upper bound the LLM is measured against — it is NOT itself the experiment.
"""
from __future__ import annotations

import uuid
from collections import deque
from typing import Optional

from core.contracts import Observation, ToolCall, ToolSpec

_DELTA = {"up": (0, -1), "down": (0, 1), "left": (-1, 0), "right": (1, 0)}


def _call(tool: str, args: dict, agent_id: str) -> ToolCall:
    return ToolCall(tool=tool, args=args, agent_id=agent_id, call_id=f"call-{uuid.uuid4()}")


class ScriptedReasoner:
    """Means-ends plan: if blocked from the goal by the gate, (1) fetch the item, (2) walk adjacent
    to the gate, (3) interact to open it, then (4) head for the goal. Pathfinds with BFS over the
    cells the world has revealed (visited)."""

    def __init__(self, agent_id: str) -> None:
        self.agent_id = agent_id
        self.last_thought = ""
        self.goto: Optional[list] = None   # honored by HybridBrain, though this brain self-navigates

    def decide(self, obs: Observation, tools: list[ToolSpec], context: dict) -> Optional[ToolCall]:
        d = obs.data
        pos = tuple((d.get("pose") or {}).get("value") or (0, 0))
        cells = {(c["x"], c["y"]): c for c in (d.get("spatial_memory") or {}).get("map", [])}
        has_item = bool((d.get("inventory") or {}).get("has_item"))
        goal = d.get("goal")
        seen = d.get("seen") or {}
        item = seen.get("item")      # discovered item position, or None
        gate = seen.get("gate")      # discovered gate position, or None
        gate_open = d.get("gate_open")

        if not has_item and item is not None:
            self.last_thought = f"fetch item at {tuple(item)}"
            return self._toward(pos, tuple(item), cells, interact_on_arrive=True)
        if gate is not None and gate_open is False:
            self.last_thought = f"carry item to gate at {tuple(gate)}"
            return self._toward_adjacent(pos, tuple(gate), cells, interact_on_arrive=True)
        if goal is not None:
            self.last_thought = f"head for goal {tuple(goal)}"
            return self._toward(pos, tuple(goal), cells, interact_on_arrive=False)
        self.last_thought = "no plan; nudging"
        return self._move("down")

    # -- helpers -------------------------------------------------------------

    def _move(self, d: str) -> ToolCall:           # turn, then step (net 1 tile, like ExploreBrain)
        return _call("press_sequence", {"buttons": [d, d]}, self.agent_id)

    def _press(self, b: str) -> ToolCall:
        return _call("press_button", {"button": b}, self.agent_id)

    def _toward(self, pos, target, cells, interact_on_arrive: bool) -> ToolCall:
        if pos == target:
            return self._press("a") if interact_on_arrive else self._move("down")
        step = self._bfs_step(pos, {target}, cells)
        if step is None:                      # target not yet reachable on the known map — explore
            step = next(iter(self._open_dirs(pos, cells)), "down")
        return self._move(step)

    def _toward_adjacent(self, pos, target, cells, interact_on_arrive: bool) -> ToolCall:
        if self._adjacent(pos, target):
            return self._press("a")
        goals = {self._add(target, _DELTA[dd]) for dd in _DELTA}
        goals &= set(cells)                   # adjacent cells we actually know
        step = self._bfs_step(pos, goals, cells)
        if step is None:
            step = next(iter(self._open_dirs(pos, cells)), "down")
        return self._move(step)

    @staticmethod
    def _add(a, b):
        return (a[0] + b[0], a[1] + b[1])

    @staticmethod
    def _adjacent(a, b) -> bool:
        return abs(a[0] - b[0]) + abs(a[1] - b[1]) == 1

    @staticmethod
    def _open_dirs(pos, cells):
        walls = set(cells.get(pos, {}).get("walls", []))
        return [d for d in ("up", "down", "left", "right") if d not in walls]

    def _bfs_step(self, start, goals, cells) -> Optional[str]:
        """First move on a shortest path from start to any cell in `goals`, over known cells."""
        if start in goals:
            return None
        prev = {start: None}
        q = deque([start])
        while q:
            node = q.popleft()
            if node in goals and node != start:
                path = [node]
                while prev[path[-1]] is not None:
                    path.append(prev[path[-1]])
                nxt = path[-2]
                dx, dy = nxt[0] - start[0], nxt[1] - start[1]
                return next((k for k, v in _DELTA.items() if v == (dx, dy)), None)
            walls = set(cells.get(node, {}).get("walls", []))
            for d in ("up", "down", "left", "right"):
                if d in walls:
                    continue
                nb = self._add(node, _DELTA[d])
                if (nb in cells or nb in goals) and nb not in prev:
                    prev[nb] = node
                    q.append(nb)
        return None
