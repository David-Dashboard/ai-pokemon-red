"""End-to-end check: replay a recorded run's REAL frames through the WIRED OverworldPerceiver and
verify the tile->function map (a) builds online, (b) recognises more / flags fewer-novel cells as it
learns (the recurrence curve), and (c) its ADVISORY predictions agree with what the agent LATER
confirmed BEHAVIOURALLY in the same run. Unlike eval/probe_tilemap.py (which tests the algorithm on
re-cropped tiles), this drives the production perceive() path exactly as a live run does.

RAM map_id is never fed to the perceiver; behavioural ground truth comes from the perceiver's OWN
occupancy map (visited => walkable; a cell a neighbour bumped into => blocked). Free, deterministic.

    uv run python -m eval.replay_tilemap [runs/fix4 ...]
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
from games.pokemon_red.perceiver import OverworldPerceiver

RUN_DIRS = sys.argv[1:] or ["runs/fix4"]
_DELTA = {"up": (0, -1), "down": (0, 1), "left": (-1, 0), "right": (1, 0)}


def _frame_path(run, r):
    p = (r.get("screen_path") or "").replace("\\", "/")
    if p and os.path.exists(p):
        return p
    cand = os.path.join(run, f"frame_{r['step']:06d}.png")
    return cand if os.path.exists(cand) else None


def main() -> int:
    first_pred: dict = {}        # (area, (x,y)) -> earliest advisory function (ALL visible cells)
    first_pred_adj: dict = {}    # same, but only cells ADJACENT to the player (clean, centred crops)
    curve = []                   # per overworld frame: (tile_types_seen, n_pred, n_novel)
    per, mem = OverworldPerceiver(), PerceptMemory()

    for run in RUN_DIRS:
        opath = os.path.join(run, "oracle.jsonl")
        if not os.path.exists(opath):
            print(f"(skip {run}: no oracle.jsonl)")
            continue
        for r in (json.loads(l) for l in open(opath, encoding="utf-8")):
            fp = _frame_path(run, r)
            if not fp:
                continue
            frame = np.asarray(iio.imread(fp))
            act = (r.get("perceived") or {}).get("action")
            s = per.perceive(frame, mem, {"last_action": act, "frame_path": fp})
            sm = s.spatial_memory or {}
            if sm.get("kind") != "occupancy-grid" or "tile_predictions" not in sm:
                continue                                      # non-overworld frame: no advisory layer
            area = s.pose["area"]
            px, py = s.pose["value"]
            for wx, wy, fn, _conf in sm.get("tile_predictions", []):
                first_pred.setdefault((area, (wx, wy)), fn)   # remember the FIRST time we predicted it
                if abs(wx - px) + abs(wy - py) == 1:          # a 4-neighbour = a clean, faced-tile crop
                    first_pred_adj.setdefault((area, (wx, wy)), fn)
            curve.append((sm["tile_types_seen"], len(sm["tile_predictions"]), len(sm["novel_tiles"])))

    if not curve:
        print("no overworld frames replayed (need a recorded run with frames). no-op.")
        return 0

    # behavioural ground truth from the FINAL occupancy map (the perceiver's own, no RAM)
    truth: dict = {}
    for area, cells in mem.data["places"].items():
        for (x, y), c in cells.items():
            if c.get("visited"):
                truth[(area, (x, y))] = "walkable"
        for (x, y), c in cells.items():                        # a bumped neighbour => that tile is blocked
            for d in c.get("walls", ()):
                dx, dy = _DELTA[d]
                nb = (area, (x + dx, y + dy))
                truth.setdefault(nb, "blocked")                # don't override a confirmed 'walkable'

    # advisory-vs-behaviour: where we predicted a cell AND later confirmed it, did we agree?
    checked = [(first_pred[k], truth[k]) for k in first_pred if k in truth]
    agree = sum(p == t for p, t in checked)
    checked_adj = [(first_pred_adj[k], truth[k]) for k in first_pred_adj if k in truth]
    agree_adj = sum(p == t for p, t in checked_adj)

    n = len(curve)
    early = curve[: n // 3] or curve
    late = curve[-n // 3:] or curve
    avg = lambda rows, i: sum(r[i] for r in rows) / len(rows)

    print(f"=== replay {RUN_DIRS}: WIRED perceiver tile->function map ===")
    print(f"overworld frames replayed: {n}")
    print(f"distinct tile-types learned (final): {curve[-1][0]}")
    print("\nrecurrence curve (per-frame avg):")
    print(f"  early third: predictions {avg(early,1):.1f}/frame   novel {avg(early,2):.1f}/frame")
    print(f"  late  third: predictions {avg(late,1):.1f}/frame   novel {avg(late,2):.1f}/frame")
    print("  (predictions should RISE and novel should FALL as the agent recognises its surroundings)")
    print(f"\nadvisory vs later-confirmed behaviour:")
    print(f"  ALL visible cells:  {agree}/{len(checked)} = "
          f"{(agree/len(checked)*100) if checked else float('nan'):.1f}% agree "
          f"(noisy: peripheral/edge crops + off-centre frames where player != (4,4))")
    print(f"  ADJACENT cells only: {agree_adj}/{len(checked_adj)} = "
          f"{(agree_adj/len(checked_adj)*100) if checked_adj else float('nan'):.1f}% agree "
          f"(clean faced-tile crops -- should track the probe's ~92% faced-tile accuracy)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
