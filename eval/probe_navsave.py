"""Task #8 measure-before-build (free, online replay): if the autopilot SKIPPED tiles the tile->function
map predicts BLOCKED (instead of bumping them to discover they're walls), how many bump-steps would it
SAVE, and how many real paths would it WRONGLY skip? Quantifies the navigation speedup + sets the
abstain dial (min_conf / skip_flat) BEFORE any ExploreBrain change.

Causal online replay, per run (the agent starts blank each run — learning-boundary): for each overworld
move, PREDICT the faced tile from the map built SO FAR, then observe the real outcome. Tally:
  avoidable-bump : predicted blocked & actually blocked  -> a bump the autopilot could have skipped (SAVED)
  harmful-skip   : predicted blocked & actually walkable  -> a real path it would have wrongly avoided (COST)
  (confirmed / unavoidable-bump / abstained = no behaviour change vs today)
across abstain settings. RAM is the oracle (labels only); no live RAM to the map.
    uv run python -m eval.probe_navsave
"""
from __future__ import annotations
import json, os, sys
from collections import Counter
import numpy as np
from PIL import Image
from core.tilemap import TileFunctionMap
from eval.probe_tilemap import OFF, PLAYER, CELL, dir_of, label_of

RUNS = sys.argv[1:] or ["runs/kanto1", "runs/race1", "runs/race2", "runs/race3", "runs/fix1",
                        "runs/fix2", "runs/fix4", "runs/fix5", "runs/novelty_val", "runs/novelty_val3"]
SETTINGS = {"default": {}, "min_conf=0.9": {"min_conf": 0.9},
            "skip_flat": {"skip_flat": True}, "skip_flat+min_conf=0.9": {"skip_flat": True, "min_conf": 0.9}}


def faced_tiles(run):
    """Chronological (fp, actual_label) faced-tile stream for one run's overworld moves."""
    op = os.path.join(run, "oracle.jsonl")
    if not os.path.exists(op):
        return
    rows = [json.loads(l) for l in open(op, encoding="utf-8")]
    for i in range(1, len(rows)):
        cur, prev = rows[i], rows[i - 1]
        p = cur.get("perceived", {})
        if p.get("context") != "overworld" or cur.get("in_battle"):
            continue
        d, lab = dir_of(p.get("action")), label_of(p.get("outcome"))
        if d is None or lab is None:
            continue
        fpath = os.path.join(run, f"frame_{prev['step']:06d}.png")
        if not os.path.exists(fpath):
            continue
        cx, cy = PLAYER[0] + OFF[d][0], PLAYER[1] + OFF[d][1]
        img = np.asarray(Image.open(fpath).convert("RGB"))
        tile = img[cy * CELL:(cy + 1) * CELL, cx * CELL:(cx + 1) * CELL]
        if tile.shape[:2] != (CELL, CELL):
            continue
        yield TileFunctionMap.fingerprint(tile), lab


def main():
    streams = {run: list(faced_tiles(run)) for run in RUNS}
    total_moves = sum(len(s) for s in streams.values())
    total_bumps = sum(sum(1 for _, lab in s if lab == "blocked") for s in streams.values())
    print(f"runs={len(RUNS)}  overworld moves={total_moves}  of which real bumps(blocked)={total_bumps}")
    print(f"\n{'setting':24} {'SAVED bumps':>12} {'HARMFUL skips':>14} {'save-rate':>10} {'harm-rate':>10}")
    for name, kw in SETTINGS.items():
        saved = harmful = 0
        for run, stream in streams.items():
            tmap = TileFunctionMap()                       # blank per run
            for fp, lab in stream:
                pred = tmap.predict(fp, **kw)
                if pred is not None and pred[0] == "blocked":
                    if lab == "blocked":
                        saved += 1
                    else:
                        harmful += 1
                tmap.observe(fp, lab)
        sr = saved / total_bumps if total_bumps else 0.0       # fraction of bumps the autopilot avoids
        hr = harmful / total_moves if total_moves else 0.0     # fraction of all moves wrongly skipped
        print(f"{name:24} {saved:>12} {harmful:>14} {sr:>9.1%} {hr:>9.2%}")
    print("\nSAVED = bumps avoided (steps saved); HARMFUL = real paths wrongly skipped (the cost the "
          "behavioural veto must catch). Pick the dial that maximises SAVED while keeping HARMFUL ~0.")


if __name__ == "__main__":
    main()
