"""VideoRecorder — encode a stream of frames to an MP4.

Game-agnostic: it takes (H, W, C) uint8 arrays and knows nothing about Pokémon (lives in core/,
beside the rest of the agnostic framework). The emulator feeds it the live framebuffer; on close()
it finalizes the file.

Frames arrive at the emulator's native rate (~60 fps); we keep 1 of every N to hit a target fps and
optionally upscale nearest-neighbor (integer scale) so the crisp pixel look survives. The encoder
(imageio + a bundled ffmpeg) is imported LAZILY, so importing this module — and the whole test
suite — never depends on it; a `writer` can also be injected for tests.
"""
from __future__ import annotations

from typing import Any, Optional

import numpy as np


class VideoRecorder:
    def __init__(self, path: str, fps: int = 30, scale: int = 3, src_fps: float = 60.0,
                 writer: Optional[Any] = None) -> None:
        self.path = path
        self.fps = max(1, int(fps))
        self.scale = max(1, int(scale))
        self._every = max(1, round(src_fps / self.fps))   # keep source frames 0, N, 2N, …
        self._seen = 0
        self.written = 0
        if writer is not None:
            self._writer = writer                          # injected (tests) — no encoder needed
        else:
            import imageio                                 # lazy: only when actually recording
            # libx264 + yuv420p = plays in browsers/QuickTime; GB dims (160×144) and any integer
            # upscale stay divisible by 16, so no padding/resize.
            self._writer = imageio.get_writer(
                path, format="FFMPEG", mode="I", fps=self.fps,
                codec="libx264", quality=8, pixelformat="yuv420p", macro_block_size=16)

    def capture(self, frame: Any) -> None:
        """Offer one source frame; kept only if it lands on the down-sample cadence."""
        keep = (self._seen % self._every) == 0
        self._seen += 1
        if not keep:
            return
        rgb = np.asarray(frame)
        if rgb.ndim == 3 and rgb.shape[2] > 3:
            rgb = rgb[:, :, :3]                             # drop alpha (PyBoy hands back RGBA)
        if self.scale > 1:
            rgb = rgb.repeat(self.scale, axis=0).repeat(self.scale, axis=1)
        self._writer.append_data(np.ascontiguousarray(rgb, dtype=np.uint8))
        self.written += 1

    def close(self) -> None:
        try:
            self._writer.close()
        except Exception:
            pass
