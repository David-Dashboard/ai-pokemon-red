"""Walk to a door found by doorscan.py and enter it. Turns door entry from a search into a move.

Kirby walks ~1px/frame, so the approach is just |dx| frames toward the door, then `up`. A small
spread of walk lengths is tried around the ideal because enemies knock Kirby around; the first one
that produces a screen-blank room change wins.

  python enter.py u01.state --door 0 --save next
"""
from __future__ import annotations

import argparse
import os

from doorscan import scan

PRIMARY = "E:/AI_Personas/10_pokemon_and_chess_and_office/ai-pokemon-red"
ROM = PRIMARY + "/roms/Kirby's Dream Land (USA, Europe).gb"
OUT = ("C:/Users/Succe/AppData/Local/Temp/claude/"
       "E--AI-Personas-10-pokemon-and-chess-and-office/"
       "671b9313-5a35-40f5-a26e-315d9f7e8f28/scratchpad/kirby3")
CAND = (0xD03B, 0xD19F, 0xD3A9, 0xD3BA, 0xD3CD)   # the 5 live candidates (C-trio eliminated)


def attempt(state_path, direction, frames, save_as=None, drop=0):
    from pyboy import PyBoy
    pb = PyBoy(ROM, window="null", sound_emulated=False)
    pb.set_emulation_speed(0)
    with open(state_path, "rb") as f:
        pb.load_state(f)
    pb.tick(1, render=True)

    rooms, was_blank = 0, False

    def play(n, held):
        nonlocal rooms, was_blank
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
        for b in held:
            pb.button_release(b)

    if drop:
        play(drop, ["down"])
    if frames:
        play(frames, [direction])
    play(14, [])
    play(35, ["up"])
    play(70, [])

    res = {"rooms": rooms, "hp": pb.memory[0xD086], "lives": pb.memory[0xD089],
           "cand": [pb.memory[a] for a in CAND],
           "score": sum(pb.memory[0xD070 + i] * 10 ** (4 - i) for i in range(4))}
    if save_as:
        pb.screen.image.save(os.path.join(OUT, f"{save_as}.png"))
        with open(os.path.join(OUT, f"{save_as}.state"), "wb") as f:
            pb.save_state(f)
    pb.stop(save=False)
    return res


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("state")
    ap.add_argument("--door", type=int, default=0)
    ap.add_argument("--save", default="entered")
    ap.add_argument("--drop", type=int, default=0, help="hold down this many frames first")
    args = ap.parse_args()

    path = args.state if os.path.exists(args.state) else os.path.join(OUT, args.state)
    doors, (kx, ky), info = scan(path)
    if not doors:
        print("no doors found by the castle-interior signature")
        return 1
    if args.door >= len(doors):
        print(f"only {len(doors)} door(s) found")
        return 1

    r, c = doors[args.door]
    px = c * 8 + 8
    dx = px - kx
    direction = "right" if dx > 0 else "left"
    ideal = int(abs(dx))
    print(f"door {args.door} at tile(r{r},c{c}) screen x~{px}; kirby at {kx:.0f} -> "
          f"walk {direction} ~{ideal}px")

    for frames in sorted({max(0, ideal + d) for d in (0, -6, 6, -12, 12, -20, 20, -30, 30)}):
        res = attempt(path, direction, frames, drop=args.drop)
        if res["rooms"]:
            res = attempt(path, direction, frames, save_as=args.save, drop=args.drop)
            print(f"ENTERED with walk={frames}: score={res['score']} hp={res['hp']} "
                  f"lives={res['lives']} candidates(5)={res['cand']}")
            print(f"saved {os.path.join(OUT, args.save + '.state')}")
            return 0
    print("no transition at any tested walk length")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
