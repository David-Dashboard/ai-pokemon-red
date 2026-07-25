"""Final falsification checks on the 4 surviving candidates (0xD19F, 0xD3A9, 0xD3BA, 0xD3CD):
  1. pause (press start) doesn't change them
  2. survives an explicit save -> NEW emulator instance -> load -> re-read round-trip
  3. fresh-boot (pre-game, title screen) reading, for context
$0, no LLM.
"""
from __future__ import annotations
import os
import sys

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
sys.path.insert(0, REPO)

from core.gb_emulator import PyBoyEmulator

PRIMARY = "E:/AI_Personas/10_pokemon_and_chess_and_office/ai-pokemon-red"
ROM = PRIMARY + "/roms/Kirby's Dream Land (USA, Europe).gb"
CAND = {"D19F": 0xD19F, "D3A9": 0xD3A9, "D3BA": 0xD3BA, "D3CD": 0xD3CD}
STAGE1_STATE = PRIMARY + "/runs/kirby_entity.state"
STAGE2_STATE = "D:/ai_pokemon_runs/2026-06-23_kirby_play/checkpoint_01.state"
SCRATCH_STATE = ("C:/Users/Succe/AppData/Local/Temp/claude/E--AI-Personas-10-pokemon-and-chess-and-office/"
                  "8a4301d3-699a-43aa-b563-0d37f6b22d43/scratchpad/kirby_gb_stage/roundtrip.state")


def read_cand(emu):
    return {k: emu.read(a) for k, a in CAND.items()}


def main() -> int:
    print("--- 1. pause (start) on Stage-2 state ---")
    emu = PyBoyEmulator(ROM, headless=True)
    emu.load_state(STAGE2_STATE)
    before = read_cand(emu)
    emu.press("start", hold_frames=8, settle_frames=30)   # open pause menu
    during = read_cand(emu)
    emu.press("start", hold_frames=8, settle_frames=30)   # unpause
    after = read_cand(emu)
    print(f"  before={before}\n  during_pause={during}\n  after_unpause={after}")
    emu.close()

    print("\n--- 2. save/reload round-trip (Stage-1 state) ---")
    emu = PyBoyEmulator(ROM, headless=True)
    emu.load_state(STAGE1_STATE)
    v1 = read_cand(emu)
    emu.save_state(SCRATCH_STATE)
    emu.close()
    emu2 = PyBoyEmulator(ROM, headless=True)
    emu2.load_state(SCRATCH_STATE)
    v2 = read_cand(emu2)
    print(f"  before_save={v1}\n  after_reload_new_instance={v2}\n  match={v1 == v2}")
    emu2.close()

    print("\n--- 3. fresh boot (title screen, no state loaded) ---")
    emu3 = PyBoyEmulator(ROM, headless=True)
    emu3.tick(120)
    v3 = read_cand(emu3)
    print(f"  fresh_boot_title_screen={v3}")
    emu3.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
