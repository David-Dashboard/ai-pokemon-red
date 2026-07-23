"""Fail-closed OFFLINE oracle scorer for graduation-exam v1 EX01 -- Red: first badge.

Task (reports/2026-07-22-graduation-exam-v1-definition.md EX01): "From the fresh bedroom start,
earn your first Gym Badge." End state: RAM oracle `badges` (0xD356, `world_mcp.py:177`, the SAME
field `eval/score_gate0.py::_red_success` already reads) bit 0 flips 0->1 (Boulder Badge).

Reads only `oracle.jsonl` `watch` rows -- never the transcript, never a model self-report -- and
mirrors `score_gate0.py::_red_success`'s fail-closed shape: a corrupted single-tick RAM read (every
watched field simultaneously 0 -- the same PyBoy polling-sampler glitch signature documented in
`score_gate0.py`) is filtered out before scoring, never treated as a real world state; anything
else missing/malformed is a hard refusal, never a guessed PASS.

Usage: `uv run python -m eval.score_exam_red_badge <oracle.jsonl>`
"""
from __future__ import annotations

from eval._exam_common import run_cli

TASK_ID = "EX01"
# The full watch dict this world logs (world_mcp.py GAMES["pokemon_red"]["watch"]) -- used only to
# detect the corrupted-glitch-row signature below, mirroring score_gate0.py's _is_corrupt_glitch_row.
_WATCHED_KEYS = ("x", "y", "map", "party", "badges", "in_battle", "party_hp_hi", "party_hp_lo")


def _is_corrupt_glitch_row(watch: dict) -> bool:
    return all(watch.get(k) == 0 for k in _WATCHED_KEYS)


def _badges_bit0(value: object) -> bool | None:
    """Boulder Badge = bit 0 of the `badges` byte. Returns None (never a guess) if `value` isn't a
    plain 0-255 int -- a bool is explicitly rejected first since `True == 1` would otherwise pass a
    numeric range/bit check meant for a real RAM byte."""
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 255:
        return None
    return bool(value & 0x01)


def _red_badge_success(rows: list[dict]) -> tuple[bool, list[str]]:
    failures: list[str] = []
    watches = [row.get("watch") for row in rows if isinstance(row.get("watch"), dict)]
    if not watches:
        return False, ["red_badge_no_watch_rows"]

    kept = [w for w in watches if not _is_corrupt_glitch_row(w)]
    if not kept:
        return False, ["red_badge_all_rows_corrupt_glitch"]

    bits = [_badges_bit0(w.get("badges")) for w in kept]
    if any(b is None for b in bits):
        return False, ["red_badge_missing_or_invalid_oracle_field"]

    if kept[0].get("party") != 0 or bits[0] is not False:
        # "Fresh bedroom start" == no party member yet AND no badge yet -- either being untrue means
        # this isn't the fresh-start trace the task requires, not a genuine badge-earning attempt.
        return False, ["red_badge_not_fresh_start"]

    transition_idx = next((i for i in range(1, len(bits)) if bits[i - 1] is False and bits[i] is True), None)
    if transition_idx is None:
        return False, ["red_badge_never_earned"]

    # Badges are permanent progress -- a bit that flips back to 0 after being set is itself a
    # corruption/tamper signal (a savestate reload, a substituted row, ...), never a real regression.
    if any(b is False for b in bits[transition_idx:]):
        failures.append("red_badge_bit_reverted_after_set")

    return not failures, failures


def score(rows: list[dict]) -> dict:
    ok, failures = _red_badge_success(rows)
    return {"schema_version": 1, "task_id": TASK_ID, "task": "red_first_badge",
            "overall": "PASS" if ok else "FAIL_CAPABILITY", "failures": failures}


def main() -> int:
    return run_cli(TASK_ID, score)


if __name__ == "__main__":
    raise SystemExit(main())
