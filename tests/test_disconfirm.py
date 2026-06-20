"""DisconfirmDetector tests — the within-run 'act -> observe -> learn' nudge (no network)."""

import pytest

from core.disconfirm import DisconfirmDetector


def test_fires_only_after_threshold_consecutive_no_progress():
    d = DisconfirmDetector(after=3)
    d.record(False); assert d.note() is None      # 1 no-progress decision
    d.record(False); assert d.note() is None       # 2
    d.record(False)                                # 3 -> fires
    note = d.note()
    # S3 beta: the note is channel-neutral (no literal "LESSON:" token — the within-run store depends
    # on the backend), but still a SURPRISE nudge to change approach + remember the blocker.
    assert note and note.startswith("SURPRISE") and "LESSON" not in note
    assert "no observable progress" in note and "remember what is blocking you" in note


def test_progress_resets_the_streak():
    d = DisconfirmDetector(after=2)
    d.record(False)
    d.record(True)                                 # progress -> streak back to 0
    d.record(False)
    assert d.note() is None                        # only 1 no-progress decision since the reset
    assert d.fired is False


def test_note_names_a_blocked_move():
    d = DisconfirmDetector(after=1)
    d.record(False, {"action": "up+up", "outcome": "blocked"})
    note = d.note()
    assert note and "blocked by a wall" in note and "up+up" in note


def test_note_describes_a_no_effect_action_when_not_blocked():
    d = DisconfirmDetector(after=1)
    d.record(False, {"action": "a", "outcome": "n/a"})
    note = d.note()
    assert note and "changed nothing" in note and "(a)" in note


def test_consuming_the_note_resets_the_streak():
    d = DisconfirmDetector(after=2)
    d.record(False); d.record(False)
    assert d.note() is not None                    # fires once...
    assert d.note() is None                        # ...and is consumed (streak reset), so not again


def test_note_fires_without_action_detail_when_last_action_missing():
    d = DisconfirmDetector(after=1)
    d.record(False, None)                          # no last_action info available
    note = d.note()
    assert note and "SURPRISE" in note and "LESSON" not in note    # channel-neutral wording (S3 beta)
    assert "last move" not in note and "last action" not in note   # no action-specific detail


def test_after_must_be_at_least_one():
    with pytest.raises(ValueError):
        DisconfirmDetector(after=0)
