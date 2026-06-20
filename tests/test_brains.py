"""Brain tests — backend selection and response parsing (no network calls)."""

import pytest

from core.brains import LLMButtonBrain, ScriptedBrain
from core.contracts import Observation

BUTTONS = ("a", "b", "start", "select", "up", "down", "left", "right")


def _obs():
    return Observation(data={"screen_path": ""}, text="state text", agent_id="a", t=0.0)


def test_scripted_brain_returns_a_button_press():
    call = ScriptedBrain("a", seed=1).decide(_obs(), [], {})
    assert call.tool == "press_button" and call.args["button"] in BUTTONS


def test_llm_brain_parses_single_button_from_free_text():
    # complete_fn stands in for the model; no server needed.
    brain = LLMButtonBrain("a", complete_fn=lambda prompt, image: "I think DOWN is best")
    call = brain.decide(_obs(), [], {})
    assert call.tool == "press_button" and call.args["button"] == "down"


def test_llm_brain_emits_sequence_for_multiple_buttons():
    brain = LLMButtonBrain("a", complete_fn=lambda prompt, image: "up up left")
    call = brain.decide(_obs(), [], {})
    assert call.tool == "press_sequence" and call.args["buttons"] == ["up", "up", "left"]


def test_llm_brain_takes_buttons_from_move_line_and_captures_thought():
    # 'down' appears in the reasoning, but only the MOVE line should drive input.
    reply = "THINK: I'll head down to the stairs on the left\nMOVE: left left"
    brain = LLMButtonBrain("a", complete_fn=lambda prompt, image: reply)
    call = brain.decide(_obs(), [], {})
    assert call.tool == "press_sequence" and call.args["buttons"] == ["left", "left"]
    assert "stairs" in brain.last_thought


def test_looks_like_api_error_detects_passthrough_errors():
    from core.brains import _looks_like_api_error
    assert _looks_like_api_error("Something went wrong on my end: ModelHTTPError: status_code: 400")
    assert _looks_like_api_error('AnthropicException - {"message":"Your credit balance is too low"}')
    assert not _looks_like_api_error("THINK: go up\nMOVE: up up")   # a normal reply must NOT trip it
    assert not _looks_like_api_error("")


def test_llm_brain_circuit_breaker_counts_api_errors_and_resets_on_a_real_reply():
    # aria echoes a backend error (credit-balance 400) as a 200 with the error as the message content,
    # so it doesn't raise — the brain must still count it toward the circuit breaker and NOT act on it.
    replies = iter([
        "Something went wrong on my end: ModelHTTPError: status_code: 400 ... credit balance is too low",
        "litellm.BadRequestError: AnthropicException - credit balance is too low",
        "THINK: ok\nMOVE: up",            # a real reply heals the breaker
    ])
    brain = LLMButtonBrain("a", complete_fn=lambda prompt, image: next(replies))
    c1 = brain.decide(_obs(), [], {})
    assert c1.args["button"] == "a" and brain.consec_api_errors == 1   # defaulted, counted
    brain.decide(_obs(), [], {})
    assert brain.consec_api_errors == 2 and "credit balance" in brain.last_api_error
    c3 = brain.decide(_obs(), [], {})
    assert c3.args["button"] == "up" and brain.consec_api_errors == 0  # healthy reply -> reset


def test_llm_brain_exception_also_counts_toward_circuit_breaker():
    def boom(prompt, image):
        raise ConnectionError("aria unreachable")
    brain = LLMButtonBrain("a", complete_fn=boom)
    brain.decide(_obs(), [], {})
    brain.decide(_obs(), [], {})
    assert brain.consec_api_errors == 2 and "aria unreachable" in brain.last_api_error


def test_llm_brain_backend_selection():
    LLMButtonBrain("a", backend="ollama")      # builds an Ollama complete_fn
    LLMButtonBrain("a", backend="llamacpp")    # builds an OpenAI-compatible one
    LLMButtonBrain("a", backend="aria", api_key="tok")  # bearer-authed OpenAI shape
    with pytest.raises(ValueError):
        LLMButtonBrain("a", backend="bogus")


# -- LESSON: per-run buffer (harness-owned within-run learning) ---------------

def test_llm_brain_captures_lesson_without_breaking_move():
    reply = "THINK: blocked north\nMOVE: down down\nLESSON: the north door is sealed, go south"
    brain = LLMButtonBrain("a", complete_fn=lambda prompt, image: reply)
    call = brain.decide(_obs(), [], {})
    assert call.tool == "press_sequence" and call.args["buttons"] == ["down", "down"]
    assert brain.lesson == "the north door is sealed, go south"
    assert brain.lessons == ["the north door is sealed, go south"]


def test_llm_brain_reinjects_lessons_on_later_decides():
    prompts: list[str] = []

    def complete(prompt, image):
        prompts.append(prompt)
        # author a lesson only on the first call; later calls just move
        return "MOVE: up up\nLESSON: ledges only drop south" if len(prompts) == 1 else "MOVE: up up"

    brain = LLMButtonBrain("a", complete_fn=complete)
    brain.decide(_obs(), [], {})          # records the lesson
    brain.decide(_obs(), [], {})          # should see it re-injected
    assert "ledges only drop south" not in prompts[0]   # not in the prompt that produced it
    assert "ledges only drop south" in prompts[1]        # re-injected on the next wake
    assert "LESSONS you recorded" in prompts[1]


def test_llm_brain_no_lesson_leaves_buffer_empty():
    brain = LLMButtonBrain("a", complete_fn=lambda prompt, image: "THINK: walk\nMOVE: left")
    brain.decide(_obs(), [], {})
    assert brain.lesson is None and brain.lessons == []


def test_llm_brain_lesson_consecutive_duplicate_stored_once():
    dup = LLMButtonBrain("a", complete_fn=lambda prompt, image: "MOVE: a\nLESSON: same")
    dup.decide(_obs(), [], {})
    dup.decide(_obs(), [], {})
    assert dup.lessons == ["same"]


def test_llm_brain_lesson_buffer_caps_to_most_recent():
    from core.brains import _LESSON_CAP
    n = {"i": 0}

    def complete(prompt, image):
        n["i"] += 1
        return f"MOVE: a\nLESSON: lesson {n['i']}"

    brain = LLMButtonBrain("a", complete_fn=complete)
    total = _LESSON_CAP + 5
    for _ in range(total):
        brain.decide(_obs(), [], {})
    assert len(brain.lessons) == _LESSON_CAP                      # capped
    assert brain.lessons[-1] == f"lesson {total}"                 # most-recent kept
    assert brain.lessons[0] == f"lesson {total - _LESSON_CAP + 1}"  # oldest evicted


def test_llm_brain_lesson_direction_words_dont_leak_as_buttons():
    # MOVE line empty/garbled -> fallback scan must NOT pull 'down' out of the LESSON/THINK prose.
    reply = "THINK: I should go down later\nMOVE: \nLESSON: always go down at the ledge"
    brain = LLMButtonBrain("a", complete_fn=lambda prompt, image: reply)
    call = brain.decide(_obs(), [], {})
    assert call.tool == "press_button" and call.args["button"] == "a"   # safe default, not 'down'
    assert brain.lesson == "always go down at the ledge"


def test_llm_brain_injects_missed_text_transcript_into_prompt():
    prompts: list[str] = []

    def complete(prompt, image):
        prompts.append(prompt)
        return "MOVE: a"

    brain = LLMButtonBrain("a", complete_fn=complete)
    brain.decide(_obs(), [], {"transcript": "PROF OAK: take this POKeMON"})
    assert "since your last decision" in prompts[0]
    assert "PROF OAK: take this POKeMON" in prompts[0]


def test_llm_brain_regrounds_belief_when_screen_text_present():
    # belief-update (feature #4): a wake carrying decoded on-screen text gets a 'trust the screen'
    # nudge so a fresh observation can overturn a stale belief (the run-#3 Bulbasaur/Squirtle confab).
    prompts: list[str] = []

    def complete(prompt, image):
        prompts.append(prompt)
        return "MOVE: a"

    brain = LLMButtonBrain("a", complete_fn=complete)
    obs = Observation(data={"screen_path": "", "screen_text": "ASH received a SQUIRTLE!"},
                      text="state", agent_id="a", t=0.0)
    brain.decide(obs, [], {})
    assert "TRUST THE SCREEN" in prompts[0]


def test_llm_brain_no_regrounding_without_screen_text():
    # No decoded text -> no nudge (keeps plain overworld wakes lean; cost-conscious).
    prompts: list[str] = []

    def complete(prompt, image):
        prompts.append(prompt)
        return "MOVE: a"

    LLMButtonBrain("a", complete_fn=complete).decide(_obs(), [], {})
    assert "TRUST THE SCREEN" not in prompts[0]


def test_llm_brain_no_regrounding_on_whitespace_only_screen_text():
    # Whitespace-only screen_text must NOT trigger the nudge (guarded by .strip()) — a blank textbox
    # shouldn't bloat every wake.
    prompts: list[str] = []

    def complete(prompt, image):
        prompts.append(prompt)
        return "MOVE: a"

    obs = Observation(data={"screen_path": "", "screen_text": "   "}, text="s", agent_id="a", t=0.0)
    LLMButtonBrain("a", complete_fn=complete).decide(obs, [], {})
    assert "TRUST THE SCREEN" not in prompts[0]


def test_llm_brain_text_only_mode_announces_no_image():
    # --no-vision: no image is sent, so the prompt must tell the model not to expect a screenshot
    # (run #9 wasted turns asking for the missing image) and the belief nudge must NOT reference an image.
    prompts: list[str] = []

    def complete(prompt, image):
        prompts.append(prompt)
        assert image is None          # text-only: no image path passed to the backend
        return "MOVE: a"

    obs = Observation(data={"screen_path": "f.png", "screen_text": "CHARMANDER used SCRATCH!"},
                      text="state", agent_id="a", t=0.0)
    LLMButtonBrain("a", complete_fn=complete, use_vision=False).decide(obs, [], {})
    p = prompts[0]
    assert "TEXT-ONLY" in p
    assert "the image and on-screen text" not in p    # nudge must not reference the (absent) image
    assert "on-screen text shows" in p                # text-only nudge wording instead


def test_llm_brain_vision_mode_has_no_text_only_banner():
    prompts: list[str] = []

    def complete(prompt, image):
        prompts.append(prompt)
        return "MOVE: a"

    LLMButtonBrain("a", complete_fn=complete, use_vision=True).decide(_obs(), [], {})
    assert "TEXT-ONLY MODE" not in prompts[0]


def test_llm_brain_regrounding_coexists_with_transcript_and_lessons():
    # The nudge is APPENDED, not substituted: a wake carrying a transcript + a prior lesson + screen_text
    # must surface all three. Guards against a refactor that overwrites feedback instead of extending it.
    prompts: list[str] = []

    def complete(prompt, image):
        prompts.append(prompt)
        return "MOVE: a\nLESSON: ledges drop south" if len(prompts) == 1 else "MOVE: a"

    brain = LLMButtonBrain("a", complete_fn=complete)
    brain.decide(_obs(), [], {})                       # seed a lesson into the per-run buffer
    obs = Observation(data={"screen_path": "", "screen_text": "ASH got a SQUIRTLE"},
                      text="s", agent_id="a", t=0.0)
    brain.decide(obs, [], {"transcript": "PROF OAK: hello"})
    p = prompts[1]
    assert "TRUST THE SCREEN" in p                      # the nudge
    assert "PROF OAK: hello" in p                       # the transcript
    assert "ledges drop south" in p                     # the re-injected lesson


def test_llm_brain_ignores_unfilled_lesson_template():
    reply = "MOVE: up\nLESSON: <one short lesson>"
    brain = LLMButtonBrain("a", complete_fn=lambda prompt, image: reply)
    brain.decide(_obs(), [], {})
    assert brain.lesson is None and brain.lessons == []


def test_llm_brain_lesson_with_colon_preserved():
    reply = "MOVE: up\nLESSON: at the fork take the left:north path"
    brain = LLMButtonBrain("a", complete_fn=lambda prompt, image: reply)
    brain.decide(_obs(), [], {})
    assert brain.lesson == "at the fork take the left:north path"


def test_llm_brain_empty_lesson_line_ignored():
    brain = LLMButtonBrain("a", complete_fn=lambda prompt, image: "MOVE: up\nLESSON:    ")
    brain.decide(_obs(), [], {})
    assert brain.lesson is None and brain.lessons == []


def test_llm_brain_non_consecutive_duplicate_lesson_not_readded():
    # A, B, then A again -> the buffer must not hold A twice (dedup is whole-buffer, not just last).
    seq = iter(["MOVE: a\nLESSON: alpha", "MOVE: a\nLESSON: beta", "MOVE: a\nLESSON: ALPHA"])
    brain = LLMButtonBrain("a", complete_fn=lambda prompt, image: next(seq))
    for _ in range(3):
        brain.decide(_obs(), [], {})
    assert brain.lessons == ["alpha", "beta"]   # case-insensitive dedup; 'ALPHA' not re-added


def test_llm_brain_empty_move_line_defaults_to_a_not_prose():
    # MOVE empty + an UNTAGGED prose line with a direction word -> must NOT leak 'down' as a button.
    reply = "THINK: blocked\nMOVE: \nthe only exit i see is down the stairs"
    brain = LLMButtonBrain("a", complete_fn=lambda prompt, image: reply)
    call = brain.decide(_obs(), [], {})
    assert call.tool == "press_button" and call.args["button"] == "a"


def test_llm_brain_move_line_truncates_concatenated_directive():
    # MOVE and a directive concatenated on one line must not add spurious presses from the prose.
    reply = "MOVE: down LESSON: go down again for the item"
    brain = LLMButtonBrain("a", complete_fn=lambda prompt, image: reply)
    call = brain.decide(_obs(), [], {})
    assert call.tool == "press_button" and call.args["button"] == "down"   # one 'down', not two


def test_llm_brain_resets_goto_and_lesson_on_model_failure():
    # A failed model call must not leave the prior turn's destination/lesson looking current.
    calls = {"n": 0}

    def complete(prompt, image):
        calls["n"] += 1
        if calls["n"] == 1:
            return "MOVE: up\nGOTO: 3 4\nLESSON: remember the ledge"
        raise RuntimeError("backend down")

    brain = LLMButtonBrain("a", complete_fn=complete)
    brain.decide(_obs(), [], {})
    assert brain.goto == [3, 4] and brain.lesson == "remember the ledge"
    brain.decide(_obs(), [], {})              # this call raises inside complete()
    assert brain.goto is None and brain.lesson is None   # not stale
    assert brain.lessons == ["remember the ledge"]       # buffer keeps the earlier lesson


# -- S3 beta: owns_memory retires the harness LESSON buffer (aria owns within-run memory) ----------

def test_owns_memory_defaults_false():
    assert LLMButtonBrain("a").owns_memory is False            # every existing caller unaffected


def test_owns_memory_true_suppresses_harness_lesson_buffer():
    prompts: list[str] = []

    def complete(p, i):
        prompts.append(p)
        return "THINK: x\nMOVE: a\nLESSON: door is locked"

    brain = LLMButtonBrain("a", owns_memory=True, complete_fn=complete)
    brain.decide(_obs(), [], {})
    brain.decide(_obs(), [], {})
    assert brain.lessons == []                                 # parsed for display but NOT stored
    assert "LESSONS you recorded earlier THIS run" not in prompts[1]   # not re-injected (aria owns it)


def test_owns_memory_false_keeps_harness_lesson_buffer():
    # the memoryless path (ollama/default/injected) is byte-for-byte the pre-S3 behaviour
    prompts: list[str] = []

    def complete(p, i):
        prompts.append(p)
        return "THINK: x\nMOVE: a\nLESSON: door is locked"

    brain = LLMButtonBrain("a", owns_memory=False, complete_fn=complete)
    brain.decide(_obs(), [], {})
    assert brain.lessons == ["door is locked"]                 # stored
    brain.decide(_obs(), [], {})
    assert "LESSONS you recorded earlier THIS run (apply them):" in prompts[1] and "door is locked" in prompts[1]


def test_aria_lesson_tag_does_not_corrupt_parsing_or_buffer():
    # An aria-style <lesson> tag (in production aria strips it server-side) must NOT be mistaken for a
    # harness LESSON: line, nor leak buttons into the move.
    reply = "THINK: walk\nMOVE: down down\n<lesson>water beats fire</lesson>"
    brain = LLMButtonBrain("a", owns_memory=True, complete_fn=lambda p, i: reply)
    call = brain.decide(_obs(), [], {})
    assert call.args["buttons"] == ["down", "down"]            # buttons intact
    assert brain.lesson is None and brain.lessons == []        # <lesson> tag != harness LESSON:


# -- S2 constitution-first: deliver the system prompt as a system-role message ------------

class _FakeResp:
    def __init__(self, content="THINK: x\nMOVE: a", usage=None):
        self._content = content
        self._usage = usage or {"prompt_tokens": 10, "completion_tokens": 2}
    def raise_for_status(self):
        pass
    def json(self):
        return {"choices": [{"message": {"content": self._content}}], "usage": self._usage}


def test_openai_complete_sends_system_as_separate_message(monkeypatch):
    # S2: the constitution rides a SYSTEM-role message; the user turn must NOT re-embed it (so a
    # constitution-aware brain caches it once instead of replaying it every wake).
    from core.brains import _openai_complete
    captured = {}
    monkeypatch.setattr("requests.post",
                        lambda url, json=None, headers=None, timeout=None: captured.update(payload=json)
                        or _FakeResp())
    complete = _openai_complete("m", "http://x", api_key="k", system="SYSTEM-CONSTITUTION")
    text, usage = complete("USER-CONTENT", None)
    msgs = captured["payload"]["messages"]
    assert msgs[0] == {"role": "system", "content": "SYSTEM-CONSTITUTION"}
    assert msgs[1]["role"] == "user"
    user_text = msgs[1]["content"][0]["text"]
    assert "USER-CONTENT" in user_text and "SYSTEM-CONSTITUTION" not in user_text   # not duplicated
    assert text.startswith("THINK") and usage["prompt_tokens"] == 10                # usage still returned


def test_openai_complete_omits_system_message_when_none(monkeypatch):
    from core.brains import _openai_complete
    captured = {}
    monkeypatch.setattr("requests.post",
                        lambda url, json=None, headers=None, timeout=None: captured.update(payload=json)
                        or _FakeResp())
    _openai_complete("m", "http://x")("USER", None)            # no system
    msgs = captured["payload"]["messages"]
    assert [m["role"] for m in msgs] == ["user"]               # only the user turn


def test_aria_backend_brain_keeps_constitution_out_of_the_user_turn(monkeypatch):
    # End-to-end through decide(): backend=aria delivers self.system as a system message; the user
    # prompt body carries the per-turn content but NOT the constitution.
    captured = {}
    monkeypatch.setattr("requests.post",
                        lambda url, json=None, headers=None, timeout=None: captured.update(payload=json)
                        or _FakeResp())
    brain = LLMButtonBrain("a", backend="aria", api_key="k", system="MY-CONSTITUTION", use_vision=False)
    assert brain._delivers_system is True
    brain.decide(_obs(), [], {})
    msgs = captured["payload"]["messages"]
    assert any(m["role"] == "system" and m["content"] == "MY-CONSTITUTION" for m in msgs)
    user_text = next(m for m in msgs if m["role"] == "user")["content"][0]["text"]
    assert "MY-CONSTITUTION" not in user_text                  # constitution not stapled into the user turn


def test_default_system_stays_inline_without_an_explicit_constitution():
    # Review MEDIUM: a plain openai/llamacpp brain with NO explicit system keeps _DEFAULT_SYSTEM inline
    # (wire format unchanged) — only an explicitly-provided constitution rides a system-role message.
    assert LLMButtonBrain("a", backend="openai")._delivers_system is False
    assert LLMButtonBrain("a", backend="openai", system="X")._delivers_system is True
    assert LLMButtonBrain("a", backend="aria", api_key="k", system="X")._delivers_system is True


def test_injected_complete_fn_keeps_system_inline_for_backward_compat():
    # An injected complete_fn (tests / custom backends) has no system-role channel, so self.system stays
    # inline in the prompt exactly as before S2 (no silent behaviour change).
    prompts: list[str] = []
    brain = LLMButtonBrain("a", system="INLINE-SYS",
                           complete_fn=lambda p, i: prompts.append(p) or "MOVE: a")
    assert brain._delivers_system is False
    brain.decide(_obs(), [], {})
    assert "INLINE-SYS" in prompts[0]                          # still prepended for injected/ollama paths


# -- S1 cost-breaker: token metering + spend estimate --------------------------

def test_estimate_cost_basic_cached_and_created():
    from core.brains import _estimate_cost, HAIKU_45_PRICING as P
    assert _estimate_cost({}, P) == 0.0
    # all-uncached: 1000 in @ $1/MTok + 100 out @ $5/MTok
    assert _estimate_cost({"prompt_tokens": 1000, "completion_tokens": 100}, P) == pytest.approx(0.0015)
    # 800 of the 1000 prompt tokens were a cache READ (@ $0.10/MTok); 200 billed at the input rate
    cached = {"prompt_tokens": 1000, "completion_tokens": 100,
              "prompt_tokens_details": {"cached_tokens": 800}}
    assert _estimate_cost(cached, P) == pytest.approx(0.00078)
    # cache-CREATION tokens (litellm key) bill at the write rate and are excluded from the remainder
    created = {"prompt_tokens": 1000, "cache_creation_input_tokens": 400, "completion_tokens": 0}
    assert _estimate_cost(created, P) == pytest.approx(600 * 1e-6 + 400 * 1.25e-6)


def test_llm_brain_meters_tokens_and_cost_from_usage_tuple():
    # The OpenAI/aria complete_fn returns (text, usage); the brain records + accumulates it.
    usage = {"prompt_tokens": 1000, "completion_tokens": 100}
    brain = LLMButtonBrain("a", complete_fn=lambda p, i: ("THINK: x\nMOVE: a", usage))
    brain.decide(_obs(), [], {})
    assert brain.last_prompt_tokens == 1000
    assert brain.total_prompt_tokens == 1000 and brain.total_completion_tokens == 100
    assert brain.total_cost_usd == pytest.approx(0.0015)


def test_llm_brain_cost_meters_accumulate_across_wakes():
    usage = {"prompt_tokens": 200, "completion_tokens": 10}
    brain = LLMButtonBrain("a", complete_fn=lambda p, i: ("THINK: x\nMOVE: a", usage))
    brain.decide(_obs(), [], {})
    brain.decide(_obs(), [], {})
    assert brain.total_prompt_tokens == 400 and brain.total_completion_tokens == 20
    assert brain.last_prompt_tokens == 200                       # most-recent wake, not the sum
    assert brain.total_cost_usd == pytest.approx(2 * (200e-6 + 10 * 5e-6))


def test_llm_brain_string_complete_fn_meters_nothing():
    # A bare-string complete_fn (Ollama / gateworld / test stubs) must still work and meter zero.
    brain = LLMButtonBrain("a", complete_fn=lambda p, i: "THINK: x\nMOVE: up")
    call = brain.decide(_obs(), [], {})
    assert call.args["button"] == "up"                          # behaviour unchanged
    assert brain.last_usage == {} and brain.last_prompt_tokens == 0
    assert brain.total_cost_usd == 0.0


def test_llm_brain_meters_usage_even_on_error_as_content_reply():
    # aria echoes a backend error as a 200 with usage attached; meter the tokens but still count the error.
    err = "litellm.BadRequestError: AnthropicException - credit balance is too low"
    brain = LLMButtonBrain("a", complete_fn=lambda p, i: (err, {"prompt_tokens": 300, "completion_tokens": 5}))
    brain.decide(_obs(), [], {})
    assert brain.consec_api_errors == 1                         # still flagged as an error (not parsed as a move)
    assert brain.last_prompt_tokens == 300 and brain.total_cost_usd > 0   # but the spend was metered


def test_llm_brain_custom_pricing_is_respected():
    # Brain is model-agnostic (ROADMAP): a different pricing dict bills differently.
    brain = LLMButtonBrain("a", pricing={"in": 2e-6, "out": 0.0, "cache_read": 0.0, "cache_write": 0.0},
                           complete_fn=lambda p, i: ("MOVE: a", {"prompt_tokens": 100, "completion_tokens": 50}))
    brain.decide(_obs(), [], {})
    assert brain.total_cost_usd == pytest.approx(100 * 2e-6)    # output billed at 0 here


def test_hybrid_forwards_cost_and_token_meters_from_fallback():
    from core.brains import ExploreBrain, HybridBrain
    llm = LLMButtonBrain("a", complete_fn=lambda p, i: ("THINK: x\nMOVE: a",
                                                        {"prompt_tokens": 500, "completion_tokens": 10}))
    hb = HybridBrain(ExploreBrain("a"), llm)
    assert hb.total_cost_usd == 0.0 and hb.last_prompt_tokens == 0   # nothing metered yet
    llm.decide(_obs(), [], {})                                       # one wake populates the fallback's meters
    assert hb.last_prompt_tokens == 500 and hb.total_prompt_tokens == 500
    assert hb.total_completion_tokens == 10
    assert hb.total_cost_usd == pytest.approx(500e-6 + 10 * 5e-6)


def test_llm_brain_counts_wakes_for_the_wake_watchdog():
    # `--brain llm` uses a BARE LLMButtonBrain (no HybridBrain), and the driver's wake-watchdog reads
    # brain.woke — so each decide() must count, or the guard is advertised-but-inert (review HIGH finding).
    brain = LLMButtonBrain("a", complete_fn=lambda p, i: "MOVE: a")
    assert brain.woke == 0
    brain.decide(_obs(), [], {})
    brain.decide(_obs(), [], {})
    assert brain.woke == 2


def test_llm_brain_clears_prompt_meter_on_call_failure():
    # An exception (no usage) must not leave a stale last_prompt_tokens that the per-wake cap reads.
    replies = iter([("MOVE: a", {"prompt_tokens": 31000, "completion_tokens": 0})])

    def complete(p, i):
        try:
            return next(replies)
        except StopIteration:
            raise ConnectionError("aria unreachable")

    brain = LLMButtonBrain("a", complete_fn=complete)
    brain.decide(_obs(), [], {})
    assert brain.last_prompt_tokens == 31000
    brain.decide(_obs(), [], {})              # raises -> meter must reset, not stay at 31000
    assert brain.last_prompt_tokens == 0 and brain.last_usage == {}


def test_hybrid_meters_cost_through_a_real_wake():
    # Exercise the path the drivers use: overworld + a stuck autopilot -> HybridBrain wakes the LLM,
    # which meters the usage; the wrapper's forwarded meters must reflect it.
    from core.brains import HybridBrain

    class _NullAutopilot:           # always "stuck" -> forces a wake
        agent_id = "a"
        last_thought = ""
        def decide(self, obs, tools, context):
            return None

    llm = LLMButtonBrain("a", complete_fn=lambda p, i: ("THINK: x\nMOVE: a",
                                                        {"prompt_tokens": 400, "completion_tokens": 20}))
    hb = HybridBrain(_NullAutopilot(), llm)
    hb.decide(_obs(), [], {})
    assert hb.woke == 1
    assert hb.last_prompt_tokens == 400 and hb.total_prompt_tokens == 400
    assert hb.total_cost_usd == pytest.approx(400e-6 + 20 * 5e-6)
