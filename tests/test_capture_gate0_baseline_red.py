"""Tests for tools/capture_gate0_baseline_red.py's pure helpers + real-path safety guard.

The interactive PyBoy/SDL2 loop itself is exercised manually (never in the automated suite -- see
DAVID_BASELINES.md and the PR description): CI machines/agents must never "play" Pokemon Red, per
the HARD LAW that only a human generates the baseline's gameplay. What IS cheap and CI-safe to pin
here is the artifact-path guard and the hash helper, both pure functions with no emulator/window.
"""
from __future__ import annotations

import hashlib

import tools.capture_gate0_baseline_red as m


def test_under_real_path_guard():
    assert m._under_real_path(m.REAL_OUT)
    assert m._under_real_path(m.REAL_OUT + "/nested")
    assert not m._under_real_path(m.REAL_OUT + "_other")
    assert not m._under_real_path("/tmp/scratch")


def test_sha256_file_matches_hashlib(tmp_path):
    p = tmp_path / "sample.bin"
    p.write_bytes(b"gate0-baseline-rig-sample-bytes")
    assert m._sha256_file(str(p)) == hashlib.sha256(p.read_bytes()).hexdigest()
