import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parents[1]


def _write_pin(tmp_path, usd_per_output_token):
    path = tmp_path / "rate_pin.json"
    path.write_text(json.dumps({
        "model": "stub-model", "rate_source": "unit test fixture -- not a real price",
        "credits_per_usd": 1, "usd_per_input_token": 0.0, "usd_per_cached_input_token": 0.0,
        "usd_per_output_token": usd_per_output_token,
    }), encoding="utf-8")
    return path


def _token_count_line(output_tokens):
    return json.dumps({
        "type": "token_count",
        "info": {"last_token_usage": {"input_tokens": 0, "cached_input_tokens": 0,
                                        "output_tokens": output_tokens, "reasoning_output_tokens": 0}},
    })


def _run(stdin_text, rate_pin, verdict_path, stall_timeout_s=5, model="stub-model"):
    # Invoked exactly as tools/run_gate0_codex.ps1's Invoke-BreakerSupervisedExec invokes it in
    # production: `python -m tools.gate0_credit_accountant` with cwd=repo root, so the module's
    # own `from tools.gate0_codex_credit_rate import ...` resolves without a sys.path hack.
    return subprocess.run(
        [sys.executable, "-m", "tools.gate0_credit_accountant", "--rate-pin", str(rate_pin),
         "--model", model, "--verdict-out", str(verdict_path), "--stall-timeout-s", str(stall_timeout_s)],
        input=stdin_text, capture_output=True, text=True, cwd=ROOT,
    )


def test_completes_cleanly_when_the_stream_never_trips(tmp_path):
    rate_pin = _write_pin(tmp_path, usd_per_output_token=0.001)
    verdict_path = tmp_path / "verdict.json"
    stdin_text = "\n".join(_token_count_line(1) for _ in range(3)) + "\n"
    result = _run(stdin_text, rate_pin, verdict_path)
    assert result.returncode == 0, result.stderr
    verdict = json.loads(verdict_path.read_text(encoding="utf-8"))
    assert verdict["result"] == "COMPLETED"
    assert verdict["trip"]["tripped"] is False


def test_exits_2_and_writes_tripped_verdict_when_the_limit_is_crossed(tmp_path):
    # One event already exceeds the 250 default limit.
    rate_pin = _write_pin(tmp_path, usd_per_output_token=1000.0)
    verdict_path = tmp_path / "verdict.json"
    stdin_text = _token_count_line(1) + "\n" + _token_count_line(1) + "\n"
    result = _run(stdin_text, rate_pin, verdict_path)
    assert result.returncode == 2
    verdict = json.loads(verdict_path.read_text(encoding="utf-8"))
    assert verdict["result"] == "TRIPPED"
    assert verdict["events_seen"] == 1


def test_exits_2_and_writes_malformed_verdict_on_a_bad_line(tmp_path):
    rate_pin = _write_pin(tmp_path, usd_per_output_token=0.001)
    verdict_path = tmp_path / "verdict.json"
    stdin_text = "not json\n"
    result = _run(stdin_text, rate_pin, verdict_path)
    assert result.returncode == 2
    verdict = json.loads(verdict_path.read_text(encoding="utf-8"))
    assert verdict["result"] == "MALFORMED"
    assert "malformed_json_line" in verdict["error"]


def test_exits_3_and_refuses_before_reading_any_stream_when_the_rate_pin_is_absent(tmp_path):
    verdict_path = tmp_path / "verdict.json"
    result = _run(_token_count_line(1) + "\n", tmp_path / "absent.json", verdict_path)
    assert result.returncode == 3
    verdict = json.loads(verdict_path.read_text(encoding="utf-8"))
    assert verdict["result"] == "RATE_NOT_PINNED"


def test_pass_through_events_do_not_trip_the_breaker(tmp_path):
    rate_pin = _write_pin(tmp_path, usd_per_output_token=1000.0)
    verdict_path = tmp_path / "verdict.json"
    stdin_text = json.dumps({"type": "agent_message_delta", "delta": "hi"}) + "\n"
    result = _run(stdin_text, rate_pin, verdict_path)
    assert result.returncode == 0, result.stderr
    verdict = json.loads(verdict_path.read_text(encoding="utf-8"))
    assert verdict["result"] == "COMPLETED"
    assert verdict["trip"]["tripped"] is False
