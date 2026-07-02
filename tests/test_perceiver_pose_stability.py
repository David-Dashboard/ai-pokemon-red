"""Golden-replay regression for the Oak's-lab cutscene pose corruption (2026-07-02 diagnosis).

Root cause (from runs/brain_red_starter/world/oracle.jsonl + frame_*.png, replayed here from the
committed fixture slice in eval/fixtures/starter_cutscene_pose/): the auto-walk cutscene at Oak's lab
spikes the best-shift residual with no real warp. The old code treated ANY large residual + a direction
as an attributed door transition, which minted a bogus place (s537), then a cell-keyed reverse edge let
a LATER unrelated scene change reuse that bogus place and reset pose to (0,0) (s543) -- while the REAL
map 0->40 lab warp (s541, during a directionless `wait`) was silently missed. The party stayed empty
because the brain, misled about its position, stalled on a phantom 2-cell map. The PR-#44 review then
showed a residual spike + a SINGLE direction also mints (f538->f539 'up' at diff 42.87), so gating on
direction alone was not enough.

The fix: a transition requires POSITIVE evidence -- the plugin's live fade watch (ctx["transition"])
AND a single unambiguous commanded direction (`_single_dir`). Everything else (residual-only scene
cuts, fades on wait/mixed actions) drops pose to UNKNOWN ("lost"), writing NO wall/visited-cell/edge,
until a single-direction step settles on REAL emulator progress (ctx["frames_advanced"] > 0 -- two
consecutive observes can return the byte-identical frame when the frame counter stalls, e.g. f539/f540
both logged frame 13224, and a diff of 0 on a frozen pair is not evidence of anything). Recovery then
re-anchors ONCE to a brand new place at (0,0) rather than guessing an identity.

Fixture note: the replayed slice skips the dialog steps s547-553 (Oak's speech; mode-detected 'dialog',
no odometry runs on them). The gap is sound only because f546 and f554-556 are byte-identical frames of
the same settled lab scene, so the perceiver's prev-frame baseline crosses the gap unchanged.

This test replays the committed frames + real recorded actions + frame-counter deltas through a fresh
OverworldPerceiver and checks the four invariants from the fix spec, plus the plugin's live wiring of
ctx["transition"] / ctx["frames_advanced"] (which the review found had never been supplied).
"""
from __future__ import annotations

import json
import os

import numpy as np
import pytest

from core.contracts import ToolCall
from core.perception import PerceptMemory, SymbolicState
from games.pokemon_red.perceiver import OverworldPerceiver

_FIXTURE_DIR = os.path.join(os.path.dirname(__file__), "..", "eval", "fixtures", "starter_cutscene_pose")


def _load_slice():
    with open(os.path.join(_FIXTURE_DIR, "oracle_slice.jsonl"), encoding="utf-8") as f:
        return [json.loads(line) for line in f]


def _frame(step: int):
    from PIL import Image
    path = os.path.join(_FIXTURE_DIR, f"frame_{step:06d}.png")
    return np.asarray(Image.open(path).convert("RGB"))


def _replay(steps):
    """Feed the recorded (frame, action, frames_advanced) triples for these oracle steps through a
    fresh perceiver. frames_advanced comes from the oracle records' emulator frame-counter deltas --
    exactly what the live plugin now supplies (0 for the frozen f537/f538 and f539/f540 pairs).
    Returns the list of (record, SymbolicState, places-count-after) tuples, in order."""
    recs = {r["step"]: r for r in _load_slice()}
    per, mem = OverworldPerceiver(), PerceptMemory()
    out, prev_fc = [], None
    for step in steps:
        r = recs[step]
        fa = None if prev_fc is None else r["frame"] - prev_fc
        prev_fc = r["frame"]
        s = per.perceive(_frame(step), mem, {"last_action": r["perceived"]["action"],
                                             "frame_path": "", "frames_advanced": fa})
        out.append((r, s, len(mem.data["places"])))
    return out, mem


# -- (49, 50): post-warp residual spike must not mint a place ------------------

def test_post_warp_residual_spike_goes_lost_not_minted():
    """s49/s50: a residual spike (100.85) on a single-direction 'up' right after a warp. Under the old
    residual+direction rule this MINTED a place (the reviewer's reproduction of the original bug); with
    fade-gated transitions it must instead drop pose to LOST -- no mint, no edge."""
    out, mem = _replay([49, 50])
    _, s, _ = out[-1]
    assert s.context == "overworld"
    assert s.pose.get("lost") is True
    assert len(mem.data["places"]) == 1 and mem.data["edges"] == {}


# -- (346, 347): a real warp UNDER the area threshold must still be handled ---

def test_real_warp_under_threshold_pair_replays_without_crashing():
    """s346/s347: the real map 0->37 warp scores only 16.39 (< the 30 area threshold) -- below the
    scene-change residual, so it is invisible to this perceiver's warp signal (a known pixels-only
    limitation, not something this fix claims to solve). It must still replay safely: no exception, and
    it must NOT be treated as a lost/unknown pose (a low residual is, by definition, not a scene change)."""
    out, _ = _replay([346, 347])
    _, s, _ = out[-1]
    assert s.context == "overworld"
    assert not (s.pose or {}).get("lost")


# -- the full cutscene corruption chain (535-546, +554-556 for re-anchor proof) ----
# (s547-553 are dialog-only steps; skipping them is sound because f546 == f554-556 byte-identical.)

_CUTSCENE_STEPS = [535, 536, 537, 538, 539, 540, 541, 542, 543, 544, 545, 546, 554, 555, 556]


def test_cutscene_span_mints_no_place_while_real_map_is_still_0():
    """(i) No place is minted or reused while the real (RAM-truth) map is still 0 (steps 535-540). The
    mixed-direction auto-walk actions, the single-direction residual spikes (s539, diff 42.87) AND the
    frozen-frame pairs (s538/s540, frames_advanced == 0) must all stay LOST on the original place 0 --
    unminted, unreused. Under the pre-review code s540 falsely settled here (frozen frame, diff 0)."""
    steps_on_map0 = [s for s in _CUTSCENE_STEPS if s <= 540]
    out, mem = _replay(steps_on_map0)
    assert all(r["watch"]["map"] == 0 for r, _, _ in out)
    assert all(s.pose["area"] == 0 for _, s, _ in out)     # no mint, no reuse, no phantom edge
    assert (out[-1][1].pose or {}).get("lost") is True      # s540 (frozen pair) did NOT settle
    assert len(mem.data["places"]) == 1


def test_cutscene_recovers_with_exactly_one_fresh_reanchor():
    """(ii) Across the whole chain there is EXACTLY ONE re-anchor -- at s555 (the first single-direction
    step with a settled residual on real emulator progress, frames_advanced 48) -- and it lands on a
    brand-new place, never back on place 0 and never on a reused id (the original bug teleported pose
    through a stale cell-keyed edge into the s537-minted phantom)."""
    out, mem = _replay(_CUTSCENE_STEPS)
    areas = [(r["step"], s.pose["area"]) for r, s, _ in out if s.context == "overworld"]
    changes = [(step, b) for (_, a), (step, b) in zip(areas, areas[1:]) if b != a]
    assert changes == [(555, 1)]                       # one re-anchor, at s555, to the one fresh id
    assert len(mem.data["places"]) == 2                # place 0 (stale) + exactly one fresh anchor
    assert mem.data["edges"] == {}                     # and never a phantom door edge


def test_pose_at_the_starter_table_is_the_fresh_anchor_not_a_phantom():
    """(iii) Once pose settles at the starter table (s555-556, real map == 40; s554 is still the tail of
    the 'lost' streak, it has not settled yet), it sits on ONE consistent fresh place -- not split across
    places, and not the stale place 0 the old bug would have reset pose back to."""
    out, _ = _replay(_CUTSCENE_STEPS)
    table_states = [s for r, s, _ in out if r["step"] in (555, 556)]
    assert all(not (s.pose or {}).get("lost") for s in table_states)   # both genuinely settled
    areas = {s.pose["area"] for s in table_states}
    assert len(areas) == 1        # one consistent anchor across the settled table interaction
    assert 0 not in areas         # not the stale pre-cutscene place


def test_no_wall_written_anywhere_while_pose_is_unknown():
    """(iv) No wall is ever written/surfaced while pose is UNKNOWN (lost). Every recorded 'lost' step
    must show an empty walls_here (occupancy writes are skipped entirely on that code path)."""
    out, _ = _replay(_CUTSCENE_STEPS)
    lost_states = [s for _, s, _ in out if (s.pose or {}).get("lost")]
    assert len(lost_states) >= 1     # the fixture does exercise the lost path
    assert all(s.spatial_memory.get("walls_here") == [] for s in lost_states)


def test_mixed_direction_action_never_transits_even_with_a_high_residual():
    """Unit-level pin: `down+left+up+right` (the cutscene auto-walk probe) must resolve to no direction,
    so neither a transition nor a wall write can ever be attributed to it."""
    from games.pokemon_red.perceiver import _single_dir
    assert _single_dir("down+left+up+right") is None
    assert _single_dir("up+up+up") == "up"        # repeated SAME direction still resolves
    assert _single_dir("up+a") == "up"            # non-directional tokens don't break agreement
    assert _single_dir("wait") is None
    assert _single_dir(None) is None


def test_single_direction_residual_spike_without_fade_does_not_transit():
    """Unit-level pin for the review's HIGH finding: a single-direction action + a scene-cut residual,
    with NO fade flag, must go LOST -- not transit (the f538->f539 'up' @ 42.87 reproduction)."""
    per, mem = OverworldPerceiver(), PerceptMemory()
    rng = np.random.RandomState(11)
    a = rng.randint(0, 200, size=(144, 160, 3)).astype(np.uint8)
    b = rng.randint(0, 200, size=(144, 160, 3)).astype(np.uint8)   # unrelated scene: no shift aligns
    per.perceive(a, mem, {"last_action": None})
    per.perceive(np.roll(a, -16, axis=1), mem, {"last_action": "right"})   # a real move (baseline)
    s = per.perceive(b, mem, {"last_action": "up"})                # scene cut, single dir, NO fade
    assert s.pose.get("lost") is True
    assert len(mem.data["places"]) == 1 and mem.data["edges"] == {}


# -- the plugin's live wiring of ctx["transition"] / ctx["frames_advanced"] ----
# (the review's root finding: the perceiver's fade flag existed but was NEVER supplied on the lean path)

class _CtxCapture:
    """A perceiver that just records the context the plugin hands it."""

    def __init__(self):
        self.contexts = []

    def perceive(self, frame, memory, context=None):
        self.contexts.append(dict(context or {}))
        return SymbolicState(confidence=0.0, context="overworld")


def _textured(seed: int = 3):
    g = np.random.RandomState(seed).randint(0, 200, size=(144, 160), dtype=np.uint16).astype(np.uint8)
    f = np.zeros((144, 160, 3), dtype=np.uint8)
    f[..., 0] = f[..., 1] = f[..., 2] = g
    return f


class _FadeEmu:
    """Fake emulator whose screen shows a near-uniform fade frame while its frame counter is inside
    [fade_lo, fade_hi) -- textured gameplay otherwise. Ticks/presses advance the counter."""

    BUTTONS = ("a", "b", "start", "select", "up", "down", "left", "right")

    def __init__(self, fade_lo=10 ** 9, fade_hi=10 ** 9):
        self._frame = 0
        self.fade_lo, self.fade_hi = fade_lo, fade_hi

    def press(self, button, hold_frames=8, settle_frames=16):
        self._frame += hold_frames + settle_frames

    def tick(self, frames):
        self._frame += frames

    def read(self, addr):
        return 0

    def save_screen(self, path):
        open(path, "wb").close()

    def screen_ndarray(self):
        if self.fade_lo <= self._frame < self.fade_hi:
            return np.full((144, 160, 3), 255, dtype=np.uint8)   # all-white fade frame (std 0)
        return _textured()

    def load_state(self, path):
        pass

    def save_state(self, path):
        pass

    @property
    def frame(self):
        return self._frame

    def close(self):
        pass


def _wait_call(frames):
    return ToolCall(tool="wait", args={"frames": frames}, agent_id="a", call_id="c")


def test_plugin_fade_watch_flags_transition_seen_during_wait(tmp_path):
    """A fade that happens mid-`wait` (the s541 real-warp case: map crossed during `wait 60`) is caught
    by the chunked-tick sampling and surfaced as ctx["transition"] on the next observe -- then the latch
    resets, so a later fade-free action reads False."""
    from core.perception_plugin import PerceptionPlugin
    cap = _CtxCapture()
    emu = _FadeEmu(fade_lo=8, fade_hi=16)              # screen fades between ticks 8..16
    p = PerceptionPlugin(emulator=emu, out_dir=str(tmp_path), perceiver=cap)
    p.handle(_wait_call(24))                            # samples every ~4 ticks -> sees the fade
    p.observe("a")
    assert cap.contexts[-1]["transition"] is True
    p.handle(_wait_call(24))                            # counter now past the fade window: no fade
    p.observe("a")
    assert cap.contexts[-1]["transition"] is False      # consumed + re-armed, not stuck latched


def test_plugin_fade_watch_samples_after_each_button_press(tmp_path):
    """A door-walk fade (visible right after a press's hold+settle ticks) is caught by the per-press
    sample in press_sequence handling."""
    from core.perception_plugin import PerceptionPlugin
    cap = _CtxCapture()
    emu = _FadeEmu(fade_lo=24, fade_hi=48)             # fade visible after the first press (24 frames)
    p = PerceptionPlugin(emulator=emu, out_dir=str(tmp_path), perceiver=cap)
    p.handle(ToolCall(tool="press_button", args={"button": "up"}, agent_id="a", call_id="c"))
    p.observe("a")
    assert cap.contexts[-1]["transition"] is True


def test_plugin_passes_frames_advanced_delta(tmp_path):
    """ctx["frames_advanced"] is the emulator frame-counter delta since the last observe -- >0 across a
    real action, and exactly 0 when nothing ticked (the frozen-frame pair the settle guard needs)."""
    from core.perception_plugin import PerceptionPlugin
    cap = _CtxCapture()
    p = PerceptionPlugin(emulator=_FadeEmu(), out_dir=str(tmp_path), perceiver=cap)
    p.handle(_wait_call(24))
    p.observe("a")
    assert cap.contexts[-1]["frames_advanced"] == 24
    p.observe("a")                                      # no action between observes: frozen pair
    assert cap.contexts[-1]["frames_advanced"] == 0


def test_pose_lost_is_surfaced_truthfully_to_the_render(tmp_path):
    """Honesty check (spec #2): when pose is lost, core.perception_plugin._render_symbolic must say so,
    not silently show the stale/frozen dead-reckoned position as if it were still trustworthy."""
    from core.perception_plugin import PerceptionPlugin

    class _FakeEmu:
        BUTTONS = ("a", "b", "up", "down", "left", "right", "start", "select")
        def __init__(self):
            self._frame = 0
        def press(self, *a, **k):
            self._frame += 1
        def tick(self, *a, **k):
            self._frame += 1
        def save_screen(self, path):
            open(path, "wb").close()
        def screen_ndarray(self):
            return _frame(537)
        def load_state(self, path):
            pass
        def save_state(self, path):
            pass
        @property
        def frame(self):
            return self._frame
        def close(self):
            pass

    per = OverworldPerceiver()
    plugin = PerceptionPlugin(emulator=_FakeEmu(), out_dir=str(tmp_path), perceiver=per)
    plugin._percept_memory.data.update({"pose_confidence": "unknown", "cursor": (0, 0), "place": 0,
                                        "places": {0: {}}, "prev_frame": _frame(536), "resync": False,
                                        "next_place": 1, "edges": {}})
    plugin._last_action = "down+left+up+right"
    obs = plugin.observe("a")
    assert "position lost" in obs.text.lower()
    assert obs.data["pose"].get("lost") is True


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-q"]))
