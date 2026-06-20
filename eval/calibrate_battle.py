"""Extend the Gen-1 glyph table with BATTLE glyphs (uppercase Pokémon/move names) — pixel-only, NO ROM.

The runtime decoder (textbox.py) is exact 8x8 bitmap-matching: maximally stable for a fixed tile font,
but only as COMPLETE as gen1_font.json. That table was calibrated from early-game DIALOG (lowercase-heavy),
so battle text decodes with '?' (SQUIRTLE -> ?O??RT?E). This completes it the robust way: auto-calibrate
from frames whose battle text is KNOWN with certainty, and accept a frame ONLY if its CURRENT decode already
agrees with the known string on every non-'?' cell — so the alignment is self-verified and a wrong guess
can't poison the table. New glyphs are unioned into the existing asset.

Run: uv run python -m eval.calibrate_battle
"""
from __future__ import annotations

import glob
import json
import os

import numpy as np
from PIL import Image

from games.pokemon_red import textbox as tb

ASSET = os.path.join("games", "pokemon_red", "gen1_font.json")
FRAME_DIRS = ["runs/run8", "runs/run9", "runs/run6b", "runs/battleseq", "runs/battle"]

# Deterministic battle WORDS (Gary's Squirtle, Charmander's + Squirtle's L5 moves, the battle UI). Words
# beat full sentences: Gen-1 wraps a message across the 2 lines at unknown points, but each word sits on
# ONE line at SOME offset. We match a word at every offset and accept only when >=2 already-known cells
# agree (the anchor) — so the alignment is self-verified and a coincidental all-'?' slice can't match.
KNOWN_WORDS = [
    "SQUIRTLE", "CHARMANDER", "SCRATCH", "GROWL", "TACKLE", "TAIL", "WHIP", "WATER", "GUN",
    "DEFENSE", "ATTACK", "SPEED", "GARY", "FIGHT", "ITEM", "PKMN", "RUN", "Enemy",
]
_ANCHOR = 2   # min already-known cells that must agree to trust the offset


def _load(p) -> np.ndarray:
    return np.asarray(Image.open(p).convert("RGB"))


def _decode_lines(cs, ft):
    """Decode the 2 textbox lines from pre-sliced cells `cs`, '?' for unknown glyphs."""
    out = []
    for li in range(2):
        s = ""
        for ci in range(tb.NCELLS):
            cell = cs[li * tb.NCELLS + ci]
            if int(cell.sum()) < 2:
                s += " "
                continue
            ch = ft.lookup(tb.pack(cell), tol=0)   # EXACT-only: an unknown glyph -> '?', never a misread,
            s += ch if ch is not None else "?"      # so the non-'?' self-check below stays trustworthy
        out.append(s)   # full 18-char line (no rstrip) so word offsets are stable
    return out


def main() -> int:
    table = {int(e["k"]): e["c"] for e in json.load(open(ASSET, encoding="utf-8"))}
    before = sorted(set(table.values()))
    ft = tb.FontTable([(k, c) for k, c in table.items()])

    frames = sorted({f for d in FRAME_DIRS for f in glob.glob(os.path.join(d, "*.png"))})
    print(f"scanning {len(frames)} frames for {len(KNOWN_WORDS)} known words...")

    added, conflicts, used = 0, 0, set()
    for path in frames:
        cs = tb.cells(_load(path))
        lines = _decode_lines(cs, ft)
        for li, line in enumerate(lines):
            for word in KNOWN_WORDS:
                w = len(word)
                for off in range(0, tb.NCELLS - w + 1):
                    seg = line[off:off + w]
                    # every non-'?' decoded cell must agree, with >= _ANCHOR already-known agreeing cells
                    anchors, ok = 0, True
                    for dc, ch in zip(seg, word):
                        if dc == "?":
                            continue
                        if dc != ch:
                            ok = False
                            break
                        anchors += 1
                    if not ok or anchors < _ANCHOR:
                        continue
                    used.add((word, off, li))
                    for i, ch in enumerate(word):
                        cell = cs[li * tb.NCELLS + off + i]
                        if int(cell.sum()) < 2:
                            continue
                        key = tb.pack(cell)
                        if key in table:
                            if table[key] != ch:
                                conflicts += 1
                            continue
                        table[key] = ch
                        added += 1

    if conflicts:
        print(f"WARNING: {conflicts} glyph conflicts (a known string was likely wrong) — kept the first")
    with open(ASSET, "w", encoding="utf-8") as f:
        json.dump([{"k": k, "c": c} for k, c in sorted(table.items())], f, ensure_ascii=False)
    after = sorted(set(table.values()))
    new_chars = "".join(c for c in after if c not in before)
    print(f"matched {len(used)} distinct word placements; +{added} glyph keys")
    print(f"chars before: {''.join(before)!r}")
    print(f"chars added : {new_chars!r}")

    # verify: re-decode a few battle frames with the EXTENDED table
    ft2 = tb.FontTable.load(ASSET)
    print("\n-- re-decode check (extended table) --")
    shown = 0
    for path in frames:
        txt = tb.decode(_load(path), ft2).replace("\n", " | ")
        if txt and ("SQUIRTLE" in txt or "TACKLE" in txt or "SCRATCH" in txt or "GROWL" in txt):
            print(f"  {os.path.basename(path)}: {txt!r}")
            shown += 1
            if shown >= 8:
                break
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
