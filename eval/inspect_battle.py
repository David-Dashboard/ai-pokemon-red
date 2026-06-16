"""Phase-A data-first inspection: run detect_mode + the textbox decoder over the battle frames we
already have on disk, and dump a classification/decode table. NO ROM/PyBoy needed — pure pixels.

Usage:  uv run python -m eval.inspect_battle
"""
from __future__ import annotations

import glob
import os

import numpy as np
from PIL import Image

from games.pokemon_red.perceiver import detect_mode, _gray
from games.pokemon_red.textbox import FontTable, decode

_RUN3 = sorted(glob.glob(os.path.join("runs", "run3", "frame_0003[5-9]*.png")))
_MODES = sorted(glob.glob(os.path.join("runs", "modes", "*battle*.png")))


def _features(frame) -> dict:
    """The exact region stats detect_mode keys off, so we can see WHY it classified each frame."""
    g = _gray(frame)
    H, W = g.shape
    w = g >= 230
    return {
        "std": round(float(g.std()), 1),
        "right": round(float(w[:, int(W * 0.6):].mean()), 3),
        "bottom": round(float(w[int(H * 0.66):, :].mean()), 3),
        "top": round(float(w[:int(H * 0.4), :].mean()), 3),
        "midright": round(float(w[int(H * 0.167):int(H * 0.62), int(W * 0.7):].mean()), 3),
    }


def main() -> None:
    table = None
    try:
        table = FontTable.load()
    except Exception as e:  # pragma: no cover - asset should exist
        print(f"(font table load failed: {e})")

    for label, paths in (("RUN3 (rival battle tail)", _RUN3), ("MODES captures", _MODES)):
        print(f"\n===== {label} — {len(paths)} frames =====")
        print(f"{'frame':<34}{'mode':<9}{'std':>6}{'top':>7}{'bot':>7}{'rght':>7}{'mdrt':>7}   text")
        for p in paths:
            frame = np.asarray(Image.open(p).convert("RGB"))
            mode = detect_mode(frame)
            f = _features(frame)
            text = decode(frame, table).replace("\n", " | ") if table is not None else "?"
            name = os.path.basename(p)
            print(f"{name:<34}{mode:<9}{f['std']:>6}{f['top']:>7}{f['bottom']:>7}"
                  f"{f['right']:>7}{f['midright']:>7}   {text!r}")


if __name__ == "__main__":
    main()
