"""eval/score_kirby_skill_precheck.py -- the SEVEN free pre-check gates pinned by
reports/2026-07-03-kirby-skill-port-entity-v3.md §6, before any paid entity-gate v3 run is scheduled.
Sibling of eval/score_skill_rung1.py (the ARC-port pre-check this file's shape mirrors) and
eval/score_a3_precheck.py (the "pure stdlib scorer, separately-run driver" split convention).

Gate summary (doc §6, numbered identically):

  1. --dry executor fixture: canned scripted-perceiver scenarios standing in for recorded frames,
     exercising the REAL World.define_skill/run_skill dispatch (world_mcp.py) -- an approach ending in
     region_changed, a retreat ending in steps_elapsed(8), a move_blocked case, and a max_iters
     cap-out. Runs headless, no ROM, no PyBoy -- CI-safe (mirrors tests/test_kirby_skill_port.py's own
     scripted-perceiver harness).
  2. Per-press executor overhead budget (mean <= 150 ms/press over >= 100 recorded frames, doc §2/§6).
     The budget applies to the RE-OBSERVATION overhead the port adds per press (plugin.observe()'s
     perceiver pass + _track_frame() + the predicate check -- doc §6 gate 2's own parenthetical), NOT
     to the emulator tick itself (press hold+settle is game time the world already paid before this
     port). Per residual #3 (PR #92 verification comment) observe-only cost is ALWAYS reported as its
     own number, separately from the full overhead the budget is judged on.
  3. entity_count_changed admission check: runs core.entities.EntityDetector.detect() against a REAL
     recorded enemy-approach frame sequence (`--frames-dir` of PNGs, chronological by filename).
     Flapping is judged ONLY across STATIONARY frame pairs (whole-frame MAD < 2.0, the same dead-zone
     as whats_changed) per the doc's own pinning ("count stable across consecutive frames of a
     stationary scene") -- so a genuine approach's real count changes (moving scene) never misfire it,
     while a period-2 sprite flicker (1,0,1,0 on a static scene) IS flagged. NOTE this gate is an
     ADMISSION DECISION, not a run blocker: a NOT_ADMITTED outcome keeps entity_count_changed demoted
     (the macro's approach half already uses region_changed -- doc §6: "FAIL costs nothing") and still
     satisfies the gate for --all's aggregate; only NEEDS_ASSETS (no decision made) fails it. RESULT
     ON THE ARCHIVED 181-FRAME CORPUS (run live 2026-07-03 during the PR #93 fix round): fired=true,
     flapping ACROSS STATIONARY PAIRS detected -> NOT_ADMITTED; entity_count_changed stays out of the
     enum, exactly the §3 demotion's prediction.
  4. tools/list seam-isolation: pure logic, no ROM -- runs unconditionally in `main()`.
  5. assert_action_tools_fresh drift check: needs a ROM for the live-plugin comparison. Standalone
     (--dry) it reports SKIPPED without one (same convention as the existing
     tests/test_world_mcp_kirby_dreamland.py freshness test); under --all a skip counts as NOT passed
     (never green with partial coverage).
  6. Seam-press physics re-validation: needs --rom AND --init-state. Verdict (`passed`) checks all of:
     (a) the walk recipe (hold_frames=30) advances exactly 46 emulator frames per press and a
     multi-press macro advances N*46; (b) the jump/mount recipe (hold_frames=20) advances exactly 36
     frames per press -- the doc §5.5/§6 pinned constants; and (c) move_blocked's wall_confirm latency
     fires on the 3rd consecutive blocked press through the seam.
  7. audit_skill_log-shape auditability check on gate 1's own skills.jsonl output -- reuses
     eval/score_skill_rung1.py::audit_skill_log verbatim (world-agnostic: reads generic jsonl rows).

ASSET AVAILABILITY (corrected after PR #93 review): the MAIN TREE HAS the gate-2/3/6 assets --
`roms/Kirby's Dream Land (USA, Europe).gb`, 181 recorded PNGs across
`runs/brain_kirby_entity/run{1_retro_taint,2_gapfalls,3_walled,4_v2_FAIL}/world/` (49+36+58+38; no
single dir reaches the >=100 minimum, so consolidate first -- see below), and candidate seed states
`runs/kirby_entity.state` / `runs/kirby_entity2.state`. These live in gitignored paths, so a fresh
worktree/CI checkout does not see them; when they are absent the gates report NEEDS_ASSETS_NOT_PRESENT
(exit nonzero, never a fabricated number).

`--all` means ALL SEVEN gates: 2/3/6 run when their asset args are supplied and report
NEEDS_ASSETS_NOT_PRESENT otherwise -- either way they are counted in the exit code, so `--all`
without assets exits NONZERO. It can never be green with partial coverage.

Usage (validated against the main tree's actual asset paths):
    uv run python -m eval.score_kirby_skill_precheck --dry           # gates 1,4,5(skip-ok),7
    uv run python -m eval.score_kirby_skill_precheck --all \\
        --rom "roms/Kirby's Dream Land (USA, Europe).gb" \\
        --init-state runs/kirby_entity.state --frames-dir <consolidated-dir>   # all seven

    # gate-2/3 frames prerequisite: consolidate the 4 run dirs into one folder first, e.g.
    #   mkdir -p /tmp/kirby_frames && i=0; for d in runs/brain_kirby_entity/run*/world; do
    #     for f in "$d"/*.png; do cp "$f" "/tmp/kirby_frames/$(printf '%05d' $i).png"; i=$((i+1)); done
    #   done
    uv run python -m eval.score_kirby_skill_precheck --measure-overhead --frames-dir /tmp/kirby_frames
    uv run python -m eval.score_kirby_skill_precheck --measure-overhead \\
        --rom "roms/Kirby's Dream Land (USA, Europe).gb" --init-state runs/kirby_entity.state
    uv run python -m eval.score_kirby_skill_precheck --check-entities --frames-dir /tmp/kirby_frames
    uv run python -m eval.score_kirby_skill_precheck --seam-physics \\
        --rom "roms/Kirby's Dream Land (USA, Europe).gb" --init-state runs/kirby_entity.state
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import sys
import time

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from eval.score_skill_rung1 import audit_skill_log, format_audit_report, load_jsonl  # noqa: E402

PER_PRESS_BUDGET_MS = 150.0     # doc §6 gate 2, pinned: mean <= 150 ms/press over the recorded-frame corpus
MIN_FRAMES_FOR_OVERHEAD = 100    # doc §6 gate 2: ">= 100 recorded Kirby frames"
STATIONARY_MAD_MAX = 2.0         # gate 3 scene-stationarity dead-zone == whats_changed's own MAD>=2.0
                                 # threshold (world_mcp.py::_whats_changed) -- a frame pair below this is
                                 # "stationary" per doc §6 gate 3's pinning
EXPECTED_WALK_FRAMES_PER_PRESS = 46   # hold_frames=30 + 16 settle (core/gb_emulator.py:114; doc §5.5/§6)
EXPECTED_JUMP_FRAMES_PER_PRESS = 36   # hold_frames=20 + 16 settle (doc §5.5/§6 corrected constants)


# ---------------------------------------------------------------------------
# Gate 1: --dry executor fixture (scripted perceiver, no ROM) -- mirrors
# tests/test_kirby_skill_port.py's own harness so a drifting executor fails BOTH the unit tests and this
# free pre-check the same way.
# ---------------------------------------------------------------------------

def _kirby_dry_scenarios():
    """Four canned scenarios (doc §6 gate 1's own list): an approach ending in region_changed, a
    retreat ending in steps_elapsed(8), a move_blocked case (pinned to fire on the THIRD blocked press,
    per §3's wall_confirm=3 note), and a max_iters cap-out (stuck loop). Each scenario pins its expected
    stop_reason substring + executed_step_count + iterations, checked mechanically below."""
    import numpy as np

    from core.perception import SymbolicState

    def moved():
        return SymbolicState(confidence=1.0, context="gameplay", pose={"value": (0, 0)},
                             spatial_memory={"visited": 1},
                             last_action={"action": "right", "outcome": "moved"})

    def blocked():
        return SymbolicState(confidence=1.0, context="gameplay", pose={"value": (0, 0)},
                             spatial_memory={"visited": 1},
                             last_action={"action": "right", "outcome": "blocked"})

    def unknown():
        return SymbolicState(confidence=1.0, context="gameplay", pose={"value": (0, 0)},
                             spatial_memory={"visited": 1},
                             last_action={"action": "right", "outcome": "unknown"})

    blank = np.zeros((144, 160, 3), dtype=np.uint8)
    changed = blank.copy()
    changed[10:20, 10:20] = 255

    return [
        {
            "name": "approach_region_changed",
            "states": [moved(), moved(), moved()],
            # screen flips to `changed` after press #2 (see the 3-calls-per-press-cycle note in
            # tests/test_kirby_skill_port.py: _sample_fade + observe + _track_frame all read
            # emu.screen_ndarray() once each per press).
            "screen_flip_after_calls": 6,
            "screen_before": blank, "screen_after": changed,
            "skill": {"name": "approach", "steps": [
                {"repeat_until": {"steps": [{"button": "right"}],
                                  "stop_when": "region_changed(10,10,20,20)", "max_iters": 8}}]},
            "expect_stop_reason_contains": "region_changed(10,10,20,20)",
            "expect_executed_steps": 3, "expect_iterations": 3,
        },
        {
            "name": "retreat_steps_elapsed",
            "states": [moved() for _ in range(10)],
            "screen_flip_after_calls": None,
            "skill": {"name": "retreat", "steps": [
                {"repeat_until": {"steps": [{"button": "left"}],
                                  "stop_when": "steps_elapsed(8)", "max_iters": 8}}]},
            "expect_stop_reason_contains": "steps_elapsed(8)",
            "expect_executed_steps": 8, "expect_iterations": 8,
        },
        {
            "name": "move_blocked",
            # HONEST SCOPING: §3's wall_confirm=3 note ("move_blocked fires on the THIRD consecutive
            # blocked press, never the first") is a property of core/grid_perceiver.py's OWN state
            # machine (WALL_CONFIRM=3), which is exercised by that module's own unit tests -- it is
            # UPSTREAM of the World-level stop_when check this scenario covers. This scripted perceiver
            # stands in for whatever outcome the real perceiver reports, so it deliberately returns
            # "blocked" starting at press 1 to isolate what THIS pre-check owns: that the EXECUTOR
            # correctly fires move_blocked on the FIRST press whose outcome IS "blocked" (it does not
            # itself impose or need to re-verify the 3-press latency -- that is doc §6 gate 6's job,
            # "on-seam" against a real ROM, since it needs the real perceiver's dead-reckoning state).
            "states": [blocked(), blocked(), blocked()],
            "screen_flip_after_calls": None,
            "skill": {"name": "bump", "steps": [
                {"repeat_until": {"steps": [{"button": "right"}],
                                  "stop_when": "move_blocked", "max_iters": 8}}]},
            "expect_stop_reason_contains": "move_blocked",
            "expect_executed_steps": 1, "expect_iterations": 1,
        },
        {
            "name": "max_iters_cap_out",
            "states": [unknown() for _ in range(10)],
            "screen_flip_after_calls": None,
            "skill": {"name": "stuck", "steps": [
                {"repeat_until": {"steps": [{"button": "right"}],
                                  "stop_when": "move_blocked", "max_iters": 4}}]},
            "expect_stop_reason_contains": "reached max_iters=4 without stop_when firing",
            "expect_executed_steps": 4, "expect_iterations": 4,
        },
    ]


def _build_dry_world(out_dir: str, scenario: dict):
    """Build a real World (kirby_dreamland's own plugin/perceiver wiring) against a FakeEmulator and a
    scripted perceiver -- exactly tests/test_kirby_skill_port.py's own harness, factored here so the
    free pre-check and the unit tests exercise the identical construction path."""
    import argparse as _argparse

    from core.brains import ExploreBrain
    from core.gateway import Gateway
    from core.perception import PerceptMemory
    from core.perception_plugin import PerceptionPlugin
    from core.permissions import Allowlist

    import world_mcp
    from world_mcp import World

    from tests.test_pokemon_red import FakeEmulator

    class _ScriptedPerceiver:
        def __init__(self, states):
            self._states = list(states)
            self._i = 0

        def perceive(self, frame, memory: PerceptMemory, context=None):
            if self._i < len(self._states):
                s = self._states[self._i]
                self._i += 1
            else:
                s = self._states[-1]
            return s

    spec = world_mcp.GAMES["kirby_dreamland"]
    emu = FakeEmulator()
    if scenario.get("screen_before") is not None:
        emu._screen = scenario["screen_before"]
    plugin = PerceptionPlugin(rom_path=None, emulator=emu, out_dir=out_dir, headless=True,
                              perceiver=_ScriptedPerceiver(scenario["states"]), watch=spec["watch"],
                              render_header="kirby precheck")
    if scenario.get("screen_flip_after_calls") is not None:
        flip_at = scenario["screen_flip_after_calls"]
        before, after = scenario["screen_before"], scenario["screen_after"]
        calls = {"n": 0}

        def _scripted_screen():
            calls["n"] += 1
            return before if calls["n"] <= flip_at else after
        plugin.emu.screen_ndarray = _scripted_screen

    w = World.__new__(World)
    w.with_screenshot = False
    w.keep_frames = False
    w.plugin = plugin
    w.gw = Gateway(plugin, Allowlist({"press_button", "press_sequence", "wait"}))
    w.explore = ExploreBrain("mcp-brain", single_step=True)
    w.lessons = []
    w.decisions = 0
    w.auto_tiles = 0
    w.visited = 0
    w.region_tools = True
    w._frame_hist = []
    w.kirby_skills_world = True
    w._kirby_skills_enabled = True
    w.skills = {}
    w._skill_log_path = os.path.join(out_dir, "skills.jsonl")
    return w


def run_dry(out_dir: str) -> dict:
    """Gate 1: drive the REAL World.define_skill/run_skill dispatch against each canned scenario,
    checking each one's pinned expectations (stop_reason substring + executed_step_count + iterations).
    Writes a combined skills.jsonl under `out_dir` for gate 7 to audit."""
    all_rows: list[dict] = []
    scenario_results: list[dict] = []
    combined_path = os.path.join(out_dir, "skills.jsonl")
    os.makedirs(out_dir, exist_ok=True)
    if os.path.exists(combined_path):
        os.remove(combined_path)

    for sc in _kirby_dry_scenarios():
        sc_out = os.path.join(out_dir, sc["name"])
        os.makedirs(sc_out, exist_ok=True)
        sc_log = os.path.join(sc_out, "skills.jsonl")
        if os.path.exists(sc_log):
            os.remove(sc_log)
        os.environ["KIRBY_SKILLS"] = "1"   # the dry driver's own purpose (doc §4.0 free-instrument
                                            # shape) is independent of the paid-run A/B gate
        w = _build_dry_world(sc_out, sc)
        w.call("define_skill", sc["skill"])
        w.call("run_skill", {"name": sc["skill"]["name"]})

        rows = load_jsonl(sc_log)
        all_rows.extend(rows)
        run_rows = [r for r in rows if r.get("event") == "run_skill"]
        rec = run_rows[0] if run_rows else {}
        reason_ok = sc["expect_stop_reason_contains"] in rec.get("stop_reason", "")
        count_ok = rec.get("executed_step_count") == sc["expect_executed_steps"]
        iters = None
        for e in rec.get("executed", []):
            if "repeat_until_summary" in e:
                iters = e.get("iterations")
        iters_ok = iters == sc["expect_iterations"]
        detail = (f"stop_reason={rec.get('stop_reason')!r}, executed={rec.get('executed_step_count')!r}, "
                 f"iterations={iters!r} (expected contains {sc['expect_stop_reason_contains']!r}, "
                 f"executed=={sc['expect_executed_steps']}, iterations=={sc['expect_iterations']})")
        scenario_results.append({"name": sc["name"], "ok": reason_ok and count_ok and iters_ok,
                                 "detail": detail})

    with open(combined_path, "w", encoding="utf-8") as f:
        for r in all_rows:
            f.write(json.dumps(r) + "\n")

    report = audit_skill_log(all_rows)
    report["scenarios"] = scenario_results
    report["all_scenarios_pass"] = all(sc["ok"] for sc in scenario_results)
    return report


# ---------------------------------------------------------------------------
# Gate 2: per-press executor overhead (mean <= 150 ms/press), observe-only cost reported SEPARATELY
# (doc's residual #3). Needs either a real PyBoy+ROM boot or a --frames-dir of >= 100 recorded PNGs;
# fails loud (does not fabricate a number) if neither is supplied.
# ---------------------------------------------------------------------------

def _overhead_report(observe_ms: list[float], overhead_ms: list[float], *, mode: str,
                     extra: dict | None = None) -> dict:
    """Pure verdict builder (unit-testable without frames or a ROM): the gate-2 budget
    (PER_PRESS_BUDGET_MS) is judged on the FULL per-press re-observation overhead (observe + track +
    predicate check -- doc §6 gate 2's parenthetical); observe-only is ALWAYS its own separate number
    (residual #3) and never carries the gate verdict, so it cannot be misread as a pass when only the
    lower bound was measured."""
    mean_observe = sum(observe_ms) / len(observe_ms)
    mean_overhead = sum(overhead_ms) / len(overhead_ms)
    rep = {"mode": mode, "n": len(overhead_ms),
           "observe_only_mean_ms": mean_observe,
           "full_overhead_mean_ms": mean_overhead,
           "budget_ms": PER_PRESS_BUDGET_MS,
           "observe_only_under_budget": mean_observe <= PER_PRESS_BUDGET_MS,
           "passed": mean_overhead <= PER_PRESS_BUDGET_MS,
           "note": "observe_only is the perceiver pass alone; full_overhead adds _track_frame's "
                   "frame-pair bookkeeping + a region_changed MAD predicate check -- the per-press "
                   "re-observation overhead doc §2/§6 budget at 150 ms/press. Reported separately "
                   "per residual #3 (PR #92 verification comment)."}
    if extra:
        rep.update(extra)
    return rep


def measure_overhead(*, rom: str | None, init_state: str | None, frames_dir: str | None,
                     n_presses: int = 100) -> dict:
    """Gate 2. The doc's own measurement (§6: 'measure the wall-clock cost of one per-press
    re-observation (plugin.observe() + _track_frame() + predicate check) over >= 100 recorded Kirby
    frames') runs from `--frames-dir` -- the MAIN TREE has the corpus (181 PNGs across
    runs/brain_kirby_entity/run*/world/, 49+36+58+38; consolidate into one dir first since no single
    run dir reaches the >=100 minimum -- see the module docstring's exact commands). `--rom`
    [+ --init-state] additionally measures the same overhead against a live PyBoy boot (real emulator
    frames instead of recorded ones), plus the end-to-end press cost for context. When neither is
    available (e.g. a fresh worktree/CI checkout, where runs/ and roms/ are gitignored) this reports
    NEEDS_ASSETS_NOT_PRESENT -- never a fabricated number."""
    if frames_dir:
        pngs = sorted(glob.glob(os.path.join(frames_dir, "*.png")))
        if len(pngs) < MIN_FRAMES_FOR_OVERHEAD:
            return {"error": f"--frames-dir {frames_dir!r} has {len(pngs)} PNG(s); need >= "
                             f"{MIN_FRAMES_FOR_OVERHEAD} (doc §6 gate 2). NEEDS_ASSETS_NOT_PRESENT. "
                             "The main tree's corpus is split across 4 run dirs under "
                             "runs/brain_kirby_entity/ (49+36+58+38 = 181 PNGs) -- consolidate them "
                             "into one --frames-dir first (see the module docstring)."}
        return _measure_overhead_from_frames(pngs)
    if not rom:
        return {"error": "gate 2 needs --frames-dir (the doc's own recorded-frame measurement; the "
                         "main tree HAS the corpus -- 181 PNGs under runs/brain_kirby_entity/run*/world/, "
                         "consolidated per the module docstring) or --rom [--init-state] (same "
                         "measurement against a live PyBoy boot). Neither was supplied. "
                         "NEEDS_ASSETS_NOT_PRESENT in THIS invocation -- these paths are gitignored, "
                         "so fresh worktree/CI checkouts do not see them."}
    return _measure_full_from_rom(rom, init_state, n_presses)


def _time_track_and_predicate(frame_hist: list, step: int, frame) -> float:
    """One press's post-observe bookkeeping, timed: the _track_frame-shaped frame-pair update plus one
    region_changed MAD predicate check (the most expensive pinned predicate -- move_blocked/
    move_succeeded/steps_elapsed are field reads/counter compares, effectively free)."""
    import numpy as np

    t0 = time.perf_counter()
    frame_hist.append((step, frame))
    del frame_hist[:-2]
    if len(frame_hist) == 2:
        (_, prev), (_, curr) = frame_hist[-2], frame_hist[-1]
        h, w = curr.shape[0], curr.shape[1]
        x0, y0 = 0, 0
        x1, y1 = min(96, w), min(96, h)   # a max-size (_REGION_MAX_SIDE) box: worst-case predicate cost
        a = prev[y0:y1, x0:x1].astype(np.float32)
        b = curr[y0:y1, x0:x1].astype(np.float32)
        float(np.mean(np.abs(a - b)))
    return (time.perf_counter() - t0) * 1000.0


def _measure_overhead_from_frames(pngs: list[str]) -> dict:
    import numpy as np
    from PIL import Image

    from core.grid_perceiver import FollowCameraPerceiver
    from core.perception import PerceptMemory

    perceiver = FollowCameraPerceiver()
    memory = PerceptMemory()
    frames = [np.array(Image.open(p).convert("RGB")) for p in pngs]
    observe_ms: list[float] = []
    overhead_ms: list[float] = []
    frame_hist: list = []
    for i, frame in enumerate(frames):
        ctx = {"frame_path": pngs[i], "last_action": "right", "transition": False, "frames_advanced": 1}
        t0 = time.perf_counter()
        perceiver.perceive(frame, memory, ctx)
        obs_cost = (time.perf_counter() - t0) * 1000.0
        track_cost = _time_track_and_predicate(frame_hist, i, frame)
        observe_ms.append(obs_cost)
        overhead_ms.append(obs_cost + track_cost)
    return _overhead_report(observe_ms, overhead_ms, mode="overhead_from_frames")


def _measure_full_from_rom(rom: str, init_state: str | None, n_presses: int) -> dict:
    import argparse as _argparse

    from world_mcp import World

    args = _argparse.Namespace(game="kirby_dreamland", rom=rom, init_state=init_state,
                               out="runs/kirby_precheck_overhead", record=False,
                               with_screenshot=False, keep_frames=False)
    os.environ["KIRBY_SKILLS"] = "1"
    w = World(args)
    try:
        w.call("observe", {})   # prime _frame_hist / patience state before timing
        observe_ms: list[float] = []
        overhead_ms: list[float] = []
        end_to_end_ms: list[float] = []
        for i in range(n_presses):
            # Press first (UNtimed for the budget -- the emulator tick is game time the world already
            # paid before this port), then time exactly the per-press RE-OBSERVATION overhead the port
            # adds: observe + track + predicate (doc §6 gate 2's parenthetical).
            t_press0 = time.perf_counter()
            from core.contracts import ToolCall
            import uuid as _uuid
            w.gw.execute(ToolCall(tool="press_button", args={"button": "right", "hold_frames": 30},
                                  agent_id="mcp-brain", call_id=str(_uuid.uuid4())))
            t0 = time.perf_counter()
            obs = w.plugin.observe("mcp-brain")
            obs_cost = (time.perf_counter() - t0) * 1000.0
            w._drop_frame(obs)
            t1 = time.perf_counter()
            w._track_frame()
            if len(w._frame_hist) == 2:
                (_, prev), (_, curr) = w._frame_hist[-2], w._frame_hist[-1]
                import numpy as np
                a = prev[0:96, 0:96].astype(np.float32)
                b = curr[0:96, 0:96].astype(np.float32)
                float(np.mean(np.abs(a - b)))
            track_cost = (time.perf_counter() - t1) * 1000.0
            observe_ms.append(obs_cost)
            overhead_ms.append(obs_cost + track_cost)
            end_to_end_ms.append((time.perf_counter() - t_press0) * 1000.0)
        return _overhead_report(observe_ms, overhead_ms, mode="full_from_rom",
                                extra={"end_to_end_press_mean_ms":
                                       sum(end_to_end_ms) / len(end_to_end_ms)})
    finally:
        w.plugin.close()


# ---------------------------------------------------------------------------
# Gate 3: entity_count_changed admission check -- runs the REAL EntityDetector against a recorded
# enemy-approach frame sequence. NEEDS_ASSETS_NOT_PRESENT if no --frames-dir is supplied (this checkout
# has none committed).
# ---------------------------------------------------------------------------

def _admission_verdict(counts: list[int], stationary: list[bool]) -> dict:
    """Pure gate-3 verdict (unit-testable without frames): `counts[i]` is the detector count on frame
    i; `stationary[i]` is True iff the (i-1, i) frame pair is stationary (whole-frame MAD <
    STATIONARY_MAD_MAX -- the same dead-zone whats_changed uses); stationary[0] is ignored (no prior
    frame to pair with).

    Doc §6 gate 3's pinning, exactly: PASS = the detector (a) fires at all, and (b) shows no
    frame-to-frame count flapping "across consecutive frames of a STATIONARY scene". Flapping is
    therefore ANY count change across a stationary pair -- including 0<->N alternation, which catches
    the period-2 fully-on/fully-off sprite flicker (1,0,1,0,...) that is the most common real GB
    flicker signature (PR #93 review finding: the previous adjacent-nonzero check could never see it,
    since a 1,0,1,0 run has no two adjacent nonzero counts). The stationarity scoping is what keeps a
    GENUINE approach's count changes from misfiring: an enemy entering/leaving frame comes with scene
    motion (MAD >= 2.0 over the whole frame), so those pairs are non-stationary and never counted as
    flapping -- while a small sprite's on/off flip moves far too few pixels to lift whole-frame MAD
    over the dead-zone, so its pair stays stationary and the flap IS flagged."""
    fired = any(c > 0 for c in counts)
    flapping_pairs = [i for i in range(1, len(counts))
                      if counts[i] != counts[i - 1] and stationary[i]]
    flapping = bool(flapping_pairs)
    return {"fired": fired, "flapping_detected": flapping, "flapping_pair_indices": flapping_pairs,
            "passed": fired and not flapping, "admitted": fired and not flapping}


def check_entities_admission(frames_dir: str | None) -> dict:
    if not frames_dir:
        return {"error": "gate 3 needs --frames-dir (a REAL recorded enemy-approach PNG sequence). "
                         "NEEDS_ASSETS_NOT_PRESENT in THIS invocation. NOTE: the main tree's archived "
                         "corpus (runs/brain_kirby_entity/run*/world/, 181 PNGs) contains ZERO "
                         "verified approach segments (0 'Entities on screen' lines across all four "
                         "transcripts -- the very finding that demoted entity_count_changed, doc §3), "
                         "so a meaningful admission check needs a FRESH approach-segment recording "
                         "through the seam, per the doc's own gate-3 note."}
    import numpy as np
    from PIL import Image

    from core.entities import EntityDetector

    pngs = sorted(glob.glob(os.path.join(frames_dir, "*.png")))
    if not pngs:
        return {"error": f"--frames-dir {frames_dir!r} has no PNGs."}
    detector = EntityDetector()
    counts: list[int] = []
    stationary: list[bool] = [False]   # index 0 has no prior pair; padded so indices align with counts
    prev = None
    for p in pngs:
        frame = np.array(Image.open(p).convert("RGB"))
        counts.append(len(detector.detect(frame)))
        if prev is not None:
            mad = float(np.mean(np.abs(frame.astype(np.float32) - prev.astype(np.float32))))
            stationary.append(mad < STATIONARY_MAD_MAX)
        prev = frame
    verdict = _admission_verdict(counts, stationary)
    verdict.update({"n_frames": len(pngs), "counts": counts,
                    "n_stationary_pairs": sum(1 for s in stationary[1:] if s)})
    return verdict


# ---------------------------------------------------------------------------
# Gate 4: tools/list seam-isolation (pure logic, no ROM).
# ---------------------------------------------------------------------------

def check_seam_isolation() -> dict:
    import world_mcp

    old = os.environ.pop("KIRBY_SKILLS", None)
    try:
        os.environ.pop("KIRBY_SKILLS", None)
        off_names = {t["name"] for t in world_mcp._static_tools("kirby_dreamland")}
        os.environ["KIRBY_SKILLS"] = "1"
        on_names = {t["name"] for t in world_mcp._static_tools("kirby_dreamland")}
    finally:
        if old is not None:
            os.environ["KIRBY_SKILLS"] = old
        else:
            os.environ.pop("KIRBY_SKILLS", None)
    off_ok = "define_skill" not in off_names and "run_skill" not in off_names
    on_ok = "define_skill" in on_names and "run_skill" in on_names
    other_worlds_clean = True
    other_leaks = []
    os.environ["KIRBY_SKILLS"] = "1"
    try:
        for game in ("cave_noire", "cave_noire_baseline", "gauntlet", "gb_generic", "pokemon_red",
                    "kirby_gba", "arcagi3"):
            names = {t["name"] for t in world_mcp._static_tools(game)}
            if "define_skill" in names or "run_skill" in names:
                other_worlds_clean = False
                other_leaks.append(game)
    finally:
        if old is not None:
            os.environ["KIRBY_SKILLS"] = old
        else:
            os.environ.pop("KIRBY_SKILLS", None)
    return {"off_hides_tools": off_ok, "on_shows_tools": on_ok,
           "other_worlds_clean": other_worlds_clean, "leaked_to": other_leaks,
           "passed": off_ok and on_ok and other_worlds_clean}


# ---------------------------------------------------------------------------
# Gate 5: assert_action_tools_fresh drift check. Needs a ROM for the live-plugin comparison; reports
# SKIPPED (not FAIL) without one, matching tests/test_world_mcp_kirby_dreamland.py's own convention.
# ---------------------------------------------------------------------------

def check_tools_fresh(rom: str | None) -> dict:
    import argparse as _argparse

    import world_mcp
    from world_mcp import World, assert_action_tools_fresh

    if not rom:
        for candidate in ("roms/Kirby's Dream Land (USA, Europe).gb",
                         "roms/Cave Noire (Japan) [T-En by Aeon Genesis v1.00].gb",
                         "roms/Gauntlet II (USA, Europe).gb"):
            if os.path.exists(candidate):
                rom = candidate
                break
    if not rom or not os.path.exists(rom):
        return {"skipped": True, "reason": "no GB ROM available in this environment"}
    args = _argparse.Namespace(game="kirby_dreamland", rom=rom, init_state=None,
                               out="runs/kirby_precheck_fresh", record=False,
                               with_screenshot=False, keep_frames=False)
    w = World(args)
    try:
        assert_action_tools_fresh(w.plugin, "kirby_dreamland")
        return {"skipped": False, "passed": True}
    except SystemExit as e:
        return {"skipped": False, "passed": False, "error": str(e)}
    finally:
        w.plugin.close()


# ---------------------------------------------------------------------------
# Gate 6: seam-press physics re-validation. Needs a real ROM + a seed state for the v2 start position,
# which the doc's own §6 gate 6 prep note flags as NOT EXISTING in runs/brain_kirby_entity/ -- this
# checkout has neither, so this reports NEEDS_ASSETS_NOT_PRESENT unless both are supplied.
# ---------------------------------------------------------------------------

def check_seam_physics(rom: str | None, init_state: str | None) -> dict:
    """Gate 6, with an explicit machine-checkable verdict (PR #93 review finding: a report the
    operator must eyeball is not a gate). `passed` requires ALL of:
      - cadence_46_ok: one walk press (hold_frames=30) advances EXACTLY 46 emulator frames, and
        macro_cadence_ok: a 4-press run_skill macro advances exactly 4*46 (per-press observes add no
        emulator ticks, so any drift here means the press physics changed under the executor);
      - cadence_36_ok: one jump/mount press (hold_frames=20) advances EXACTLY 36 frames -- the doc's
        §5.5/§6 corrected 46/36 constants, BOTH recipes exercised;
      - fires_on_third_blocked_press: a walk-into-wall run_skill's move_blocked stop_reason reports
        firing on the 3rd press (wall_confirm=3 through the real perceiver, on-seam). This last check
        assumes the seed state faces a wall within the loop's reach (the doc's gate-6 setup); if the
        macro caps out on max_iters instead, this is False and the gate fails -- rerun from a seed
        state actually adjacent to a wall."""
    if not rom or not init_state:
        return {"error": "gate 6 needs --rom AND --init-state. NEEDS_ASSETS_NOT_PRESENT in THIS "
                         "invocation. The main tree has candidate assets: roms/Kirby's Dream Land "
                         "(USA, Europe).gb and runs/kirby_entity.state / runs/kirby_entity2.state "
                         "(plausible PyBoy save states; whether either IS the v2 start position is "
                         "unconfirmed -- verify before trusting the wall_confirm half's result)."}
    import argparse as _argparse

    from world_mcp import World

    os.environ["KIRBY_SKILLS"] = "1"
    args = _argparse.Namespace(game="kirby_dreamland", rom=rom, init_state=init_state,
                               out="runs/kirby_precheck_seam", record=False,
                               with_screenshot=False, keep_frames=False)
    w = World(args)
    try:
        w.call("observe", {})
        # (c-FIRST) wall_confirm latency on-seam. This probe MUST run before any other same-direction
        # press: the wall_confirm counter is per (cell, direction) and cumulative across the session
        # (core/grid_perceiver.py blocked_attempts), so cadence presses in the same direction would
        # pre-consume the 3-press latency and make move_blocked fire on the probe's 1st press (observed
        # live against runs/kirby_entity.state when this gate originally ran the cadence probes first).
        # The seed state must face a wall in the probe direction; a fire at exactly press 3 is the
        # doc's pinned latency.
        w.call("define_skill", {"name": "wall_probe", "steps": [
            {"repeat_until": {"steps": [{"button": "right", "hold_frames": 30}],
                              "stop_when": "move_blocked", "max_iters": 8}}]})
        t0 = time.perf_counter()
        result = w.call("run_skill", {"name": "wall_probe"})
        elapsed_s = time.perf_counter() - t0
        text = " ".join(c["text"] for c in result if c.get("type") == "text")
        # (a) single-press cadence, BOTH pinned recipes (walk hold=30 -> 46; jump/mount hold=20 -> 36).
        # Direction deliberately differs from the wall probe's so these presses can never contaminate
        # a re-run of it; frame cadence is fixed per press regardless of whether the move lands.
        f0 = w.plugin.emu.frame
        w.call("press_button", {"button": "left", "hold_frames": 30})
        walk_frames = w.plugin.emu.frame - f0
        f0 = w.plugin.emu.frame
        w.call("press_button", {"button": "a", "hold_frames": 20})
        jump_frames = w.plugin.emu.frame - f0
        cadence_46_ok = walk_frames == EXPECTED_WALK_FRAMES_PER_PRESS
        cadence_36_ok = jump_frames == EXPECTED_JUMP_FRAMES_PER_PRESS
        # (b) macro cadence: 4 walking presses inside run_skill must advance exactly 4*46 frames
        # (the per-press re-observations are read-only -- no emulator ticks).
        w.call("define_skill", {"name": "cadence_probe", "steps": [
            {"repeat_until": {"steps": [{"button": "left", "hold_frames": 30}],
                              "stop_when": "steps_elapsed(4)", "max_iters": 4}}]})
        f0 = w.plugin.emu.frame
        w.call("run_skill", {"name": "cadence_probe"})
        macro_frames = w.plugin.emu.frame - f0
        macro_cadence_ok = macro_frames == 4 * EXPECTED_WALK_FRAMES_PER_PRESS
        rows = load_jsonl(os.path.join(args.out, "skills.jsonl"))
        run_rec = [r for r in rows
                   if r.get("event") == "run_skill" and r.get("name") == "wall_probe"][-1]
        fires_on_third = "3 press(es)" in run_rec.get("stop_reason", "")
        return {"walk_frames_per_press": walk_frames,
                "expected_walk_frames_per_press": EXPECTED_WALK_FRAMES_PER_PRESS,
                "cadence_46_ok": cadence_46_ok,
                "jump_frames_per_press": jump_frames,
                "expected_jump_frames_per_press": EXPECTED_JUMP_FRAMES_PER_PRESS,
                "cadence_36_ok": cadence_36_ok,
                "macro_frames": macro_frames, "macro_cadence_ok": macro_cadence_ok,
                "wall_probe_elapsed_s": elapsed_s,
                "wall_probe_stop_reason": run_rec.get("stop_reason"),
                "wall_probe_executed_step_count": run_rec.get("executed_step_count"),
                "fires_on_third_blocked_press": fires_on_third,
                "passed": cadence_46_ok and cadence_36_ok and macro_cadence_ok and fires_on_third,
                "text": text}
    finally:
        w.plugin.close()


# ---------------------------------------------------------------------------
# Gate 7: audit_skill_log-shape check on gate 1's own skills.jsonl (reused verbatim from the ARC port's
# scorer -- world-agnostic, reads generic jsonl rows).
# ---------------------------------------------------------------------------

def check_auditability(out_dir: str) -> dict:
    path = os.path.join(out_dir, "skills.jsonl")
    if not os.path.exists(path):
        return {"error": f"{path} does not exist -- run gate 1 (--dry) first."}
    rows = load_jsonl(path)
    return audit_skill_log(rows)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def format_report(dry_report, seam_report, fresh_report, audit_report) -> str:
    lines = ["=== Kirby skill port free pre-check gates (reports/2026-07-03-kirby-skill-port-entity-v3.md §6) ===", ""]
    lines.append("-- Gate 1 (--dry executor fixture) --")
    if dry_report is not None:
        lines.append(format_audit_report(dry_report, source="--dry"))
    lines.append("")
    lines.append("-- Gate 4 (tools/list seam-isolation) --")
    lines.append(json.dumps(seam_report, indent=2))
    lines.append("")
    lines.append("-- Gate 5 (assert_action_tools_fresh drift check) --")
    lines.append(json.dumps(fresh_report, indent=2))
    lines.append("")
    lines.append("-- Gate 7 (auditability check on gate 1's own log) --")
    if audit_report is not None:
        lines.append(json.dumps({k: v for k, v in audit_report.items() if k != "scenarios"}, indent=2))
    return "\n".join(lines)


def _gate_status(report: dict | None, *, skipped_ok: bool = False) -> tuple[str, bool]:
    """(human-readable status line, counts-as-passed). NEEDS_ASSETS and errors are never passed;
    a SKIPPED gate 5 counts as passed only where the caller says so (standalone --dry convention —
    NEVER under --all, per the PR #93 SEV-1 finding: --all can't be green with partial coverage)."""
    if report is None:
        return "NOT RUN", False
    if "error" in report:
        return ("NEEDS_ASSETS" if "NEEDS_ASSETS_NOT_PRESENT" in report["error"] else "ERROR"), False
    if report.get("skipped"):
        return "SKIPPED (no ROM)", skipped_ok
    return ("PASS" if report.get("passed") else "FAIL"), bool(report.get("passed"))


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry", action="store_true", help="run gate 1 (scripted-perceiver executor fixture)")
    ap.add_argument("--all", action="store_true",
                    help="run ALL SEVEN gates. Gates 2/3/6 run for real when --rom/--init-state/"
                         "--frames-dir are supplied and report NEEDS_ASSETS otherwise -- either way "
                         "they count toward the exit code, so --all without assets exits NONZERO "
                         "(never green with partial coverage).")
    ap.add_argument("--measure-overhead", action="store_true", help="run gate 2")
    ap.add_argument("--check-entities", action="store_true", help="run gate 3")
    ap.add_argument("--seam-physics", action="store_true", help="run gate 6")
    ap.add_argument("--rom", default=None)
    ap.add_argument("--init-state", default=None)
    ap.add_argument("--frames-dir", default=None)
    ap.add_argument("--out", default="runs/kirby_skill_precheck")
    args = ap.parse_args(argv)

    if not any([args.dry, args.all, args.measure_overhead, args.check_entities, args.seam_physics]):
        args.dry = True   # default action, mirrors score_skill_rung1.py's --dry default

    # Which gates run: --all means ALL SEVEN (PR #93 SEV-1 fix); dedicated flags select individually.
    want_g1 = args.dry or args.all
    want_g2 = args.measure_overhead or args.all
    want_g3 = args.check_entities or args.all
    want_g6 = args.seam_physics or args.all

    g2_report = g3_report = g6_report = None
    if want_g2:
        g2_report = measure_overhead(rom=args.rom, init_state=args.init_state,
                                     frames_dir=args.frames_dir)
        print("=== Gate 2: per-press executor overhead ===")
        print(json.dumps(g2_report, indent=2))
        if "error" in g2_report:
            print(g2_report["error"], file=sys.stderr)
    if want_g3:
        g3_report = check_entities_admission(args.frames_dir)
        print("=== Gate 3: entity_count_changed admission check ===")
        print(json.dumps({k: v for k, v in g3_report.items() if k != "counts"}, indent=2))
        if "error" in g3_report:
            print(g3_report["error"], file=sys.stderr)
    if want_g6:
        g6_report = check_seam_physics(args.rom, args.init_state)
        print("=== Gate 6: seam-press physics re-validation ===")
        print(json.dumps(g6_report, indent=2))
        if "error" in g6_report:
            print(g6_report["error"], file=sys.stderr)

    dry_report = None
    audit_report = None
    if want_g1:
        dry_report = run_dry(args.out)
        audit_report = check_auditability(args.out)

    seam_report = fresh_report = None
    if want_g1 or args.all:
        seam_report = check_seam_isolation()
        fresh_report = check_tools_fresh(args.rom)
        print(format_report(dry_report, seam_report, fresh_report, audit_report))

    # Per-gate summary + aggregate. A gate that was REQUESTED counts toward the exit code:
    # standalone --dry tolerates gate 5 skipping (no ROM, the unit-test convention); --all does NOT.
    checks: list[tuple[str, str, bool]] = []
    if want_g1:
        g1_ok = bool(dry_report and dry_report["auditable"] and dry_report["all_scenarios_pass"])
        checks.append(("gate 1 (dry executor fixture)", "PASS" if g1_ok else "FAIL", g1_ok))
    if want_g2:
        status, ok = _gate_status(g2_report)
        checks.append(("gate 2 (per-press overhead)", status, ok))
    if want_g3:
        # Gate 3 is an ADMISSION DECISION, not a run blocker (doc §6 gate 3: "FAIL costs nothing:
        # the macro's approach half already uses region_changed" -- only a PASS promotes
        # entity_count_changed into the enum, and the decision must be made BEFORE the paid run,
        # never mid-run). The gate therefore counts as satisfied when the check RAN and produced a
        # decision either way; only NEEDS_ASSETS/error (no decision made) fails it.
        if g3_report is not None and "error" not in g3_report:
            status = ("DECIDED: ADMITTED" if g3_report.get("admitted")
                      else "DECIDED: NOT_ADMITTED (entity_count_changed stays demoted; "
                           "macro uses region_changed)")
            checks.append(("gate 3 (entity admission)", status, True))
        else:
            status, ok = _gate_status(g3_report)
            checks.append(("gate 3 (entity admission)", status, ok))
    if seam_report is not None:
        checks.append(("gate 4 (seam isolation)", "PASS" if seam_report["passed"] else "FAIL",
                       seam_report["passed"]))
    if fresh_report is not None:
        status, ok = _gate_status(fresh_report, skipped_ok=not args.all)
        checks.append(("gate 5 (tools freshness)", status, ok))
    if want_g6:
        status, ok = _gate_status(g6_report)
        checks.append(("gate 6 (seam physics)", status, ok))
    if want_g1:
        g7_ok = bool(audit_report and audit_report.get("auditable"))
        checks.append(("gate 7 (auditability)", "PASS" if g7_ok else "FAIL", g7_ok))

    print("\n=== Gate summary ===")
    for name, status, _ in checks:
        print(f"  {name}: {status}")
    gates_pass = all(ok for _, _, ok in checks)
    print(f"ALL REQUESTED GATES PASS: {'YES' if gates_pass else 'NO'}")
    return 0 if gates_pass else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
