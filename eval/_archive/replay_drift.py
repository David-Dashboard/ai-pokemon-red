"""Validate the interior-navigation DRIFT fix on REAL frames (free, no API): replay a recorded run's
frames through the perceiver and compare its dead-reckoned pose DELTA to the RAM ground-truth delta,
step by step, within each same-map segment. The run-#15 perceiver capped every move at one tile, so a
2-tile [d,d] move drifted ~1 tile per same-direction step (measured: 40% of moves mismatched). With
measured-distance odometry the pose delta should match RAM almost everywhere.

RAM x/y is the oracle ground truth (never an agent input); the perceiver sees only pixels + the
recorded action. The recorded run predates the fade flag in the log, so transitions here ride the
translation signal alone (a lower bound) — we only score WITHIN-segment moves, where it doesn't matter.

Run: uv run python -m eval.replay_drift [runs/run15]
"""
from __future__ import annotations

import json
import os
import sys

import numpy as np

try:
    import imageio.v2 as iio
except Exception:
    import imageio as iio

from core.perception import PerceptMemory
from games.pokemon_red.perceiver import _SHIFT_RANGE, _TILE_PX, OverworldPerceiver

RUN = sys.argv[1] if len(sys.argv) > 1 else "runs/run15"


def main() -> int:
    rows = [json.loads(l) for l in open(os.path.join(RUN, "oracle.jsonl"), encoding="utf-8")]
    per, mem = OverworldPerceiver(), PerceptMemory()
    _AXES = {"up", "down", "left", "right"}
    prev = None
    total = mismatch = twotile = 0
    cap_bug = missed = multiaxis = beyond = 0   # categorize the residual
    examples = []
    for r in rows:
        p = (r.get("screen_path") or "").replace("\\", "/")
        if not (p and os.path.exists(p)):
            continue
        frame = np.asarray(iio.imread(p))
        act = (r.get("perceived") or {}).get("action")
        s = per.perceive(frame, mem, {"last_action": act, "frame_path": p})
        if s.context != "overworld":
            prev = None
            continue
        cur = dict(m=r["map_id"], rx=r["x"], ry=r["y"],
                   px=s.pose["value"][0], py=s.pose["value"][1], area=s.pose["area"],
                   act=act, out=s.last_action["outcome"], step=r["step"])
        if prev is not None and prev["m"] == cur["m"] and prev["area"] == cur["area"]:
            ram_d = (cur["rx"] - prev["rx"], cur["ry"] - prev["ry"])
            per_d = (cur["px"] - prev["px"], cur["py"] - prev["py"])
            total += 1
            if abs(ram_d[0]) + abs(ram_d[1]) >= 2:
                twotile += 1
            if ram_d != per_d:
                mismatch += 1
                # Categorize: the CAP BUG is a same-axis move the perceiver DETECTED ('moved') but
                # counted the wrong distance — that's what this fix targets. The other two are
                # pre-existing/inherent and out of scope: a MISS (perceiver saw no move — a re-baseline
                # frame right after a menu, by design) and a MULTI-AXIS LLM press (e.g. right+right+down)
                # that single-axis odometry can only approximate.
                axis_tokens = {t for t in str(cur["act"] or "").replace("+", " ").split() if t in _AXES}
                if len(axis_tokens) > 1 or (ram_d[0] and ram_d[1]):
                    multiaxis += 1
                elif per_d == (0, 0):
                    missed += 1
                elif abs(ram_d[0]) + abs(ram_d[1]) > _SHIFT_RANGE // _TILE_PX:
                    beyond += 1   # real move exceeded the +/-4-tile search window (clamped, by design)
                else:
                    cap_bug += 1
                    if len(examples) < 12:
                        examples.append((cur["step"], cur["act"], "RAM", ram_d, "PER", per_d))
        prev = cur

    pct = 100 * mismatch / max(1, total)
    print(f"=== drift replay: {RUN} through the PATCHED perceiver (measured-distance odometry) ===")
    print(f"same-segment move pairs = {total}")
    print(f"total delta mismatches = {mismatch} ({pct:.1f}%)  "
          f"[RAM moved >=2 tiles on {twotile} of all pairs]")
    print(f"\nBASELINE (run #15 as recorded, cap-at-one perceiver): 144/358 = 40.2% mismatched.")
    print("residual, by cause:")
    print(f"  CAP-BUG (detected move, wrong distance — THIS FIX'S TARGET): {cap_bug}")
    print(f"  miss (no move detected; re-baseline after a menu — pre-existing): {missed}")
    print(f"  multi-axis LLM press (single-axis odometry approximation — out of scope): {multiaxis}")
    print(f"  beyond the +/-4-tile search window (multi-press move >4 tiles — clamped): {beyond}")
    if examples:
        print("remaining cap-bug examples:")
        for e in examples:
            print("  ", e)
    ok = cap_bug == 0
    print("\nVERDICT:", "PASS — the cap-at-one drift is eliminated (residual is pre-existing/inherent)"
          if ok else f"FAIL — {cap_bug} cap-bug mismatches remain")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
