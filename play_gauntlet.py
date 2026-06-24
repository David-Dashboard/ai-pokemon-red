"""Run the EXISTING brain on Gauntlet II — the constancy test (the brain/core is reused UNCHANGED; only
the games/gauntlet/ perceiver + plugin + prompt are new). Smallest thing that works: the same
ExploreBrain / Gateway / run_episode the Pokemon driver uses, pointed at the Gauntlet plugin.

  uv run python play_gauntlet.py --rom "roms/Gauntlet II (USA, Europe).gb" --steps 150 --brain scripted
"""
from __future__ import annotations

import argparse
import os
import uuid

from core.brains import ExploreBrain, ScriptedBrain
from core.gateway import Gateway
from core.runner import run_episode
from games.gauntlet import GAUNTLET_SANDBOX, GauntletPlugin
from games.gauntlet.perceiver import GauntletPerceiver


def main() -> int:
    ap = argparse.ArgumentParser(description="Run the existing brain on Gauntlet II (constancy test).")
    ap.add_argument("--rom", default="roms/Gauntlet II (USA, Europe).gb")
    ap.add_argument("--out", default="runs/gauntlet_constancy")
    ap.add_argument("--steps", type=int, default=150)
    ap.add_argument("--brain", choices=["scripted", "explore"], default="scripted",
                    help="scripted = no-API smoke (mashes through the title, exercises the loop); "
                         "explore = the frontier autopilot that reads the perceiver's occupancy map")
    ap.add_argument("--window", action="store_true", help="show the SDL2 window (default headless)")
    ap.add_argument("--init-state", default=None,
                    help="load a gameplay save-state (skip the title/hero-select so ExploreBrain can navigate)")
    ap.add_argument("--save-state", default=None,
                    help="write the emulator state at the end (capture a gameplay checkpoint to reuse)")
    ap.add_argument("--seed", type=int, default=0, help="ScriptedBrain seed (vary the warmup landing spot)")
    args = ap.parse_args()

    agent_id = f"agent-{uuid.uuid4()}"
    plugin = GauntletPlugin(rom_path=args.rom, out_dir=args.out, headless=not args.window,
                            init_state=args.init_state, perceiver=GauntletPerceiver(),
                            watch={"x": 0xC286, "y": 0xC2C6})   # RAM -> oracle log ONLY (scoring)
    brain = (ScriptedBrain(agent_id, seed=args.seed) if args.brain == "scripted"
             else ExploreBrain(agent_id, single_step=True))   # the SAME core brains as Pokemon
    gateway = Gateway(plugin, GAUNTLET_SANDBOX)

    def on_step(step, obs, result, events):
        if step % 25 == 0 or step == args.steps - 1:
            d = obs.data
            sm = d.get("spatial_memory") or {}
            la = d.get("last_action") or {}
            print(f"  step {step:3d}  context={d.get('context'):8s}  pose={d.get('pose', {}).get('value')}  "
                  f"visited={sm.get('visited')}  frontiers={len(sm.get('frontiers') or [])}  "
                  f"last={la.get('action')}->{la.get('outcome')}")

    print(f"Gauntlet constancy run: {args.brain} brain, {args.steps} steps -> {args.out}")
    try:
        summary = run_episode(gateway, plugin, brain, agent_id, max_steps=args.steps, on_step=on_step)
        if args.save_state:
            os.makedirs(os.path.dirname(args.save_state) or ".", exist_ok=True)
            plugin.save_state(args.save_state)
            print(f"saved state -> {args.save_state}")
    finally:
        plugin.close()
    print(f"\nDone. calls={summary['steps']}  events={summary['event_counts']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
