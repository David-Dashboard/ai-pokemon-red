"""$0 oracle hunt (2026-07-25): dump a screenshot + candidate-byte readout for each available Kirby
savestate, so we know which one (if any) starts past Stage 1 before scripting fresh play. NO LLM.

Run: <venv-python> reports/probes/2026-07-25-kirby-gb-stage/inspect_states.py
"""
from __future__ import annotations
import os
import sys

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
sys.path.insert(0, REPO)

from core.gb_emulator import PyBoyEmulator

# ROM + runs/ live in the PRIMARY checkout (gitignored there, not shared by `git worktree add`) --
# reference by absolute path, read-only, never copy/commit.
PRIMARY = "E:/AI_Personas/10_pokemon_and_chess_and_office/ai-pokemon-red"
ROM = PRIMARY + "/roms/Kirby's Dream Land (USA, Europe).gb"
STATES = [
    PRIMARY + "/runs/kirby_entity.state",
    PRIMARY + "/runs/kirby_entity2.state",
    "D:/ai_pokemon_runs/2026-06-23_kirby_play/checkpoint_01.state",
    "D:/ai_pokemon_runs/2026-06-23_kirby_ramplay/checkpoint_01.state",
]

# prior hunt's candidates + hp
CANDIDATES = {"hp": 0xD086, "cand_a_0xD048": 0xD048, "cand_b_0xD052": 0xD052, "cand_c_0xD3EE": 0xD3EE}

OUT_DIR = "C:/Users/Succe/AppData/Local/Temp/claude/E--AI-Personas-10-pokemon-and-chess-and-office/8a4301d3-699a-43aa-b563-0d37f6b22d43/scratchpad/kirby_gb_stage"


def main() -> int:
    os.makedirs(OUT_DIR, exist_ok=True)
    for state in STATES:
        if not os.path.exists(state):
            print(f"MISSING: {state}")
            continue
        emu = PyBoyEmulator(ROM, headless=True)
        emu.load_state(state)
        emu.tick(4)
        vals = {name: emu.read(addr) for name, addr in CANDIDATES.items()}
        tag = state.replace(":", "").replace("/", "_").replace("\\", "_").replace(".state", "")
        png = os.path.join(OUT_DIR, f"state_{tag}.png")
        emu.save_screen(png)
        print(f"{state}: frame={emu.frame} vals={vals} -> {png}")
        emu.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
