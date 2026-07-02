"""Score `core.static_objects.StaticObjectDetector` against a hand-labeled fixture set -- the SCORED GATE
for the referential-grounding static-object channel (`reports/2026-07-03-referential-grounding-design.md`
section 4). Built FIRST, before the detector is tuned against it, so the detector cannot be fit to the
grader by construction (still possible to overfit by iterating, but the labels are frozen ground truth,
not derived from the detector's own output).

Fixture: `eval/fixtures/static_objects_pokeball/` -- a small committed set (no runs/ dependency) mixing:
  * 5 Pokemon Red frames of Oak's-lab Poke-Ball table (the design doc's probe frames + 2 more camera
    framings) with hand-labeled ball bboxes ("targets").
  * 9 DISTRACTOR frames with NO target object: other Red interiors/overworld, and frames from other
    (non-Pokemon) games recorded under runs/ -- including one adversarial same-red-hue distractor
    (a different game's lab with a red appliance sprite) to stress precision honestly.

Metrics (the design doc's gate, section 4):
  * recall    = matched targets / total targets (IoU >= --iou-thresh counts as a match)
  * precision = matched candidates / total candidates (over ALL frames, targets + distractors)
  * phantom_count = candidates on DISTRACTOR frames specifically (must be 0 to greenlight; a phantom
    on a distractor frame is worse than a miss -- fail-safe over recall, per CONTEXT-BRIEFING.md's
    cheap-index rule referenced by the design doc).

Usage:
    uv run python -m eval.score_static_objects
    uv run python -m eval.score_static_objects --group          # apply group_equal_collinear precision heuristic
"""
from __future__ import annotations

import argparse
import glob
import json
import os

import numpy as np
from PIL import Image

from core.static_objects import Candidate, StaticObjectDetector, group_equal_collinear

_FIXTURE_DIR = os.path.join(os.path.dirname(__file__), "fixtures", "static_objects_pokeball")


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


def _candidate_boxes(cands: list[Candidate], grouped: bool) -> list[tuple]:
    if not grouped:
        return [c.bbox for c in cands]
    groups = group_equal_collinear(cands)
    kept_ids = {id(c) for g in groups for c in g}
    return [c.bbox for c in cands if id(c) in kept_ids]


def score(fixture_dir: str = _FIXTURE_DIR, *, iou_thresh: float = 0.3, grouped: bool = False,
          detector: StaticObjectDetector | None = None) -> dict:
    detector = detector or StaticObjectDetector()
    frames = _load_fixture(fixture_dir)

    total_targets = matched_targets = 0
    total_candidates = matched_candidates = 0
    phantom_count = 0
    per_frame = []

    for rec in frames:
        img = Image.open(os.path.join(fixture_dir, rec["file"])).convert("RGB")
        frame = np.asarray(img)
        cands = detector.detect(frame)
        boxes = _candidate_boxes(cands, grouped)
        targets = [tuple(t) for t in rec["targets"]]

        # match candidates -> targets greedily by best IoU (one candidate per target, one target per candidate)
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
    ap.add_argument("--group", action="store_true",
                    help="apply the equal-area/collinear grouping heuristic before scoring precision")
    ap.add_argument("--chroma-thresh", type=float, default=28.0)
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()

    det = StaticObjectDetector(chroma_thresh=args.chroma_thresh)
    result = score(args.fixture, iou_thresh=args.iou_thresh, grouped=args.group, detector=det)

    print(f"recall:    {result['recall']:.2f}  ({result['matched_targets']}/{result['total_targets']} targets)"
          if result["recall"] is not None else "recall: n/a (no targets)")
    print(f"precision: {result['precision']:.2f}  ({result['matched_candidates']}/{result['total_candidates']} candidates)"
          if result["precision"] is not None else "precision: n/a (no candidates)")
    print(f"phantom_count (distractor frames): {result['phantom_count']}")

    if args.verbose:
        print("\nper-frame:")
        for r in result["per_frame"]:
            if r["matched"] is not None:
                print(f"  {r['file']:28s} targets={r['targets']} candidates={r['candidates']} matched={r['matched']}")
            else:
                print(f"  {r['file']:28s} DISTRACTOR candidates={r['candidates']} phantoms={r['phantoms']}")

    gate = (result["recall"] or 0) >= 0.9 and (result["precision"] or 0) >= 0.8 and result["phantom_count"] == 0
    print(f"\nGATE: {'PASS' if gate else 'FAIL'} (recall>=0.9, precision>=0.8, phantoms==0)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
