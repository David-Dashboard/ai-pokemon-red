"""Fail-closed OFFLINE oracle scorer for graduation-exam v1 EX01 -- Red: first badge.

Task (reports/2026-07-22-graduation-exam-v1-definition.md EX01, PR #129 -- v1-DRAFT, NOT frozen;
task bars here are pending David's freeze of that PR): "From the fresh bedroom start, earn your
first Gym Badge." End state: RAM oracle `badges` (0xD356, `world_mcp.py:177`, the SAME field
`eval/score_gate0.py::_red_success` already reads) bit 0 flips 0->1 (Boulder Badge).

Reads only `oracle.jsonl` `watch` rows -- never the transcript, never a model self-report -- and
mirrors `score_gate0.py::_red_success`'s fail-closed shape in full, not just the corrupt-row filter:
a corrupted single-tick RAM read (every watched field simultaneously 0 -- the same PyBoy
polling-sampler glitch signature documented in `score_gate0.py`) is filtered out before scoring,
never treated as a real world state; anything else missing/malformed is a hard refusal, never a
guessed PASS. Critically, a bare `badges` bit-0 flip is NEVER enough on its own (PR #139 review
finding 1: a stuck/corrupted/substituted single byte can flip with zero real progress behind it) --
the flip must be CORROBORATED by the same two preconditions `_red_success` requires before trusting
any Red RAM transition: (1) an exact `party` 0->1 transition (a starter must exist -- mirrors
`_red_success`'s own exact-transition check), and (2) a real battle (`in_battle == 2`, at or after
the starter exists) strictly before the badge bit flips (a Gym Badge cannot be won without a Gym
Leader battle). Both are hard refusals when missing, exactly like `_red_success`.

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


def _plain_int(value: object) -> bool:
    """True only for a genuine RAM-byte-shaped int -- bool explicitly excluded (`True == 1` would
    otherwise pass a numeric check meant for a real byte, same reasoning as `_badges_bit0`)."""
    return not isinstance(value, bool) and isinstance(value, int)


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

    parties = [w.get("party") for w in kept]
    in_battles = [w.get("in_battle") for w in kept]
    if any(not _plain_int(p) for p in parties) or any(not _plain_int(b) for b in in_battles):
        return False, ["red_badge_missing_or_invalid_oracle_field"]

    if parties[0] != 0 or bits[0] is not False:
        # "Fresh bedroom start" == no party member yet AND no badge yet -- either being untrue means
        # this isn't the fresh-start trace the task requires, not a genuine badge-earning attempt.
        return False, ["red_badge_not_fresh_start"]

    # Corroboration #1 (mirrors score_gate0.py::_red_success): a starter must actually exist before
    # a badge can be earned. Find the FIRST party transition and require it be exactly 0 -> 1 -- a
    # corrupted/out-of-order jump (e.g. straight to 2) is refused, not silently accepted.
    party_idx = next((i for i in range(1, len(parties)) if parties[i] != parties[i - 1]), None)
    if party_idx is None:
        return False, ["red_badge_no_party_0_to_1"]
    if parties[party_idx - 1] != 0 or parties[party_idx] != 1:
        return False, ["red_badge_party_transition_not_exactly_0_to_1"]

    # Corroboration #2: a real battle (in_battle == 2 -- the same trainer/gym-leader encoding
    # score_gate0.py's _red_success reads), at or after the starter exists, must actually appear in
    # the trace. A badge-bit flip with zero battle evidence anywhere is refused, never trusted.
    battle_idx = next((i for i in range(party_idx, len(in_battles)) if in_battles[i] == 2), None)
    if battle_idx is None:
        return False, ["red_badge_no_battle_after_party_acquisition"]

    transition_idx = next((i for i in range(1, len(bits)) if bits[i - 1] is False and bits[i] is True), None)
    if transition_idx is None:
        return False, ["red_badge_never_earned"]

    if transition_idx <= battle_idx:
        # The badge bit must flip strictly AFTER the qualifying battle row -- a flip that precedes
        # or coincides with battle-entry has no real battle behind it yet.
        return False, ["red_badge_flip_not_after_battle"]

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
