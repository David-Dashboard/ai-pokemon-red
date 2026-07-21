"""Gate 0 exact-wake-boundary mechanism proof (report 2026-07-21-gate0-readiness-final.md section 4).

Proves the wake-counting MECHANISM in tools/check_gate0_codex.py::audit() is correct against a
fixed, deterministic synthetic Codex transcript -- at $0, no paid run involved -- the same kind of
standalone detector-correctness proof tools/gate0_credit_breaker.py's dry_run_synthetic() already
provides for the live credit breaker (see that module's docstring). eval/score_gate0.py's
_verify_sources() reads this artifact's `status` field (must be "PASS") as one of the six named
source artifacts a scored gate needs, independent of any specific arm's real paid-run wakes --
those are cross-checked separately per-arm via audit()/agent_metrics.json.

Deterministic by construction: the embedded synthetic transcript is a fixed Python literal (hashed
into the artifact, like gate0_credit_breaker.py's synthetic_credit_stream), and nothing time- or
machine-dependent (wall clock, temp paths, PIDs) is written into the artifact itself -- only the
fixed events and the audit() result they produce. The scratch files audit() needs to read
(receipt/expected-pins/artifacts_dir) are materialized into a throwaway temp directory purely to
satisfy audit()'s file-based API; their paths never appear in the returned artifact.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import tempfile
from pathlib import Path

from tools.check_gate0_codex import SERVER, TOOLS, audit


_ARM = "miniwob"
# 6 decisions (turn.completed events), one mcp_tool_call each -- small, fixed, and easy to hand-
# verify: wakes must come back exactly 6, primitive_action_events exactly 6.
_EXPECTED_WAKES = 6
_USAGE = {"input_tokens": 12, "cached_input_tokens": 4, "output_tokens": 5, "reasoning_output_tokens": 1}


def _synthetic_transcript_events() -> list[dict]:
    events = [{"type": "thread.started"}]
    for _ in range(_EXPECTED_WAKES):
        events.append({"type": "item.completed", "item": {
            "type": "mcp_tool_call", "server": SERVER, "tool": "observe"}})
        events.append({"type": "turn.completed", "usage": dict(_USAGE)})
    return events


def _write(path: Path, data: bytes) -> str:
    path.write_bytes(data)
    return hashlib.sha256(data).hexdigest()


def _build_fixture(tmp_dir: Path) -> tuple[Path, Path, Path, Path]:
    """Materialize a self-consistent, clean receipt/expected-pins/artifacts_dir -- same shape as
    tests/test_check_gate0_codex.py's `_fixture()` helper -- so audit() reports zero leak/
    constancy/run failures. That is the only way to ever reach the wake-accounting branch."""
    artifacts = tmp_dir / _ARM
    (artifacts / "launch" / ".codex").mkdir(parents=True)
    codex = artifacts / "codex.exe"
    files = {
        codex: b"synthetic-codex",
        artifacts / "brain-config.toml": b"model='gpt-5.6-sol'\n",
        artifacts / "launch" / "TASK.md": b"synthetic task\n",
        artifacts / "launch" / ".codex" / "config.toml": b"synthetic config\n",
        artifacts / "codex-mcp-list.json": b'[{"name":"gate0_world"}]\n',
        artifacts / "mcp-tools.json": (json.dumps([{"name": name} for name in TOOLS[_ARM]]) + "\n").encode(),
    }
    hashes = {path: _write(path, data) for path, data in files.items()}
    receipt = {
        "schema_version": 2, "arm": _ARM,
        "readiness": "NO_GO_INSUFFICIENT_WAKES", "paid_execution_enabled": False,
        "auth_method": "chatgpt", "planned_model": "gpt-5.6-sol",
        "codex_version": "codex-cli 0.144.3", "codex_path": str(codex),
        "codex_executable_sha256": hashes[codex],
        "critical_config_transport": "explicit_cli_overrides",
        "mcp_servers_observed": [SERVER], "mcp_tools_observed": TOOLS[_ARM],
        "brain_config_sha256": hashes[artifacts / "brain-config.toml"],
        "task_sha256": hashes[artifacts / "launch" / "TASK.md"],
        "config_sha256": hashes[artifacts / "launch" / ".codex" / "config.toml"],
        "codex_mcp_list_sha256": hashes[artifacts / "codex-mcp-list.json"],
        "tool_schema_sha256": hashes[artifacts / "mcp-tools.json"],
        "world_image_tag": "miniwob-world",
        "world_image_id": "sha256:" + "0" * 64,
        "host_code_sha256": {"/app/world_mcp.py": "1" * 64, "/app/core/miniwob_world.py": "2" * 64},
        "image_code_sha256": {"/app/world_mcp.py": "1" * 64, "/app/core/miniwob_world.py": "2" * 64},
    }
    receipt_path = artifacts / "handshake-receipt.json"
    expected_path = artifacts / "expected-pins.json"
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
    expected_path.write_text(json.dumps(receipt), encoding="utf-8")
    transcript_path = artifacts / "transcript.jsonl"
    events = _synthetic_transcript_events()
    transcript_path.write_text("".join(json.dumps(e) + "\n" for e in events), encoding="utf-8")
    return transcript_path, receipt_path, expected_path, artifacts


def dry_run_synthetic() -> dict:
    """Run audit() against the fixed synthetic transcript above and build the eval/score_gate0.py-
    shaped exact_wake_boundary artifact. `status` is only ever "PASS" if audit() actually reported
    overall=PASS/wake_accounting=PASS AND the wake count matches the known-correct expected value
    -- earned by the mechanism, never hand-typed (mirrors gate0_credit_breaker.py's
    dry_run_synthetic() "earned_pass" discipline)."""
    events = _synthetic_transcript_events()
    stream_bytes = ("\n".join(json.dumps(e) for e in events) + "\n").encode("utf-8")
    stream_sha256 = hashlib.sha256(stream_bytes).hexdigest()

    with tempfile.TemporaryDirectory() as tmp:
        transcript_path, receipt_path, expected_path, artifacts_dir = _build_fixture(Path(tmp))
        result = audit(transcript_path, receipt_path, expected_path, artifacts_dir, _ARM)

    earned_pass = (result["overall"] == "PASS" and result["wake_accounting"] == "PASS"
                   and result["wakes"] == _EXPECTED_WAKES
                   and result["primitive_action_events"] == _EXPECTED_WAKES)
    return {
        "schema_version": 1,
        "kind": "exact_wake_boundary",
        "status": "PASS" if earned_pass else "FAIL",
        "wake_definition": (
            "One wake = one turn.completed transcript event carrying a valid usage object -- the "
            "same event tools/check_gate0_codex.py::audit() already counts as token_usage_events "
            "for token accounting. See reports/2026-07-21-gate0-readiness-final.md section 4."
        ),
        "mode": "dry_run_synthetic",
        "produced_by": "tools/gate0_wake_boundary.py:dry_run_synthetic",
        "expected_wakes": _EXPECTED_WAKES,
        "synthetic_transcript_events": events,
        "synthetic_transcript_sha256": stream_sha256,
        "audit_result": result,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    dry = sub.add_parser("dry-run-synthetic",
                          help="Run audit() against a built-in synthetic transcript and write the "
                               "exact_wake_boundary artifact.")
    dry.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "dry-run-synthetic":
        artifact = dry_run_synthetic()
        args.out.parent.mkdir(parents=True, exist_ok=True)
        # newline="\n" is load-bearing: default newline translation would write CRLF on Windows,
        # making the artifact's sha256 platform-dependent (same trap gate0_credit_breaker.py's
        # dry-run writer already avoids).
        args.out.write_text(json.dumps(artifact, indent=2, sort_keys=False) + "\n",
                            encoding="utf-8", newline="\n")
        print(json.dumps({"status": artifact["status"], "wakes": artifact["audit_result"]["wakes"],
                          "out": str(args.out)}, sort_keys=True))
        return 0 if artifact["status"] == "PASS" else 1
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
