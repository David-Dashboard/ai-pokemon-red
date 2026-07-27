"""Genuine broad RAM diff between two savestates over the whole 4MB NDS main-RAM region
(0x02000000-0x023FFFFF), used to search for lap/checkpoint-progress candidate bytes around a
captured event boundary -- not just spot-check the named lead (0x022C8094).

Usage:
  <venv>/python.exe ram_diff.py --assets <primary-checkout> --a <state_before> --b <state_after> \
      [--baseline-a <state> --baseline-b <state>]  # a 'boring' pair with no event, to subtract
      the continuously-ticking noise floor (timers, animation counters, audio, etc.)

Prints every changed address in (a,b) whose value ALSO changed in (baseline_a, baseline_b)
-- the noise floor -- separately from addresses that changed ONLY in (a,b): those are the
real event-specific candidates.
"""
from __future__ import annotations

import argparse
import os
import sys

import numpy as np

RAM_BASE = 0x02000000
RAM_SIZE = 0x00400000


def _dump(emu, rom_used):
    return np.frombuffer(bytes(emu._emu.memory.unsigned[RAM_BASE:RAM_BASE + RAM_SIZE]), dtype=np.uint8).copy()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--assets", required=True)
    ap.add_argument("--repo", default=None)
    ap.add_argument("--a", required=True)
    ap.add_argument("--b", required=True)
    ap.add_argument("--baseline-a", default=None)
    ap.add_argument("--baseline-b", default=None)
    ap.add_argument("--max-print", type=int, default=200)
    args = ap.parse_args()

    assets = os.path.abspath(args.assets)
    repo = os.path.abspath(args.repo) if args.repo else assets
    sys.path.insert(0, repo)
    from core.nds_emulator import DeSmuMEEmulator  # noqa: E402

    rom = os.path.join(assets, "roms/nds/Mario Kart DS (USA) (En,Fr,De,Es,It).nds")
    emu = DeSmuMEEmulator(rom, headless=True)

    emu.load_state(args.a)
    ram_a = _dump(emu, rom)
    emu.load_state(args.b)
    ram_b = _dump(emu, rom)

    changed = np.nonzero(ram_a != ram_b)[0]
    print(f"Event pair: {len(changed)} bytes changed out of {RAM_SIZE} "
          f"({RAM_BASE:#010x}-{RAM_BASE + RAM_SIZE - 1:#010x})")

    noise = set()
    if args.baseline_a and args.baseline_b:
        emu.load_state(args.baseline_a)
        base_a = _dump(emu, rom)
        emu.load_state(args.baseline_b)
        base_b = _dump(emu, rom)
        noise = set(np.nonzero(base_a != base_b)[0].tolist())
        print(f"Baseline (no-event) pair: {len(noise)} bytes changed (noise floor)")

    emu.close()

    candidates = [int(i) for i in changed if int(i) not in noise]
    print(f"\nEVENT-SPECIFIC candidates (changed in event pair, NOT in baseline noise): {len(candidates)}")
    for i in candidates[: args.max_print]:
        addr = RAM_BASE + i
        print(f"  {addr:#010x}  {ram_a[i]:3d} (0x{ram_a[i]:02x}) -> {ram_b[i]:3d} (0x{ram_b[i]:02x})")
    if len(candidates) > args.max_print:
        print(f"  ... ({len(candidates) - args.max_print} more)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
