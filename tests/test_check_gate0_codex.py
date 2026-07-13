from __future__ import annotations

import json
import sys

import pytest

import tools.check_gate0_codex as checker
from tools.check_gate0_codex import SERVER, TOOLS, audit, tool_schema_sha256


def _receipt(arm="miniwob"):
    return {"schema_version": 1, "arm": arm, "auth_method": "chatgpt",
            "model": "gpt-5.4", "codex_version": "codex-cli 1.2.3",
            "codex_path": "C:/tools/codex.exe", "codex_executable_sha256": "d" * 64,
            "mcp_servers": [SERVER], "mcp_tools": TOOLS[arm],
            "brain_config_sha256": "b" * 64, "task_sha256": "c" * 64,
            "config_sha256": "a" * 64, "tool_schema_sha256": tool_schema_sha256(arm)}


def _events(item=None, usages=None):
    events = [{"type": "thread.started", "thread_id": "synthetic"},
              {"type": "turn.started"}]
    if item is not None:
        events.append({"type": "item.completed", "item": item})
    for usage in usages or [{"input_tokens": 10, "cached_input_tokens": 3,
                             "output_tokens": 4, "reasoning_output_tokens": 2}]:
        events.append({"type": "turn.completed", "usage": usage})
    return events


def _write_run(tmp_path, events, receipt=None):
    transcript = tmp_path / "transcript.jsonl"
    transcript.write_text("".join(json.dumps(event) + "\n" for event in events), encoding="utf-8")
    receipt_path = tmp_path / "receipt.json"
    receipt_path.write_text(json.dumps(_receipt() if receipt is None else receipt), encoding="utf-8")
    return transcript, receipt_path


def test_clean_target_mcp_is_no_leak_pass_but_wakes_insufficient(tmp_path):
    item = {"type": "mcp_tool_call", "server": SERVER, "tool": "observe"}
    usages = [{"input_tokens": 10, "cached_input_tokens": 3, "output_tokens": 4,
               "reasoning_output_tokens": 2},
              {"input_tokens": 20, "cached_input_tokens": 7, "output_tokens": 8,
               "reasoning_output_tokens": 5}]
    transcript, receipt = _write_run(tmp_path, _events(item, usages))
    result = audit(transcript, receipt, "miniwob")
    assert result["no_leak"] == "PASS"
    assert result["overall"] == "NO_GO_INSUFFICIENT_WAKES"
    assert result["wakes"] is None
    assert result["token_usage"] == {"input_tokens": 30, "cached_input_tokens": 10,
                                     "output_tokens": 12, "reasoning_output_tokens": 7}
    assert result["token_usage_events"] == 2


@pytest.mark.parametrize("item_type", [
    "command_execution", "file_change", "web_search", "tool_search", "connector_call", "unknown_tool",
])
def test_non_mcp_tool_item_classes_fail_no_leak(tmp_path, item_type):
    transcript, receipt = _write_run(tmp_path, _events({"type": item_type}))
    result = audit(transcript, receipt, "miniwob")
    assert result["no_leak"] == "NO_LEAK"
    assert result["overall"] == "NO_LEAK"
    assert any("forbidden_item" in reason for reason in result["failures"])


@pytest.mark.parametrize("item", [
    {"type": "mcp_tool_call", "server": "connector", "tool": "observe"},
    {"type": "mcp_tool_call", "server": SERVER, "tool": "shell"},
    {"type": "mcp_tool_call", "server": SERVER},
])
def test_other_server_or_tool_fails_no_leak(tmp_path, item):
    transcript, receipt = _write_run(tmp_path, _events(item))
    assert audit(transcript, receipt, "miniwob")["no_leak"] == "NO_LEAK"


@pytest.mark.parametrize(("field", "value", "reason"), [
    ("auth_method", "api", "auth_not_chatgpt"),
    ("model", "", "model_unavailable"),
    ("codex_version", "", "version_unavailable"),
    ("codex_path", "", "codex_path"),
    ("codex_executable_sha256", "bad", "codex_executable_hash"),
    ("mcp_servers", [SERVER, "extra"], "mcp_server_inventory"),
    ("mcp_tools", TOOLS["miniwob"] + ["shell"], "mcp_tool_inventory"),
    ("config_sha256", "bad", "config_hash"),
    ("brain_config_sha256", "bad", "brain_config_hash"),
    ("task_sha256", "bad", "task_hash"),
    ("tool_schema_sha256", "b" * 64, "tool_schema_hash"),
])
def test_bad_receipt_fails_closed(tmp_path, field, value, reason):
    receipt_data = _receipt()
    receipt_data[field] = value
    transcript, receipt = _write_run(tmp_path, _events(), receipt_data)
    result = audit(transcript, receipt, "miniwob")
    assert result["no_leak"] == "NO_LEAK"
    assert reason in result["failures"]


def test_wrong_arm_inventory_fails_closed(tmp_path):
    transcript, receipt = _write_run(tmp_path, _events(), _receipt("red"))
    result = audit(transcript, receipt, "miniwob")
    assert result["no_leak"] == "NO_LEAK"
    assert "receipt_arm" in result["failures"]


def test_malformed_jsonl_fails_closed(tmp_path):
    transcript, receipt = _write_run(tmp_path, _events())
    transcript.write_text('{"type":"thread.started"}\nnot-json\n', encoding="utf-8")
    result = audit(transcript, receipt, "miniwob")
    assert result["no_leak"] == "NO_LEAK"
    assert any(reason.startswith("malformed_jsonl") for reason in result["failures"])


def test_reasoning_and_agent_message_are_allowed(tmp_path):
    events = _events()
    events.insert(2, {"type": "item.completed", "item": {"type": "reasoning", "text": "private"}})
    events.insert(3, {"type": "item.completed", "item": {"type": "agent_message", "text": "done"}})
    transcript, receipt = _write_run(tmp_path, events)
    assert audit(transcript, receipt, "miniwob")["no_leak"] == "PASS"


def test_missing_usage_is_no_go_accounting_without_inventing_wakes(tmp_path):
    transcript, receipt = _write_run(tmp_path, [{"type": "thread.started"},
                                                {"type": "turn.completed"}])
    result = audit(transcript, receipt, "miniwob")
    assert result["no_leak"] == "PASS"
    assert result["overall"] == "NO_GO_INSUFFICIENT_ACCOUNTING"
    assert result["wakes"] is None


def test_run_failure_precedes_insufficient_accounting(tmp_path):
    transcript, receipt = _write_run(tmp_path, [
        {"type": "thread.started"},
        {"type": "error", "message": "synthetic"},
        {"type": "turn.completed"},
    ])
    result = audit(transcript, receipt, "miniwob")
    assert result["overall"] == "NO_GO_RUN_FAILED"
    assert result["run_failures"]
    assert result["accounting_failures"]


def test_no_leak_precedes_run_failure(tmp_path):
    transcript, receipt = _write_run(tmp_path, [
        {"type": "thread.started"},
        {"type": "item.completed", "item": {"type": "command_execution"}},
        {"type": "error", "message": "synthetic"},
        {"type": "turn.completed", "usage": {
            "input_tokens": 1, "cached_input_tokens": 0,
            "output_tokens": 1, "reasoning_output_tokens": 0,
        }},
    ])
    result = audit(transcript, receipt, "miniwob")
    assert result["overall"] == "NO_LEAK"
    assert result["failures"]
    assert result["run_failures"]


@pytest.mark.parametrize(("overall", "expected_exit"), [
    ("NO_LEAK", 1),
    ("NO_GO_RUN_FAILED", 1),
    ("NO_GO_INSUFFICIENT_ACCOUNTING", 1),
    ("NO_GO_INSUFFICIENT_WAKES", 1),
    ("PASS", 0),
])
def test_main_exits_zero_only_for_literal_pass(monkeypatch, capsys, overall, expected_exit):
    monkeypatch.setattr(sys, "argv", [
        "check_gate0_codex.py", "transcript.jsonl", "receipt.json", "--arm", "miniwob",
    ])
    monkeypatch.setattr(checker, "audit", lambda *_args: {"overall": overall})
    assert checker.main() == expected_exit
    assert json.loads(capsys.readouterr().out)["overall"] == overall
