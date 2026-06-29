"""Boot-to-gameplay bake-off: blind ladder vs VLM vs OCR+LLM navigator.

Drives one ROM for N steps under one policy and saves a captioned trajectory strip (each tile shows the
button it chose there; the final tile is where it ended up = the verdict to hand-label / eyeball).

  python -m eval.bakeoff gb "roms/Final Fantasy Adventure (USA).gb" ladder out.png
  ... kind in {ladder, vlm, ocr}

Single-environment by design: run it where the emulator + a local llama-server both live (WSL for gb/gba).
"""
from __future__ import annotations

import json
import random
import sys

import numpy as np
from PIL import Image, ImageDraw

from core.modality import detect_modality

N_STEPS = 36
KEEP_EVERY = 6


def _emu(console: str, rom: str):
    if console == "gb":
        from core.gb_emulator import PyBoyEmulator
        return PyBoyEmulator(rom, headless=True), (lambda e: e.screen_ndarray())
    if console == "gba":
        from core.gba_emulator import GBAEmulator
        return GBAEmulator(rom), (lambda e: e.screen_ndarray())
    if console == "nds":
        from core.nds_emulator import DeSmuMEEmulator
        return DeSmuMEEmulator(rom, headless=True), (lambda e: e.screen_ndarray())
    raise SystemExit(f"unknown console {console}")


def _stepper(kind: str):
    """Return f(prev, curr, last_buttons) -> list[str] buttons."""
    if kind == "ladder":
        from core.autoplay import ModalAutoPolicy
        pol = ModalAutoPolicy(random.Random(0), lambda r: ["right"])
        return lambda prev, curr, last: pol.decide(prev, curr, last)[1]
    if kind == "vlm":
        from core.navigators import VLMNavigator
        nav = VLMNavigator()
        return lambda prev, curr, last: [nav.decide(curr)]
    if kind == "ocr":
        from core.navigators import MenuPerceiverNavigator
        nav = MenuPerceiverNavigator()
        return lambda prev, curr, last: [nav.decide(curr)]
    if kind in ("vlm-h", "ocr-h"):
        from core.navigators import HarnessNavigator
        nav = HarnessNavigator(mode="vlm" if kind == "vlm-h" else "ocr")
        return lambda prev, curr, last: [nav.decide(curr)]
    if kind in ("nds-vlm", "nds-ocr"):
        from core.navigators import NDSTouchNavigator
        nav = NDSTouchNavigator(mode="vlm" if kind == "nds-vlm" else "ocr")
        return lambda prev, curr, last: [nav.decide(curr)]
    if kind in ("vlm-react", "ocr-react"):
        from core.navigators import ReActNavigator
        nav = ReActNavigator(mode="vlm" if kind == "vlm-react" else "ocr")
        return lambda prev, curr, last: [nav.decide(curr)]
    if kind == "ladder-llm":
        from core.navigators import LadderLLMNavigator
        nav = LadderLLMNavigator()
        return lambda prev, curr, last: [nav.decide(curr)]
    if kind == "vlm-mem":
        from core.navigators import MemNavigator
        nav = MemNavigator(mode="vlm")
        return lambda prev, curr, last: [nav.decide(curr)]
    if kind == "vlm-prime":
        from core.navigators import VLMNavigator
        nav = VLMNavigator(primed=True)
        return lambda prev, curr, last: [nav.decide(curr)]
    if kind == "ocr-prime":
        from core.navigators import MenuPerceiverNavigator
        nav = MenuPerceiverNavigator(primed=True)
        return lambda prev, curr, last: [nav.decide(curr)]
    if kind == "uitars-nds":
        from core.navigators import UITARSNavigator
        nav = UITARSNavigator(console="nds")
        return lambda prev, curr, last: [nav.decide(curr)]
    if kind == "uitars-gb":
        from core.navigators import UITARSNavigator
        nav = UITARSNavigator(console="gb")
        return lambda prev, curr, last: [nav.decide(curr)]
    if kind == "uitars-gba":
        from core.navigators import UITARSNavigator
        nav = UITARSNavigator(console="gba")
        return lambda prev, curr, last: [nav.decide(curr)]
    raise SystemExit(f"unknown kind {kind}")


def _save_strip(frames, path):
    tiles = [(s, b, Image.fromarray(np.asarray(f)[..., :3].astype("uint8"), "RGB")) for s, f, b in frames]
    cap = 14
    h = max(im.height for _, _, im in tiles) + cap
    w = sum(im.width for _, _, im in tiles) + 2 * (len(tiles) - 1)
    strip = Image.new("RGB", (w, h), (20, 20, 20))
    d = ImageDraw.Draw(strip)
    x = 0
    for s, b, im in tiles:
        d.text((x + 1, 2), f"{s}:{b}", fill=(230, 230, 140))
        strip.paste(im, (x, cap))
        x += im.width + 2
    strip.save(path)


def _label(action) -> str:
    """Human-readable label for a strip caption: str actions pass through; touch tuples compact."""
    if isinstance(action, str):
        return action
    return f"touch{action[1]},{action[2]}"


def main() -> int:
    from core.navigators import apply_action
    console, rom, kind, out = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]
    n_steps = int(sys.argv[5]) if len(sys.argv) > 5 else N_STEPS
    emu, ff = _emu(console, rom)
    step = _stepper(kind)
    prev, last, frames = None, [], []
    try:
        for i in range(n_steps):
            curr = ff(emu)
            buttons = step(prev, curr, last)
            if i % KEEP_EVERY == 0:
                frames.append((i, curr.copy(), "+".join(_label(a) for a in buttons)))
            for action in buttons:
                apply_action(emu, action)
            prev, last = curr, buttons
        frames.append((n_steps, ff(emu), "END"))
        _save_strip(frames, out)
    finally:
        emu.close()
    print(json.dumps({"console": console, "rom": rom.split("/")[-1], "kind": kind, "strip": out}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
