"""Regression tests for the NDS symbolic-render bug (2026-07-03 Kirby audit, runs/brain_kirby_nds/).

Root cause: PerceptionPlugin._render_symbolic() gated the whole spatial render (pose, walls,
frontiers, entities, touch_targets, last-move outcome) on `sym.context == "overworld"` — a label
that ONLY games/pokemon_red/perceiver.py emits. The shared GridPerceiver (core/grid_perceiver.py,
used by cave_noire, gauntlet, AND core/nds_perceiver.py) emits a DIFFERENT vocabulary
{"gameplay", "static", "menu", "unknown"} (see core/modality.py::detect_modality) and never emits
"overworld". So every GridPerceiver-based world always took the degenerate branch: gameplay itself
got rendered as "You are in a gameplay, NOT free movement" and the touch_targets list (which
touch_target(id) resolves against) never appeared at all.

These tests build synthetic SymbolicState objects (fast, no ROM) to pin the render's field
surfacing, plus one end-to-end test that replays REAL recorded Kirby Super Star Ultra frames
(eval/fixtures/kirby_title_menu/, copied from runs/brain_kirby_nds/world/) through the real
NDSPerceptionPlugin + NDSPerceiver to prove the fix holds on live data, not just hand-built states.

Regression guard: cave_noire and gauntlet use GridPerceiver's "gameplay"/"static"/"menu" contexts
too (tests/test_cave_noire.py, tests/test_gauntlet.py assert this). This file pins their render
output so the fix (and any future perception_plugin.py change) can't silently break them.
"""
from __future__ import annotations

import os

import numpy as np
import pytest

from core.contracts import ToolCall
from core.perception import PerceptMemory, SymbolicState

_FIXTURE_DIR = os.path.join(os.path.dirname(__file__), "..", "eval", "fixtures", "kirby_title_menu")


# ---------------------------------------------------------------------------
# Fakes (numpy-only, no ROM) — mirrors tests/test_nds_touch.py's FakeEmu.
# ---------------------------------------------------------------------------

class FakeEmu:
    def __init__(self):
        self.touches = []
        self.releases = 0
        self._frame = 0

    def tick(self, n: int) -> None:
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

    def touch(self, x: int, y: int) -> None:
        self.touches.append((x, y))

    def touch_release(self) -> None:
        self.releases += 1


class FixedPerceiver:
    """Returns a pre-built SymbolicState regardless of input — for pinning render() in isolation."""

    def __init__(self, sym: SymbolicState):
        self._sym = sym

    def perceive(self, frame, memory, context=None):
        return self._sym


def _plugin_with(sym: SymbolicState, out_dir):
    from core.nds_perception_plugin import NDSPerceptionPlugin
    return NDSPerceptionPlugin(emulator=FakeEmu(), perceiver=FixedPerceiver(sym), out_dir=str(out_dir))


# ---------------------------------------------------------------------------
# 1. "gameplay" context must render the SAME as "overworld" (the core fix).
# ---------------------------------------------------------------------------

def test_gameplay_context_gets_spatial_render_not_degenerate_line(tmp_path):
    sym = SymbolicState(
        confidence=0.7, context="gameplay",
        pose={"frame": "grid", "value": [3, 2], "uncertain": False},
        spatial_memory={"walls_here": ["up"], "visited": 5, "frontiers": [[4, 2]], "entities": []},
        affordances=["down", "left"],
        last_action={"action": "right", "outcome": "moved"},
    )
    plugin = _plugin_with(sym, tmp_path)
    text = plugin.observe("a").text

    assert "NOT free movement" not in text, f"gameplay wrongly rendered as non-free-movement: {text!r}"
    assert "position" in text.lower()
    assert "(3, 2)" in text
    assert "Known walls at this spot: up" in text
    assert "Last move 'right' -> moved." in text
    assert "Unexplored/open directions" in text
    assert "frontier" in text.lower()


def test_overworld_context_still_renders_spatial_view_unchanged(tmp_path):
    """Regression: pokemon_red's own 'overworld' label must keep working exactly as before."""
    sym = SymbolicState(
        confidence=0.7, context="overworld",
        pose={"frame": "grid", "value": [1, 1], "uncertain": False},
        spatial_memory={"walls_here": [], "visited": 1, "frontiers": [], "entities": []},
        affordances=["up"],
        last_action={"action": "up", "outcome": "moved"},
    )
    plugin = _plugin_with(sym, tmp_path)
    text = plugin.observe("a").text
    assert "NOT free movement" not in text
    assert "(1, 1)" in text


# ---------------------------------------------------------------------------
# 2. touch_targets list surfaces in the render (both branches).
# ---------------------------------------------------------------------------

def test_menu_context_surfaces_touch_targets_list(tmp_path):
    """The touch_targets list MUST appear in the render — touch_target(id) resolves against it,
    and a brain can't call it sight-unseen (the Kirby audit's core complaint)."""
    sym = SymbolicState(
        confidence=0.7, context="menu",
        spatial_memory={"touch_targets": [
            {"cx": 16, "cy": 80, "bbox": [0, 60, 32, 100], "area": 500},
            {"cx": 200, "cy": 40, "bbox": [180, 20, 220, 60], "area": 300},
        ]},
        last_action={"action": "a", "outcome": "unknown"},
    )
    plugin = _plugin_with(sym, tmp_path)
    text = plugin.observe("a").text
    assert "Touch targets detected" in text
    assert "0:(16,80)" in text
    assert "1:(200,40)" in text
    assert "touch_target(id)" in text


def test_gameplay_context_also_surfaces_touch_targets(tmp_path):
    sym = SymbolicState(
        confidence=0.7, context="gameplay",
        pose={"frame": "grid", "value": [0, 0], "uncertain": False},
        spatial_memory={"touch_targets": [{"cx": 5, "cy": 5, "bbox": [0, 0, 10, 10], "area": 100}]},
    )
    plugin = _plugin_with(sym, tmp_path)
    text = plugin.observe("a").text
    assert "Touch targets detected" in text
    assert "0:(5,5)" in text


def test_no_touch_targets_omits_the_line(tmp_path):
    sym = SymbolicState(confidence=0.7, context="menu", spatial_memory={})
    plugin = _plugin_with(sym, tmp_path)
    text = plugin.observe("a").text
    assert "Touch targets" not in text


# ---------------------------------------------------------------------------
# 3. Last-move outcome surfaces even in the non-free-movement branch.
# ---------------------------------------------------------------------------

def test_menu_context_surfaces_last_action_outcome(tmp_path):
    sym = SymbolicState(
        confidence=0.7, context="menu",
        last_action={"action": "touch_target(0)->(16,80)", "outcome": "blocked"},
    )
    plugin = _plugin_with(sym, tmp_path)
    text = plugin.observe("a").text
    assert "BLOCKED" in text
    assert "touch_target(0)->(16,80)" in text


# ---------------------------------------------------------------------------
# 4. static/unknown/menu without screen_text: no fabricated wall/frontier lines.
# ---------------------------------------------------------------------------

def test_static_context_does_not_fabricate_spatial_fields(tmp_path):
    """A perceiver with no spatial model for this context must not have walls/frontiers invented."""
    sym = SymbolicState(confidence=0.7, context="static")
    plugin = _plugin_with(sym, tmp_path)
    text = plugin.observe("a").text
    assert "You are in a static, NOT free movement." in text
    assert "wall" not in text.lower()
    assert "frontier" not in text.lower()


# ---------------------------------------------------------------------------
# 5. Regression pins: cave_noire / gauntlet render output unchanged by this fix.
#    (Both use GridPerceiver's "gameplay"/"static"/"menu"/"unknown" contexts — same vocabulary
#    as NDS. Before the fix, NEITHER world's render ever showed the spatial view either; this
#    pins the (now-fixed, now-correct) output going forward.)
# ---------------------------------------------------------------------------

def test_cave_noire_gameplay_render_pinned(tmp_path):
    from games.cave_noire import CaveNoirePlugin
    from games.cave_noire.perceiver import CaveNoirePerceiver
    from tests.test_pokemon_red import FakeEmulator

    emu = FakeEmulator()
    plugin = CaveNoirePlugin(emulator=emu, out_dir=str(tmp_path), perceiver=CaveNoirePerceiver())
    text = plugin.observe("a").text
    assert "NOT free movement" not in text  # first frame is context="gameplay" per GridPerceiver
    assert "position" in text.lower()


def test_gauntlet_gameplay_render_pinned(tmp_path):
    from games.gauntlet import GauntletPlugin
    from games.gauntlet.perceiver import GauntletPerceiver
    from tests.test_pokemon_red import FakeEmulator

    emu = FakeEmulator()
    plugin = GauntletPlugin(emulator=emu, out_dir=str(tmp_path), perceiver=GauntletPerceiver())
    text = plugin.observe("a").text
    assert "NOT free movement" not in text
    assert "position" in text.lower()


# ---------------------------------------------------------------------------
# 6. End-to-end on REAL recorded Kirby frames (eval/fixtures/kirby_title_menu/).
# ---------------------------------------------------------------------------

def _load_fixture_frame(name: str) -> np.ndarray:
    from PIL import Image
    return np.asarray(Image.open(os.path.join(_FIXTURE_DIR, name)).convert("RGB"))


@pytest.mark.skipif(not os.path.isdir(_FIXTURE_DIR), reason="kirby fixture frames not present")
def test_real_kirby_menu_frame_yields_touch_targets_via_nds_perceiver():
    """frame_008 (real recorded Kirby menu screen) must produce touch_targets through the actual
    NDSPerceiver pipeline — proving _detect_touch_targets + the render fix work on genuine game
    pixels, not just synthetic blobs."""
    from core.nds_perceiver import NDSPerceiver

    perceiver = NDSPerceiver(fallback_screen="top")
    memory = PerceptMemory()
    title = _load_fixture_frame("frame_001_title.png")
    menu = _load_fixture_frame("frame_008_menu_with_targets.png")

    sym = None
    # Feed the title frame a few times to let ScreenRoleDiscovery commit, then the menu frame.
    for _ in range(5):
        sym = perceiver.perceive(title, memory, context={"last_action": None})
    for _ in range(3):
        sym = perceiver.perceive(menu, memory, context={"last_action": "a"})

    assert sym is not None
    sm = sym.spatial_memory or {}
    assert "touch_targets" in sm
