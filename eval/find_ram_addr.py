"""Auto RAM-address finder — discover which WRAM byte(s) hold the player/camera POSITION for a game with NO
published RAM map, from data we already record: ram.bin (8 KB WRAM/step) + buttons.jsonl. No game knowledge.

The position register is the byte whose per-step delta is CONSISTENTLY SIGNED with the pressed direction
(right -> one sign, left -> the other; down/up for Y). This is independent of best_shift, so a found address is a
clean TRUTH oracle for the ego-motion estimator (feed it to `record.py --watch`). Tests single bytes AND
little-endian 16-bit pairs (covers tile-coord / 8-bit-pixel / 16-bit-pixel encodings).

  uv run python -m eval.find_ram_addr runs/<run-with-ram.bin> [--max-steps 4000] [--top 6]
"""
from __future__ import annotations

import argparse
import json
import os

import numpy as np

WRAM0 = 0xC000
WRAM_LEN = 0x2000          # 8 KB dumped: 0xC000..0xDFFF
MIN_SAMPLES = 20
SINGLE_MAX = 40            # plausible single-step |delta| for an 8-bit position (excludes screen-wrap + noise)
PAIR_MAX = 400             # ... for a little-endian 16-bit position


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
    """values: (N, K) per-step register values; cause_sign: (N,) press sign. Per-K returns (consistency,
    n_samples, flipped): consistency = max(frac, 1-frac) of sign(delta)==press over clean single-step moves
    (1<=|delta|<=dmax) on pressed steps; flipped = the press DEcrEments the register."""
    d = values[1:] - values[:-1]                  # (N-1, K) delta caused by buttons[i]
    s = cause_sign[1:]                            # (N-1,) aligned cause
    m = s != 0
    d, s = d[m], s[m]
    valid = (np.abs(d) >= 1) & (np.abs(d) <= dmax)
    nval = valid.sum(0).astype(float)             # (K,)
    nmat = ((np.sign(d) == s[:, None]) & valid).sum(0).astype(float)
    with np.errstate(invalid="ignore", divide="ignore"):
        frac = np.where(nval >= MIN_SAMPLES, nmat / nval, np.nan)
    return np.maximum(frac, 1.0 - frac), nval, frac < 0.5


def _candidates(ram, sign):
    cons1, n1, flip1 = _score(ram.astype(np.int32), sign, SINGLE_MAX)
    pair = ram[:, :-1].astype(np.int32) + 256 * ram[:, 1:].astype(np.int32)   # little-endian u16, addr = low byte
    cons2, n2, flip2 = _score(pair, sign, PAIR_MAX)
    rng1 = ram.max(0).astype(int) - ram.min(0).astype(int)
    rng2 = pair.max(0) - pair.min(0)
    out = []
    for b in range(ram.shape[1]):
        if not np.isnan(cons1[b]):
            out.append((float(cons1[b]), WRAM0 + b, "u8", int(n1[b]), int(rng1[b]), bool(flip1[b])))
    for b in range(pair.shape[1]):
        if not np.isnan(cons2[b]):
            out.append((float(cons2[b]), WRAM0 + b, "u16", int(n2[b]), int(rng2[b]), bool(flip2[b])))
    out.sort(key=lambda c: (-c[0], -c[3], -c[4]))  # consistency, then EVIDENCE (n), then value-range -- all desc
    return out


def _report(name, ram, sign, top):
    cands = _candidates(ram, sign)
    print(f"\n  {name}  (top {top}; conv '+' = press increments the register, '-' = flipped)")
    print(f"    {'addr':8}{'type':5}{'consist':>9}{'n':>6}{'range':>9}  conv")
    seen, shown = set(), 0
    for cons, addr, typ, n, rng, flip in cands:
        if addr in seen:                           # a u16 low byte often echoes its u8 hit; show the addr once
            continue
        seen.add(addr)
        print(f"    0x{addr:04X}  {typ:5}{cons:>8.0%}{n:>6}{rng:>9}  {'-' if flip else '+'}")
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
    print("\n  -> pick the HIGH-consistency, HIGH-range candidate (range hi = world/camera register that "
          "accumulates; lo = screen-relative). Confirm: record.py --watch name=<addr>  (check it tracks movement).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
