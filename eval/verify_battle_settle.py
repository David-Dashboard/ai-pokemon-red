"""Validate the PRODUCTION battle-settle path (PyBoyEmulator.settle, the same call plugin uses)
on REAL battle pixels: reach the rival battle, then press A a few times WITH settle and confirm
each observation lands on a STABLE screen (a text box or a menu) instead of a mid-animation frame —
and that the FIGHT/move menus are reached within a handful of presses (run #3 needed >40 and never
got there). RAM is read ONLY to navigate to the battle and to label frames (the oracle role).

Run: uv run python -m eval.verify_battle_settle
"""
from __future__ import annotations

import glob
import os
import random
import sys

import numpy as np

from games.pokemon_red.emulator import PyBoyEmulator
from games.pokemon_red.memory_map import ADDR_IS_IN_BATTLE, ADDR_MAP_ID, ADDR_X, ADDR_Y
from games.pokemon_red.perceiver import detect_mode
from games.pokemon_red.textbox import FontTable, decode

ROM = sys.argv[1] if len(sys.argv) > 1 else "roms/PokemonRed.gb"
STATE = sys.argv[2] if len(sys.argv) > 2 else "start.state"
OUT = "runs/battle_settle"
BIAS = {38: ["up", "right"], 37: ["down"], 0: ["up"], 40: ["up"]}


def main() -> int:
    os.makedirs(OUT, exist_ok=True)
    for f in glob.glob(os.path.join(OUT, "*.png")):
        os.remove(f)
    emu = PyBoyEmulator(ROM, headless=True)
    emu.load_state(STATE)
    M = emu._pyboy.memory
    rng = random.Random(1)
    try:
        table = FontTable.load()
    except Exception:
        table = None

    # navigate to the rival battle (RAM-guided; oracle use only)
    for _ in range(1500):
        if M[ADDR_IS_IN_BATTLE]:
            break
        if rng.random() < 0.40:
            emu.press("a" if rng.random() < 0.5 else "b")
        else:
            d = rng.choice(BIAS.get(M[ADDR_MAP_ID], []) + ["up", "down", "left", "right"])
            emu.press(d); emu.press(d)
    if not M[ADDR_IS_IN_BATTLE]:
        print("DID NOT REACH BATTLE"); emu.close(); return 1
    print(f"reached battle (in_battle={M[ADDR_IS_IN_BATTLE]}).\n")

    # Press A WITH the production settle, logging each settled observation. Each line is one
    # observation the agent would see -> one potential LLM wake. We expect a handful of distinct
    # stable screens that march intro -> action menu -> move list, not dozens of mid-animation frames.
    print(f"{'press':<7}{'settled':>8}{'frames':>8}{'mode':>9}{'diff_vs_prev':>13}   text")
    prev = None
    for i in range(12):
        before = emu.frame
        settled = emu.settle()                # the exact call plugin._settle_if_battle makes
        frame = emu.screen_ndarray()
        mode = detect_mode(frame)
        d = 0.0 if prev is None else float(np.abs(frame.astype(np.int16) - prev).mean())
        text = decode(frame, table).replace("\n", " | ") if table is not None else "?"
        emu._pyboy.screen.image.save(os.path.join(OUT, f"{i:02d}_{mode}.png"))
        print(f"A#{i:<5}{str(settled):>8}{emu.frame-before:>8}{mode:>9}{d:>13.2f}   {text!r}")
        prev = frame.astype(np.int16)
        emu.press("a")                        # advance to the next state

    emu.close()
    print("\nframes in", OUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
