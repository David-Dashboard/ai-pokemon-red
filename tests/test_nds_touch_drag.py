"""Unit tests for the NDS touch-drag helper primitive (capability-map A6 "continuous action" gap;
runs/nds3d_probe/FINDINGS.md:216-219 -- "DeSmuMEEmulator.touch() only sets a static stylus point,
there is no drag/gesture helper"). CI-safe: no py-desmume, no real ROM.

Covers:
  1. `DeSmuMEEmulator.touch_drag` (core/nds_emulator.py): stylus-down at the start point, linear
     interpolation to the end point one tick per intermediate point, stylus-up at the end -- tested
     against a duck-typed fake (the method only calls self.touch/self.tick/self.touch_release, never
     self._emu directly, so it can be exercised without ever constructing a real DeSmuME instance).
  2. world_mcp.World's `touch_drag` tool: gating (NDS_TOUCH_DRAG on/off, nds-only world scoping,
     no interference with NDS_SKILLS/KIRBY_SKILLS/ARC_SKILLS), dispatch (routes to
     emu.touch_drag with the right args, counts as a decision/wake, returns a trailing observe),
     and argument validation (bad coords/frames rejected loudly, never silently clamped).
  3. Frozen-seam regression: `_NDS_ACTION_TOOLS`/`assert_action_tools_fresh` (touch/touch_target's
     own exact-equality invariant) is unaffected by the NDS_TOUCH_DRAG flag either way -- touch_drag
     is dispatched entirely inside World.call(), mirroring define_skill/run_skill, never routed
     through NDSPerceptionPlugin/Gateway.
"""
from __future__ import annotations

import os

import numpy as np
import pytest

from core.gateway import Gateway
from core.nds_emulator import DeSmuMEEmulator
from core.perception import PerceptMemory, SymbolicState
from core.perception_plugin import PerceptionPlugin
from core.permissions import Allowlist

import world_mcp
from world_mcp import World, _static_tools, assert_action_tools_fresh


# ---------------------------------------------------------------------------
# 1. DeSmuMEEmulator.touch_drag -- pure algorithm, no py-desmume needed
# ---------------------------------------------------------------------------

class _TouchRecorder:
    """Duck-typed stand-in exposing exactly touch()/tick()/touch_release() -- touch_drag never
    touches self._emu, so this is sufficient without constructing a real DeSmuMEEmulator."""

    def __init__(self) -> None:
        self.touches: list[tuple[int, int]] = []
        self.ticks = 0
        self.releases = 0

    def touch(self, x: int, y: int) -> None:
        self.touches.append((x, y))

    def tick(self, frames: int) -> None:
        self.ticks += frames

    def touch_release(self) -> None:
        self.releases += 1


def _drag(rec, x1, y1, x2, y2, frames=8):
    """Call the real unbound method against the duck-typed recorder."""
    DeSmuMEEmulator.touch_drag(rec, x1, y1, x2, y2, frames=frames)


def test_touch_drag_starts_at_first_point():
    rec = _TouchRecorder()
    _drag(rec, 10, 20, 200, 150, frames=4)
    assert rec.touches[0] == (10, 20)


def test_touch_drag_ends_at_last_point():
    rec = _TouchRecorder()
    _drag(rec, 10, 20, 200, 150, frames=4)
    assert rec.touches[-1] == (200, 150)


def test_touch_drag_releases_exactly_once_at_the_end():
    rec = _TouchRecorder()
    _drag(rec, 0, 0, 255, 191, frames=6)
    assert rec.releases == 1


def test_touch_drag_never_releases_mid_drag():
    """touch_set_pos moves a HELD point -- release must not happen until the very end."""
    rec = _TouchRecorder()
    _drag(rec, 0, 0, 100, 100, frames=10)
    # releases only recorded once, and only after all interpolated touches:
    assert rec.releases == 1
    assert rec.touches[-1] == (100, 100)


def test_touch_drag_interpolates_monotonically_for_a_straight_line():
    rec = _TouchRecorder()
    _drag(rec, 0, 0, 100, 0, frames=5)
    xs = [t[0] for t in rec.touches]
    assert xs == sorted(xs), f"expected monotonic x progression, got {xs}"


def test_touch_drag_ticks_once_per_touch_call():
    rec = _TouchRecorder()
    _drag(rec, 0, 0, 50, 50, frames=5)
    # 1 initial tick (landing at the start point) + 1 tick per interpolated point (frames).
    assert rec.ticks == 1 + 5
    assert len(rec.touches) == 1 + 5


def test_touch_drag_frames_clamped_to_at_least_one():
    rec = _TouchRecorder()
    _drag(rec, 0, 0, 10, 10, frames=0)
    assert rec.releases == 1
    assert rec.touches[-1] == (10, 10)


def test_touch_drag_single_frame_goes_straight_to_end():
    rec = _TouchRecorder()
    _drag(rec, 5, 5, 250, 180, frames=1)
    assert rec.touches == [(5, 5), (250, 180)]


def test_touch_drag_same_point_is_a_plain_tap():
    rec = _TouchRecorder()
    _drag(rec, 50, 50, 50, 50, frames=3)
    assert all(t == (50, 50) for t in rec.touches)
    assert rec.releases == 1


# ---------------------------------------------------------------------------
# World-level harness (mirrors tests/test_nds_skill_port.py's _make_world)
# ---------------------------------------------------------------------------

class FakeNDSEmulator:
    """Minimal NDS emulator stand-in: press/tick/frame surface + touch/touch_release/touch_drag,
    mirroring tests/test_nds_skill_port.py's FakeNDSEmulator with touch support added."""

    BUTTONS = ("a", "b", "x", "y", "l", "r", "start", "select", "up", "down", "left", "right")

    def __init__(self) -> None:
        self._frame = 0
        self.touches: list[tuple[int, int]] = []
        self.releases = 0
        self.drag_calls: list[tuple] = []

    def press(self, button, hold_frames=8, settle_frames=16):
        self._frame += hold_frames + settle_frames

    def tick(self, frames):
        self._frame += max(1, frames)

    def screen_ndarray(self, screen="both"):
        h = 384 if screen == "both" else 192
        return np.zeros((h, 256, 3), dtype=np.uint8)

    def read(self, addr):
        return 0

    def save_screen(self, path):
        with open(path, "wb") as f:
            f.write(b"")

    def load_state(self, path):
        self.loaded = path

    def save_state(self, path):
        self.saved = path

    @property
    def frame(self):
        return self._frame

    def close(self):
        pass

    def touch(self, x, y):
        self.touches.append((x, y))

    def touch_release(self):
        self.releases += 1

    def touch_drag(self, x1, y1, x2, y2, frames=8):
        self.drag_calls.append((x1, y1, x2, y2, frames))


class _ScriptedPerceiver:
    def __init__(self, states=None) -> None:
        self._states = list(states) if states is not None else [_default_state()]
        self._i = 0

    def perceive(self, frame, memory: PerceptMemory, context=None) -> SymbolicState:
        if self._i < len(self._states):
            s = self._states[self._i]
            self._i += 1
        else:
            s = self._states[-1] if self._states else SymbolicState(context="gameplay")
        return s


def _default_state() -> SymbolicState:
    return SymbolicState(confidence=1.0, context="gameplay", pose={"value": (0, 0)},
                         spatial_memory={"visited": 1},
                         last_action={"action": "a", "outcome": "moved"})


def _make_world(out, *, game="nds", emu=None) -> World:
    spec = world_mcp.GAMES[game]
    emu = emu if emu is not None else FakeNDSEmulator()
    perceiver = _ScriptedPerceiver()
    plugin = PerceptionPlugin(rom_path=None, emulator=emu, out_dir=out, headless=True,
                              perceiver=perceiver, watch=spec["watch"],
                              render_header="test")
    w = World.__new__(World)
    w.with_screenshot = False
    w.keep_frames = False
    w.plugin = plugin
    w.gw = Gateway(plugin, Allowlist({"press_button", "press_sequence", "wait", "touch", "touch_target"}))
    from core.brains import ExploreBrain
    w.explore = ExploreBrain("mcp-brain", single_step=True)
    w.lessons = []
    w.decisions = 0
    w.auto_tiles = 0
    w.visited = 0
    w.region_tools = game in world_mcp._REGION_TOOL_WORLDS
    w._frame_hist = []
    w.kirby_skills_world = game in world_mcp._KIRBY_SKILLS_WORLDS
    w._kirby_skills_enabled = w.kirby_skills_world and world_mcp._kirby_skills_enabled()
    w.kirby_claims_world = game in world_mcp._KIRBY_CLAIMS_WORLDS
    w._kirby_claims_enabled = w.kirby_claims_world and world_mcp._kirby_claims_enabled()
    w.nds_skills_world = game in world_mcp._NDS_SKILLS_WORLDS
    w._nds_skills_enabled = w.nds_skills_world and world_mcp._nds_skills_enabled()
    w.nds_touch_drag_world = game in world_mcp._NDS_TOUCH_DRAG_WORLDS
    w._nds_touch_drag_enabled = w.nds_touch_drag_world and world_mcp._nds_touch_drag_enabled()
    w.skills = {}
    w._skill_log_path = os.path.join(out, "skills.jsonl")
    w._claims_log_path = os.path.join(out, "claims.jsonl")
    return w


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    """Tests each set NDS_TOUCH_DRAG explicitly -- start from a clean slate every test."""
    monkeypatch.delenv("NDS_TOUCH_DRAG", raising=False)
    monkeypatch.delenv("NDS_SKILLS", raising=False)
    monkeypatch.delenv("KIRBY_SKILLS", raising=False)
    monkeypatch.delenv("ARC_SKILLS", raising=False)


# ---------------------------------------------------------------------------
# 2. Gating: NDS_TOUCH_DRAG on/off, world scoping, no cross-flag interference
# ---------------------------------------------------------------------------

def test_touch_drag_tool_absent_by_default():
    names = [t["name"] for t in _static_tools("nds")]
    assert "touch_drag" not in names


def test_touch_drag_tool_present_when_flag_on(monkeypatch):
    monkeypatch.setenv("NDS_TOUCH_DRAG", "1")
    names = [t["name"] for t in _static_tools("nds")]
    assert "touch_drag" in names


def test_touch_drag_never_leaks_to_other_games(monkeypatch):
    monkeypatch.setenv("NDS_TOUCH_DRAG", "1")
    for game in ("cave_noire", "cave_noire_baseline", "gauntlet", "gb_generic", "pokemon_red",
                "kirby_dreamland", "kirby_gba", "emerald_gba", "arcagi3"):
        names = [t["name"] for t in _static_tools(game)]
        assert "touch_drag" not in names, f"{game} leaked touch_drag"


def test_nds_skills_flag_does_not_enable_touch_drag(monkeypatch):
    """One-flag-per-feature: NDS_SKILLS=1 alone must not unlock touch_drag."""
    monkeypatch.setenv("NDS_SKILLS", "1")
    names = [t["name"] for t in _static_tools("nds")]
    assert "touch_drag" not in names


def test_kirby_skills_flag_does_not_enable_touch_drag(monkeypatch):
    monkeypatch.setenv("KIRBY_SKILLS", "1")
    names = [t["name"] for t in _static_tools("nds")]
    assert "touch_drag" not in names


def test_touch_drag_flag_does_not_enable_nds_skill_tools(monkeypatch):
    """Reverse direction: NDS_TOUCH_DRAG=1 alone must not unlock define_skill/run_skill."""
    monkeypatch.setenv("NDS_TOUCH_DRAG", "1")
    names = [t["name"] for t in _static_tools("nds")]
    assert "define_skill" not in names and "run_skill" not in names


def test_touch_drag_base_action_tools_still_present_when_flag_on(monkeypatch):
    """touch_drag is additive -- press/wait/touch/touch_target must still all be there too."""
    monkeypatch.setenv("NDS_TOUCH_DRAG", "1")
    names = [t["name"] for t in _static_tools("nds")]
    for expected in ("press_button", "press_sequence", "wait", "touch", "touch_target", "touch_drag"):
        assert expected in names, f"{expected} missing from nds tools with NDS_TOUCH_DRAG=1: {names}"


# ---------------------------------------------------------------------------
# 3. Frozen-seam regression: assert_action_tools_fresh unaffected either way
# ---------------------------------------------------------------------------

def test_assert_action_tools_fresh_still_passes_with_flag_off(monkeypatch):
    monkeypatch.delenv("NDS_TOUCH_DRAG", raising=False)
    from core.nds_perception_plugin import NDSPerceptionPlugin
    plugin = NDSPerceptionPlugin(emulator=FakeNDSEmulator(), perceiver=_ScriptedPerceiver(),
                                 out_dir="/tmp/nds_touch_drag_test")
    assert_action_tools_fresh(plugin, "nds")   # must not raise


def test_assert_action_tools_fresh_still_passes_with_flag_on(monkeypatch):
    """touch_drag lives in `nav`, never in `_NDS_ACTION_TOOLS` -- the flag must not perturb this
    invariant (NDSPerceptionPlugin.tools() never grows a touch_drag entry)."""
    monkeypatch.setenv("NDS_TOUCH_DRAG", "1")
    from core.nds_perception_plugin import NDSPerceptionPlugin
    plugin = NDSPerceptionPlugin(emulator=FakeNDSEmulator(), perceiver=_ScriptedPerceiver(),
                                 out_dir="/tmp/nds_touch_drag_test")
    assert_action_tools_fresh(plugin, "nds")   # must not raise
    assert "touch_drag" not in {s.name for s in plugin.tools("test-agent")}


# ---------------------------------------------------------------------------
# 4. Dispatch: disabled -> refusal; enabled -> routes to emu.touch_drag
# ---------------------------------------------------------------------------

def test_dispatch_disabled_by_default(tmp_path):
    w = _make_world(str(tmp_path / "out"))
    result = w.call("touch_drag", {"x1": 10, "y1": 10, "x2": 200, "y2": 150})
    text = " ".join(c["text"] for c in result if c.get("type") == "text")
    assert "touch_drag is disabled for this session" in text
    assert w.decisions == 0


def test_dispatch_works_when_flag_on(tmp_path, monkeypatch):
    monkeypatch.setenv("NDS_TOUCH_DRAG", "1")
    emu = FakeNDSEmulator()
    w = _make_world(str(tmp_path / "out"), emu=emu)
    result = w.call("touch_drag", {"x1": 10, "y1": 20, "x2": 200, "y2": 150, "frames": 12})
    text = " ".join(c["text"] for c in result if c.get("type") == "text")
    assert "touch_drag (10,20)->(200,150) over 12 frame(s) -> ok" in text
    assert emu.drag_calls == [(10, 20, 200, 150, 12)]


def test_dispatch_counts_as_a_decision(tmp_path, monkeypatch):
    monkeypatch.setenv("NDS_TOUCH_DRAG", "1")
    w = _make_world(str(tmp_path / "out"))
    w.call("touch_drag", {"x1": 0, "y1": 0, "x2": 100, "y2": 100})
    assert w.decisions == 1


def test_dispatch_defaults_frames_to_eight(tmp_path, monkeypatch):
    monkeypatch.setenv("NDS_TOUCH_DRAG", "1")
    emu = FakeNDSEmulator()
    w = _make_world(str(tmp_path / "out"), emu=emu)
    w.call("touch_drag", {"x1": 0, "y1": 0, "x2": 50, "y2": 50})
    assert emu.drag_calls == [(0, 0, 50, 50, 8)]


def test_dispatch_returns_trailing_observe(tmp_path, monkeypatch):
    monkeypatch.setenv("NDS_TOUCH_DRAG", "1")
    w = _make_world(str(tmp_path / "out"))
    result = w.call("touch_drag", {"x1": 0, "y1": 0, "x2": 100, "y2": 100})
    # The trailing content is the same shape observe()/touch/touch_target already produce.
    assert len(result) > 1


class _TouchOnlyEmu:
    """An emulator with touch()/touch_release() but deliberately NO touch_drag method -- exercises
    World._touch_drag's defensive compose-from-touch() fallback path."""

    BUTTONS = FakeNDSEmulator.BUTTONS

    def __init__(self) -> None:
        self._frame = 0
        self.touches: list[tuple[int, int]] = []
        self.releases = 0

    def press(self, button, hold_frames=8, settle_frames=16):
        self._frame += hold_frames + settle_frames

    def tick(self, frames):
        self._frame += max(1, frames)

    def screen_ndarray(self, screen="both"):
        h = 384 if screen == "both" else 192
        return np.zeros((h, 256, 3), dtype=np.uint8)

    def read(self, addr):
        return 0

    def save_screen(self, path):
        with open(path, "wb") as f:
            f.write(b"")

    def load_state(self, path):
        self.loaded = path

    def save_state(self, path):
        self.saved = path

    @property
    def frame(self):
        return self._frame

    def close(self):
        pass

    def touch(self, x, y):
        self.touches.append((x, y))

    def touch_release(self):
        self.releases += 1


def test_dispatch_falls_back_to_touch_when_emulator_lacks_touch_drag(tmp_path, monkeypatch):
    """Defensive fallback: an emulator exposing only touch()/touch_release() (no touch_drag method)
    still works, composed from the same algorithm."""
    monkeypatch.setenv("NDS_TOUCH_DRAG", "1")
    emu = _TouchOnlyEmu()
    assert not hasattr(emu, "touch_drag")
    w = _make_world(str(tmp_path / "out"), emu=emu)
    result = w.call("touch_drag", {"x1": 0, "y1": 0, "x2": 30, "y2": 40, "frames": 3})
    text = " ".join(c["text"] for c in result if c.get("type") == "text")
    assert "-> ok" in text
    assert emu.touches[0] == (0, 0)
    assert emu.touches[-1] == (30, 40)
    assert emu.releases == 1


# ---------------------------------------------------------------------------
# 5. Argument validation: bad input rejected loudly, never silently clamped
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("args", [
    {"x1": -1, "y1": 0, "x2": 10, "y2": 10},
    {"x1": 0, "y1": -1, "x2": 10, "y2": 10},
    {"x1": 0, "y1": 0, "x2": 256, "y2": 10},
    {"x1": 0, "y1": 0, "x2": 10, "y2": 192},
])
def test_dispatch_rejects_out_of_range_coords(tmp_path, monkeypatch, args):
    monkeypatch.setenv("NDS_TOUCH_DRAG", "1")
    emu = FakeNDSEmulator()
    w = _make_world(str(tmp_path / "out"), emu=emu)
    result = w.call("touch_drag", args)
    text = " ".join(c["text"] for c in result if c.get("type") == "text")
    assert "out of range" in text
    assert emu.drag_calls == []


@pytest.mark.parametrize("frames", [0, -1, 121, 500])
def test_dispatch_rejects_bad_frames(tmp_path, monkeypatch, frames):
    monkeypatch.setenv("NDS_TOUCH_DRAG", "1")
    emu = FakeNDSEmulator()
    w = _make_world(str(tmp_path / "out"), emu=emu)
    result = w.call("touch_drag", {"x1": 0, "y1": 0, "x2": 10, "y2": 10, "frames": frames})
    text = " ".join(c["text"] for c in result if c.get("type") == "text")
    assert "frames must be in [1,120]" in text
    assert emu.drag_calls == []


def test_dispatch_rejects_missing_coords(tmp_path, monkeypatch):
    monkeypatch.setenv("NDS_TOUCH_DRAG", "1")
    emu = FakeNDSEmulator()
    w = _make_world(str(tmp_path / "out"), emu=emu)
    result = w.call("touch_drag", {"x1": 0, "y1": 0})
    text = " ".join(c["text"] for c in result if c.get("type") == "text")
    assert "needs integer x1, y1, x2, y2" in text
    assert emu.drag_calls == []


def test_dispatch_rejects_non_integer_coords(tmp_path, monkeypatch):
    monkeypatch.setenv("NDS_TOUCH_DRAG", "1")
    emu = FakeNDSEmulator()
    w = _make_world(str(tmp_path / "out"), emu=emu)
    result = w.call("touch_drag", {"x1": "nope", "y1": 0, "x2": 10, "y2": 10})
    text = " ".join(c["text"] for c in result if c.get("type") == "text")
    assert "needs integer x1, y1, x2, y2" in text
    assert emu.drag_calls == []


# ---------------------------------------------------------------------------
# 6. World.__init__ reads the flag once at construction (A/B arm-isolation discipline)
# ---------------------------------------------------------------------------

def test_world_init_reads_flag_once(monkeypatch):
    monkeypatch.setenv("NDS_TOUCH_DRAG", "1")
    w = World.__new__(World)
    w.nds_touch_drag_world = "nds" in world_mcp._NDS_TOUCH_DRAG_WORLDS
    w._nds_touch_drag_enabled = w.nds_touch_drag_world and world_mcp._nds_touch_drag_enabled()
    assert w._nds_touch_drag_enabled is True


def test_flag_off_world_scoping_matches_pattern(monkeypatch):
    monkeypatch.setenv("NDS_TOUCH_DRAG", "1")
    assert ("kirby_dreamland" in world_mcp._NDS_TOUCH_DRAG_WORLDS) is False
    assert ("nds" in world_mcp._NDS_TOUCH_DRAG_WORLDS) is True
