"""Calibrate the Gen-1 glyph table (games/pokemon_red/gen1_font.json) from PIXELS.

The decoder (games/pokemon_red/textbox.py) matches 8x8 textbox cells against this table. We build the
table from a handful of dialog frames whose text we READ off the screen (ground truth) — pixel-only,
no RAM/VRAM. Rendering is deterministic, so a given character's 8x8 bitmap is identical across frames;
calibrating from a few frames generalizes. Unknown glyphs decode to '?', so partial coverage is safe
to ship and easy to extend: add a (frame, line1, line2) tuple below and re-run.

Run: uv run python -m eval.calibrate_font   (needs the captured frames under runs/; see capture_dialog.py)
"""
from __future__ import annotations

import json
import os
from typing import Optional

import numpy as np
from PIL import Image

from games.pokemon_red import textbox as tb

ASSET = os.path.join("games", "pokemon_red", "gen1_font.json")

# (frame, line1, line2) — text read directly off the screen. Stop each line at the real text (omit the
# blinking ▼ "more" arrow). Frames live under runs/ (gitignored); the resulting asset is committed.
SAMPLES = [
    ("runs/dialog/264_nickname_window.png", "give a nickname", "to CHARMANDER?"),
    ("runs/modes/374_ui_candidate_dialog.png", "POKéMON appears,", "your POKéMON can"),
    ("runs/dialog/209_dialog_candidate.png", "Wild POKéMON live", "in tall grass!"),
    ("runs/modes/213_ui_candidate_dialog.png", "You need your own", "POKéMON for your"),
    ("runs/dialog/256_dialog_candidate.png", "This POKéMON is", "really energetic!"),
    ("runs/modes/246_ui_candidate_dialog.png", "have only 3 left,", "but"),
]

# held-out frames (text we know) to check the table generalizes across frames it was NOT built from.
HOLDOUT = [
    ("runs/dialog/240_dialog_candidate.png", "have only 3 left,\nbut you can have"),
]


def _load(p) -> np.ndarray:
    return np.asarray(Image.open(p).convert("RGB"))


def build() -> dict:
    """Map glyph-key -> char from the ground-truth samples. Returns {key:int -> char}."""
    table: dict = {}
    conflicts = 0
    for path, l1, l2 in SAMPLES:
        cs = tb.cells(_load(path))
        for li, line in enumerate((l1, l2)):
            for ci in range(tb.NCELLS):
                ch = line[ci] if ci < len(line) else " "
                cell = cs[li * tb.NCELLS + ci]
                nonblank = int(cell.sum()) >= 2
                if ch == " " or not nonblank:
                    continue
                key = tb.pack(cell)
                if key in table and table[key] != ch:
                    conflicts += 1   # same bitmap, two labels -> a misread/misalignment; keep the first
                    continue
                table.setdefault(key, ch)
    # The blinking ▼ "more text" prompt: learn its glyph -> "" so it's dropped (not a '?') from the
    # transcript. It sits just after the text on line 2 of a frame waiting for A (here 240, cell 16).
    arrow = ("runs/dialog/240_dialog_candidate.png", 1, 17)   # ▼ renders at the fixed bottom-right cell
    if os.path.exists(arrow[0]):
        cs = tb.cells(_load(arrow[0]))
        table.setdefault(tb.pack(cs[arrow[1] * tb.NCELLS + arrow[2]]), "")
    if conflicts:
        print(f"WARNING: {conflicts} glyph conflicts (check the ground-truth strings/alignment)")
    return table


def main() -> int:
    if not all(os.path.exists(p) for p, *_ in SAMPLES):
        print("Calibration frames missing under runs/. Run: uv run python -m eval.capture_dialog")
        return 1
    table = build()
    with open(ASSET, "w", encoding="utf-8") as f:
        json.dump([{"k": k, "c": c} for k, c in sorted(table.items())], f, ensure_ascii=False)
    print(f"wrote {ASSET}: {len(table)} glyphs, chars = {''.join(sorted(set(table.values())))}")

    ft = tb.FontTable.load(ASSET)

    def score(decoded: str, truth: str) -> str:
        d, t = decoded.replace("\n", " "), truth.replace("\n", " ")
        n = max(len(d), len(t))
        hits = sum(1 for a, b in zip(d, t) if a == b)
        return f"{hits}/{n}"

    print("\n-- self (calibration frames) --")
    for path, l1, l2 in SAMPLES:
        got = tb.decode(_load(path), ft)
        print(f"  {score(got, l1 + ' ' + l2):>7}  {got!r}")
    print("\n-- held-out (not in the calibration set) --")
    for path, truth in HOLDOUT:
        got = tb.decode(_load(path), ft)
        print(f"  {score(got, truth):>7}  got={got!r}  want={truth!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
