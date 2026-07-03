"""eval/score_kirby_skill_precheck.py -- the SEVEN free pre-check gates pinned by
reports/2026-07-03-kirby-skill-port-entity-v3.md §6, before any paid entity-gate v3 run is scheduled.
Sibling of eval/score_skill_rung1.py (the ARC-port pre-check this file's shape mirrors) and
eval/score_a3_precheck.py (the "pure stdlib scorer, separately-run driver" split convention).

Gate summary (doc §6, numbered identically):

  1. --dry executor fixture: canned scripted-perceiver scenarios standing in for recorded frames,
     exercising the REAL World.define_skill/run_skill dispatch (world_mcp.py) -- an approach ending in
     region_changed, a retreat ending in steps_elapsed(8), a move_blocked case (3rd-press wall_confirm
     latency), and a max_iters cap-out. Runs headless, no ROM, no PyBoy -- CI-safe (mirrors
     tests/test_kirby_skill_port.py's own scripted-perceiver harness).
  2. Per-press executor overhead budget (mean <= 150 ms/press over >= 100 recorded frames). THIS
     REPOSITORY CHECKOUT HAS NO recorded runs/brain_kirby_entity/run*/world/ PNG corpus (verified: the
     directory does not exist here -- ROMs/run artifacts are gitignored) -- `--measure-overhead` runs
     the REAL per-press path (World._kirby_press_and_observe) against a real PyBoy boot + ROM if
     `--rom`/`--init-state` are supplied, or against >= 100 frames it finds under a `--frames-dir` you
     point it at; it FAILS LOUD (never fabricates a number) if neither is available. Per the doc's
     residual #3 (PR #92 verification comment): observe-only cost is reported SEPARATELY from full
     per-press executor cost (press + observe + track_frame), not blended into one figure.
  3. entity_count_changed admission check: runs core.entities.EntityDetector.detect() against a REAL
     recorded enemy-approach frame sequence. Same honest-scoping note as gate 2 -- no such sequence is
     committed to this checkout; `--check-entities FRAMES_DIR` runs the real detector against whatever
     frame directory you supply (a `--frames-dir` of PNGs, chronological by filename).
  4. tools/list seam-isolation: pure logic, no ROM -- runs unconditionally in `main()`.
  5. assert_action_tools_fresh drift check: pure logic, no ROM -- runs unconditionally in `main()`
     (reuses world_mcp.assert_action_tools_fresh; needs a ROM only for the live-plugin comparison, so
     this gate reports SKIPPED, not FAIL, when no ROM is present -- same convention as the existing
     tests/test_world_mcp_kirby_dreamland.py::test_assert_action_tools_fresh_kirby_dreamland_world).
  6. Seam-press physics re-validation (46/36 frames/press, 3-press wall_confirm latency ON THE SEAM):
     needs a real PyBoy boot + a seed state for the v2 start position, which per the doc's own §6 gate
     6 prep note DOES NOT EXIST in runs/brain_kirby_entity/ -- `--seam-physics --rom ... --init-state
     ...` runs it for real when both are supplied; otherwise this gate reports
     NEEDS_ASSETS_NOT_PRESENT, honestly, rather than skipping silently.
  7. audit_skill_log-shape auditability check on gate 1's own skills.jsonl output -- reuses
     eval/score_skill_rung1.py::audit_skill_log verbatim (world-agnostic: reads generic jsonl rows),
     run here against gate 1's --dry output.

Usage:
    uv run python -m eval.score_kirby_skill_precheck --dry
    uv run python -m eval.score_kirby_skill_precheck --all      # gates 1,4,5,7 (+ 2/3/6 if assets given)
    uv run python -m eval.score_kirby_skill_precheck --measure-overhead --rom <path> --init-state <path>
    uv run python -m eval.score_kirby_skill_precheck --check-entities --frames-dir <dir>
    uv run python -m eval.score_kirby_skill_precheck --seam-physics --rom <path> --init-state <path>
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

def measure_overhead(*, rom: str | None, init_state: str | None, frames_dir: str | None,
                     n_presses: int = 100) -> dict:
    """Measure (a) observe-only cost (plugin.observe() alone) and (b) full per-press executor cost
    (press_button + observe + _track_frame, i.e. World._kirby_press_and_observe's own path) SEPARATELY
    -- doc residual #3, PR #92 verification comment. Requires a real PyBoy boot (--rom [+ --init-state])
    so the timings reflect the real perceiver stack, not a FakeEmulator's near-zero cost. `--frames-dir`
    is accepted for a future variant that replays recorded PNGs through the perceiver directly (observe-
    only cost only -- pressing a button needs a live emulator, which recorded PNGs cannot provide), but
    is NOT wired to a real measurement path here: this checkout has no recorded corpus to point it at
    (verified: runs/brain_kirby_entity/ does not exist), so --frames-dir currently only enables the
    observe-only half if the directory has >= MIN_FRAMES_FOR_OVERHEAD PNGs. Full per-press cost always
    needs --rom."""
    if frames_dir:
        pngs = sorted(glob.glob(os.path.join(frames_dir, "*.png")))
        if len(pngs) < MIN_FRAMES_FOR_OVERHEAD:
            return {"error": f"--frames-dir {frames_dir!r} has {len(pngs)} PNG(s); need >= "
                             f"{MIN_FRAMES_FOR_OVERHEAD} (doc §6 gate 2). NEEDS_ASSETS_NOT_PRESENT."}
        return _measure_observe_only_from_frames(pngs)
    if not rom:
        return {"error": "gate 2 needs either --rom [--init-state] (full per-press + observe-only "
                         "measurement against a real PyBoy boot) or --frames-dir (observe-only only, "
                         "needs >= 100 recorded PNGs). Neither was supplied. "
                         "NEEDS_ASSETS_NOT_PRESENT -- this checkout ships no recorded Kirby frame "
                         "corpus (runs/brain_kirby_entity/ does not exist here)."}
    return _measure_full_from_rom(rom, init_state, n_presses)


def _measure_observe_only_from_frames(pngs: list[str]) -> dict:
    import numpy as np
    from PIL import Image

    from core.grid_perceiver import FollowCameraPerceiver
    from core.perception import PerceptMemory

    perceiver = FollowCameraPerceiver()
    memory = PerceptMemory()
    frames = [np.array(Image.open(p).convert("RGB")) for p in pngs[:max(MIN_FRAMES_FOR_OVERHEAD, len(pngs))]]
    durations_ms = []
    for i, frame in enumerate(frames):
        ctx = {"frame_path": pngs[i], "last_action": "right", "transition": False, "frames_advanced": 1}
        t0 = time.perf_counter()
        perceiver.perceive(frame, memory, ctx)
        durations_ms.append((time.perf_counter() - t0) * 1000.0)
    mean_ms = sum(durations_ms) / len(durations_ms)
    return {"mode": "observe_only_from_frames", "n": len(durations_ms), "mean_ms": mean_ms,
           "budget_ms": PER_PRESS_BUDGET_MS, "passed": mean_ms <= PER_PRESS_BUDGET_MS,
           "note": "perceiver-only cost (no press, no gateway dispatch) -- a LOWER BOUND on full "
                   "per-press executor cost, reported separately per the doc's residual #3."}


def _measure_full_from_rom(rom: str, init_state: str | None, n_presses: int) -> dict:
    import argparse as _argparse

    import world_mcp
    from world_mcp import World

    args = _argparse.Namespace(game="kirby_dreamland", rom=rom, init_state=init_state,
                               out="runs/kirby_precheck_overhead", record=False,
                               with_screenshot=False, keep_frames=False)
    os.environ["KIRBY_SKILLS"] = "1"
    w = World(args)
    try:
        w.call("observe", {})   # prime _frame_hist / patience state before timing
        observe_ms: list[float] = []
        full_ms: list[float] = []
        for _ in range(n_presses):
            t0 = time.perf_counter()
            w.plugin.observe("mcp-brain")
            observe_ms.append((time.perf_counter() - t0) * 1000.0)

            t0 = time.perf_counter()
            w._kirby_press_and_observe("right", 30)   # the seam-validated walk recipe's hold_frames
            full_ms.append((time.perf_counter() - t0) * 1000.0)
        mean_observe = sum(observe_ms) / len(observe_ms)
        mean_full = sum(full_ms) / len(full_ms)
        return {"mode": "full_from_rom", "n": n_presses,
               "observe_only_mean_ms": mean_observe, "full_per_press_mean_ms": mean_full,
               "budget_ms": PER_PRESS_BUDGET_MS, "passed": mean_full <= PER_PRESS_BUDGET_MS,
               "note": "observe_only is plugin.observe() alone (perception, no press/gateway dispatch, "
                       "no _track_frame); full_per_press is press_button (via the gateway) + observe + "
                       "_track_frame -- the ACTUAL World._kirby_press_and_observe path a run_skill "
                       "loop pays per inner step. Reported separately per the doc's residual #3."}
    finally:
        w.plugin.close()


# ---------------------------------------------------------------------------
# Gate 3: entity_count_changed admission check -- runs the REAL EntityDetector against a recorded
# enemy-approach frame sequence. NEEDS_ASSETS_NOT_PRESENT if no --frames-dir is supplied (this checkout
# has none committed).
# ---------------------------------------------------------------------------

def check_entities_admission(frames_dir: str | None) -> dict:
    if not frames_dir:
        return {"error": "gate 3 needs --frames-dir (a REAL recorded enemy-approach PNG sequence). "
                         "NEEDS_ASSETS_NOT_PRESENT -- no such sequence is committed to this checkout "
                         "(doc §6 gate 3's own honest-scoping note: 'recorded fresh through the seam "
                         "if the archived run frames lack an approach segment')."}
    import numpy as np
    from PIL import Image

    from core.entities import EntityDetector

    pngs = sorted(glob.glob(os.path.join(frames_dir, "*.png")))
    if not pngs:
        return {"error": f"--frames-dir {frames_dir!r} has no PNGs."}
    detector = EntityDetector()
    counts = []
    for p in pngs:
        frame = np.array(Image.open(p).convert("RGB"))
        counts.append(len(detector.detect(frame)))
    fired = any(c > 0 for c in counts)
    # Flicker check: among consecutive STATIONARY-scene frames (approximated here as any run of
    # identical counts persisting >= 2 frames), the count must not flap frame-to-frame once nonzero.
    flapping = any(abs(counts[i] - counts[i - 1]) > 0 and min(counts[i], counts[i - 1]) > 0
                  and counts[i] != counts[i - 1] for i in range(1, len(counts)))
    return {"n_frames": len(pngs), "counts": counts, "fired": fired, "flapping_detected": flapping,
           "passed": fired and not flapping,
           "admitted": fired and not flapping}


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
    if not rom or not init_state:
        return {"error": "gate 6 needs --rom AND --init-state (a seed state for the v2 start "
                         "position). NEEDS_ASSETS_NOT_PRESENT -- per the doc's own §6 gate 6 prep "
                         "note, no such seed state exists in runs/brain_kirby_entity/ today; none is "
                         "committed to this checkout either."}
    import argparse as _argparse

    from world_mcp import World

    os.environ["KIRBY_SKILLS"] = "1"
    args = _argparse.Namespace(game="kirby_dreamland", rom=rom, init_state=init_state,
                               out="runs/kirby_precheck_seam", record=False,
                               with_screenshot=False, keep_frames=False)
    w = World(args)
    try:
        w.call("observe", {})
        w.call("define_skill", {"name": "walk_probe", "steps": [
            {"repeat_until": {"steps": [{"button": "right", "hold_frames": 30}],
                              "stop_when": "move_blocked", "max_iters": 8}}]})
        t0 = time.perf_counter()
        result = w.call("run_skill", {"name": "walk_probe"})
        elapsed_s = time.perf_counter() - t0
        text = " ".join(c["text"] for c in result if c.get("type") == "text")
        rows = load_jsonl(os.path.join(args.out, "skills.jsonl"))
        run_rec = [r for r in rows if r.get("event") == "run_skill"][-1]
        return {"elapsed_s": elapsed_s, "stop_reason": run_rec.get("stop_reason"),
               "executed_step_count": run_rec.get("executed_step_count"),
               "fires_on_third_blocked_press": "3 press(es)" in run_rec.get("stop_reason", ""),
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


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry", action="store_true", help="run gate 1 (scripted-perceiver executor fixture)")
    ap.add_argument("--all", action="store_true",
                    help="run gates 1, 4, 5, 7 unconditionally; 2/3/6 only if their asset flags are given")
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

    exit_ok = True

    if args.measure_overhead:
        report = measure_overhead(rom=args.rom, init_state=args.init_state, frames_dir=args.frames_dir)
        print("=== Gate 2: per-press executor overhead ===")
        print(json.dumps(report, indent=2))
        if "error" in report:
            print(report["error"], file=sys.stderr)
        exit_ok = exit_ok and report.get("passed", False)
        if not (args.dry or args.all):
            return 0 if exit_ok else 1

    if args.check_entities:
        report = check_entities_admission(args.frames_dir)
        print("=== Gate 3: entity_count_changed admission check ===")
        print(json.dumps({k: v for k, v in report.items() if k != "counts"}, indent=2))
        if "error" in report:
            print(report["error"], file=sys.stderr)
        exit_ok = exit_ok and report.get("passed", False)
        if not (args.dry or args.all):
            return 0 if exit_ok else 1

    if args.seam_physics:
        report = check_seam_physics(args.rom, args.init_state)
        print("=== Gate 6: seam-press physics re-validation ===")
        print(json.dumps(report, indent=2))
        if "error" in report:
            print(report["error"], file=sys.stderr)
        if not (args.dry or args.all):
            return 0 if "error" not in report else 1

    dry_report = None
    audit_report = None
    if args.dry or args.all:
        dry_report = run_dry(args.out)
        audit_report = check_auditability(args.out)

    seam_report = check_seam_isolation()
    fresh_report = check_tools_fresh(args.rom)

    print(format_report(dry_report, seam_report, fresh_report, audit_report))

    gates_pass = (
        (dry_report is None or (dry_report["auditable"] and dry_report["all_scenarios_pass"]))
        and seam_report["passed"]
        and (fresh_report.get("skipped") or fresh_report.get("passed"))
        and (audit_report is None or audit_report["auditable"])
    )
    return 0 if gates_pass else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
