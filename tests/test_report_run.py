"""Tests for the per-run report scaffolder (eval/report_run.py) — pure fact extraction + rendering.

The whole point of the scaffolder is that the numbers are reliable, so the win/no-win detector (which
must NOT call a 1-frame in_battle blip a win — the run #8 over-claim) and the counts are pinned here.
"""

from eval.report_run import extract_facts, render_report, _battle_outcome


def _oracle(in_battle, maps=None):
    maps = maps or [40] * len(in_battle)
    return [{"in_battle": ib, "map_id": m, "party_level_sum": None, "badges": 0}
            for ib, m in zip(in_battle, maps)]


def test_won_needs_a_sustained_exit_not_a_one_frame_blip():
    # run #12/#13 shape: 2...2 then 0 forever -> won at the exit index.
    won = [2] * 5 + [0] * 20
    assert _battle_outcome(won) == ("won", 5)
    # run #8 shape: a single transient 0 mid-battle, ends at 2 -> NOT a win.
    blip = [2, 2, 2, 0, 2, 2, 2, 2, 2, 2]
    assert _battle_outcome(blip) == ("in-battle-at-cap", None)
    # run #4 shape: never in a battle.
    assert _battle_outcome([0] * 10) == ("no-battle", None)


def test_extract_facts_from_oracle_and_log():
    rows = _oracle([2] * 4 + [0] * 12, maps=[40, 40, 40, 40] + [0] * 12)
    log = "\n".join([
        "[0000] pose=[0,0]", "        think: [wake:mode] enter battle  -> a",
        "[0001] pose=[0,0]", "        think: [auto-advance]  -> a",
        "[0002] pose=[0,0]", "        think: [auto-advance]  -> a",
        "[0003] pose=[0,0]", "        think: [wake:mode] move menu, SCRATCH  -> a",
        "[0010] pose=[0,0]", "        think: [wake:stuck] exploring  -> up",   # a post-battle wake
        "=== episode summary ===", "  total_reward: 4.5",
        "  llm_woke: 3/16 steps (18.8%) - autopilot handled the rest",
    ])
    f = extract_facts(rows, log)
    assert f["outcome"] == "won" and f["exit_step"] == 4
    assert f["wakes"] == 3 and f["auto_advances"] == 2
    assert f["battle_wakes"] == 2          # the two wakes at steps 0 and 3 (< exit step 4)
    assert f["trajectory"] == [40, 0]
    assert f["summary_woke"] == 3 and f["summary_wake_pct"] == 18.8 and f["total_reward"] == 4.5
    assert f["errors"] == 0


def test_extract_facts_counts_errors_and_handles_missing_artifacts():
    f = extract_facts(None, "litellm 400: Your credit balance is too low\nTraceback (most recent call):")
    assert f["has_oracle"] is False and f["has_log"] is True
    assert f["errors"] >= 2                 # the 400 + the Traceback
    g = extract_facts(_oracle([2, 2, 2]), None)
    assert g["has_log"] is False and g["outcome"] == "in-battle-at-cap"


def test_render_report_has_facts_and_todos():
    rows = _oracle([2] * 3 + [0] * 12)
    f = extract_facts(rows, "[0000]\n        think: [wake:mode] x  -> a")
    md = render_report(f, {"run_id": "13", "title": "battle auto-advance", "date": "2026-06-20"})
    assert "# Live run #13 — battle auto-advance (2026-06-20)" in md
    assert "**WON**" in md and "sustained-exit @ 3" in md
    assert "TODO" in md                     # narrative placeholders present
    assert "DEFINITION OF DONE" in md       # the checklist reminder is embedded
