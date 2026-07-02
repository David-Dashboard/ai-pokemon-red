"""Golden-replay regression for the Oak's-lab cutscene pose corruption (2026-07-02 diagnosis).

Root cause (from runs/brain_red_starter/world/oracle.jsonl + frame_*.png, replayed here from the
committed fixture slice in eval/fixtures/starter_cutscene_pose/): the auto-walk cutscene at Oak's lab
issues MIXED multi-directional actions (e.g. 'down+left+up+right') that spike the best-shift residual
with no real warp. The old code treated ANY large residual + a (possibly last-token) direction as an
attributed door transition, which minted a bogus place (s537), then a cell-keyed reverse edge let a
LATER unrelated scene change reuse that bogus place and reset pose to (0,0) (s543) -- while the REAL
map 0->40 lab warp (s541, during a directionless `wait`) was silently missed. The party stayed empty
because the brain, misled about its position, stalled on a phantom 2-cell map.

The fix: a large/faded residual alone never mints or reuses a place. It only becomes an attributed
transition when the commanded action is a single unambiguous direction (`_single_dir`); otherwise pose
drops to UNKNOWN ("lost") and NO wall/visited-cell/edge is written until a later step both (a) is not
itself a fresh scene-change/fade and (b) is driven by a real single-direction command whose residual
reads as settled -- at which point the perceiver re-anchors ONCE to a brand new place at (0,0) rather
than guessing an identity.

This test replays the committed frames + real recorded actions through a fresh OverworldPerceiver and
checks the four invariants from the fix spec.
"""
from __future__ import annotations

import json
import os

import numpy as np
import pytest

from core.perception import PerceptMemory
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
    """Feed the recorded (frame, action) pairs for these oracle steps through a fresh perceiver.
    Returns the list of (record, SymbolicState, places-count-after) tuples, in order."""
    recs = {r["step"]: r for r in _load_slice()}
    per, mem = OverworldPerceiver(), PerceptMemory()
    out = []
    for step in steps:
        r = recs[step]
        s = per.perceive(_frame(step), mem, {"last_action": r["perceived"]["action"], "frame_path": ""})
        out.append((r, s, len(mem.data["places"])))
    return out, mem


# -- (49, 50): post-warp fade spike must not corrupt pose ---------------------

def test_post_warp_fade_spike_pair_replays_without_crashing():
    """s49/s50: a residual spike (100.85) right after a warp. Just needs to replay cleanly (pixels-only
    smoke coverage for the pair the diagnosis flagged); the real invariants are covered by the full
    cutscene span below, which is where the corruption actually happened."""
    out, _ = _replay([49, 50])
    assert out[-1][1].context == "overworld"


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

_CUTSCENE_STEPS = [535, 536, 537, 538, 539, 540, 541, 542, 543, 544, 545, 546, 554, 555, 556]


def test_cutscene_span_mints_no_place_while_real_map_is_still_0():
    """(i) No place is minted or reused while the real (RAM-truth) map is still 0 (steps 535-539 --
    s540 is the boundary step where the perceiver's own pixels-only settle first fires, see the
    re-anchor test below). The mixed-direction auto-walk actions (s537/538, residual 47/0 -- two
    consecutive frames can be pixel-identical mid-cutscene) must never attribute a scene-change residual
    to a transition: every one of these steps must stay on the original place 0, unminted, unreused."""
    steps_on_map0 = [s for s in _CUTSCENE_STEPS if s <= 539]
    out, mem = _replay(steps_on_map0)
    assert all(r["watch"]["map"] == 0 for r, _, _ in out)
    assert all(s.pose["area"] == 0 for _, s, _ in out)     # no mint, no reuse, no phantom edge
    assert len(mem.data["places"]) == 1


def test_cutscene_recovers_by_re_anchoring_fresh_never_reusing_the_old_place():
    """(ii) Whenever the perceiver's pixels-only settle check fires after a lost pose (s540, then again
    at s555 -- the real, table-side settle), it re-anchors to a BRAND NEW place id, never back to place 0
    (the stale pre-cutscene place) and never by REUSING a place id already seen -- i.e. no stale edge or
    cell-keyed reuse can capture a later scene change into an old place, unlike the original bug (s543
    reused the s537-minted place and reset pose to (0,0))."""
    out, mem = _replay(_CUTSCENE_STEPS)
    areas = [s.pose["area"] for _, s, _ in out if s.context == "overworld"]
    seen = []
    for a in areas:
        if not seen or a != seen[-1]:
            seen.append(a)
    # every place we land on is either 0 (the starting place, before any re-anchor) or STRICTLY NEW
    # relative to everything visited so far -- once we leave a place via re-anchor we never return to it
    visited_before = {0}
    for a in seen:
        if a != 0:
            assert a not in visited_before, f"re-anchored back into a previously-visited place {a}"
        visited_before.add(a)
    assert len(mem.data["places"]) == len(set(seen))     # exactly the places actually visited -- no extras


def test_pose_at_the_starter_table_is_the_fresh_anchor_not_a_phantom():
    """(iii) Once pose settles at the starter table (s555-556, real map == 40; s554 is still the tail of
    the 'lost' streak -- see (iv), it has not settled yet), it sits on ONE consistent fresh place -- not
    split across places, and not the stale place 0 the old bug would have reset pose back to via the
    cell-keyed reverse-edge reuse."""
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
    """Unit-level pin for the root cause: `down+left+up+right` (the cutscene auto-walk probe) at a
    residual (47.28) well above the area threshold must NOT mint/reuse a place -- direction must resolve
    to None for a mixed multi-directional action, so the scene-change branch can't attribute it."""
    from games.pokemon_red.perceiver import _single_dir
    assert _single_dir("down+left+up+right") is None
    assert _single_dir("up+up+up") == "up"        # repeated SAME direction still resolves
    assert _single_dir("wait") is None
    assert _single_dir(None) is None


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
