"""Unit tests for the NDS continuous-time skill port (world_mcp.World.define_skill/run_skill on
--game nds), per reports/2026-07-04-mkds-continuous-time-build-plan.md (the build spec) and
reports/2026-07-04-continuous-time-stopwhen-design.md (the design it implements). CI-safe: no
py-desmume, no real ROM -- nds's World is built directly against a FakeNDSEmulator (mirrors
tests/test_pokemon_red.py's FakeEmulator, extended with the NDS screen_ndarray("both") shape) and a
small scripted Perceiver (tests/test_kirby_skill_port.py's _ScriptedPerceiver pattern) so
elapsed_frames/idle_settled fire deterministically without depending on NDSPerceiver's real pixel
algorithm or a live emulator's frame timing.

Covers (mirrors tests/test_kirby_skill_port.py's coverage, adapted to NDS's frame-counted enum):
  1. define_skill: valid definitions accepted + logged verbatim; malformed definitions rejected loudly.
  2. run_skill: step dispatch (each step resolves to the exact press/tick execution path), unknown skill.
  3. Each pinned stop_when predicate: elapsed_frames, idle_settled (fires + does not fire).
  4. Loop caps: max_iters <= 8 enforced; nesting rejected.
  5. Reachability / define-time satisfiability: elapsed_frames(n) needs n<=F; idle_settled needs k*s<=F;
     idle_settled's threshold must be in the open interval (0, 1).
  6. The frame-ceiling absolute cap, enforced regardless of the skill's own definition.
  7. Logging shape: skills.jsonl gets one define_skill record + one run_skill record with executed
     steps, stop reason, executed-step count, world_frames_used, and stop_when_fired (the conditional-
     half gate field the eventual A/B scorer needs, design §7).
  8. Skill lifetime: skills live only in the World object, gone when a fresh session starts.
  9. No-leak: define_skill/run_skill results never carry an oracle/RAM field.
  10. Gating: NDS_SKILLS on/off, KIRBY_SKILLS/ARC_SKILLS must not leak the tools onto nds and vice versa,
      other games never see these tools even with NDS_SKILLS=1 set.
  11. The "none" pseudo-button (passive body) is valid; an idle_settled loop with an ACTING body never
      accumulates a streak (design §6/§7: acting body resets idle_settled's streak every sample).
"""
from __future__ import annotations

import argparse
import json

import numpy as np
import pytest

from core.gateway import Gateway
from core.perception import PerceptMemory, SymbolicState
from core.perception_plugin import PerceptionPlugin
from core.permissions import Allowlist

import world_mcp
from world_mcp import World, _NDS_SKILL_MAX_WORLD_FRAMES, _NDS_SKILL_SAMPLE_STRIDE, _static_tools


class FakeNDSEmulator:
    """Minimal stand-in for core.nds_emulator.DeSmuMEEmulator: same press/tick/frame surface as
    tests/test_pokemon_red.py's FakeEmulator, but screen_ndarray(screen="both") returns the NDS
    (384, 256, 3) shape (default arg matches DeSmuMEEmulator.screen_ndarray's signature) and press()
    always advances by hold_frames + settle_frames -- the exact accounting world_mcp's executor reads
    off `emu.frame` deltas for, never assumed."""

    BUTTONS = ("a", "b", "x", "y", "l", "r", "start", "select", "up", "down", "left", "right")

    def __init__(self) -> None:
        self._frame = 0
        # A queue of (frame_index -> pct_changed-driving) screens. Tests drive idle_settled/elapsed_frames
        # by pushing a sequence of frames via `self.screens`; screen_ndarray() pops the next one each
        # call (repeating the last once exhausted), so successive samples see the scripted sequence.
        self.screens: list[np.ndarray] = [np.zeros((384, 256, 3), dtype=np.uint8)]
        self._screen_i = 0

    def press(self, button, hold_frames=8, settle_frames=16):
        self._frame += hold_frames + settle_frames

    def tick(self, frames):
        self._frame += max(1, frames)

    def screen_ndarray(self, screen="both"):
        if self._screen_i < len(self.screens):
            s = self.screens[self._screen_i]
            self._screen_i += 1
        else:
            s = self.screens[-1] if self.screens else np.zeros((384, 256, 3), dtype=np.uint8)
        return s

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


class _ScriptedPerceiver:
    """Same shape as tests/test_kirby_skill_port.py's _ScriptedPerceiver -- a pre-programmed queue of
    SymbolicStates, one per perceive() call (repeats the last once exhausted). Decouples the skill
    executor's own logic from NDSPerceiver's real pixel algorithm (covered elsewhere)."""

    def __init__(self, states: list[SymbolicState]) -> None:
        self._states = list(states)
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


def _make_world(out, *, states=None, screens=None, game="nds") -> World:
    """Build a real World against nds's own plugin/perceiver-module wiring, but with a FakeNDSEmulator
    (no py-desmume) and a scripted perceiver standing in for NDSPerceiver's real pixel algorithm.
    `screens`, if given, seeds the emulator's scripted screen_ndarray() queue -- tests drive
    idle_settled/elapsed_frames by pushing a sequence of frames with known pixel-change between them."""
    spec = world_mcp.GAMES[game]
    emu = FakeNDSEmulator()
    if screens is not None:
        emu.screens = list(screens)
    perceiver = _ScriptedPerceiver(states) if states is not None else _ScriptedPerceiver([_default_state()])
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
    w.nds_skills_world = game in world_mcp._NDS_SKILLS_WORLDS
    w._nds_skills_enabled = w.nds_skills_world and world_mcp._nds_skills_enabled()
    w.skills = {}
    import os
    w._skill_log_path = os.path.join(out, "skills.jsonl")
    return w


@pytest.fixture(autouse=True)
def _skills_on_by_default(monkeypatch):
    """This file tests the skill MECHANISM, orthogonal to the NDS_SKILLS gate itself (section 10 below
    tests the gate). Default the flag ON so mechanism tests don't all need to set it."""
    monkeypatch.setenv("NDS_SKILLS", "1")
    monkeypatch.delenv("KIRBY_SKILLS", raising=False)
    monkeypatch.delenv("ARC_SKILLS", raising=False)


def _load_jsonl(path: str) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def _quiet_frames(n: int, base_val: int = 10) -> list[np.ndarray]:
    """n frames that are pixel-IDENTICAL to each other (pct_changed == 0.0 between any consecutive
    pair) -- drives idle_settled's dwell counter up cleanly."""
    frame = np.full((384, 256, 3), base_val, dtype=np.uint8)
    return [frame.copy() for _ in range(n)]


def _loud_frame() -> np.ndarray:
    """A single frame that differs from a base_val=10 frame by 255 in every channel -- pct_changed
    == 1.0 against any `_quiet_frames` frame, comfortably above any valid threshold (< 1.0)."""
    return np.full((384, 256, 3), 255, dtype=np.uint8)


# ---------------------------------------------------------------------------
# 1. define_skill: accept valid, reject malformed
# ---------------------------------------------------------------------------

def test_define_skill_accepts_flat_step_list(tmp_path):
    w = _make_world(str(tmp_path / "out"))
    result = w.call("define_skill", {"name": "launch", "steps": [{"button": "a"}, {"button": "a"}]})
    text = " ".join(c["text"] for c in result if c.get("type") == "text")
    assert "define_skill 'launch' -> ok, 2 top-level step(s)" in text
    assert "launch" in w.skills


def test_define_skill_accepts_none_pseudo_button(tmp_path):
    """"none" (no input this step) is valid -- the passive-body idle_settled use case (design §6)."""
    w = _make_world(str(tmp_path / "out"))
    result = w.call("define_skill", {"name": "wait_out", "steps": [{"button": "none", "hold_frames": 20}]})
    text = " ".join(c["text"] for c in result if c.get("type") == "text")
    assert "ok, 1 top-level step(s)" in text
    assert "wait_out" in w.skills


def test_define_skill_rejects_empty_steps(tmp_path):
    w = _make_world(str(tmp_path / "out"))
    result = w.call("define_skill", {"name": "noop", "steps": []})
    text = " ".join(c["text"] for c in result if c.get("type") == "text")
    assert "must be a non-empty list" in text
    assert "noop" not in w.skills


def test_define_skill_rejects_unknown_button(tmp_path):
    w = _make_world(str(tmp_path / "out"))
    result = w.call("define_skill", {"name": "bad", "steps": [{"button": "diagonal"}]})
    text = " ".join(c["text"] for c in result if c.get("type") == "text")
    assert "is not valid" in text
    assert "bad" not in w.skills


def test_define_skill_rejects_missing_name(tmp_path):
    w = _make_world(str(tmp_path / "out"))
    result = w.call("define_skill", {"name": "", "steps": [{"button": "a"}]})
    text = " ".join(c["text"] for c in result if c.get("type") == "text")
    assert "non-empty string" in text


def test_define_skill_rejects_bad_hold_frames(tmp_path):
    w = _make_world(str(tmp_path / "out"))
    result = w.call("define_skill", {"name": "bad", "steps": [{"button": "a", "hold_frames": 0}]})
    text = " ".join(c["text"] for c in result if c.get("type") == "text")
    assert "hold_frames must be an int in [1, 120]" in text


def test_define_skill_logs_definition_verbatim(tmp_path):
    out = str(tmp_path / "out")
    w = _make_world(out)
    steps = [{"button": "a"}, {"button": "a"}]
    w.call("define_skill", {"name": "launch", "steps": steps})
    rows = _load_jsonl(f"{out}/skills.jsonl")
    define_rows = [r for r in rows if r["event"] == "define_skill"]
    assert len(define_rows) == 1
    assert define_rows[0]["definition"] == {"name": "launch", "steps": steps}


# ---------------------------------------------------------------------------
# 2. run_skill: step dispatch + unknown skill
# ---------------------------------------------------------------------------

def test_run_skill_unknown_name_errors(tmp_path):
    w = _make_world(str(tmp_path / "out"))
    result = w.call("run_skill", {"name": "ghost"})
    text = " ".join(c["text"] for c in result if c.get("type") == "text")
    assert "no skill named 'ghost'" in text


def test_run_skill_executes_flat_steps_via_exact_press_path(tmp_path):
    out = str(tmp_path / "out")
    w = _make_world(out)
    w.call("define_skill", {"name": "launch", "steps": [{"button": "a"}, {"button": "a"}]})
    result = w.call("run_skill", {"name": "launch"})
    text = " ".join(c["text"] for c in result if c.get("type") == "text")
    assert "run_skill 'launch' -> 2 step(s) executed" in text
    assert "all top-level steps executed" in text
    # Each press() call is hold(8, default) + settle(16, default) = 24 frames -> 48 total.
    assert w.plugin.emu.frame == 48


def test_run_skill_stops_on_illegal_button_like_press_would(tmp_path):
    out = str(tmp_path / "out")
    w = _make_world(out)
    # Bypass define_skill's own validation to exercise the executor's own defense-in-depth.
    w.skills["bad"] = {"name": "bad", "steps": [{"button": "diagonal"}]}
    result = w.call("run_skill", {"name": "bad"})
    text = " ".join(c["text"] for c in result if c.get("type") == "text")
    assert "0 step(s) executed" in text
    assert "invalid button" in text


# ---------------------------------------------------------------------------
# 3. stop_when predicates
# ---------------------------------------------------------------------------

def test_elapsed_frames_fires_after_n_frames(tmp_path):
    out = str(tmp_path / "out")
    w = _make_world(out)
    # Each inner "a" press advances 24 frames (8 hold + 16 settle default). elapsed_frames(50) needs
    # >=50 frames elapsed since the loop started -> fires after the 3rd press (72 frames), not the 2nd (48).
    w.call("define_skill", {"name": "hold_a", "steps": [
        {"repeat_until": {"steps": [{"button": "a"}], "stop_when": "elapsed_frames(50)", "max_iters": 8}}]})
    result = w.call("run_skill", {"name": "hold_a"})
    text = " ".join(c["text"] for c in result if c.get("type") == "text")
    assert "elapsed_frames(50)" in text
    assert "72 frame(s)" in text
    assert "3 step(s) executed" in text


def test_elapsed_frames_does_not_fire_before_n(tmp_path):
    out = str(tmp_path / "out")
    w = _make_world(out)
    # n=200 (<=F=300, so definable) but max_iters=2 -> 2 presses = 48 frames, never reaches 200.
    w.call("define_skill", {"name": "hold_a", "steps": [
        {"repeat_until": {"steps": [{"button": "a"}], "stop_when": "elapsed_frames(200)", "max_iters": 2}}]})
    result = w.call("run_skill", {"name": "hold_a"})
    text = " ".join(c["text"] for c in result if c.get("type") == "text")
    assert "reached max_iters=2 without stop_when firing" in text


def test_idle_settled_fires_on_a_passive_quiet_streak(tmp_path):
    """The count-in scenario (design §6): a passive body ("none") ticking through a genuinely quiet
    run of frames. threshold=0.01, k=3 -- three consecutive stride-sampled frames identical to each
    other (pct_changed == 0.0 < 0.01) must satisfy the dwell."""
    out = str(tmp_path / "out")
    # hold_frames=40 with stride s=_NDS_SKILL_SAMPLE_STRIDE -> several samples inside one step; all
    # frames pixel-identical -> every sample reads pct_changed == 0.0, well under any valid threshold.
    screens = _quiet_frames(20)
    w = _make_world(out, screens=screens)
    w.call("define_skill", {"name": "wait_out", "steps": [
        {"repeat_until": {"steps": [{"button": "none", "hold_frames": 40}],
                          "stop_when": "idle_settled(0.01, 3)", "max_iters": 8}}]})
    result = w.call("run_skill", {"name": "wait_out"})
    text = " ".join(c["text"] for c in result if c.get("type") == "text")
    assert "idle_settled(0.01, 3)" in text
    assert "fired after" in text


def test_idle_settled_does_not_fire_during_active_play(tmp_path):
    """design §6/§7: idle_settled must NOT fire against an actively-changing scene (the active-play
    floor from the probe never drops near zero) -- alternating loud/quiet frames never build a streak."""
    out = str(tmp_path / "out")
    # Alternate loud/quiet so consecutive pct_changed readings never stay below threshold for 2 in a row.
    quiet = np.full((384, 256, 3), 10, dtype=np.uint8)
    loud = _loud_frame()
    # 3 iterations x (1 initial "prev" pop + 4 stride samples) == 15 pops in the worst case (it never
    # fires, so all 3 iterations run) -- supply well more than enough alternating frames so the queue
    # never runs dry and silently repeats (which would falsely read as "identical", i.e. pct==0.0).
    screens = [quiet, loud] * 12
    w = _make_world(out, screens=screens)
    w.call("define_skill", {"name": "wait_out", "steps": [
        {"repeat_until": {"steps": [{"button": "none", "hold_frames": _NDS_SKILL_SAMPLE_STRIDE * 4}],
                          "stop_when": "idle_settled(0.01, 2)", "max_iters": 3}}]})
    result = w.call("run_skill", {"name": "wait_out"})
    text = " ".join(c["text"] for c in result if c.get("type") == "text")
    assert "reached max_iters=3 without stop_when firing" in text


def test_idle_settled_streak_resets_on_a_loud_sample(tmp_path):
    """A single above-threshold sample must reset the dwell counter, not just pause it -- k consecutive
    quiet samples are required, not k total."""
    out = str(tmp_path / "out")
    quiet = np.full((384, 256, 3), 10, dtype=np.uint8)
    loud = _loud_frame()
    # One iteration of hold_frames=4*s pops 1 initial "prev" frame + 4 stride samples == 5 pops total.
    # Sequence: prev=quiet; samples vs (quiet,quiet,loud,quiet) -> pct (0,0,1,1) -> streak (1,2,0,0).
    # Streak reaches 2 then resets on the loud sample and never climbs back to k=3 before max_iters=1
    # ends the loop -- proves a single loud sample resets the dwell counter, not merely pauses it.
    screens = [quiet, quiet, quiet, loud, quiet]
    w = _make_world(out, screens=screens)
    w.call("define_skill", {"name": "wait_out", "steps": [
        {"repeat_until": {"steps": [{"button": "none", "hold_frames": _NDS_SKILL_SAMPLE_STRIDE * 4}],
                          "stop_when": "idle_settled(0.01, 3)", "max_iters": 1}}]})
    result = w.call("run_skill", {"name": "wait_out"})
    text = " ".join(c["text"] for c in result if c.get("type") == "text")
    assert "reached max_iters=1 without stop_when firing" in text


def test_idle_settled_with_acting_body_is_self_defeating(tmp_path):
    """design §7: pairing idle_settled with an ACTING body is self-defeating because a press() call
    only takes ONE sample (start vs end of the whole press) -- if that single sample is loud, the
    streak never even starts. This test pins that documented degenerate case behaves as expected
    (never fires), not as a silent success."""
    out = str(tmp_path / "out")
    quiet = np.full((384, 256, 3), 10, dtype=np.uint8)
    loud = _loud_frame()
    screens = [quiet, loud, quiet, loud, quiet, loud, quiet, loud]
    w = _make_world(out, screens=screens)
    w.call("define_skill", {"name": "act_and_wait", "steps": [
        {"repeat_until": {"steps": [{"button": "a"}], "stop_when": "idle_settled(0.01, 2)", "max_iters": 3}}]})
    result = w.call("run_skill", {"name": "act_and_wait"})
    text = " ".join(c["text"] for c in result if c.get("type") == "text")
    assert "reached max_iters=3 without stop_when firing" in text


def test_stop_when_rejects_predicate_outside_pinned_enum(tmp_path):
    """region_changed is Kirby's enum, not NDS's -- must be rejected here (NDS defers foveated
    region_* to the 3D-perception climb, design §3)."""
    w = _make_world(str(tmp_path / "out"))
    result = w.call("define_skill", {"name": "bad", "steps": [
        {"repeat_until": {"steps": [{"button": "a"}],
                          "stop_when": "region_changed(0,0,10,10)", "max_iters": 8}}]})
    text = " ".join(c["text"] for c in result if c.get("type") == "text")
    assert "not one of the pinned NDS predicates" in text


def test_stop_when_rejects_n_above_frame_ceiling(tmp_path):
    w = _make_world(str(tmp_path / "out"))
    result = w.call("define_skill", {"name": "bad", "steps": [
        {"repeat_until": {"steps": [{"button": "a"}],
                          "stop_when": f"elapsed_frames({_NDS_SKILL_MAX_WORLD_FRAMES + 1})",
                          "max_iters": 8}}]})
    text = " ".join(c["text"] for c in result if c.get("type") == "text")
    assert "n must satisfy" in text


def test_stop_when_rejects_zero_n(tmp_path):
    w = _make_world(str(tmp_path / "out"))
    result = w.call("define_skill", {"name": "bad", "steps": [
        {"repeat_until": {"steps": [{"button": "a"}], "stop_when": "elapsed_frames(0)", "max_iters": 8}}]})
    text = " ".join(c["text"] for c in result if c.get("type") == "text")
    assert "n must satisfy" in text


def test_stop_when_rejects_idle_settled_threshold_at_or_above_one(tmp_path):
    w = _make_world(str(tmp_path / "out"))
    result = w.call("define_skill", {"name": "bad", "steps": [
        {"repeat_until": {"steps": [{"button": "none", "hold_frames": 10}],
                          "stop_when": "idle_settled(1.0, 3)", "max_iters": 8}}]})
    text = " ".join(c["text"] for c in result if c.get("type") == "text")
    assert "threshold must satisfy 0.005 < threshold < 0.06" in text


def test_stop_when_rejects_idle_settled_threshold_at_or_below_zero(tmp_path):
    w = _make_world(str(tmp_path / "out"))
    result = w.call("define_skill", {"name": "bad", "steps": [
        {"repeat_until": {"steps": [{"button": "none", "hold_frames": 10}],
                          "stop_when": "idle_settled(0.0, 3)", "max_iters": 8}}]})
    text = " ".join(c["text"] for c in result if c.get("type") == "text")
    assert "threshold must satisfy 0.005 < threshold < 0.06" in text


def test_stop_when_rejects_idle_settled_threshold_above_band_ceiling(tmp_path):
    """design §7's threshold-gaming guard: a threshold above the ~6% active-play floor would let
    idle_settled trivially fire during active play too, defeating the PASSIVE-vs-ACTIVE distinction --
    must be rejected even though 0.1 is still inside the open (0, 1) interval."""
    w = _make_world(str(tmp_path / "out"))
    result = w.call("define_skill", {"name": "bad", "steps": [
        {"repeat_until": {"steps": [{"button": "none", "hold_frames": 10}],
                          "stop_when": "idle_settled(0.1, 3)", "max_iters": 8}}]})
    text = " ".join(c["text"] for c in result if c.get("type") == "text")
    assert "threshold must satisfy 0.005 < threshold < 0.06" in text


def test_stop_when_rejects_idle_settled_threshold_below_band_floor(tmp_path):
    """Symmetric case: a threshold below the count-in hold's own ~0.5% noise floor would never
    reliably fire on real data -- rejected even though 0.001 is still inside the open (0, 1) interval."""
    w = _make_world(str(tmp_path / "out"))
    result = w.call("define_skill", {"name": "bad", "steps": [
        {"repeat_until": {"steps": [{"button": "none", "hold_frames": 10}],
                          "stop_when": "idle_settled(0.001, 3)", "max_iters": 8}}]})
    text = " ".join(c["text"] for c in result if c.get("type") == "text")
    assert "threshold must satisfy 0.005 < threshold < 0.06" in text


def test_stop_when_rejects_idle_settled_unreachable_k_times_s_over_ceiling(tmp_path):
    """design §5's satisfiability rule: k*s <= F must be enforced at DEFINE time, not discovered at
    runtime -- a box that can never fire (mirrors world_mcp.py's Kirby region_changed size-cap check)."""
    w = _make_world(str(tmp_path / "out"))
    unreachable_k = (_NDS_SKILL_MAX_WORLD_FRAMES // _NDS_SKILL_SAMPLE_STRIDE) + 5
    result = w.call("define_skill", {"name": "bad", "steps": [
        {"repeat_until": {"steps": [{"button": "none", "hold_frames": 10}],
                          "stop_when": f"idle_settled(0.01, {unreachable_k})", "max_iters": 8}}]})
    text = " ".join(c["text"] for c in result if c.get("type") == "text")
    assert "k*s <= F required" in text


def test_stop_when_rejects_idle_settled_k_zero(tmp_path):
    w = _make_world(str(tmp_path / "out"))
    result = w.call("define_skill", {"name": "bad", "steps": [
        {"repeat_until": {"steps": [{"button": "none", "hold_frames": 10}],
                          "stop_when": "idle_settled(0.01, 0)", "max_iters": 8}}]})
    text = " ".join(c["text"] for c in result if c.get("type") == "text")
    assert "k must be >= 1" in text


def test_hp_or_ram_style_predicate_rejected():
    """No oracle/RAM field ever enters stop_when -- same no-leak law as Kirby's hp_dropped rejection."""
    from world_mcp import World
    with pytest.raises(ValueError, match="not one of the pinned NDS predicates"):
        World._parse_nds_stop_when("checkpoint_reached")


def test_region_changed_style_predicate_rejected_not_in_this_enum():
    """Foveated region_* is explicitly deferred to the 3D-perception climb (design §3) -- NOT in this
    rung's enum, unlike Kirby's."""
    from world_mcp import World
    with pytest.raises(ValueError, match="not one of the pinned NDS predicates"):
        World._parse_nds_stop_when("region_changed(0,0,10,10)")


# ---------------------------------------------------------------------------
# 4. Loop caps: max_iters <= 8; no nesting
# ---------------------------------------------------------------------------

def test_max_iters_above_cap_rejected(tmp_path):
    w = _make_world(str(tmp_path / "out"))
    result = w.call("define_skill", {"name": "bad", "steps": [
        {"repeat_until": {"steps": [{"button": "a"}], "stop_when": "elapsed_frames(24)", "max_iters": 9}}]})
    text = " ".join(c["text"] for c in result if c.get("type") == "text")
    assert "max_iters must be an int in [1, 8]" in text


def test_max_iters_zero_rejected(tmp_path):
    w = _make_world(str(tmp_path / "out"))
    result = w.call("define_skill", {"name": "bad", "steps": [
        {"repeat_until": {"steps": [{"button": "a"}], "stop_when": "elapsed_frames(24)", "max_iters": 0}}]})
    text = " ".join(c["text"] for c in result if c.get("type") == "text")
    assert "max_iters must be an int in [1, 8]" in text


def test_nested_repeat_until_rejected(tmp_path):
    w = _make_world(str(tmp_path / "out"))
    result = w.call("define_skill", {"name": "bad", "steps": [
        {"repeat_until": {"steps": [{"repeat_until": {"steps": [{"button": "a"}],
                                                       "stop_when": "elapsed_frames(24)", "max_iters": 2}}],
                          "stop_when": "elapsed_frames(48)", "max_iters": 2}}]})
    text = " ".join(c["text"] for c in result if c.get("type") == "text")
    assert "nesting is not allowed" in text


# ---------------------------------------------------------------------------
# 5. The absolute frame ceiling F
# ---------------------------------------------------------------------------

def test_absolute_frame_ceiling_enforced_across_multiple_top_level_loops(tmp_path):
    out = str(tmp_path / "out")
    w = _make_world(out)
    # Each "a" press is 24 frames. One loop's own iteration budget is max_iters=8 x 24f = 192 frames,
    # so elapsed_frames(300) (the max definable value, F itself) never fires WITHIN a single loop (192
    # < 300) -- but 2 such loops back to back is 384 possible frames > F=300, so the ABSOLUTE ceiling
    # must cut the run off mid-way through the second loop, not either loop's own stop_when/max_iters.
    w.call("define_skill", {"name": "huge", "steps": [
        {"repeat_until": {"steps": [{"button": "a"}], "stop_when": "elapsed_frames(300)", "max_iters": 8}}
        for _ in range(2)
    ]})
    result = w.call("run_skill", {"name": "huge"})
    text = " ".join(c["text"] for c in result if c.get("type") == "text")
    assert f"stopped: absolute {_NDS_SKILL_MAX_WORLD_FRAMES}-frame ceiling hit" in text
    # 300 // 24 == 12 whole presses fit before the ceiling trips on the 13th.
    assert "12 step(s) executed" in text


# ---------------------------------------------------------------------------
# 6. Logging shape
# ---------------------------------------------------------------------------

def test_run_skill_log_has_all_pinned_fields(tmp_path):
    out = str(tmp_path / "out")
    w = _make_world(out)
    w.call("define_skill", {"name": "launch", "steps": [{"button": "a"}, {"button": "a"}]})
    w.call("run_skill", {"name": "launch"})
    rows = _load_jsonl(f"{out}/skills.jsonl")
    run_rows = [r for r in rows if r["event"] == "run_skill"]
    assert len(run_rows) == 1
    rec = run_rows[0]
    for key in ("executed", "executed_step_count", "stop_reason", "world_frames_used", "step", "name",
               "stop_when_fired"):
        assert key in rec, f"missing {key!r} in run_skill record: {rec}"
    assert rec["executed_step_count"] == 2
    assert rec["world_frames_used"] == 48
    assert rec["name"] == "launch"
    assert rec["stop_when_fired"] is False   # no repeat_until in this skill at all


def test_stop_when_fired_true_when_a_qualifying_predicate_fires(tmp_path):
    """design §7's conditional-half gate field: stop_when_fired must be True when a real predicate
    branch fired (not a ceiling/max_iters timeout)."""
    out = str(tmp_path / "out")
    w = _make_world(out)
    w.call("define_skill", {"name": "hold_a", "steps": [
        {"repeat_until": {"steps": [{"button": "a"}], "stop_when": "elapsed_frames(50)", "max_iters": 8}}]})
    w.call("run_skill", {"name": "hold_a"})
    rows = _load_jsonl(f"{out}/skills.jsonl")
    rec = [r for r in rows if r["event"] == "run_skill"][0]
    assert rec["stop_when_fired"] is True


def test_stop_when_fired_false_on_max_iters_exhaustion(tmp_path):
    out = str(tmp_path / "out")
    w = _make_world(out)
    # n=300 (max definable, <=F) but max_iters=2 -> only 48 frames elapse, never reaches 300.
    w.call("define_skill", {"name": "hold_a", "steps": [
        {"repeat_until": {"steps": [{"button": "a"}], "stop_when": "elapsed_frames(300)", "max_iters": 2}}]})
    w.call("run_skill", {"name": "hold_a"})
    rows = _load_jsonl(f"{out}/skills.jsonl")
    rec = [r for r in rows if r["event"] == "run_skill"][0]
    assert rec["stop_when_fired"] is False


def test_stop_when_fired_true_when_an_early_loop_fires_but_a_later_one_times_out(tmp_path):
    """Regression for the bug where stop_when_fired only checked executed[-1]: a skill with TWO
    sequential repeat_until blocks (design §6's launch+wait_out_banner shape) where the FIRST block's
    stop_when fires cleanly but the SECOND hits its own max_iters ceiling must still log True overall
    -- the qualifying evidence design §7's conditional-half gate needs must not be discarded just
    because the last top-level entry happened to be a timeout."""
    out = str(tmp_path / "out")
    w = _make_world(out)
    w.call("define_skill", {"name": "launch_then_stall", "steps": [
        # Block 1: fires after 3 presses (72 frames >= 50) -- mirrors
        # test_elapsed_frames_fires_after_n_frames's construction.
        {"repeat_until": {"steps": [{"button": "a"}], "stop_when": "elapsed_frames(50)", "max_iters": 8}},
        # Block 2: never reaches 200 frames within 2 iterations (48 frames) -- mirrors
        # test_elapsed_frames_does_not_fire_before_n's construction. This is the LAST executed entry.
        {"repeat_until": {"steps": [{"button": "a"}], "stop_when": "elapsed_frames(200)", "max_iters": 2}},
    ]})
    w.call("run_skill", {"name": "launch_then_stall"})
    rows = _load_jsonl(f"{out}/skills.jsonl")
    rec = [r for r in rows if r["event"] == "run_skill"][0]
    summaries = [e["repeat_until_summary"] for e in rec["executed"] if "repeat_until_summary" in e]
    assert len(summaries) == 2
    assert "fired after" in summaries[0]                                    # first (early) block
    assert "reached max_iters=2 without stop_when firing" in summaries[-1]  # second (later) block, last executed entry
    assert rec["stop_when_fired"] is True


def test_repeat_until_summary_carries_iterations_field(tmp_path):
    out = str(tmp_path / "out")
    w = _make_world(out)
    w.call("define_skill", {"name": "hold_a", "steps": [
        {"repeat_until": {"steps": [{"button": "a"}], "stop_when": "elapsed_frames(50)", "max_iters": 8}}]})
    w.call("run_skill", {"name": "hold_a"})
    rows = _load_jsonl(f"{out}/skills.jsonl")
    rec = [r for r in rows if r["event"] == "run_skill"][0]
    summary = [e for e in rec["executed"] if "repeat_until_summary" in e][0]
    assert summary["iterations"] == 3   # 3 presses (72 frames) needed to clear elapsed_frames(50)


# ---------------------------------------------------------------------------
# 7. Skill lifetime: within-run only
# ---------------------------------------------------------------------------

def test_skills_do_not_survive_a_new_session(tmp_path):
    out1 = str(tmp_path / "out1")
    w1 = _make_world(out1)
    w1.call("define_skill", {"name": "launch", "steps": [{"button": "a"}]})
    assert "launch" in w1.skills

    out2 = str(tmp_path / "out2")
    w2 = _make_world(out2)
    assert "launch" not in w2.skills


# ---------------------------------------------------------------------------
# 8. No-leak: no oracle/RAM field ever in a tool result
# ---------------------------------------------------------------------------

def test_define_and_run_skill_never_leak_oracle_fields(tmp_path):
    out = str(tmp_path / "out")
    w = _make_world(out)
    r1 = w.call("define_skill", {"name": "launch", "steps": [{"button": "a"}]})
    r2 = w.call("run_skill", {"name": "launch"})
    for result in (r1, r2):
        for c in result:
            if c.get("type") == "text":
                assert "0x" not in c["text"]   # no raw RAM address ever surfaces


# ---------------------------------------------------------------------------
# 9. Gating: NDS_SKILLS on/off, world scoping, KIRBY_SKILLS/ARC_SKILLS non-interference
# ---------------------------------------------------------------------------

def test_nds_skill_tools_absent_from_tools_list_by_default(monkeypatch):
    monkeypatch.delenv("NDS_SKILLS", raising=False)
    names = [t["name"] for t in _static_tools("nds")]
    assert "define_skill" not in names and "run_skill" not in names


def test_nds_skill_tools_present_in_tools_list_when_flag_on(monkeypatch):
    monkeypatch.setenv("NDS_SKILLS", "1")
    names = [t["name"] for t in _static_tools("nds")]
    assert "define_skill" in names and "run_skill" in names


def test_nds_skill_tools_never_leak_to_other_games(monkeypatch):
    monkeypatch.setenv("NDS_SKILLS", "1")
    for game in ("cave_noire", "cave_noire_baseline", "gauntlet", "gb_generic", "pokemon_red",
                "kirby_dreamland", "kirby_gba", "emerald_gba", "arcagi3"):
        names = [t["name"] for t in _static_tools(game)]
        assert "define_skill" not in names and "run_skill" not in names, f"{game} leaked skill tools"


def test_kirby_skills_flag_does_not_enable_nds_skill_tools(monkeypatch):
    """One-flag-per-world: KIRBY_SKILLS=1 alone must not unlock nds's skill tools."""
    monkeypatch.delenv("NDS_SKILLS", raising=False)
    monkeypatch.setenv("KIRBY_SKILLS", "1")
    names = [t["name"] for t in _static_tools("nds")]
    assert "define_skill" not in names and "run_skill" not in names


def test_arc_skills_flag_does_not_enable_nds_skill_tools(monkeypatch):
    monkeypatch.delenv("NDS_SKILLS", raising=False)
    monkeypatch.setenv("ARC_SKILLS", "1")
    names = [t["name"] for t in _static_tools("nds")]
    assert "define_skill" not in names and "run_skill" not in names


def test_nds_skills_flag_does_not_enable_kirby_skill_tools(monkeypatch):
    """Reverse direction: NDS_SKILLS=1 alone must not unlock kirby_dreamland's skill tools."""
    monkeypatch.delenv("KIRBY_SKILLS", raising=False)
    monkeypatch.setenv("NDS_SKILLS", "1")
    names = [t["name"] for t in _static_tools("kirby_dreamland")]
    assert "define_skill" not in names and "run_skill" not in names


def test_nds_skills_flag_does_not_enable_arc_skill_tools(monkeypatch):
    monkeypatch.delenv("ARC_SKILLS", raising=False)
    monkeypatch.setenv("NDS_SKILLS", "1")
    names = [t["name"] for t in _static_tools("arcagi3")]
    assert "define_skill" not in names and "run_skill" not in names


def test_dispatch_of_skill_tools_disabled_by_default(tmp_path, monkeypatch):
    monkeypatch.delenv("NDS_SKILLS", raising=False)
    w = _make_world(str(tmp_path / "out"))
    result = w.call("define_skill", {"name": "launch", "steps": [{"button": "a"}]})
    text = " ".join(c["text"] for c in result if c.get("type") == "text")
    assert "skill tools are disabled for this session" in text
    assert "launch" not in w.skills
    result2 = w.call("run_skill", {"name": "launch"})
    text2 = " ".join(c["text"] for c in result2 if c.get("type") == "text")
    assert "skill tools are disabled for this session" in text2


def test_dispatch_of_skill_tools_works_when_flag_on(tmp_path):
    w = _make_world(str(tmp_path / "out"))   # autouse fixture already sets NDS_SKILLS=1
    result = w.call("define_skill", {"name": "launch", "steps": [{"button": "a"}]})
    text = " ".join(c["text"] for c in result if c.get("type") == "text")
    assert "ok, 1 top-level step(s)" in text


def test_world_init_reads_nds_skills_once_at_construction(tmp_path, monkeypatch):
    """A/B arm isolation: NDS_SKILLS is read at World.__init__ time, not per-call."""
    monkeypatch.setenv("NDS_SKILLS", "1")
    w = _make_world(str(tmp_path / "out"))
    assert w._nds_skills_enabled is True
    monkeypatch.delenv("NDS_SKILLS", raising=False)
    assert w._nds_skills_enabled is True   # unaffected by env flip after construction


def test_nds_skills_scoped_to_nds_only_via_world_flag(tmp_path):
    """kirby_dreamland must NOT get NDS's skill tools even with NDS_SKILLS=1 -- the world-membership
    check (_NDS_SKILLS_WORLDS) is the actual gate."""
    w = _make_world(str(tmp_path / "out"), game="kirby_dreamland")
    assert w._nds_skills_enabled is False
    result = w.call("define_skill", {"name": "launch", "steps": [{"button": "a"}]})
    text = " ".join(c["text"] for c in result if c.get("type") == "text")
    assert "skill tools are disabled" in text


def test_top_level_stop_when_rejected_loudly(tmp_path):
    w = _make_world(str(tmp_path / "out"))
    result = w.call("define_skill", {"name": "bad", "steps": [{"button": "a"}],
                                     "stop_when": "elapsed_frames(24)"})
    text = " ".join(c["text"] for c in result if c.get("type") == "text")
    assert "belongs INSIDE a repeat_until step" in text
    assert "bad" not in w.skills


def test_redefinition_is_a_distinct_logged_event(tmp_path):
    out = str(tmp_path / "out")
    w = _make_world(out)
    w.call("define_skill", {"name": "launch", "steps": [{"button": "a"}]})
    w.call("define_skill", {"name": "launch", "steps": [{"button": "b"}]})
    rows = _load_jsonl(f"{out}/skills.jsonl")
    redefine_rows = [r for r in rows if r["event"] == "redefine_skill"]
    assert len(redefine_rows) == 1
    assert redefine_rows[0]["prior_definition"] == {"name": "launch", "steps": [{"button": "a"}]}
    assert redefine_rows[0]["definition"] == {"name": "launch", "steps": [{"button": "b"}]}
