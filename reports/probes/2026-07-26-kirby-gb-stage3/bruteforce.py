"""Randomised action search from a savestate, scored by the room-change detector.

Reading room geometry off 160x144 screenshots stopped paying: several hand-planned routes through
Castle Lololo's water room all failed for reasons that were not visible in a still frame. This
throws many varied button sequences at the same savestate instead and keeps whatever produces a
room change or new forward progress. Savestate-chained, so trials are independent.

Deterministic: trial i is generated from `seed + i`, so any hit can be replayed exactly.

  python bruteforce.py X02.state --trials 200 --frames 600
"""
from __future__ import annotations

import argparse
import os
import random

PRIMARY = "E:/AI_Personas/10_pokemon_and_chess_and_office/ai-pokemon-red"
ROM = PRIMARY + "/roms/Kirby's Dream Land (USA, Europe).gb"
OUT = ("C:/Users/Succe/AppData/Local/Temp/claude/"
       "E--AI-Personas-10-pokemon-and-chess-and-office/"
       "671b9313-5a35-40f5-a26e-315d9f7e8f28/scratchpad/kirby3")
CAND = (0xC057, 0xC073, 0xC07B, 0xD03B, 0xD19F, 0xD3A9, 0xD3BA, 0xD3CD)

# Weighted toward "rightward and vertical", which is where progress lies, but with enough
# variety (inhale, jump, idle) to stumble through things a planned route missed.
MOVES = (
    ["right"], ["right"], ["right"], ["right", "a"], ["right", "up"], ["right", "down"],
    ["up"], ["up"], ["down"], ["down"], ["a"], ["a", "right"], ["b"], ["left"], [],
    ["up", "left"], ["down", "right"], ["right", "b"],
)


def gen(seed, frames):
    rng = random.Random(seed)
    steps, total = [], 0
    while total < frames:
        n = rng.choice((8, 12, 16, 20, 30, 45))
        steps.append((n, rng.choice(MOVES)))
        total += n
    return steps


def trial(state_path, steps, save_as=None):
    from pyboy import PyBoy
    pb = PyBoy(ROM, window="null", sound_emulated=False)
    pb.set_emulation_speed(0)
    with open(state_path, "rb") as f:
        pb.load_state(f)
    pb.tick(1, render=True)

    rooms, was_blank, died = 0, False, False
    xmax = pb.memory[0xD051]
    for frames, held in steps:
        for b in held:
            pb.button_press(b)
        left = frames
        while left > 0:
            chunk = min(4, left)
            pb.tick(chunk, render=True)
            left -= chunk
            px = pb.screen.ndarray[:, :, 0]
            blank = bool((px == px[0, 0]).mean() > 0.98)
            if blank and not was_blank:
                rooms += 1
            was_blank = blank
            if pb.memory[0xD086] == 0:
                died = True
            xmax = max(xmax, pb.memory[0xD051])
        for b in held:
            pb.button_release(b)
        if died or rooms:
            break

    # NOTE: an earlier version of this file treated a missing HUD score row as evidence the search
    # had corrupted the game, and gated hits on it. That was WRONG -- the post-warp-star area just
    # draws a different, legitimate HUD row. The measurement is kept for information only and no
    # longer gates anything. Do not reintroduce it as a filter without re-deriving it.
    pb.tick(180, render=True)
    hud_dark = int((pb.screen.ndarray[128:136, 0:96, 0] < 128).sum())

    res = {"rooms": rooms, "xmax": xmax, "died": died, "hud": hud_dark, "valid": True,
           "hp": pb.memory[0xD086], "lives": pb.memory[0xD089],
           "cand": [pb.memory[a] for a in CAND]}
    if save_as:
        pb.screen.image.save(os.path.join(OUT, f"{save_as}.png"))
        with open(os.path.join(OUT, f"{save_as}.state"), "wb") as f:
            pb.save_state(f)
    pb.stop(save=False)
    return res


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("state")
    ap.add_argument("--trials", type=int, default=200)
    ap.add_argument("--frames", type=int, default=600)
    ap.add_argument("--seed", type=int, default=1000)
    ap.add_argument("--tag", default="bf")
    args = ap.parse_args()

    state = args.state if os.path.exists(args.state) else os.path.join(OUT, args.state)
    base = trial(state, [(4, [])])
    print(f"baseline x={base['xmax']} hp={base['hp']} lives={base['lives']}")

    best_x, hits = base["xmax"], []
    for i in range(args.trials):
        seed = args.seed + i
        res = trial(state, gen(seed, args.frames))
        interesting = res["rooms"] > 0 or res["xmax"] > best_x
        if interesting and not res["died"]:
            tag = f"{args.tag}_{seed}"
            trial(state, gen(seed, args.frames), save_as=tag)   # replay to save it
            note = "ROOM CHANGE" if res["rooms"] else f"new max x={res['xmax']}"
            print(f"seed {seed}: {note}  hp={res['hp']} lives={res['lives']} "
                  f"hud={res['hud']} cand={res['cand']} -> {tag}")
            hits.append((seed, res))
            best_x = max(best_x, res["xmax"])
    print(f"\n{len(hits)} interesting trial(s) out of {args.trials}; best x={best_x}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
