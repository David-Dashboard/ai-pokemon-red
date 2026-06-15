"""Capture REAL dialog/menu/choice frames for the step-3 auto-advance + decoder design.

`capture_modes.py` grades detect_mode (overworld vs not); it does NOT give the structure I need to
SAFELY auto-advance dialog: a plain advanceable textbox (press A for more) vs a CHOICE (a YES/NO menu
with a cursor — must NOT be auto-mashed). This driver collects those, plus a numeric feature log so
the thresholds are picked from data (the project rule: look at the data before coding the rule).

It captures, with frames saved as PNGs and per-frame features in dialog_log.jsonl:
  * the START menu (deterministic: a real menu box + the ▶ cursor) — and the cursor at two rows,
  * a window of frames right after the party count goes 0->1 (the 'give a nickname? YES/NO' choice),
  * plain dialog frames met on a seeded walk toward the starter.

RAM (party_count, map, x, y) is used ONLY to time/label captures and as the oracle — never fed to a
perceiver. Run: uv run python -m eval.capture_dialog
"""
from __future__ import annotations

import glob
import json
import os
import random
import sys

import numpy as np
from pyboy import PyBoy

from games.pokemon_red.memory_map import ADDR_MAP_ID, ADDR_PARTY_COUNT, ADDR_X, ADDR_Y

ROM = sys.argv[1] if len(sys.argv) > 1 else "roms/PokemonRed.gb"
STATE = sys.argv[2] if len(sys.argv) > 2 else "start.state"
OUT = "runs/dialog"
BIAS = {38: ["up", "right"], 37: ["down"], 0: ["up"], 40: ["up"]}


def _gray(frame):
    g = np.asarray(frame)
    return g[..., :3].mean(axis=2) if g.ndim == 3 else g.astype(float)


def features(frame, prev) -> dict:
    """Cheap pixel features (no RAM). Regions in GB pixel coords (160 wide, 144 tall, 8px tiles)."""
    g = _gray(frame)
    white = g >= 230
    box = g[96:, :]                       # bottom 6 rows: where the dialog/textbox lives
    rightpanel = white[:, 112:]           # right 6 cols: a menu/choice box sits here (START menu, YES/NO)
    arrow = g[128:140, 140:156]           # bottom-right interior: the ▼ 'more text' prompt blinks here
    d = 0.0 if prev is None else float(np.abs(g.astype(np.int16) - _gray(prev).astype(np.int16)).mean())
    return {
        "bottom_white": round(float(white[96:, :].mean()), 3),
        "bottom_std": round(float(box.std()), 1),       # >0 => text/border drawn in the box
        "right_white": round(float(rightpanel.mean()), 3),
        "arrow_std": round(float(arrow.std()), 1),       # the blinking arrow makes this nonzero
        "arrow_dark": int((arrow < 100).sum()),
        "diff_prev": round(d, 2),                        # ~0 => frame stable (text fully rendered)
    }


def main() -> int:
    os.makedirs(OUT, exist_ok=True)
    for f in glob.glob(os.path.join(OUT, "*.png")):
        os.remove(f)
    pb = PyBoy(ROM, window="null")
    M = pb.memory
    with open(STATE, "rb") as f:
        pb.load_state(f)
    pb.tick(4, render=True)
    rng = random.Random(1)
    log: list[dict] = []
    n = {"i": 0}
    prev = {"f": None}

    def ram():
        return {"map": M[ADDR_MAP_ID], "x": M[ADDR_X], "y": M[ADDR_Y], "party": M[ADDR_PARTY_COUNT]}

    def cap(label: str):
        n["i"] += 1
        frame = pb.screen.ndarray
        rec = {"i": n["i"], "label": label, **features(frame, prev["f"]), **ram()}
        path = os.path.join(OUT, f"{n['i']:03d}_{label}.png")
        pb.screen.image.save(path)
        rec["path"] = path
        prev["f"] = np.asarray(frame).copy()
        log.append(rec)
        return rec

    def press(b: str, hold: int = 8, settle: int = 16):
        pb.button(b, delay=hold)
        pb.tick(hold + settle, render=True)

    # 1) START menu (a real menu box + the cursor) — deterministic from the bedroom state.
    press("start"); cap("menu_start")
    press("down"); cap("menu_start_cursor2")
    press("down"); cap("menu_start_cursor3")
    press("b"); cap("after_menu_close")

    # 2) walk toward the starter; grab dialog frames; densely sample the nickname YES/NO window.
    got_starter = False
    for step in range(1500):
        r = ram()
        if r["party"] >= 1 and not got_starter:
            got_starter = True
            for _ in range(14):                 # the 'give a nickname? YES/NO' choice lives in here
                cap("nickname_window")
                press("a" if rng.random() < 0.5 else "b")
            break
        if rng.random() < 0.40:
            press("a" if rng.random() < 0.5 else "b")
            cap("dialog_candidate")
        else:
            d = rng.choice(BIAS.get(r["map"], []) + ["up", "down", "left", "right"])
            press(d); press(d)

    with open(os.path.join(OUT, "dialog_log.jsonl"), "w", encoding="utf-8") as f:
        for r in log:
            f.write(json.dumps(r) + "\n")
    print(f"got_starter={got_starter}  saved {len(log)} frames in {OUT}/  final RAM: {ram()}")
    pb.stop(save=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
