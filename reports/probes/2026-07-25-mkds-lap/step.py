"""Interactive single-burst driver: load a state, drive a fixed policy for N frames, save the
resulting state, print the RAM oracles, optionally save a screenshot, and append the exact
per-frame commands issued to a running commands-log (JSON list of per-frame button lists).

Exists because py-desmume SIGSEGVs on a second instance in one process (documented gotcha),
so a human-in-the-loop drive across many decisions has to be one process per decision, with
a savestate as the checkpoint carried between processes. Concatenating the commands-log at
the end reproduces the whole drive deterministically in a single pass (see replay_and_shoot.py
/ verify against a fresh drive_lap.py-style single-process run for the byte-identical check).

Policies (fixed, open-loop over the burst -- all steering decisions are made by the CALLER,
between bursts, using the printed oracle values and/or a screenshot):
  pulse_left / pulse_right   accel + half-strength steer (alternate frames, f3 spine)
  full_left / full_right     accel + full steer
  straight                   accel only
  reverse / reverse_left / reverse_right   B (+ steer)
  coast                      no input

Usage:
  <venv>/python.exe step.py --assets <primary-checkout> --in-state <path-or-ORIGINAL> \
      --out-state <path> --policy pulse_left --frames 200 --commands-log <path> [--shot <dir>/tag]
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


def _speed(emu) -> int:
    b = bytes(emu._emu.memory.unsigned[SPEED_ADDR:SPEED_ADDR + 4])
    return struct.unpack("<I", b)[0]


def _policy_fn(name):
    if name == "pulse_left":
        return lambda f: ("a", "left") if f % 2 == 0 else ("a",)
    if name == "pulse_right":
        return lambda f: ("a", "right") if f % 2 == 0 else ("a",)
    if name == "full_left":
        return lambda _f: ("a", "left")
    if name == "full_right":
        return lambda _f: ("a", "right")
    if name == "straight":
        return lambda _f: ("a",)
    if name == "reverse":
        return lambda _f: ("b",)
    if name == "reverse_left":
        return lambda _f: ("b", "left")
    if name == "reverse_right":
        return lambda _f: ("b", "right")
    if name == "coast":
        return lambda _f: ()
    if name == "wiggle":
        # rock-the-car: alternate reverse-left / reverse-right every 20f to break a wedge
        return lambda f: ("b", "left") if (f // 20) % 2 == 0 else ("b", "right")
    if name == "gun_wiggle":
        # accelerate while alternating full-left / full-right every 15f
        return lambda f: ("a", "left") if (f // 15) % 2 == 0 else ("a", "right")
    raise ValueError(f"unknown policy: {name}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--assets", required=True)
    ap.add_argument("--repo", default=None)
    ap.add_argument("--in-state", required=True, help="'ORIGINAL' for the banked race-start savestate, else a path")
    ap.add_argument("--out-state", required=True)
    ap.add_argument("--policy", required=True)
    ap.add_argument("--frames", type=int, required=True)
    ap.add_argument("--commands-log", required=True)
    ap.add_argument("--shot", default=None, help="dir/tag prefix to save top+bottom PNGs at burst end")
    ap.add_argument("--shot-every", type=int, default=0, help="also save every Nth frame within the burst")
    args = ap.parse_args()

    assets = os.path.abspath(args.assets)
    repo = os.path.abspath(args.repo) if args.repo else assets
    sys.path.insert(0, repo)
    from core.nds_emulator import DeSmuMEEmulator  # noqa: E402
    from desmume.controls import Keys, keymask  # noqa: E402

    rom = os.path.join(assets, "roms/nds/Mario Kart DS (USA) (En,Fr,De,Es,It).nds")
    orig_state = os.path.join(assets, "runs/nds3d_probe/mkds_race_start.state")
    in_state = orig_state if args.in_state == "ORIGINAL" else args.in_state

    emu = DeSmuMEEmulator(rom, headless=True)
    key_of = {b: keymask(getattr(Keys, "KEY_" + b.upper())) for b in
              ("a", "b", "left", "right", "up", "down")}

    emu.load_state(in_state)
    for m in key_of.values():
        emu._emu.input.keypad_rm_key(m)
    if args.in_state == "ORIGINAL":
        emu.tick(1)  # match drive_lap.py's settle tick right after the fresh load

    fn = _policy_fn(args.policy)
    held: set[str] = set()
    speeds, ckpt90s, ckpt94s = [], [], []
    commands = []
    for f in range(args.frames):
        want = set(fn(f))
        for b in want - held:
            emu._emu.input.keypad_add_key(key_of[b])
        for b in held - want:
            emu._emu.input.keypad_rm_key(key_of[b])
        held = want
        commands.append(sorted(want))
        emu.tick(1)
        speeds.append(_speed(emu))
        ckpt90s.append(emu.read(CKPT90_ADDR))
        ckpt94s.append(emu.read(CKPT94_ADDR))
        if args.shot_every and f % args.shot_every == 0:
            from PIL import Image
            arr = emu.screen_ndarray()
            base = args.shot or os.path.join(os.path.dirname(args.out_state), "shot")
            Image.fromarray(arr[:192], "RGB").save(f"{base}_top_f{f:05d}.png")
            Image.fromarray(arr[192:], "RGB").save(f"{base}_bot_f{f:05d}.png")

    for m in key_of.values():
        emu._emu.input.keypad_rm_key(m)

    if args.shot:
        from PIL import Image
        arr = emu.screen_ndarray()
        Image.fromarray(arr[:192], "RGB").save(f"{args.shot}_top_end.png")
        Image.fromarray(arr[192:], "RGB").save(f"{args.shot}_bot_end.png")

    emu.save_state(args.out_state)
    emu.close()

    # append this burst's commands to the running log
    log = []
    if os.path.exists(args.commands_log):
        log = json.load(open(args.commands_log))
    log.extend(commands)
    with open(args.commands_log, "w") as fh:
        json.dump(log, fh)

    print(json.dumps({
        "policy": args.policy, "frames": args.frames,
        "speed_start": speeds[0], "speed_end": speeds[-1], "speed_min": min(speeds), "speed_max": max(speeds),
        "ckpt90_start": ckpt90s[0], "ckpt90_end": ckpt90s[-1],
        "ckpt94_start": ckpt94s[0], "ckpt94_end": ckpt94s[-1],
        "ckpt90_trace_changes": [i for i in range(1, len(ckpt90s)) if ckpt90s[i] != ckpt90s[i - 1]],
        "ckpt94_trace_changes": [i for i in range(1, len(ckpt94s)) if ckpt94s[i] != ckpt94s[i - 1]],
        "total_commands_logged": len(log),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
