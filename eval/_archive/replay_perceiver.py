"""Phase B validation: replay run #4's REAL frames through the NEW perceiver (translation odometry +
place-graph) and check it no longer LUMPS distinct maps into one occupancy area. Run #4's OLD perceiver
put RAM maps {0, 39} (Pallet + the rival's house) into one corrupt area 2; the fix should keep them
apart. RAM map_id is the oracle LABEL only; the perceiver sees pixels + the recorded action — and NO
fade flag (run #4 predates it), so this is the translation signal ALONE, i.e. a lower bound.

Run: uv run python -m eval.replay_perceiver
"""
from __future__ import annotations

import json
import os
from collections import defaultdict

import numpy as np

try:
    import imageio.v2 as iio
except Exception:
    import imageio as iio

from core.perception import PerceptMemory
from games.pokemon_red.perceiver import OverworldPerceiver

ORACLE = "runs/run4/oracle.jsonl"


def main() -> int:
    rows = [json.loads(l) for l in open(ORACLE, encoding="utf-8")]
    per, mem = OverworldPerceiver(), PerceptMemory()
    map_to_places, place_to_maps = defaultdict(set), defaultdict(set)
    transitions, prev_place = 0, None

    for r in rows:
        p = (r.get("screen_path") or "").replace("\\", "/")
        if not (p and os.path.exists(p)):
            continue
        frame = np.asarray(iio.imread(p))
        act = (r.get("perceived") or {}).get("action")
        s = per.perceive(frame, mem, {"last_action": act, "frame_path": p})
        place = s.pose["area"]
        map_to_places[r.get("map_id")].add(place)
        place_to_maps[place].add(r.get("map_id"))
        if prev_place is not None and place != prev_place:
            transitions += 1
        prev_place = place

    print("=== NEW perceiver replay of run #4 (translation-only; no fade flag = lower bound) ===")
    print("RAM map_id -> perceiver places it was assigned:")
    for k in sorted(map_to_places, key=lambda x: (x is None, x)):
        print(f"  map {k}: places {sorted(map_to_places[k])}")
    print("perceiver place -> distinct RAM maps lumped into it (want 1 each => NO lumping):")
    lumped = 0
    for k in sorted(place_to_maps):
        ms = sorted(m for m in place_to_maps[k] if m is not None)
        if len(set(ms)) > 1:
            lumped += 1
        print(f"  place {k}: maps {ms}")
    minted = max(place_to_maps) + 1 if place_to_maps else 0
    print(f"\nplaces minted: {minted}  perceiver-transitions: {transitions}  "
          f"places lumping >1 RAM map: {lumped}")
    print("(run #4 OLD result: ONE area lumped RAM maps {0, 39}; want 0 lumped now)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
