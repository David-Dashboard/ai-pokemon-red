"""Entity-detector precision/recall probe.

Scores the EntityDetector against v2 hand-label GT boxes (avatar+enemy+item).
Sweeps:
  - connectivity: 4 vs 8
  - avatar-exclusion filter: on vs off
  - HUD-mask filter: on vs off  (cave noire / games with visible HUD strip)
  - min_area filter: 16 vs 64

Reports per-game and per-camera-class tables.
Held-out games (crystalis, zelda, sml, f1race) are reported SEPARATELY —
thresholds are NEVER tuned on them.

Usage:
    UV_PROJECT_ENVIRONMENT=.venv-win UV_NATIVE_TLS=true uv run python -m eval.probe_entities
    UV_PROJECT_ENVIRONMENT=.venv-win UV_NATIVE_TLS=true uv run python -m eval.probe_entities cavenoire
"""
from __future__ import annotations

import glob
import json
import os
import sys
from dataclasses import dataclass, field
from typing import Optional

import numpy as np
from PIL import Image

from core.entities import EntityDetector
from eval._eval_utils import _slug, _camera, _is_held_out, _iou, FOLLOW_KEYS as _FOLLOW_KEYS

_LABEL_ROOT = "datasets/labels/v2"
_IOU_THRESH = 0.3

# HUD region used for games with a visible status bar at the bottom.
# Cave Noire has a ~8px HUD strip at bottom of the 144-tall screen.
_HUD_CAVENOIRE = (0, 128, 160, 144)

# Games that have a visible HUD band at bottom (used to enable HUD filter)
_HUD_GAMES = ("cavenoire", "gauntlet", "ffa")


@dataclass
class Acc:
    tp: int = 0
    fp: int = 0
    fn: int = 0

    def prec(self) -> float:
        return self.tp / (self.tp + self.fp) if (self.tp + self.fp) else 0.0

    def rec(self) -> float:
        return self.tp / (self.tp + self.fn) if (self.tp + self.fn) else 0.0

    def f1(self) -> float:
        p, r = self.prec(), self.rec()
        return 2 * p * r / (p + r) if (p + r) else 0.0

    def __iadd__(self, other: "Acc") -> "Acc":
        self.tp += other.tp; self.fp += other.fp; self.fn += other.fn
        return self




def _score_detector(detector: EntityDetector, label_path: str,
                    use_avatar_excl: bool) -> Optional[Acc]:
    """Run detector over one game's frames and return Acc (or None if no run dir)."""
    slug = _slug(label_path)
    run_dir = os.path.join("runs", os.path.basename(label_path).replace(".json", ""))
    if not os.path.isdir(run_dir):
        return None

    labels_raw = json.load(open(label_path, encoding="utf-8"))
    labs = {r["frame"]: r for r in labels_raw
            if r.get("avatar") and r.get("mode") == "gameplay"}
    if len(labs) < 4:
        return None

    last = max(labs)
    acc = Acc()

    for i in range(last + 1):
        fp = os.path.join(run_dir, f"frame_{i:06d}.png")
        if not os.path.exists(fp):
            break
        frame = np.asarray(Image.open(fp).convert("RGB"))

        # avatar pixel centre for exclusion filter
        avatar_px: Optional[tuple[float, float]] = None
        if use_avatar_excl and i in labs:
            ab = labs[i]["avatar"][0]
            avatar_px = ((ab[0] + ab[2]) / 2, (ab[1] + ab[3]) / 2)

        det_entities = detector.detect(frame, avatar_px=avatar_px)

        if i not in labs:
            continue

        lab = labs[i]
        gt_boxes = (
            lab.get("avatar", []) +
            lab.get("enemy", []) +
            lab.get("item", [])
        )
        det_boxes = [e["bbox"] for e in det_entities]

        matched_gt: set[int] = set()
        matched_det: set[int] = set()
        for gi, gb in enumerate(gt_boxes):
            for di, db in enumerate(det_boxes):
                if _iou(gb, db) >= _IOU_THRESH and gi not in matched_gt and di not in matched_det:
                    matched_gt.add(gi)
                    matched_det.add(di)
                    break
        acc.tp += len(matched_gt)
        acc.fp += len(det_boxes) - len(matched_det)
        acc.fn += len(gt_boxes) - len(matched_gt)

    return acc


@dataclass
class Config:
    name: str
    connectivity: int
    avatar_excl: bool
    hud_mask: bool
    min_area: int


_CONFIGS = [
    # baseline (same as compare_localizers blob P/R: 4-conn, no filters)
    Config("baseline(4-conn,no-filter)", connectivity=4, avatar_excl=False, hud_mask=False, min_area=16),
    # 8-conn without filters
    Config("8-conn,no-filter",           connectivity=8, avatar_excl=False, hud_mask=False, min_area=16),
    # 4-conn + avatar excl only
    Config("4-conn,+avt",                connectivity=4, avatar_excl=True,  hud_mask=False, min_area=16),
    # 4-conn + hud mask only
    Config("4-conn,+hud",                connectivity=4, avatar_excl=False, hud_mask=True,  min_area=16),
    # 4-conn + min_area=64
    Config("4-conn,area64",              connectivity=4, avatar_excl=False, hud_mask=False, min_area=64),
    # 4-conn + all filters
    Config("4-conn,all-filters",         connectivity=4, avatar_excl=True,  hud_mask=True,  min_area=64),
    # 8-conn + all filters  (the intended production config)
    Config("8-conn,all-filters",         connectivity=8, avatar_excl=True,  hud_mask=True,  min_area=64),
]


def _make_detector(cfg: Config, slug: str) -> EntityDetector:
    hud = None
    if cfg.hud_mask and any(g in slug for g in _HUD_GAMES):
        hud = _HUD_CAVENOIRE
    return EntityDetector(
        connectivity=cfg.connectivity,
        min_area=cfg.min_area,
        avatar_radius=20.0,
        hud_region=hud,
    )


def main() -> int:
    filt = sys.argv[1] if len(sys.argv) > 1 else ""
    label_files = sorted(glob.glob(os.path.join(_LABEL_ROOT, "*.json")))
    label_files = [f for f in label_files if filt in f]

    if not label_files:
        print("No label files found."); return 1

    # Per-config results: config_name -> list of (slug, cam, held_out, acc)
    all_results: dict[str, list[tuple[str, str, bool, Acc]]] = {c.name: [] for c in _CONFIGS}

    for lf in label_files:
        slug = _slug(lf)
        cam = _camera(slug)
        held = _is_held_out(slug)
        run_dir = os.path.join("runs", os.path.basename(lf).replace(".json", ""))
        if not os.path.isdir(run_dir):
            print(f"  {slug}: skipped (no run dir)")
            continue
        for cfg in _CONFIGS:
            det = _make_detector(cfg, slug)
            acc = _score_detector(det, lf, use_avatar_excl=cfg.avatar_excl)
            if acc is not None:
                all_results[cfg.name].append((slug, cam, held, acc))

    # ── per-game table ────────────────────────────────────────────────────────
    # collect all slugs that have data
    slugs_seen: dict[str, tuple[str, bool]] = {}
    for rows in all_results.values():
        for slug, cam, held, _ in rows:
            slugs_seen[slug] = (cam, held)

    if not slugs_seen:
        print("No results."); return 1

    cfg_names = [c.name for c in _CONFIGS]
    col_w = 22
    hdr = f"{'game':<22} {'cam':6} {'H':1}  " + "  ".join(f"{n[:col_w]:<{col_w}}" for n in cfg_names)
    sub = " " * 30 + "  ".join(f"{'P%':>5} {'R%':>5} {'F1':>5}   " for _ in cfg_names)

    print("\n=== Entity detector P/R vs GT boxes (avatar+enemy+item, IoU>=0.3) ===")
    print("    H=held-out (never tune on these)")
    print()
    print(hdr)
    print(sub)
    print("-" * len(hdr))

    dev_cam_acc: dict[str, dict[str, Acc]] = {}   # cam -> cfg_name -> Acc (dev only)
    held_cam_acc: dict[str, dict[str, Acc]] = {}

    for slug in sorted(slugs_seen):
        cam, held = slugs_seen[slug]
        H = "Y" if held else " "
        row = f"{slug[:20]:<22} {cam:<6} {H}  "
        for cfg in _CONFIGS:
            entry = next(((s, c, ho, a) for s, c, ho, a in all_results[cfg.name] if s == slug), None)
            if entry is None:
                row += f"{'N/A':>5} {'N/A':>5} {'N/A':>5}   "
                continue
            _, _, _, acc = entry
            row += f"{acc.prec():5.0%} {acc.rec():5.0%} {acc.f1():5.0%}   "
            # aggregate by cam
            target = held_cam_acc if held else dev_cam_acc
            if cam not in target:
                target[cam] = {c.name: Acc() for c in _CONFIGS}
            target[cam][cfg.name] += acc
        print(row)

    # ── per-camera-class aggregate (dev) ─────────────────────────────────────
    def _cam_table(title: str, cam_acc: dict[str, dict[str, Acc]]) -> None:
        if not cam_acc:
            return
        print(f"\n{title}")
        print(f"{'class':<8}  " + "  ".join(f"{n[:col_w]:<{col_w}}" for n in cfg_names))
        print(" " * 10 + "  ".join(f"{'P%':>5} {'R%':>5} {'F1':>5}   " for _ in cfg_names))
        for cam in sorted(cam_acc):
            row = f"{cam:<8}  "
            for cfg in _CONFIGS:
                a = cam_acc[cam].get(cfg.name, Acc())
                row += f"{a.prec():5.0%} {a.rec():5.0%} {a.f1():5.0%}   "
            print(row)
        # totals
        row = f"{'TOTAL':<8}  "
        for cfg in _CONFIGS:
            tot = Acc()
            for a_map in cam_acc.values():
                tot += a_map.get(cfg.name, Acc())
            row += f"{tot.prec():5.0%} {tot.rec():5.0%} {tot.f1():5.0%}   "
        print(row)

    _cam_table("=== Per camera-class (DEV — tuning games) ===", dev_cam_acc)
    _cam_table("=== Per camera-class (HELD-OUT — report only) ===", held_cam_acc)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
