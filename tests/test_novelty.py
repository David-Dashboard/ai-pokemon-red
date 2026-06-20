"""NoveltyMemory — the seen-states signal (visit-counting, rising-edge)."""
from core.novelty import NoveltyMemory


def test_first_sighting_is_one_visit():
    nm = NoveltyMemory()
    assert nm.observe(("dialog", "hello")) == 1


def test_held_frame_stays_one_visit():
    """A state held across consecutive observations (a settled textbox not yet advanced) is ONE
    visit — the step-300 'Don't go out!' held-frame guard, so a normal dialog isn't mistaken for a
    loop."""
    nm = NoveltyMemory()
    counts = [nm.observe(("dialog", "Don't go out!")) for _ in range(4)]
    assert counts == [1, 1, 1, 1]


def test_leave_and_return_counts_each_visit():
    """The cycle case: the SAME state returned to after leaving it (Oak's 'which POKéMON?' reopening)
    counts a new visit each time."""
    nm = NoveltyMemory()
    a = ("dialog", "which POKEMON?")
    b = ("dialog", "OAK: Now, ASH,")
    assert nm.observe(a) == 1
    assert nm.observe(b) == 1     # leave a
    assert nm.observe(a) == 2     # return to a -> 2nd visit
    assert nm.observe(b) == 2
    assert nm.observe(a) == 3     # 3rd visit


def test_none_key_breaks_a_held_run():
    """A None key (a transition/empty frame) carries no state but still BREAKS a held run, so a state
    seen before and after a gap counts twice (matches the validated gate simulation: prev=None on
    skipped frames)."""
    nm = NoveltyMemory()
    a = ("dialog", "x")
    assert nm.observe(a) == 1
    assert nm.observe(None) == 0      # None always returns 0...
    assert nm.observe(a) == 2         # ...and the gap makes the next sighting a fresh visit


def test_distinct_keys_are_counted_independently():
    nm = NoveltyMemory()
    a, b = ("overworld", "A"), ("overworld", "B")
    assert [nm.observe(a), nm.observe(b), nm.observe(a), nm.observe(b)] == [1, 1, 2, 2]


def test_visits_is_read_only():
    """visits() reports the running count without registering a new observation."""
    nm = NoveltyMemory()
    a = ("dialog", "x")
    nm.observe(a)
    assert nm.visits(a) == 1
    assert nm.visits(a) == 1          # querying did not increment
    assert nm.visits(("never", "seen")) == 0
    assert nm.visits(None) == 0
    assert nm.observe(a) == 1         # a held run: observe right after a same-key query is still held
