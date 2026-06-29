"""Cross-method avatar-localization comparison against v2 hand labels.

Scores four methods against datasets/labels/v2/ avatar boxes:
  baseline  -- core.localize.AvatarLocalizer (decaying heatmap + argmax + outlier gate)
  bayes     -- core.localize_bayes.BayesAvatarLocalizer (Bayes-filter posterior over heatmap)
  blob      -- core.localize_blob.BlobContingencyLocalizer (blob-level contingency)
  scroll    -- core.localize_scroll.ScrollingLocalizer wrapping BayesAvatarLocalizer

Per game AND per camera-class (fixed vs follow/scroll):
  in-box%   -- fraction of locked + labelled frames where estimate falls inside GT avatar box
  px        -- median pixel error to GT box centre (on locked frames)

Also: blob precision/recall vs entity GT boxes (avatar+enemy+item).

Usage:
  uv run python -m eval.compare_localizers            # all games
  uv run python -m eval.compare_localizers cavenoire  # substring filter
"""
from __future__ import annotations

import glob
import json
import os
import sys
from typing import Optional

import numpy as np
from PIL import Image

from core.localize import AvatarLocalizer
from core.localize_bayes import BayesAvatarLocalizer
from core.localize_blob import BlobContingencyLocalizer
from core.localize_scroll import ScrollingLocalizer
from core.blob import RollingBg, segment_blobs
from eval._eval_utils import _slug as _game_slug, _camera as _camera_class, _is_held_out, _iou

# Camera class by game-name substring (spread < 15 = follow/scroll, >= 15 = fixed/flip)
# Derived from eval/score_localize spread column; games with spread >= 15 = fixed.
_DIRS = ("up", "down", "left", "right")
_LABEL_ROOT = "datasets/labels/v2"


def _dir(buttons) -> Optional[str]:
    t = [b for b in (buttons or []) if b in _DIRS]
    return t[-1] if t else None


def _ctr(box):
    return ((box[0] + box[2]) / 2, (box[1] + box[3]) / 2)


def _inside(p, box) -> bool:
    return box[0] <= p[0] <= box[2] and box[1] <= p[1] <= box[3]


def run_game(label_path: str) -> Optional[dict]:
    slug = _game_slug(label_path)
    run_dir = os.path.join("runs", os.path.basename(label_path).replace(".json", ""))

    labels_raw = json.load(open(label_path, encoding="utf-8"))
    labs = {r["frame"]: r for r in labels_raw
            if r.get("avatar") and r.get("mode") == "gameplay"}
    if len(labs) < 4:
        return None
    if not os.path.isdir(run_dir):
        return None

    btn_path = os.path.join(run_dir, "buttons.jsonl")
    if not os.path.exists(btn_path):
        return None
    btns = [json.loads(l) for l in open(btn_path, encoding="utf-8")]

    last = max(labs)
    localizers = {
        "baseline": AvatarLocalizer(),
        "bayes":    BayesAvatarLocalizer(),
        "blob":     BlobContingencyLocalizer(),
        "scroll":   ScrollingLocalizer(BayesAvatarLocalizer()),
    }

    # Per-method accumulators: (errors, in_box_count, locked_count, n_labelled)
    acc = {name: {"errs": [], "ins": 0, "locked": 0, "n": 0} for name in localizers}

    # Blob precision/recall accumulators; separate bg to avoid double-updating the localizer's buffer
    blob_tp, blob_fp, blob_fn = 0, 0, 0
    pr_bg = RollingBg(window=6)

    for i in range(last + 1):
        fp = os.path.join(run_dir, f"frame_{i:06d}.png")
        if not os.path.exists(fp):
            break
        d = _dir(btns[i].get("buttons")) if i < len(btns) else None
        frame = np.asarray(Image.open(fp).convert("RGB"))

        outs = {}
        for name, loc in localizers.items():
            outs[name] = loc.update(frame, d)

        # Update independent P/R bg tracker
        gray_pr = frame[..., :3].mean(2).astype(np.float32)
        fg_pr = pr_bg.update(gray_pr)

        if i in labs:
            lab = labs[i]
            avatar_box = lab["avatar"][0]  # [x0, y0, x1, y1]
            gt_ctr = _ctr(avatar_box)

            for name in localizers:
                a = acc[name]
                a["n"] += 1
                out = outs[name]
                if out is not None:
                    a["locked"] += 1
                    err = float(np.hypot(out[0] - gt_ctr[0], out[1] - gt_ctr[1]))
                    a["errs"].append(err)
                    if _inside((out[0], out[1]), avatar_box):
                        a["ins"] += 1

            # Blob P/R: all GT entity boxes (avatar+enemy+item) vs blob segments
            gt_boxes = (
                lab.get("avatar", []) +
                lab.get("enemy", []) +
                lab.get("item", [])
            )
            if fg_pr is not None:
                det_blobs = segment_blobs(None, fg_mag=fg_pr, thresh=15.0, min_area=16)
                det_boxes = [[b.x0, b.y0, b.x1, b.y1] for b in det_blobs]
            else:
                det_boxes = []

            matched_gt = set()
            matched_det = set()
            for gi, gb in enumerate(gt_boxes):
                for di, db in enumerate(det_boxes):
                    if _iou(gb, db) >= 0.3 and gi not in matched_gt and di not in matched_det:
                        matched_gt.add(gi)
                        matched_det.add(di)
                        break
            blob_tp += len(matched_gt)
            blob_fp += len(det_boxes) - len(matched_det)
            blob_fn += len(gt_boxes) - len(matched_gt)

    result = {"slug": slug, "camera": _camera_class(slug), "held_out": _is_held_out(slug)}
    for name in localizers:
        a = acc[name]
        n, locked = a["n"], a["locked"]
        result[name] = dict(
            n=n,
            lock=locked / n if n else 0.0,
            inbox=a["ins"] / locked if locked else 0.0,
            med=float(np.median(a["errs"])) if a["errs"] else -1.0,
        )

    # blob P/R
    prec = blob_tp / (blob_tp + blob_fp) if (blob_tp + blob_fp) > 0 else 0.0
    rec  = blob_tp / (blob_tp + blob_fn) if (blob_tp + blob_fn) > 0 else 0.0
    result["blob_pr"] = dict(tp=blob_tp, fp=blob_fp, fn=blob_fn, prec=prec, rec=rec)

    return result


def _fmt(r: dict, name: str) -> str:
    m = r[name]
    ib = f"{m['inbox']:5.0%}" if m["lock"] > 0 else "  N/A"
    px = f"{m['med']:4.0f}" if m["med"] >= 0 else "  -"
    return f"{ib} /{px}"


def main():
    filt = sys.argv[1] if len(sys.argv) > 1 else ""
    label_files = sorted(glob.glob(os.path.join(_LABEL_ROOT, "*.json")))
    label_files = [f for f in label_files if filt in f]

    results = []
    for lf in label_files:
        r = run_game(lf)
        if r is None:
            slug = _game_slug(lf)
            print(f"  {slug}: skipped (no run dir or too few labels)")
            continue
        results.append(r)

    if not results:
        print("No results."); return 1

    methods = ["baseline", "bayes", "blob", "scroll"]
    hdr = f"{'game':<20} {'cam':6} {'heldout':7}  " + "  ".join(
        f"{'  ' + m + ' in%/px':>14}" for m in methods
    )
    print("\n=== Avatar-localization comparison (v2 labels) ===\n")
    print(hdr)
    print("-" * len(hdr))

    cam_acc: dict[str, dict] = {}  # camera_class -> method -> lists of inbox bools + errs

    for r in results:
        slug = r["slug"][:18]
        cam = r["camera"]
        held = "Y" if r["held_out"] else " "
        cols = "  ".join(_fmt(r, m) for m in methods)
        print(f"{slug:<20} {cam:<6} {held:<7}  {cols}")

        # aggregate by camera class
        if cam not in cam_acc:
            cam_acc[cam] = {m: {"ins": 0, "locked": 0, "errs": []} for m in methods}
        for m in methods:
            mm = r[m]
            cam_acc[cam][m]["locked"] += mm["locked"] if "locked" in mm else int(mm["lock"] * mm["n"])
            # recompute from stored values
            n, lock_rate = mm["n"], mm["lock"]
            locked = int(round(lock_rate * n))
            ins = int(round(mm["inbox"] * locked))
            cam_acc[cam][m]["ins"] += ins
            cam_acc[cam][m]["locked"] += 0  # already counted above via mm
            cam_acc[cam][m]["errs"]  # errs not stored; aggregate inbox only

    # Per-camera summary (inbox % from aggregated ins/locked stored in results)
    print()
    print("=== Per camera-class aggregate ===")
    print(f"{'class':<8} " + "  ".join(f"{'  ' + m + ' in%':>12}" for m in methods))

    # re-aggregate properly
    cam_agg2: dict[str, dict] = {}
    for r in results:
        cam = r["camera"]
        if cam not in cam_agg2:
            cam_agg2[cam] = {m: {"ins": 0, "locked": 0, "errs": []} for m in methods}
        for m in methods:
            mm = r[m]
            n = mm["n"]
            locked = int(round(mm["lock"] * n))
            ins = int(round(mm["inbox"] * locked))
            cam_agg2[cam][m]["ins"] += ins
            cam_agg2[cam][m]["locked"] += locked
            if mm["med"] >= 0:
                cam_agg2[cam][m]["errs"].append(mm["med"])

    for cam, cacc in sorted(cam_agg2.items()):
        parts = []
        for m in methods:
            locked = cacc[m]["locked"]
            ins = cacc[m]["ins"]
            ib = f"{ins/locked:5.0%}" if locked else "  N/A"
            parts.append(f"{ib:>12}")
        print(f"{cam:<8} " + "  ".join(parts))

    # Blob P/R summary
    print()
    print("=== Blob detector P/R vs entity GT boxes (avatar+enemy+item, IoU>=0.3) ===")
    tp_tot = fp_tot = fn_tot = 0
    for r in results:
        bp = r["blob_pr"]
        slug = r["slug"][:18]
        print(f"  {slug:<20}  P={bp['prec']:.0%}  R={bp['rec']:.0%}  "
              f"tp={bp['tp']}  fp={bp['fp']}  fn={bp['fn']}")
        tp_tot += bp["tp"]; fp_tot += bp["fp"]; fn_tot += bp["fn"]
    prec_tot = tp_tot / (tp_tot + fp_tot) if (tp_tot + fp_tot) else 0
    rec_tot  = tp_tot / (tp_tot + fn_tot) if (tp_tot + fn_tot) else 0
    print(f"  {'TOTAL':<20}  P={prec_tot:.0%}  R={rec_tot:.0%}  "
          f"tp={tp_tot}  fp={fp_tot}  fn={fn_tot}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
