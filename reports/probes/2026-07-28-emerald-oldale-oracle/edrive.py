"""Offline $0 Emerald (GBA) drive+dump probe. Imports core.gba_emulator.GBAEmulator UNMODIFIED.

Extends the banked reports/probes/2026-07-25-gba-exam/gba_drive.py with:
  * mid-sequence screenshots (`shot:NAME` action token) so a long scripted drive is graded
    eyes-on at every step instead of only at the end;
  * full-region EWRAM (0x02000000, 256 KB) + IWRAM (0x03000000, 32 KB) dumps for bit-level
    diffing (the banked script dumped a single caller-specified EWRAM slice only).

Usage (from WSL, via run_edrive.sh):
  edrive.py --rom ROM [--state-in S] --state-out S2 [--shot-dir DIR] [--actions "..."]
            [--watch "name=0xADDR:u8,..."] [--dump-prefix PREFIX]

Action tokens (comma separated):
  BUTTON | BUTTON:HOLD:SETTLE | wait:N | shot:NAME | TOKEN*K
"""
from __future__ import annotations

import argparse
import json
import os
import sys

EWRAM_BASE, EWRAM_LEN = 0x02000000, 0x40000
IWRAM_BASE, IWRAM_LEN = 0x03000000, 0x8000


def expand_actions(spec: str) -> list[str]:
    out: list[str] = []
    for raw in (spec or "").split(","):
        raw = raw.strip()
        if not raw:
            continue
        if "*" in raw:
            token, count = raw.rsplit("*", 1)
            out.extend([token] * int(count))
        else:
            out.append(raw)
    return out


def read_width(emu, addr: int, width: str) -> int:
    n = {"u8": 1, "u16": 2, "u32": 4}[width]
    b = [emu.read(addr + i) for i in range(n)]
    return sum(v << (8 * i) for i, v in enumerate(b))


def parse_watch(spec: str) -> dict:
    out = {}
    for item in (spec or "").split(","):
        item = item.strip()
        if not item:
            continue
        name, rest = item.split("=", 1)
        addr_s, width = rest.split(":", 1)
        out[name] = (int(addr_s, 0), width)
    return out


def dump_region(emu, kind: str) -> bytes:
    """Bulk-read a whole RAM region via mgba's native u8 accessor (no core/ edits)."""
    mem = emu._core.memory  # read-only consumer of the same object core.gba_emulator.read() uses
    block = getattr(mem, kind)
    n = EWRAM_LEN if kind == "wram" else IWRAM_LEN
    return bytes(bytearray(block.u8[i] for i in range(n)))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rom", required=True)
    ap.add_argument("--state-in", default=None)
    ap.add_argument("--state-out", required=True)
    ap.add_argument("--shot-dir", default=None)
    ap.add_argument("--actions", default="")
    ap.add_argument("--watch", default="")
    ap.add_argument("--dump-prefix", default=None)
    ap.add_argument("--json-out", default=None)
    args = ap.parse_args()

    # mgba's C logger writes to STDOUT, which corrupts this script's JSON line. Silence it.
    try:
        import mgba.log
        mgba.log.silence()
    except Exception:
        pass

    from core.gba_emulator import GBAEmulator

    emu = GBAEmulator(args.rom)
    if args.state_in:
        emu.load_state(args.state_in)
        emu.tick(1)

    shots = []
    for token in expand_actions(args.actions):
        if token.startswith("shot:"):
            if args.shot_dir:
                os.makedirs(args.shot_dir, exist_ok=True)
                p = os.path.join(args.shot_dir, token.split(":", 1)[1] + ".png")
                emu.save_screen(p)
                shots.append(p)
            continue
        if token.startswith("wait:"):
            emu.tick(int(token.split(":", 1)[1]))
            continue
        parts = token.split(":")
        emu.press(parts[0],
                  hold_frames=int(parts[1]) if len(parts) > 1 else 8,
                  settle_frames=int(parts[2]) if len(parts) > 2 else 16)

    result = {"frame": emu.frame, "shots": shots,
              "watch": {n: read_width(emu, a, w) for n, (a, w) in parse_watch(args.watch).items()}}

    if args.shot_dir:
        os.makedirs(args.shot_dir, exist_ok=True)
        emu.save_screen(os.path.join(args.shot_dir, "final.png"))
    emu.save_state(args.state_out)

    if args.dump_prefix:
        for kind, suffix in (("wram", "ewram"), ("iwram", "iwram")):
            with open(f"{args.dump_prefix}.{suffix}.bin", "wb") as f:
                f.write(dump_region(emu, kind))
        result["dumped"] = args.dump_prefix

    out = json.dumps(result, sort_keys=True)
    if args.json_out:
        with open(args.json_out, "w") as f:
            f.write(out)
    sys.stderr.write(out + "\n")
    emu.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
