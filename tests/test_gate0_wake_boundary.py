import hashlib
import json

from tools.gate0_wake_boundary import _EXPECTED_WAKES, dry_run_synthetic


def test_dry_run_synthetic_produces_an_earned_pass_not_a_self_declared_one():
    artifact = dry_run_synthetic()
    assert artifact["schema_version"] == 1
    assert artifact["kind"] == "exact_wake_boundary"
    assert artifact["status"] == "PASS"
    # The tightening this exists for: PASS must be backed by a real audit() run against a
    # known-count transcript, not asserted.
    assert artifact["audit_result"]["overall"] == "PASS"
    assert artifact["audit_result"]["wake_accounting"] == "PASS"
    assert artifact["audit_result"]["wakes"] == _EXPECTED_WAKES
    assert artifact["audit_result"]["primitive_action_events"] == _EXPECTED_WAKES
    stream_bytes = ("\n".join(json.dumps(e) for e in artifact["synthetic_transcript_events"]) + "\n").encode("utf-8")
    assert artifact["synthetic_transcript_sha256"] == hashlib.sha256(stream_bytes).hexdigest()


def test_dry_run_synthetic_is_deterministic_across_invocations():
    # No wall clock, temp path, or PID may leak into the artifact -- otherwise its sha256 (the
    # thing eval/score_gate0.py's source pins hash-pin) would be non-reproducible.
    first = dry_run_synthetic()
    second = dry_run_synthetic()
    assert first == second


def test_main_writes_artifact_and_exits_zero(tmp_path):
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
    assert written["status"] == "PASS"
    assert written["kind"] == "exact_wake_boundary"
