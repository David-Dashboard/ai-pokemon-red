"""Task #8 closed-loop A/B (free, headless, NO LLM): run the ExploreBrain autopilot DRIVING the real
emulator with vs without prediction-skipping, from the same state + same overworld-step budget, and
compare bumps / cells-visited. Unlike eval/probe_navsave (which replays a FIXED recorded trajectory),
this lets the path DIVERGE — so it shows the speedup MATERIALISE and that the fallback prevents
stranding (B must visit >= A's cells). The perceiver builds the tile-map online and surfaces
tile_predictions; ExploreBrain(use_predictions=True) consumes them. RAM is the oracle (no leak).

    uv run python -m eval.closed_loop_ab --state start.state --steps 300
"""
from __future__ import annotations
import argparse
import numpy as np
from core.brains import ExploreBrain
from core.contracts import Observation
from core.perception import PerceptMemory
from games.pokemon_red.memory_map import read_state
from games.pokemon_red.perceiver import OverworldPerceiver


def run(rom, state, steps, use_pred, pred_min_conf=0.0, skip_flat=False):
    from pyboy import PyBoy
    pb = PyBoy(rom, window="null")
    with open(state, "rb") as f:
        pb.load_state(f)
    pb.tick(8, render=True)
    per, mem = OverworldPerceiver(), PerceptMemory()
    ex = ExploreBrain("ab", single_step=True, use_predictions=use_pred,
                      pred_min_conf=pred_min_conf, skip_flat_pred=skip_flat)

    def press(bs):
        for b in bs:
            pb.button(b, delay=8)
            pb.tick(24, render=True)

    last = None
    ow_steps = bumps = stuck = 0
    for _ in range(steps * 4):                       # headroom for dialog advances
        if ow_steps >= steps:
            break
        sym = per.perceive(pb.screen.ndarray, mem, {"last_action": last})
        if sym.context != "overworld":
            press(["a"]); last = "a"; continue       # advance any dialog/menu so both variants progress
        outcome = (sym.last_action or {}).get("outcome")
        if outcome in ("moved", "blocked"):          # a resolved overworld move
            ow_steps += 1
            bumps += (outcome == "blocked")
        call = ex.decide(Observation(data=sym.to_dict(), text="", agent_id="ab", t=0.0), [], {})
        if call is None:
            stuck += 1
            if stuck > 5:
                break                                # truly exhausted everything reachable
            press(["a"]); last = "a"; continue
        stuck = 0
        bs = call.args["buttons"]
        press(bs); last = "+".join(bs)
    cells = sum(sum(1 for c in p.values() if c.get("visited")) for p in mem.data.get("places", {}).values())
    pb.stop(save=False)
    return {"ow_steps": ow_steps, "bumps": bumps, "cells": cells,
            "places": len(mem.data.get("places", {})), "tiles": len(mem.data.get("tilemap", []))}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rom", default="roms/PokemonRed.gb")
    ap.add_argument("--state", default="start.state")
    ap.add_argument("--steps", type=int, default=300)
    args = ap.parse_args()
    variants = [("A baseline (no pred)", dict(use_pred=False)),
                ("B pred (default)", dict(use_pred=True)),
                ("B pred skip_flat", dict(use_pred=True)),                    # skip_flat via kw below
                ("B pred skip_flat+conf0.9", dict(use_pred=True))]
    kwextra = [{}, {}, {"skip_flat": True}, {"skip_flat": True, "min_conf": 0.9}]
    print(f"closed-loop A/B  state={args.state}  budget={args.steps} overworld steps")
    print("(B must visit >= A's cells = no strand; lower bumps = the speedup)\n")
    print(f"{'variant':28} {'steps':>5} {'cells':>6} {'bumps':>6} {'bump-rate':>10} {'places':>7}")
    base = None
    for (name, _), extra in zip(variants, kwextra):
        r = run(args.rom, args.state, args.steps, use_pred=("B" in name),
                pred_min_conf=extra.get("min_conf", 0.0), skip_flat=extra.get("skip_flat", False))
        br = r["bumps"] / r["ow_steps"] if r["ow_steps"] else 0.0
        flag = ""
        if base is None:
            base = r
        else:
            if base["bumps"]:
                flag = f"  {(1 - r['bumps'] / base['bumps']) * 100:.0f}% fewer bumps"
            if r["cells"] < base["cells"] * 0.95:
                flag += f"  !! STRANDED ({r['cells']}<{base['cells']} cells)"
        print(f"{name:28} {r['ow_steps']:>5} {r['cells']:>6} {r['bumps']:>6} {br:>9.1%} {r['places']:>7}{flag}")


if __name__ == "__main__":
    main()
