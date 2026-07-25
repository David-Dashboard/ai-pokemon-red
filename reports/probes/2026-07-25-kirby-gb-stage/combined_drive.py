"""Combined driver: RLE-human-log prefix (reaches the Green Greens pillar reliably) + a hand-tuned
jump+float-over sequence (confirmed working in float_try.py: A,A puffs Kirby up; holding
up (+right) ascends over the pillar) + resume the RLE-compiled human log for the remainder of the
level. Dumps a full WRAM+HRAM snapshot and a screenshot at every compiled step so the stage-1 ->
stage-2 transition (and RAM around it) can be found and diffed. $0, no LLM.
"""
from __future__ import annotations
import argparse
import json
import os
import sys

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.dirname(__file__))

from core.gb_emulator import PyBoyEmulator
from replay_dump import load_button_runs, ROM, WRAM_LO, WRAM_HI, HRAM_LO, HRAM_HI, snapshot

BUTTONS = "D:/ai_pokemon_runs/2026-06-23_kirby_play/buttons.jsonl"

FLOAT_OVER_PILLAR = [
    ("a", 10, 2),
    ("a", 10, 2),
    (None, 20, 0),
    ("up", 20, 0),
    (None, 10, 0),
    ("right", 20, 0),
    ("up", 20, 0),
    (None, 10, 0),
    ("right", 30, 0),
    (None, 20, 0),   # let Kirby settle/descend back to ground
    ("right", 40, 10),
]


def apply(emu, button, hold, settle):
    if button is None:
        emu.tick(hold + settle)
    else:
        emu.press(button, hold_frames=hold, settle_frames=settle)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--prefix-runs", type=int, default=200)
    ap.add_argument("--max-log-step", type=int, default=1800)
    ap.add_argument("--resume-runs", type=int, default=10_000, help="how many post-float RLE runs to replay")
    args = ap.parse_args()

    runs, _ = load_button_runs(BUTTONS, max_step=args.max_log_step)
    prefix = runs[:args.prefix_runs]
    resume = runs[args.prefix_runs:args.prefix_runs + args.resume_runs]

    os.makedirs(args.out, exist_ok=True)
    frames_dir = os.path.join(args.out, "frames")
    os.makedirs(frames_dir, exist_ok=True)
    manifest = open(os.path.join(args.out, "manifest.jsonl"), "w", encoding="utf-8")
    ram_out = open(os.path.join(args.out, "ram.bin"), "wb")

    emu = PyBoyEmulator(ROM, headless=True)
    step = 0

    def record(phase, button):
        nonlocal step
        ram_out.write(snapshot(emu))
        png = f"step_{step:06d}.png"
        emu.save_screen(os.path.join(frames_dir, png))
        manifest.write(json.dumps({"step": step, "phase": phase, "button": button,
                                    "frame": emu.frame, "screen_png": png}) + "\n")
        step += 1

    print(f"prefix: {len(prefix)} runs")
    for button, total_frames in prefix:
        apply(emu, button, max(1, total_frames - 2) if button else total_frames, 2 if button else 0)
        record("prefix", button)

    print("float-over-pillar sequence")
    for button, hold, settle in FLOAT_OVER_PILLAR:
        apply(emu, button, hold, settle)
        record("float", button)

    print(f"resume: {len(resume)} runs")
    for i, (button, total_frames) in enumerate(resume):
        apply(emu, button, max(1, total_frames - 2) if button else total_frames, 2 if button else 0)
        record("resume", button)
        if (i + 1) % 100 == 0:
            print(f"  resume {i+1}/{len(resume)}  emu_frame={emu.frame}")

    manifest.close()
    ram_out.close()
    emu.close()
    print(f"done: {step} recorded steps -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
