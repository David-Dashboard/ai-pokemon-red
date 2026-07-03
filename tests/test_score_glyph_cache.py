"""Unit tests for eval/score_glyph_cache.py -- the Gate 2 scorer. Builds a small SYNTHETIC dialog-frame
sequence + a synthetic FontTable oracle (no dependency on the real runs/dialog/ recording or the real
games/pokemon_red/gen1_font.json, so this test is CI-safe and independent of the actual gate's measured
PASS/FAIL) to pin the replay/warmup/frac_free/mismatch-detection mechanics."""
from __future__ import annotations

import os
import tempfile

import numpy as np
from PIL import Image

from games.pokemon_red.textbox import CELL, LINES, NCELLS, X0, FontTable, pack
from eval.score_glyph_cache import FRAC_FREE_BAR, N_WARMUP_CONFIRMING_FRAMES, score

_GLYPH_A = np.zeros((CELL, CELL), dtype=np.uint8)
_GLYPH_A[1:7, 3] = 1   # a simple vertical-stroke "glyph" shape, binarized (matches textbox.cells' dtype)
_GLYPH_B = np.zeros((CELL, CELL), dtype=np.uint8)
_GLYPH_B[3, 1:7] = 1   # a distinct horizontal-stroke shape


def _distinct_glyph(i: int) -> np.ndarray:
    """A distinct binarized 8x8 "glyph" shape per index i (single-pixel-per-row diagonal stripe,
    shifted by i) -- used to give each warmup frame at least one genuinely NEW shape, mirroring how
    real dialog text introduces new letters across its first several frames (a repeated single shape
    across all warmup frames would only ever confirm once, never satisfying N_WARMUP_CONFIRMING_FRAMES
    -- this is a fixture-construction detail, not a scorer behavior under test)."""
    g = np.zeros((CELL, CELL), dtype=np.uint8)
    g[:, i % CELL] = 1
    g[i % CELL, :] = 1
    return g


def _paint_cell(pixels: np.ndarray, gray_binarized: np.ndarray, x0: int, y0: int) -> None:
    """Paint a binarized 8x8 cell (1=dark) into an RGB frame at (x0, y0), matching textbox.cells'
    `< thresh` convention (dark pixels = text)."""
    block = np.where(gray_binarized[..., None] == 1, 0, 255).astype(np.uint8)
    pixels[y0:y0 + CELL, x0:x0 + CELL, :] = block


def _make_frame(line0_glyphs: list, line1_glyphs: list = ()) -> np.ndarray:
    """A 160x144 GB-sized frame with the given glyph shapes placed left-to-right on the two textbox
    rows (blank cells left white -- matches textbox.py's real dialog layout)."""
    frame = np.full((144, 160, 3), 255, dtype=np.uint8)
    for i, g in enumerate(line0_glyphs):
        _paint_cell(frame, g, X0 + i * CELL, LINES[0][0])
    for i, g in enumerate(line1_glyphs):
        _paint_cell(frame, g, X0 + i * CELL, LINES[1][0])
    return frame


def _write_frames(tmpdir: str, frames: list[np.ndarray]) -> None:
    for i, frame in enumerate(frames):
        Image.fromarray(frame).save(os.path.join(tmpdir, f"{i:03d}_dialog_candidate.png"))


_ALPHABET = {chr(ord("A") + i): _distinct_glyph(i) for i in range(8)}


def _oracle_table() -> FontTable:
    """A synthetic FontTable whose ground truth matches the synthetic glyph shapes exactly (the
    oracle stand-in this scorer treats as 'what the brain would report on first sight')."""
    entries = [(pack(_GLYPH_A), "A"), (pack(_GLYPH_B), "B")]
    entries += [(pack(g), ch) for ch, g in _ALPHABET.items()]
    return FontTable(entries)


def test_repeated_glyphs_are_served_free_after_warmup():
    with tempfile.TemporaryDirectory() as tmp:
        # Each warmup frame introduces one genuinely NEW glyph shape (mirrors real dialog, where each
        # frame typically shows different letters for the first time) so every warmup frame keeps
        # contributing a fresh confirmation, satisfying N_WARMUP_CONFIRMING_FRAMES; then many more
        # frames reuse the SAME small alphabet, which should mostly be served free.
        glyphs = list(_ALPHABET.values())
        warmup_frames = [_make_frame([glyphs[i]] * 5) for i in range(N_WARMUP_CONFIRMING_FRAMES)]
        post_frames = [_make_frame([glyphs[i % len(glyphs)] for i in range(5)]) for _ in range(10)]
        _write_frames(tmp, warmup_frames + post_frames)

        result = score(tmp, table=_oracle_table())
        assert result["mismatches"] == 0
        assert result["frac_free"] >= FRAC_FREE_BAR
        assert result["distinct_glyphs_confirmed"] == N_WARMUP_CONFIRMING_FRAMES


def test_novel_glyph_after_warmup_is_not_free_but_no_mismatch():
    with tempfile.TemporaryDirectory() as tmp:
        glyphs = list(_ALPHABET.values())[:N_WARMUP_CONFIRMING_FRAMES]
        warmup_frames = [_make_frame([g] * 5) for g in glyphs]
        # a frame using a glyph shape NEVER seen in warmup -- must charge a fresh confirmation (not
        # free), but still must not mismatch (it wasn't cached before this).
        novel_frame = _make_frame([_GLYPH_B] * 3)
        _write_frames(tmp, warmup_frames + [novel_frame])

        result = score(tmp, table=_oracle_table())
        assert result["mismatches"] == 0
        assert result["free_lookups"] < result["total_occurrences"]


def test_blank_cells_are_not_counted_as_occurrences():
    with tempfile.TemporaryDirectory() as tmp:
        blank = _make_frame([])   # an all-white frame -- no glyphs at all
        frames = [blank] * (N_WARMUP_CONFIRMING_FRAMES + 2)
        _write_frames(tmp, frames)

        result = score(tmp, table=_oracle_table())
        assert result["frac_free"] is None
        assert result["total_occurrences"] == 0


def test_gate_bar_constants_match_design_doc():
    # Pinned before the cache was scored (reports/2026-07-05-glyph-read-design.md section 5) --
    # regression guard against silently loosening the bar to make a future run pass.
    assert FRAC_FREE_BAR == 0.80
    assert N_WARMUP_CONFIRMING_FRAMES == 5
