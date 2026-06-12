"""Create a start state headlessly by auto-playing past the intro.

Pokémon Red's intro (Oak's speech + name entry) is unskippable, and a
button-mashing agent brain can't clear it. This drives it *headless* — no SDL2
window, so no `pysdl2-dll` (which some antivirus flags). It starts a NEW GAME,
mashes A through Oak's speech, picks the preset names at both name menus
(avoiding the on-screen keyboard), and stops the instant the player can move in
the bedroom — then writes a save state you can boot the agent from:

    python new_game.py --rom "roms/Pokemon Red.gb" --out start.state
    python play_pokemon.py --rom "roms/Pokemon Red.gb" --load-state start.state --brain scripted

Assumes a fresh cartridge (no existing in-game save). Save states embed
copyrighted game memory, so they're gitignored — keep them local.
"""

from __future__ import annotations

import argparse

from games.pokemon_red.memory_map import ADDR_MAP_ID, ADDR_X, ADDR_Y

REDS_HOUSE_2F = 38  # the bedroom you start in


def main() -> int:
    ap = argparse.ArgumentParser(description="Auto-play past the intro; save a start state.")
    ap.add_argument("--rom", required=True, help="path to your Pokémon Red ROM (.gb)")
    ap.add_argument("--out", default="start.state", help="where to write the save state")
    ap.add_argument("--window", action="store_true", help="watch it run (needs SDL2)")
    args = ap.parse_args()

    if args.window:
        from games.pokemon_red.emulator import ensure_sdl_dll_path
        ensure_sdl_dll_path()
    from pyboy import PyBoy

    pyboy = PyBoy(args.rom, window="SDL2" if args.window else "null")

    def press(btn, settle=14, hold=4):
        pyboy.button(btn, delay=hold)
        pyboy.tick(hold + settle, render=True)

    # 1) Start a NEW GAME and advance Oak's speech until the bedroom map loads.
    for _ in range(120):
        press("a")
        if pyboy.memory[ADDR_MAP_ID] == REDS_HOUSE_2F:
            break
    else:
        pyboy.stop(save=False)
        raise SystemExit("Never reached the bedroom map — intro flow unexpected.")

    # 2) Clear both name menus by taking the first preset name: DOWN moves the
    #    cursor off "NEW NAME" onto a preset (and is a harmless no-op inside text
    #    boxes), A confirms. Stop the moment a DOWN actually moves the player —
    #    that is overworld control.
    in_control = False
    for _ in range(250):
        y0 = pyboy.memory[ADDR_Y]
        press("down")
        if pyboy.memory[ADDR_Y] != y0:
            in_control = True
            break
        press("a")

    if not in_control:
        pyboy.stop(save=False)
        raise SystemExit("Reached the bedroom but never gained control — aborting.")

    with open(args.out, "wb") as f:
        pyboy.save_state(f)
    print(f"In control: map {pyboy.memory[ADDR_MAP_ID]} "
          f"at ({pyboy.memory[ADDR_X]},{pyboy.memory[ADDR_Y]}). "
          f"Saved start state -> {args.out}")
    pyboy.stop(save=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
