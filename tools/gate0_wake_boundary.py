"""Gate 0 exact-wake-boundary mechanism demo (reports/2026-07-21-gate0-wake-grounding.md, PR #126).

This module originally tried to PROVE the wake-counting mechanism in
tools/check_gate0_codex.py::audit() correct against a fixed synthetic transcript. A real
`codex exec --json` capture (PR #126) falsified the wake definition it would have proven: a single
turn.completed event bundles >=2 real model decisions (its usage is cumulative for the whole turn),
and no other event in Codex's JSONL schema marks a per-model-call boundary -- so there is no sound
mechanism to demonstrate yet. audit() reverted to its fail-closed hardcode (wakes=None,
wake_accounting="INSUFFICIENT_WAKES") and this module's job changed to match: it now demonstrates
that fail-closed guarantee HOLDS, even against a fully clean, leak/constancy/run/accounting-free
synthetic transcript -- i.e. wake accounting is not silently regressing back to "count something
and call it PASS" the moment nothing else is wrong.

`status` in the returned/written artifact can therefore never be "PASS" today -- eval/score_gate0.py's
_verify_sources() treats any wake_boundary status other than exactly "PASS" as a
`wake_boundary_artifact` source failure (by design: this keeps Gate 0 from ever scoring on a wake
count nobody can vouch for). `fail_closed_regression_guard_holds` is the field that actually says
whether THIS demo passed: True means audit() correctly stayed fail-closed as documented; False would
mean audit() silently started reporting wakes again -- a regression -- and demands investigation.

Deterministic by construction: the embedded synthetic transcript is a fixed Python literal (hashed
into the artifact, like tools/gate0_credit_breaker.py's synthetic_credit_stream), and nothing time-
or machine-dependent (wall clock, temp paths, PIDs) is written into the artifact itself. The scratch
files audit() needs to read (receipt/expected-pins/artifacts_dir) are materialized into a throwaway
temp directory purely to satisfy audit()'s file-based API; their paths never appear in the artifact.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import tempfile
from pathlib import Path

from tools.check_gate0_codex import SERVER, TOOLS, audit


_ARM = "miniwob"
# 6 decisions (turn.completed events), one mcp_tool_call each -- small and fixed. Under the
# reverted, fail-closed audit(), the exact count no longer matters for `wakes` (always None), but
# primitive_action_events (a real, sound count -- see check_gate0_codex.py's comment) is still
# expected to come back exactly 6.
_DECISION_COUNT = 6
_USAGE = {"input_tokens": 12, "cached_input_tokens": 4, "output_tokens": 5, "reasoning_output_tokens": 1}


def _synthetic_transcript_events() -> list[dict]:
    events = [{"type": "thread.started"}]
    for _ in range(_DECISION_COUNT):
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
    constancy/run/accounting failures. That is the hardest case for the fail-closed guarantee:
    nothing else is wrong, so if wake accounting were ever going to slip back to reporting a
    number, this is exactly the input that would let it."""
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
    shaped exact_wake_boundary artifact. `status` is always "FAIL" today -- no exact wake boundary
    is provable given Codex's current JSONL schema (see module docstring) -- but
    `fail_closed_regression_guard_holds` reports whether audit() actually kept its documented
    fail-closed promise (wakes=None/wake_accounting="INSUFFICIENT_WAKES"/overall != "PASS") even
    for this maximally-clean transcript. That flag going False would mean the fail-closed guarantee
    silently broke -- the actual regression this demo exists to catch."""
    events = _synthetic_transcript_events()
    stream_bytes = ("\n".join(json.dumps(e) for e in events) + "\n").encode("utf-8")
    stream_sha256 = hashlib.sha256(stream_bytes).hexdigest()

    with tempfile.TemporaryDirectory() as tmp:
        transcript_path, receipt_path, expected_path, artifacts_dir = _build_fixture(Path(tmp))
        result = audit(transcript_path, receipt_path, expected_path, artifacts_dir, _ARM)

    fail_closed_holds = (result["overall"] == "NO_GO_INSUFFICIENT_WAKES"
                         and result["wake_accounting"] == "INSUFFICIENT_WAKES"
                         and result["wakes"] is None
                         and result["primitive_action_events"] == _DECISION_COUNT)
    return {
        "schema_version": 1,
        "kind": "exact_wake_boundary",
        # Intentionally never "PASS": eval/score_gate0.py::_verify_sources() requires exactly
        # status == "PASS" to accept this artifact, so any other string (this one included)
        # correctly keeps Gate 0 from scoring on a wake count nobody can vouch for.
        "status": "FAIL",
        "blocked_reason": (
            "reports/2026-07-21-gate0-wake-grounding.md: a real codex exec --json transcript "
            "showed a single turn.completed bundles >=2 real model decisions (cumulative usage "
            "for the whole turn), and no per-decision boundary event exists in Codex's JSONL "
            "schema to count instead. tools/check_gate0_codex.py::audit() reverted its "
            "wakes = usage_events definition (which undercounted by >=2x) back to the fail-closed "
            "wakes=None / wake_accounting=INSUFFICIENT_WAKES hardcode. This artifact cannot report "
            "status=PASS until Codex ships a documented per-model-call boundary event."
        ),
        "fail_closed_regression_guard_holds": fail_closed_holds,
        "mode": "dry_run_synthetic",
        "produced_by": "tools/gate0_wake_boundary.py:dry_run_synthetic",
        "synthetic_transcript_events": events,
        "synthetic_transcript_sha256": stream_sha256,
        "audit_result": result,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    dry = sub.add_parser("dry-run-synthetic",
                          help="Run audit() against a built-in synthetic transcript and write the "
                               "exact_wake_boundary artifact (always status=FAIL today; see "
                               "fail_closed_regression_guard_holds for whether the demo itself "
                               "confirms fail-closed behavior).")
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
        print(json.dumps({
            "status": artifact["status"],
            "fail_closed_regression_guard_holds": artifact["fail_closed_regression_guard_holds"],
            "out": str(args.out),
        }, sort_keys=True))
        # Exit code tracks whether the fail-closed GUARANTEE holds, not artifact["status"] (which
        # is permanently "FAIL" by design -- see module docstring). 0 = confirmed fail-closed;
        # nonzero = regression, investigate immediately.
        return 0 if artifact["fail_closed_regression_guard_holds"] else 1
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
