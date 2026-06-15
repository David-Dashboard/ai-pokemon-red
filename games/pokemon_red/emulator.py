"""Thin PyBoy wrapper. The ONLY module that imports PyBoy.

Everything else (plugin, memory map, reward) is emulator-agnostic and talks
to the small `Emulator` surface defined here. That boundary is what lets the
plugin be unit-tested against a `FakeEmulator` with no ROM and no PyBoy
installed (see tests/test_pokemon_red.py).

Targets PyBoy >= 2.0. Install: `pip install pyboy` (or
`pip install -r requirements-pokemon.txt`). You must supply your own
legally-obtained Pokémon Red ROM — none is, or will be, bundled here.
"""

from __future__ import annotations

import os
import time
from typing import Optional, Protocol

# The seven inputs a Game Boy exposes (no L/R shoulders on the original).
BUTTONS = ("a", "b", "start", "select", "up", "down", "left", "right")

# The original Game Boy runs at ~59.73 Hz. We pace to this ourselves (see the governor in
# PyBoyEmulator) instead of trusting PyBoy's set_emulation_speed, which we measured to NOT throttle
# across window backends (a null window's tick(120) returned in 16 ms, not ~2 s).
_GB_FPS = 59.7275


def ensure_sdl_dll_path() -> None:
    """Best-effort fallback for PySDL2's DLL discovery.

    On some installs the `sdl2dll` helper package loses its `__init__.py` (e.g.
    after antivirus quarantines files), so PySDL2 can't locate the bundled SDL2
    binaries even though they're present — `import sdl2` then fails with
    "could not find any library for SDL2". If PYSDL2_DLL_PATH is unset, point it
    at the bundled `sdl2dll/dll` folder directly. Harmless when discovery already
    works or SDL isn't installed (needed only for the visible window).
    """
    if os.environ.get("PYSDL2_DLL_PATH"):
        return
    try:
        import sdl2dll  # noqa: F401  (namespace package; we only want its path)

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
                f"ROM not found: {rom_path}\n"
                "Supply your own legally-obtained Pokémon Red ROM (.gb) and pass "
                "its path via --rom. This project bundles no ROM."
            )
        if not headless:
            ensure_sdl_dll_path()  # make the SDL2 window findable if discovery is broken
        try:
            from pyboy import PyBoy
        except ImportError as e:  # pragma: no cover - environment dependent
            raise ImportError(
                "PyBoy is not installed. Run: pip install pyboy\n"
                "(or pip install -r requirements-pokemon.txt)"
            ) from e

        self._pyboy = PyBoy(
            rom_path,
            window="null" if headless else "SDL2",
            sound_emulated=sound,
            sound_volume=100 if sound else 0,
        )
        # Watchable real-time is OUR job, not PyBoy's: any windowed/sound run is paced by the
        # frame-by-frame governor below (see _advance). Headless agent runs stay unbounded.
        self._realtime = (not headless) if realtime is None else realtime
        self._pyboy.set_emulation_speed(0)   # unbounded; we own the wall-clock pacing
        self._next_frame_t: Optional[float] = None
        # Optional MP4 capture of the run; recorded frame-by-frame in _advance, finalized in close().
        # Works with or without a window (recording does not require --sound/--window).
        self._recorder = None
        if record_path:
            from core.recorder import VideoRecorder
            self._recorder = VideoRecorder(record_path, fps=record_fps, scale=record_scale,
                                           src_fps=_GB_FPS)
        # Let the boot/intro settle a little so the first observation is real (unpaced, unrecorded).
        self._pyboy.tick(60, render=True)

    def _advance(self, frames: int, render: bool) -> None:
        """Emulate `frames`. In real-time mode, step ONE frame at a time and sleep to the wall
        clock so motion is watchable AND the audio stays continuous (a bulk tick + sleep would
        starve the sound queue). Headless mode bulk-ticks as fast as possible."""
        frames = max(1, frames)
        rec = self._recorder is not None
        # Bulk-tick only when neither pacing NOR recording needs per-frame access.
        if not self._realtime and not rec:
            self._pyboy.tick(frames, render=render)
            return
        for _ in range(frames):
            self._pyboy.tick(1, render=render or rec)   # recorder needs a fresh framebuffer
            if rec:
                self._recorder.capture(self._pyboy.screen.ndarray)
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
            # Fell well behind (e.g. a slow LLM decision between frames) — re-anchor instead of
            # fast-forwarding to "catch up", which would look like a speed-up.
            self._next_frame_t = time.perf_counter()

    def press(self, button: str, hold_frames: int = 8, settle_frames: int = 16) -> None:
        b = button.lower()
        if b not in BUTTONS:
            raise ValueError(f"unknown button: {button}")
        # PyBoy 2.x: button(name, delay) presses then releases over `delay` frames.
        self._pyboy.button(b, delay=hold_frames)
        self._advance(hold_frames, render=False)
        # Let menus open / text scroll / the character finish a step.
        self._advance(settle_frames, render=True)

    def tick(self, frames: int) -> None:
        self._advance(max(1, frames), render=True)

    def read(self, addr: int) -> int:
        return self._pyboy.memory[addr]

    def save_screen(self, path: str) -> None:
        self._pyboy.screen.image.save(path)

    def screen_ndarray(self):
        """Current frame as an (144, 160, C) uint8 numpy array (a copy, so the live
        framebuffer can't mutate it under the perceiver). Pixels only — the perception
        path's input; no RAM."""
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
            self._recorder.close()   # finalize the MP4 before tearing down the emulator
        try:
            self._pyboy.stop(save=False)
        except Exception:
            pass
