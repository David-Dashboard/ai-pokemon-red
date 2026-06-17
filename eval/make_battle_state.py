"""Build a rival-battle .state FIXTURE: navigate (RAM-guided) from start.state to the first rival battle
and save the emulator state at the battle start, so Phase A's battle POLICY can be tested in a SHORT
paid run — under aria's ~45-wake context ceiling — without the long, flaky Pallet->lab navigation that
gated runs #4/#5. RAM is used ONLY to drive the fixture setup + detect the battle (the oracle role); the
agent, in the actual run that loads this state, still sees ONLY pixels.

Run: uv run python -m eval.make_battle_state [rom] [out.state]
"""
from __future__ import annotations

import random
import sys

from games.pokemon_red.emulator import PyBoyEmulator
from games.pokemon_red.memory_map import ADDR_IS_IN_BATTLE, ADDR_MAP_ID

ROM = sys.argv[1] if len(sys.argv) > 1 else "roms/PokemonRed.gb"
OUT = sys.argv[2] if len(sys.argv) > 2 else "rival_battle.state"
SEED_STATE = "start.state"
# Proven per-map bias (from the battle-capture evals): reliably reaches Oak's lab, gets a starter via
# A-mashing through the forced dialog, then triggers the rival battle.
BIAS = {38: ["up", "right"], 37: ["down"], 0: ["up"], 40: ["up"]}


def main() -> int:
    emu = PyBoyEmulator(ROM, headless=True)
    emu.load_state(SEED_STATE)
    M = emu._pyboy.memory
    rng = random.Random(1)

    for _ in range(2500):
        if M[ADDR_IS_IN_BATTLE]:
            break
        if rng.random() < 0.40:
            emu.press("a" if rng.random() < 0.5 else "b")     # mash through Oak's dialog / menus
        else:
            d = rng.choice(BIAS.get(M[ADDR_MAP_ID], []) + ["up", "down", "left", "right"])
            emu.press(d); emu.press(d)                         # turn, then move (Gen-1)

    if not M[ADDR_IS_IN_BATTLE]:
        print("DID NOT REACH BATTLE"); emu.close(); return 1

    emu.settle()                 # let the send-out animation finish -> a stable battle screen
    emu.save_state(OUT)
    print(f"saved rival-battle fixture -> {OUT}  (in_battle={M[ADDR_IS_IN_BATTLE]}, map={M[ADDR_MAP_ID]})")
    emu.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
