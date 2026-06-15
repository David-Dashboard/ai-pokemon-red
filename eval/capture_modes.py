"""Capture REAL mode frames and grade detect_mode() against ground truth.

Iteration-01..03 left battle/dialog as *structural priors* in detect_mode() — we never had real
battle/dialog frames (the autopilot is gated behind getting the starter; see LEARNINGS). This
driver scripts the opening so we DO reach them, then scores the detector:

    bedroom(38) -> house 1F(37) -> Pallet Town(0) -> Oak cutscene -> Oak's Lab(40)
                -> pick Charmander (A on a ball, A=yes, B=no-nickname) -> RIVAL BATTLE (in_battle!=0)

Navigation is a seeded random walk with a light per-map directional bias plus periodic A/B presses
(A advances dialog / confirms; B answers "give a nickname?" with NO so we don't get stuck at the
naming keyboard). RAM (map_id, x, y, in_battle, party_count) is used ONLY to navigate robustly and
to SCORE perception — the oracle role, never fed to a perceiver.

What's auto-graded from RAM ground truth:
  * OVERWORLD: a frame right after the player's tile changed (same map, not in battle) -> truth overworld.
  * BATTLE:    settled frames while in_battle != 0 (skipping the 1-frame fade-to-black at battle start).
The headline metric is OVERWORLD vs NON-OVERWORLD (what drives HybridBrain's wake decision); the exact
non-overworld sub-label (battle/menu/dialog) is secondary. Dialog/menu frames are saved for eyeballing.

Run: uv run python -m eval.capture_modes
"""
from __future__ import annotations

import glob
import json
import os
import random
import sys

from pyboy import PyBoy

from games.pokemon_red.memory_map import (ADDR_IS_IN_BATTLE, ADDR_MAP_ID, ADDR_PARTY_COUNT,
                                          ADDR_X, ADDR_Y)
from games.pokemon_red.perceiver import detect_mode

ROM = sys.argv[1] if len(sys.argv) > 1 else "roms/PokemonRed.gb"
STATE = sys.argv[2] if len(sys.argv) > 2 else "start.state"
OUT = "runs/modes"

BIAS = {38: ["up", "right"], 37: ["down"], 0: ["up"], 40: ["up"]}


def main() -> int:
    os.makedirs(OUT, exist_ok=True)
    for f in glob.glob(os.path.join(OUT, "*.png")):  # fresh run, no stale frames
        os.remove(f)
    pb = PyBoy(ROM, window="null")
    M = pb.memory
    with open(STATE, "rb") as f:
        pb.load_state(f)
    pb.tick(4, render=True)
    rng = random.Random(1)

    log: list[dict] = []
    n = {"i": 0}

    def ram():
        return {"map": M[ADDR_MAP_ID], "x": M[ADDR_X], "y": M[ADDR_Y],
                "in_battle": M[ADDR_IS_IN_BATTLE], "party": M[ADDR_PARTY_COUNT]}

    def capture(truth: str, save: bool):
        n["i"] += 1
        mode = detect_mode(pb.screen.ndarray)
        rec = {"i": n["i"], "truth": truth, "detected": mode, **ram()}
        if save:
            path = os.path.join(OUT, f"{n['i']:03d}_{truth}_{mode}.png")
            pb.screen.image.save(path)
            rec["path"] = path
        log.append(rec)
        return rec

    def press(b: str, hold: int = 8, settle: int = 16):
        pb.button(b, delay=hold)
        pb.tick(hold + settle, render=True)

    # --- drive to the rival battle, sampling ground-truthed frames on the way ---
    for step in range(1500):
        r = ram()
        if r["in_battle"]:
            break
        if rng.random() < 0.40:
            press("a" if rng.random() < 0.5 else "b")
            capture("ui_candidate", save=True)        # dialog/menu candidates (eyeball these)
        else:
            d = rng.choice(BIAS.get(r["map"], []) + ["up", "down", "left", "right"])
            press(d); press(d)
            after = ram()
            if (after["x"], after["y"]) != (r["x"], r["y"]) and after["map"] == r["map"]:
                if step % 3 == 0:
                    capture("overworld", save=False)  # RAM-confirmed moving overworld

    reached = bool(ram()["in_battle"])
    if reached:
        press("a")                                     # step past the 1-frame fade-to-black
        for _ in range(8):                             # settled battle frames (our whole point)
            capture("battle", save=True)
            press("a")
    print("reached_battle:", reached, " final RAM:", ram())

    with open(os.path.join(OUT, "modes_log.jsonl"), "w", encoding="utf-8") as f:
        for r in log:
            f.write(json.dumps(r) + "\n")

    # --- scorecard ---
    def rate(rows, pred):
        hit = sum(1 for r in rows if pred(r))
        return hit, len(rows)

    ow = [r for r in log if r["truth"] == "overworld"]
    ba = [r for r in log if r["truth"] == "battle"]
    print(f"\n=== detect_mode on REAL pixels ({len(log)} frames) ===")
    h, t = rate(ow, lambda r: r["detected"] == "overworld")
    print(f"OVERWORLD (truth: tile moved)   detect==overworld : {h}/{t}")
    h, t = rate(ba, lambda r: r["detected"] == "battle")
    print(f"BATTLE    (truth: in_battle!=0) detect==battle     : {h}/{t}")
    # headline: overworld vs non-overworld on every RAM-groundable frame
    grp = ow + ba
    h, t = rate(grp, lambda r: (r["detected"] == "overworld") == (r["truth"] == "overworld"))
    print(f"HEADLINE  overworld-vs-NONoverworld correctness   : {h}/{t}")
    dist: dict = {}
    for r in log:
        dist[r["detected"]] = dist.get(r["detected"], 0) + 1
    print("detect_mode label distribution (all frames):", dist)
    saved = [r for r in log if r.get("path") and r["detected"] != "overworld"]
    print(f"\n{len(saved)} saved non-overworld frames (dialog/menu/battle candidates) in {OUT}/")
    pb.stop(save=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
