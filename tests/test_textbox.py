"""Gen-1 textbox decoder tests — pixels -> text via a glyph table (no ROM, synthetic frames)."""

import json

import numpy as np

from games.pokemon_red import textbox as tb

# a recognizable 8x8 'A'-ish glyph (1 = dark pixel)
GLYPH_A = np.array([
    [0, 0, 1, 1, 1, 0, 0, 0],
    [0, 1, 0, 0, 0, 1, 0, 0],
    [0, 1, 0, 0, 0, 1, 0, 0],
    [0, 1, 1, 1, 1, 1, 0, 0],
    [0, 1, 0, 0, 0, 1, 0, 0],
    [0, 1, 0, 0, 0, 1, 0, 0],
    [0, 1, 0, 0, 0, 1, 0, 0],
    [0, 0, 0, 0, 0, 0, 0, 0],
], dtype=np.uint8)


def _white():
    return np.full((144, 160, 3), 255, dtype=np.uint8)


def _frame_with(bits, li=0, ci=0):
    f = _white()
    y0 = tb.LINES[li][0]
    x0 = tb.X0 + ci * tb.CELL
    f[y0:y0 + 8, x0:x0 + 8][bits.astype(bool)] = 0   # paint dark where bits==1
    return f


def _table(frame, ci, ch):
    return tb.FontTable([(tb.pack(tb.cells(frame)[ci]), ch)])


def test_decode_known_glyph():
    f = _frame_with(GLYPH_A, 0, 0)
    assert tb.decode(f, _table(f, 0, "A")) == "A"


def test_blank_textbox_decodes_to_empty_string():
    assert tb.decode(_white(), tb.FontTable([(tb.pack(GLYPH_A), "A")])) == ""


def test_unknown_glyph_is_question_mark_not_a_wrong_guess():
    table = _table(_frame_with(GLYPH_A, 0, 0), 0, "A")   # table knows only 'A'
    solid = np.ones((8, 8), dtype=np.uint8)              # a far-off glyph
    assert tb.decode(_frame_with(solid, 0, 0), table) == "?"


def test_two_lines_join_with_newline():
    f = _white()
    a = _frame_with(GLYPH_A, 0, 0)
    # put 'A' on line0 col0 and line1 col0
    f[tb.LINES[0][0]:tb.LINES[0][0] + 8, tb.X0:tb.X0 + 8][GLYPH_A.astype(bool)] = 0
    f[tb.LINES[1][0]:tb.LINES[1][0] + 8, tb.X0:tb.X0 + 8][GLYPH_A.astype(bool)] = 0
    assert tb.decode(f, _table(a, 0, "A")) == "A\nA"


def test_glyph_mapped_to_empty_string_is_dropped():
    # the blinking ▼ arrow is calibrated to "" so it vanishes from the text (not rendered as '?').
    arrow = np.zeros((8, 8), dtype=np.uint8)
    arrow[1:7, 3:5] = 1
    f = _frame_with(GLYPH_A, 0, 0)
    x1 = tb.X0 + tb.CELL
    f[tb.LINES[0][0]:tb.LINES[0][0] + 8, x1:x1 + 8][arrow.astype(bool)] = 0   # arrow in line0 col1
    table = tb.FontTable([(tb.pack(GLYPH_A), "A"), (tb.pack(arrow), "")])
    assert tb.decode(f, table) == "A"   # 'A' then "" (dropped)


def test_font_table_roundtrips_via_json(tmp_path):
    p = tmp_path / "f.json"
    key = tb.pack(GLYPH_A)
    with open(p, "w", encoding="utf-8") as fh:
        json.dump([{"k": key, "c": "A"}], fh)
    assert tb.FontTable.load(str(p)).lookup(key) == "A"
