"""Measure boot-to-gameplay reach for ONE ROM on a given console. Prints one JSON line.

  python -m eval.reach_measure gb  "roms/Kirby's Dream Land (USA, Europe).gb"
  python -m eval.reach_measure nds "roms/nds/New Super Mario Bros. (USA).nds"
  python -m eval.reach_measure gba "roms/gba/Pokemon - Emerald Version (U).gba"

One ROM per process so a frozen ROM can't poison the sweep and emulator singletons (DeSmuME/mgba)
never collide. A shell loop over the corpus aggregates the JSON lines into a table.
"""
from __future__ import annotations

import json
import os
import sys

import numpy as np

from core.reach_gameplay import reach_gameplay
from eval._eval_utils import _is_held_out, _slug

MAX_STEPS = 150


def _save_strip(frames, trace, path) -> None:
    """Tile sampled frames horizontally into one strip (a frozen film-strip of the run) for hand-label.
    Each tile is captioned with its step + the modality the detector THOUGHT it saw, so the labeller can
    spot where the appearance classifier was fooled. frames: list of (step, HxWx(>=3) uint8)."""
    from PIL import Image, ImageDraw
    tiles = []
    for step, f in frames:
        a = np.asarray(f)[..., :3].astype("uint8")   # force 3-channel (PyBoy may hand back RGBA)
        mode = trace[step] if step < len(trace) else "?"
        tiles.append((step, mode, Image.fromarray(a, "RGB")))
    if not tiles:
        return
    cap = 14
    h = max(im.height for _, _, im in tiles) + cap
    w = sum(im.width for _, _, im in tiles) + 2 * (len(tiles) - 1)
    strip = Image.new("RGB", (w, h), (30, 30, 30))
    draw = ImageDraw.Draw(strip)
    x = 0
    for step, mode, im in tiles:
        # caption: step + the modality the DETECTOR thought it saw (so a 'gameplay' caption over a
        # title frame is a visible false positive). 'g' highlighted so reached-claims stand out.
        draw.text((x + 1, 2), f"{step} {mode[:4]}", fill=(120, 255, 120) if mode == "gameplay" else (200, 200, 200))
        strip.paste(im, (x, cap))
        x += im.width + 2
    strip.save(path)


def _make(console: str, rom: str):
    """Return (emulator, frame_fn) for the console."""
    if console == "gb":
        from core.gb_emulator import PyBoyEmulator
        return PyBoyEmulator(rom, headless=True), None
    if console == "gba":
        from core.gba_emulator import GBAEmulator
        return GBAEmulator(rom), None
    if console == "nds":
        from core.nds_emulator import DeSmuMEEmulator
        emu = DeSmuMEEmulator(rom, headless=True)
        # judge modality on the TOP screen (the most common NDS gameplay screen)
        return emu, (lambda e: e.screen_ndarray()[:192])
    raise SystemExit(f"unknown console: {console}")


def main() -> int:
    console, rom = sys.argv[1], sys.argv[2]
    save_png = sys.argv[3] if len(sys.argv) > 3 else None  # save the frame where we stopped, for hand-label
    slug = _slug(os.path.basename(rom)).lower()
    rec = {"console": console, "rom": os.path.basename(rom), "held_out": _is_held_out(slug)}
    emu = None
    try:
        emu, frame_fn = _make(console, rom)
        res = reach_gameplay(emu, max_steps=MAX_STEPS, frame_fn=frame_fn,
                             keep_every=(12 if save_png else 0))
        rec.update(reached=res["reached"], first_gameplay=res["first_gameplay"],
                   steps=res["steps"], stalls=res["stalls"])
        # compact mode histogram for diagnosis
        tr = res["mode_trace"]
        rec["modes"] = {m: tr.count(m) for m in ("gameplay", "static", "menu", "unknown")}
        if save_png and res["frames"]:
            _save_strip(res["frames"], tr, save_png)
    except Exception as e:
        rec["error"] = f"{type(e).__name__}: {e}"
    finally:
        if emu is not None:
            try:
                emu.close()
            except Exception:
                pass
    print(json.dumps(rec))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
