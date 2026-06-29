"""Thin mgba wrapper satisfying the same 9-method Emulator Protocol as PyBoyEmulator.

mgba is imported lazily so the module loads fine without it installed (mirrors PyBoyEmulator's
pattern). GBA ROM address-space: WRAM is 0x02000000–0x0203FFFF (256 KB); for anything outside
WRAM use core.memory[addr] (slower generic path).

mgba API quirks captured in the prior WSL spike (source-built 0.10.2, Python bindings via cffi):
  - `mgba.core.load_path(rom)` returns the Core; must call `.reset()` before first frame.
  - `core.screen` is a native surface; framebuffer bytes via `ffi.buffer(screen.buffer, w*h*4)`.
  - Screen dimensions: GBA native 240×160 (width×height). screen_ndarray returns (160,240,3).
  - `run_frame()` advances exactly one frame (no batch equivalent in the Python binding).
  - `set_keys(raw=BITMASK)` sets the live key state; call with 0 to release all.
  - `save_raw_state()` returns a cffi buffer; serialise with `ffi.buffer(s, len(s))`.
  - `load_raw_state()` takes a cffi buffer; use `ffi.from_buffer(bytes)`.
  - No `.close()` on Core — just del or let it GC.
"""
from __future__ import annotations

import os
from typing import Optional

import numpy as np

# GBA exposes 8 GB-equivalent buttons plus L and R shoulders.
BUTTONS = ("a", "b", "select", "start", "right", "left", "up", "down", "r", "l")

# GBA key bitmasks (from mgba's Python binding docs / GBA BIOS spec).
_BITMASK: dict[str, int] = {
    "a":      0x001,
    "b":      0x002,
    "select": 0x004,
    "start":  0x008,
    "right":  0x010,
    "left":   0x020,
    "up":     0x040,
    "down":   0x080,
    "r":      0x100,
    "l":      0x200,
}

# GBA screen dimensions (pixels).
_GBA_W, _GBA_H = 240, 160


class GBAEmulator:
    """Live mgba-backed GBA emulator satisfying the Emulator Protocol."""

    def __init__(self, rom_path: str):
        if not os.path.exists(rom_path):
            raise FileNotFoundError(
                f"ROM not found: {rom_path}\nSupply your own legally-obtained (.gba) ROM.")
        try:
            import mgba.core
            import mgba.image
            from mgba._pylib import ffi  # cffi bindings exposed by mgba's Python package
        except ImportError as e:
            raise ImportError(
                "mgba Python bindings not installed. "
                "Try: pip install mgba  (Python 3.10+, Linux/macOS wheel) "
                "or source-build mgba 0.10.2 with EReader no-op stubs."
            ) from e

        self._ffi = ffi
        self._core = mgba.core.load_path(rom_path)
        if self._core is None:
            raise RuntimeError(f"mgba could not load ROM: {rom_path}")
        self._screen = mgba.image.Image(_GBA_W, _GBA_H)
        self._core.set_video_buffer(self._screen)
        self._core.reset()
        # Warm-up: let the boot intro settle so the first screen_ndarray isn't blank ROM garbage.
        for _ in range(60):
            self._core.run_frame()

    # ------------------------------------------------------------------
    # Emulator Protocol
    # ------------------------------------------------------------------

    def press(self, button: str, hold_frames: int = 8, settle_frames: int = 16) -> None:
        b = button.lower()
        if b not in _BITMASK:
            raise ValueError(f"unknown GBA button: {button!r}. Valid: {BUTTONS}")
        mask = _BITMASK[b]
        self._core.set_keys(raw=mask)
        for _ in range(hold_frames):
            self._core.run_frame()
        self._core.set_keys(raw=0)
        for _ in range(settle_frames):
            self._core.run_frame()

    def tick(self, frames: int) -> None:
        for _ in range(max(1, frames)):
            self._core.run_frame()

    def read(self, addr: int) -> int:
        """Read one byte from GBA address space. WRAM (0x02000000–0x0203FFFF) uses fast path."""
        if 0x02000000 <= addr <= 0x0203FFFF:
            return self._core.memory.wram.u8[addr - 0x02000000]
        return self._core.memory[addr]

    def screen_ndarray(self):
        """Current frame as a (160, 240, 3) uint8 numpy array — a copy, RGB channels only."""
        ffi = self._ffi
        screen = self._screen
        # The native buffer is RGBA (4 bytes/pixel); drop the alpha channel.
        raw = bytes(ffi.buffer(screen.buffer, _GBA_W * _GBA_H * 4))
        return np.frombuffer(raw, dtype=np.uint8).reshape(_GBA_H, _GBA_W, 4)[:, :, :3].copy()

    def save_screen(self, path: str) -> None:
        from PIL import Image
        arr = self.screen_ndarray()
        Image.fromarray(arr, "RGB").save(path)

    def save_state(self, path: str) -> None:
        ffi = self._ffi
        s = self._core.save_raw_state()
        with open(path, "wb") as f:
            f.write(bytes(ffi.buffer(s, len(s))))

    def load_state(self, path: str) -> None:
        # mgba raw state restores CPU + RAM (frame_counter reverts correctly).
        # The video framebuffer is NOT part of the state — it updates on the next run_frame().
        ffi = self._ffi
        with open(path, "rb") as f:
            data = f.read()
        self._core.load_raw_state(ffi.from_buffer(data))

    @property
    def frame(self) -> int:
        return self._core.frame_counter

    def close(self) -> None:
        # mgba Core has no explicit close; release the reference.
        try:
            del self._core
        except Exception:
            pass
