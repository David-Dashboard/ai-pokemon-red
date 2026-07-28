"""Chain forward through rooms automatically, stopping the moment the stage candidates change.

After Lololo is beaten the game continues through several rooms before the stage actually ends.
This repeatedly searches for a transition from the current state, takes the first one that leaves
Kirby alive, settles it, and repeats -- so the run can be left unattended.

Stops on: any of the 5 live candidates leaving 1 (the answer EX02 needs), or no transition found.

  python advance.py --start post_boss_final.state --rooms 12
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
CAND = (0xD03B, 0xD19F, 0xD3A9, 0xD3BA, 0xD3CD)
MOVES = (["right"], ["right"], ["right"], ["right", "a"], ["right", "up"], ["up"], ["up"],
         ["a"], ["a", "right"], ["down"], ["b"], ["left"], [], ["right", "b"], ["down", "right"])


def gen(seed, frames):
    rng = random.Random(seed)
    steps, tot = [], 0
    while tot < frames:
        n = rng.choice((8, 12, 16, 24, 36))
        steps.append((n, rng.choice(MOVES)))
        tot += n
    return steps


def run(state, steps, settle=0, save_as=None):
    from pyboy import PyBoy
    pb = PyBoy(ROM, window="null", sound_emulated=False)
    pb.set_emulation_speed(0)
    with open(os.path.join(OUT, state), "rb") as f:
        pb.load_state(f)
    pb.tick(1, render=True)
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
    if settle:
        pb.tick(settle, render=True)
    res = {"rooms": rooms, "died": died, "hp": pb.memory[0xD086], "lives": pb.memory[0xD089],
           "cand": [pb.memory[a] for a in CAND], "d052": pb.memory[0xD052],
           "score": sum(pb.memory[0xD070 + i] * 10 ** (4 - i) for i in range(4))}
    if save_as:
        pb.screen.image.save(os.path.join(OUT, f"{save_as}.png"))
        with open(os.path.join(OUT, f"{save_as}.state"), "wb") as f:
            pb.save_state(f)
    pb.stop(save=False)
    return res


def die_and_respawn(state, save_as):
    """Kill Kirby and wait out the respawn. Refills HP and often relocates him usefully."""
    from pyboy import PyBoy
    pb = PyBoy(ROM, window="null", sound_emulated=False)
    pb.set_emulation_speed(0)
    with open(os.path.join(OUT, state), "rb") as f:
        pb.load_state(f)
    pb.tick(1, render=True)
    t = 0
    while pb.memory[0xD086] > 0 and t < 9000:
        pb.tick(60, render=True)
        t += 60
    if pb.memory[0xD086] > 0:
        pb.stop(save=False)
        return False
    pb.tick(800, render=True)
    with open(os.path.join(OUT, f"{save_as}.state"), "wb") as f:
        pb.save_state(f)
    ok = pb.memory[0xD089] > 0
    pb.stop(save=False)
    return ok


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="post_boss_final.state")
    ap.add_argument("--rooms", type=int, default=12)
    ap.add_argument("--trials", type=int, default=220)
    ap.add_argument("--seed", type=int, default=900000)
    args = ap.parse_args()

    base, seed = args.start, args.seed
    for step in range(args.rooms):
        found = False
        # escalate: short attempts, then long ones, then a deliberate death-and-respawn (which
        # both refills HP and relocates Kirby, and has repeatedly unstuck a stalled room)
        for frames in (1400, 2600, 4000):
            if found:
                break
            for i in range(args.trials):
                r = run(base, gen(seed, frames))
                seed += 1
                if not (r["rooms"] and not r["died"]):
                    continue
                tag = f"adv_{step:02d}"
                r = run(base, gen(seed - 1, frames), settle=500, save_as=tag)
                print(f"room {step}: -> {tag}  score={r['score']} hp={r['hp']} "
                      f"lives={r['lives']} D052={r['d052']} candidates5={r['cand']} f={frames}",
                      flush=True)
                if any(v != 1 for v in r["cand"]):
                    print("\n*** CANDIDATES CHANGED -- this is the Stage-3 sample EX02 needs ***")
                    print(f"    {dict(zip((hex(a) for a in CAND), r['cand']))}")
                    return 0
                base, found = f"{tag}.state", True
                break
        if not found:
            print(f"room {step}: stalled from {base}; trying a death-reset", flush=True)
            reset = f"adv_{step:02d}_r"
            if not die_and_respawn(base, reset):
                print(f"room {step}: no transition and no death-reset -- stopping", flush=True)
                return 1
            base = f"{reset}.state"
    print("room budget exhausted; candidates never left 1")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
