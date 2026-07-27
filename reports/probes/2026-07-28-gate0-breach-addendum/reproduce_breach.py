"""$0 reproduction of the banked Gate-0 CONSTANCY_BREACH on both paid arms.

Pure function over already-banked artifacts: no paid run, no LLM call, no episode
re-execution, no docker. Calls the FROZEN tools/check_gate0_codex.py::audit() twice per arm:

  MODE A "raw"      -- expected_pins = the committed .appserver fixture verbatim.
                       This is what the launcher at commit c838355 (launcher_sha256
                       b21d3012..., the value both banked run-receipt.json files carry)
                       actually did in _finalize_real_run. It reproduces the banked verdict.
  MODE B "resolved" -- expected_pins = resolve_expected_pins(fixture, config_sha256=...,
                       codex_mcp_list_sha256=...) taken from THIS arm's own banked
                       handshake-receipt.json, i.e. what the launcher at commit 3c3f704
                       (landed 13 min after the miniwob arm finished) does today.

Run dirs are READ-ONLY here: nothing under runs/ is written, moved, or created. The
resolved fixture is materialised into a scratch dir outside the repo.
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

from tools.check_gate0_codex import audit  # noqa: E402
from tools.gate0_appserver_arm import resolve_expected_pins  # noqa: E402

ARMS = ("miniwob", "red")


def run_arm(arm: str, runs_root: Path, scratch: Path) -> dict:
    run_dir = runs_root / arm
    fixture = REPO / "eval" / "fixtures" / f"gate0_expected_pins_{arm}.appserver.json"
    transcript = run_dir / "transcript.jsonl"
    receipt_path = run_dir / "handshake-receipt.json"

    raw = audit(transcript, receipt_path, fixture, run_dir, arm)

    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    base = json.loads(fixture.read_text(encoding="utf-8"))
    resolved = resolve_expected_pins(
        base,
        config_sha256=receipt["config_sha256"],
        codex_mcp_list_sha256=receipt["codex_mcp_list_sha256"],
    )
    resolved_path = scratch / f"expected-pins.resolved.{arm}.json"
    resolved_path.write_text(json.dumps(resolved, indent=2) + "\n", encoding="utf-8")
    post = audit(transcript, receipt_path, resolved_path, run_dir, arm)

    # MODE C: what eval/score_gate0.py (the actual Gate-0 scorer) sees. Its audit paths are
    # hard-pinned in eval/fixtures/gate0_paid_source_pins.json:audit_paths to the NON-.appserver
    # exec-era fixtures, plus the peer receipt. Reproduced here to close the third failure the
    # paired-verdict report flagged but did not diagnose byte-level.
    exec_fixture = REPO / "eval" / "fixtures" / f"gate0_expected_pins_{arm}.json"
    peer = runs_root / ("miniwob" if arm == "red" else "red") / "handshake-receipt.json"
    scorer = audit(transcript, receipt_path, exec_fixture, run_dir, arm, peer)

    return {
        "arm": arm,
        "run_dir": str(run_dir),
        "banked_audit_overall": json.loads(
            (run_dir / "run-receipt.json").read_text(encoding="utf-8"))["audit_overall"],
        "expected_pins_resolved_json_present_in_run_dir": (
            run_dir / "expected-pins.resolved.json").exists(),
        "A_raw_fixture": {k: raw[k] for k in (
            "overall", "no_leak", "constancy_failures", "leak_failures",
            "accounting_failures", "run_failures")},
        "B_resolved_fixture": {k: post[k] for k in (
            "overall", "no_leak", "constancy_failures", "leak_failures",
            "accounting_failures", "run_failures")},
        "C_score_gate0_exec_fixture": {k: scorer[k] for k in (
            "overall", "no_leak", "peer_constancy", "constancy_failures", "leak_failures",
            "accounting_failures", "run_failures")},
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs-root", type=Path, required=True,
                        help="path to runs/gate0_paid (read-only)")
    args = parser.parse_args()
    with tempfile.TemporaryDirectory() as tmp:
        results = [run_arm(a, args.runs_root, Path(tmp)) for a in ARMS]
    print(json.dumps(results, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
