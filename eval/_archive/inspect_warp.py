"""Phase B, data-first: does a Gen-1 MAP WARP emit a detectable FADE (a near-uniform frame) in the
intra-action frames? The per-decision frames the perceiver sees miss it (the fade happens BETWEEN
decisions, during the button press + walk), so a fade-based transition detector must sample frames
DURING the press — exactly like `settle` does for battle animations.

This walks out of the house and around, ticking frame-by-frame, and dumps the per-frame screen `std`
around each RAM `map_id` change. RAM is the ORACLE here (it only LABELS where a warp happened); the
signal under test is pixels-only (`std`). If a warp reliably shows a sub-6 std frame that non-warp steps
never do, fade-detection is a clean transition signal.

Run: uv run python -m eval.inspect_warp
"""
from __future__ import annotations

import random
import sys

import numpy as np

from games.pokemon_red.emulator import PyBoyEmulator
from games.pokemon_red.memory_map import ADDR_MAP_ID

ROM = sys.argv[1] if len(sys.argv) > 1 else "roms/PokemonRed.gb"
STATE = sys.argv[2] if len(sys.argv) > 2 else "start.state"

# Proven per-map bias from the battle-capture evals (reliably crossed 38->37->0->40).
BIAS = {38: ["up", "right"], 37: ["down"], 0: ["up"], 40: ["up"]}
DIRS = ["up", "down", "left", "right"]


def main() -> int:
    emu = PyBoyEmulator(ROM, headless=True)
    emu.load_state(STATE)
    pb = emu._pyboy
    M = pb.memory
    rng = random.Random(1)

    def std() -> float:
        g = np.asarray(pb.screen.ndarray)[..., :3].mean(axis=2)
        return float(g.std())

    frame = [0]

    def press_sampled(button: str, hold: int = 8, settle: int = 20) -> list[tuple[int, float, int]]:
        """Mirror PyBoyEmulator.press (button held `hold` frames) but tick one frame at a time so we
        can read the per-frame std + map_id THROUGH the press — the window where a warp fade lives."""
        pb.button(button, delay=hold)
        out = []
        for _ in range(hold + settle):
            pb.tick(1, True)
            frame[0] += 1
            out.append((frame[0], std(), M[ADDR_MAP_ID]))
        return out

    log: list[tuple[int, float, int]] = []
    warps: list[tuple[int, int, int]] = []
    cur_map = M[ADDR_MAP_ID]
    print(f"start map_id={cur_map}")

    while frame[0] < 6000 and len(warps) < 6:
        if rng.random() < 0.35:
            samples = press_sampled("a" if rng.random() < 0.5 else "b")
        else:
            d = rng.choice(BIAS.get(cur_map, []) + DIRS)
            samples = press_sampled(d) + press_sampled(d)   # turn, then move (Gen-1 [d,d])
        for (fi, s, m) in samples:
            log.append((fi, s, m))
            if m != cur_map:
                warps.append((fi, cur_map, m))
                cur_map = m

    print(f"frames={frame[0]}  warps={len(warps)}")
    for (wi, a, b) in warps:
        window = [l for l in log if wi - 14 <= l[0] <= wi + 8]
        mn = min(s for _, s, _ in window)
        flags = "  ".join(f"{s:.0f}{'<' if s < 6 else ''}" for _, s, _ in window)
        print(f"\nWARP @{wi}: map {a}->{b}   min_std={mn:.2f}   (sub-6 fade present: {mn < 6})")
        print(f"   std around warp: {flags}")

    allstd = [s for _, s, _ in log]
    sub6 = sum(1 for s in allstd if s < 6)
    print(f"\noverall std: min={min(allstd):.2f}  median~{sorted(allstd)[len(allstd) // 2]:.2f}  "
          f"max={max(allstd):.2f}")
    print(f"frames with std<6 (fade-like) over the whole run: {sub6}/{len(allstd)}")
    emu.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
