"""Smoke test: can Haiku drive the Pokémon harness using Red's constitution?

Bypasses Docker/aria-server. Builds a complete_fn that calls the Anthropic API
(claude-haiku-4-5) directly with:
  system  = Red's assembled constitution (rendered earlier to red_system_prompt.txt)
  user    = the harness's THINK/MOVE prompt + the live screenshot (vision)
…then runs a short episode on the real emulator and prints Haiku's reasoning + moves.

This faithfully mirrors what the aria server would send, minus aria's journal/memory
writes. It is an evaluation script, not part of the harness.
"""
from __future__ import annotations

import base64
import os
import sys
import uuid
from pathlib import Path

import requests

from core.brains import LLMButtonBrain
from core.gateway import Gateway
from core.permissions import POKEMON_SANDBOX
from core.runner import run_episode

ROM = sys.argv[1] if len(sys.argv) > 1 else "roms/Pokemon Red Version (Colorization).gb"
STEPS = int(sys.argv[2]) if len(sys.argv) > 2 else 18
MODEL = "claude-haiku-4-5"

RED_PROMPT = Path("red_system_prompt.txt").read_text(encoding="utf-8")


def _api_key() -> str:
    if os.environ.get("ANTHROPIC_API_KEY"):
        return os.environ["ANTHROPIC_API_KEY"]
    env = Path("../ai-aria/.env")
    for line in env.read_text(encoding="utf-8").splitlines():
        if line.startswith("ANTHROPIC_API_KEY="):
            return line.split("=", 1)[1].strip()
    raise SystemExit("no ANTHROPIC_API_KEY found")


KEY = _api_key()


def haiku_complete(prompt: str, image_path: str | None) -> str:
    content: list = [{"type": "text", "text": prompt}]
    if image_path:
        try:
            b64 = base64.b64encode(Path(image_path).read_bytes()).decode()
            content.append({"type": "image", "source": {
                "type": "base64", "media_type": "image/png", "data": b64}})
        except OSError:
            pass
    r = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers={"x-api-key": KEY, "anthropic-version": "2023-06-01",
                 "content-type": "application/json"},
        json={"model": MODEL, "max_tokens": 100, "temperature": 0,
              "system": RED_PROMPT,
              "messages": [{"role": "user", "content": content}]},
        timeout=120,
    )
    r.raise_for_status()
    parts = [b.get("text", "") for b in r.json().get("content", []) if b.get("type") == "text"]
    return "".join(parts)


def main() -> int:
    agent_id = f"agent-{uuid.uuid4()}"
    from games.pokemon_red import PokemonRedPlugin
    plugin = PokemonRedPlugin(rom_path=ROM, out_dir="runs/haiku_eval", headless=True)
    brain = LLMButtonBrain(agent_id, complete_fn=haiku_complete, use_vision=True)
    gateway = Gateway(plugin, POKEMON_SANDBOX)

    def on_step(step, obs, result, events):
        think = getattr(brain, "last_thought", "")[:120].encode("ascii", "replace").decode()
        action = getattr(result, "data", {}).get("action", "")
        print(f"[{step:02d}] move={action!s:<22} think: {think}")

    print(f"=== Haiku ({MODEL}) playing for {STEPS} steps (vision, from boot) ===\n")
    try:
        summary = run_episode(gateway, plugin, brain, agent_id, max_steps=STEPS, on_step=on_step)
    finally:
        plugin.close()
    print("\n=== summary ===")
    for k, v in summary.items():
        print(f"  {k}: {v}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
