"""Iteratively play Pokémon Red toward the Elite Four, persisting progress.

One continuous session: checkpoints the emulator state every --chunk steps (so progress survives a
crash and resumes across launches) and logs badges / maps / party level from the RAM oracle (for the
log only — never fed to the agent). With --perception the LLM plans over the SymbolicState (odometry +
occupancy map) that proved it can actually leave rooms, instead of raw pixels alone.

The whole game is tens of thousands of steps, so one launch won't finish it — relaunch to continue.

    ARIA_BEARER_TOKEN=... uv run python play_loop.py --rom roms/PokemonRed.gb --perception
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
    ap.add_argument("--state", default="progress.state", help="checkpoint (resumed + rewritten)")
    ap.add_argument("--seed-state", default="start.state", help="initial state if no progress yet")
    ap.add_argument("--chunk", type=int, default=40, help="checkpoint + log every N steps")
    ap.add_argument("--max-steps", type=int, default=2000, help="total step budget this launch")
    ap.add_argument("--perception", action="store_true", help="plan over the SymbolicState (recommended)")
    ap.add_argument("--url", default="http://localhost:8001")
    ap.add_argument("--model", default="aria")
    ap.add_argument("--token", default=os.environ.get("ARIA_BEARER_TOKEN"))
    args = ap.parse_args()

    from games.pokemon_red import PokemonRedPlugin
    from games.pokemon_red.memory_map import read_state

    perceiver = None
    if args.perception:
        from games.pokemon_red.perceiver import OverworldPerceiver
        perceiver = OverworldPerceiver()

    aid = f"agent-{uuid.uuid4()}"
    init = args.state if os.path.exists(args.state) else args.seed_state
    print(f"[loop] resume={init}  budget={args.max_steps}  checkpoint every {args.chunk}  "
          f"perception={args.perception}", flush=True)

    plugin = PokemonRedPlugin(rom_path=args.rom, out_dir="runs/loop", headless=True,
                              init_state=init, perceiver=perceiver)
    brain = LLMButtonBrain(aid, model=args.model, url=args.url, backend="aria",
                           api_key=args.token, use_vision=True)

    def on_step(step, obs, result, events):
        if (step + 1) % args.chunk == 0:
            plugin.save_state(args.state)
            st = read_state(plugin.emu.read)  # ORACLE: progress telemetry for the log, never the agent
            print(f"[loop] step {step + 1}/{args.max_steps}  badges={st['badges']} "
                  f"maps_seen={plugin._reward.maps_seen} lvl_sum={st['party_level_sum']} "
                  f"map={st['map_id']} party={st['party_count']}", flush=True)
            if st["badges"] >= 8:
                print("[loop] all 8 badges — onward to the Elite Four!", flush=True)

    try:
        run_episode(Gateway(plugin, POKEMON_SANDBOX), plugin, brain, aid,
                    max_steps=args.max_steps, on_step=on_step)
        plugin.save_state(args.state)
    finally:
        plugin.close()
    print(f"[loop] budget reached; progress saved to {args.state} — relaunch to continue.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
