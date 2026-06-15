"""GateWorld — a tiny synthetic world that isolates ONE capability: means-ends reasoning with
backtracking past a *gate* (the dependency problem). See reports/2026-06-15-gating-probe-spec.md.

Why it exists: the free autopilot can only do reactive navigation (class-1). The whole rest of an
RPG is *gates* — "you can't go north until you've fetched the thing that's off to the side" (Red gates
Route 1 behind getting the starter; later: Cut/Surf/Strength/badges). That class-2 reasoning is what an
expensive brain must earn its cost on. But measuring it on Pokémon is contaminated: the model already
*memorised* Pokémon Red, so solving the Oak gate could be recall, not reasoning. GateWorld is fully
synthetic (no walkthrough exists), and ships in two THEMES — a `familiar` skin that invokes a generic
"key opens door" prior and a `novel` skin with no semantic open-relationship — so the same structure,
under a neutral prompt, separates reasoning from recall by the solve-delta between skins.

Design that makes the SAME agent run here unchanged:
  * It speaks the Game Boy button contract (press_button / press_sequence / wait) — so HybridBrain,
    ExploreBrain and LLMButtonBrain need no edits; 'A' is the context-sensitive interact.
  * observe() emits the SAME role-named SymbolicState (pose / spatial_memory{map,frontiers} /
    affordances / last_action / context) the perceiver emits, plus reasoning extras in the text.
  * It is god's-eye (synthetic), so it reports ground-truth walls for visited cells — no perceiver
    needed. RAM has no analogue here; nothing is hidden behind a privileged channel.

The autopilot CANNOT solve it (it only moves, never interacts), so it explores the reachable side,
gets stuck at the gate, and HybridBrain wakes the reasoner — exactly the event the probe measures.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Optional

from core.contracts import Event, Observation, ToolCall, ToolResult, ToolSpec

BUTTONS = ("a", "b", "start", "select", "up", "down", "left", "right")
_DELTA = {"up": (0, -1), "down": (0, 1), "left": (-1, 0), "right": (1, 0)}

# Default layout (x = col, y = row). One wall column (x=3) splits start-side from goal-side, with a
# single GATE opening at (3,2). The item K sits in a side branch on the start-side — AWAY from the
# gate's row — so reaching it is a genuine detour/backtrack, not on the path to the gate.
#   S . . # . . .
#   . . . # . . .
#   . . . G . . .
#   . K . # . . X
#   . . . # . . .
GATE_MAP = [
    "S..#...",
    "...#...",
    "...G...",
    ".K.#..X",
    "...#...",
]


@dataclass(frozen=True)
class Theme:
    """Surface skin only — the world STRUCTURE is identical across themes. The leak control lives in
    how suggestive these strings are; the system prompt stays neutral."""
    name: str
    goal_word: str
    gate_seen: str          # how a still-sealed gate is described once discovered
    gate_needs: str         # cue shown when you interact at the gate WITHOUT the item
    item_seen: str          # how the pickup item is described once discovered
    pickup_msg: str         # outcome text when you pick the item up
    unlock_msg: str         # outcome text when the gate opens

# `familiar`: invokes the universal "key → locked door" prior (recall-friendly).
FAMILIAR = Theme(
    name="familiar", goal_word="the exit",
    gate_seen="a locked door blocks the way",
    gate_needs="the door is locked — it needs a key you don't have",
    item_seen="a key", pickup_msg="you picked up the key",
    unlock_msg="you unlock the door with the key — it swings open")

# `novel`: a barrier and a fragment with NO inherent open-relationship — the link must be inferred
# from the observed mechanic, not from the words.
NOVEL = Theme(
    name="novel", goal_word="the marked tile",
    gate_seen="a humming barrier blocks the way",
    gate_needs="the barrier is sealed — it resists; it seems to need something you don't carry",
    item_seen="a glowing fragment", pickup_msg="you pick up the glowing fragment",
    unlock_msg="the fragment flares and the barrier dissolves")


class GateWorld:
    """A GamePlugin (GamePlugin-only, like the Pokémon world): no reset/step/terminal."""

    def __init__(self, ascii_map: Optional[list[str]] = None, theme: Theme = NOVEL) -> None:
        rows = ascii_map or GATE_MAP
        self.theme = theme
        self.W, self.H = len(rows[0]), len(rows)
        self.floor: set[tuple[int, int]] = set()
        self.gate: Optional[tuple[int, int]] = None
        self.item: Optional[tuple[int, int]] = None
        self.goal: Optional[tuple[int, int]] = None
        self.start = (0, 0)
        for y, line in enumerate(rows):
            for x, ch in enumerate(line):
                c = (x, y)
                if ch == "#":
                    continue
                self.floor.add(c)            # every non-wall cell is walkable floor
                if ch == "S":
                    self.start = c
                elif ch == "G":
                    self.gate = c
                elif ch == "K":
                    self.item = c
                elif ch == "X":
                    self.goal = c

        self.pos = self.start
        self.facing = "down"          # Gen-1 turn-then-move: a press in a NEW direction turns first
        self.has_item = False
        self.gate_open = False
        self.solved = False
        self.visited: set[tuple[int, int]] = {self.start}
        self.seen: set[tuple[int, int]] = set()   # special cells the agent has discovered
        self._events: list[Event] = []
        self._last_action: Optional[dict] = None
        self._steps = 0
        self._reveal()

    # -- GamePlugin surface --------------------------------------------------

    def tools(self, agent_id: str) -> list[ToolSpec]:
        btn = {"type": "string", "enum": list(BUTTONS)}
        return [
            ToolSpec(name="press_button",
                     description=("Press one button. up/down/left/right move one tile; A interacts "
                                  "with what you're on or standing next to; B does nothing."),
                     schema={"type": "object",
                             "properties": {"button": btn},
                             "required": ["button"]},
                     cost=1, mutating=True),
            ToolSpec(name="press_sequence",
                     description="Press several buttons in order in one call (e.g. walk a few tiles).",
                     schema={"type": "object",
                             "properties": {"buttons": {"type": "array", "items": btn,
                                                         "maxItems": 16}},
                             "required": ["buttons"]},
                     cost=1, mutating=True),
            ToolSpec(name="wait", description="Do nothing for a beat.",
                     schema={"type": "object", "properties": {}}, cost=1, mutating=True),
        ]

    def handle(self, call: ToolCall) -> ToolResult:
        try:
            if call.tool == "press_button":
                return self._do([call.args.get("button")], call)
            if call.tool == "press_sequence":
                btns = call.args.get("buttons")
                if not isinstance(btns, list) or not btns:
                    return self._reject(call, "buttons must be a non-empty list")
                return self._do(btns, call)
            if call.tool == "wait":
                return self._post(call, {"action": "wait", "outcome": "no_effect"})
            return self._reject(call, f"unknown tool: {call.tool}",
                                {"available": ["press_button", "press_sequence", "wait"]})
        except Exception as e:  # never raise across the gateway
            return self._reject(call, f"internal error: {e}")

    def observe(self, agent_id: str) -> Observation:
        self._steps += 1
        x, y = self.pos
        grid = [{"x": cx, "y": cy, "visited": True, "walls": self._walls_at((cx, cy))}
                for (cx, cy) in sorted(self.visited)]
        frontiers = [[cx, cy] for (cx, cy) in self.visited
                     if self._is_frontier((cx, cy))]
        affordances = [d for d in ("up", "down", "left", "right")
                       if d not in self._walls_at(self.pos)]
        unexplored = [d for d in affordances
                      if self._step((x, y), d) not in self.visited]
        data = {
            "context": "overworld",
            "pose": {"frame": "grid", "value": [x, y], "area": 0, "uncertain": False},
            "spatial_memory": {"kind": "occupancy-grid", "area": 0,
                               "visited": len(self.visited),
                               "walls_here": self._walls_at(self.pos),
                               "map": grid, "frontiers": frontiers},
            "affordances": unexplored or affordances,
            "last_action": self._last_action or {"action": None, "outcome": "unknown"},
            "confidence": 1.0,           # synthetic world: perception is exact
            "raw_available": False, "raw_ref": "", "screen_path": "",
            # reasoning extras (ignored by the autopilot; surfaced in text for an LLM planner, and
            # read directly by the scripted oracle reasoner). These are positions VISIBLE on the grid
            # once discovered — an observation, not a privileged channel (there is no RAM here).
            "inventory": {"has_item": self.has_item},
            "goal": list(self.goal) if self.goal else None,
            "solved": self.solved,
            "gate_open": self.gate_open,
            "seen": {
                "item": list(self.item) if (self.item and self.item in self.seen) else None,
                "gate": list(self.gate) if (self.gate and self.gate in self.seen) else None,
            },
            "step": self._steps,
        }
        return Observation(data=data, text=self._render(), agent_id=agent_id, t=time.time())

    def drain_events(self) -> list[Event]:
        out, self._events = self._events, []
        return out

    # -- mechanics -----------------------------------------------------------

    def _do(self, buttons: list, call: ToolCall) -> ToolResult:
        for b in buttons:
            if not isinstance(b, str) or b.lower() not in BUTTONS:
                return self._reject(call, f"invalid button: {b!r}", {"valid_buttons": list(BUTTONS)})
        outcome = "no_effect"
        for b in buttons:
            outcome = self._apply(b.lower())
        return self._post(call, {"action": "+".join(str(b) for b in buttons), "outcome": outcome})

    def _apply(self, b: str) -> str:
        if b in _DELTA:
            # Gen-1 overworld semantics (what ExploreBrain's [d,d] = "turn, then move" assumes): a
            # press toward a direction you're not facing only TURNS you (no move); pressing the way
            # you already face actually steps. This keeps stride parity sane (a direction change
            # costs one tile), so the autopilot lands on adjacent frontiers instead of overshooting.
            if self.facing != b:
                self.facing = b
                return "turned"
            target = self._step(self.pos, b)
            if self._passable(target):
                self.pos = target
                self.visited.add(target)
                self._reveal()
                if target == self.goal and not self.solved:
                    self.solved = True
                    self._events.append(Event(type="goal_reached", t=time.time(),
                                              agent_id=None, data={"steps": self._steps},
                                              reward=1.0))
                return "moved"
            return "blocked"
        if b == "a":
            return self._interact()
        return "no_effect"  # b / start / select

    def _interact(self) -> str:
        if self.item is not None and self.pos == self.item and not self.has_item:
            self.has_item = True
            self.item = None
            self._events.append(Event(type="item_picked", t=time.time(), agent_id=None, data={}))
            return "picked"
        if self.gate is not None and not self.gate_open and self._adjacent(self.pos, self.gate):
            if self.has_item:
                self.gate_open = True
                self.has_item = False            # the item is consumed opening the gate
                self._events.append(Event(type="gate_opened", t=time.time(), agent_id=None, data={}))
                return "unlocked"
            return "needs_item"
        return "no_effect"

    def _post(self, call: ToolCall, action: dict) -> ToolResult:
        self._last_action = action
        return ToolResult(call_id=call.call_id, ok=True,
                          data={"action": action["action"], "outcome": action["outcome"],
                                "solved": self.solved, "has_item": self.has_item},
                          cost_charged=1)

    def _reject(self, call: ToolCall, reason: str, extra: Optional[dict] = None) -> ToolResult:
        data = {"valid_buttons": list(BUTTONS)}
        if extra:
            data.update(extra)
        return ToolResult(call_id=call.call_id, ok=False, data=data, error=reason, cost_charged=1)

    # -- geometry / reveal ---------------------------------------------------

    @staticmethod
    def _step(c, d):
        dx, dy = _DELTA[d]
        return (c[0] + dx, c[1] + dy)

    @staticmethod
    def _adjacent(a, b) -> bool:
        return abs(a[0] - b[0]) + abs(a[1] - b[1]) == 1

    def _passable(self, c) -> bool:
        if not (0 <= c[0] < self.W and 0 <= c[1] < self.H):
            return False
        if c == self.gate:
            return self.gate_open
        return c in self.floor

    def _walls_at(self, c) -> list:
        """Ground-truth wall directions from cell c, given the CURRENT gate state (so a wall toward
        the gate clears the instant it opens — turning that direction into a fresh frontier)."""
        return [d for d in ("up", "down", "left", "right") if not self._passable(self._step(c, d))]

    def _is_frontier(self, c) -> bool:
        for d in ("up", "down", "left", "right"):
            nb = self._step(c, d)
            if self._passable(nb) and nb not in self.visited:
                return True
        return False

    def _reveal(self) -> None:
        """Discover special cells adjacent to (or under) the current position — they then appear in
        the text so the planner can reason about them."""
        for c in (self.pos, *(self._step(self.pos, d) for d in _DELTA)):
            if c in (self.gate, self.item, self.goal) and c is not None:
                self.seen.add(c)

    # -- rendering -----------------------------------------------------------

    def _render(self) -> str:
        t = self.theme
        x, y = self.pos
        lines = [f"You are on a tile grid at ({x},{y}). Reach {t.goal_word} to finish."]
        if self.goal:
            gx, gy = self.goal
            comp = self._compass((gx, gy))
            lines.append(f"{t.goal_word.capitalize()} is at ({gx},{gy}) — {comp} from you.")
        if self.gate and self.gate in self.seen and not self.gate_open:
            comp = self._compass(self.gate)
            lines.append(f"At ({self.gate[0]},{self.gate[1]}), {comp} of you, {t.gate_seen}.")
        if self.item and self.item in self.seen and not self.has_item:
            comp = self._compass(self.item)
            lines.append(f"You can see {t.item_seen} at ({self.item[0]},{self.item[1]}), {comp} of you.")
        lines.append(f"You are carrying: {'the ' + t.item_seen.split(' ', 1)[-1] if self.has_item else 'nothing'}.")
        la = self._last_action or {}
        msg = {"moved": "you moved.", "blocked": "that way is blocked by a wall.",
               "turned": "you turn to face that way.",
               "picked": t.pickup_msg + ".", "unlocked": t.unlock_msg + ".",
               "needs_item": t.gate_needs + ".", "no_effect": "nothing happened.",
               "unknown": ""}.get(la.get("outcome"), "")
        if msg:
            lines.append(f"Last action ({la.get('action')}): {msg}")
        lines.append("Move with up/down/left/right; press A to interact when on or next to something.")
        return "\n".join(lines)

    def _compass(self, target) -> str:
        x, y = self.pos
        tx, ty = target
        v = ("north" if ty < y else "south" if ty > y else "")
        h = ("west" if tx < x else "east" if tx > x else "")
        return (v + h) or "here"
