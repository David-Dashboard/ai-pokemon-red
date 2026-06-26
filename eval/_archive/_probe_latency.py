"""Throwaway: aggregate per-model latency from the vision-probe results."""
import json, statistics as st
from collections import defaultdict

rows = json.load(open("runs/vision_probe/results.json", encoding="utf-8"))
rows = [r for r in rows if not r["error"] and r["latency_s"] > 0]

def bucket(cond):
    return "4x" if cond.endswith("4x") else ("2x" if cond.endswith("2x") else "native")

by_model = defaultdict(list)
by_ms = defaultdict(list)
for r in rows:
    by_model[r["model"]].append(r["latency_s"])
    by_ms[(r["model"], bucket(r["condition"]))].append(r["latency_s"])

print("=== per model (all calls) ===")
for m, xs in sorted(by_model.items()):
    print(f"{m:10} n={len(xs):3}  mean={st.mean(xs):6.2f}s  median={st.median(xs):6.2f}s  "
          f"min={min(xs):5.2f}  max={max(xs):6.2f}")

print("\n=== per model x scale (mean s) ===")
for (m, s), xs in sorted(by_ms.items()):
    print(f"{m:10} {s:7} n={len(xs):3}  mean={st.mean(xs):6.2f}s")
