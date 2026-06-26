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
from games.pokemon_red.textbox import FontTable, battle_subscreen, decode

_RUN3 = sorted(glob.glob(os.path.join("runs", "run3", "frame_0003[5-9]*.png")))
_MODES = sorted(glob.glob(os.path.join("runs", "modes", "*battle*.png")))
# Real action-menu / move-menu / narration captures — the ground truth for the sub-screen split.
_BATTLE = sorted(glob.glob(os.path.join("runs", "battle", "*.png")))
# A naming-keyboard capture reads as 'battle' in detect_mode; confirm battle_subscreen wakes on it.
_KBD = sorted(glob.glob(os.path.join("runs", "modes", "*keyboard*.png")))


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

    groups = (("BATTLE captures (action/move/narration)", _BATTLE),
              ("NAMING-KEYBOARD (should wake -> battle_menu)", _KBD),
              ("RUN3 (rival battle tail)", _RUN3),
              ("MODES captures", _MODES))
    for label, paths in groups:
        print(f"\n===== {label} — {len(paths)} frames =====")
        print(f"{'frame':<34}{'mode':<9}{'subscreen':<12}{'std':>6}{'top':>7}{'bot':>7}"
              f"{'rght':>7}{'mdrt':>7}   text")
        for p in paths:
            frame = np.asarray(Image.open(p).convert("RGB"))
            mode = detect_mode(frame)
            f = _features(frame)
            # The perceiver consults the sub-screen split ONLY in a battle ('battle_text' -> auto-
            # advance vs 'battle' -> wake); '-' marks frames where detect_mode wouldn't reach it.
            sub = (battle_subscreen(frame, table) if (table is not None and mode == "battle") else "-")
            text = decode(frame, table).replace("\n", " | ") if table is not None else "?"
            name = os.path.basename(p)
            print(f"{name:<34}{mode:<9}{sub:<12}{f['std']:>6}{f['top']:>7}{f['bottom']:>7}"
                  f"{f['right']:>7}{f['midright']:>7}   {text!r}")


if __name__ == "__main__":
    main()
