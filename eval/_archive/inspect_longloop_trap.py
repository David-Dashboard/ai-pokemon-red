"""Data-first inspection of the longloop run's Oak starter-dialog trap.

Reads runs/longloop/oracle.jsonl and answers the seen-states-signal design question:
at Oak's "which POKEMON?" prompt, is screen_text FROZEN or CYCLING, and how many
distinct (context, screen_text) states does the agent revisit while stuck?

Run: uv run python -m eval.inspect_longloop_trap
"""
import json
import sys
from collections import Counter
from pathlib import Path

ORACLE = Path("runs/longloop/oracle.jsonl")


def load(path):
    recs = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                recs.append(json.loads(line))
    return recs


def main():
    recs = load(ORACLE)
    print(f"total steps: {len(recs)}")

    # 1. Map trajectory: contiguous runs of map_id.
    print("\n=== MAP TRAJECTORY (contiguous runs) ===")
    runs = []
    for r in recs:
        m = r["map_id"]
        if not runs or runs[-1][0] != m:
            runs.append([m, r["step"], r["step"]])
        else:
            runs[-1][2] = r["step"]
    for m, a, b in runs:
        print(f"  map {m:>3}  steps {a:>4}..{b:<4} ({b - a + 1} steps)")

    # 2. Did it ever enter battle / get the starter?
    in_batt = [r["step"] for r in recs if r.get("in_battle")]
    print(f"\nin_battle steps: {len(in_batt)}" + (f"  first={in_batt[0]}" if in_batt else "  (NEVER)"))

    # 3. On the lab map (40), dump the (context, screen_text) sequence.
    lab = [r for r in recs if r["map_id"] == 40]
    print(f"\n=== MAP 40 (Oak's lab): {len(lab)} steps ===")
    print("step  x  y  inB  context        screen_text")
    prev_key = None
    transitions = []
    for r in lab:
        p = r["perceived"]
        txt = (p.get("screen_text") or "").replace("\n", "|")
        key = (p.get("context"), txt)
        mark = "" if key == prev_key else "  <-- state change"
        if key != prev_key:
            transitions.append((r["step"], key))
        prev_key = key
        print(f"{r['step']:>4} {r['x']:>2} {r['y']:>2} {r['in_battle']:>3}  "
              f"{str(p.get('context')):<14} {txt[:60]!r}{mark}")

    # 4. Distinct states on map 40 + revisit counts (the seen-states question).
    print("\n=== DISTINCT (context, screen_text) STATES on map 40 ===")
    counts = Counter((r["perceived"].get("context"),
                      (r["perceived"].get("screen_text") or "").replace("\n", "|"))
                     for r in lab)
    for (ctx, txt), n in counts.most_common():
        print(f"  x{n:<4} [{ctx}] {txt[:70]!r}")
    print(f"\n# distinct states: {len(counts)}   # state-change transitions: {len(transitions)}")

    # 5. REGRESSION CHECK: run the SHIPPED cycle-gate over the real run, EXACTLY as HybridBrain.decide()
    #    does — core.outcome.state_signature for the key, core.novelty.NoveltyMemory for visit-counting,
    #    core.brains._CYCLE_REVISITS for the threshold — and ASSERT every trip lands in the lab trap
    #    (map 40), never in Oak's legit intro monologue or the Pallet held-frame. This makes the real
    #    run a guard on the shipped code (the data proof in the plan). The oracle's `perceived` gives the
    #    same fields the perceiver feeds the brain (RAM is NOT used).
    from core.brains import _CYCLE_REVISITS
    from core.novelty import NoveltyMemory
    from core.outcome import state_signature

    print(f"\n=== SHIPPED-GATE REGRESSION over the real run (K=_CYCLE_REVISITS={_CYCLE_REVISITS}) ===")
    ADVANCEABLE = {"dialog", "battle_text"}
    nm = NoveltyMemory()
    trips = []
    for r in recs:
        p = r["perceived"]
        ctx = p.get("context")
        txt = (p.get("screen_text") or "").strip()
        data = {"context": ctx, "pose": {"value": p.get("pose"), "area": p.get("area")}}
        nkey = (state_signature(data), txt) if (ctx in ADVANCEABLE and txt) else None
        if nm.observe(nkey) >= _CYCLE_REVISITS and nkey is not None:
            trips.append((r["step"], r["map_id"], txt.replace("\n", "|")))
    for step, m, txt in trips:
        print(f"  trip @ step {step:>4} (map {m})  {txt[:42]!r}")
    bad = [t for t in trips if t[1] != 40]
    assert trips, "expected the gate to trip in the Oak-lab trap, but it NEVER tripped"
    assert not bad, f"FALSE POSITIVE — gate tripped OUTSIDE the lab trap (map != 40): {bad}"
    print(f"  PASS: {len(trips)} trip(s), ALL in the lab trap (map 40); first @ step {trips[0][0]} "
          f"(the trap ran uncaught to step {recs[-1]['step']}).")


if __name__ == "__main__":
    sys.exit(main())
