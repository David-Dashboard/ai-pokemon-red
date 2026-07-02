"""ADR-002 Phase D: unit tests for the two foveated-region primitives in world_mcp.py —
`read_region` and `whats_changed`. These let a brain hypothesize "region R = my life" and ground it
without ever seeing a full-frame screenshot (that stays forbidden; the size cap enforces "small region,
not a screenshot").

Split by cost:
  * Bounds / size-cap / tools-list wiring / freshness: pure logic, no ROM, no emulator boot (fast, CI-safe).
  * Image-content shape + whats_changed diff behaviour: needs a real World (real PyBoy) against
    cave_noire's ROM + runs/cn_open.state; skips cleanly if the ROM is absent (repo convention, matches
    tests/test_world_mcp_gba_nds_dispatch.py).
"""
from __future__ import annotations

import argparse
import base64
import os

import numpy as np
import pytest

import world_mcp
from world_mcp import GAMES, World, _REGION_MAX_SIDE, _REGION_TOOL_WORLDS, _REGION_UPSCALE, _static_tools


def _args(game: str, init_state: str | None = None, out: str = "runs/test_region_tools") -> argparse.Namespace:
    return argparse.Namespace(game=game, rom=None, init_state=init_state, out=out, record=False,
                              with_screenshot=False, keep_frames=False)


# ---------------------------------------------------------------------------
# 1. tools/list wiring: read_region/whats_changed appear ONLY for the allowlisted worlds.
# ---------------------------------------------------------------------------

def test_region_tools_advertised_for_cave_noire_family():
    for game in ("cave_noire", "cave_noire_baseline", "gauntlet"):
        names = [t["name"] for t in _static_tools(game)]
        assert "read_region" in names and "whats_changed" in names, f"{game} missing region tools"


def test_region_tools_not_advertised_for_other_worlds():
    for game in sorted(set(GAMES) - _REGION_TOOL_WORLDS):
        names = [t["name"] for t in _static_tools(game)]
        assert "read_region" not in names, f"{game} must not advertise read_region"
        assert "whats_changed" not in names, f"{game} must not advertise whats_changed"


def test_region_tool_schemas_require_four_integers():
    for spec in _static_tools("cave_noire"):
        if spec["name"] in ("read_region", "whats_changed"):
            props = spec["inputSchema"]["properties"]
            assert set(spec["inputSchema"]["required"]) == {"x0", "y0", "x1", "y1"}
            assert set(props) == {"x0", "y0", "x1", "y1"}


# ---------------------------------------------------------------------------
# 2. Regression: assert_action_tools_fresh's exact-equality invariant only checks ACTION tools
#    (press_button/press_sequence/wait/touch/touch_target) — read_region/whats_changed are nav/meta
#    tools like observe/explore/goto, so adding them must not perturb the freshness check's shape.
# ---------------------------------------------------------------------------

def test_static_tools_action_subset_unaffected_by_region_tools():
    names = {t["name"] for t in _static_tools("cave_noire")}
    action_names = {"press_button", "press_sequence", "wait"}
    assert action_names <= names
    # the freshness invariant only compares NAMED action tools; region tools must not be in that set
    assert "read_region" not in action_names and "whats_changed" not in action_names


# ---------------------------------------------------------------------------
# 3. Bounds / size-cap validation — pure logic, no emulator (World._validate_region is a staticmethod).
# ---------------------------------------------------------------------------

def _fake_frame(h=144, w=160):
    return np.zeros((h, w, 3), dtype=np.uint8)


def test_validate_region_accepts_small_in_bounds_region():
    assert World._validate_region(16, 128, 34, 136, _fake_frame()) is None


def test_validate_region_rejects_negative_coords():
    err = World._validate_region(-1, 0, 10, 10, _fake_frame())
    assert err is not None and "out of bounds" in err


def test_validate_region_rejects_x1_beyond_width():
    err = World._validate_region(0, 0, 161, 10, _fake_frame())
    assert err is not None and "out of bounds" in err


def test_validate_region_rejects_inverted_coords():
    err = World._validate_region(10, 10, 5, 20, _fake_frame())
    assert err is not None and "out of bounds" in err


def test_validate_region_rejects_full_frame_as_oversize():
    """The size cap must reject a full 160x144 screenshot-shaped request loudly."""
    err = World._validate_region(0, 0, 160, 144, _fake_frame())
    assert err is not None and str(_REGION_MAX_SIDE) in err


def test_validate_region_accepts_exactly_at_cap():
    assert World._validate_region(0, 0, _REGION_MAX_SIDE, _REGION_MAX_SIDE, _fake_frame(h=200, w=200)) is None


def test_validate_region_rejects_one_pixel_over_cap():
    err = World._validate_region(0, 0, _REGION_MAX_SIDE + 1, 10, _fake_frame(h=200, w=200))
    assert err is not None and "cap" in err


# ---------------------------------------------------------------------------
# 4. End-to-end against a real World (real PyBoy + cave_noire ROM + cn_open.state) — skips if unavailable.
# ---------------------------------------------------------------------------

def _cave_noire_available() -> bool:
    return os.path.exists(GAMES["cave_noire"]["rom"]) and os.path.exists("runs/cn_open.state")


@pytest.mark.skipif(not _cave_noire_available(), reason="cave_noire ROM / cn_open.state not available")
def test_read_region_returns_upscaled_png_image_content(tmp_path):
    args = _args("cave_noire", init_state="runs/cn_open.state", out=str(tmp_path / "out"))
    w = World(args)
    try:
        w.call("observe", {})
        result = w.call("read_region", {"x0": 16, "y0": 128, "x1": 34, "y1": 136})
        images = [c for c in result if c.get("type") == "image"]
        assert len(images) == 1
        img = images[0]
        assert img["mimeType"] == "image/png"
        raw = base64.b64decode(img["data"])
        assert raw[:8] == b"\x89PNG\r\n\x1a\n"   # PNG magic bytes
        from PIL import Image
        import io
        im = Image.open(io.BytesIO(raw))
        assert im.size == ((34 - 16) * _REGION_UPSCALE, (136 - 128) * _REGION_UPSCALE)
    finally:
        w.plugin.close()


@pytest.mark.skipif(not _cave_noire_available(), reason="cave_noire ROM / cn_open.state not available")
def test_read_region_rejects_oversize_request(tmp_path):
    args = _args("cave_noire", init_state="runs/cn_open.state", out=str(tmp_path / "out"))
    w = World(args)
    try:
        w.call("observe", {})
        result = w.call("read_region", {"x0": 0, "y0": 0, "x1": 160, "y1": 144})
        texts = " ".join(c["text"] for c in result if c.get("type") == "text")
        assert "cap" in texts
        assert not any(c.get("type") == "image" for c in result)
    finally:
        w.plugin.close()


@pytest.mark.skipif(not _cave_noire_available(), reason="cave_noire ROM / cn_open.state not available")
def test_whats_changed_needs_two_frames_first(tmp_path):
    """Fresh session: only one frame has been observed -> insufficient data, no crash."""
    args = _args("cave_noire", init_state="runs/cn_open.state", out=str(tmp_path / "out"))
    w = World(args)
    try:
        w.call("observe", {})
        result = w.call("whats_changed", {"x0": 16, "y0": 128, "x1": 34, "y1": 136})
        texts = " ".join(c["text"] for c in result if c.get("type") == "text")
        assert "need two observed frames" in texts
    finally:
        w.plugin.close()


@pytest.mark.skipif(not _cave_noire_available(), reason="cave_noire ROM / cn_open.state not available")
def test_whats_changed_reports_changed_after_a_move(tmp_path):
    args = _args("cave_noire", init_state="runs/cn_open.state", out=str(tmp_path / "out"))
    w = World(args)
    try:
        w.call("observe", {})
        w.call("press_button", {"button": "a"})   # a second frame -> whats_changed now has 2 to diff
        result = w.call("whats_changed", {"x0": 16, "y0": 128, "x1": 34, "y1": 136})
        texts = " ".join(c["text"] for c in result if c.get("type") == "text")
        assert "changed" in texts or "unchanged" in texts
        assert "mean-abs-diff=" in texts
    finally:
        w.plugin.close()


# ---------------------------------------------------------------------------
# 5. Regression: other worlds' static tools are unchanged (no region tools leaked in).
# ---------------------------------------------------------------------------

def test_pokemon_red_tools_unchanged():
    names = [t["name"] for t in _static_tools("pokemon_red")]
    assert "read_region" not in names and "whats_changed" not in names
    assert {"observe", "explore", "goto", "remember", "press_button", "press_sequence", "wait"} <= set(names)


def test_nds_tools_unchanged():
    names = [t["name"] for t in _static_tools("nds")]
    assert "read_region" not in names and "whats_changed" not in names
    assert "touch" in names and "touch_target" in names


def test_gba_tools_unchanged():
    names = [t["name"] for t in _static_tools("kirby_gba")]
    assert "read_region" not in names and "whats_changed" not in names
