"""Fail-closed Codex transcript audit against frozen, observed Gate 0 pins."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path


SERVER = "gate0_world"
# eval/score_gate0.py::MODES -- duplicated here (not imported) to keep this module free of any
# eval.* import, matching its existing zero-cross-package-import shape.
AGENT_METRICS_MODES = ("readiness_dev", "paid_gate0")
TOOLS = {
    "red": ["observe", "explore", "goto", "remember", "press_button", "press_sequence", "wait"],
    "miniwob": ["observe", "read_region", "whats_changed", "click", "type_text",
                "press_key", "reset_episode"],
}
TOKEN_FIELDS = ("input_tokens", "cached_input_tokens", "output_tokens", "reasoning_output_tokens")
PIN_FIELDS = (
    "arm", "readiness", "paid_execution_enabled", "auth_method", "planned_model",
    "codex_version", "codex_path", "codex_executable_sha256", "critical_config_transport",
    "mcp_servers_observed", "mcp_tools_observed", "brain_config_sha256", "task_sha256",
    "config_sha256", "codex_mcp_list_sha256", "tool_schema_sha256", "world_image_tag",
    "world_image_id", "host_code_sha256", "image_code_sha256",
)
CONSTANCY_FIELDS = (
    "readiness", "paid_execution_enabled", "auth_method", "planned_model", "codex_version",
    "codex_path", "codex_executable_sha256", "critical_config_transport", "brain_config_sha256",
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def _receipt_shape_failures(receipt: object, arm: str) -> list[str]:
    if not isinstance(receipt, dict):
        return ["receipt_not_object"]
    failures = []
    if receipt.get("schema_version") != 2:
        failures.append("receipt_schema")
    if receipt.get("arm") != arm:
        failures.append("receipt_arm")
    if receipt.get("readiness") != "NO_GO_INSUFFICIENT_WAKES":
        failures.append("readiness_not_fail_closed")
    if receipt.get("paid_execution_enabled") is not False:
        failures.append("paid_execution_not_disabled")
    if receipt.get("auth_method") != "chatgpt":
        failures.append("auth_not_chatgpt")
    if receipt.get("critical_config_transport") != "explicit_cli_overrides":
        failures.append("config_transport")
    if receipt.get("mcp_servers_observed") != [SERVER]:
        failures.append("observed_mcp_servers")
    if receipt.get("mcp_tools_observed") != TOOLS[arm]:
        failures.append("observed_mcp_tools")
    for field in ("planned_model", "codex_version", "codex_path"):
        if not isinstance(receipt.get(field), str) or not receipt[field].strip():
            failures.append(field)
    for field in ("codex_executable_sha256", "brain_config_sha256", "task_sha256",
                  "config_sha256", "codex_mcp_list_sha256", "tool_schema_sha256"):
        value = receipt.get(field)
        if not isinstance(value, str) or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
            failures.append(field)
    image_id = receipt.get("world_image_id")
    if (not isinstance(image_id, str) or not image_id.startswith("sha256:") or len(image_id) != 71
            or any(c not in "0123456789abcdef" for c in image_id[7:])):
        failures.append("world_image_id")
    expected_tag = "gb-mcp-world" if arm == "red" else "miniwob-world"
    if receipt.get("world_image_tag") != expected_tag:
        failures.append("world_image_tag")
    for field in ("host_code_sha256", "image_code_sha256"):
        value = receipt.get(field)
        if not isinstance(value, dict) or set(value) != {
                "/app/world_mcp.py", "/app/core/miniwob_world.py"}:
            failures.append(field)
        elif any(not isinstance(digest, str) or len(digest) != 64
                 or any(c not in "0123456789abcdef" for c in digest)
                 for digest in value.values()):
            failures.append(field)
    if (isinstance(receipt.get("host_code_sha256"), dict)
            and isinstance(receipt.get("image_code_sha256"), dict)
            and receipt["host_code_sha256"] != receipt["image_code_sha256"]):
        failures.append("stale_world_image")
    return failures


def _expected_failures(receipt: object, expected: object) -> list[str]:
    if not isinstance(receipt, dict) or not isinstance(expected, dict):
        return ["expected_pins_malformed"]
    failures = []
    if expected.get("schema_version") != 2:
        failures.append("expected_schema")
    for field in PIN_FIELDS:
        if field not in expected:
            failures.append(f"expected_missing:{field}")
        elif receipt.get(field) != expected[field]:
            failures.append(f"pin_mismatch:{field}")
    return failures


def _artifact_failures(receipt: object, artifacts_dir: Path, arm: str) -> list[str]:
    if not isinstance(receipt, dict):
        return ["artifacts_without_receipt"]
    paths = {
        "brain_config_sha256": artifacts_dir / "brain-config.toml",
        "task_sha256": artifacts_dir / "launch" / "TASK.md",
        "config_sha256": artifacts_dir / "launch" / ".codex" / "config.toml",
        "codex_mcp_list_sha256": artifacts_dir / "codex-mcp-list.json",
        "tool_schema_sha256": artifacts_dir / "mcp-tools.json",
    }
    failures = []
    for field, path in paths.items():
        try:
            observed = _sha256(path)
        except OSError:
            failures.append(f"artifact_missing:{field}")
            continue
        if observed != receipt.get(field):
            failures.append(f"artifact_hash_mismatch:{field}")
    try:
        mcp_list = _load_json(paths["codex_mcp_list_sha256"])
    except Exception:
        failures.append("artifact_malformed:codex_mcp_list_sha256")
    else:
        if (not isinstance(mcp_list, list) or len(mcp_list) != 1
                or not isinstance(mcp_list[0], dict) or mcp_list[0].get("name") != SERVER):
            failures.append("artifact_inventory:mcp_servers")
    try:
        tool_list = _load_json(paths["tool_schema_sha256"])
    except Exception:
        failures.append("artifact_malformed:tool_schema_sha256")
    else:
        names = [item.get("name") for item in tool_list] if isinstance(tool_list, list) and all(
            isinstance(item, dict) for item in tool_list) else None
        if names != TOOLS[arm]:
            failures.append("artifact_inventory:mcp_tools")
    try:
        executable_hash = _sha256(Path(receipt["codex_path"]))
    except (KeyError, OSError, TypeError):
        failures.append("artifact_missing:codex_executable_sha256")
    else:
        if executable_hash != receipt.get("codex_executable_sha256"):
            failures.append("artifact_hash_mismatch:codex_executable_sha256")
    return failures


def compare_constancy(receipt: object, peer: object) -> list[str]:
    if not isinstance(receipt, dict) or not isinstance(peer, dict):
        return ["peer_receipt_malformed"]
    failures = []
    if {receipt.get("arm"), peer.get("arm")} != {"red", "miniwob"}:
        failures.append("peer_arms")
    for field in CONSTANCY_FIELDS:
        if receipt.get(field) != peer.get(field):
            failures.append(f"peer_mismatch:{field}")
    return failures


def _mcp_identity(item: dict) -> tuple[object, object]:
    return item.get("server", item.get("server_name")), item.get("tool", item.get("tool_name"))


def audit(transcript_path: Path, receipt_path: Path, expected_path: Path,
          artifacts_dir: Path, expected_arm: str, peer_receipt_path: Path | None = None) -> dict:
    constancy_failures: list[str] = []
    leak_failures: list[str] = []
    accounting_failures: list[str] = []
    run_failures: list[str] = []
    usage = {field: 0 for field in TOKEN_FIELDS}
    usage_events = 0
    primitive_action_events = 0

    try:
        receipt = _load_json(Path(receipt_path))
    except Exception:
        receipt = None
        constancy_failures.append("malformed_receipt")
    try:
        expected = _load_json(Path(expected_path))
    except Exception:
        expected = None
        constancy_failures.append("malformed_expected_pins")
    if expected_arm not in TOOLS:
        constancy_failures.append("unknown_expected_arm")
    elif receipt is not None:
        constancy_failures.extend(_receipt_shape_failures(receipt, expected_arm))
        constancy_failures.extend(_expected_failures(receipt, expected))
        constancy_failures.extend(_artifact_failures(receipt, Path(artifacts_dir), expected_arm))
    if peer_receipt_path is not None and receipt is not None:
        try:
            peer = _load_json(Path(peer_receipt_path))
        except Exception:
            peer = None
        constancy_failures.extend(compare_constancy(receipt, peer))

    try:
        lines = Path(transcript_path).read_text(encoding="utf-8").splitlines()
    except Exception:
        lines = []
        leak_failures.append("transcript_unreadable")
    if not lines:
        leak_failures.append("transcript_empty")

    allowed_tools = set(TOOLS.get(expected_arm, ()))
    for line_number, line in enumerate(lines, 1):
        try:
            event = json.loads(line)
        except Exception:
            leak_failures.append(f"malformed_jsonl:{line_number}")
            continue
        if not isinstance(event, dict) or not isinstance(event.get("type"), str):
            leak_failures.append(f"malformed_event:{line_number}")
            continue
        event_type = event["type"]
        if event_type in {"thread.started", "turn.started"}:
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
        if event_type in {"turn.failed", "error"}:
            run_failures.append(f"run_event:{line_number}:{event_type}")
            continue
        if event_type.startswith("item."):
            item = event.get("item")
            if not isinstance(item, dict) or not isinstance(item.get("type"), str):
                leak_failures.append(f"malformed_item:{line_number}")
                continue
            item_type = item["type"]
            if item_type in {"reasoning", "agent_message"}:
                continue
            if item_type == "mcp_tool_call":
                server, tool = _mcp_identity(item)
                if server != SERVER:
                    leak_failures.append(f"non_target_mcp:{line_number}")
                elif tool not in allowed_tools:
                    leak_failures.append(f"non_allowlisted_tool:{line_number}")
                else:
                    primitive_action_events += 1
                continue
            leak_failures.append(f"forbidden_item:{line_number}:{item_type}")
            continue
        leak_failures.append(f"unknown_event:{line_number}:{event_type}")

    if usage_events == 0:
        accounting_failures.append("no_observable_token_usage")

    # A wake = one turn.completed event carrying valid usage -- the SAME event this loop already
    # counts as usage_events for token accounting above (report 2026-07-21-gate0-readiness-final.md
    # §4: "one turn.completed event ... reuse usage_events already computed in the same loop"). No
    # new counting mechanism, no new channel: wakes just names the number token accounting already
    # produces. Fail-closed: a real, non-fabricated wake count is only ever reported once every
    # other category above is clean (leak/constancy/run/accounting) -- accounting_failures already
    # guarantees usage_events > 0 whenever it is empty (see "no_observable_token_usage" above), so
    # this branch never reports wakes=0 dressed as a pass. Any other branch keeps the fail-closed
    # INSUFFICIENT_WAKES hardcode: a transcript with a leak, a constancy breach, a run failure, or
    # broken accounting cannot be trusted to yield a genuine wake count, so none is fabricated.
    if leak_failures:
        overall, no_leak = "NO_LEAK", "NO_LEAK"
        wakes, wake_accounting = None, "INSUFFICIENT_WAKES"
    elif constancy_failures:
        overall, no_leak = "CONSTANCY_BREACH", "PASS"
        wakes, wake_accounting = None, "INSUFFICIENT_WAKES"
    elif run_failures:
        overall, no_leak = "NO_GO_RUN_FAILED", "PASS"
        wakes, wake_accounting = None, "INSUFFICIENT_WAKES"
    elif accounting_failures:
        overall, no_leak = "NO_GO_INSUFFICIENT_ACCOUNTING", "PASS"
        wakes, wake_accounting = None, "INSUFFICIENT_WAKES"
    else:
        overall, no_leak = "PASS", "PASS"
        wakes, wake_accounting = usage_events, "PASS"
    return {
        "schema_version": 2,
        "arm": expected_arm,
        "no_leak": no_leak,
        "overall": overall,
        "wakes": wakes,
        "wake_accounting": wake_accounting,
        "peer_constancy": "PASS" if peer_receipt_path is not None and not any(
            f.startswith("peer_") for f in constancy_failures) else "NOT_PROVEN",
        "token_usage": usage,
        "token_usage_events": usage_events,
        "primitive_action_events": primitive_action_events,
        "leak_failures": leak_failures,
        "constancy_failures": constancy_failures,
        "accounting_failures": accounting_failures,
        "run_failures": run_failures,
    }


def build_agent_metrics(result: dict, arm: str, mode: str, wall_clock_s: float, cost_usd: float,
                         normalized_credits: float) -> dict:
    """Build the eval/score_gate0.py-shaped `{arm}_agent` metrics record straight off an audit()
    result -- wakes and primitive_actions are read from the SAME pass over the transcript that
    already produced them above, never recomputed. wall_clock_s/cost_usd/normalized_credits are
    not observable from the transcript alone (they are supervision-level timing and signed-rate-
    pin outputs tools/gate0_credit_accountant.py and the paid launcher already produce), so the
    caller supplies them. Fail-closed: refuses to build a metrics record from anything but a clean
    overall=PASS/wake_accounting=PASS audit -- an agent_metrics.json `wakes` field must never be
    sourced from a run whose wake accounting itself could not be trusted."""
    if (result.get("overall") != "PASS" or result.get("wake_accounting") != "PASS"
            or not isinstance(result.get("wakes"), int) or isinstance(result.get("wakes"), bool)):
        raise ValueError("audit_not_clean: refusing to write agent_metrics.json from a non-PASS audit")
    return {
        "schema_version": 1,
        "arm": arm,
        "role": "agent",
        "mode": mode,
        "wall_clock_s": wall_clock_s,
        "primitive_actions": result["primitive_action_events"],
        "wakes": result["wakes"],
        "cost_usd": cost_usd,
        "normalized_credits": normalized_credits,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("transcript", type=Path)
    parser.add_argument("receipt", type=Path)
    parser.add_argument("expected_pins", type=Path)
    parser.add_argument("artifacts_dir", type=Path)
    parser.add_argument("--arm", required=True, choices=sorted(TOOLS))
    parser.add_argument("--peer-receipt", type=Path)
    parser.add_argument("--write-agent-metrics", type=Path,
                         help="Also write an eval/score_gate0.py-shaped agent_metrics.json here, "
                              "from the SAME audit() pass (requires --mode/--wall-clock-s/"
                              "--cost-usd/--normalized-credits).")
    parser.add_argument("--mode", choices=AGENT_METRICS_MODES)
    parser.add_argument("--wall-clock-s", type=float)
    parser.add_argument("--cost-usd", type=float)
    parser.add_argument("--normalized-credits", type=float)
    args = parser.parse_args()
    summary = audit(args.transcript, args.receipt, args.expected_pins, args.artifacts_dir,
                    args.arm, args.peer_receipt)
    print(json.dumps(summary, sort_keys=True))
    if args.write_agent_metrics is not None:
        missing = [name for name, value in (
            ("--mode", args.mode), ("--wall-clock-s", args.wall_clock_s),
            ("--cost-usd", args.cost_usd), ("--normalized-credits", args.normalized_credits),
        ) if value is None]
        if missing:
            parser.error(f"--write-agent-metrics requires {', '.join(missing)}")
        try:
            metrics = build_agent_metrics(summary, args.arm, args.mode, args.wall_clock_s,
                                          args.cost_usd, args.normalized_credits)
        except ValueError as exc:
            print(json.dumps({"error": str(exc)}), file=sys.stderr)
            return 1
        args.write_agent_metrics.parent.mkdir(parents=True, exist_ok=True)
        args.write_agent_metrics.write_text(json.dumps(metrics, sort_keys=True) + "\n",
                                            encoding="utf-8", newline="\n")
    return 0 if summary["overall"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
