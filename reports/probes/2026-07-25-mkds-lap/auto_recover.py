"""When stuck (speed pinned near rest), empirically SCAN several short recovery candidates from
the SAME stuck state (reloading one emulator instance repeatedly -- reload_state is not a new
DeSmuME() instance, so this respects the one-instance-per-process gotcha), rank by which one
actually regains speed, then COMMIT the winner for a longer follow-through burst.

This replaces guessing steering direction from a screenshot: the speed oracle 0x0237438C
gives a fast, objective, closed-loop verdict on which recovery direction actually works from
this exact stuck configuration.

Usage:
  <venv>/python.exe auto_recover.py --assets <primary-checkout> --in-state <path> \
      --out-state <path> --commands-log <path> --shot <dir>/tag \
      [--candidates reverse,reverse_left,reverse_right,pulse_left,pulse_right] \
      [--test-frames 60] [--commit-frames 150]
"""
from __future__ import annotations

import argparse
import json
import os
import struct
import sys

SPEED_ADDR = 0x0237438C
CKPT90_ADDR = 0x022C8090
CKPT94_ADDR = 0x022C8094

DEFAULT_CANDIDATES = ["reverse", "reverse_left", "reverse_right",
                      "pulse_left", "pulse_right", "straight"]


def _speed(emu) -> int:
    b = bytes(emu._emu.memory.unsigned[SPEED_ADDR:SPEED_ADDR + 4])
    return struct.unpack("<I", b)[0]


def _policy_fn(name):
    return {
        "pulse_left": lambda f: ("a", "left") if f % 2 == 0 else ("a",),
        "pulse_right": lambda f: ("a", "right") if f % 2 == 0 else ("a",),
        "full_left": lambda _f: ("a", "left"),
        "full_right": lambda _f: ("a", "right"),
        "straight": lambda _f: ("a",),
        "reverse": lambda _f: ("b",),
        "reverse_left": lambda _f: ("b", "left"),
        "reverse_right": lambda _f: ("b", "right"),
        "coast": lambda _f: (),
    }[name]


def _run(emu, key_of, in_state, fn, frames):
    emu.load_state(in_state)
    for m in key_of.values():
        emu._emu.input.keypad_rm_key(m)
    held: set[str] = set()
    speeds = []
    commands = []
    for f in range(frames):
        want = set(fn(f))
        for b in want - held:
            emu._emu.input.keypad_add_key(key_of[b])
        for b in held - want:
            emu._emu.input.keypad_rm_key(key_of[b])
        held = want
        commands.append(sorted(want))
        emu.tick(1)
        speeds.append(_speed(emu))
    for m in key_of.values():
        emu._emu.input.keypad_rm_key(m)
    return speeds, commands


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--assets", required=True)
    ap.add_argument("--repo", default=None)
    ap.add_argument("--in-state", required=True)
    ap.add_argument("--out-state", required=True)
    ap.add_argument("--commands-log", required=True)
    ap.add_argument("--shot", default=None)
    ap.add_argument("--candidates", default=",".join(DEFAULT_CANDIDATES))
    ap.add_argument("--test-frames", type=int, default=60)
    ap.add_argument("--commit-frames", type=int, default=150)
    args = ap.parse_args()

    assets = os.path.abspath(args.assets)
    repo = os.path.abspath(args.repo) if args.repo else assets
    sys.path.insert(0, repo)
    from core.nds_emulator import DeSmuMEEmulator  # noqa: E402
    from desmume.controls import Keys, keymask  # noqa: E402

    rom = os.path.join(assets, "roms/nds/Mario Kart DS (USA) (En,Fr,De,Es,It).nds")
    emu = DeSmuMEEmulator(rom, headless=True)
    key_of = {b: keymask(getattr(Keys, "KEY_" + b.upper())) for b in
              ("a", "b", "left", "right", "up", "down")}

    candidates = args.candidates.split(",")
    results = {}
    for name in candidates:
        speeds, _ = _run(emu, key_of, args.in_state, _policy_fn(name), args.test_frames)
        results[name] = {"end": speeds[-1], "max": max(speeds), "min": min(speeds)}
        print(f"  candidate {name:14s} end={speeds[-1]:>9} max={max(speeds):>9}", flush=True)

    winner = max(candidates, key=lambda n: (results[n]["end"], results[n]["max"]))
    print(f"-> winner: {winner}", flush=True)

    speeds, commands = _run(emu, key_of, args.in_state, _policy_fn(winner), args.commit_frames)
    ckpt90 = emu.read(CKPT90_ADDR)
    ckpt94 = emu.read(CKPT94_ADDR)

    if args.shot:
        from PIL import Image
        arr = emu.screen_ndarray()
        Image.fromarray(arr[:192], "RGB").save(f"{args.shot}_top_end.png")
        Image.fromarray(arr[192:], "RGB").save(f"{args.shot}_bot_end.png")

    emu.save_state(args.out_state)
    emu.close()

    log = []
    if os.path.exists(args.commands_log):
        log = json.load(open(args.commands_log))
    log.extend(commands)
    with open(args.commands_log, "w") as fh:
        json.dump(log, fh)

    print(json.dumps({
        "winner": winner, "scan": results, "commit_frames": args.commit_frames,
        "speed_start": speeds[0], "speed_end": speeds[-1], "speed_max": max(speeds),
        "ckpt90": ckpt90, "ckpt94": ckpt94, "total_commands_logged": len(log),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
