"""Drive Kirby from a fresh boot to the base of the early Green Greens pillar (the obstacle the
2026-07-23 hunt got stuck on) using the RLE-compiled human button log as a reliable prefix (it
consistently reaches the pillar by RLE-run ~200, per this session's replay_dump.py experiment),
then save a state there so float-mechanic attempts can iterate without re-driving the prefix
every time. $0, no LLM.
"""
from __future__ import annotations
import os
import sys

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.dirname(__file__))

from core.gb_emulator import PyBoyEmulator
from replay_dump import load_button_runs, ROM

BUTTONS = "D:/ai_pokemon_runs/2026-06-23_kirby_play/buttons.jsonl"
OUT = "C:/Users/Succe/AppData/Local/Temp/claude/E--AI-Personas-10-pokemon-and-chess-and-office/8a4301d3-699a-43aa-b563-0d37f6b22d43/scratchpad/kirby_gb_stage"


def main() -> int:
    runs, _ = load_button_runs(BUTTONS, max_step=800)
    emu = PyBoyEmulator(ROM, headless=True)
    for i, (button, total_frames) in enumerate(runs[:200]):
        if button is None:
            emu.tick(total_frames)
        else:
            emu.press(button, hold_frames=max(1, total_frames - 2), settle_frames=2)
    emu.save_screen(os.path.join(OUT, "at_pillar.png"))
    emu.save_state(os.path.join(OUT, "at_pillar.state"))
    print(f"saved at_pillar.state / .png, frame={emu.frame}")
    emu.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
