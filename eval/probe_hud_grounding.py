"""Offline ADR-002 gate smoke-test (fixture A = Pokemon battle HP).

Validates the grounding LOGIC on the recorded battle BEFORE any live-MCP build:
 - arm (a): read_text(player-HP region) via OCR tracks the RAM oracle (0xD015 BE current HP).
 - consequence (pixels-only, region-independent): the dialog says "Enemy ... used ..." = I took damage
   (read with the existing Gen-1 letter glyph reader — reliable on the dialog box).
 - arm (b): the player-HP region DROPS in step with that consequence, while a decoy region (the static
   player LEVEL) does not co-move -> a region that doesn't track the consequence is discarded.
read_text = the general OCR primitive (RapidOCR); RAM is the SCORER only, never on the wire.

Run in the OCR venv:  <parent>/.venv-ocr/Scripts/python.exe eval/probe_hud_grounding.py
"""
import re
import numpy as np
from PIL import Image
from rapidocr_onnxruntime import RapidOCR

from games.pokemon_red.textbox import FontTable, decode

RUN = "runs/red_battle_agent"
ocr = RapidOCR()
FONT = FontTable.load()
HP_BOX = (88, 76, 120, 90)     # player CURRENT hp (left number)
LVL_BOX = (100, 58, 132, 72)   # player level ":L6" -> a static decoy


def frame(f):
    return Image.open(f"{RUN}/frame_{f:06d}.png").convert("RGB")


def read_box(im, box):
    c = im.crop(box)
    c = c.resize((c.width * 8, c.height * 8), Image.NEAREST)
    r, _ = ocr(np.array(c))
    return " ".join(x[1] for x in (r or []))


def first_int(s):
    m = re.search(r"\d+", s)
    return int(m.group()) if m else None


def level_int(s):
    m = re.search(r"[lL](\d+)", s)
    return int(m.group(1)) if m else None


ram = np.fromfile(f"{RUN}/ram.bin", np.uint8)
n = ram.size // 8192
ram = ram[: n * 8192].reshape(n, 8192)
oracle = ram[:, 0xD015 - 0xC000].astype(int) * 256 + ram[:, 0xD016 - 0xC000]

rows = []
for f in range(70, n):
    im = frame(f)
    hp = first_int(read_box(im, HP_BOX))
    lvl = level_int(read_box(im, LVL_BOX))
    dlg = decode(np.asarray(im), FONT).lower()
    cons = ("enemy" in dlg) and ("used" in dlg)
    rows.append((f, hp, lvl, cons, int(oracle[f])))

# arm (a): OCR HP vs oracle (valid HP-range frames only -> skips the transient glitch)
va = [(f, hp, o) for (f, hp, _l, _c, o) in rows if hp is not None and 0 < o <= 99]
agree = sum(1 for _f, hp, o in va if hp == o)
print(f"arm(a)  read_text(HP) == oracle 0xD015 on {agree}/{len(va)} valid frames ({100*agree//len(va)}%)")

# arm (b): does each candidate region DROP within ~6 frames after a consequence rising-edge?
cons_edges = [r[0] for i, r in enumerate(rows) if r[3] and (i == 0 or not rows[i - 1][3])]


def series(idx):
    return {r[0]: r[idx] for r in rows if r[idx] is not None}


def drops_after(s):
    hits = 0
    for ce in cons_edges:
        before = [s[g] for g in range(ce - 2, ce + 1) if g in s]
        after = [s[g] for g in range(ce + 1, ce + 8) if g in s]
        if before and after and min(after) < max(before):
            hits += 1
    return hits


hp_s, lvl_s = series(1), series(2)
print(f"arm(b)  consequence ('Enemy...used') rising-edge frames: {cons_edges}")
print(f"        read_text(HP)    distinct={sorted(set(hp_s.values()))}  "
      f"drops-after-consequence={drops_after(hp_s)}/{len(cons_edges)}  -> GROUNDED")
print(f"        read_text(LEVEL) distinct={sorted(set(lvl_s.values()))}  "
      f"drops-after-consequence={drops_after(lvl_s)}/{len(cons_edges)}  -> decoy rejected")
