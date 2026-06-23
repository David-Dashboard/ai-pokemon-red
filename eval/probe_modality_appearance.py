"""FAIR cross-game test: can APPEARANCE (CLIP) and/or OCR classify GAMEPLAY vs NOT-GAMEPLAY, and
GENERALIZE to a game it never trained on?  (+ the cheap numpy detector as baseline.)

This exists to PROVE or REFUTE the prior under-proven claim "menu classification by appearance doesn't
generalize across games". Modality (menu/intro vs gameplay) is a COARSE whole-scene task, plausibly a
CLIP strength -- so we give appearance its best shot and follow the data.

Two modes:
  --make-sheets   build montage contact sheets (PIL only; main uv env) for hand-labeling.
  (default)       run the leave-one-GAME-out probe (needs .venv-probe4: open_clip + rapidocr).

LEAKAGE GUARD: all Pokemon runs are ONE unit ("pokemon") -- red_random1 + red_smart1 + kanto1 share a
domain, so splitting them would be same-domain leakage masquerading as cross-game generalization.

  uv run python eval/probe_modality_appearance.py --make-sheets        # generate sheets (then label)
  .venv-probe4\\Scripts\\python.exe eval/probe_modality_appearance.py   # run the probe
"""
from __future__ import annotations

import argparse
import os
import sys

import numpy as np
from PIL import Image, ImageDraw

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

SHEET_DIR = "runs/_modality_sheets"

# Runs to hand-label via montage. Pokemon NOT-class examples come from the red_* cold-boot runs
# (title/name-entry/dialog/fade); kanto1 contributes Pokemon GAMEPLAY via its free oracle labels.
SHEET_RUNS = ["red_random1", "red_smart1", "kirby_auto1", "metroid_auto1", "gauntlet_auto1", "spaceinv_smart1"]


def _run_len(run: str) -> int:
    with open(os.path.join("runs", run, "buttons.jsonl"), encoding="utf-8") as f:
        return sum(1 for _ in f)


def _sample_indices(n: int, k_front: int = 12, k_spread: int = 13, front: int = 600) -> list:
    """Front-loaded + whole-run uniform sample, so titles/menus/intros (early) AND gameplay are present."""
    front = min(front, n - 1)
    a = np.linspace(0, front, k_front)
    b = np.linspace(0, n - 1, k_spread)
    return sorted({int(round(x)) for x in list(a) + list(b)})


def make_sheets(scale: int = 2, cols: int = 5) -> None:
    os.makedirs(SHEET_DIR, exist_ok=True)
    for run in SHEET_RUNS:
        rundir = os.path.join("runs", run)
        if not os.path.isdir(rundir):
            print(f"skip (missing): {run}")
            continue
        n = _run_len(run)
        idxs = _sample_indices(n)
        cw, strip = 160 * scale, 18
        ch = 144 * scale + strip
        rows = (len(idxs) + cols - 1) // cols
        sheet = Image.new("RGB", (cols * cw, rows * ch), (25, 25, 25))
        draw = ImageDraw.Draw(sheet)
        for i, fi in enumerate(idxs):
            fp = os.path.join(rundir, f"frame_{fi:06d}.png")
            if not os.path.exists(fp):
                continue
            im = Image.open(fp).convert("RGB").resize((160 * scale, 144 * scale), Image.NEAREST)
            cx, cy = (i % cols) * cw, (i // cols) * ch
            sheet.paste(im, (cx, cy + strip))
            draw.text((cx + 3, cy + 4), f"{fi}", fill=(255, 255, 0))
        out = os.path.join(SHEET_DIR, f"{run}.png")
        sheet.save(out)
        print(f"{run}: n={n}  {len(idxs)} frames -> {out}")
        print(f"   indices: {idxs}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--make-sheets", action="store_true", help="generate montage sheets for hand-labeling")
    args = ap.parse_args()
    if args.make_sheets:
        make_sheets()
        return 0
    # the probe mode is added after labeling (needs .venv-probe4)
    from eval._modality_probe_run import run_probe  # noqa: WPS433 (lazy; heavy deps)
    return run_probe()


if __name__ == "__main__":
    raise SystemExit(main())
