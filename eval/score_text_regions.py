"""Score `core.text_regions.TextRegionDetector` against a hand-labeled fixture -- the pre-registered
GATE 1 for the glyph-read design (`reports/2026-07-05-glyph-read-design.md` section 5, Gate 1).

Fixture: `eval/fixtures/text_regions/` -- >=30 hand-labeled frames spanning all 6 recorded GBA sweep
games (`runs/probe_*/world/`, HANDOFF 2026-07-04) plus 5 no-text distractor frames from the same
sweep. Labels (`labels.json`) are ground-truth text-bearing bboxes drawn by inspecting the PNGs
directly with a pixel-ruler overlay -- built BEFORE the detector was scored against it, so the fixture
cannot be fit to the detector by construction.

Metrics (the design doc's Gate 1, pinned BEFORE this scorer was run):
  * recall    = matched targets / total targets (IoU >= --iou-thresh counts as a match)
  * precision = matched candidates / total candidates (over ALL frames, targets + distractors)
  * phantom_count = candidates on DISTRACTOR frames specifically (must be 0 to pass -- a phantom on a
    distractor is worse than a miss, the same fail-safe-over-recall rule as the static-object gate,
    `eval/score_static_objects.py`).

PINNED BAR (decided before running the detector, per the design doc): recall >= 0.85 AND
precision >= 0.70 AND phantom_count == 0. FAIL kills the detector cheap -- the brain falls back to
tiled `read_region` guessing (still workable, just costlier); thresholds are NOT tuned post-hoc to pass.

Usage:
    uv run python -m eval.score_text_regions
    uv run python -m eval.score_text_regions -v
"""
from __future__ import annotations

import argparse
import json
import os

import numpy as np
from PIL import Image

from core.text_regions import TextRegion, TextRegionDetector

_FIXTURE_DIR = os.path.join(os.path.dirname(__file__), "fixtures", "text_regions")

# The pinned Gate 1 bar (reports/2026-07-05-glyph-read-design.md section 5) -- do not tune to pass.
RECALL_BAR = 0.85
PRECISION_BAR = 0.70


def _iou(a: tuple, b: tuple) -> float:
    ax0, ay0, ax1, ay1 = a
    bx0, by0, bx1, by1 = b
    ix0, iy0 = max(ax0, bx0), max(ay0, by0)
    ix1, iy1 = min(ax1, bx1), min(ay1, by1)
    inter = max(0, ix1 - ix0) * max(0, iy1 - iy0)
    if inter <= 0:
        return 0.0
    area_a = max(0, ax1 - ax0) * max(0, ay1 - ay0)
    area_b = max(0, bx1 - bx0) * max(0, by1 - by0)
    return inter / (area_a + area_b - inter)


def _load_fixture(path: str = _FIXTURE_DIR) -> list[dict]:
    with open(os.path.join(path, "labels.json"), encoding="utf-8") as f:
        data = json.load(f)
    return data["frames"]


def score(fixture_dir: str = _FIXTURE_DIR, *, iou_thresh: float = 0.3,
          detector: TextRegionDetector | None = None) -> dict:
    detector = detector or TextRegionDetector()
    frames = _load_fixture(fixture_dir)

    total_targets = matched_targets = 0
    total_candidates = matched_candidates = 0
    phantom_count = 0
    per_frame = []

    for rec in frames:
        img = Image.open(os.path.join(fixture_dir, rec["file"])).convert("RGB")
        frame = np.asarray(img)
        regions: list[TextRegion] = detector.detect(frame)
        boxes = [r.bbox for r in regions]
        targets = [tuple(t) for t in rec["targets"]]

        # Greedy best-IoU matching, one candidate per target and vice versa (same convention as
        # eval/score_static_objects.py).
        used_c = set()
        n_matched_t = 0
        for t in targets:
            best_j, best_iou = None, 0.0
            for j, b in enumerate(boxes):
                if j in used_c:
                    continue
                v = _iou(t, b)
                if v > best_iou:
                    best_iou, best_j = v, j
            if best_j is not None and best_iou >= iou_thresh:
                used_c.add(best_j)
                n_matched_t += 1

        is_distractor = len(targets) == 0
        n_phantom = len(boxes) if is_distractor else 0

        total_targets += len(targets)
        matched_targets += n_matched_t
        total_candidates += len(boxes)
        matched_candidates += len(used_c)
        phantom_count += n_phantom

        per_frame.append({
            "file": rec["file"], "targets": len(targets), "candidates": len(boxes),
            "matched": n_matched_t if not is_distractor else None,
            "phantoms": n_phantom if is_distractor else None,
        })

    recall = matched_targets / total_targets if total_targets else None
    precision = matched_candidates / total_candidates if total_candidates else None

    return {
        "recall": recall, "precision": precision, "phantom_count": phantom_count,
        "total_targets": total_targets, "total_candidates": total_candidates,
        "matched_targets": matched_targets, "matched_candidates": matched_candidates,
        "per_frame": per_frame,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fixture", default=_FIXTURE_DIR)
    ap.add_argument("--iou-thresh", type=float, default=0.3)
    ap.add_argument("--cell", type=int, default=8)
    ap.add_argument("--row-thresh", type=float, default=20.0)
    ap.add_argument("--min-rows", type=int, default=2)
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()

    det = TextRegionDetector(cell=args.cell, row_thresh=args.row_thresh, min_rows=args.min_rows)
    result = score(args.fixture, iou_thresh=args.iou_thresh, detector=det)

    print(f"recall:    {result['recall']:.2f}  ({result['matched_targets']}/{result['total_targets']} targets)"
          if result["recall"] is not None else "recall: n/a (no targets)")
    print(f"precision: {result['precision']:.2f}  ({result['matched_candidates']}/{result['total_candidates']} candidates)"
          if result["precision"] is not None else "precision: n/a (no candidates)")
    print(f"phantom_count (distractor frames): {result['phantom_count']}")

    if args.verbose:
        print("\nper-frame:")
        for r in result["per_frame"]:
            if r["matched"] is not None:
                print(f"  {r['file']:32s} targets={r['targets']} candidates={r['candidates']} matched={r['matched']}")
            else:
                print(f"  {r['file']:32s} DISTRACTOR candidates={r['candidates']} phantoms={r['phantoms']}")

    gate = (result["recall"] or 0) >= RECALL_BAR and (result["precision"] or 0) >= PRECISION_BAR \
        and result["phantom_count"] == 0
    print(f"\nGATE 1: {'PASS' if gate else 'FAIL'} "
          f"(recall>={RECALL_BAR}, precision>={PRECISION_BAR}, phantoms==0)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
