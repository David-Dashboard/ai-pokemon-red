"""Read specific addresses out of a ram.bin dump (per-step WRAM 0xC000-0xE000 + HRAM
0xFF80-0x10000 snapshots, as written by replay_dump.py/combined_drive.py/continue_stage2.py) for
a list of step indices. $0 offline analysis helper, no emulator needed -- just slices ram.bin.
"""
from __future__ import annotations
import argparse
import sys

WRAM_LO, WRAM_HI = 0xC000, 0xE000
HRAM_LO, HRAM_HI = 0xFF80, 0x10000
SPAN = (WRAM_HI - WRAM_LO) + (HRAM_HI - HRAM_LO)


def offset(addr: int) -> int:
    if WRAM_LO <= addr < WRAM_HI:
        return addr - WRAM_LO
    if HRAM_LO <= addr < HRAM_HI:
        return (WRAM_HI - WRAM_LO) + (addr - HRAM_LO)
    raise ValueError(f"addr 0x{addr:04X} outside WRAM/HRAM span")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ram", required=True)
    ap.add_argument("--steps", required=True, help="comma-separated step indices")
    ap.add_argument("--addrs", required=True, help="comma-separated hex addrs, e.g. D048,D052")
    args = ap.parse_args()

    steps = [int(s) for s in args.steps.split(",")]
    addrs = [int(a, 16) for a in args.addrs.split(",")]

    with open(args.ram, "rb") as f:
        data = f.read()
    n_steps = len(data) // SPAN
    print(f"{args.ram}: {n_steps} steps available (span={SPAN} bytes/step)")

    def bcd(b):
        return (b >> 4) * 10 + (b & 0xF)

    header = "step".rjust(6) + "".join(f"  0x{a:04X}".rjust(14) for a in addrs)
    print(header)
    for s in steps:
        if s >= n_steps:
            print(f"{s:6d}  (out of range, only {n_steps} steps)")
            continue
        base = s * SPAN
        vals = [data[base + offset(a)] for a in addrs]
        row = f"{s:6d}" + "".join(f"  {v:3d}(bcd{bcd(v):2d})".rjust(14) for v in vals)
        print(row)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
