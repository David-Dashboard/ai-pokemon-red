"""Score `core.text_regions_r1.GlyphRegionDetector` against a same-game warm/held-out split -- the
pre-registered R1 GATE (`reports/2026-07-03-glyph-r1-cache-driven-detection.md` section 4).

Reuses, unmodified: `eval/score_text_regions.py`'s `_iou` + `_load_fixture` (the exact Gate 1 IoU
matching machinery, just imported here rather than re-run through its `score()` wrapper, since R1
needs a WARM, PER-GAME cache before scoring -- `score()` itself is not called or edited);
`eval/score_glyph_cache.py`'s `N_WARMUP_CONFIRMING_FRAMES` / `_MIN_REAL_CELLS` constants (Gate 2's
own warmup-confirming-frame rule, reused for R1's warmup harness, unmodified); `core.text_regions_r1`'s
`confirm_region` (the pinned snap-to-grid mitigation).

Warmup harness (design doc section 4a item 3): `warm_cache_from_labels` takes a probe-dir + the
`eval/fixtures/text_regions/warmup_labels.json` frame list for one game and returns a `GlyphCache`
warmed via SIMULATED confirmation -- every non-blank grid cell inside a labeled warmup bbox is
confirmed with a single shared placeholder reading (section 4a item 2: legitimate because this gate
tests DETECTION, `from_cache` boolean, not character identity). Stops after the first
`N_WARMUP_CONFIRMING_FRAMES` (5) confirming frames, exactly Gate 2's own rule.

`runs/` is gitignored and NOT present in a fresh worktree -- callers must pass `--probe-root` pointing
at a checkout that has it (e.g. the main checkout). No paid brain call anywhere in this gate: warmup
replays probe-dir frames already on disk, scoring replays `eval/fixtures/text_regions/labels.json`
(both free/offline, per the design doc's pinned cost class).

PINNED BAR (decided before running, design doc section 4b) -- do not tune to pass:
  PASS: recall >= 0.85 AND precision >= 0.90 AND phantom_count == 0, on qualifying same-game
        warm/held-out pairs only.
  KILL: recall <= 0.27 OR precision <= 0.49 (R0's own failed numbers) on the same split.
  Anything strictly between is INCONCLUSIVE -- reported as such, never rounded to a pass.

Usage:
    uv run python -m eval.score_glyph_r1 --probe-root <path-to-checkout-with-runs/>
    uv run python -m eval.score_glyph_r1 --probe-root <path> -v
"""
from __future__ import annotations

import argparse
import json
import os

import numpy as np
from PIL import Image

from core.glyph_cache import GlyphCache
from core.text_regions_r1 import GlyphRegionDetector, confirm_region
from eval.score_glyph_cache import N_WARMUP_CONFIRMING_FRAMES, _MIN_REAL_CELLS
from eval.score_text_regions import _iou, _load_fixture, _FIXTURE_DIR

_WARMUP_LABELS_PATH = os.path.join(os.path.dirname(__file__), "fixtures", "text_regions", "warmup_labels.json")

# Pinned R1 bar (reports/2026-07-03-glyph-r1-cache-driven-detection.md section 4b) -- do not tune to pass.
RECALL_BAR = 0.85
PRECISION_BAR = 0.90
KILL_RECALL = 0.27     # R0's own failed recall -- at or below this is a clean kill, not noise
KILL_PRECISION = 0.49  # R0's own failed precision

_PLACEHOLDER_READING = "#"   # single shared placeholder (design doc section 4a item 2)


def load_warmup_labels(path: str = _WARMUP_LABELS_PATH) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)["games"]


def warm_cache_from_labels(probe_dir: str, frame_records: list, *, cell: int = 8) -> tuple[GlyphCache, dict]:
    """Replay `frame_records` (from warmup_labels.json, in list/file order) against `probe_dir`,
    confirming every non-blank grid cell inside each labeled bbox with a shared placeholder reading.
    Stops after the first N_WARMUP_CONFIRMING_FRAMES confirming frames -- Gate 2's own rule
    (a frame counts iff it contributes >=1 first-sight confirmation AND has >= _MIN_REAL_CELLS
    non-blank cells), reused unmodified so "warm" means the same thing here as it did for Gate 2."""
    cache = GlyphCache()
    confirming_frames = 0
    frames_used: list[str] = []

    for rec in frame_records:
        path = os.path.join(probe_dir, rec["file"])
        img = Image.open(path).convert("RGB")
        frame = np.asarray(img)

        frame_real = frame_new = 0
        for rect in rec["targets"]:
            n_real, n_new = confirm_region(cache, frame, tuple(rect), _PLACEHOLDER_READING, cell=cell)
            frame_real += n_real
            frame_new += n_new

        frames_used.append(rec["file"])
        if frame_new > 0 and frame_real >= _MIN_REAL_CELLS:
            confirming_frames += 1
            if confirming_frames >= N_WARMUP_CONFIRMING_FRAMES:
                break

    return cache, {
        "confirming_frames": confirming_frames,
        "frames_used": frames_used,
        "distinct_glyphs_confirmed": len(cache),
        "warm": confirming_frames >= N_WARMUP_CONFIRMING_FRAMES,
    }


def score_game(game: str, probe_root: str, warmup_labels: dict, *, fixture_dir: str = _FIXTURE_DIR,
               iou_thresh: float = 0.3, cell: int = 8) -> dict:
    """Warm a fresh GlyphCache on `game`'s own probe-dir frames, then score
    `core.text_regions_r1.GlyphRegionDetector` against labels.json's frames for that SAME game only
    (same-game warm/held-out pairing, design doc section 4b)."""
    entry = warmup_labels[game]
    probe_dir = os.path.join(probe_root, entry["probe_dir"])
    cache, warm_stats = warm_cache_from_labels(probe_dir, entry["frames"], cell=cell)
    detector = GlyphRegionDetector(cache, cell=cell)

    frames = [rec for rec in _load_fixture(fixture_dir) if rec.get("game") == game]

    total_targets = matched_targets = 0
    total_candidates = matched_candidates = 0
    phantom_count = 0
    per_frame = []

    for rec in frames:
        img = Image.open(os.path.join(fixture_dir, rec["file"])).convert("RGB")
        frame = np.asarray(img)
        regions = detector.detect(frame)
        boxes = [r.bbox for r in regions]
        targets = [tuple(t) for t in rec["targets"]]

        used_c: set = set()
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

        per_frame.append({"file": rec["file"], "targets": len(targets), "candidates": len(boxes),
                           "matched": n_matched_t if not is_distractor else None,
                           "phantoms": n_phantom if is_distractor else None})

    recall = matched_targets / total_targets if total_targets else None
    precision = matched_candidates / total_candidates if total_candidates else None

    return {
        "game": game, "warm": warm_stats, "recall": recall, "precision": precision,
        "phantom_count": phantom_count, "total_targets": total_targets,
        "total_candidates": total_candidates, "matched_targets": matched_targets,
        "matched_candidates": matched_candidates, "per_frame": per_frame,
    }


def _classify(recall, precision, phantom_count: int) -> str:
    if recall is None:
        return "INCONCLUSIVE (no targets)"
    if recall >= RECALL_BAR and (precision or 0) >= PRECISION_BAR and phantom_count == 0:
        return "PASS"
    if recall <= KILL_RECALL or (precision or 0) <= KILL_PRECISION:
        return "KILL"
    return "INCONCLUSIVE"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--probe-root", required=True,
                     help="checkout root containing runs/ (gitignored, not in this worktree)")
    ap.add_argument("--fixture", default=_FIXTURE_DIR)
    ap.add_argument("--warmup-labels", default=_WARMUP_LABELS_PATH)
    ap.add_argument("--iou-thresh", type=float, default=0.3)
    ap.add_argument("--cell", type=int, default=8)
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()

    warmup_labels = load_warmup_labels(args.warmup_labels)

    pooled_mt = pooled_tt = pooled_mc = pooled_tc = pooled_phantom = 0
    any_inconclusive_warm = False

    for game in sorted(warmup_labels):
        result = score_game(game, args.probe_root, warmup_labels, fixture_dir=args.fixture,
                             iou_thresh=args.iou_thresh, cell=args.cell)
        verdict = _classify(result["recall"], result["precision"], result["phantom_count"])
        warm = result["warm"]
        if not warm["warm"]:
            any_inconclusive_warm = True

        print(f"\n=== {game} ===")
        print(f"  warm-cache: {warm['confirming_frames']}/{N_WARMUP_CONFIRMING_FRAMES} confirming frames "
              f"({'WARM' if warm['warm'] else 'NOT WARM -- measured, reported, not silently skipped'}), "
              f"{warm['distinct_glyphs_confirmed']} distinct glyph shapes confirmed "
              f"from {len(warm['frames_used'])} warmup frames replayed")
        if result["recall"] is None:
            print("  recall: n/a (no targets for this game)")
        else:
            print(f"  recall:    {result['recall']:.3f}  ({result['matched_targets']}/{result['total_targets']} targets)")
        if result["precision"] is None:
            print("  precision: n/a (no candidates)")
        else:
            print(f"  precision: {result['precision']:.3f}  ({result['matched_candidates']}/{result['total_candidates']} candidates)")
        print(f"  phantom_count (distractor frames): {result['phantom_count']}")
        print(f"  verdict: {verdict}")

        if args.verbose:
            for r in result["per_frame"]:
                if r["matched"] is not None:
                    print(f"    {r['file']:32s} targets={r['targets']} candidates={r['candidates']} matched={r['matched']}")
                else:
                    print(f"    {r['file']:32s} DISTRACTOR candidates={r['candidates']} phantoms={r['phantoms']}")

        pooled_mt += result["matched_targets"]; pooled_tt += result["total_targets"]
        pooled_mc += result["matched_candidates"]; pooled_tc += result["total_candidates"]
        pooled_phantom += result["phantom_count"]

    pooled_recall = pooled_mt / pooled_tt if pooled_tt else None
    pooled_precision = pooled_mc / pooled_tc if pooled_tc else None
    pooled_verdict = _classify(pooled_recall, pooled_precision, pooled_phantom)

    print("\n=== POOLED (all qualifying games) ===")
    print(f"  recall:    {pooled_recall:.3f}  ({pooled_mt}/{pooled_tt} targets)" if pooled_recall is not None else "  recall: n/a")
    print(f"  precision: {pooled_precision:.3f}  ({pooled_mc}/{pooled_tc} candidates)" if pooled_precision is not None else "  precision: n/a")
    print(f"  phantom_count: {pooled_phantom}")
    if any_inconclusive_warm:
        print("  NOTE: at least one game's cache did not reach 5 confirming warmup frames -- its "
              "per-game numbers above are measured on a cache warmed with FEWER than the pinned "
              "warmup, reported honestly, not treated as a clean same-condition measurement.")
    print(f"\nR1 GATE (pooled): {pooled_verdict} "
          f"(PASS>=({RECALL_BAR},{PRECISION_BAR},0 phantoms); KILL<=({KILL_RECALL},{KILL_PRECISION}))")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
