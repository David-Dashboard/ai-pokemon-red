"""Gen-1 textbox decoder — read the on-screen dialog text from PIXELS (the no-leak rule).

Gen-1 renders text on a fixed 8x8 tile grid; the dialog textbox shows two lines at known rows. We
slice the text region into 8x8 cells and template-match each against a glyph table (a static asset
calibrated once from pixels, `gen1_font.json`). The runtime decoder sees ONLY pixels + that asset —
it never touches RAM/VRAM, so the no-leak guarantee is structural (same as the rest of perception).

Decoding is deliberately CONSERVATIVE: an unknown cell decodes to '?' (never a wrong guess), so a
partial glyph table degrades gracefully (some '?') rather than fabricating text — the same honesty
the project demands of perception. Extend coverage with `eval/calibrate_font.py`.

This is the second payoff of the dialog work: the decoded text (a) feeds a "text since your last
decision" transcript for the planner, and (b) grounds location/event semantics (the LLM read its
location wrong in live run #2 — now it can read the actual on-screen words).
"""
from __future__ import annotations

import json
import os
from typing import Optional

import numpy as np

CELL = 8                       # Gen-1 tile size (px)
X0 = 8                         # text starts one tile in from the textbox's left edge
NCELLS = 18                    # text cells per line
LINES = ((112, 120), (128, 136))   # the two dialog text rows (y pixel ranges), standard Gen-1 layout
_ASSET = os.path.join(os.path.dirname(__file__), "gen1_font.json")


def _gray(frame) -> np.ndarray:
    g = np.asarray(frame)
    return g[..., :3].mean(axis=2) if g.ndim == 3 else g.astype(float)


def cells(frame, thresh: float = 140.0) -> list:
    """The 2x18 text cells as binarized 8x8 arrays (dark text = 1), row-major (line0 then line1)."""
    g = _gray(frame)
    out = []
    for (y0, y1) in LINES:
        for c in range(NCELLS):
            x = X0 + c * CELL
            out.append((g[y0:y1, x:x + CELL] < thresh).astype(np.uint8))
    return out


def pack(cell: np.ndarray) -> int:
    """An 8x8 binary cell -> a 64-bit int key (for exact match / Hamming distance)."""
    return int.from_bytes(np.packbits(cell.reshape(-1)).tobytes(), "big")


class FontTable:
    """glyph-key -> char, with an exact-match fast path and a small-Hamming fallback. Built once from
    pixels (calibration) and saved to gen1_font.json; rendering is deterministic, so exact match
    usually hits and the fallback only absorbs the odd edge pixel."""

    def __init__(self, entries: list) -> None:
        self.items = [(int(k), c) for k, c in entries]
        self.exact = {int(k): c for k, c in entries}

    @classmethod
    def load(cls, path: str = _ASSET) -> "FontTable":
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return cls([(e["k"], e["c"]) for e in data])

    def lookup(self, key: int, tol: int = 4) -> Optional[str]:
        ch = self.exact.get(key)
        if ch is not None:
            return ch
        best, best_d = None, 65
        for k, c in self.items:
            d = bin(key ^ k).count("1")
            if d < best_d:
                best_d, best = d, c
        return best if best_d <= tol else None


def decode(frame, table: FontTable, blank: int = 2) -> str:
    """Decode the textbox to text. Blank cells -> spaces; unknown glyphs -> '?'. Returns the (up to)
    two lines joined by a newline, trailing blanks/'?'-runs trimmed; '' when there's no text."""
    cs = cells(frame)
    lines = []
    for li in range(2):
        s = ""
        for ci in range(NCELLS):
            cell = cs[li * NCELLS + ci]
            if int(cell.sum()) < blank:
                s += " "
                continue
            ch = table.lookup(pack(cell))
            s += ch if ch is not None else "?"
        lines.append(s.rstrip())
    return "\n".join(s for s in lines if s).strip()
