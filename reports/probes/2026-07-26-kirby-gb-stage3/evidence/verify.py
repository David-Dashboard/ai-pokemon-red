"""Re-derive the EX02 stage-oracle verdict from the COMMITTED JSONL alone (no ram.bin, no ROM).

Backs `reports/2026-07-26-oracle-kirby-gb-stage3.md`: `0xD03B` (column c1) is Kirby's 0-indexed stage
counter; `0xD19F/0xD3A9/0xD3BA/0xD3CD` (c2..c5) are one-time "past Stage 1" latches.

    uv run python reports/probes/2026-07-26-kirby-gb-stage3/evidence/verify.py
"""
import json
import os

COLS = {"c1": "0xD03B", "c2": "0xD19F", "c3": "0xD3A9", "c4": "0xD3BA", "c5": "0xD3CD",
        "band": "0xD052"}
SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "human_stage3_oracle.jsonl")

rows = [json.loads(l) for l in open(SRC, encoding="utf-8")]
steps = [r["step"] for r in rows]
seg = [i for i in range(1, len(rows)) if steps[i] <= steps[i - 1]]
print(f"{len(rows)} rows | max step {max(steps)} | step-index restarts at row(s) {seg} "
      f"-> {len(seg) + 1} recording segment(s)")

for c, addr in COLS.items():
    v = [r["watch"][c] for r in rows]
    tr = [i for i in range(1, len(v)) if v[i] != v[i - 1]]
    print(f"  {c} = {addr}: values {sorted(set(v))}  transitions {len(tr)}  at rows {tr[:8]}"
          + (" ..." if len(tr) > 8 else ""))

c1 = [r["watch"]["c1"] for r in rows]
flip = c1.index(2)
latch = all(set(r["watch"][c] for r in rows) == {1} for c in ("c2", "c3", "c4", "c5"))
print(f"\nc1/0xD03B: 1 -> 2 once, at row {flip} (step {rows[flip]['step']}, "
      f"frame {rows[flip]['frame']}); {len(rows) - flip} rows observed with c1==2 (inside Stage 3)")
print(f"c2..c5: constant 1 over every row incl. that Stage-3 window: {latch}")
print("\nVERDICT: 0xD03B is the stage counter; the other four are 'past Stage 1' latches."
      if len(set(c1)) == 2 and latch else "\nVERDICT NOT REPRODUCED")
print("BOUND: the Stage-3 window is only the last "
      f"{len(rows) - flip} rows, and Stage 1 (value 0) is NOT in this file -- that anchor is PR #169's.")
