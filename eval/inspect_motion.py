"""Data-first probe for MOTION-SALIENCY (free NPC detector): when the camera is STATIC (the player
didn't move/scroll — a blocked move or an A-press), any pixel region that still CHANGES between two
consecutive frames is a moving entity (an idle-animating NPC). The overworld camera centers the
player, so a changing region away from the screen centre = an NPC at a known world offset.

This probe asks the prerequisite question BEFORE we wire anything: on real frames, does an NPC's idle
animation actually produce a detectable, localized off-centre change when the camera is still? It
replays a recorded run, finds camera-static frame pairs (perceiver outcome 'blocked'), computes the
per-16px-tile abs-diff, and reports where the change is (centre = the player's own bump animation;
off-centre = a candidate NPC). RAM is read only to label which map we're on (oracle role).

Run: uv run python -m eval.inspect_motion [runs/run16]
"""
from __future__ import annotations

import json
import os
import sys
from collections import Counter

import numpy as np

try:
    import imageio.v2 as iio
except Exception:
    import imageio as iio

RUN = sys.argv[1] if len(sys.argv) > 1 else "runs/run16"


def main() -> int:
    from collections import defaultdict

    from games.pokemon_red.saliency import motion_rois

    rows = [json.loads(l) for l in open(os.path.join(RUN, "oracle.jsonl"), encoding="utf-8")]
    # per map: [camera-static pairs, FILTERED ROI events (small clusters), total ROIs]
    per_map = defaultdict(lambda: [0, 0, 0])
    examples = defaultdict(list)
    prevpath = None
    for r in rows:
        p = (r.get("screen_path") or "").replace("\\", "/")
        out = (r.get("perceived") or {}).get("outcome")
        # camera-static iff the move was BLOCKED (no scroll) and we have the prior frame
        if out == "blocked" and prevpath and os.path.exists(prevpath) and os.path.exists(p):
            rois = motion_rois(iio.imread(prevpath), iio.imread(p))   # cluster-FILTERED (terrain dropped)
            m = r["map_id"]
            per_map[m][0] += 1
            if rois:
                per_map[m][1] += 1
                per_map[m][2] += len(rois)
                if len(examples[m]) < 5:
                    examples[m].append((r["step"], rois))
        prevpath = p

    print(f"=== motion-saliency (cluster-filtered) probe: {RUN} ===")
    print("per map: [blocked pairs | NPC-ROI events | total ROIs]")
    for m in sorted(per_map):
        sp, ev, tot = per_map[m]
        tag = "  <- indoor: any motion = NPC" if m == 40 else ("  <- animated water (should be filtered)" if m == 0 else "")
        print(f"  map {m}: [{sp:>3} | {ev:>3} | {tot:>3}]{tag}")
    print("\nexamples by map (step, ROI screen tiles [tx,ty]):")
    for m in sorted(examples):
        for e in examples[m]:
            print(f"  map {m}: {e}")
    print("\nread: the cluster filter should KEEP the lab's NPC hits (map 40) and REJECT Pallet's water")
    print("(map 0 large clusters dropped). Compare to the raw counts in git history (map 0 had 35 events).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
