"""Variant of replay_dump.py: NO run-length merging -- replay buttons.jsonl 1:1, one
PyBoyEmulator.press(button, hold_frames=8, settle_frames=16) call per logged step (matching
meta.json's hold/settle, which equal PyBoyEmulator.press()'s own defaults), tick(24) for an
empty-button step. Written because the RLE-merged variant (replay_dump.py) diverged badly
(got stuck at the same early Green Greens wall the 2026-07-23 hunt reported, losing lives) --
testing whether 1:1 per-step press/release (vs. one long continuous hold) tracks the human
run's score/progress more faithfully.
"""
from __future__ import annotations
import argparse
import json
import os
import sys

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
sys.path.insert(0, REPO)

from core.gb_emulator import PyBoyEmulator

PRIMARY = "E:/AI_Personas/10_pokemon_and_chess_and_office/ai-pokemon-red"
ROM = PRIMARY + "/roms/Kirby's Dream Land (USA, Europe).gb"

WRAM_LO, WRAM_HI = 0xC000, 0xE000
HRAM_LO, HRAM_HI = 0xFF80, 0x10000


def snapshot(emu: PyBoyEmulator) -> bytes:
    wram = bytes(emu.read(a) for a in range(WRAM_LO, WRAM_HI))
    hram = bytes(emu.read(a) for a in range(HRAM_LO, HRAM_HI))
    return wram + hram


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--buttons", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--max-step", type=int, default=None)
    ap.add_argument("--screenshot-every", type=int, default=1)
    args = ap.parse_args()

    recs = []
    with open(args.buttons, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            if args.max_step is not None and rec["step"] > args.max_step:
                break
            recs.append(rec)
    print(f"loaded {len(recs)} steps")

    os.makedirs(args.out, exist_ok=True)
    frames_dir = os.path.join(args.out, "frames")
    os.makedirs(frames_dir, exist_ok=True)

    emu = PyBoyEmulator(ROM, headless=True)
    manifest = open(os.path.join(args.out, "manifest.jsonl"), "w", encoding="utf-8")
    ram_out = open(os.path.join(args.out, "ram.bin"), "wb")

    for i, rec in enumerate(recs):
        btns = rec.get("buttons") or []
        if btns:
            emu.press(btns[0], hold_frames=8, settle_frames=16)
        else:
            emu.tick(24)
        ram_out.write(snapshot(emu))
        png = None
        if i % args.screenshot_every == 0:
            png = f"step_{i:06d}.png"
            emu.save_screen(os.path.join(frames_dir, png))
        manifest.write(json.dumps({"step": i, "orig_step": rec["step"], "frame": emu.frame,
                                    "button": (btns[0] if btns else None),
                                    "screen_png": png}) + "\n")
        if (i + 1) % 100 == 0:
            print(f"  step {i+1}/{len(recs)}  emu_frame={emu.frame}")

    manifest.close()
    ram_out.close()
    emu.close()
    print(f"done: {len(recs)} steps -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
