"""Re-establish a FULL-HEALTH start inside Castle Lololo's water room, in one call.

Why this exists: the water room is full of Gordos (invincible spikes), so attempts there are only
worth making at high HP -- and the approach is ~1,300 frames of corridor. Dying is the cheapest
full heal in this game (HP back to 6, costs one life), and the respawn checkpoint is early, so the
loop is: die -> respawn -> autopilot -> walk left -> jump the block into the door.

The corridor is NOT deterministic (enemies knock Kirby around), so the final door entry retries
over offsets from a saved checkpoint until the screen-blank room detector fires.

  python route.py W06.state --save water_full
"""
from __future__ import annotations

import argparse
import os

PRIMARY = "E:/AI_Personas/10_pokemon_and_chess_and_office/ai-pokemon-red"
ROM = PRIMARY + "/roms/Kirby's Dream Land (USA, Europe).gb"
OUT = ("C:/Users/Succe/AppData/Local/Temp/claude/"
       "E--AI-Personas-10-pokemon-and-chess-and-office/"
       "671b9313-5a35-40f5-a26e-315d9f7e8f28/scratchpad/kirby3")
CAND = (0xC057, 0xC073, 0xC07B, 0xD03B, 0xD19F, 0xD3A9, 0xD3BA, 0xD3CD)

APPROACH = ([(420, [])]                             # let any death animation + respawn finish
            + [(50, ["right"]), (20, ["right", "a"])] * 8   # autopilot to the corridor's right end
            + [(700, ["left"])])                    # travel to the corridor's left end
DOOR = [(22, ["left", "a"]), (45, ["left"]), (12, []), (35, ["up"]), (60, [])]


def play(pb, steps):
    """Run steps, returning how many screen-blank room changes fired."""
    rooms, was_blank = 0, False
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
        for b in held:
            pb.button_release(b)
    return rooms


def load(path):
    from pyboy import PyBoy
    pb = PyBoy(ROM, window="null", sound_emulated=False)
    pb.set_emulation_speed(0)
    with open(path, "rb") as f:
        pb.load_state(f)
    pb.tick(1, render=True)
    return pb


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("state")
    ap.add_argument("--save", default="water_full")
    args = ap.parse_args()

    src = args.state if os.path.exists(args.state) else os.path.join(OUT, args.state)
    tmp = os.path.join(OUT, "_route_atdoor.state")

    pb = load(src)
    play(pb, APPROACH)
    hp_at_door = pb.memory[0xD086]
    band, col = pb.memory[0xD052], pb.memory[0xD051]
    pb.screen.image.save(os.path.join(OUT, "_route_atdoor.png"))
    with open(tmp, "wb") as f:
        pb.save_state(f)
    pb.stop(save=False)
    print(f"reached corridor left end, hp={hp_at_door} band(D052)={band} col(D051)={col}")

    for offset in range(0, 260, 4):
        pb = load(tmp)
        rooms = play(pb, [(offset, ["left"])] + DOOR)
        if rooms:
            hp = pb.memory[0xD086]
            cand = [pb.memory[a] for a in CAND]
            out_state = os.path.join(OUT, f"{args.save}.state")
            pb.screen.image.save(os.path.join(OUT, f"{args.save}.png"))
            with open(out_state, "wb") as f:
                pb.save_state(f)
            lives = pb.memory[0xD089]
            pb.stop(save=False)
            print(f"lives={lives}")
            print(f"ENTERED water room at offset {offset}: hp={hp} cand={cand}")
            print(f"saved {out_state}")
            return 0
        pb.stop(save=False)

    print("FAILED to find the door this pass -- rerun (corridor is not deterministic)")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
