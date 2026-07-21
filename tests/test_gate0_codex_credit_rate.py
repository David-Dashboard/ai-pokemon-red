import json
import subprocess
import sys
from pathlib import Path

import pytest

from tools.gate0_codex_credit_rate import (
    CreditRateNotPinned,
    codex_event_to_credit_event,
    load_credit_rate_pin,
    token_usage_delta_to_credits,
)

ROOT = Path(__file__).parents[1]
VALID_PIN = {
    "model": "gpt-5.6-sol",
    "rate_source": "unit test fixture -- not a real price",
    "credits_per_usd": 25,
    "usd_per_input_token": 0.000002,
    "usd_per_cached_input_token": 0.0000005,
    "usd_per_output_token": 0.00001,
}


def _write_pin(tmp_path, overrides=None, missing=None):
    pin = dict(VALID_PIN)
    if overrides:
        pin.update(overrides)
    if missing:
        for key in missing:
            pin.pop(key, None)
    path = tmp_path / "rate_pin.json"
    path.write_text(json.dumps(pin), encoding="utf-8")
    return path


def test_load_credit_rate_pin_missing_file(tmp_path):
    with pytest.raises(CreditRateNotPinned, match="rate_pin_missing"):
        load_credit_rate_pin(tmp_path / "absent.json", "gpt-5.6-sol")


def test_load_credit_rate_pin_malformed_json(tmp_path):
    path = tmp_path / "rate_pin.json"
    path.write_text("not json", encoding="utf-8")
    with pytest.raises(CreditRateNotPinned, match="rate_pin_unreadable"):
        load_credit_rate_pin(path, "gpt-5.6-sol")


@pytest.mark.parametrize("missing_field", [
    "model", "rate_source", "credits_per_usd", "usd_per_input_token",
    "usd_per_cached_input_token", "usd_per_output_token",
])
def test_load_credit_rate_pin_fails_closed_on_missing_field(tmp_path, missing_field):
    path = _write_pin(tmp_path, missing=[missing_field])
    with pytest.raises(CreditRateNotPinned, match="rate_pin_missing_fields"):
        load_credit_rate_pin(path, "gpt-5.6-sol")


def test_load_credit_rate_pin_fails_closed_on_empty_rate_source(tmp_path):
    path = _write_pin(tmp_path, overrides={"rate_source": "   "})
    with pytest.raises(CreditRateNotPinned, match="rate_pin_empty_rate_source"):
        load_credit_rate_pin(path, "gpt-5.6-sol")


@pytest.mark.parametrize("bad_value", [-1, "x", True, float("nan")])
def test_load_credit_rate_pin_fails_closed_on_invalid_numeric_field(tmp_path, bad_value):
    path = _write_pin(tmp_path, overrides={"usd_per_output_token": bad_value})
    with pytest.raises(CreditRateNotPinned, match="rate_pin_invalid_field"):
        load_credit_rate_pin(path, "gpt-5.6-sol")


def test_load_credit_rate_pin_fails_closed_on_nonpositive_credits_per_usd(tmp_path):
    path = _write_pin(tmp_path, overrides={"credits_per_usd": 0})
    with pytest.raises(CreditRateNotPinned, match="nonpositive_credits_per_usd"):
        load_credit_rate_pin(path, "gpt-5.6-sol")


def test_load_credit_rate_pin_refuses_the_reviewers_implausibly_low_poc(tmp_path):
    # PR #122 review Finding 3 / coordinator M3: 1e-12 $/token (a plausible units mistake, e.g.
    # quoting a per-1M-token price as a per-token price) previously passed validation and made the
    # 250-credit ceiling need ~2.5 billion turns to reach -- effectively unreachable.
    path = _write_pin(tmp_path, overrides={"usd_per_output_token": 1e-12})
    with pytest.raises(CreditRateNotPinned, match="rate_pin_implausible_field:usd_per_output_token"):
        load_credit_rate_pin(path, "gpt-5.6-sol")


def test_load_credit_rate_pin_refuses_the_reviewers_implausibly_high_poc(tmp_path):
    # A rate 10x+ too high makes a single trivial turn alone trip instantly -- safe but wastes the
    # one pre-registered attempt on a units error rather than a real run.
    path = _write_pin(tmp_path, overrides={"usd_per_output_token": 1.0})
    with pytest.raises(CreditRateNotPinned, match="rate_pin_implausible_field:usd_per_output_token"):
        load_credit_rate_pin(path, "gpt-5.6-sol")


def test_load_credit_rate_pin_allows_an_exact_zero_token_rate(tmp_path):
    # A genuine "this token class is free" tier is a legitimate price, not a units bug -- only a
    # NONZERO-but-astronomically-tiny value is the error signature the plausibility band guards.
    path = _write_pin(tmp_path, overrides={"usd_per_cached_input_token": 0.0})
    pin = load_credit_rate_pin(path, "gpt-5.6-sol")
    assert pin["usd_per_cached_input_token"] == 0.0


@pytest.mark.parametrize("boundary_value", [1e-8, 1e-2])
def test_load_credit_rate_pin_accepts_the_plausibility_band_boundaries(tmp_path, boundary_value):
    path = _write_pin(tmp_path, overrides={"usd_per_output_token": boundary_value})
    load_credit_rate_pin(path, "gpt-5.6-sol")


@pytest.mark.parametrize("bad_credits_per_usd", [1e-6, 0.5, 1e6, 1e9])
def test_load_credit_rate_pin_refuses_an_implausible_credits_per_usd(tmp_path, bad_credits_per_usd):
    path = _write_pin(tmp_path, overrides={"credits_per_usd": bad_credits_per_usd})
    with pytest.raises(CreditRateNotPinned, match="rate_pin_implausible_field:credits_per_usd"):
        load_credit_rate_pin(path, "gpt-5.6-sol")


def test_load_credit_rate_pin_refuses_a_model_mismatch(tmp_path):
    path = _write_pin(tmp_path)
    with pytest.raises(CreditRateNotPinned, match="rate_pin_model_mismatch"):
        load_credit_rate_pin(path, "some-other-model")


def test_load_credit_rate_pin_accepts_a_valid_pin(tmp_path):
    path = _write_pin(tmp_path)
    pin = load_credit_rate_pin(path, "gpt-5.6-sol")
    assert pin["model"] == "gpt-5.6-sol"


def test_token_usage_delta_to_credits_prices_uncached_cached_and_output_separately():
    usage = {"input_tokens": 100, "cached_input_tokens": 40, "output_tokens": 10,
              "reasoning_output_tokens": 5}
    rate_pin = {"usd_per_input_token": 2.0, "usd_per_cached_input_token": 1.0,
                "usd_per_output_token": 3.0, "credits_per_usd": 10}
    # uncached input = 60 tokens * 2.0 = 120; cached = 40 * 1.0 = 40; output = 10 * 3.0 = 30
    # usd = 190; credits = 1900
    assert token_usage_delta_to_credits(usage, rate_pin) == pytest.approx(1900.0)


def test_token_usage_delta_to_credits_fails_closed_on_missing_field():
    usage = {"input_tokens": 1, "cached_input_tokens": 0, "output_tokens": 1}
    with pytest.raises(ValueError, match="invalid_token_field"):
        token_usage_delta_to_credits(usage, VALID_PIN)


def test_token_usage_delta_to_credits_fails_closed_on_cached_exceeding_input():
    usage = {"input_tokens": 5, "cached_input_tokens": 10, "output_tokens": 1,
              "reasoning_output_tokens": 0}
    with pytest.raises(ValueError, match="cached_input_tokens_exceeds_input_tokens"):
        token_usage_delta_to_credits(usage, VALID_PIN)


def test_codex_event_to_credit_event_reads_the_bare_token_count_shape():
    # The exact shape empirically observed in pre-existing (already-paid) local Codex session
    # rollouts, 2026-07-21 -- see tools/gate0_codex_credit_rate.py's module docstring.
    event = {
        "type": "token_count",
        "info": {"last_token_usage": {"input_tokens": 100, "cached_input_tokens": 0,
                                        "output_tokens": 10, "reasoning_output_tokens": 0}},
    }
    result = codex_event_to_credit_event(event, VALID_PIN)
    assert result["raw_type"] == "token_count"
    assert result["normalized_credits"] > 0


def test_codex_event_to_credit_event_reads_the_msg_wrapped_shape():
    event = {"msg": {"type": "token_count",
                       "info": {"last_token_usage": {"input_tokens": 1, "cached_input_tokens": 0,
                                                        "output_tokens": 1, "reasoning_output_tokens": 0}}}}
    result = codex_event_to_credit_event(event, VALID_PIN)
    assert result["raw_type"] == "token_count"


def test_codex_event_to_credit_event_passes_through_non_token_count_events_at_zero_credit():
    event = {"type": "agent_message_delta", "delta": "hello"}
    result = codex_event_to_credit_event(event, VALID_PIN)
    assert result == {"normalized_credits": 0.0, "raw_type": "agent_message_delta"}


def test_codex_event_to_credit_event_refuses_a_malformed_token_count_event():
    event = {"type": "token_count", "info": {}}
    with pytest.raises(ValueError, match="missing_last_token_usage"):
        codex_event_to_credit_event(event, VALID_PIN)


def test_validate_cli_exits_zero_for_a_valid_pin(tmp_path):
    path = _write_pin(tmp_path)
    result = subprocess.run(
        [sys.executable, "-m", "tools.gate0_codex_credit_rate", "validate",
         "--rate-pin", str(path), "--model", "gpt-5.6-sol"],
        cwd=ROOT, capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {"ok": True}


def test_validate_cli_exits_nonzero_and_fails_closed_for_an_absent_pin(tmp_path):
    result = subprocess.run(
        [sys.executable, "-m", "tools.gate0_codex_credit_rate", "validate",
         "--rate-pin", str(tmp_path / "absent.json"), "--model", "gpt-5.6-sol"],
        cwd=ROOT, capture_output=True, text=True,
    )
    assert result.returncode != 0
    assert json.loads(result.stderr)["ok"] is False
