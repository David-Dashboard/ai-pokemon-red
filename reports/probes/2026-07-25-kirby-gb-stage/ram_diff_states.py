"""Full-WRAM+HRAM diff across the existing Kirby savestates: three independently-confirmed
STAGE-1 (Green Greens) states + one independently-confirmed STAGE-2 (Castle Lololo) state
(kirby_play/checkpoint_01.state -- confirmed by eye: its frame matches frame_001938.png of the
recorded session, and scanning that session's own frame images shows a "STAGE 2 CASTLE LOLOLO"
title card at frame ~1738, only 200 frames earlier in the SAME monotonic run -- see the report).

Finds every byte address that is CONSTANT across all three Stage-1 samples, constant across the
Stage-2 sample (trivially true, n=1), and DIFFERENT between the two groups. $0, no LLM.
"""
from __future__ import annotations
import os
import sys

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
sys.path.insert(0, REPO)

from core.gb_emulator import PyBoyEmulator

PRIMARY = "E:/AI_Personas/10_pokemon_and_chess_and_office/ai-pokemon-red"
ROM = PRIMARY + "/roms/Kirby's Dream Land (USA, Europe).gb"

STAGE1_STATES = [
    PRIMARY + "/runs/kirby_entity.state",
    PRIMARY + "/runs/kirby_entity2.state",
    "D:/ai_pokemon_runs/2026-06-23_kirby_ramplay/checkpoint_01.state",
]
STAGE2_STATES = [
    "D:/ai_pokemon_runs/2026-06-23_kirby_play/checkpoint_01.state",
]

WRAM_LO, WRAM_HI = 0xC000, 0xE000
HRAM_LO, HRAM_HI = 0xFF80, 0x10000


def dump(state_path: str) -> dict[int, int]:
    emu = PyBoyEmulator(ROM, headless=True)
    emu.load_state(state_path)
    emu.tick(4)
    out = {a: emu.read(a) for a in range(WRAM_LO, WRAM_HI)}
    out.update({a: emu.read(a) for a in range(HRAM_LO, HRAM_HI)})
    emu.close()
    return out


def main() -> int:
    s1_dumps = [dump(p) for p in STAGE1_STATES]
    s2_dumps = [dump(p) for p in STAGE2_STATES]

    addrs = sorted(s1_dumps[0].keys())
    hits = []
    for a in addrs:
        v1s = {d[a] for d in s1_dumps}
        if len(v1s) != 1:
            continue   # not stable within stage-1
        v1 = next(iter(v1s))
        v2s = {d[a] for d in s2_dumps}
        if len(v2s) != 1:
            continue
        v2 = next(iter(v2s))
        if v1 != v2:
            hits.append((a, v1, v2))

    print(f"stage-1 samples: {STAGE1_STATES}")
    print(f"stage-2 samples: {STAGE2_STATES}")
    print(f"{len(hits)} bytes are stable-within-group and differ stage1 vs stage2 (ALL):\n")

    def bcd(b):
        return (b >> 4) * 10 + (b & 0xF)

    # A real stage/level counter should be a SMALL scalar (0-9ish plain, or a valid BCD digit
    # pair), not an arbitrary tile-map byte -- most of the raw hit list is graphics-buffer noise
    # (any of 0-255), so filter to plausible small-int candidates on BOTH sides.
    small = [(a, v1, v2) for a, v1, v2 in hits if v1 <= 9 and v2 <= 9]
    print(f"\n{len(small)} of those are SMALL-INT on both sides (plausible state scalars):\n")
    for a, v1, v2 in small:
        print(f"  0x{a:04X}: stage1={v1} (0x{v1:02X}, bcd={bcd(v1)})   "
              f"stage2={v2} (0x{v2:02X}, bcd={bcd(v2)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
