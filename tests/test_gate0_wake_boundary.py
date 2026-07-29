import hashlib
import json

from tools.gate0_wake_boundary import _DECISION_COUNT, dry_run_synthetic


def test_dry_run_synthetic_stays_fail_closed_even_for_a_maximally_clean_transcript():
    # reports/2026-07-21-gate0-wake-grounding.md: there is no sound per-decision wake observable
    # today, so this artifact must never claim status="PASS" -- not even against a synthetic
    # transcript with zero leak/constancy/run/accounting failures (the hardest case: nothing else
    # is wrong, so this is exactly the input that would let a regression slip a number through).
    artifact = dry_run_synthetic()
    assert artifact["schema_version"] == 1
    assert artifact["kind"] == "exact_wake_boundary"
    assert artifact["status"] == "FAIL"
    assert artifact["fail_closed_regression_guard_holds"] is True
    assert artifact["audit_result"]["audit_overall"] == "NO_GO_INSUFFICIENT_WAKES"
    assert artifact["audit_result"]["wake_accounting"] == "INSUFFICIENT_WAKES"
    assert artifact["audit_result"]["wakes"] is None
    assert artifact["audit_result"]["primitive_action_events"] == _DECISION_COUNT
    stream_bytes = ("\n".join(json.dumps(e) for e in artifact["synthetic_transcript_events"]) + "\n").encode("utf-8")
    assert artifact["synthetic_transcript_sha256"] == hashlib.sha256(stream_bytes).hexdigest()


def test_dry_run_synthetic_is_deterministic_across_invocations():
    # No wall clock, temp path, or PID may leak into the artifact -- otherwise its sha256 (the
    # thing eval/score_gate0.py's source pins hash-pin) would be non-reproducible.
    first = dry_run_synthetic()
    second = dry_run_synthetic()
    assert first == second


def test_main_writes_artifact_and_exits_zero_when_fail_closed_holds(tmp_path):
    import sys

    from tools import gate0_wake_boundary as module

    out = tmp_path / "wake_boundary.json"
    argv = ["gate0_wake_boundary.py", "dry-run-synthetic", "--out", str(out)]
    old_argv = sys.argv
    sys.argv = argv
    try:
        assert module.main() == 0
    finally:
        sys.argv = old_argv
    written = json.loads(out.read_text(encoding="utf-8"))
    # Status is permanently "FAIL" (no PASS path exists); exit 0 tracks the regression guard, not
    # this field -- eval/score_gate0.py is the one that reads `status` and correctly refuses it.
    assert written["status"] == "FAIL"
    assert written["kind"] == "exact_wake_boundary"
    assert written["fail_closed_regression_guard_holds"] is True
