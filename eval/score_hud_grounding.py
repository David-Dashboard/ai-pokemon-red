"""ADR-002 GATE (report `reports/_archive/2026-06-25-adr-002-ontology-discovery.md` section 9) --
score a HYPOTHESIZED region-detector against the RAM `hp` oracle, offline, free, no LLM.

This is the "gate is RUNNABLE" proof for Rung 0 (`reports/_archive/2026-06-25-roadmap-v2-discovery-loop.md`
Phase B/C, gate-first): given recorded frames + their `hp` oracle values, take a candidate
"read region R" detector (representing what a brain would HYPOTHESIZE: "that box is my life") and score
it against the oracle per SECTION 9's two required arms:

  (a) grounds truth   -- the detector's reading correlates with (agrees with) the oracle's hp value
                         across the run.  Metric (this harness): frame-level EXACT-VALUE agreement rate
                         on frames where the oracle hp is in-range (BCD, clamped 0..max_hp).
  (b) rejects a decoy -- handed a plausible-but-wrong region (e.g. the ENEMY counter, a static UI box),
                         the SAME detector machinery must show much WORSE agreement, so a
                         hypothesize->ground->compile loop would discard it.

Pre-stated PASS/FAIL threshold for this harness (ours to pick per SS9/Phase B -- documented, not vibes):
  PASS  = truth-region agreement >= 0.90  AND  decoy-region agreement <= 0.50 (and strictly worse than
          the truth region by >= 0.30 absolute) on the same frame set.
  FAIL  = either arm misses.
This is NOT the full ADR-002 gate (that needs a live brain to HYPOTHESIZE region R over MCP -- Phase D,
paid, out of scope here). This harness proves the SCORING side is runnable and gives an offline baseline
for one hand-written candidate detector standing in for "what a brain might propose."

Data: `runs/2026-06-26_cavenoire_combat_auto/` (frames + ram.bin + oracle.jsonl; gitignored, reproduce by
copying from a machine that has it, or record fresh with `play_cave_noire.py`). Falls back to the tiny
committed fixture `eval/fixtures/cavenoire_hp_oracle/` (2 anchor frames only -- too few to score
agreement meaningfully, but enough to sanity-check the code path end-to-end).

Usage:
    uv run python -m eval.score_hud_grounding --run runs/2026-06-26_cavenoire_combat_auto
    uv run python -m eval.score_hud_grounding --run eval/fixtures/cavenoire_hp_oracle --oracle-from-ram
"""
from __future__ import annotations

import argparse
import glob
import json
import os

import numpy as np
from PIL import Image

WRAM0 = 0xC000
WRAM_LEN = 0x2000
HP_ADDR = 0xC120          # ADR-002 gate life oracle -- BCD (see reports/2026-07-03-adr002-gate-plan.md
                           # for the 0xC120-vs-0xD389 verdict: 0xD389 is WRONG, confirmed against this run)


def _bcd(b: int) -> int:
    return (b >> 4) * 10 + (b & 0x0F)


def _load_oracle_from_ram(run_dir: str, addr: int = HP_ADDR) -> list[int | None]:
    """hp per frame index, decoded BCD, clamped to [0, 10] (None = out-of-range / transition garbage)."""
    ram = np.fromfile(os.path.join(run_dir, "ram.bin"), dtype=np.uint8)
    n = ram.size // WRAM_LEN
    ram = ram[: n * WRAM_LEN].reshape(n, WRAM_LEN)
    col = ram[:, addr - WRAM0]
    out = []
    for b in col:
        v = _bcd(int(b))
        out.append(v if 0 <= v <= 10 else None)
    return out


def _frame_paths(run_dir: str) -> list[str]:
    paths = sorted(glob.glob(os.path.join(run_dir, "frame_*.png")))
    return paths


# --- candidate detector: a hand-written "read the digit(s) in region R" stand-in for a brain hypothesis.
# Deliberately CHEAP/classical (R0 tier): threshold to ink pixels, find the ink bounding box inside the
# hypothesized region, and nearest-match its shape against a small template set built from the SAME run's
# own frames at few known-value anchors (a brain grounding a hypothesis would calibrate this way too --
# few-shot from the oracle-scored consequence of its own guesses, not a pre-built font table).

def _region_ink_bbox(gray: np.ndarray, y0: int, y1: int, x0: int, x1: int, thresh: int = 128):
    box = gray[y0:y1, x0:x1]
    mask = box < thresh
    if not mask.any():
        return None
    ys, xs = np.where(mask)
    return box[ys.min():ys.max() + 1, xs.min():xs.max() + 1]


def _resize_bin(img: np.ndarray, size=(10, 8)) -> np.ndarray:
    im = Image.fromarray((img * 255).astype(np.uint8)) if img.dtype == bool else Image.fromarray(img)
    im = im.convert("L").resize(size, Image.NEAREST)
    arr = np.asarray(im) < 128
    return arr


class RegionDigitDetector:
    """Hypothesize: 'the digit(s) just right of the HUD's left-most label, top status line, = my life.'
    Region R is a FIXED pixel box (no segmentation, per roadmap-v2 Phase B: "no segmentation in Rung 0").
    Calibrates a 0-9 template bank from a few (frame_idx -> known value) anchors, then nearest-neighbor
    matches the ink bbox in R against templates for every frame; two adjacent glyphs (bbox wide enough)
    are read as a 2-digit number."""

    def __init__(self, y0: int, y1: int, x0: int, x1: int, glyph_w: int = 8):
        self.y0, self.y1, self.x0, self.x1 = y0, y1, x0, x1
        self.glyph_w = glyph_w
        self.templates: dict[int, np.ndarray] = {}

    def calibrate(self, frames: list[np.ndarray], anchors: dict[int, int]) -> None:
        """anchors: {frame_index: true_value} -- single-digit anchors only, builds one glyph template
        per distinct digit 0-9 seen. Multi-digit anchors are skipped (can't isolate a lone glyph without
        already knowing digit count -- exactly the segmentation-free constraint)."""
        for idx, val in anchors.items():
            if not (0 <= val <= 9):
                continue
            bbox = _region_ink_bbox(frames[idx], self.y0, self.y1, self.x0, self.x1)
            if bbox is None:
                continue
            self.templates[val] = _resize_bin(bbox)

    def read(self, gray: np.ndarray) -> int | None:
        bbox = _region_ink_bbox(gray, self.y0, self.y1, self.x0, self.x1)
        if bbox is None or not self.templates:
            return None
        w = bbox.shape[1]
        # crude 1-vs-2-digit split: a lone glyph is ~self.glyph_w wide; wider ink = two glyphs side by side
        if w <= self.glyph_w + 2:
            return self._match_glyph(bbox)
        mid = w // 2
        left = bbox[:, :mid]
        right = bbox[:, mid:]
        d1, d2 = self._match_glyph(left), self._match_glyph(right)
        if d1 is None or d2 is None:
            return self._match_glyph(bbox)  # fall back to whole-blob match (won't be great, that's honest)
        return d1 * 10 + d2

    def _match_glyph(self, blob: np.ndarray) -> int | None:
        if blob.size == 0:
            return None
        target = _resize_bin(blob)
        best_d, best_v = None, None
        for v, tmpl in self.templates.items():
            d = int(np.sum(target != tmpl))
            if best_d is None or d < best_d:
                best_d, best_v = d, v
        return best_v


# HP digit region: bottom status bar, "HP" label then the current-HP digit(s) before "/max".
# Pinned from eyeballing runs/2026-06-26_cavenoire_combat_auto frames (see reports/2026-07-03-adr002-gate-plan.md).
HP_REGION = dict(y0=128, y1=136, x0=16, x1=34)
# Decoy region: the ENEMY counter on the same status bar, second line -- a plausible-but-wrong hypothesis
# (Phase A precheck flagged ENEMY count + floor number as the enumerable decoy set).
ENEMY_REGION = dict(y0=136, y1=144, x0=48, x1=66)


def _agreement(oracle: list[int | None], readings: list[int | None]) -> tuple[float, int]:
    agree = total = 0
    for o, r in zip(oracle, readings):
        if o is None:
            continue
        total += 1
        if r is not None and r == o:
            agree += 1
    return (agree / total if total else 0.0), total


def score(run_dir: str, *, calib_frames: list[int] | None = None, max_frames: int | None = None) -> dict:
    paths = _frame_paths(run_dir)
    if max_frames:
        paths = paths[:max_frames]
    grays = [np.asarray(Image.open(p).convert("L")) for p in paths]
    oracle = _load_oracle_from_ram(run_dir)[: len(grays)]

    # calibration anchors: pick a few frames with known single-digit HP from the oracle itself (the
    # detector is SELF-calibrating from the oracle-graded few-shot the hypothesize->ground loop would use;
    # the oracle is the SCORER here, consistent with SS11 -- these anchor frames are not held out from
    # scoring, mirroring how a real brain would bootstrap on a handful of its own early observations).
    if calib_frames is None:
        seen = {}
        for i, v in enumerate(oracle):
            if v is not None and 0 <= v <= 9 and v not in seen:
                seen[v] = i
            if len(seen) >= 6:
                break
        calib_frames = list(seen.values())
        calib_map = seen
    else:
        calib_map = {oracle[i]: i for i in calib_frames if oracle[i] is not None}

    truth_det = RegionDigitDetector(**HP_REGION)
    truth_det.calibrate(grays, {i: oracle[i] for i in calib_frames if oracle[i] is not None and oracle[i] <= 9})

    decoy_det = RegionDigitDetector(**ENEMY_REGION)
    decoy_det.calibrate(grays, {i: oracle[i] for i in calib_frames if oracle[i] is not None and oracle[i] <= 9})

    truth_readings = [truth_det.read(g) for g in grays]
    decoy_readings = [decoy_det.read(g) for g in grays]

    truth_agree, truth_n = _agreement(oracle, truth_readings)
    decoy_agree, decoy_n = _agreement(oracle, decoy_readings)

    return {
        "run": run_dir, "n_frames": len(grays), "n_scored_truth": truth_n, "n_scored_decoy": decoy_n,
        "calib_frames": calib_frames, "calib_map": calib_map,
        "truth_agreement": truth_agree, "decoy_agreement": decoy_agree,
    }


TRUTH_THRESHOLD = 0.90
DECOY_MAX = 0.50
DECOY_GAP_MIN = 0.30


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", default="runs/2026-06-26_cavenoire_combat_auto")
    ap.add_argument("--max-frames", type=int, default=None)
    args = ap.parse_args()

    if not os.path.isdir(args.run):
        print(f"run dir not found: {args.run}\n"
              "This harness needs recorded frames + ram.bin (gitignored). Reproduce via:\n"
              "  uv run python play_cave_noire.py --rom <cave-noire.gb> --steps 2000 --brain scripted "
              "--out runs/<name>\n"
              "or copy an existing recording that has ram.bin + frame_*.png.")
        return 1

    result = score(args.run, max_frames=args.max_frames)
    print(f"run: {result['run']}  frames: {result['n_frames']}")
    print(f"calibration anchors (frame->hp): {result['calib_map']}")
    print(f"\nTRUTH region {HP_REGION}: agreement={result['truth_agreement']:.3f} "
          f"({result['n_scored_truth']} scored frames)")
    print(f"DECOY region {ENEMY_REGION}: agreement={result['decoy_agreement']:.3f} "
          f"({result['n_scored_decoy']} scored frames)")

    arm_a = result["truth_agreement"] >= TRUTH_THRESHOLD
    arm_b = (result["decoy_agreement"] <= DECOY_MAX
              and (result["truth_agreement"] - result["decoy_agreement"]) >= DECOY_GAP_MIN)
    gate = arm_a and arm_b
    print(f"\nARM (a) grounds truth  (agreement >= {TRUTH_THRESHOLD}): {'PASS' if arm_a else 'FAIL'}")
    print(f"ARM (b) rejects decoy  (decoy <= {DECOY_MAX} AND gap >= {DECOY_GAP_MIN}): {'PASS' if arm_b else 'FAIL'}")
    print(f"\nGATE: {'PASS' if gate else 'FAIL'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
