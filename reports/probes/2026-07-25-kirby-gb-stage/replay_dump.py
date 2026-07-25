"""$0 oracle hunt (2026-07-25): replay the recorded HUMAN Kirby's Dream Land session
(D:/ai_pokemon_runs/2026-06-23_kirby_play/buttons.jsonl -- a human playthrough that reached
score 39460 in a Castle Lololo room per its checkpoint_01.state) through a FRESH PyBoy boot,
dumping a full WRAM snapshot (0xC000-0xE000) + HRAM (0xFF80-0x10000) + a screenshot at every
step. NO LLM, $0, offline PyBoy only.

The original recorder logged one polled button per 12-frame tick (meta.json sample_every=12);
consecutive identical single-button polls are run-length-encoded here into ONE continuous hold
of 12*N frames (closer to what a human actually did -- holding a direction/A -- than N separate
press+release cycles) via PyBoyEmulator.press(button, hold_frames=12*N, settle_frames=2).

Output (written under --out, a scratch dir -- nothing here is committed):
  manifest.jsonl : {step, frame, screen_png}
  ram.bin        : concatenated per-step snapshots, RAM_SPAN bytes each (WRAM+HRAM)
  frames/step_%06d.png

Run:
  <venv-python> reports/probes/2026-07-25-kirby-gb-stage/replay_dump.py \
      --buttons D:/ai_pokemon_runs/2026-06-23_kirby_play/buttons.jsonl \
      --out <scratch>/replay_kirby_play --max-step 1800
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

WRAM_LO, WRAM_HI = 0xC000, 0xE000     # 8192 bytes
HRAM_LO, HRAM_HI = 0xFF80, 0x10000    # 128 bytes
RAM_SPAN = (WRAM_HI - WRAM_LO) + (HRAM_HI - HRAM_LO)


def load_button_runs(path: str, max_step: int | None):
    """Read buttons.jsonl -> run-length-encoded (button_or_None, total_frames) list."""
    entries = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            if max_step is not None and rec["step"] > max_step:
                break
            btns = rec.get("buttons") or []
            entries.append(btns[0] if btns else None)
    runs = []
    i = 0
    while i < len(entries):
        b = entries[i]
        j = i
        while j < len(entries) and entries[j] == b:
            j += 1
        runs.append((b, (j - i) * 12))   # sample_every=12 frames/poll
        i = j
    return runs, len(entries)


def snapshot(emu: PyBoyEmulator) -> bytes:
    wram = bytes(emu.read(a) for a in range(WRAM_LO, WRAM_HI))
    hram = bytes(emu.read(a) for a in range(HRAM_LO, HRAM_HI))
    return wram + hram


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--buttons", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--max-step", type=int, default=None)
    ap.add_argument("--screenshot-every", type=int, default=1,
                     help="save a PNG every N steps (1 = every step)")
    args = ap.parse_args()

    runs, n_entries = load_button_runs(args.buttons, args.max_step)
    print(f"loaded {n_entries} logged steps -> {len(runs)} RLE runs")

    os.makedirs(args.out, exist_ok=True)
    frames_dir = os.path.join(args.out, "frames")
    os.makedirs(frames_dir, exist_ok=True)

    emu = PyBoyEmulator(ROM, headless=True)
    manifest = open(os.path.join(args.out, "manifest.jsonl"), "w", encoding="utf-8")
    ram_out = open(os.path.join(args.out, "ram.bin"), "wb")

    step = 0
    for button, total_frames in runs:
        if button is None:
            emu.tick(total_frames)
        else:
            emu.press(button, hold_frames=max(1, total_frames - 2), settle_frames=2)
        snap = snapshot(emu)
        ram_out.write(snap)
        png = None
        if step % args.screenshot_every == 0:
            png = f"step_{step:06d}.png"
            emu.save_screen(os.path.join(frames_dir, png))
        manifest.write(json.dumps({"step": step, "frame": emu.frame, "button": button,
                                    "run_frames": total_frames, "screen_png": png}) + "\n")
        step += 1
        if step % 100 == 0:
            print(f"  step {step}/{len(runs)}  emu_frame={emu.frame}")

    manifest.close()
    ram_out.close()
    emu.close()
    print(f"done: {step} steps -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
