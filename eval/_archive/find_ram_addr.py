"""Auto RAM-address finder — discover which WRAM byte(s) hold the player/camera POSITION for a game with NO
published RAM map, from data we already record: ram.bin (8 KB WRAM/step) + buttons.jsonl. No game knowledge.

The position register is the byte whose per-step delta is CONSISTENTLY SIGNED with the pressed direction
(right -> one sign, left -> the other; down/up for Y). Independent of best_shift, so a found address is a clean
TRUTH oracle for the ego-motion estimator (feed it to `record.py --watch`). Tests single bytes AND little-endian
16-bit pairs.

GHOST CAVEAT: an 8-bit register at addr X also shows up in the HIGH byte of the u16 anchored at X-1 (every move
= +-256). Those composites are excluded by PAIR_MAX (<256) and out-ranked by preferring the clean u8 -- so the
guidance points at the real single byte, not a ghost. Confirm any pick with `record.py --watch`.

  uv run python -m eval.find_ram_addr runs/<run-with-ram.bin> [--max-steps 4000] [--top 6]
"""
from __future__ import annotations

import argparse
import json
import os
import warnings

import numpy as np

WRAM0 = 0xC000
WRAM_LEN = 0x2000          # 8 KB dumped: 0xC000..0xDFFF
MIN_SAMPLES = 20
SINGLE_MAX = 40            # plausible single-step |delta| for an 8-bit position (excludes screen-wrap + noise)
PAIR_MAX = 120             # a REAL 16-bit position moves in small steps; |delta|>=256 is an 8-bit ghost -> excluded


def _axis_sign(rows, pos, neg):
    """+1 if only `pos` pressed this step, -1 if only `neg`, else 0. buttons[i] caused transition i-1 -> i."""
    s = np.zeros(len(rows), dtype=np.int8)
    for i, r in enumerate(rows):
        b = set(r.get("buttons") or [])
        if pos in b and neg not in b:
            s[i] = 1
        elif neg in b and pos not in b:
            s[i] = -1
    return s


def _score(values, cause_sign, dmax):
    """Per-column (consistency, n, flipped, median|delta|) over clean single-step moves (1<=|d|<=dmax) on pressed
    steps. consistency = max(frac, 1-frac) of sign(delta)==press; med|delta| discriminates a real position
    (small steps) from a high-byte ghost (~256)."""
    d = values[1:] - values[:-1]                  # (N-1, K) delta caused by buttons[i]
    s = cause_sign[1:]
    m = s != 0
    d, s = d[m], s[m]
    valid = (np.abs(d) >= 1) & (np.abs(d) <= dmax)
    nval = valid.sum(0).astype(float)
    nmat = ((np.sign(d) == s[:, None]) & valid).sum(0).astype(float)
    absd = np.where(valid, np.abs(d), np.nan).astype(float)
    with np.errstate(invalid="ignore", divide="ignore"), warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)     # all-NaN columns -> nan median, filtered out below
        frac = np.where(nval >= MIN_SAMPLES, nmat / nval, np.nan)
        mdl = np.nanmedian(absd, axis=0)
    return np.maximum(frac, 1.0 - frac), nval, frac < 0.5, mdl


def _candidates(ram, sign):
    c1, n1, f1, m1 = _score(ram.astype(np.int32), sign, SINGLE_MAX)
    pair = ram[:, :-1].astype(np.int32) + 256 * ram[:, 1:].astype(np.int32)   # little-endian u16; addr = low byte
    c2, n2, f2, m2 = _score(pair, sign, PAIR_MAX)
    r1 = ram.max(0).astype(int) - ram.min(0).astype(int)
    r2 = pair.max(0) - pair.min(0)
    out = []   # (consistency, type_rank, addr, type, n, med|d|, range, flipped)
    for b in range(ram.shape[1]):
        if not np.isnan(c1[b]):
            out.append((float(c1[b]), 0, WRAM0 + b, "u8", int(n1[b]), float(m1[b]), int(r1[b]), bool(f1[b])))
    for b in range(pair.shape[1]):
        if not np.isnan(c2[b]):
            out.append((float(c2[b]), 1, WRAM0 + b, "u16", int(n2[b]), float(m2[b]), int(r2[b]), bool(f2[b])))
    out.sort(key=lambda c: (-c[0], c[1], -c[4]))   # consistency desc, u8 BEFORE u16, then evidence (n) desc
    return out


def _report(name, ram, sign, top):
    cands = _candidates(ram, sign)
    print(f"\n  {name}  (top {top}; conv '+' = press increments register, '-' = flipped)")
    print(f"    {'addr':8}{'type':5}{'consist':>9}{'n':>6}{'med|d|':>8}{'range':>9}  conv")
    seen, shown = set(), 0
    for cons, _tr, addr, typ, n, mdl, rng, flip in cands:
        if addr in seen:        # u8 ranks before its u16 echo at the same low addr -> the clean u8 is what shows
            continue
        seen.add(addr)
        print(f"    0x{addr:04X}  {typ:5}{cons:>8.0%}{n:>6}{mdl:>8.0f}{rng:>9}  {'-' if flip else '+'}")
        shown += 1
        if shown >= top:
            break


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("run", help="run dir with ram.bin + buttons.jsonl")
    ap.add_argument("--max-steps", type=int, default=4000, help="cap steps analysed (bounds memory)")
    ap.add_argument("--top", type=int, default=6)
    args = ap.parse_args()

    rows = [json.loads(line) for line in open(os.path.join(args.run, "buttons.jsonl"), encoding="utf-8")]
    ram = np.fromfile(os.path.join(args.run, "ram.bin"), dtype=np.uint8)
    n = min(ram.size // WRAM_LEN, len(rows), args.max_steps)
    if n < MIN_SAMPLES + 1:
        print(f"too few steps with ram.bin ({n})")
        return 1
    ram = ram[: n * WRAM_LEN].reshape(n, WRAM_LEN)
    rows = rows[:n]
    print(f"{args.run}: {n} steps x {WRAM_LEN} WRAM bytes (0x{WRAM0:04X}..0x{WRAM0 + WRAM_LEN - 1:04X})")

    _report("X axis (right/left)", ram, _axis_sign(rows, "right", "left"), args.top)
    _report("Y axis (down/up)", ram, _axis_sign(rows, "down", "up"), args.top)
    print("\n  -> prefer a u8 with HIGH consist + n and SMALL med|d| (a real position moves in small steps; a u16")
    print("     with med|d|~256 is an 8-bit ghost in the high byte). Confirm: record.py --watch name=<addr>")
    print("     -- for a genuine u16 position, --watch BOTH bytes (addr and addr+1) and combine offline.")
    print("     CAVEAT: on GBC (.gbc), 0xD000-0xDFFF is BANK-SWITCHED -> an address there can alias across steps")
    print("     (depressing its consistency); prefer DMG titles or addresses in the fixed 0xC000-0xCFFF half.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
