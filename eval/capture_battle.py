"""Phase-A capture: reach a real battle and capture the frames run #3 never got to — the FIGHT /
PKMN / ITEM / RUN **action menu** and the **move-select** screen (+ cursor positions). The battle
intro text we already have (runs/run3, runs/modes); what's missing is the decision menus.

Robust without fragile A-press timing: we never blindly mash A. We advance text only while the
screen is animating; once it goes STATIC we're waiting for input, and we PROBE with a d-pad press —
at a menu the cursor moves (screen changes), at a plain text box it does nothing. That cleanly tells
"action menu" from "still scrolling text", so we stop exactly at the menu and dwell there to capture.

RAM (in_battle) is read ONLY to know we reached the fight and to label frames — the oracle role,
never fed to a perceiver. Output frames feed the detect_mode/decoder design for the battle policy.

Run: uv run python -m eval.capture_battle
"""
from __future__ import annotations

import glob
import os
import random
import sys

import numpy as np
from pyboy import PyBoy

from games.pokemon_red.memory_map import ADDR_IS_IN_BATTLE, ADDR_MAP_ID, ADDR_X, ADDR_Y
from games.pokemon_red.perceiver import detect_mode
from games.pokemon_red.textbox import FontTable, decode

ROM = sys.argv[1] if len(sys.argv) > 1 else "roms/PokemonRed.gb"
STATE = sys.argv[2] if len(sys.argv) > 2 else "start.state"
OUT = "runs/battle"
BIAS = {38: ["up", "right"], 37: ["down"], 0: ["up"], 40: ["up"]}


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
    try:
        table = FontTable.load()
    except Exception:
        table = None

    n = {"i": 0}

    def press(b: str, hold: int = 8, settle: int = 16):
        pb.button(b, delay=hold)
        pb.tick(hold + settle, render=True)

    def frame():
        return pb.screen.ndarray.copy()

    def diff(a, b) -> float:
        return float(np.abs(a.astype(np.int16) - b.astype(np.int16)).mean())

    def wait_static(max_ticks: int = 300, win: int = 24, eps: float = 2.0) -> bool:
        """Tick until the screen holds still (< eps) for `win` consecutive ticks — i.e. we're waiting
        for input (a menu or a text box). Cursor blink is < eps so it doesn't break the streak."""
        prev = frame()
        stable = 0
        for _ in range(max_ticks):
            pb.tick(1, render=True)
            cur = pb.screen.ndarray
            d = diff(cur, prev)
            prev = cur.copy()
            if d < eps:
                stable += 1
                if stable >= win:
                    return True
            else:
                stable = 0
        return False

    def capture(label: str):
        n["i"] += 1
        f = frame()
        mode = detect_mode(f)
        text = decode(f, table).replace("\n", " | ") if table is not None else "?"
        path = os.path.join(OUT, f"{n['i']:02d}_{label}_{mode}.png")
        pb.screen.image.save(path)
        print(f"  saved {os.path.basename(path):<32} mode={mode:<8} battle={M[ADDR_IS_IN_BATTLE]}  {text!r}")

    def probe_is_menu() -> bool:
        """At a static screen, does a d-pad press move a cursor (menu) or do nothing (text box)?"""
        before = frame()
        press("down", hold=4, settle=10)
        moved = diff(before, frame()) > eps_probe
        return moved

    eps_probe = 1.5

    # --- 1) navigate to the rival battle (seeded walk; A advances dialog, B declines nickname) ---
    for _ in range(1500):
        if M[ADDR_IS_IN_BATTLE]:
            break
        if rng.random() < 0.40:
            press("a" if rng.random() < 0.5 else "b")
        else:
            mp, x, y = M[ADDR_MAP_ID], M[ADDR_X], M[ADDR_Y]
            d = rng.choice(BIAS.get(mp, []) + ["up", "down", "left", "right"])
            press(d); press(d)
    if not M[ADDR_IS_IN_BATTLE]:
        print("DID NOT REACH BATTLE"); pb.stop(save=False); return 1
    print(f"reached battle (in_battle={M[ADDR_IS_IN_BATTLE]}). clearing intro...")

    # --- 2) advance intro text until a menu appears (static + cursor probe) ---
    at_menu = False
    for attempt in range(10):
        wait_static()
        if probe_is_menu():            # the probe DOWN already moved the cursor -> we're at the menu
            at_menu = True
            print(f"  action menu reached after {attempt+1} settle(s)")
            break
        press("a")                     # plain text box -> advance it
    if not at_menu:
        print("  never reached a menu; capturing whatever is on screen")

    # --- 3) capture the ACTION menu at each cursor position (d-pad doesn't dismiss it) ---
    press("up"); press("left"); wait_static()
    capture("action_fight")            # cursor home = FIGHT (top-left of the 2x2)
    press("right"); wait_static(); capture("action_topright")   # PKMN/PK
    press("down"); wait_static(); capture("action_botright")    # RUN
    press("left"); wait_static(); capture("action_botleft")     # ITEM
    press("up"); press("left"); wait_static()                    # home back to FIGHT

    # --- 4) enter move-select, capture each move-cursor position, then back out ---
    press("a"); wait_static(); capture("move_1")
    press("down"); wait_static(); capture("move_2")
    press("down"); wait_static(); capture("move_3")
    press("up"); press("up"); wait_static()
    press("b"); wait_static(); capture("back_action")

    print("\nframes in", OUT)
    pb.stop(save=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
