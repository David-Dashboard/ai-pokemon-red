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
    with pytest.raises(ValueError):
        LLMButtonBrain("a", backend="bogus")
