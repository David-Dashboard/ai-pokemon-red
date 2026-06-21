"""Robust start-state generator (diagnostic). Reaches the bedroom, then confirms
overworld control by probing ALL four directions (press twice: turn then move) and
clearing residual dialog with A. Saves when movement is confirmed; falls back to
saving anyway once safely in the bedroom map."""
from __future__ import annotations

import sys
from pyboy import PyBoy
from games.pokemon_red.memory_map import ADDR_MAP_ID, ADDR_X, ADDR_Y

ROM = sys.argv[1] if len(sys.argv) > 1 else "roms/PokemonRed.gb"
OUT = sys.argv[2] if len(sys.argv) > 2 else "start.state"
BEDROOM = 38

pyboy = PyBoy(ROM, window="null")
M = pyboy.memory


def press(b, hold=4, settle=14):
    pyboy.button(b, delay=hold)
    pyboy.tick(hold + settle, render=True)


def pos():
    return (M[ADDR_MAP_ID], M[ADDR_X], M[ADDR_Y])


ADDR_MAXMENU = 0xCC28  # wMaxMenuItem: title menu (NEW GAME/OPTION) => 1; name menu (NEW NAME+presets) => 3

# A-mash the whole intro, EXCEPT when a >=3-item menu is open (a name menu): there,
# DOWN moves the cursor off "NEW NAME" onto a preset and A selects it, so we never
# open the on-screen keyboard. The title/main menu (<=2 items) is left on A so we
# keep "NEW GAME" selected. Stop once the bedroom map is loaded and the player moves.
in_control = False
picked = 0
for k in range(800):
    map_, x, y = pos()
    mm = M[ADDR_MAXMENU]
    if map_ == BEDROOM:
        before = (x, y)
        press("down"); press("down")          # turn then move
        if (M[ADDR_X], M[ADDR_Y]) != before:
            in_control = True
            print(f"CONTROL at round {k}; pos={pos()}")
            break
        press("a")                            # clear any residual text, retry
    elif mm >= 3 and picked < 2:
        press("down"); press("a")             # name menu -> pick first preset
        picked += 1
        print(f"round {k}: name menu (mm={mm}) -> picked preset #{picked}")
    else:
        press("a")
    if k % 40 == 0:
        print(f"round {k}: map={map_} mm={mm} pos=({x},{y}) picked={picked}")

with open(OUT, "wb") as f:
    pyboy.save_state(f)
print(f"saved {OUT}: map={M[ADDR_MAP_ID]} pos=({M[ADDR_X]},{M[ADDR_Y]}) "
      f"in_control={in_control}")
pyboy.stop(save=False)
