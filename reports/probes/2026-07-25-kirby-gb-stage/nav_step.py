"""Interactive-ish navigation helper: load a state, apply a hand-specified sequence, save a new
state + screenshot, print candidate values. Used to eyes-on-iterate through Castle Lololo one
short burst at a time (mirrors the pillar-crossing approach in float_try.py). $0, no LLM.
"""
from __future__ import annotations
import argparse
import os
import sys

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.dirname(__file__))

from core.gb_emulator import PyBoyEmulator
from replay_dump import ROM

OUT = "C:/Users/Succe/AppData/Local/Temp/claude/E--AI-Personas-10-pokemon-and-chess-and-office/8a4301d3-699a-43aa-b563-0d37f6b22d43/scratchpad/kirby_gb_stage"
CAND = {"D19F": 0xD19F, "D3A9": 0xD3A9, "D3BA": 0xD3BA, "D3CD": 0xD3CD, "D086_hp": 0xD086}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--load", required=True, help="state file to load (path or name under OUT)")
    ap.add_argument("--save", required=True, help="name (under OUT) to save resulting state+png")
    ap.add_argument("--seq", required=True,
                     help="semicolon-separated button:hold:settle, e.g. right:20:4;a:10:2;right:30:10")
    args = ap.parse_args()

    load_path = args.load if os.path.exists(args.load) else os.path.join(OUT, args.load)
    emu = PyBoyEmulator(ROM, headless=True)
    emu.load_state(load_path)

    for spec in args.seq.split(";"):
        spec = spec.strip()
        if not spec:
            continue
        parts = spec.split(":")
        button = parts[0]
        hold = int(parts[1]) if len(parts) > 1 else 10
        settle = int(parts[2]) if len(parts) > 2 else 4
        if button in ("none", "wait", "-"):
            emu.tick(hold + settle)
        else:
            emu.press(button, hold_frames=hold, settle_frames=settle)

    png = os.path.join(OUT, f"{args.save}.png")
    state = os.path.join(OUT, f"{args.save}.state")
    emu.save_screen(png)
    emu.save_state(state)
    vals = {name: emu.read(a) for name, a in CAND.items()}
    print(f"saved {state} / {png}  frame={emu.frame}  vals={vals}")
    emu.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
