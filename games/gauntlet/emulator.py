"""Thin PyBoy wrapper for Gauntlet II — the ONLY module in this package that imports PyBoy.

A near-copy of games/pokemon_red/emulator.py with the Gen-1 map-WARP fade machinery removed (Gauntlet is
one continuous level, no fade warps). Copied, not imported: a game package may not import a sibling
(tests/test_import_boundaries.py). Targets PyBoy >= 2.0; supply your own legally-obtained ROM.
"""
from __future__ import annotations

import os
import time
from typing import Optional, Protocol

# The seven inputs a Game Boy exposes (a/b + start/select + d-pad). Gauntlet uses the d-pad to move and
# b to FIRE; a/start advance the title/hero-select.
BUTTONS = ("a", "b", "start", "select", "up", "down", "left", "right")

_GB_FPS = 59.7275


def ensure_sdl_dll_path() -> None:
    """Best-effort fallback for PySDL2's DLL discovery (only needed for a visible window)."""
    if os.environ.get("PYSDL2_DLL_PATH"):
        return
    try:
        import sdl2dll  # noqa: F401

        for base in list(getattr(sdl2dll, "__path__", [])):
            dll_dir = os.path.join(base, "dll")
            if os.path.exists(os.path.join(dll_dir, "SDL2.dll")):
                os.environ["PYSDL2_DLL_PATH"] = dll_dir
                return
    except Exception:
        pass


class Emulator(Protocol):
    """The minimal surface the plugin needs. Real and fake both satisfy it."""

    def press(self, button: str, hold_frames: int = 8, settle_frames: int = 16) -> None: ...
    def tick(self, frames: int) -> None: ...
    def read(self, addr: int) -> int: ...
    def save_screen(self, path: str) -> None: ...
    def screen_ndarray(self): ...   # current frame as an (H, W, C) uint8 array — for pixel perception
    def load_state(self, path: str) -> None: ...
    def save_state(self, path: str) -> None: ...
    @property
    def frame(self) -> int: ...
    def close(self) -> None: ...


class PyBoyEmulator:
    """Live PyBoy-backed Game Boy. Wraps version drift behind a small surface."""

    def __init__(self, rom_path: str, headless: bool = True, sound: bool = False,
                 realtime: Optional[bool] = None, record_path: Optional[str] = None,
                 record_fps: int = 30, record_scale: int = 3):
        if not os.path.exists(rom_path):
            raise FileNotFoundError(
                f"ROM not found: {rom_path}\nSupply your own legally-obtained Gauntlet II (.gb) ROM.")
        if not headless:
            ensure_sdl_dll_path()
        try:
            from pyboy import PyBoy
        except ImportError as e:  # pragma: no cover - environment dependent
            raise ImportError("PyBoy is not installed. Run: pip install pyboy") from e

        want_sound = sound or bool(record_path)
        self._pyboy = PyBoy(
            rom_path,
            window="null" if headless else "SDL2",
            sound_emulated=want_sound,
            sound_volume=100 if want_sound else 0,
        )
        self._realtime = (not headless) if realtime is None else realtime
        self._pyboy.set_emulation_speed(0)   # unbounded; we own the wall-clock pacing
        self._next_frame_t: Optional[float] = None
        self._recorder = None
        if record_path:
            from core.recorder import VideoRecorder
            self._recorder = VideoRecorder(record_path, fps=record_fps, scale=record_scale,
                                           src_fps=_GB_FPS,
                                           sample_rate=int(self._pyboy.sound.sample_rate))
        self._pyboy.tick(60, render=True)   # let the boot settle a little (unpaced, unrecorded)

    def _advance(self, frames: int, render: bool) -> None:
        frames = max(1, frames)
        rec = self._recorder is not None
        if not self._realtime and not rec:
            self._pyboy.tick(frames, render=render)
            return
        for _ in range(frames):
            self._pyboy.tick(1, render=render or rec)
            if rec:
                self._recorder.capture(self._pyboy.screen.ndarray)
                self._recorder.capture_audio(self._pyboy.sound.ndarray)
            if self._realtime:
                self._pace_one_frame()

    def _pace_one_frame(self) -> None:
        now = time.perf_counter()
        if self._next_frame_t is None:
            self._next_frame_t = now
        self._next_frame_t += 1.0 / _GB_FPS
        delay = self._next_frame_t - time.perf_counter()
        if delay > 0:
            time.sleep(delay)
        elif delay < -0.25:
            self._next_frame_t = time.perf_counter()

    def press(self, button: str, hold_frames: int = 8, settle_frames: int = 16) -> None:
        b = button.lower()
        if b not in BUTTONS:
            raise ValueError(f"unknown button: {button}")
        self._pyboy.button(b, delay=hold_frames)   # PyBoy 2.x: press+release over `delay` frames
        self._advance(hold_frames, render=False)
        self._advance(settle_frames, render=True)   # let the move/animation finish before we observe

    def tick(self, frames: int) -> None:
        self._advance(max(1, frames), render=True)

    def read(self, addr: int) -> int:
        return self._pyboy.memory[addr]

    def save_screen(self, path: str) -> None:
        self._pyboy.screen.image.save(path)

    def screen_ndarray(self):
        """Current frame as an (144, 160, C) uint8 numpy array (a copy). Pixels only — no RAM."""
        return self._pyboy.screen.ndarray.copy()

    def load_state(self, path: str) -> None:
        with open(path, "rb") as f:
            self._pyboy.load_state(f)

    def save_state(self, path: str) -> None:
        with open(path, "wb") as f:
            self._pyboy.save_state(f)

    @property
    def frame(self) -> int:
        return self._pyboy.frame_count

    def close(self) -> None:
        if self._recorder is not None:
            self._recorder.close()
        try:
            self._pyboy.stop(save=False)
        except Exception:
            pass
