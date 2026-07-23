"""Shared MiniWoB success predicate for the graduation-exam v1 browser tasks (EX07, EX08).

Mirrors `eval/score_gate0.py::_miniwob_success` EXACTLY (same refuse-on-malformed-or-missing shape:
extra/mismatched episode-seed rows, a row carrying the wrong task name, a terminal reward that
isn't a genuine `1.0` float, a stray row logged after the success terminal) -- parameterized on
`task`/`expected_seeds` so EX07 (`focus-text`) and EX08 (`click-checkboxes`, exam-own seeds) share
one algorithm without copy-pasting it, instead of each hardcoding Gate 0's `click-checkboxes`
constant. `eval/score_gate0.py` itself is Gate-0-frozen machinery (gate-methodology: "reused
byte-for-byte") and is NOT imported or modified here.

See reports/2026-07-22-graduation-exam-v1-definition.md EX07/EX08 for the task definitions.
"""
from __future__ import annotations


def miniwob_task_success(rows: list[dict], expected_seeds: list[int], task: str) -> tuple[bool, list[str]]:
    failures: list[str] = []
    expected = dict(enumerate(expected_seeds))
    if any(row.get("episode") not in expected or row.get("seed") != expected.get(row.get("episode"))
           for row in rows):
        failures.append("miniwob_extra_episode_or_seed_conflict")
    # Every row must carry the pinned task. A row with any other task value is a hard scorer
    # refusal (a malformed/tampered manifest or cross-task oracle mixup), never silently ignored.
    if any(row.get("task") != task for row in rows):
        failures.append("miniwob_wrong_task_row")
    for episode, seed in expected.items():
        episode_rows = [row for row in rows if row.get("episode") == episode and row.get("seed") == seed]
        terminal_idx = [i for i, row in enumerate(episode_rows)
                        if row.get("done") is True or row.get("abandoned") is True]
        if len(terminal_idx) != 1:
            failures.append(f"miniwob_episode_{episode}_terminal_count")
            continue
        idx = terminal_idx[0]
        terminal = episode_rows[idx]
        reward = terminal.get("reward")
        # JSON `true`/`false` decode to Python bool, and `True == 1.0` -- reject bool explicitly
        # before the numeric check so a boolean can never stand in for the pinned float reward.
        success = (terminal.get("done") is True and terminal.get("abandoned") is False
                  and terminal.get("task") == task
                  and not isinstance(reward, bool) and isinstance(reward, (int, float))
                  and reward == 1.0)
        if not success:
            failures.append(f"miniwob_episode_{episode}_terminal_not_success")
        elif idx != len(episode_rows) - 1:
            # A row for this episode/seed was logged after its success terminal -- the terminal
            # must be the last thing this episode did.
            failures.append(f"miniwob_episode_{episode}_terminal_not_last_row")
    return not failures, failures
