"""Thin py-desmume wrapper for NDS worlds — the ONLY core module that imports DeSmuME.

Satisfies the same `Emulator` Protocol as `PyBoyEmulator` in gb_emulator.py so the
perception plugin is drop-in reusable. NDS adds two extras beyond the GB surface:
  - `touch(x, y)`  — stylus-down at screen coordinates
  - `touch_release()` — lift the stylus

Screen layout: DeSmuME stacks both NDS screens into one 384×256 RGBX buffer (top 0–191,
bottom 192–383). `screen_ndarray()` returns the full (384, 256, 3) array by default;
pass `screen="top"` or `screen="bottom"` to get a (192, 256, 3) slice instead.

Lazy/guarded import: `import core.nds_emulator` succeeds even when py-desmume is absent —
exactly like gb_emulator.py tolerates missing PyBoy. Do NOT add py-desmume to
pyproject.toml; it is an out-of-band dep (David approves separately).
"""
from __future__ import annotations

import os
from typing import Literal, Optional

import numpy as np

# NDS has 12 inputs: all four face buttons, both shoulders, start/select, four d-pad.
BUTTONS = ("a", "b", "x", "y", "l", "r", "start", "select", "up", "down", "left", "right")

# Map button string → Keys member name (verified via dir(Keys) on the spike venv).
_BUTTON_KEY = {
    "a":      "KEY_A",
    "b":      "KEY_B",
    "x":      "KEY_X",
    "y":      "KEY_Y",
    "l":      "KEY_L",
    "r":      "KEY_R",
    "start":  "KEY_START",
    "select": "KEY_SELECT",
    "up":     "KEY_UP",
    "down":   "KEY_DOWN",
    "left":   "KEY_LEFT",
    "right":  "KEY_RIGHT",
}

_NDS_FPS = 59.8261  # NDS hardware framerate


class DeSmuMEEmulator:
    """Live DeSmuME-backed Nintendo DS. Mirrors PyBoyEmulator's public surface exactly."""

    # Expose the module-level BUTTONS as a class attribute (single source of truth) so
    # PerceptionPlugin._buttons() can discover it via getattr(type(self.emu), "BUTTONS").
    BUTTONS = BUTTONS

    def __init__(self, rom_path: str, headless: bool = True):
        if not os.path.exists(rom_path):
            raise FileNotFoundError(
                f"ROM not found: {rom_path}\nSupply your own legally-obtained (.nds) ROM.")
        try:
            from desmume.emulator import DeSmuME
            from desmume.controls import Keys, keymask  # noqa: F401 — validated here
        except ImportError as e:  # pragma: no cover - environment dependent
            raise ImportError(
                "py-desmume is not installed. Install it in your NDS venv separately.") from e

        self._emu = DeSmuME()
        self._emu.open(rom_path)
        self._frame_count = 0

        # Advance a few frames so the ROM initialises before the caller interacts with it.
        for _ in range(60):
            self._emu.cycle()
        self._frame_count += 60

    # -- Protocol surface (matches gb_emulator.Emulator) -------------------------

    def press(self, button: str, hold_frames: int = 8, settle_frames: int = 16) -> None:
        b = button.lower()
        if b not in _BUTTON_KEY:
            raise ValueError(f"unknown button: {button!r}")
        from desmume.controls import Keys, keymask
        key = getattr(Keys, _BUTTON_KEY[b])
        mask = keymask(key)
        self._emu.input.keypad_add_key(mask)
        self.tick(hold_frames)
        self._emu.input.keypad_rm_key(mask)
        self.tick(settle_frames)

    def tick(self, frames: int) -> None:
        frames = max(1, frames)
        for _ in range(frames):
            self._emu.cycle()
        self._frame_count += frames

    def read(self, addr: int) -> int:
        return self._emu.memory.unsigned[addr]

    def save_screen(self, path: str) -> None:
        from PIL import Image
        arr = self.screen_ndarray()
        Image.fromarray(arr, "RGB").save(path)

    def screen_ndarray(
        self,
        screen: Literal["both", "top", "bottom"] = "both",
    ) -> np.ndarray:
        """Both NDS screens as a uint8 numpy array.

        Default ("both") returns (384, 256, 3) — top screen in rows 0–191,
        bottom (touch) screen in rows 192–383. Pass screen="top" or "bottom"
        for a (192, 256, 3) slice. Always a fresh copy.
        """
        raw = np.frombuffer(bytes(self._emu.display_buffer_as_rgbx()), dtype=np.uint8)
        both = raw[: 256 * 384 * 4].reshape(384, 256, 4)[:, :, :3].copy()
        if screen == "top":
            return both[:192]
        if screen == "bottom":
            return both[192:]
        return both

    def load_state(self, path: str) -> None:
        self._emu.savestate.load_file(path)

    def save_state(self, path: str) -> None:
        self._emu.savestate.save_file(path)

    @property
    def frame(self) -> int:
        return self._frame_count

    def close(self) -> None:
        try:
            self._emu.destroy()
        except Exception:
            pass

    # -- NDS-specific extensions ------------------------------------------------

    def touch(self, x: int, y: int) -> None:
        """Press the stylus at bottom-screen pixel (x, y). Range: 0–255 × 0–191."""
        self._emu.input.touch_set_pos(x, y)

    def touch_release(self) -> None:
        """Lift the stylus."""
        self._emu.input.touch_release()
