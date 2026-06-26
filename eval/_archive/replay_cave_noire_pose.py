"""Offline pose check for CaveNoirePerceiver (measure-first, before any live run). Replays the
`2026-06-23_cavenoire_explore` frames + buttons through the perceiver and scores its emitted `pose.value`
trajectory against the RAM oracle (x=0xC504, y=0xC503, found by eval/find_ram_addr). Cave Noire is a FIXED
camera, so this validates the FOREGROUND-motion move signal (not best_shift). Same drift methodology as
eval/replay_gauntlet_pose. RAM is the oracle, never an input.

  uv run python -m eval.replay_cave_noire_pose
"""
from __future__ import annotations

import json
import os

import numpy as np
from PIL import Image

from core.perception import PerceptMemory
from eval.probe_pose_drift import WINDOWS, _drift_segmented, _net_dir_agreement, _wrapb
from games.cave_noire.perceiver import CaveNoirePerceiver

RUN = "runs/2026-06-23_cavenoire_explore"
AX, AY = 0x504, 0x503   # ram.bin column offsets for 0xC504 / 0xC503


def main():
    ram = np.fromfile(os.path.join(RUN, "ram.bin"), dtype=np.uint8)
    n = ram.size // 8192
    ram = ram[:n * 8192].reshape(n, 8192)
    btn = [json.loads(l) for l in open(os.path.join(RUN, "buttons.jsonl"), encoding="utf-8")][:n]
    perc, mem = CaveNoirePerceiver(), PerceptMemory()
    ego_xy, ram_xy = [], []
    for i, row in enumerate(btn):
        fp = os.path.join(RUN, f"frame_{i:06d}.png")
        if not os.path.exists(fp):
            continue
        frame = np.asarray(Image.open(fp).convert("RGB"))
        action = "+".join(row.get("buttons", []))
        sym = perc.perceive(frame, mem, {"frame_path": fp, "last_action": action})
        ego_xy.append(tuple(sym.pose["value"]))
        ram_xy.append((int(ram[i, AX]), int(ram[i, AY])))

    ego = np.array(ego_xy, float)
    ram_p = np.array(ram_xy, float)
    egod = np.diff(ego, axis=0)
    orad = np.array([(_wrapb(int(dx)), _wrapb(int(dy))) for dx, dy in np.diff(ram_p, axis=0)], float)

    print(f"=== CaveNoirePerceiver offline pose vs RAM oracle ({RUN}, n={len(ego)}) ===")
    cells = []
    for W in WINDOWS:
        ok, tot = _net_dir_agreement(orad, egod, W)
        cells.append(f"W={W}:{ok}/{tot}={ok / tot:.0%}" if tot else f"W={W}:-")
    print("  net-dir (perceiver pose vs oracle): " + "   ".join(cells))
    d = _drift_segmented(orad, egod)
    if d:
        k, drift, nseg, worst = d
        print(f"  drift (warp-segmented, k={k:.1f}px/cell): {drift:.2f} over {nseg} seg(s) (worst {worst:.2f})")
    print("  PASS if net-dir stays high/flat -> the FOREGROUND-motion move signal tracks the fixed-camera player.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
