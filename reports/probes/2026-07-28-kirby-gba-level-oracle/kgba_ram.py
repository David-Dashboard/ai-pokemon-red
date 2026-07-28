"""Offline RAM sweep/diff over mgba GBA savestate FILES (no emulator, no WSL, runs on the Windows host).

Why this exists: the 2026-07-25 hunt read RAM only through live `emu.read()` calls, one address at a
time, which makes a whole-region uniqueness sweep impractical. An mgba raw GBA savestate is a flat
0x61000-byte `GBASerializedState`; both RAM regions sit at fixed offsets inside it, so every state
already on disk is a complete RAM snapshot that can be diffed instantly and offline.

Region offsets are NOT assumed -- they were measured (reports/2026-07-28-kirby-gba-level-oracle.md
"Savestate layout"): 7 probe words read live through `core.gba_emulator.GBAEmulator.read()` at
EWRAM 0x02000000/0x02020000/0x0203FFFC/0x02006020 and IWRAM 0x03000000/0x03004000/0x03007FFC were
matched byte-exact against the file at these bases, and the two rejected alternatives are recorded.

Usage:
  python kgba_ram.py diff  A.state B.state [--width u8|u16|u32] [--delta N]
  python kgba_ram.py trace ADDR:WIDTH  S1.state S2.state ...
  python kgba_ram.py equals VALUE:WIDTH S.state          # every address holding VALUE
  python kgba_ram.py unique "v1,v2,v3" WIDTH S1.state S2.state S3.state
        -> count addresses whose values across the states are exactly the given tuple
"""
from __future__ import annotations

import struct
import sys

STATE_SIZE = 0x61000
REGIONS = {                      # name: (gba_base_addr, file_offset, length)
    "IWRAM": (0x03000000, 0x19000, 0x8000),
    "EWRAM": (0x02000000, 0x21000, 0x40000),
}
_FMT = {"u8": ("<B", 1), "u16": ("<H", 2), "u32": ("<I", 4)}


def load(path: str) -> bytes:
    d = open(path, "rb").read()
    if len(d) != STATE_SIZE:
        raise ValueError(f"{path}: expected {STATE_SIZE} bytes, got {len(d)}")
    return d


def addr_to_off(addr: int) -> int:
    for base, off, length in REGIONS.values():
        if base <= addr < base + length:
            return off + (addr - base)
    raise ValueError(f"addr {addr:#x} is in neither swept region")


def iter_addrs(width: str):
    fmt, size = _FMT[width]
    for base, off, length in REGIONS.values():
        for i in range(0, length - size + 1, size):
            yield base + i, off + i


def read_at(data: bytes, addr: int, width: str) -> int:
    fmt, _ = _FMT[width]
    return struct.unpack_from(fmt, data, addr_to_off(addr))[0]


def cmd_diff(argv):
    width = "u8"
    delta = None
    args = []
    i = 0
    while i < len(argv):
        if argv[i] == "--width":
            width = argv[i + 1]; i += 2
        elif argv[i] == "--delta":
            delta = int(argv[i + 1]); i += 2
        else:
            args.append(argv[i]); i += 1
    a, b = load(args[0]), load(args[1])
    fmt, _ = _FMT[width]
    hits = []
    for addr, off in iter_addrs(width):
        va = struct.unpack_from(fmt, a, off)[0]
        vb = struct.unpack_from(fmt, b, off)[0]
        if va == vb:
            continue
        if delta is not None and (vb - va) != delta:
            continue
        hits.append((addr, va, vb))
    print(f"# {len(hits)} differing {width} slots"
          + (f" with delta {delta}" if delta is not None else ""))
    for addr, va, vb in hits[:400]:
        print(f"{addr:#010x} {va} -> {vb}")


def cmd_trace(argv):
    addr_s, width = argv[0].split(":")
    addr = int(addr_s, 0)
    for p in argv[1:]:
        print(f"{p}\t{read_at(load(p), addr, width)}")


def cmd_equals(argv):
    val_s, width = argv[0].split(":")
    val = int(val_s, 0)
    d = load(argv[1])
    fmt, _ = _FMT[width]
    hits = [addr for addr, off in iter_addrs(width) if struct.unpack_from(fmt, d, off)[0] == val]
    print(f"# {len(hits)} addresses hold {val} as {width}")
    for a in hits[:400]:
        print(f"{a:#010x}")


def cmd_unique(argv):
    want = [int(x, 0) for x in argv[0].split(",")]
    width = argv[1]
    states = [load(p) for p in argv[2:]]
    if len(states) != len(want):
        raise SystemExit("need one state per wanted value")
    fmt, _ = _FMT[width]
    hits = []
    for addr, off in iter_addrs(width):
        if all(struct.unpack_from(fmt, s, off)[0] == w for s, w in zip(states, want)):
            hits.append(addr)
    print(f"# {len(hits)} {width} addresses match the tuple {want}")
    for a in hits[:400]:
        region = "EWRAM" if a >= 0x02000000 and a < 0x02040000 else "IWRAM"
        print(f"{a:#010x} {region}")


def cmd_cands(argv):
    """cands WIDTH  g1a.state,g1b.state  g2a.state,g2b.state  [g3...]

    Keeps addresses that are CONSTANT inside every group and take a DISTINCT value in each group.
    Groups are "all the states where the answer should be the same" (e.g. several snapshots taken at
    different times/rooms inside stage 1-1), so within-group variation kills timers, camera/physics
    scratch, RNG and animation counters without any hand-picked whitelist."""
    width = argv[0]
    groups = [[load(p) for p in g.split(",")] for g in argv[1:]]
    fmt, _ = _FMT[width]
    hits = []
    for addr, off in iter_addrs(width):
        vals = []
        ok = True
        for g in groups:
            v0 = struct.unpack_from(fmt, g[0], off)[0]
            if any(struct.unpack_from(fmt, s, off)[0] != v0 for s in g[1:]):
                ok = False
                break
            vals.append(v0)
        if ok and len(set(vals)) == len(vals):
            hits.append((addr, vals))
    print(f"# {len(hits)} {width} addresses constant-within / distinct-across {len(groups)} groups")
    for addr, vals in hits[:600]:
        print(f"{addr:#010x} {vals}")


if __name__ == "__main__":
    {"diff": cmd_diff, "trace": cmd_trace, "equals": cmd_equals,
     "unique": cmd_unique, "cands": cmd_cands}[sys.argv[1]](sys.argv[2:])
