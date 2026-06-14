"""Iteratively play Pokémon Red toward the Elite Four.

Runs the agent in chunks, persisting the emulator state between chunks so progress accumulates
across runs (and survives a crash). Resumes from --state if it exists, else --seed-state. Logs
badges / maps / party level each chunk; stops at --max-steps or all 8 badges.

The whole game is tens of thousands of steps, so one launch won't finish it — this just keeps
making (and saving) progress. Relaunch any time to continue from progress.state.

    ARIA_BEARER_TOKEN=... uv run python play_loop.py --rom roms/PokemonRed.gb
"""
from __future__ import annotations

import argparse
import os
import uuid

from core.brains import LLMButtonBrain
from core.gateway import Gateway
from core.permissions import POKEMON_SANDBOX
from core.runner import run_episode


def main() -> int:
    ap = argparse.ArgumentParser(description="Iteratively play Pokémon Red, persisting progress.")
    ap.add_argument("--rom", required=True)
    ap.add_argument("--state", default="progress.state", help="persistent save (resumed + rewritten each chunk)")
    ap.add_argument("--seed-state", default="start.state", help="initial state if no progress yet")
    ap.add_argument("--chunk", type=int, default=40, help="steps per chunk (saved after each)")
    ap.add_argument("--max-steps", type=int, default=2000, help="total step budget this launch")
    ap.add_argument("--url", default="http://localhost:8001")
    ap.add_argument("--model", default="aria")
    ap.add_argument("--token", default=os.environ.get("ARIA_BEARER_TOKEN"))
    args = ap.parse_args()

    from games.pokemon_red import PokemonRedPlugin
    aid = f"agent-{uuid.uuid4()}"
    init = args.state if os.path.exists(args.state) else args.seed_state
    done = 0
    print(f"[loop] resume={init}  budget={args.max_steps} in chunks of {args.chunk}", flush=True)

    while done < args.max_steps:
        plugin = PokemonRedPlugin(rom_path=args.rom, out_dir="runs/loop", headless=True, init_state=init)
        brain = LLMButtonBrain(aid, model=args.model, url=args.url, backend="aria",
                               api_key=args.token, use_vision=True)
        try:
            summary = run_episode(Gateway(plugin, POKEMON_SANDBOX), plugin, brain, aid, max_steps=args.chunk)
            plugin.save_state(args.state)
        finally:
            plugin.close()
        done += args.chunk
        init = args.state
        fs = summary.get("final_state", {})
        print(f"[loop] +{args.chunk} (total {done}/{args.max_steps})  badges={fs.get('badges')} "
              f"maps_seen={fs.get('maps_seen')} lvl_sum={fs.get('party_level_sum')} "
              f"map={fs.get('map_id')} reward={summary.get('total_reward')}", flush=True)
        if (fs.get("badges") or 0) >= 8:
            print("[loop] all 8 badges — onward to the Elite Four!", flush=True)

    print(f"[loop] budget reached; progress saved to {args.state} — relaunch to continue.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
