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
