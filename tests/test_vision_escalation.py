"""VisionEscalator — strong-VLM grounding at stuck moments, cached per state + per-run capped."""
from core.vision_escalation import VisionEscalator


def _counter_fn(text="a name-entry keyboard; press START to confirm"):
    calls = []

    def fn(prompt, image_path):
        calls.append((prompt, image_path))
        return text
    return fn, calls


def test_ground_returns_description_and_counts_a_call():
    fn, calls = _counter_fn()
    ve = VisionEscalator(fn)
    assert ve.ground("f.png", ("dialog", "x")) == "a name-entry keyboard; press START to confirm"
    assert ve.calls == 1 and len(calls) == 1


def test_same_state_is_cached_one_call_per_screen():
    """The held-keyboard case: 44 wakes on the SAME state must cost ONE VLM call, not 44."""
    fn, calls = _counter_fn()
    ve = VisionEscalator(fn)
    key = ("battle", "")
    for _ in range(44):
        ve.ground("f.png", key)
    assert ve.calls == 1 and len(calls) == 1


def test_distinct_states_each_call_once():
    fn, calls = _counter_fn()
    ve = VisionEscalator(fn)
    ve.ground("f.png", ("a", "1"))
    ve.ground("f.png", ("b", "2"))
    ve.ground("f.png", ("a", "1"))      # revisit -> cached
    assert ve.calls == 2 and len(calls) == 2


def test_per_run_cap_degrades_to_none():
    fn, calls = _counter_fn()
    ve = VisionEscalator(fn, max_calls=2)
    assert ve.ground("f.png", ("s", "1")) is not None
    assert ve.ground("f.png", ("s", "2")) is not None
    assert ve.ground("f.png", ("s", "3")) is None      # cap hit
    assert ve.calls == 2 and len(calls) == 2


def test_no_image_no_call():
    fn, calls = _counter_fn()
    ve = VisionEscalator(fn)
    assert ve.ground(None, ("s", "1")) is None
    assert ve.ground("", ("s", "2")) is None
    assert ve.calls == 0 and len(calls) == 0


def test_describe_fn_failure_is_swallowed_and_cached():
    def boom(prompt, image_path):
        raise RuntimeError("litellm down")
    ve = VisionEscalator(boom)
    assert ve.ground("f.png", ("s", "1")) is None       # graceful: never raises
    assert ve.ground("f.png", ("s", "1")) is None       # cached None -> no retry
    assert ve.calls == 1                                # one attempt only


def test_tolerates_text_and_tuple_and_empty():
    # (text, usage) tuple (the _openai_complete shape)
    ve1 = VisionEscalator(lambda p, i: ("grounding text", {"prompt_tokens": 9}))
    assert ve1.ground("f.png", ("s", "1")) == "grounding text"
    # whitespace-only -> None
    ve2 = VisionEscalator(lambda p, i: "   ")
    assert ve2.ground("f.png", ("s", "1")) is None


def test_escalation_spend_is_metered():
    """The Sonnet usage is metered into total_cost_usd so a single cost cap can bound escalation too."""
    ve = VisionEscalator(lambda p, i: ("text", {"prompt_tokens": 1000, "completion_tokens": 200}))
    assert ve.total_cost_usd == 0.0
    ve.ground("f.png", ("s", "1"))
    assert ve.total_cost_usd > 0.0                  # 1000 in x $3/M + 200 out x $15/M
    ve.ground("f.png", ("s", "1"))                  # cached -> no new spend
    after = ve.total_cost_usd
    ve.ground("f.png", ("s", "1"))
    assert ve.total_cost_usd == after
