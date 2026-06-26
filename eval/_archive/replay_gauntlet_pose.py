"""Offline pose check for GauntletPerceiver (measure-first, before any live run). Replays the recorded
`2026-06-23_gauntlet_ramplay` frames + human buttons through GauntletPerceiver and scores its emitted
`pose.value` trajectory against the RAM oracle (`x=0xC286,y=0xC2C6`) -- the SAME drift methodology as
eval/probe_pose_drift.py, but through the PACKAGED perceiver (not the raw recipe). Confirms the perceiver
reproduces the gate (drift ~0.02, net-heading high). Pixels in, RAM only as the never-leaked oracle.

  uv run python -m eval.replay_gauntlet_pose
"""
from __future__ import annotations

import json
import os

import numpy as np
from PIL import Image

from core.perception import PerceptMemory
from eval.probe_pose_drift import WINDOWS, _net_dir_agreement, _wrapb
from games.gauntlet.perceiver import GauntletPerceiver

RUN = "2026-06-23_gauntlet_ramplay"


def main():
    btn = [json.loads(l) for l in open(os.path.join("runs", RUN, "buttons.jsonl"), encoding="utf-8")]
    ora = {r["step"]: r["watch"] for r in
           (json.loads(l) for l in open(os.path.join("runs", RUN, "oracle.jsonl"), encoding="utf-8"))}
    perc, mem = GauntletPerceiver(), PerceptMemory()
    ego_xy, ram_xy = [], []
    for row in btn:
        step = row["step"]
        if step not in ora:
            continue
        fp = os.path.join("runs", RUN, os.path.basename(row["screen_path"].replace("\\", "/")))
        if not os.path.exists(fp):
            continue
        frame = np.asarray(Image.open(fp).convert("RGB"))
        action = "+".join(row.get("buttons", []))   # the action that produced THIS frame (recorder order)
        sym = perc.perceive(frame, mem, {"frame_path": fp, "last_action": action})
        ego_xy.append(tuple(sym.pose["value"]))
        ram_xy.append((ora[step]["x"], ora[step]["y"]))

    ego = np.array(ego_xy, float)
    ram = np.array(ram_xy, float)
    egod = np.diff(ego, axis=0)
    orad = np.array([(_wrapb(int(dx)), _wrapb(int(dy))) for dx, dy in np.diff(ram, axis=0)], float)

    print(f"=== GauntletPerceiver offline pose vs RAM oracle ({RUN}, n={len(ego)}) ===")
    cells = []
    for W in WINDOWS:
        ok, tot = _net_dir_agreement(orad, egod, W)
        cells.append(f"W={W}:{ok}/{tot}={ok / tot:.0%}" if tot else f"W={W}:-")
    print("  net-dir (perceiver pose vs oracle): " + "   ".join(cells))
    mags = np.hypot(orad[:, 0], orad[:, 1])
    k = np.median(mags[mags > 0]) if np.any(mags > 0) else 1.0
    egopos = np.cumsum(egod, 0) * k
    orapos = np.cumsum(orad, 0)
    err = np.hypot(*(egopos - orapos).T)
    path = np.cumsum(mags)
    drr = "  ".join(f"{int(f*100)}%:{err[int((len(err)-1)*f)] / max(path[int((len(path)-1)*f)], 1):.2f}"
                    for f in (0.25, 0.5, 0.75, 1.0))
    print(f"  drift err/path (perceiver pose, k={k:.1f}px/cell): {drr}")
    print("  PASS if net-dir stays high/flat and drift stays low (in line with the gate: ~87% / ~0.02).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
