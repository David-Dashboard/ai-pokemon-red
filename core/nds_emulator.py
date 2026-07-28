"""Thin py-desmume wrapper for NDS worlds — the ONLY core module that imports DeSmuME.

Satisfies the same `Emulator` Protocol as `PyBoyEmulator` in gb_emulator.py so the
perception plugin is drop-in reusable. NDS adds extras beyond the GB surface:
  - `touch(x, y)`  — stylus-down at screen coordinates
  - `touch_release()` — lift the stylus
  - `touch_drag(x1, y1, x2, y2, frames)` — stylus-drag between two points over N ticks, built
    entirely out of touch()/touch_release() (no new emulator call), release guaranteed by a
    `finally` and followed by tick(_TOUCH_SETTLE) so the lift reaches the ROM. Exposed as an MCP tool only
    behind NDS_TOUCH_DRAG=1 (world_mcp.py) — off by default, does not alter the frozen NDS tool
    surface (`_NDS_ACTION_TOOLS`/`assert_action_tools_fresh`).

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

# Frames emulated AFTER a stylus lift so the released-stylus state actually reaches the ROM
# (DeSmuME samples input only on cycle()). Defined here — the lowest NDS layer — and imported by
# core/nds_perception_plugin.py's _tap(), so tap and drag can never drift apart.
_TOUCH_SETTLE = 4

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

    def touch_drag(self, x1: int, y1: int, x2: int, y2: int, frames: int = 8) -> None:
        """Stylus-drag from (x1, y1) to (x2, y2) over `frames` ticks, one tick per interpolated
        point. Reuses touch()/touch_release() verbatim -- touch_set_pos moves a HELD point, it does
        not lift it, so a drag is just repeated touch() calls without an intervening release.

        Fills the gap flagged (not patched) during the 4-ROM NDS probe: `touch()` only ever set a
        static point, with no drag/gesture helper for a continuous stylus motion
        (runs/nds3d_probe/FINDINGS.md:216-219 -- Spirit Tracks rail-drawing, RE:DS item drag/combine
        and aiming both need this). `frames` is the caller's coarse speed/smoothness knob; frames=1
        drags straight to the end point in one tick.

        Ends exactly like NDSPerceptionPlugin._tap(): release THEN tick(_TOUCH_SETTLE). DeSmuME
        samples input only on cycle(), so without that trailing tick no released-stylus frame is
        ever emulated and the lift leaks into whatever tool runs next. The release sits in a
        `finally` so an exception mid-drag can never strand the stylus down for the rest of the
        episode (World.call() does not catch, so such an error escapes the primitive entirely).
        """
        frames = max(1, frames)
        try:
            self.touch(x1, y1)
            self.tick(1)
            for i in range(1, frames + 1):
                t = i / frames
                x = round(x1 + (x2 - x1) * t)
                y = round(y1 + (y2 - y1) * t)
                self.touch(x, y)
                self.tick(1)
        finally:
            self.touch_release()
            self.tick(_TOUCH_SETTLE)
