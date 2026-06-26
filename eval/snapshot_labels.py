"""Snapshot the hand-label dataset into a committed, VERSIONED folder (datasets/labels/<version>/).

Labels are authored live into runs/<game>/frame_labels.json (the gitignored corpus). This freezes the current
set as an immutable version (v1, v2, ...) under git, with a MANIFEST of what's in it -- so the dataset is
reproducible, diffable as it grows, and the labour is version-controlled even though the raw frames stay in the
corpus. Re-run with a new --version to cut the next snapshot.

  uv run python -m eval.snapshot_labels --version v1
"""
from __future__ import annotations

import argparse
import glob
import json
import os
from collections import Counter

CATS = ["avatar", "enemy", "item", "text", "health", "exit", "npc"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--version", required=True, help="version tag, e.g. v1")
    ap.add_argument("--base", default="datasets/labels", help="committed dataset root")
    args = ap.parse_args()

    out = os.path.join(args.base, args.version)
    os.makedirs(out, exist_ok=True)
    srcs = sorted(glob.glob("runs/*/frame_labels.json"))
    if not srcs:
        print("no runs/*/frame_labels.json found"); return 1

    rows, tot_frames, tot_cat, tot_mode, tot_val = [], 0, Counter(), Counter(), 0
    for p in srcs:
        game = os.path.basename(os.path.dirname(p))
        data = json.load(open(p, encoding="utf-8"))
        for r in data:                                       # normalize older records (backfill new categories)
            r.setdefault("mode", None)
            for c in CATS:
                r.setdefault(c, [])
        json.dump(data, open(os.path.join(out, f"{game}.json"), "w", encoding="utf-8"), indent=0)
        modes = Counter(r.get("mode") for r in data if r.get("mode"))
        catc = {c: sum(len(r.get(c, [])) for r in data) for c in CATS}
        vals = sum(1 for r in data for c in ("text", "health") for b in r.get(c, []) if len(b) > 4 and b[4])
        rows.append((game, len(data), modes, catc, vals))
        tot_frames += len(data); tot_cat.update(catc); tot_mode.update(modes); tot_val += vals

    # manifest.md
    with open(os.path.join(out, "manifest.md"), "w", encoding="utf-8") as f:
        f.write(f"# Label dataset {args.version}\n\n")
        f.write(f"{len(rows)} games · {tot_frames} labelled frames · "
                f"{sum(tot_cat.values())} boxes · {tot_val} read-values (text/health).\n")
        th = tot_cat.get("text", 0) + tot_cat.get("health", 0)
        f.write(f"**OCR-value coverage is sparse:** only {tot_val}/{th} ({tot_val / th if th else 0:.0%}) of "
                "text+health boxes carry a read string — the HUD-gate OCR ground truth is a milestone, **not yet "
                "cross-world** (concentrated in the early games). Treat accordingly.\n")
        f.write("Frames live in `runs/<game>/` (corpus, gitignored); these JSONs are the annotations.\n\n")
        f.write("| game | frames | " + " | ".join(CATS) + " | values | modes |\n")
        f.write("|" + "---|" * (len(CATS) + 4) + "\n")
        for game, nf, modes, catc, vals in rows:
            md = ",".join(f"{k}:{v}" for k, v in modes.most_common())
            f.write(f"| {game} | {nf} | " + " | ".join(str(catc[c]) for c in CATS) + f" | {vals} | {md} |\n")
        f.write(f"| **TOTAL** | **{tot_frames}** | " + " | ".join(f"**{tot_cat[c]}**" for c in CATS)
                + f" | **{tot_val}** | {','.join(f'{k}:{v}' for k,v in tot_mode.most_common())} |\n")

    print(f"snapshot {args.version}: {len(rows)} games, {tot_frames} frames, {sum(tot_cat.values())} boxes -> {out}")
    for game, nf, modes, catc, vals in rows:
        print(f"  {game:34s} {nf:3d} frames  boxes={sum(catc.values()):3d}  values={vals:3d}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
