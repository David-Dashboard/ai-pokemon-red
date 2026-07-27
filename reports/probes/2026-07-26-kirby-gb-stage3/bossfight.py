"""Fight Lololo (Castle Lololo's boss). Winning it ends Stage 2 and produces the Stage-3 sample
EX02 needs. $0, offline PyBoy, no LLM.

Uniform random input does not win this (300 trials, 0 wins): the fight has a specific shape --
Lololo pushes a block along a ledge, Kirby must be on that ledge, face the block, HOLD b to inhale
it, then TAP b to spit it back. So each trial here is a sequence of structured cycles
(reposition -> settle -> inhale -> spit) with randomised parameters, rather than random buttons.

Reward: a room change (the stage ends when the boss dies) is the win; score gain is the shaping
signal for landing hits.

  python bossfight.py --trials 300 --cycles 12
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
START = "boss_ready.state"
CAND = (0xD03B, 0xD19F, 0xD3A9, 0xD3BA, 0xD3CD)


def cycles(seed, n):
    """One trial: n rounds of reposition -> settle -> inhale -> spit."""
    rng = random.Random(seed)
    steps = []
    for _ in range(n):
        move = rng.choice(["left", "right", None])
        if move:
            steps.append((rng.choice((10, 20, 30, 45, 60)), [move]))
        for _ in range(rng.choice((0, 0, 1, 2, 3))):        # climb to a ledge
            steps.append((9, ["a"]))
            steps.append((7, []))
        face = rng.choice(["left", "right"])
        steps.append((6, [face]))                            # face the incoming block
        steps.append((rng.choice((8, 14, 20)), []))          # let it come
        steps.append((rng.choice((30, 45, 60, 80)), ["b"]))  # inhale (hold)
        steps.append((rng.choice((6, 12, 20)), []))
        opp = "right" if face == "left" else "left"
        steps.append((6, [rng.choice([face, opp])]))         # turn toward Lololo
        steps.append((8, ["b"]))                             # spit
        steps.append((rng.choice((10, 20)), []))
    return steps


def trial(steps, save_as=None):
    from pyboy import PyBoy
    pb = PyBoy(ROM, window="null", sound_emulated=False)
    pb.set_emulation_speed(0)
    with open(os.path.join(OUT, START), "rb") as f:
        pb.load_state(f)
    pb.tick(1, render=True)

    score0 = sum(pb.memory[0xD070 + i] * 10 ** (4 - i) for i in range(4))
    rooms, was_blank, died = 0, False, False
    for n, held in steps:
        for b in held:
            pb.button_press(b)
        left = n
        while left > 0:
            c = min(4, left)
            pb.tick(c, render=True)
            left -= c
            px = pb.screen.ndarray[:, :, 0]
            blank = bool((px == px[0, 0]).mean() > 0.98)
            if blank and not was_blank:
                rooms += 1
            was_blank = blank
            if pb.memory[0xD086] == 0:
                died = True
        for b in held:
            pb.button_release(b)
        if died or rooms:
            break

    if rooms:                       # let the next screen settle so candidates are readable
        for _ in range(60):
            pb.tick(4, render=True)
    score = sum(pb.memory[0xD070 + i] * 10 ** (4 - i) for i in range(4))
    res = {"rooms": rooms, "died": died, "gain": score - score0, "score": score,
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
    ap.add_argument("--trials", type=int, default=300)
    ap.add_argument("--cycles", type=int, default=12)
    ap.add_argument("--seed", type=int, default=100000)
    args = ap.parse_args()

    best = 0
    for i in range(args.trials):
        s = args.seed + i
        r = trial(cycles(s, args.cycles))
        if r["rooms"]:
            r = trial(cycles(s, args.cycles), save_as=f"WIN_{s}")
            print(f"*** seed {s}: ROOM CHANGE score={r['score']} gain={r['gain']} "
                  f"hp={r['hp']} lives={r['lives']} candidates5={r['cand']} -> WIN_{s}")
            return 0
        if r["gain"] > best:
            best = r["gain"]
            print(f"seed {s}: score gain {best} (died={r['died']} hp={r['hp']})")
    print(f"no win in {args.trials} trials; best score gain {best}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
