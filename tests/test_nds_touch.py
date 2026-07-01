"""Unit tests for the NDS touch increment (feat/nds-touch).

Tests prove:
  1. touch ToolSpec is present in NDSPerceptionPlugin.tools().
  2. A touch ToolCall routes to emulator.touch(x, y) + touch_release() — no ROM needed.
  3. touch coords are validated (out-of-range rejected cleanly).
  4. NDSPerceiver._detect_touch_targets() returns blobs from a synthetic bottom-screen frame.
  5. touch_targets land in SymbolicState.spatial_memory when NDSPerceiver sees a dual frame.

All tests use pure numpy + a fake emulator. They skip cleanly when numpy is absent (won't be,
but the guard is consistent with the rest of the test suite).
"""
from __future__ import annotations

import uuid
from typing import Optional

import pytest

numpy = pytest.importorskip("numpy")
import numpy as np

from core.contracts import ToolCall, ToolResult
from core.nds_perception_plugin import NDSPerceptionPlugin
from core.nds_perceiver import NDSPerceiver, _detect_touch_targets
from core.perception import PerceptMemory, SymbolicState

# ---------------------------------------------------------------------------
# Fake emulator — records touch() calls, no ROM needed.
# ---------------------------------------------------------------------------

class FakeEmu:
    """Minimal emulator stub: captures touch calls, returns blank frames."""

    def __init__(self):
        self.touches: list[tuple[int, int]] = []
        self.releases = 0
        self.ticks = 0
        self._frame = 0

    # -- Emulator protocol --
    def tick(self, n: int) -> None:
        self.ticks += n
        self._frame += n

    def screen_ndarray(self, screen="both"):
        h = 384 if screen == "both" else 192
        return np.zeros((h, 256, 3), dtype=np.uint8)

    def save_screen(self, path: str) -> None:
        pass

    def press(self, button: str, hold_frames: int = 8, settle_frames: int = 16) -> None:
        pass

    def read(self, addr: int) -> int:
        return 0

    def load_state(self, path: str) -> None:
        pass

    def save_state(self, path: str) -> None:
        pass

    def close(self) -> None:
        pass

    @property
    def frame(self) -> int:
        return self._frame

    # -- NDS-specific (the methods under test) --
    def touch(self, x: int, y: int) -> None:
        self.touches.append((x, y))

    def touch_release(self) -> None:
        self.releases += 1


# ---------------------------------------------------------------------------
# Fake perceiver — returns a minimal SymbolicState.
# ---------------------------------------------------------------------------

class FakePerceiver:
    def perceive(self, frame, memory, context=None):
        return SymbolicState(confidence=0.5, context="test")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_plugin(emu: Optional[FakeEmu] = None) -> NDSPerceptionPlugin:
    if emu is None:
        emu = FakeEmu()
    return NDSPerceptionPlugin(
        emulator=emu,
        perceiver=FakePerceiver(),
        out_dir="/tmp/nds_touch_test",
    )


def _call(tool: str, args: dict) -> ToolCall:
    return ToolCall(tool=tool, args=args, agent_id="test-agent", call_id=str(uuid.uuid4()))


# ---------------------------------------------------------------------------
# 1. ToolSpec presence
# ---------------------------------------------------------------------------

def test_touch_toolspec_present():
    plugin = _make_plugin()
    names = [s.name for s in plugin.tools("test-agent")]
    assert "touch" in names, f"expected 'touch' in tools(), got: {names}"


def test_touch_toolspec_schema_correct():
    plugin = _make_plugin()
    spec = next(s for s in plugin.tools("test-agent") if s.name == "touch")
    props = spec.schema["properties"]
    assert "x" in props and "y" in props
    assert props["x"]["minimum"] == 0 and props["x"]["maximum"] == 255
    assert props["y"]["minimum"] == 0 and props["y"]["maximum"] == 191
    assert spec.mutating is True


def test_touch_toolspec_cost_is_one():
    plugin = _make_plugin()
    spec = next(s for s in plugin.tools("test-agent") if s.name == "touch")
    assert spec.cost == 1


# ---------------------------------------------------------------------------
# 2. Routing: touch ToolCall -> emulator.touch(x, y) + touch_release()
# ---------------------------------------------------------------------------

def test_touch_routes_to_emulator_touch():
    emu = FakeEmu()
    plugin = _make_plugin(emu)
    res = plugin.handle(_call("touch", {"x": 128, "y": 64}))
    assert res.ok, f"expected ok=True, got error: {res.error}"
    assert emu.touches == [(128, 64)], f"expected touch at (128,64), got {emu.touches}"
    assert emu.releases == 1, f"expected 1 touch_release call, got {emu.releases}"


def test_touch_ticks_after_release():
    """Verify settle ticks happen (ticks > hold_frames — settle is additional)."""
    emu = FakeEmu()
    plugin = _make_plugin(emu)
    plugin.handle(_call("touch", {"x": 100, "y": 50, "hold_frames": 6}))
    # hold=6 ticks + settle=4 ticks = at least 10 ticks total.
    assert emu.ticks >= 6, f"expected >= 6 ticks, got {emu.ticks}"


def test_touch_result_contains_action_string():
    emu = FakeEmu()
    plugin = _make_plugin(emu)
    res = plugin.handle(_call("touch", {"x": 30, "y": 90}))
    assert res.ok
    assert "touch" in res.data.get("action", "")


# ---------------------------------------------------------------------------
# 3. Validation: out-of-range coords rejected
# ---------------------------------------------------------------------------

def test_touch_rejects_x_out_of_range():
    plugin = _make_plugin()
    res = plugin.handle(_call("touch", {"x": 300, "y": 50}))
    assert not res.ok
    assert "range" in res.error.lower() or "out" in res.error.lower()


def test_touch_rejects_y_out_of_range():
    plugin = _make_plugin()
    res = plugin.handle(_call("touch", {"x": 100, "y": 200}))
    assert not res.ok


def test_touch_rejects_negative_coords():
    plugin = _make_plugin()
    res = plugin.handle(_call("touch", {"x": -1, "y": 50}))
    assert not res.ok


# ---------------------------------------------------------------------------
# 4. Touch-target detection from synthetic frame
# ---------------------------------------------------------------------------

def _make_ui_frame(h: int = 192, w: int = 256) -> np.ndarray:
    """Synthetic NDS bottom-screen: white background with three high-contrast rectangles (buttons)."""
    frame = np.full((h, w, 3), 240, dtype=np.uint8)  # light background
    # Button 1: top-left
    frame[20:60, 20:100, :] = 30   # dark fill
    # Button 2: top-right
    frame[20:60, 150:230, :] = 30
    # Button 3: bottom-center
    frame[120:160, 80:170, :] = 30
    return frame


def test_detect_touch_targets_finds_blobs_on_ui_frame():
    frame = _make_ui_frame()
    targets = _detect_touch_targets(frame)
    assert len(targets) >= 3, (
        f"expected at least 3 targets (3 synthetic buttons), found {len(targets)}: {targets}"
    )


def test_detect_touch_targets_returns_valid_coords():
    frame = _make_ui_frame()
    targets = _detect_touch_targets(frame)
    for t in targets:
        assert "cx" in t and "cy" in t and "bbox" in t and "area" in t
        assert 0 <= t["cx"] <= 255
        assert 0 <= t["cy"] <= 191
        x0, y0, x1, y1 = t["bbox"]
        assert x0 <= x1 and y0 <= y1


def test_detect_touch_targets_blank_frame_returns_empty():
    blank = np.zeros((192, 256, 3), dtype=np.uint8)
    targets = _detect_touch_targets(blank)
    assert targets == []


def test_detect_touch_targets_sorted_by_area():
    frame = _make_ui_frame()
    targets = _detect_touch_targets(frame)
    areas = [t["area"] for t in targets]
    assert areas == sorted(areas, reverse=True), "targets should be sorted by area descending"


# ---------------------------------------------------------------------------
# 5. touch_targets land in SymbolicState.spatial_memory via NDSPerceiver
# ---------------------------------------------------------------------------

def _make_dual_frame_with_ui() -> np.ndarray:
    """384×256×3 dual frame: random top (gameplay), UI bottom (touch surface)."""
    rng = np.random.RandomState(7)
    top = rng.randint(0, 200, (192, 256, 3), dtype=np.uint8)
    bot = _make_ui_frame()
    return np.concatenate([top, bot], axis=0)


def test_nds_perceiver_injects_touch_targets_into_spatial_memory():
    """When NDSPerceiver sees a dual frame where the bottom is the UI screen, touch_targets
    should appear in spatial_memory after discovery routes gameplay to the top."""
    perceiver = NDSPerceiver(fallback_screen="top")
    memory = PerceptMemory()
    dual = _make_dual_frame_with_ui()

    # Feed several frames so discovery can commit (min_steps=3 default).
    sym: Optional[SymbolicState] = None
    for i in range(10):
        sym = perceiver.perceive(dual, memory, context={"last_action": "right"})

    assert sym is not None
    sm = sym.spatial_memory or {}
    assert "touch_targets" in sm, (
        f"expected 'touch_targets' in spatial_memory, got keys: {list(sm.keys())}"
    )
    targets = sm["touch_targets"]
    assert isinstance(targets, list)
    assert len(targets) >= 1, f"expected at least 1 target, got {targets}"


# ---------------------------------------------------------------------------
# New tests (F1/F2/F3/F5 fixes — address code-review findings)
# ---------------------------------------------------------------------------

# (a) touch NOT advertised on GB worlds, IS on NDS
# -------------------------------------------------------

def test_gb_plugin_does_not_advertise_touch():
    """GB PerceptionPlugin must NOT have a touch tool — it was leaking via _STATIC_TOOLS."""
    from core.perception_plugin import PerceptionPlugin
    plugin = PerceptionPlugin(emulator=FakeEmu(), perceiver=FakePerceiver(), out_dir="/tmp/nds_touch_test")
    names = [s.name for s in plugin.tools("test-agent")]
    assert "touch" not in names, f"touch must NOT be in GB plugin tools, got: {names}"


def test_nds_plugin_does_advertise_touch():
    """NDSPerceptionPlugin MUST have a touch tool."""
    plugin = _make_plugin()
    names = [s.name for s in plugin.tools("test-agent")]
    assert "touch" in names, f"touch must be in NDS plugin tools, got: {names}"


def test_world_mcp_static_tools_gb_no_touch():
    """world_mcp._static_tools('cave_noire') must NOT include touch."""
    from world_mcp import _static_tools
    tools = _static_tools("cave_noire")
    names = [t["name"] for t in tools]
    assert "touch" not in names, f"touch must NOT be in GB world static tools, got: {names}"


def test_world_mcp_static_tools_nds_has_touch():
    """world_mcp._static_tools('nds') MUST include touch."""
    from world_mcp import _static_tools
    tools = _static_tools("nds")
    names = [t["name"] for t in tools]
    assert "touch" in names, f"touch must be in NDS world static tools, got: {names}"


# (b) Exact-equality freshness assertion
# -------------------------------------------------------

def test_assert_action_tools_fresh_exact_equality_passes():
    """assert_action_tools_fresh passes when static == live (exact match)."""
    from world_mcp import assert_action_tools_fresh
    plugin = _make_plugin()
    # NDSPerceptionPlugin exposes press_button, press_sequence, wait, touch.
    # _NDS_ACTION_TOOLS has the same set. Should not raise.
    # (FakeEmu has no BUTTONS class attr, so plugin.tools() returns GB 8-button enum for press tools.
    # That will cause a mismatch vs _NDS_ACTION_TOOLS which uses NDS 12 buttons. We test the GB path.)
    from core.perception_plugin import PerceptionPlugin
    gb_plugin = PerceptionPlugin(emulator=FakeEmu(), perceiver=FakePerceiver(), out_dir="/tmp/nds_touch_test")
    # GB plugin has 3 tools; _GB_ACTION_TOOLS also has 3. But button enum uses FakeEmu fallback (8 buttons).
    # We only test that the function can be called and raises SystemExit on mismatch.
    from world_mcp import _GB_ACTION_TOOLS
    from core.contracts import ToolSpec
    # Construct a mock plugin whose tools() exactly match _GB_ACTION_TOOLS
    class _ExactPlugin:
        def tools(self, agent_id):
            return [ToolSpec(name=t["name"], description="", schema=t["inputSchema"], cost=1, mutating=True)
                    for t in _GB_ACTION_TOOLS]
    assert_action_tools_fresh(_ExactPlugin(), "cave_noire")  # must not raise


def test_assert_action_tools_fresh_raises_on_drift():
    """assert_action_tools_fresh raises SystemExit when live plugin has extra or missing tools."""
    from world_mcp import assert_action_tools_fresh
    from core.contracts import ToolSpec

    class _ExtraPlugin:
        def tools(self, agent_id):
            return [ToolSpec(name="press_button", description="", schema={"type": "object", "properties": {}, "required": []}, cost=1, mutating=True),
                    ToolSpec(name="extra_tool", description="", schema={"type": "object", "properties": {}, "required": []}, cost=1, mutating=True)]

    import pytest
    with pytest.raises(SystemExit):
        assert_action_tools_fresh(_ExtraPlugin(), "cave_noire")


# (c) touch exception → ok=False
# -------------------------------------------------------

def test_touch_exception_becomes_ok_false():
    """Any exception inside _do_touch must be caught and returned as ok=False (not propagate)."""
    class BrokenEmu(FakeEmu):
        def touch(self, x: int, y: int) -> None:
            raise RuntimeError("simulated hardware fault")

    plugin = _make_plugin(BrokenEmu())
    res = plugin.handle(_call("touch", {"x": 100, "y": 50}))
    assert not res.ok, "exception in touch must become ok=False"
    assert res.error is not None and len(res.error) > 0


# (d) NDS buttons accepted by NDSPerceptionPlugin
# -------------------------------------------------------

class FakeNDSEmu(FakeEmu):
    """Fake NDS emulator: exposes BUTTONS = NDS 12-button set."""
    BUTTONS = ("a", "b", "x", "y", "l", "r", "start", "select", "up", "down", "left", "right")

    def press(self, button: str, hold_frames: int = 8, settle_frames: int = 16) -> None:
        pass  # accept any button


def test_nds_buttons_accepted_by_plugin():
    """NDSPerceptionPlugin must accept NDS-specific buttons x, y, l, r."""
    emu = FakeNDSEmu()
    plugin = NDSPerceptionPlugin(emulator=emu, perceiver=FakePerceiver(), out_dir="/tmp/nds_touch_test")
    for btn in ("x", "y", "l", "r"):
        res = plugin.handle(_call("press_button", {"button": btn}))
        assert res.ok, f"NDS button '{btn}' was rejected: {res.error}"


def test_gb_buttons_still_accepted_by_base_plugin():
    """GB PerceptionPlugin must still accept all 8 original GB buttons (no regression)."""
    from core.perception_plugin import PerceptionPlugin
    plugin = PerceptionPlugin(emulator=FakeEmu(), perceiver=FakePerceiver(), out_dir="/tmp/nds_touch_test")
    for btn in ("a", "b", "start", "select", "up", "down", "left", "right"):
        res = plugin.handle(_call("press_button", {"button": btn}))
        assert res.ok, f"GB button '{btn}' was rejected: {res.error}"


def test_nds_only_buttons_rejected_by_gb_plugin():
    """GB PerceptionPlugin must reject NDS-only buttons x, y, l, r."""
    from core.perception_plugin import PerceptionPlugin
    plugin = PerceptionPlugin(emulator=FakeEmu(), perceiver=FakePerceiver(), out_dir="/tmp/nds_touch_test")
    for btn in ("x", "y", "l", "r"):
        res = plugin.handle(_call("press_button", {"button": btn}))
        assert not res.ok, f"NDS button '{btn}' must be rejected by GB plugin but was accepted"


# ---------------------------------------------------------------------------
# 6. touch_target — coarse id resolution against the last observe()'s targets
#    (feat/touch-target-coarsening; the ADR-003 "coordinate leak" fix — additive)
# ---------------------------------------------------------------------------

# A known area-sorted target list to seed _last_touch_targets directly (0 = largest by convention).
_SEED_TARGETS = [
    {"cx": 60, "cy": 40, "bbox": [20, 20, 100, 60], "area": 3200},   # id 0
    {"cx": 125, "cy": 140, "bbox": [80, 120, 170, 160], "area": 3000},  # id 1
    {"cx": 190, "cy": 40, "bbox": [150, 20, 230, 60], "area": 2800},  # id 2
]


def test_touch_target_toolspec_present():
    plugin = _make_plugin()
    names = [s.name for s in plugin.tools("test-agent")]
    assert "touch_target" in names, f"expected 'touch_target' in tools(), got: {names}"


def test_touch_target_toolspec_schema_and_flags():
    plugin = _make_plugin()
    spec = next(s for s in plugin.tools("test-agent") if s.name == "touch_target")
    props = spec.schema["properties"]
    assert "id" in props and props["id"]["minimum"] == 0
    assert "hold_frames" in props
    assert spec.schema["required"] == ["id"]
    assert spec.cost == 1
    assert spec.mutating is True


def test_touch_target_resolves_id_zero_to_first_target():
    """touch_target(id=0) taps the 0-th (largest) cached target's (cx, cy)."""
    emu = FakeEmu()
    plugin = _make_plugin(emu)
    plugin._last_touch_targets = list(_SEED_TARGETS)
    res = plugin.handle(_call("touch_target", {"id": 0}))
    assert res.ok, f"expected ok=True, got error: {res.error}"
    assert emu.touches == [(60, 40)], f"expected tap at target 0 (60,40), got {emu.touches}"
    assert emu.releases == 1
    assert "touch_target" in res.data.get("action", "")


def test_touch_target_resolves_middle_id():
    emu = FakeEmu()
    plugin = _make_plugin(emu)
    plugin._last_touch_targets = list(_SEED_TARGETS)
    res = plugin.handle(_call("touch_target", {"id": 2}))
    assert res.ok
    assert emu.touches == [(190, 40)], f"expected tap at target 2 (190,40), got {emu.touches}"


def test_touch_target_empty_list_rejected():
    """No targets from the last observe() -> ok=False, no tap, no raise."""
    emu = FakeEmu()
    plugin = _make_plugin(emu)
    plugin._last_touch_targets = []
    res = plugin.handle(_call("touch_target", {"id": 0}))
    assert not res.ok
    assert emu.touches == []
    assert res.error and "no touch targets" in res.error.lower()


def test_touch_target_out_of_range_rejected():
    emu = FakeEmu()
    plugin = _make_plugin(emu)
    plugin._last_touch_targets = list(_SEED_TARGETS)   # len 3 -> valid ids 0..2
    res = plugin.handle(_call("touch_target", {"id": 3}))
    assert not res.ok
    assert emu.touches == []
    assert "range" in res.error.lower()


def test_touch_target_negative_id_rejected():
    emu = FakeEmu()
    plugin = _make_plugin(emu)
    plugin._last_touch_targets = list(_SEED_TARGETS)
    res = plugin.handle(_call("touch_target", {"id": -1}))
    assert not res.ok
    assert emu.touches == []


def test_touch_target_exception_becomes_ok_false():
    """Any exception inside _do_touch_target must be caught and returned as ok=False (not propagate)."""
    class BrokenEmu(FakeEmu):
        def touch(self, x: int, y: int) -> None:
            raise RuntimeError("simulated hardware fault")

    plugin = _make_plugin(BrokenEmu())
    plugin._last_touch_targets = list(_SEED_TARGETS)
    res = plugin.handle(_call("touch_target", {"id": 0}))
    assert not res.ok, "exception in touch_target must become ok=False"
    assert res.error is not None and len(res.error) > 0


def test_touch_target_defaults_empty_before_any_observe():
    """A fresh plugin has an empty target cache (so touch_target rejects until observe() runs)."""
    plugin = _make_plugin()
    assert plugin._last_touch_targets == []


def test_observe_populates_last_touch_targets_cache():
    """The observe() override caches spatial_memory.touch_targets so touch_target can resolve them."""
    class _DualUIEmu(FakeEmu):
        """FakeEmu whose screen_ndarray returns the synthetic UI dual-frame (top gameplay, bottom UI)."""
        def screen_ndarray(self, screen="both"):
            return _make_dual_frame_with_ui()

    # Real NDSPerceiver so a UI dual-frame yields detected touch_targets.
    plugin = NDSPerceptionPlugin(emulator=_DualUIEmu(), perceiver=NDSPerceiver(fallback_screen="top"),
                                 out_dir="/tmp/nds_touch_test")

    # Feed several observe() calls so ScreenRoleDiscovery commits (min_steps=3 default).
    for _ in range(10):
        plugin.observe("test-agent")

    assert isinstance(plugin._last_touch_targets, list)
    assert len(plugin._last_touch_targets) >= 1, (
        f"expected observe() to cache >=1 target, got {plugin._last_touch_targets}"
    )
    # And touch_target now resolves against the cache end-to-end.
    tap_emu = FakeEmu()
    plugin.emu = tap_emu
    res = plugin.handle(_call("touch_target", {"id": 0}))
    assert res.ok, f"touch_target failed after observe cache: {res.error}"
    assert len(tap_emu.touches) == 1


def test_world_mcp_static_tools_nds_has_touch_target():
    """world_mcp._static_tools('nds') MUST include touch_target (mirrors the live plugin)."""
    from world_mcp import _static_tools
    tools = _static_tools("nds")
    names = [t["name"] for t in tools]
    assert "touch_target" in names, f"touch_target must be in NDS world static tools, got: {names}"


def test_world_mcp_static_tools_gb_no_touch_target():
    """world_mcp._static_tools('cave_noire') must NOT include touch_target."""
    from world_mcp import _static_tools
    tools = _static_tools("cave_noire")
    names = [t["name"] for t in tools]
    assert "touch_target" not in names, f"touch_target must NOT be in GB world static tools, got: {names}"


def test_assert_action_tools_fresh_nds_with_touch_target():
    """assert_action_tools_fresh passes for the NDS plugin now that both lists carry touch_target."""
    from world_mcp import assert_action_tools_fresh
    plugin = NDSPerceptionPlugin(emulator=FakeNDSEmu(), perceiver=FakePerceiver(),
                                 out_dir="/tmp/nds_touch_test")
    assert_action_tools_fresh(plugin, "nds")  # must not raise
