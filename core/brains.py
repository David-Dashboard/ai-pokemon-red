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
import uuid
from typing import Callable, Optional

from core.contracts import Observation, ToolCall, ToolSpec

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
    "MOVE: <2-4 buttons separated by spaces, from: up down left right a b>"
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
        prompt = (f"{_SYSTEM}\n\n{strategy}\n{feedback}\n\n"
                  f"Current state:\n{obs.text}\n\nYour reply:")
        image = obs.data.get("screen_path") if self.use_vision else None
        try:
            raw = self.complete(prompt, image)
        except Exception as e:
            print(f"[LLMButtonBrain] model call failed ({e}); defaulting to 'a'")
            return _call("press_button", {"button": "a"}, self.agent_id)
        buttons, thought = self._parse(raw)
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
