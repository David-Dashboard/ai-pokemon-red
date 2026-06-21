"""One headless auto-exploration "racer" — a FREE dumb auto-player (no LLM, no aria).

Overworld = the frontier autopilot (ExploreBrain, single-step + wall-probing) with a little seeded
exploration noise so different seeds diverge; dialog/menu/battle = mash A (advance/confirm/first move)
with occasional B/direction. It can't win gym trainers or pick the starter cleverly, but it wanders,
blows through forced dialog, and spams the first move in wild battles — enough to "race" for furthest
progress AND to generate auto-labelled tile data. Records the probe-compatible oracle + frames.

RAM is the non-leaking oracle (side-log only); the perceiver sees pixels. Run several with different
--seed/--name to race; eval/index_runs.py then scores maps-seen / battle / badges per run.

    uv run python -m eval.auto_race --name race1 --seed 1 --steps 4000
"""
from __future__ import annotations

import argparse
import json
import os
import random
import time

from core.brains import ExploreBrain
from core.contracts import Observation
from core.perception import PerceptMemory
from games.pokemon_red.memory_map import read_state
from games.pokemon_red.perceiver import OverworldPerceiver

DIRS = ["up", "down", "left", "right"]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rom", default="roms/PokemonRed.gb")
    ap.add_argument("--load-state", default="start.state")
    ap.add_argument("--name", required=True)
    ap.add_argument("--steps", type=int, default=4000)
    ap.add_argument("--seed", type=int, default=1)
    args = ap.parse_args()

    out = os.path.join("runs", args.name)
    os.makedirs(out, exist_ok=True)
    rng = random.Random(args.seed)

    from pyboy import PyBoy
    pb = PyBoy(args.rom, window="null")
    if os.path.exists(args.load_state):
        with open(args.load_state, "rb") as f:
            pb.load_state(f)
    pb.tick(8, render=True)
    rd = lambda a: pb.memory[a]

    per = OverworldPerceiver()
    mem = PerceptMemory()
    ex = ExploreBrain(f"race{args.seed}", single_step=True, probe_interactables=True)
    oracle = open(os.path.join(out, "oracle.jsonl"), "w", encoding="utf-8")

    def press(b):
        pb.button(b, delay=8)
        pb.tick(24, render=True)

    last_act = None
    maps: set = set()
    for step in range(args.steps):
        frame = pb.screen.ndarray
        st = read_state(rd)
        maps.add(st["map_id"])
        sym = per.perceive(frame, mem, {"last_action": last_act})
        path = os.path.join(out, f"frame_{step:06d}.png")
        pb.screen.image.save(path)
        la, sm = sym.last_action or {}, sym.spatial_memory or {}
        oracle.write(json.dumps({
            "step": step, "t": time.time(), "frame": pb.frame_count,
            "screen_path": path.replace("\\", "/"), "mode": "auto",
            "map_id": st["map_id"], "x": st["x"], "y": st["y"],
            "in_battle": st["in_battle"], "badges": st["badges"],
            "perceived": {"outcome": la.get("outcome"), "action": la.get("action"),
                          "context": sym.context, "pose": (sym.pose or {}).get("value"),
                          "area": (sym.pose or {}).get("area"),
                          "tile_types_seen": sm.get("tile_types_seen")},
        }) + "\n")

        if sym.context == "overworld":
            if rng.random() < 0.12:                       # exploration noise -> seeds diverge
                bs = [rng.choice(DIRS)]
            else:
                call = ex.decide(Observation(data=sym.to_dict(), text="", agent_id="race", t=time.time()), [], {})
                bs = (call.args.get("buttons") if call else None) or [rng.choice(DIRS)]
        else:                                             # dialog/menu/battle: mostly mash A
            bs = ["a"] if rng.random() < 0.7 else [rng.choice(["a", "b"] + DIRS)]
        for b in bs:
            press(b)
        last_act = "+".join(bs)

        if step % 250 == 0:
            oracle.flush()
            print(f"[{args.name}] step {step:4d}  map {st['map_id']:>3}  maps {sorted(maps)}  "
                  f"battle {st['in_battle']}  badges {st['badges']}  tiles {len(mem.data.get('tilemap', []))}",
                  flush=True)

    oracle.close()
    print(f"[{args.name}] DONE {args.steps} steps  maps={sorted(maps)}  badges={st['badges']}  "
          f"tile-types={len(mem.data.get('tilemap', []))}", flush=True)
    pb.stop(save=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
