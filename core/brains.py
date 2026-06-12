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


def _openai_complete(model: str, url: str) -> Callable[[str, Optional[str]], str]:
    """complete_fn for an OpenAI-compatible /v1/chat/completions endpoint —
    e.g. llama.cpp's `llama-server` (run it with `--mmproj` for vision). Also
    works with any OpenAI-shaped server. Images ride as base64 data URIs."""
    import requests

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
            "max_tokens": 16,
            "temperature": 0,
        }
        r = requests.post(f"{url}/v1/chat/completions", json=payload, timeout=120)
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]

    return complete


_SYSTEM = (
    "You are playing Pokémon Red (top-down view). You control the small trainer "
    "sprite. Your job right now is to EXPLORE — walk to doors, stairs, and exits to "
    "reach new areas.\n"
    "Move with the d-pad. A single tap only TURNS you to face that way, so send a "
    "direction 2-4 times to actually walk, e.g. 'down down down'. Press A ONLY to "
    "talk to a person or confirm a dialog box; do NOT press A in an empty room — it "
    "wastes the turn. Never press START or SELECT.\n"
    "Reply with ONLY 2-4 movement buttons separated by spaces, e.g. 'left left up'. "
    "Allowed: up down left right a b."
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
    ) -> None:
        self.agent_id = agent_id
        self.use_vision = use_vision
        if complete_fn is not None:
            self.complete = complete_fn
        elif backend == "ollama":
            self.complete = _ollama_complete(model, url)
        elif backend in ("llamacpp", "openai"):
            self.complete = _openai_complete(model, url)
        else:
            raise ValueError(f"unknown LLM backend: {backend!r} (use 'ollama' or 'llamacpp')")

    def decide(self, obs: Observation, tools: list[ToolSpec], context: dict) -> Optional[ToolCall]:
        strategy = context.get("strategy", "")  # KB-injected strategy doc, if any
        prompt = f"{_SYSTEM}\n\n{strategy}\n\nCurrent state:\n{obs.text}\n\nButtons:"
        image = obs.data.get("screen_path") if self.use_vision else None
        try:
            raw = self.complete(prompt, image)
        except Exception as e:
            print(f"[LLMButtonBrain] model call failed ({e}); defaulting to 'a'")
            return _call("press_button", {"button": "a"}, self.agent_id)
        buttons = self._parse(raw)
        if len(buttons) == 1:
            return _call("press_button", {"button": buttons[0]}, self.agent_id)
        return _call("press_sequence", {"buttons": buttons}, self.agent_id)

    @staticmethod
    def _parse(raw: str, max_buttons: int = 4) -> list[str]:
        """Extract an ordered list of buttons from the model's reply (1..max)."""
        text = raw.strip().lower()
        # Try strict JSON first ({"buttons": [...]} or {"button": "x"}).
        try:
            obj = json.loads(text)
            if isinstance(obj, dict):
                seq = obj.get("buttons")
                if isinstance(seq, list):
                    picks = [b for b in seq if b in BUTTONS]
                    if picks:
                        return picks[:max_buttons]
                if obj.get("button") in BUTTONS:
                    return [obj["button"]]
        except (json.JSONDecodeError, TypeError):
            pass
        # Fall back to the button keywords in order, capped.
        picks = [t for t in text.replace(",", " ").replace("\n", " ").split() if t in BUTTONS]
        return picks[:max_buttons] or ["a"]  # safe default: advance
