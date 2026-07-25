"""Replay a commands.json (as produced by drive_lap.py) from the savestate and dump artifacts.

Deterministic replay: the exact same per-frame button sets are re-issued, so results match
the original drive_lap.py run byte-for-byte (confirmed pattern: reports/2026-07-23-oracle-mkds-
lap.md's "byte-identical... fresh-process replay"). This lets drive_lap.py stay screenshot-free
(fast, for iterating on the driving policy) while this script does the expensive image/RAM
capture only over the frame windows that matter.

Modes (any combination):
  --shots F1,F2,...       save top+bottom screenshot PNGs at these exact frames
  --shots-range A:B:STEP  save screenshots for frames in range(A, B, STEP)
  --ram-dump F1,F2,...    dump the full 4MB main-RAM region (0x02000000-0x023FFFFF) at these
                          frames, as .bin files, for later diffing (ram_diff.py)

Usage:
  <venv>/python.exe replay_and_shoot.py --assets <primary-checkout> --commands <dir>/commands.json \
      --out <dir> --shots-range 550:650:5
"""
from __future__ import annotations

import argparse
import json
import os
import sys

RAM_BASE = 0x02000000
RAM_SIZE = 0x00400000  # 4 MiB NDS main RAM


def _parse_frame_list(s: str | None) -> list[int]:
    if not s:
        return []
    return [int(x) for x in s.split(",") if x.strip()]


def _parse_range(s: str | None) -> list[int]:
    if not s:
        return []
    a, b, step = (int(x) for x in s.split(":"))
    return list(range(a, b, step))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--assets", required=True)
    ap.add_argument("--repo", default=None)
    ap.add_argument("--commands", required=True, help="path to commands.json from drive_lap.py")
    ap.add_argument("--out", required=True)
    ap.add_argument("--shots", default=None)
    ap.add_argument("--shots-range", default=None)
    ap.add_argument("--ram-dump", default=None)
    args = ap.parse_args()

    assets = os.path.abspath(args.assets)
    repo = os.path.abspath(args.repo) if args.repo else assets
    sys.path.insert(0, repo)
    from core.nds_emulator import DeSmuMEEmulator  # noqa: E402
    from desmume.controls import Keys, keymask  # noqa: E402
    from PIL import Image  # noqa: E402

    rom = os.path.join(assets, "roms/nds/Mario Kart DS (USA) (En,Fr,De,Es,It).nds")
    state = os.path.join(assets, "runs/nds3d_probe/mkds_race_start.state")
    out = os.path.abspath(args.out)
    os.makedirs(out, exist_ok=True)

    commands = json.load(open(args.commands))
    shot_frames = set(_parse_frame_list(args.shots)) | set(_parse_range(args.shots_range))
    ram_frames = set(_parse_frame_list(args.ram_dump))

    emu = DeSmuMEEmulator(rom, headless=True)
    key_of = {b: keymask(getattr(Keys, "KEY_" + b.upper())) for b in
              ("a", "b", "left", "right", "up", "down")}

    emu.load_state(state)
    for m in key_of.values():
        emu._emu.input.keypad_rm_key(m)
    emu.tick(1)

    held: set[str] = set()
    for f, want_list in enumerate(commands):
        want = set(want_list)
        for b in want - held:
            emu._emu.input.keypad_add_key(key_of[b])
        for b in held - want:
            emu._emu.input.keypad_rm_key(key_of[b])
        held = want
        emu.tick(1)
        if f in shot_frames:
            arr = emu.screen_ndarray()
            Image.fromarray(arr[:192], "RGB").save(os.path.join(out, f"top_f{f:06d}.png"))
            Image.fromarray(arr[192:], "RGB").save(os.path.join(out, f"bot_f{f:06d}.png"))
        if f in ram_frames:
            buf = bytes(emu._emu.memory.unsigned[RAM_BASE:RAM_BASE + RAM_SIZE])
            with open(os.path.join(out, f"ram_f{f:06d}.bin"), "wb") as fh:
                fh.write(buf)

    for m in key_of.values():
        emu._emu.input.keypad_rm_key(m)
    emu.close()
    print(f"Replayed {len(commands)} frames. shots={len(shot_frames)} ram_dumps={len(ram_frames)} -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
