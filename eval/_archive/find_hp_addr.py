"""Reproduce the Cave Noire life-oracle claim: which WRAM byte reads the visible HP at known frames?

Phase A (ADR-002 gate) needs a life RAM oracle to score the brain's pixel life-detector against. This finds
it the same no-game-knowledge way `find_ram_addr.py` finds position: scan the dumped WRAM (ram.bin, 8 KB/step)
for the byte(s) whose value at each ANCHOR frame equals the HP read off that frame's screenshot. A byte that
matches every (frame, value) anchor is a candidate; if exactly one byte matches, the oracle is pinned.

Committed so the `0xD389` claim is reproducible by any reviewer (the prior scan lived on an external mount):

  uv run python -m eval.find_hp_addr <run-with-ram.bin> --anchors 100:7 500:10 [--max-hp 10]

Reports, for each matching byte: its value distribution over the run and any frames reading ABOVE --max-hp
(transient transition artifacts — a clean HP register should sit in [0, max] except for those).
"""
from __future__ import annotations

import argparse
import os

import numpy as np

WRAM0 = 0xC000
WRAM_LEN = 0x2000          # 8 KB dumped: 0xC000..0xDFFF


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("run", help="run dir with ram.bin")
    ap.add_argument("--anchors", nargs="+", default=["100:7", "500:10"],
                    help="frame:value pairs the byte must match (HP read off that frame's screenshot)")
    ap.add_argument("--max-hp", type=int, default=10, help="displayed max HP; values above it are flagged")
    args = ap.parse_args()

    anchors = [(int(f), int(v)) for f, v in (a.split(":") for a in args.anchors)]
    ram = np.fromfile(os.path.join(args.run, "ram.bin"), dtype=np.uint8)
    n = ram.size // WRAM_LEN
    ram = ram[: n * WRAM_LEN].reshape(n, WRAM_LEN)
    print(f"{args.run}: {n} steps x {WRAM_LEN} WRAM bytes (0x{WRAM0:04X}..0x{WRAM0 + WRAM_LEN - 1:04X})")
    print(f"anchors (frame==value): {anchors}")

    match = np.ones(WRAM_LEN, dtype=bool)
    for f, v in anchors:
        match &= ram[f] == v
    addrs = [WRAM0 + b for b in np.where(match)[0]]
    print(f"\nbyte(s) matching ALL anchors: {[f'0x{a:04X}' for a in addrs] or 'NONE'}")

    for a in addrs:
        col = ram[:, a - WRAM0]
        over = np.where(col > args.max_hp)[0]
        print(f"\n  0x{a:04X}: distinct={sorted(set(int(x) for x in col))}  "
              f"min={int(col.min())} max={int(col.max())}")
        print(f"    frames > max_hp({args.max_hp}): {len(over)}/{n}"
              + (f"  at {over[:10].tolist()}{'...' if len(over) > 10 else ''}" if len(over) else ""))
    if len(addrs) != 1:
        print("\n  -> not pinned to a single byte; add more anchors (distinct HP values at known frames).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
