"""Run an agent on Pokémon Red.

Examples:
    # zero-dependency smoke test (still needs PyBoy + your own ROM):
    python play_pokemon.py --rom path/to/PokemonRed.gb --brain scripted --steps 50

    # LLM agent via a local Ollama vision model:
    python play_pokemon.py --rom path/to/PokemonRed.gb --brain llm \
        --model llama3.2-vision --steps 200 --window

You must supply your own legally-obtained Pokémon Red ROM. None is bundled.
"""

from __future__ import annotations

import argparse
import sys
import uuid

from core.gateway import Gateway
from core.permissions import POKEMON_SANDBOX
from core.runner import run_episode


def main() -> int:
    ap = argparse.ArgumentParser(description="Let an AI agent play Pokémon Red.")
    ap.add_argument("--rom", required=True, help="path to your Pokémon Red ROM (.gb)")
    ap.add_argument("--brain", choices=["scripted", "llm"], default="scripted")
    ap.add_argument("--steps", type=int, default=100)
    ap.add_argument("--model", default="llama3.2-vision", help="Ollama model for --brain llm")
    ap.add_argument("--ollama-url", default="http://localhost:11434")
    ap.add_argument("--no-vision", action="store_true", help="text-only LLM prompt")
    ap.add_argument("--window", action="store_true", help="show the emulator window")
    ap.add_argument("--out", default="runs/pokemon_red")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--load-state", default=None,
                    help="boot from a .state saved past the intro (see human_play.py)")
    ap.add_argument("--save-state", default=None,
                    help="write the final emulator state here when the run ends")
    args = ap.parse_args()

    agent_id = f"agent-{uuid.uuid4()}"

    try:
        from games.pokemon_red import PokemonRedPlugin
        plugin = PokemonRedPlugin(rom_path=args.rom, out_dir=args.out,
                                  headless=not args.window, init_state=args.load_state)
    except (FileNotFoundError, ImportError) as e:
        print(f"\nSetup error:\n{e}\n", file=sys.stderr)
        return 2

    if args.brain == "llm":
        from core.brains import LLMButtonBrain
        brain = LLMButtonBrain(agent_id, model=args.model, url=args.ollama_url,
                               use_vision=not args.no_vision)
    else:
        from core.brains import ScriptedBrain
        brain = ScriptedBrain(agent_id, seed=args.seed)

    gateway = Gateway(plugin, POKEMON_SANDBOX)

    def on_step(step, obs, result, events):
        r = getattr(result, "data", {}).get("reward", 0.0)
        flair = f"  reward={r:+.1f}" if r else ""
        print(f"[{step:04d}] map={obs.data['map_id']} ({obs.data['x']},{obs.data['y']}) "
              f"badges={obs.data['badges']} lvls={obs.data['party_level_sum']}{flair}")

    print(f"Agent {agent_id} playing for {args.steps} steps with the {args.brain} brain...\n")
    try:
        summary = run_episode(gateway, plugin, brain, agent_id,
                              max_steps=args.steps, on_step=on_step)
        if args.save_state:
            plugin.save_state(args.save_state)
            print(f"saved final state -> {args.save_state}")
    finally:
        plugin.close()

    print("\n=== episode summary ===")
    for k, v in summary.items():
        print(f"  {k}: {v}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
