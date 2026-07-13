"""Fail-closed Codex JSONL isolation/accounting audit for Gate 0."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path


SERVER = "gate0_world"
TOOLS = {
    "red": ["observe", "explore", "goto", "remember", "press_button", "press_sequence", "wait"],
    "miniwob": ["observe", "read_region", "whats_changed", "click", "type_text",
                "press_key", "reset_episode"],
}
TOKEN_FIELDS = ("input_tokens", "cached_input_tokens", "output_tokens", "reasoning_output_tokens")
_HASH_RE = re.compile(r"[0-9a-f]{64}")
_MODEL_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]+")
_VERSION_RE = re.compile(r"codex(?:-cli)?\s+[A-Za-z0-9][A-Za-z0-9.+-]*")


def tool_schema_sha256(arm: str) -> str:
    payload = json.dumps({"server": SERVER, "tools": TOOLS[arm]},
                         sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(payload).hexdigest()


def _receipt_failures(receipt: object, arm: str) -> list[str]:
    if not isinstance(receipt, dict):
        return ["receipt_not_object"]
    failures = []
    if receipt.get("schema_version") != 1:
        failures.append("receipt_schema")
    if receipt.get("arm") != arm:
        failures.append("receipt_arm")
    if receipt.get("auth_method") != "chatgpt":
        failures.append("auth_not_chatgpt")
    model = receipt.get("model")
    if not isinstance(model, str) or not _MODEL_RE.fullmatch(model):
        failures.append("model_unavailable")
    version = receipt.get("codex_version")
    if not isinstance(version, str) or not _VERSION_RE.fullmatch(version):
        failures.append("version_unavailable")
    codex_path = receipt.get("codex_path")
    if not isinstance(codex_path, str) or not codex_path.strip():
        failures.append("codex_path")
    executable_hash = receipt.get("codex_executable_sha256")
    if not isinstance(executable_hash, str) or not _HASH_RE.fullmatch(executable_hash):
        failures.append("codex_executable_hash")
    if receipt.get("mcp_servers") != [SERVER]:
        failures.append("mcp_server_inventory")
    if receipt.get("mcp_tools") != TOOLS[arm]:
        failures.append("mcp_tool_inventory")
    config_hash = receipt.get("config_sha256")
    if not isinstance(config_hash, str) or not _HASH_RE.fullmatch(config_hash):
        failures.append("config_hash")
    brain_config_hash = receipt.get("brain_config_sha256")
    if not isinstance(brain_config_hash, str) or not _HASH_RE.fullmatch(brain_config_hash):
        failures.append("brain_config_hash")
    task_hash = receipt.get("task_sha256")
    if not isinstance(task_hash, str) or not _HASH_RE.fullmatch(task_hash):
        failures.append("task_hash")
    if receipt.get("tool_schema_sha256") != tool_schema_sha256(arm):
        failures.append("tool_schema_hash")
    return failures


def _mcp_identity(item: dict) -> tuple[object, object]:
    server = item.get("server", item.get("server_name"))
    tool = item.get("tool", item.get("tool_name"))
    return server, tool


def audit(transcript_path: Path, receipt_path: Path, expected_arm: str) -> dict:
    failures: list[str] = []
    accounting_failures: list[str] = []
    run_failures: list[str] = []
    usage = {field: 0 for field in TOKEN_FIELDS}
    usage_events = 0

    if expected_arm not in TOOLS:
        failures.append("unknown_expected_arm")
    else:
        try:
            receipt = json.loads(Path(receipt_path).read_text(encoding="utf-8"))
        except Exception:
            receipt = None
            failures.append("malformed_receipt")
        if receipt is not None:
            failures.extend(_receipt_failures(receipt, expected_arm))

    try:
        lines = Path(transcript_path).read_text(encoding="utf-8").splitlines()
    except Exception:
        lines = []
        failures.append("transcript_unreadable")
    if not lines:
        failures.append("transcript_empty")

    allowed_tools = set(TOOLS.get(expected_arm, ()))
    for line_number, line in enumerate(lines, 1):
        try:
            event = json.loads(line)
        except Exception:
            failures.append(f"malformed_jsonl:{line_number}")
            continue
        if not isinstance(event, dict) or not isinstance(event.get("type"), str):
            failures.append(f"malformed_event:{line_number}")
            continue
        event_type = event["type"]
        if event_type == "thread.started" or event_type == "turn.started":
            continue
        if event_type == "turn.completed":
            raw_usage = event.get("usage")
            if not isinstance(raw_usage, dict):
                accounting_failures.append(f"missing_usage:{line_number}")
                continue
            values = []
            for field in TOKEN_FIELDS:
                value = raw_usage.get(field)
                if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                    accounting_failures.append(f"invalid_usage:{line_number}:{field}")
                    break
                values.append(value)
            else:
                usage_events += 1
                for field, value in zip(TOKEN_FIELDS, values):
                    usage[field] += value
            continue
        if event_type == "turn.failed" or event_type == "error":
            run_failures.append(f"run_event:{line_number}:{event_type}")
            continue
        if event_type.startswith("item."):
            item = event.get("item")
            if not isinstance(item, dict) or not isinstance(item.get("type"), str):
                failures.append(f"malformed_item:{line_number}")
                continue
            item_type = item["type"]
            if item_type in {"reasoning", "agent_message"}:
                continue
            if item_type == "mcp_tool_call":
                server, tool = _mcp_identity(item)
                if server != SERVER:
                    failures.append(f"non_target_mcp:{line_number}")
                elif tool not in allowed_tools:
                    failures.append(f"non_allowlisted_tool:{line_number}")
                continue
            failures.append(f"forbidden_item:{line_number}:{item_type}")
            continue
        failures.append(f"unknown_event:{line_number}:{event_type}")

    if usage_events == 0:
        accounting_failures.append("no_observable_token_usage")

    if failures:
        overall = "NO_LEAK"
        no_leak = "NO_LEAK"
    elif run_failures:
        overall = "NO_GO_RUN_FAILED"
        no_leak = "PASS"
    elif accounting_failures:
        overall = "NO_GO_INSUFFICIENT_ACCOUNTING"
        no_leak = "PASS"
    else:
        overall = "NO_GO_INSUFFICIENT_WAKES"
        no_leak = "PASS"
    return {
        "schema_version": 1,
        "arm": expected_arm,
        "no_leak": no_leak,
        "overall": overall,
        "wakes": None,
        "wake_accounting": "INSUFFICIENT_WAKES",
        "token_usage": usage,
        "token_usage_events": usage_events,
        "failures": failures,
        "accounting_failures": accounting_failures,
        "run_failures": run_failures,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("transcript", type=Path)
    parser.add_argument("receipt", type=Path)
    parser.add_argument("--arm", required=True, choices=sorted(TOOLS))
    args = parser.parse_args()
    summary = audit(args.transcript, args.receipt, args.arm)
    print(json.dumps(summary, sort_keys=True))
    return 0 if summary["overall"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
