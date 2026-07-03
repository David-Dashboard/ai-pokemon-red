"""eval/score_skill_rung1.py -- the FREE pre-check pinned by
reports/2026-07-03-skill-compilation-design.md §4.0, before any paid A/B (§4.1) is scheduled: a
scripted/replay comparison (ARC API steps are free; no brain session) confirming (a) the pinned ARC
stop-conditions fire at the points a human reading a transcript would call the macro "done", and (b)
the skill log (skills.jsonl) is auditable -- a reviewer can read define_skill's logged definition and
run_skill's per-call step log and reconstruct exactly what happened. This is a BUILD-CORRECTNESS check,
not the gate itself (doc §4.0: "must pass before any paid arm is scheduled").

Two modes:

  --dry (default, recommended; consumes NO real API sessions): drives ArcAgi3Session's real
    define_skill/run_skill dispatch against CANNED grid-sequence scenarios
    (eval/fixtures/skill_rung1_push_macro.json) with requests.Session.post/get monkeypatched exactly
    like tests/test_arcagi3_world.py's FakeArcApi -- same no-network discipline as the unit tests, so
    this mode is free to run in CI or locally with no ARC_API_KEY at all. The fixture covers the happy
    path AND the unhappy ones (PR #89 review finding 5): a stop_when firing mid-loop on a multi-action
    inner list, a max_iters cap-out, the absolute 50-world-step ceiling, and an illegal-action failure
    -- each scenario pins the expected stop reason + executed count and the driver CHECKS them, so a
    drifting executor fails the pre-check loudly.

  --score-only SKILLS_JSONL: audits an EXISTING skills.jsonl from a real (paid or --dry) run --
    mechanically checks every define_skill/redefine_skill record has a verbatim `definition` (and, for
    redefines, the `prior_definition`), every run_skill record has
    `executed`/`executed_step_count`/`stop_reason`/`world_steps_used`, and reports the qualifying-
    call count (executed_step_count >= 3, the doc §4.1 degenerate-strategy guard) so a reviewer doesn't
    have to eyeball raw jsonl by hand.

NOTE on the doc's literal wording (flagged at design review, see PR body): §4.0 describes replaying
"existing wa30 transcripts (three runs in runs/brain_arcagi3/)" through run_skill. That directory does
not exist in this checkout (no wa30 transcripts are committed to the repo), and even if it did, replaying
against the LIVE ARC API would consume real API sessions -- contrary to §4.0's own "free instrument
first" framing. --dry is the substitute: it exercises the SAME executor code path
(ArcAgi3Session._define_skill/_run_skill) against a small canned fixture built to mirror doc §5's worked
push-block example, so the build-correctness properties (a) and (b) above are checked for real, for
free, without a live API call. If real wa30 transcripts become available later, --score-only can audit
their skills.jsonl directly (no code change needed).

Usage:
    uv run python -m eval.score_skill_rung1 --dry
    uv run python -m eval.score_skill_rung1 --score-only runs/brain_arcagi3/run1/world/skills.jsonl
"""
from __future__ import annotations

import argparse
import json
import os
import sys

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

QUALIFYING_MIN_EXECUTED_STEPS = 3   # doc §4.1 degenerate-strategy guard: executed (not defined) steps

DEFAULT_FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "skill_rung1_push_macro.json")


# ---------------------------------------------------------------------------
# Part 1: the auditability scorer -- pure stdlib, works on any skills.jsonl.
# ---------------------------------------------------------------------------

def audit_skill_log(rows: list[dict]) -> dict:
    """Mechanical audit of a skills.jsonl row list: every define_skill row must carry a verbatim
    `definition` (a redefine_skill row additionally the `prior_definition` it replaced — PR #89 review
    finding 3); every run_skill row must carry the fields doc §3's auditability requirement pins
    (executed steps, iteration counts / stop reason, executed-step count). Returns a report dict; never
    raises on a malformed row -- the whole point is to surface issues, not crash on them."""
    define_rows = [r for r in rows if r.get("event") == "define_skill"]
    redefine_rows = [r for r in rows if r.get("event") == "redefine_skill"]
    run_rows = [r for r in rows if r.get("event") == "run_skill"]

    def _bad_definition(d) -> bool:
        return not isinstance(d, dict) or "steps" not in d or "name" not in d

    define_issues = []
    for r in define_rows:
        if _bad_definition(r.get("definition")):
            define_issues.append(f"define_skill row at step {r.get('step')} missing a verbatim "
                                 f"definition (name+steps): {r!r}")
    for r in redefine_rows:
        if _bad_definition(r.get("definition")) or _bad_definition(r.get("prior_definition")):
            define_issues.append(f"redefine_skill row at step {r.get('step')} must carry BOTH the new "
                                 f"`definition` and the replaced `prior_definition`: {r!r}")

    run_issues = []
    qualifying = 0
    for r in run_rows:
        missing = [k for k in ("executed", "executed_step_count", "stop_reason", "world_steps_used")
                  if k not in r]
        if missing:
            run_issues.append(f"run_skill row at step {r.get('step')} missing field(s) {missing}: {r!r}")
            continue
        if r["executed_step_count"] >= QUALIFYING_MIN_EXECUTED_STEPS:
            qualifying += 1

    auditable = not define_issues and not run_issues
    return {
        "n_define_skill": len(define_rows), "n_redefine_skill": len(redefine_rows),
        "n_run_skill": len(run_rows),
        "n_qualifying_calls": qualifying,
        "define_issues": define_issues, "run_issues": run_issues,
        "auditable": auditable,
        # doc §4.1: "if Arm B's qualifying-call count is 0, the A/B is uninformative" -- surfaced here
        # so a reviewer of a --dry or real run immediately sees whether ANY qualifying call happened.
        "insufficient_data_if_paid_run": qualifying == 0,
    }


def format_audit_report(report: dict, *, source: str) -> str:
    lines = [f"=== skill_rung1 auditability pre-check ({source}) ===", ""]
    lines.append(f"define_skill records:   {report['n_define_skill']}")
    if report.get("n_redefine_skill"):
        lines.append(f"redefine_skill records: {report['n_redefine_skill']}")
    lines.append(f"run_skill records:      {report['n_run_skill']}")
    lines.append(f"qualifying calls (executed_step_count >= {QUALIFYING_MIN_EXECUTED_STEPS}): "
                 f"{report['n_qualifying_calls']}")
    if report["define_issues"] or report["run_issues"]:
        lines.append("")
        lines.append("ISSUES:")
        for msg in report["define_issues"] + report["run_issues"]:
            lines.append(f"  - {msg}")
    if report.get("scenarios") is not None:
        lines.append("")
        lines.append("scenarios (expected stop reason + executed count, checked against the log):")
        for sc in report["scenarios"]:
            lines.append(f"  {'PASS' if sc['ok'] else 'FAIL'}  {sc['name']}: {sc['detail']}")
    lines.append("")
    lines.append(f"auditable: {'YES' if report['auditable'] else 'NO'}")
    if report.get("scenarios") is not None:
        lines.append(f"all scenarios pass: {'YES' if report['all_scenarios_pass'] else 'NO'}")
    if report["insufficient_data_if_paid_run"]:
        lines.append("NOTE: 0 qualifying calls -- per doc §4.1, a paid A/B arm with this log would bank "
                     "as INSUFFICIENT_DATA, not PASS/FAIL.")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Part 2: --dry driver -- exercises the REAL executor against a canned fixture, no live API.
# ---------------------------------------------------------------------------

def _install_scenario_fake_api(monkeypatch, scenario: dict, game_id: str):
    """Same monkeypatch shape as tests/test_arcagi3_world.py's FakeArcApi, scripted from the
    scenario's frame list instead of hand-written per-test frames. A frame entry may carry
    "repeat": N to stand for N identical consecutive post-action frames (used by the ceiling_hit
    scenario, which needs 50+ frames)."""
    from tests.test_arcagi3_world import FakeArcApi

    api_frames = []
    for fr in scenario["frames"]:
        for _ in range(int(fr.get("repeat", 1))):
            api_frames.append({
                "game_id": game_id, "guid": "fixture-guid",
                "frame": [fr["grid"]], "state": fr.get("state", "NOT_FINISHED"),
                "levels_completed": 0, "win_levels": 254,
                "available_actions": fr["available_actions"],
            })
    fake = FakeArcApi(api_frames)
    monkeypatch.setattr("requests.Session.post",
                        lambda self, url, json=None, timeout=None: fake.post(url, json=json, timeout=timeout))
    monkeypatch.setattr("requests.Session.get",
                        lambda self, url, timeout=None: fake.get(url, timeout=timeout))
    monkeypatch.setattr("time.sleep", lambda s: None)
    return fake


def run_dry(fixture_path: str, out_dir: str) -> dict:
    """Drive the REAL ArcAgi3Session.define_skill/run_skill dispatch against each canned scenario in
    the fixture, with the ARC REST API monkeypatched out exactly like the unit tests. Each scenario
    gets a fresh session (its own <out>/<scenario>/skills.jsonl); the combined rows are audited and
    each scenario's pinned expectations (stop-reason substring + executed-step count) are CHECKED, so
    the pre-check fails loudly on executor drift, not just on malformed logs. Uses pytest's
    MonkeyPatch directly (no pytest session needed) so this can run as a plain script, matching
    eval/score_a3_precheck.py's "pure stdlib scorer, separately-run driver" split."""
    import argparse as _argparse

    from _pytest.monkeypatch import MonkeyPatch

    from world_mcp import ArcAgi3Session

    with open(fixture_path, encoding="utf-8") as f:
        fixture = json.load(f)
    game_id = fixture.get("game_id", "fixture")

    all_rows: list[dict] = []
    scenario_results: list[dict] = []
    combined_path = os.path.join(out_dir, "skills.jsonl")
    os.makedirs(out_dir, exist_ok=True)
    if os.path.exists(combined_path):
        os.remove(combined_path)   # fresh combined log per invocation (scenario logs are per-subdir)

    for sc in fixture["scenarios"]:
        sc_out = os.path.join(out_dir, sc["name"])
        os.makedirs(sc_out, exist_ok=True)
        sc_log = os.path.join(sc_out, "skills.jsonl")
        if os.path.exists(sc_log):
            os.remove(sc_log)
        mp = MonkeyPatch()
        try:
            _install_scenario_fake_api(mp, sc, game_id)
            # This driver's whole purpose is to exercise define_skill/run_skill dispatch (the doc §4.0
            # free instrument, a build-correctness check) -- independent of the A/B ARC_SKILLS gate
            # (doc §4.1) that controls whether a live BRAIN session sees these tools.
            mp.setenv("ARC_SKILLS", "1")
            args = _argparse.Namespace(game="arcagi3", rom=None, init_state=None, out=sc_out,
                                       record=False, with_screenshot=False, keep_frames=False,
                                       seeds_file=None, seed=None, arc_game=game_id)
            sess = ArcAgi3Session(args)
            for define_payload in sc["define"]:
                sess.call("define_skill", define_payload)
            sess.call("run_skill", {"name": sc["run"]})
        finally:
            mp.undo()

        rows = load_jsonl(sc_log)
        all_rows.extend(rows)
        run_rows = [r for r in rows if r.get("event") == "run_skill"]
        rec = run_rows[0] if run_rows else {}
        reason_ok = sc["expect_stop_reason_contains"] in rec.get("stop_reason", "")
        count_ok = rec.get("executed_step_count") == sc["expect_executed_steps"]
        detail = (f"stop_reason={rec.get('stop_reason')!r}, "
                  f"executed={rec.get('executed_step_count')!r} "
                  f"(expected contains {sc['expect_stop_reason_contains']!r}, "
                  f"executed == {sc['expect_executed_steps']})")
        scenario_results.append({"name": sc["name"], "ok": reason_ok and count_ok, "detail": detail})

    with open(combined_path, "w", encoding="utf-8") as f:
        for r in all_rows:
            f.write(json.dumps(r) + "\n")

    report = audit_skill_log(all_rows)
    report["scenarios"] = scenario_results
    report["all_scenarios_pass"] = all(sc["ok"] for sc in scenario_results)
    return report


def load_jsonl(path: str) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_mutually_exclusive_group()
    sub.add_argument("--dry", action="store_true", default=True,
                     help="(default) drive the real executor against a canned fixture -- no live API, "
                          "no ARC_API_KEY needed.")
    sub.add_argument("--score-only", metavar="SKILLS_JSONL",
                     help="audit an EXISTING skills.jsonl (e.g. from a real run) for auditability + "
                          "the qualifying-call count. No fixture/executor involved.")
    ap.add_argument("--fixture", default=DEFAULT_FIXTURE, help="--dry only: canned grid-sequence JSON")
    ap.add_argument("--out", default="runs/skill_rung1_precheck", help="--dry only: where to write "
                    "the fresh skills.jsonl")
    args = ap.parse_args(argv)

    if args.score_only:
        rows = load_jsonl(args.score_only)
        report = audit_skill_log(rows)
        print(format_audit_report(report, source=args.score_only))
        return 0 if report["auditable"] else 1

    report = run_dry(args.fixture, args.out)
    print(format_audit_report(report, source=f"--dry ({args.fixture})"))
    print(f"\nskills.jsonl (combined + per-scenario) written under {args.out}/", file=sys.stderr)
    return 0 if (report["auditable"] and report["all_scenarios_pass"]) else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
