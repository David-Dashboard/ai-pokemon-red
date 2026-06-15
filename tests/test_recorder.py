"""VideoRecorder tests — no encoder, no ROM. A fake writer captures appended frames so we can
check the down-sample cadence, the integer upscale, and RGBA->RGB, without imageio/ffmpeg."""
from __future__ import annotations

import numpy as np

from core.recorder import VideoRecorder


class _FakeWriter:
    def __init__(self):
        self.frames = []
        self.closed = False

    def append_data(self, f):
        self.frames.append(np.asarray(f))

    def close(self):
        self.closed = True


def test_downsamples_60_to_30_keeps_every_other_frame():
    w = _FakeWriter()
    r = VideoRecorder("x.mp4", fps=30, scale=1, src_fps=60, writer=w)
    for i in range(6):
        r.capture(np.full((144, 160, 3), i, dtype=np.uint8))
    assert r.written == 3                      # frames 0,2,4 kept
    assert [int(f[0, 0, 0]) for f in w.frames] == [0, 2, 4]


def test_matching_fps_keeps_every_frame():
    w = _FakeWriter()
    r = VideoRecorder("x.mp4", fps=60, scale=1, src_fps=60, writer=w)
    for _ in range(4):
        r.capture(np.zeros((144, 160, 3), dtype=np.uint8))
    assert r.written == 4


def test_integer_upscale_and_rgba_to_rgb():
    w = _FakeWriter()
    r = VideoRecorder("x.mp4", fps=60, scale=2, src_fps=60, writer=w)
    r.capture(np.full((144, 160, 4), 200, dtype=np.uint8))  # RGBA in
    assert w.frames[0].shape == (288, 320, 3)               # 2x upscale, alpha dropped
    assert w.frames[0].dtype == np.uint8


def test_close_finalizes_writer():
    w = _FakeWriter()
    VideoRecorder("x.mp4", writer=w).close()
    assert w.closed


def test_audio_capture_accumulates_full_rate_and_scales_to_int16():
    w = _FakeWriter()
    r = VideoRecorder("x.mp4", fps=30, scale=1, src_fps=60, sample_rate=48000, writer=w)
    r.capture_audio(np.array([[10, -10], [20, -20]], dtype=np.int8))
    r.capture_audio(np.array([[5, 5]], dtype=np.int8))          # every frame, never down-sampled
    pcm = r._audio_int16()
    assert pcm.shape == (3, 2) and pcm.dtype == np.int16
    assert pcm[0, 0] == 10 * 256 and pcm[0, 1] == -10 * 256     # int8 -> int16 (audible)
    r.close()                                                   # injected writer -> no ffmpeg mux
    assert w.closed


def test_no_audio_when_sample_rate_unset():
    r = VideoRecorder("x.mp4", writer=_FakeWriter())
    r.capture_audio(np.zeros((4, 2), dtype=np.int8))            # ignored: audio disabled
    assert r._audio_int16().shape == (0, 2)
