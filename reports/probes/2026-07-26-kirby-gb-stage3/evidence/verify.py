"""Re-derive the EX02 stage-oracle verdict from the COMMITTED logs alone (no ROM, no savestate).

Backs `reports/2026-07-26-oracle-kirby-gb-stage3.md`: `0xD03B` is Kirby's 0-indexed stage index;
`0xD19F/0xD3A9/0xD3BA/0xD3CD` are stale "past Stage 1" latches that do not track the current stage.

    uv run python reports/probes/2026-07-26-kirby-gb-stage3/evidence/verify.py
"""
import json
import os

D = os.path.dirname(os.path.abspath(__file__))
COLS = {"c1": "0xD03B", "c2": "0xD19F", "c3": "0xD3A9", "c4": "0xD3BA", "c5": "0xD3CD",
        "band": "0xD052"}
ELIM = ["D19F", "D3A9", "D3BA", "D3CD"]
load = lambda f: [json.loads(l) for l in open(os.path.join(D, f), encoding="utf-8")]
setof = lambda rows, k: sorted({r[k] for r in rows})
trans = lambda rows, k: [i for i in range(1, len(rows)) if rows[i][k] != rows[i - 1][k]]

print("== A. human run (2026-07-28), sampled oracle rows ==")
rows = load("human_stage3_oracle.jsonl")
steps = [r["step"] for r in rows]
seg = [i for i in range(1, len(rows)) if steps[i] <= steps[i - 1]]
print(f"{len(rows)} rows | max step {max(steps)} | step index restarts at {seg} -> {len(seg)+1} segments")
for c, addr in COLS.items():
    v = [r["watch"][c] for r in rows]
    t = [i for i in range(1, len(v)) if v[i] != v[i - 1]]
    print(f"  {c} = {addr}: values {sorted(set(v))}  transitions {len(t)}  at rows {t[:8]}")
flip = [r["watch"]["c1"] for r in rows].index(2)
print(f"  -> c1 flips 1->2 once at row {flip} (step {rows[flip]['step']}); {len(rows)-flip} rows "
      f"follow. Boss kill at row 1018 [NOT derivable here: read off run frames], so flip is 64 later.")

print("\n== B. sustained live play per stage (test1b, 300 samples / 9,000 frames each) ==")
for tag, stage in (("v0", "Green Greens"), ("v2", "Float Islands"), ("v3", "Bubbly Clouds")):
    r = load(f"test1b_{tag}.jsonl")
    print(f"  {stage:14s} D03B={setof(r,'D03B')} ({len(trans(r,'D03B'))} transitions) | "
          f"latches={[setof(r,e) for e in ELIM]} | liveness: x takes "
          f"{len(setof(r,'x'))} values, hp {setof(r,'hp')}, lives {setof(r,'lives')}")
print("  -> v0 is the REVERSE DISSOCIATION: D03B=0 (Green Greens) while all four latches read 1.")
print("  -> v3's single transition in every column is the title-screen reset after lives ran out.")
print("\nVERDICT: 0xD03B tracks the current stage; the four latches do not. The causal leg (writing")
print("0/1/2/3/4 selects which stage loads) is in causal_map.png -- reproducing that needs the ROM.")
