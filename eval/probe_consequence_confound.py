"""Phase B (ADR-002 gate): measure the consequence-confound frequency.

Of the HP-drop (damage) events in the life oracle 0xD389, how many coincide with a whole-screen
TRANSITION (floor/menu redraw) vs a clean in-gameplay damage frame? This decides whether a pixels-only
"I took damage" consequence (the gate's §9 decoy-rejection arm keystone) is isolable from the existing
corpus or needs a combat-focused recapture. RAM is the SCORER here (offline), never on the wire.

Run: UV_PROJECT_ENVIRONMENT=.venv-win UV_NATIVE_TLS=true uv run python -m eval.probe_consequence_confound
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from PIL import Image

from core.modality import GAMEPLAY_FRAC, modality_signals

RUN = Path("runs/2026-06-26_cavenoire_combat_auto")
HP_ADDR = 0xC120           # current HP, BCD-encoded (validated vs the visible HUD on 2 runs; Phase A's
HP_OFF = HP_ADDR - 0xC000  # 0xD389 was WRONG — its finder tested raw-decimal, but Cave Noire stores HP in BCD)
WRAM = 0x2000
MAX_HP = 10


def main() -> int:
    ram = (RUN / "ram.bin").read_bytes()
    n = len(ram) // WRAM
    hp = [(b >> 4) * 10 + (b & 0xF) for b in (ram[f * WRAM + HP_OFF] for f in range(n))]  # BCD decode
    assert hp[900] == 10 and hp[1400] == 4, f"oracle offset wrong: hp900={hp[900]} hp1400={hp[1400]}"

    valid = lambda v: 0 <= v <= MAX_HP
    drops = [f for f in range(1, n) if valid(hp[f]) and valid(hp[f - 1]) and hp[f] < hp[f - 1]]
    print(f"frames={n}  HP distinct={sorted(set(hp))}  drop events={len(drops)}")

    def frame(f):
        return np.asarray(Image.open(RUN / f"frame_{f:06d}.png").convert("RGB"))

    base = np.array([modality_signals(frame(f - 1), frame(f))["frac_changed"]
                     for f in range(50, n, 53)])
    print(f"baseline frac_changed: median={np.median(base):.2f} p90={np.percentile(base, 90):.2f} "
          f"max={base.max():.2f}  (gameplay thr={GAMEPLAY_FRAC})\n")

    # For each drop, take the MAX change over a +/-3 window (a damage flash may lead/lag the RAM update by a
    # frame). Three-way: TRANSITION (whole-screen redraw), FLASH (localized, candidate clean consequence),
    # INVISIBLE (no pixel correlate at all -> unusable as a consequence, whatever the byte did).
    print(f"{'frame':>6} {'hp':>8} {'win_fdiff':>9} {'win_frac':>8}  class")
    n_trans = n_flash = n_invis = 0
    for f in drops:
        w = [modality_signals(frame(g - 1), frame(g))
             for g in range(max(1, f - 3), min(n, f + 4))]
        fd = max(s["frame_diff"] for s in w)
        fc = max(s["frac_changed"] for s in w)
        if fc >= 0.5:
            cls, n_trans = "TRANSITION", n_trans + 1
        elif fc >= 0.05:
            cls, n_flash = "flash", n_flash + 1
        else:
            cls, n_invis = "INVISIBLE", n_invis + 1
        print(f"{f:>6} {hp[f-1]:>3}->{hp[f]:<3} {fd:>9.1f} {fc:>8.2f}  {cls}")

    print(f"\nof {len(drops)} HP-drops (window +/-3):  TRANSITION={n_trans}  "
          f"flash(localized, candidate clean)={n_flash}  INVISIBLE(no pixel correlate)={n_invis}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
