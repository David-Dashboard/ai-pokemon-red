"""DEV vs HELD-OUT game split for the cross-game perception-generalization work.

HARD RULE: we NEVER develop, tune, calibrate, or pick thresholds against the HELD-OUT games. They are
touched ONLY at final verification (e.g. eval/cross_game.py as the `--test` set). Data MAY be collected
for them — we just never look at it while building. This is the guard against overfitting the
"generalizable" odometry/perception to the specific games we developed on.

The held-out set is ONE GAME PER PERCEPTION AXIS, so the verification measures generalization across all
four camera/view challenges at once while dev still has an example of each axis:
  follow      -> Crystalis        (real-time, 8-way diagonal — hardest follow variant)
  flip/static -> Zelda LA         (the canonical flip-screen; passing it UNSEEN is the strongest evidence)
  side-scroll -> Super Mario Land (dev keeps Kirby + Metroid II; test on an unseen 3rd side-scroller)
  other view  -> F-1 Race         (pseudo-3D — zero-shot new view)
  3D / 1st-person -> Doom          (ViZDoom my_way_home — a NEW camera model entirely; zero-shot 3D test)

To ADJUST the split, edit HELDOUT below (substring-matched against the ROM filename AND the run-dir name,
case-insensitive — some recorders, e.g. the ViZDoom 3D recorder, write no meta ROM).

NOTE: Cave Noire is now a DEV `fixed` unit (single-screen rooms — walking moves a local sprite, the camera
never scrolls). Do NOT also hold it out, or a dev run would be both dev and held-out (silent leakage).
Taxonomy caveat: `fixed` lumps truly-fixed (Space Invaders) with flip-screen (Zelda LA — discrete screen
transitions); fine for the current scroll-vs-fixed cut, but a finer split is future work.
"""
from __future__ import annotations

import json
import os

# Substrings matched (case-insensitively) against a run's ROM filename (runs/<name>/meta.json -> "rom").
HELDOUT = [
    "Crystalis",            # follow / real-time 8-way
    "Link's Awakening",     # flip-screen (Zelda LA)
    "Super Mario Land",     # side-scroller (ROM to be added)
    "F-1 Race",             # pseudo-3D
    "Doom",                 # 3D first-person (ViZDoom) -- matches the "vizdoom_*" run dir ("doom" substring)
]


def is_heldout_rom(rom_name: str) -> bool:
    """True if a ROM filename belongs to the held-out verification set (never tune on it)."""
    r = (rom_name or "").lower()
    return any(h.lower() in r for h in HELDOUT)


def run_rom(run_dir: str) -> str:
    """The ROM a recorded run used, from runs/<name>/meta.json (\"\" if absent)."""
    try:
        with open(os.path.join(run_dir, "meta.json"), encoding="utf-8") as f:
            return json.load(f).get("rom", "")
    except Exception:
        return ""


def is_heldout_run(run_dir: str) -> bool:
    """True if a recorded run belongs to a held-out game. Checks the meta.json ROM AND the run-dir name
    (some recorders -- e.g. the ViZDoom 3D recorder -- write no meta ROM, so the dir name is the fallback)."""
    return is_heldout_rom(run_rom(run_dir)) or is_heldout_rom(os.path.basename(run_dir.rstrip("/\\")))


def partition(run_dirs):
    """Split run dirs into (dev, heldout) by their ROM. Use dev for ALL development; touch heldout only
    at final verification."""
    dev, held = [], []
    for d in run_dirs:
        (held if is_heldout_run(d) else dev).append(d)
    return dev, held
