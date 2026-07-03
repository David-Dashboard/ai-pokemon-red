"""Score `core.glyph_cache.GlyphCache` against a replayed Pokemon Red dialog frame sequence -- the
pre-registered GATE 2 for the glyph-read design (`reports/2026-07-05-glyph-read-design.md` section 5,
Gate 2). This is the "recognition" half's own gate: Gate 1 (`eval/score_text_regions.py`) asks "do we
know where to look"; this asks "once we've looked once, do we have to look again."

Fixture: `runs/dialog/*_dialog_candidate.png` + `*_nickname_window.png` -- an existing Pokemon Red
dialog recording (frames already on disk, free/offline, no paid call). Frames are decoded to their
2x18 textbox glyph cells via `games.pokemon_red.textbox.cells` (the existing Gen-1 pixel-geometry
decoder -- reused here ONLY to slice cells consistently, not to identify characters).

SIMULATED BRAIN CONFIRMATION (the design doc's explicit, legitimate stand-in for a live `read_region`
call, section 5): `games/pokemon_red/gen1_font.json` (`games.pokemon_red.textbox.FontTable`, an
already-calibrated ground-truth glyph->char table) plays the oracle for "what would the brain have
reported on first sight of this glyph shape." This is legitimate BECAUSE this gate measures the
CACHE's hit-rate mechanics (does `core.glyph_cache.GlyphCache`'s hashing recognise a recurring glyph
cell and serve it for free), NOT whether a brain can read pixels -- the HUD-grounding gate already
answered that question live (`reports/2026-07-03-adr002-gate-plan.md`). The oracle's key scheme
(`textbox.pack`, an exact 64-bit cell packing) is DELIBERATELY DIFFERENT from the cache's own key
scheme (`GlyphCache.fingerprint`, a tolerant perceptual hash) -- the oracle is a ground-truth reference,
not the thing under test.

PROCEDURE (pinned before running, per the design doc): replay frames in filename order; for each
non-blank glyph cell encountered, if `GlyphCache.lookup` already has a confirmed reading for its
fingerprint, serve free; else "confirm" it now (charge one simulated read against the oracle) and
`GlyphCache.confirm` it. Track, over the frames AFTER the first N=5 CONFIRMING frames (frames that
contributed at least one first-time confirmation), `frac_free = free_lookups / total_glyph_occurrences`
in that post-warmup window, and count SILENT MISMATCHES: any cache hit whose served character disagrees
with the oracle's ground truth for that exact bitmap.

PINNED BAR (decided before running, per the design doc): frac_free >= 0.80 (measured after the first 5
confirming frames) AND 0 silent mismatches. FAIL on either kills or revises the keying scheme before
any live/paid validation -- not tuned post-hoc to pass.

Usage:
    uv run python -m eval.score_glyph_cache
    uv run python -m eval.score_glyph_cache -v
"""
from __future__ import annotations

import argparse
import glob
import os

import numpy as np
from PIL import Image

from core.glyph_cache import GlyphCache
from games.pokemon_red.textbox import FontTable, cells, pack

_DIALOG_DIR = os.path.join(os.path.dirname(__file__), "..", "runs", "dialog")

# Pinned Gate 2 bar (reports/2026-07-05-glyph-read-design.md section 5) -- do not tune to pass.
FRAC_FREE_BAR = 0.80
N_WARMUP_CONFIRMING_FRAMES = 5
_MIN_REAL_CELLS = 4   # a frame needs at least this many non-blank cells to count as "confirming" (matches
                       # textbox.py's own _MIN_TEXT_GLYPHS narration-vs-noise threshold)


def _load_frames(dialog_dir: str = _DIALOG_DIR) -> list[str]:
    files = sorted(glob.glob(os.path.join(dialog_dir, "*.png")))
    return files


def score(dialog_dir: str = _DIALOG_DIR, *, table: FontTable | None = None,
          cache: GlyphCache | None = None) -> dict:
    table = table or FontTable.load()
    cache = cache or GlyphCache()
    files = _load_frames(dialog_dir)

    confirming_frames_seen = 0
    warmup_done = False
    total_occurrences = free_lookups = mismatches = 0
    per_frame = []

    for f in files:
        img = Image.open(f).convert("RGB")
        frame = np.asarray(img)
        frame_cells = cells(frame)

        frame_confirmed_new = 0
        frame_total = frame_free = frame_mismatch = 0
        for cell in frame_cells:
            if int(cell.sum()) < 2:
                continue   # blank cell (matches textbox.decode's own blank threshold) -- not a glyph occurrence
            oracle_char = table.lookup(pack(cell))
            if oracle_char is None:
                continue   # the oracle itself doesn't know this glyph shape -- not scoreable either way

            crop_hash = GlyphCache.fingerprint(cell)
            cached = cache.lookup(crop_hash)

            if warmup_done:
                total_occurrences += 1
            if cached is not None:
                if warmup_done:
                    frame_free += 1
                    if cached != oracle_char:
                        frame_mismatch += 1
                        mismatches += 1
                # Even a cache hit gets reinforced/re-confirmed against the oracle -- a real brain would
                # only re-read on demand, but every occurrence here has a ground-truth answer available,
                # and reinforcing lets a genuine mismatch surface via GlyphCache's own majority-vote
                # self-correction rather than silently trusting the first answer forever.
                cache.confirm(crop_hash, oracle_char)
            else:
                cache.confirm(crop_hash, oracle_char)   # first sight -- charge one simulated read
                frame_confirmed_new += 1
            if warmup_done:
                frame_total += 1

        if not warmup_done and frame_confirmed_new > 0 and sum(int(c.sum()) >= 2 for c in frame_cells) >= _MIN_REAL_CELLS:
            confirming_frames_seen += 1
            if confirming_frames_seen >= N_WARMUP_CONFIRMING_FRAMES:
                warmup_done = True

        per_frame.append({"file": os.path.basename(f), "total": frame_total, "free": frame_free,
                           "mismatch": frame_mismatch})

    frac_free = free_lookups_ratio(free_lookups=sum(r["free"] for r in per_frame),
                                    total=sum(r["total"] for r in per_frame))
    return {
        "frac_free": frac_free,
        "total_occurrences": sum(r["total"] for r in per_frame),
        "free_lookups": sum(r["free"] for r in per_frame),
        "mismatches": mismatches,
        "distinct_glyphs_confirmed": len(cache),
        "per_frame": per_frame,
    }


def free_lookups_ratio(*, free_lookups: int, total: int) -> float | None:
    return free_lookups / total if total else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dialog-dir", default=_DIALOG_DIR)
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()

    result = score(args.dialog_dir)

    if result["frac_free"] is None:
        print("frac_free: n/a (no post-warmup glyph occurrences -- fixture too short)")
    else:
        print(f"frac_free: {result['frac_free']:.3f}  "
              f"({result['free_lookups']}/{result['total_occurrences']} occurrences post-warmup)")
    print(f"mismatches: {result['mismatches']}")
    print(f"distinct glyph shapes confirmed this run: {result['distinct_glyphs_confirmed']}")

    if args.verbose:
        print("\nper-frame (post-warmup only shown with nonzero total):")
        for r in result["per_frame"]:
            if r["total"]:
                print(f"  {r['file']:32s} total={r['total']} free={r['free']} mismatch={r['mismatch']}")

    gate = (result["frac_free"] or 0) >= FRAC_FREE_BAR and result["mismatches"] == 0
    print(f"\nGATE 2: {'PASS' if gate else 'FAIL'} (frac_free>={FRAC_FREE_BAR}, mismatches==0)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
