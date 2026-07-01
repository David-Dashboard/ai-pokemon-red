"""Create a starting save state by playing the game yourself.

Pokémon Red's intro (Oak's speech + name entry) is unskippable and a
button-mashing brain can't reliably clear it. Standard practice for agent/RL
setups: play past it once, save a state, then boot the agent from there:

    python human_play.py --rom "roms/Pokemon Red.gb" --out start.state
    python world_mcp.py --game pokemon_red --init-state start.state --out runs/mcp_world

A window opens — play with your keyboard (PyBoy's default Game Boy bindings:
arrow keys = d-pad, A = the 'a' key, B = the 's' key, Start = Enter). When you've
reached the point you want the agent to start from (e.g. standing in the bedroom,
or after getting your starter), close the window or press Ctrl-C; the state is
written to --out.

Save states are gitignored (they embed copyrighted game memory) — keep them local.
"""

from __future__ import annotations

import argparse


def main() -> int:
    ap = argparse.ArgumentParser(description="Play Pokémon Red yourself and save a start state.")
    ap.add_argument("--rom", required=True, help="path to your Pokémon Red ROM (.gb)")
    ap.add_argument("--out", default="start.state", help="where to write the save state")
    args = ap.parse_args()

    from games.pokemon_red.emulator import ensure_sdl_dll_path
    ensure_sdl_dll_path()
    from pyboy import PyBoy

    pyboy = PyBoy(args.rom, window="SDL2")
    print("Play to your desired start point, then close the window (or Ctrl-C) to save...")
    try:
        while pyboy.tick(1, True):
            pass
    except KeyboardInterrupt:
        pass
    finally:
        with open(args.out, "wb") as f:
            pyboy.save_state(f)
        print(f"Saved start state -> {args.out}")
        pyboy.stop(save=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
