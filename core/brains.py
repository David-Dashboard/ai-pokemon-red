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


_SYSTEM = (
    "You are playing Pokémon Red on a Game Boy. Decide the single best next "
    "button press to make progress (explore, win battles, earn badges).\n"
    "Reply with EXACTLY one token from this list and nothing else:\n"
    "a, b, start, select, up, down, left, right\n"
    "(a = confirm/interact, b = cancel/back, d-pad = walk)."
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
    ) -> None:
        self.agent_id = agent_id
        self.use_vision = use_vision
        self.complete = complete_fn or _ollama_complete(model, url)

    def decide(self, obs: Observation, tools: list[ToolSpec], context: dict) -> Optional[ToolCall]:
        strategy = context.get("strategy", "")  # KB-injected strategy doc, if any
        prompt = f"{_SYSTEM}\n\n{strategy}\n\nCurrent state:\n{obs.text}\n\nNext button:"
        image = obs.data.get("screen_path") if self.use_vision else None
        try:
            raw = self.complete(prompt, image)
        except Exception as e:
            print(f"[LLMButtonBrain] model call failed ({e}); defaulting to 'a'")
            return _call("press_button", {"button": "a"}, self.agent_id)
        return _call("press_button", {"button": self._parse(raw)}, self.agent_id)

    @staticmethod
    def _parse(raw: str) -> str:
        text = raw.strip().lower()
        # Try strict JSON first, then fall back to first button keyword seen.
        try:
            obj = json.loads(text)
            if isinstance(obj, dict) and obj.get("button") in BUTTONS:
                return obj["button"]
        except (json.JSONDecodeError, TypeError):
            pass
        for token in text.replace(",", " ").replace("\n", " ").split():
            if token in BUTTONS:
                return token
        return "a"  # safe default: advance
