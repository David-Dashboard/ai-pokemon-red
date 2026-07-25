"""One-off check: replay a commands.json (from drive_lap.py or step.py's running log) in a
SINGLE continuous process from the ORIGINAL savestate, and report speed/ckpt90/ckpt94 at the
end. Used to rule out savestate-chain accumulation drift in the incremental step.py/
auto_recover.py workflow (each decision is a fresh process reloading the previous savestate) --
if this continuous replay matches the chained result byte-for-byte, the chaining technique
itself is not the source of any observed difficulty.

Usage: <venv>/python.exe verify_continuous.py --assets <primary-checkout> --commands <path>
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


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--assets", required=True)
    ap.add_argument("--repo", default=None)
    ap.add_argument("--commands", required=True)
    args = ap.parse_args()

    assets = os.path.abspath(args.assets)
    repo = os.path.abspath(args.repo) if args.repo else assets
    sys.path.insert(0, repo)
    from core.nds_emulator import DeSmuMEEmulator  # noqa: E402
    from desmume.controls import Keys, keymask  # noqa: E402

    rom = os.path.join(assets, "roms/nds/Mario Kart DS (USA) (En,Fr,De,Es,It).nds")
    state = os.path.join(assets, "runs/nds3d_probe/mkds_race_start.state")
    commands = json.load(open(args.commands))

    emu = DeSmuMEEmulator(rom, headless=True)
    key_of = {b: keymask(getattr(Keys, "KEY_" + b.upper())) for b in
              ("a", "b", "left", "right", "up", "down")}
    emu.load_state(state)
    for m in key_of.values():
        emu._emu.input.keypad_rm_key(m)
    emu.tick(1)

    held: set[str] = set()
    speeds = []
    for f, want_list in enumerate(commands):
        want = set(want_list)
        for b in want - held:
            emu._emu.input.keypad_add_key(key_of[b])
        for b in held - want:
            emu._emu.input.keypad_rm_key(key_of[b])
        held = want
        emu.tick(1)
        if f >= len(commands) - 5:
            b = bytes(emu._emu.memory.unsigned[SPEED_ADDR:SPEED_ADDR + 4])
            speeds.append(struct.unpack("<I", b)[0])

    ckpt90, ckpt94 = emu.read(CKPT90_ADDR), emu.read(CKPT94_ADDR)
    emu.close()
    print(json.dumps({"total_frames": len(commands), "last5_speeds": speeds,
                      "ckpt90": ckpt90, "ckpt94": ckpt94}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
