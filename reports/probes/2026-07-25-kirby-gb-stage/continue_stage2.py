"""Continue play from the confirmed-Stage-2 checkpoint (kirby_play/checkpoint_01.state, Castle
Lololo, score 39460) with a simple right-biased autopilot (periodic jumps + occasional
up/down for doors/elevators), dumping a WRAM+HRAM snapshot and screenshot every step so multiple
INDEPENDENT Stage-2 room samples can be picked for the stability check (does a stage-counter
candidate stay constant across different rooms within the same stage, unlike a room-ID byte).
$0, no LLM.
"""
from __future__ import annotations
import argparse
import json
import os
import random
import sys

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.dirname(__file__))

from core.gb_emulator import PyBoyEmulator
from replay_dump import ROM, snapshot

CHECKPOINT = "D:/ai_pokemon_runs/2026-06-23_kirby_play/checkpoint_01.state"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--steps", type=int, default=300)
    ap.add_argument("--seed", type=int, default=7)
    args = ap.parse_args()
    random.seed(args.seed)

    os.makedirs(args.out, exist_ok=True)
    frames_dir = os.path.join(args.out, "frames")
    os.makedirs(frames_dir, exist_ok=True)
    manifest = open(os.path.join(args.out, "manifest.jsonl"), "w", encoding="utf-8")
    ram_out = open(os.path.join(args.out, "ram.bin"), "wb")

    emu = PyBoyEmulator(ROM, headless=True)
    emu.load_state(CHECKPOINT)

    cycle = (["right"] * 3 + ["b"] * 3 + ["right"] * 3 + ["a"] + ["right"] * 3 + ["b"] * 3)
    for i in range(args.steps):
        button = cycle[i % len(cycle)]
        emu.press(button, hold_frames=10, settle_frames=14)
        ram_out.write(snapshot(emu))
        png = f"step_{i:06d}.png"
        emu.save_screen(os.path.join(frames_dir, png))
        manifest.write(json.dumps({"step": i, "button": button, "frame": emu.frame,
                                    "screen_png": png}) + "\n")
        if (i + 1) % 50 == 0:
            print(f"  step {i+1}/{args.steps}  frame={emu.frame}")

    manifest.close()
    ram_out.close()
    emu.close()
    print(f"done: {args.steps} steps -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
