"""VideoRecorder — encode a stream of frames (and optional audio) to an MP4.

Game-agnostic: it takes (H, W, C) uint8 frames and (N, 2) int8 audio chunks and knows nothing about
Pokémon (lives in core/, beside the rest of the agnostic framework). The emulator feeds it the live
framebuffer and the per-frame audio buffer; on close() it finalizes the file.

Video frames arrive at the emulator's native rate (~60 fps); we keep 1 of every N to hit a target
fps and optionally upscale nearest-neighbor (integer scale) so the crisp pixel look survives. Audio
is kept at FULL rate (every frame) so it stays continuous and time-aligned — both streams span the
same wall-clock, so a final ffmpeg mux lines them up. The encoder (imageio + a bundled ffmpeg) is
imported LAZILY, so importing this module — and the whole test suite — never depends on it; a
`writer` can also be injected for tests (which disables the file/mux machinery).
"""
from __future__ import annotations

import os
import subprocess
import wave
from typing import Any, List, Optional

import numpy as np


class VideoRecorder:
    def __init__(self, path: str, fps: int = 30, scale: int = 3, src_fps: float = 60.0,
                 sample_rate: Optional[int] = None, channels: int = 2,
                 writer: Optional[Any] = None) -> None:
        self.path = path
        self.fps = max(1, int(fps))
        self.scale = max(1, int(scale))
        self._every = max(1, round(src_fps / self.fps))   # keep video frames 0, N, 2N, …
        self._seen = 0
        self.written = 0
        self.sample_rate = sample_rate
        self.channels = channels
        self._audio: Optional[List[np.ndarray]] = [] if sample_rate else None
        self._injected = writer is not None
        # With audio we must mux after encoding, so write video to a temp and assemble `path` on
        # close(). Injected-writer (test) mode never touches the filesystem.
        self._video_target = path
        if writer is not None:
            self._writer = writer
        else:
            if sample_rate:
                self._video_target = path + ".video.mp4"
            import imageio  # lazy: only when actually recording
            self._writer = imageio.get_writer(
                self._video_target, format="FFMPEG", mode="I", fps=self.fps,
                codec="libx264", quality=8, pixelformat="yuv420p", macro_block_size=16)

    def capture(self, frame: Any) -> None:
        """Offer one source video frame; kept only on the down-sample cadence."""
        keep = (self._seen % self._every) == 0
        self._seen += 1
        if not keep:
            return
        rgb = np.asarray(frame)
        if rgb.ndim == 3 and rgb.shape[2] > 3:
            rgb = rgb[:, :, :3]                              # drop alpha (PyBoy hands back RGBA)
        if self.scale > 1:
            rgb = rgb.repeat(self.scale, axis=0).repeat(self.scale, axis=1)
        self._writer.append_data(np.ascontiguousarray(rgb, dtype=np.uint8))
        self.written += 1

    def capture_audio(self, samples: Any) -> None:
        """Offer one frame's audio buffer (N, channels) — kept at FULL rate (call every frame)."""
        if self._audio is None:
            return
        self._audio.append(np.array(samples, dtype=np.int8, copy=True))  # buffer is reused -> copy

    def _audio_int16(self) -> np.ndarray:
        """Concatenated audio as 16-bit PCM (PyBoy emits signed int8; scale up so it's audible)."""
        if not self._audio:
            return np.zeros((0, self.channels), dtype=np.int16)
        return (np.concatenate(self._audio, axis=0).astype(np.int16) << 8)

    def close(self) -> None:
        try:
            self._writer.close()
        except Exception:
            pass
        if self._injected or not self._audio:
            return                                           # tests / no-audio: video already at path
        # mux: write the captured audio to a temp WAV, then combine with the temp video into `path`.
        wav = self.path + ".audio.wav"
        try:
            pcm = self._audio_int16()
            with wave.open(wav, "wb") as w:
                w.setnchannels(self.channels)
                w.setsampwidth(2)
                w.setframerate(int(self.sample_rate))
                w.writeframes(pcm.tobytes())
            import imageio_ffmpeg
            ff = imageio_ffmpeg.get_ffmpeg_exe()
            subprocess.run([ff, "-y", "-loglevel", "error", "-i", self._video_target,
                            "-i", wav, "-c:v", "copy", "-c:a", "aac", "-b:a", "128k",
                            "-shortest", self.path], check=True)
            os.remove(self._video_target)
        except Exception:
            # Muxing failed — keep the silent video so the recording isn't lost.
            if self._video_target != self.path and os.path.exists(self._video_target):
                try:
                    os.replace(self._video_target, self.path)
                except OSError:
                    pass
        finally:
            if os.path.exists(wav):
                try:
                    os.remove(wav)
                except OSError:
                    pass
