"""Brains — everything that decides (the Brain protocol).

Two are provided:

  * ScriptedBrain — zero-dependency. A seeded "mash A and wander" policy that
    proves the whole pipeline (gateway → plugin → emulator) end to end without
    any model. This is your smoke test.

  * LLMButtonBrain — an LLM agent. Builds a prompt from the observation's text
    (and optionally the screenshot, for vision models) and asks a local Ollama
    model for the next button. Provider is pluggable via `complete_fn`; the
    default talks to Ollama over HTTP. Point it at Claude/any API by passing
    your own complete_fn.

Both obey invariant 13: one ToolCall per decide() call. Multi-step play is the
runner looping, not a fatter brain.
"""

from __future__ import annotations

import base64
import json
import random
import re
import uuid
from typing import Callable, Optional

from core.contracts import Observation, ToolCall, ToolSpec
from core.outcome import OutcomeMemory, action_key, state_signature

BUTTONS = ("a", "b", "start", "select", "up", "down", "left", "right")


def _call(tool: str, args: dict, agent_id: str) -> ToolCall:
    return ToolCall(tool=tool, args=args, agent_id=agent_id, call_id=f"call-{uuid.uuid4()}")


class ScriptedBrain:
    """Deterministic smoke-test policy: mostly advance dialog, sometimes walk."""

    def __init__(self, agent_id: str, seed: int = 0) -> None:
        self.agent_id = agent_id
        self.rng = random.Random(seed)

    def decide(self, obs: Observation, tools: list[ToolSpec], context: dict) -> Optional[ToolCall]:
        # 60% press A (advance text / confirm), 40% a random walk direction.
        if self.rng.random() < 0.6:
            button = "a"
        else:
            button = self.rng.choice(["up", "down", "left", "right"])
        return _call("press_button", {"button": button}, self.agent_id)


_DELTA = {"up": (0, -1), "down": (0, 1), "left": (-1, 0), "right": (1, 0)}


class ExploreBrain:
    """Local frontier-exploration autopilot — NO LLM, NO API. Reads the SymbolicState's occupancy
    map and BFS-paths to the nearest frontier, stepping there two presses at a time (turn+move) so a
    turn-in-place isn't misread as a wall. This is the cheap controller that does routine traversal,
    so an expensive brain is only needed at real decisions. Returns None when no frontier remains
    (exploration of the known area is exhausted)."""

    def __init__(self, agent_id: str) -> None:
        self.agent_id = agent_id
        self.last_thought = ""

    def decide(self, obs: Observation, tools: list[ToolSpec], context: dict) -> Optional[ToolCall]:
        sm = obs.data.get("spatial_memory") or {}
        pose = (obs.data.get("pose") or {}).get("value")
        cells = {(c["x"], c["y"]): c for c in sm.get("map", [])}
        if pose is None:
            self.last_thought = "bootstrap"
            return self._move("down")
        cur = (pose[0], pose[1])
        # goto(target): if the planner set a destination, pathfind to it (free); when it's reached
        # or unreachable from the known map, fall through to ordinary frontier exploration.
        goto = (context or {}).get("goto")
        if goto is not None and tuple(goto[:2]) != cur:
            d = self._bfs_first_step(cur, cells, {tuple(goto[:2])})
            if d:
                self.last_thought = f"goto {tuple(goto[:2])} via {d}"
                return self._move(d)
        d = self._unexplored_dir(cur, cells)
        if d:
            self.last_thought = f"frontier here -> {d}"
            return self._move(d)
        d = self._bfs_first_step(cur, cells, {tuple(f) for f in sm.get("frontiers", [])})
        if d:
            self.last_thought = f"to nearest frontier via {d}"
            return self._move(d)
        self.last_thought = "no reachable frontier — area explored"
        return None

    @staticmethod
    def _unexplored_dir(cur, cells) -> Optional[str]:
        walls = set(cells.get(cur, {}).get("walls", []))
        for d in ("up", "down", "left", "right"):
            if d in walls:
                continue
            dx, dy = _DELTA[d]
            nbr = cells.get((cur[0] + dx, cur[1] + dy))
            if nbr is None or not nbr.get("visited"):
                return d
        return None

    @staticmethod
    def _bfs_first_step(cur, cells, frontiers) -> Optional[str]:
        from collections import deque
        prev = {cur: None}
        q = deque([cur])
        while q:
            node = q.popleft()
            if node != cur and node in frontiers:
                path = [node]
                while prev[path[-1]] is not None:
                    path.append(prev[path[-1]])
                step = path[-2]  # first cell after cur on the path back
                dx, dy = step[0] - cur[0], step[1] - cur[1]
                return next((k for k, v in _DELTA.items() if v == (dx, dy)), None)
            walls = set(cells.get(node, {}).get("walls", []))
            for d in ("up", "down", "left", "right"):
                if d in walls:
                    continue
                dx, dy = _DELTA[d]
                nb = (node[0] + dx, node[1] + dy)
                if nb in cells and cells[nb].get("visited") and nb not in prev:
                    prev[nb] = node
                    q.append(nb)
        return None

    def _move(self, d: str) -> ToolCall:
        return _call("press_sequence", {"buttons": [d, d]}, self.agent_id)  # turn, then move


class HybridBrain:
    """Event-driven router (the cost win): run a free local autopilot by default, and WAKE an
    expensive brain (the LLM) only at real decisions —
      * a non-overworld mode (battle / menu / dialog), when perception reports `context != overworld`, or
      * the autopilot is stuck (no frontier left to explore).
    Dozens of free moves between rare LLM calls. `wake_rate` reports how often the expensive brain
    was actually needed. The mode trigger is dormant until perception sets `context` (the CV sub-step)."""

    def __init__(self, autopilot, fallback) -> None:
        self.autopilot = autopilot
        self.fallback = fallback
        self.last_thought = ""
        self.woke = 0
        self.total = 0
        self.mode = "autopilot"
        self.outcome = OutcomeMemory()   # feature #1: learn which actions do nothing here
        self._last_sig = None
        self._last_action = None
        # feature #2 (goto hookup): a destination the woken planner named, persisted so the FREE
        # autopilot drives there over the next overworld steps without re-waking the LLM each tile.
        self.goto: Optional[list] = None

    def decide(self, obs: Observation, tools: list[ToolSpec], context: dict) -> Optional[ToolCall]:
        self.total += 1
        sig = state_signature(obs.data)
        if self._last_action is not None:  # grade the PREVIOUS action: did the situation change?
            self.outcome.record(self._last_sig, self._last_action, effective=(sig != self._last_sig))
        # tell whoever decides which actions have repeatedly done nothing here, so it doesn't repeat them
        context = {**(context or {}), "avoid": self.outcome.dead_actions(sig)}

        # goto(target): consume it on arrival, else hand the persistent target to the free autopilot.
        pose = (obs.data.get("pose") or {}).get("value")
        if self.goto is not None and pose is not None and list(pose) == list(self.goto):
            self.goto = None                          # arrived — destination reached, stop steering there
        if self.goto is not None:
            context["goto"] = self.goto               # the autopilot BFS-pathfinds toward it (free), else explores

        if (obs.data.get("context") or "overworld") != "overworld":
            call = self._wake(obs, tools, context, "mode")
        else:
            call = self.autopilot.decide(obs, tools, context)
            if call is not None:
                self.mode = "autopilot"
                self.last_thought = getattr(self.autopilot, "last_thought", "")
            else:
                call = self._wake(obs, tools, context, "stuck")  # autopilot exhausted -> LLM
        self._last_sig = sig
        self._last_action = action_key(call)
        return call

    def _wake(self, obs, tools, context, why: str) -> Optional[ToolCall]:
        self.mode = "llm"
        self.woke += 1
        call = self.fallback.decide(obs, tools, context)
        # If the planner named a destination this turn, adopt it — the free autopilot pursues it on
        # the next overworld steps (no GOTO = keep any target already in flight).
        named = getattr(self.fallback, "goto", None)
        if named is not None:
            self.goto = named
        tail = f" goto={self.goto}" if self.goto else ""
        self.last_thought = (f"[wake:{why}] "
                             f"{getattr(self.fallback, 'last_thought', '')}{tail}").strip()
        return call

    @property
    def wake_rate(self) -> float:
        return self.woke / self.total if self.total else 0.0


def _ollama_complete(model: str, url: str) -> Callable[[str, Optional[str]], str]:
    """Return a complete_fn(prompt, image_path) -> text backed by Ollama."""
    import requests

    def complete(prompt: str, image_path: Optional[str]) -> str:
        payload: dict = {"model": model, "prompt": prompt, "stream": False}
        if image_path:
            try:
                with open(image_path, "rb") as f:
                    payload["images"] = [base64.b64encode(f.read()).decode()]
            except OSError:
                pass
        r = requests.post(f"{url}/api/generate", json=payload, timeout=120)
        r.raise_for_status()
        return r.json().get("response", "")

    return complete


def _openai_complete(
    model: str, url: str, api_key: Optional[str] = None
) -> Callable[[str, Optional[str]], str]:
    """complete_fn for an OpenAI-compatible /v1/chat/completions endpoint —
    e.g. llama.cpp's `llama-server` (run it with `--mmproj` for vision), or the
    decoupled `ai-aria` companion (POST :8001, bearer-authed, vision via data
    URIs). Also works with any OpenAI-shaped server. Images ride as base64 data
    URIs. Pass api_key to send an `Authorization: Bearer <key>` header."""
    import requests

    headers = {"Authorization": f"Bearer {api_key}"} if api_key else None

    def complete(prompt: str, image_path: Optional[str]) -> str:
        content: list = [{"type": "text", "text": prompt}]
        if image_path:
            try:
                with open(image_path, "rb") as f:
                    b64 = base64.b64encode(f.read()).decode()
                content.append({"type": "image_url",
                                "image_url": {"url": f"data:image/png;base64,{b64}"}})
            except OSError:
                pass
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": content}],
            "stream": False,
            "max_tokens": 64,   # room for a one-line THINK + the MOVE
            "temperature": 0,
        }
        r = requests.post(f"{url}/v1/chat/completions", json=payload,
                          headers=headers, timeout=120)
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]

    return complete


_SYSTEM = (
    "You are playing Pokémon Red (top-down view). You control the small trainer "
    "sprite. Your job right now is to EXPLORE — walk to doors, stairs, and exits to "
    "reach new areas.\n"
    "Move with the d-pad. A single tap only TURNS you to face that way, so send a "
    "direction 2-4 times to actually walk, e.g. 'down down down'. Press A ONLY to "
    "talk to a person or confirm a dialog box; do NOT press A in an empty room. "
    "Never press START or SELECT.\n"
    "Reply in EXACTLY this format and nothing else:\n"
    "THINK: <one short sentence — what you see and what you'll do>\n"
    "MOVE: <2-4 buttons separated by spaces, from: up down left right a b>\n"
    "Optionally add a final line 'GOTO: x y' to send yourself to a known map cell "
    "(coordinates are shown when available); a free pathfinder then walks you there over the "
    "next steps, so you needn't steer every tile."
)


class LLMButtonBrain:
    """LLM agent that picks one button per turn from the observation."""

    def __init__(
        self,
        agent_id: str,
        model: str = "llama3.2-vision",
        url: str = "http://localhost:11434",
        use_vision: bool = True,
        complete_fn: Optional[Callable[[str, Optional[str]], str]] = None,
        backend: str = "ollama",
        api_key: Optional[str] = None,
    ) -> None:
        self.agent_id = agent_id
        self.use_vision = use_vision
        self.last_thought = ""       # the model's latest reasoning, for display
        self.goto: Optional[list] = None  # destination cell the planner named this turn (or None)
        self._last_pos = None        # (x, y) at the previous decision
        self._last_buttons = None    # what we pressed last, for wall-bump feedback
        if complete_fn is not None:
            self.complete = complete_fn
        elif backend == "ollama":
            self.complete = _ollama_complete(model, url)
        # `aria` is the decoupled ai-aria companion: same OpenAI wire format as
        # llamacpp/openai, but bearer-authed. It runs as its own service — we only
        # speak HTTP to it, importing none of its code.
        elif backend in ("llamacpp", "openai", "aria"):
            self.complete = _openai_complete(model, url, api_key=api_key)
        else:
            raise ValueError(
                f"unknown LLM backend: {backend!r} (use 'ollama', 'llamacpp', or 'aria')")

    def decide(self, obs: Observation, tools: list[ToolSpec], context: dict) -> Optional[ToolCall]:
        strategy = context.get("strategy", "")  # KB-injected strategy doc, if any
        feedback = self._movement_feedback(obs)
        avoid = context.get("avoid") or []      # actions that did nothing here (outcome memory)
        if avoid:
            feedback = (feedback + f"\nNOTE: these did NOTHING here, do NOT repeat them: "
                        f"{', '.join(avoid)}. Try something different.").strip()
        prompt = (f"{_SYSTEM}\n\n{strategy}\n{feedback}\n\n"
                  f"Current state:\n{obs.text}\n\nYour reply:")
        image = obs.data.get("screen_path") if self.use_vision else None
        try:
            raw = self.complete(prompt, image)
        except Exception as e:
            print(f"[LLMButtonBrain] model call failed ({e}); defaulting to 'a'")
            return _call("press_button", {"button": "a"}, self.agent_id)
        buttons, thought = self._parse(raw)
        self.goto = self._parse_goto(raw)   # optional destination for the free autopilot (feature #2)
        self.last_thought = thought or raw.strip()[:160]
        self._last_pos = (obs.data.get("x"), obs.data.get("y"))
        self._last_buttons = buttons
        if len(buttons) == 1:
            return _call("press_button", {"button": buttons[0]}, self.agent_id)
        return _call("press_sequence", {"buttons": buttons}, self.agent_id)

    def _movement_feedback(self, obs: Observation) -> str:
        """Tell the model when its previous move hit a wall (position unchanged). Skipped in
        perception mode (no RAM x/y) — the wall signal comes from the symbolic text instead."""
        if obs.data.get("x") is None:
            return ""
        pos = (obs.data.get("x"), obs.data.get("y"))
        dirs = {"up", "down", "left", "right"}
        if (self._last_pos is not None and pos == self._last_pos
                and self._last_buttons and set(self._last_buttons) & dirs):
            return (f"NOTE: your last move ({' '.join(self._last_buttons)}) did NOT "
                    f"move you — you walked into a wall. Pick a DIFFERENT direction.")
        return ""

    @staticmethod
    def _parse(raw: str, max_buttons: int = 4) -> tuple[list[str], str]:
        """Return (buttons, thought). When the model uses the THINK/MOVE format,
        buttons are taken only from the MOVE line — so direction words in the
        reasoning ('head down to the stairs') aren't mistaken for inputs.
        Otherwise scan the whole reply."""
        text = raw.strip()
        thought, move_src = "", None
        for line in text.splitlines():
            low = line.strip().lower()
            if low.startswith("think:"):
                thought = line.split(":", 1)[1].strip()
            elif low.startswith(("move:", "buttons:", "action:")):
                move_src = line.split(":", 1)[1]
        src = move_src if move_src is not None else text
        picks = [t for t in src.lower().replace(",", " ").split() if t in BUTTONS]
        if not picks:  # MOVE line empty/garbled — scan the whole reply
            picks = [t for t in text.lower().replace(",", " ").split() if t in BUTTONS]
        return picks[:max_buttons] or ["a"], thought  # 'a' = safe default

    @staticmethod
    def _parse_goto(raw: str) -> Optional[list]:
        """Optional 'GOTO: x y' (or 'x,y') line -> [x, y]; None if absent/garbled. This is the
        planner naming a destination cell once; HybridBrain persists it and the local autopilot
        pathfinds there for free (no per-tile LLM calls). Only read from a dedicated GOTO line so
        coordinates mentioned in prose ('go to the door') aren't mistaken for a target."""
        for line in raw.splitlines():
            if line.strip().lower().startswith("goto:"):
                nums = re.findall(r"-?\d+", line.split(":", 1)[1])
                if len(nums) >= 2:
                    return [int(nums[0]), int(nums[1])]
        return None
