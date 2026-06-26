"""Build a GENERAL consequence detector empirically, by running across games (held-out set excluded).

A consequence detector is a PIXELS-ONLY "something bad just happened (I took damage)" signal. It is
validated against the game's RAM oracle (the SCORER, never on the wire): does the detector fire exactly
when the oracle scalar DROPS? We report precision/recall per candidate detector, per game, and keep
whichever generalize (likely a small MENU, not one universal detector).

Candidate detectors (cheap pixel ops; numpy only):
  - flash:       a transient whole-frame spike that REVERTS (a hit-flash, not a permanent scene change).
  - local_spike: a large LOCALIZED change (sprite flash / knockback) on an 8x8 grid.
  - text_change: the bottom dialog strip changed a lot (battle/event narration) -- RPG-ish.

Run per game:  UV_PROJECT_ENVIRONMENT=.venv-win UV_NATIVE_TLS=true uv run --frozen \
                 python -m eval.probe_consequence_detector <run-dir> <oracle_hex> <u8|u16|bcd>
Defaults to the Pokemon battle run.
"""
import sys
import numpy as np
from PIL import Image

CELL = 8
W = 3                 # a detector "fires near" a damage event if within +/-W frames


def read_scalar(ram, addr, kind):
    o = addr - 0xC000
    if kind == "u8":
        return ram[:, o].astype(int)
    if kind == "u16":      # little/big both tried by caller; default big-endian
        return ram[:, o].astype(int) * 256 + ram[:, o + 1]
    if kind == "bcd":
        b = ram[:, o]
        return (b >> 4) * 10 + (b & 0xF)
    raise ValueError(kind)


def main():
    run = sys.argv[1] if len(sys.argv) > 1 else "runs/red_battle_agent"
    addr = int(sys.argv[2], 16) if len(sys.argv) > 2 else 0xD015
    kind = sys.argv[3] if len(sys.argv) > 3 else "u16"

    ram = np.fromfile(f"{run}/ram.bin", np.uint8)
    n = ram.size // 8192
    ram = ram[: n * 8192].reshape(n, 8192)
    scalar = read_scalar(ram, addr, kind)

    G = [np.asarray(Image.open(f"{run}/frame_{f:06d}.png").convert("L"), float) for f in range(n)]

    def fd(a, b):
        return float(np.abs(a - b).mean())

    def flash(f):
        if f < 1 or f + 2 >= n:
            return False
        din = fd(G[f - 1], G[f])
        return din > 12 and fd(G[f - 1], G[f + 2]) < 0.5 * din

    def local_spike(f):
        if f < 1:
            return False
        d = np.abs(G[f] - G[f - 1])
        nh, nw = d.shape
        ch, cw = nh // CELL, nw // CELL
        return float(d[: ch * CELL, : cw * CELL].reshape(CELL, ch, CELL, cw).mean((1, 3)).max()) > 35

    def text_change(f):
        if f < 1:
            return False
        return fd(G[f - 1][108:140], G[f][108:140]) > 12

    DET = {"flash": flash, "local_spike": local_spike, "text_change": text_change}

    def valid(v):
        return 0 < v <= 999
    dmg = [f for f in range(1, n) if valid(scalar[f]) and valid(scalar[f - 1]) and scalar[f] < scalar[f - 1]]
    print(f"{run}  oracle 0x{addr:04X} ({kind})  damage events (scalar drops): {dmg}")
    for name, fn in DET.items():
        fired = [f for f in range(n) if fn(f)]
        recall = sum(1 for d in dmg if any(abs(d - x) <= W for x in fired)) / max(1, len(dmg))
        prec = sum(1 for x in fired if any(abs(d - x) <= W for d in dmg)) / max(1, len(fired))
        print(f"  {name:12} fired={len(fired):3}  recall={recall:.2f}  precision={prec:.2f}")


if __name__ == "__main__":
    main()
