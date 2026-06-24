"""Run the EXISTING brain on Cave Noire — the constancy test for the FIXED-camera class (the brain/core
is reused UNCHANGED; only the games/cave_noire/ perceiver + config + prompt are new). Same
ExploreBrain / Gateway / run_episode the Pokemon and Gauntlet drivers use, pointed at the Cave Noire
plugin (the shared core.PerceptionPlugin).

  uv run python play_cave_noire.py --rom "roms/Cave Noire (Japan) [T-En by Aeon Genesis v1.00].gb" --steps 150 --brain scripted
"""
from __future__ import annotations

import argparse
import os
import uuid

from core.brains import ExploreBrain, ScriptedBrain
from core.gateway import Gateway
from core.runner import run_episode
from games.cave_noire import CAVE_NOIRE_SANDBOX, CaveNoirePlugin
from games.cave_noire.perceiver import CaveNoirePerceiver


def main() -> int:
    ap = argparse.ArgumentParser(description="Run the existing brain on Cave Noire (constancy test).")
    ap.add_argument("--rom", default="roms/Cave Noire (Japan) [T-En by Aeon Genesis v1.00].gb")
    ap.add_argument("--out", default="runs/cave_noire_constancy")
    ap.add_argument("--steps", type=int, default=150)
    ap.add_argument("--brain", choices=["scripted", "explore"], default="scripted",
                    help="scripted = no-API smoke (mashes through the title, exercises the loop); "
                         "explore = the frontier autopilot that reads the perceiver's occupancy map")
    ap.add_argument("--window", action="store_true", help="show the SDL2 window (default headless)")
    ap.add_argument("--init-state", default=None,
                    help="load a gameplay save-state (skip the title/menu so ExploreBrain can navigate)")
    ap.add_argument("--save-state", default=None,
                    help="write the emulator state at the end (capture a gameplay checkpoint to reuse)")
    ap.add_argument("--seed", type=int, default=0, help="ScriptedBrain seed (vary the warmup landing spot)")
    args = ap.parse_args()

    agent_id = f"agent-{uuid.uuid4()}"
    plugin = CaveNoirePlugin(rom_path=args.rom, out_dir=args.out, headless=not args.window,
                             init_state=args.init_state, perceiver=CaveNoirePerceiver(),
                             watch={"x": 0xC504, "y": 0xC503})   # RAM -> oracle log ONLY (scoring)
    brain = (ScriptedBrain(agent_id, seed=args.seed) if args.brain == "scripted"
             else ExploreBrain(agent_id, single_step=True))   # the SAME core brains; turn-based = one press/move
    gateway = Gateway(plugin, CAVE_NOIRE_SANDBOX)

    def on_step(step, obs, result, events):
        if step % 25 == 0 or step == args.steps - 1:
            d = obs.data
            sm = d.get("spatial_memory") or {}
            la = d.get("last_action") or {}
            print(f"  step {step:3d}  context={d.get('context'):8s}  pose={d.get('pose', {}).get('value')}  "
                  f"visited={sm.get('visited')}  frontiers={len(sm.get('frontiers') or [])}  "
                  f"last={la.get('action')}->{la.get('outcome')}")

    print(f"Cave Noire constancy run: {args.brain} brain, {args.steps} steps -> {args.out}")
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
