from __future__ import annotations

import hashlib
import json
import sys

import pytest

import tools.check_gate0_codex as checker
from tools.check_gate0_codex import SERVER, TOOLS, audit


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _fixture(tmp_path, arm="miniwob", events=None):
    artifacts = tmp_path / arm
    (artifacts / "launch" / ".codex").mkdir(parents=True)
    codex = artifacts / "codex.exe"
    files = {
        codex: b"synthetic-codex",
        artifacts / "brain-config.toml": b"model='gpt-5.4'\n",
        artifacts / "launch" / "TASK.md": b"synthetic task\n",
        artifacts / "launch" / ".codex" / "config.toml": b"synthetic config\n",
        artifacts / "codex-mcp-list.json": b'[{"name":"gate0_world"}]\n',
        artifacts / "mcp-tools.json": (json.dumps([{"name": name} for name in TOOLS[arm]]) + "\n").encode(),
    }
    for path, data in files.items():
        path.write_bytes(data)
    hashes = {path: _sha(data) for path, data in files.items()}
    receipt = {
        "schema_version": 2, "arm": arm,
        "readiness": "NO_GO_INSUFFICIENT_WAKES", "paid_execution_enabled": False,
        "auth_method": "chatgpt", "planned_model": "gpt-5.4",
        "codex_version": "codex-cli 1.2.3", "codex_path": str(codex),
        "codex_executable_sha256": hashes[codex],
        "critical_config_transport": "explicit_cli_overrides",
        "mcp_servers_observed": [SERVER], "mcp_tools_observed": TOOLS[arm],
        "brain_config_sha256": hashes[artifacts / "brain-config.toml"],
        "task_sha256": hashes[artifacts / "launch" / "TASK.md"],
        "config_sha256": hashes[artifacts / "launch" / ".codex" / "config.toml"],
        "codex_mcp_list_sha256": hashes[artifacts / "codex-mcp-list.json"],
        "tool_schema_sha256": hashes[artifacts / "mcp-tools.json"],
        "world_image_tag": "miniwob-world" if arm == "miniwob" else "gb-mcp-world",
        "world_image_id": "sha256:" + "1" * 64,
        "host_code_sha256": {"/app/world_mcp.py": "2" * 64,
                             "/app/core/miniwob_world.py": "3" * 64},
        "image_code_sha256": {"/app/world_mcp.py": "2" * 64,
                              "/app/core/miniwob_world.py": "3" * 64},
    }
    receipt_path = artifacts / "handshake-receipt.json"
    expected_path = artifacts / "expected-pins.json"
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
    expected_path.write_text(json.dumps(receipt), encoding="utf-8")
    transcript = artifacts / "transcript.jsonl"
    if events is None:
        events = [
            {"type": "thread.started"},
            {"type": "item.completed", "item": {
                "type": "mcp_tool_call", "server": SERVER, "tool": "observe"}},
            {"type": "turn.completed", "usage": {
                "input_tokens": 10, "cached_input_tokens": 3,
                "output_tokens": 4, "reasoning_output_tokens": 2}},
        ]
    transcript.write_text("".join(json.dumps(e) + "\n" for e in events), encoding="utf-8")
    return transcript, receipt_path, expected_path, artifacts, receipt


def _audit(run):
    transcript, receipt, expected, artifacts, _ = run
    return audit(transcript, receipt, expected, artifacts, artifacts.name)


def test_exact_observed_pins_are_still_no_go_until_wakes_exist(tmp_path):
    # A short-lived PR #125 briefly made this PASS with wakes = usage_events (one wake per
    # turn.completed event). PR #126's real codex exec --json capture falsified that: a single
    # turn.completed bundles >=2 real model decisions (cumulative usage for the whole turn), and
    # no per-decision boundary event exists in Codex's JSONL schema to count instead -- see
    # reports/2026-07-21-gate0-wake-grounding.md. Reverted: even a fully clean transcript with a
    # valid turn.completed event must still report the fail-closed hardcode, not a fabricated count.
    result = _audit(_fixture(tmp_path))
    assert result["no_leak"] == "PASS"
    assert result["audit_overall"] == "NO_GO_INSUFFICIENT_WAKES"
    assert result["wakes"] is None
    assert result["wake_accounting"] == "INSUFFICIENT_WAKES"
    assert result["token_usage"] == {"input_tokens": 10, "cached_input_tokens": 3,
                                     "output_tokens": 4, "reasoning_output_tokens": 2}


def test_primitive_action_events_counts_every_allowlisted_tool_call(tmp_path):
    # primitive_action_events counts actual allowlisted mcp_tool_call items, not model decisions --
    # it has no analogous undercount problem to wakes (reports/2026-07-21-gate0-wake-grounding.md)
    # and stays a sound, real count even though wakes itself stays fail-closed.
    usage = {"input_tokens": 1, "cached_input_tokens": 0, "output_tokens": 1, "reasoning_output_tokens": 0}
    events = [{"type": "thread.started"}]
    for _ in range(5):
        events.append({"type": "item.completed", "item": {
            "type": "mcp_tool_call", "server": SERVER, "tool": "observe"}})
        events.append({"type": "turn.completed", "usage": usage})
    result = _audit(_fixture(tmp_path, events=events))
    assert result["audit_overall"] == "NO_GO_INSUFFICIENT_WAKES"
    assert result["wakes"] is None
    assert result["wake_accounting"] == "INSUFFICIENT_WAKES"
    assert result["primitive_action_events"] == 5


def test_missing_transcript_data_still_reports_insufficient_wakes_honestly(tmp_path):
    # The free-handshake case (no codex exec ever ran, so no transcript exists) must not fabricate
    # a wake count just because the receipt/pins/artifacts are otherwise clean.
    result = _audit(_fixture(tmp_path, events=[]))
    assert result["audit_overall"] == "NO_LEAK"
    assert "transcript_empty" in result["leak_failures"]
    assert result["wakes"] is None
    assert result["wake_accounting"] == "INSUFFICIENT_WAKES"


def test_invalid_usage_accounting_failure_keeps_wakes_insufficient(tmp_path):
    run = _fixture(tmp_path, events=[
        {"type": "thread.started"},
        {"type": "turn.completed", "usage": {"input_tokens": -1, "cached_input_tokens": 0,
                                              "output_tokens": 0, "reasoning_output_tokens": 0}},
    ])
    result = _audit(run)
    assert result["audit_overall"] == "NO_GO_INSUFFICIENT_ACCOUNTING"
    assert result["wakes"] is None
    assert result["wake_accounting"] == "INSUFFICIENT_WAKES"


@pytest.mark.parametrize("item", [
    {"type": "command_execution"},
    {"type": "mcp_tool_call", "server": "other", "tool": "observe"},
    {"type": "mcp_tool_call", "server": SERVER, "tool": "shell"},
])
def test_nonworld_surface_fails_no_leak(tmp_path, item):
    run = _fixture(tmp_path, events=[
        {"type": "thread.started"}, {"type": "item.completed", "item": item},
        {"type": "turn.completed", "usage": {"input_tokens": 1, "cached_input_tokens": 0,
                                                "output_tokens": 1, "reasoning_output_tokens": 0}},
    ])
    result = _audit(run)
    assert result["audit_overall"] == "NO_LEAK"
    assert result["leak_failures"]


def test_expected_pin_drift_fails_constancy(tmp_path):
    run = _fixture(tmp_path)
    expected = json.loads(run[2].read_text(encoding="utf-8"))
    expected["planned_model"] = "different"
    run[2].write_text(json.dumps(expected), encoding="utf-8")
    result = _audit(run)
    assert result["audit_overall"] == "CONSTANCY_BREACH"
    assert "pin_mismatch:planned_model" in result["constancy_failures"]


def test_artifact_mutation_fails_constancy(tmp_path):
    run = _fixture(tmp_path)
    (run[3] / "launch" / "TASK.md").write_text("changed", encoding="utf-8")
    assert "artifact_hash_mismatch:task_sha256" in _audit(run)["constancy_failures"]


def test_artifact_inventory_cannot_be_self_declared(tmp_path):
    run = _fixture(tmp_path)
    path = run[3] / "codex-mcp-list.json"
    path.write_text('[{"name":"gate0_world"},{"name":"extra"}]\n', encoding="utf-8")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    for receipt_path in (run[1], run[2]):
        data = json.loads(receipt_path.read_text(encoding="utf-8"))
        data["codex_mcp_list_sha256"] = digest
        receipt_path.write_text(json.dumps(data), encoding="utf-8")
    assert "artifact_inventory:mcp_servers" in _audit(run)["constancy_failures"]


def test_stale_image_code_fails_constancy(tmp_path):
    run = _fixture(tmp_path)
    receipt = json.loads(run[1].read_text(encoding="utf-8"))
    receipt["image_code_sha256"]["/app/world_mcp.py"] = "4" * 64
    run[1].write_text(json.dumps(receipt), encoding="utf-8")
    run[2].write_text(json.dumps(receipt), encoding="utf-8")
    result = _audit(run)
    assert "stale_world_image" in result["constancy_failures"]


def test_peer_receipts_prove_only_common_brain_constancy(tmp_path):
    mini = _fixture(tmp_path / "mini", "miniwob")
    red = _fixture(tmp_path / "red", "red")
    mini_receipt = json.loads(mini[1].read_text(encoding="utf-8"))
    red_receipt = json.loads(red[1].read_text(encoding="utf-8"))
    for field in checker.CONSTANCY_FIELDS:
        red_receipt[field] = mini_receipt[field]
    red[1].write_text(json.dumps(red_receipt), encoding="utf-8")
    result = audit(mini[0], mini[1], mini[2], mini[3], "miniwob", red[1])
    assert result["peer_constancy"] == "PASS"
    red_receipt["planned_model"] = "different"
    red[1].write_text(json.dumps(red_receipt), encoding="utf-8")
    result = audit(mini[0], mini[1], mini[2], mini[3], "miniwob", red[1])
    assert result["audit_overall"] == "CONSTANCY_BREACH"
    assert "peer_mismatch:planned_model" in result["constancy_failures"]


def test_run_failure_precedes_missing_accounting(tmp_path):
    run = _fixture(tmp_path, events=[{"type": "thread.started"}, {"type": "error"}])
    assert _audit(run)["audit_overall"] == "NO_GO_RUN_FAILED"


def test_main_exits_zero_for_a_clean_synthetic_transcript(monkeypatch, capsys, tmp_path):
    # Exit 0 == the four fields eval/score_gate0.py::score() consumes are clean. It is NOT a Gate 0
    # PASS: audit_overall still reports the permanently fail-closed NO_GO_INSUFFICIENT_WAKES
    # (reports/2026-07-21-gate0-wake-grounding.md), which is not what the exit code tracks.
    run = _fixture(tmp_path)
    monkeypatch.setattr(sys, "argv", ["check_gate0_codex.py", str(run[0]), str(run[1]),
                                      str(run[2]), str(run[3]), "--arm", "miniwob"])
    assert checker.main() == 0
    result = json.loads(capsys.readouterr().out)
    assert result["audit_overall"] == "NO_GO_INSUFFICIENT_WAKES"
    assert result["wake_accounting"] == "INSUFFICIENT_WAKES"


def test_main_exits_nonzero_when_transcript_lacks_wake_data(monkeypatch, capsys, tmp_path):
    run = _fixture(tmp_path, events=[])
    monkeypatch.setattr(sys, "argv", ["check_gate0_codex.py", str(run[0]), str(run[1]),
                                      str(run[2]), str(run[3]), "--arm", "miniwob"])
    assert checker.main() == 1
    result = json.loads(capsys.readouterr().out)
    assert result["audit_overall"] == "NO_LEAK"
    assert result["wake_accounting"] == "INSUFFICIENT_WAKES"


def test_audit_never_emits_a_bare_overall_key(tmp_path):
    # Locks the 2026-07-28 rename so the trap cannot be reintroduced: a key literally named
    # "overall" here reads as eval/score_gate0.py::score()'s verdict field and gets misquoted as
    # the Gate 0 result (it is not -- see tools/check_gate0_codex.py's module docstring).
    result = _audit(_fixture(tmp_path))
    assert "overall" not in result
    assert result["audit_overall"] == "NO_GO_INSUFFICIENT_WAKES"
    # Pin the whole emitted shape, not just the absent key: a future field named "overall",
    # "verdict", or "result" would reintroduce the same collision, and schema_version must move
    # if this dict's shape ever does again.
    assert set(result) == {
        "schema_version", "arm", "no_leak", "audit_overall", "wakes", "wake_accounting",
        "peer_constancy", "token_usage", "token_usage_events", "primitive_action_events",
        "leak_failures", "constancy_failures", "accounting_failures", "run_failures"}
    assert result["schema_version"] == 3
