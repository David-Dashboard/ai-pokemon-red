"""Generic $0 offline GBA driver/probe for the EX03 (Emerald/Oldale) and EX04 (Kirby GBA/Level 1-1)
oracle hunts. Not part of the shipped harness -- a throwaway-but-committed script per the task's
instruction to commit probe scripts under reports/probes/2026-07-25-gba-exam/.

Imports core.gba_emulator.GBAEmulator UNMODIFIED (no edits to core/ -- this is a read-only consumer).
Run from WSL with the same env the 2026-06-29 recipe documents:
  LD_LIBRARY_PATH=~/gba-spike PYTHONPATH=~/gba-spike/mgba-build/python/lib.linux-x86_64-3.8:<repo_root> \
    ~/gba-spike/.venv/bin/python3 gba_drive.py ...

Usage:
  gba_drive.py --rom PATH [--state-in PATH] --state-out PATH [--screenshot PATH]
               [--actions "a,wait:60,start:16:30*3"] [--watch "name=0xADDR:u8,..."]

Action tokens (comma separated, applied in order):
  BUTTON                 press with default hold=8 settle=16
  BUTTON:HOLD:SETTLE     press with explicit frame counts
  wait:N                 advance N frames with no keys held
  TOKEN*K                repeat the token K times (expanded before execution)

Watch tokens (comma separated): NAME=0xADDR:WIDTH where WIDTH in {u8,u16,u32}. u16/u32 are decoded
little-endian from consecutive core.read() byte calls -- core/gba_emulator.py itself only exposes
single-byte read(), so multi-byte assembly happens here, not in core/.
"""
from __future__ import annotations

import argparse
import json
import sys


def expand_actions(spec: str) -> list[str]:
    if not spec:
        return []
    out = []
    for raw in spec.split(","):
        raw = raw.strip()
        if not raw:
            continue
        if "*" in raw:
            token, count = raw.rsplit("*", 1)
            out.extend([token] * int(count))
        else:
            out.append(raw)
    return out


def apply_action(emu, token: str) -> None:
    if token.startswith("wait:"):
        emu.tick(int(token.split(":", 1)[1]))
        return
    parts = token.split(":")
    button = parts[0]
    hold = int(parts[1]) if len(parts) > 1 else 8
    settle = int(parts[2]) if len(parts) > 2 else 16
    emu.press(button, hold_frames=hold, settle_frames=settle)


def read_width(emu, addr: int, width: str) -> int:
    if width == "u8":
        return emu.read(addr)
    if width == "u16":
        lo, hi = emu.read(addr), emu.read(addr + 1)
        return lo | (hi << 8)
    if width == "u32":
        b = [emu.read(addr + i) for i in range(4)]
        return b[0] | (b[1] << 8) | (b[2] << 16) | (b[3] << 24)
    raise ValueError(f"unknown width {width!r}")


def parse_watch(spec: str) -> dict[str, tuple[int, str]]:
    out = {}
    if not spec:
        return out
    for item in spec.split(","):
        item = item.strip()
        if not item:
            continue
        name, rest = item.split("=", 1)
        addr_s, width = rest.split(":", 1)
        out[name] = (int(addr_s, 0), width)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rom", required=True)
    ap.add_argument("--state-in", default=None)
    ap.add_argument("--state-out", required=True)
    ap.add_argument("--screenshot", default=None)
    ap.add_argument("--actions", default="")
    ap.add_argument("--watch", default="")
    ap.add_argument("--dump-region", default=None,
                     help="optional START:LEN (hex or dec) EWRAM slice to dump raw bytes for diffing")
    ap.add_argument("--dump-region-out", default=None)
    args = ap.parse_args()

    # Repo root must already be on PYTHONPATH (see module docstring) so this import resolves to
    # core/gba_emulator.py unmodified.
    from core.gba_emulator import GBAEmulator

    emu = GBAEmulator(args.rom)
    if args.state_in:
        emu.load_state(args.state_in)

    for token in expand_actions(args.actions):
        apply_action(emu, token)

    watch = parse_watch(args.watch)
    result = {"frame": emu.frame, "watch": {name: read_width(emu, addr, width)
                                             for name, (addr, width) in watch.items()}}

    if args.screenshot:
        emu.save_screen(args.screenshot)
    emu.save_state(args.state_out)

    if args.dump_region:
        start_s, len_s = args.dump_region.split(":")
        start, length = int(start_s, 0), int(len_s, 0)
        data = bytes(emu.read(start + i) for i in range(length))
        if args.dump_region_out:
            with open(args.dump_region_out, "wb") as f:
                f.write(data)
        result["dump_region"] = {"start": hex(start), "len": length,
                                  "out": args.dump_region_out}

    print(json.dumps(result, sort_keys=True))
    emu.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
