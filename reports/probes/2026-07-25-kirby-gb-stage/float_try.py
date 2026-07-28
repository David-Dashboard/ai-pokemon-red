"""Iterate on Kirby's float-over-the-pillar input sequence from the at_pillar.state checkpoint
(reach_pillar.py). Applies a hardcoded sequence of presses, screenshotting after every press so
the sequence can be eyeballed and adjusted. $0, no LLM -- pure mechanics probing.

Usage: edit SEQUENCE below, then run.
"""
from __future__ import annotations
import os
import sys

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
sys.path.insert(0, REPO)

from core.gb_emulator import PyBoyEmulator

PRIMARY = "E:/AI_Personas/10_pokemon_and_chess_and_office/ai-pokemon-red"
ROM = PRIMARY + "/roms/Kirby's Dream Land (USA, Europe).gb"
OUT = "C:/Users/Succe/AppData/Local/Temp/claude/E--AI-Personas-10-pokemon-and-chess-and-office/8a4301d3-699a-43aa-b563-0d37f6b22d43/scratchpad/kirby_gb_stage"
STATE = os.path.join(OUT, "at_pillar.state")

# (button_or_None, hold_frames, settle_frames)
SEQUENCE = [
    ("a", 10, 2),     # jump
    ("a", 10, 2),     # inflate/float (2nd A while airborne)
    (None, 20, 0),    # observe
    ("up", 20, 0),    # try: does UP ascend while floating?
    (None, 10, 0),
    ("right", 20, 0),
    ("up", 20, 0),
    (None, 10, 0),
    ("right", 30, 0),
]


def main() -> int:
    emu = PyBoyEmulator(ROM, headless=True)
    emu.load_state(STATE)
    tag_dir = os.path.join(OUT, "float_try")
    os.makedirs(tag_dir, exist_ok=True)
    for i, (button, hold, settle) in enumerate(SEQUENCE):
        if button is None:
            emu.tick(hold + settle)
        else:
            emu.press(button, hold_frames=hold, settle_frames=settle)
        png = os.path.join(tag_dir, f"seq_{i:02d}_{button}.png")
        emu.save_screen(png)
        print(f"{i}: {button} hold={hold} settle={settle} -> {png}  frame={emu.frame}")
    emu.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
