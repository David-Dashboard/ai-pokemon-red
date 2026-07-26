"""Find which spot in a room actually triggers a transition, instead of guessing at screenshots.

For each horizontal offset, reload the SAME state, walk that far, then try an exit action; report
where the room id / position collapses (a transition). Savestate-chained so every trial is
independent -- no drift between trials. $0, offline PyBoy, no LLM.

  python doorsweep.py r15.state --dir left --max 320 --step 20
"""
from __future__ import annotations

import argparse
import os

PRIMARY = "E:/AI_Personas/10_pokemon_and_chess_and_office/ai-pokemon-red"
ROM = PRIMARY + "/roms/Kirby's Dream Land (USA, Europe).gb"
OUT = ("C:/Users/Succe/AppData/Local/Temp/claude/"
       "E--AI-Personas-10-pokemon-and-chess-and-office/"
       "671b9313-5a35-40f5-a26e-315d9f7e8f28/scratchpad/kirby3")
X_LO, X_HI = 0xD051, 0xD052
CAND = (0xC057, 0xC073, 0xC07B, 0xD03B, 0xD19F, 0xD3A9, 0xD3BA, 0xD3CD)

# Exit actions worth trying at each spot: plain door entry, and floating up through a ceiling gap.
ACTIONS = {
    "up": [(35, ["up"]), (60, [])],
    "float_up": [(10, ["a"]), (6, []), (10, ["a"]), (6, []), (40, ["up"]), (60, [])],
    "down": [(35, ["down"]), (60, [])],
    # The corridor door sits BEYOND a `?` block, so plain walking never reaches it -- the only
    # sequence that ever worked jumps the block first. Sweeping without this finds nothing.
    "hop_left_up": [(22, ["left", "a"]), (45, ["left"]), (12, []), (35, ["up"]), (60, [])],
    "hop_right_up": [(22, ["right", "a"]), (45, ["right"]), (12, []), (35, ["up"]), (60, [])],
}


def run(state_path, walk_dir, walk_frames, action, save_as=None):
    from pyboy import PyBoy
    pb = PyBoy(ROM, window="null", sound_emulated=False)
    pb.set_emulation_speed(0)
    with open(state_path, "rb") as f:
        pb.load_state(f)
    pb.tick(1, render=False)

    def x():
        return (pb.memory[X_HI] << 8) | pb.memory[X_LO]

    x0 = x()
    if walk_frames:
        pb.button_press(walk_dir)
        pb.tick(walk_frames, render=False)
        pb.button_release(walk_dir)
    x_walked = x()
    rooms, was_blank = 0, False
    for frames, held in ACTIONS[action]:
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
    pb.tick(1, render=True)
    x1 = x()
    cand = [pb.memory[a] for a in CAND]
    hp = pb.memory[0xD086]
    if save_as:
        pb.screen.image.save(os.path.join(OUT, f"{save_as}.png"))
        with open(os.path.join(OUT, f"{save_as}.state"), "wb") as f:
            pb.save_state(f)
    pb.stop(save=False)
    return x0, x_walked, x1, hp, cand, rooms


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("state")
    ap.add_argument("--dir", default="left", choices=["left", "right"])
    ap.add_argument("--max", type=int, default=320)
    ap.add_argument("--step", type=int, default=20)
    ap.add_argument("--actions", default="up,float_up")
    ap.add_argument("--save-hits", action="store_true", help="save state/png for each transition")
    args = ap.parse_args()

    state = args.state if os.path.exists(args.state) else os.path.join(OUT, args.state)
    actions = [a.strip() for a in args.actions.split(",") if a.strip()]

    hits = []
    for action in actions:
        for walk in range(0, args.max + 1, args.step):
            tag = f"sweep_{action}_{walk:03d}"
            x0, xw, x1, hp, cand, rooms = run(state, args.dir, walk, action,
                                              save_as=tag if args.save_hits else None)
            flag = f"  <== {rooms} ROOM CHANGE(S)" if rooms else ""
            print(f"{action:9s} walk={walk:3d} x {x0} -> {xw} -> {x1}  hp={hp} "
                  f"cand={cand[0]}{flag}")
            if rooms:
                hits.append((action, walk, x1, cand))
    print()
    if hits:
        for action, walk, x1, cand in hits:
            print(f"HIT {action} walk={walk} -> x={x1} candidates={cand}")
    else:
        print("no transition found in this sweep")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
