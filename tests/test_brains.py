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
