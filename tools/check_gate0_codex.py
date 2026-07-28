"""Fail-closed Codex transcript audit against frozen, observed Gate 0 pins.

=====================================================================================================
THIS MODULE'S `audit_overall` IS NOT THE GATE 0 VERDICT -- DO NOT QUOTE IT AS ONE
=====================================================================================================

- `audit()`'s `audit_overall` is an INTERMEDIATE PER-ARM AUDIT INPUT, not the gate's printed
  verdict. The Gate 0 verdict authority is `eval/score_gate0.py::score()` and its OWN `overall`.
- `score()` consumes exactly four fields off an audit dict -- `leak_failures`,
  `constancy_failures`, `run_failures` (eval/score_gate0.py:318-320) and `accounting_failures`
  (:336). It NEVER reads `audit_overall`. `wake_accounting` is read once (:297) purely to populate
  an informational `"status": "DEFERRED"` payload, and never gates.
- `audit_overall` can NEVER be "PASS": wake accounting is permanently fail-closed by design (see
  the block comment above audit()'s return), so the verdict chain always bottoms out in
  "NO_GO_INSUFFICIENT_WAKES". That does NOT cap the gate -- see
  reports/2026-07-25-gate0-v2-prereg.md Sec. 0.1 and reports/2026-07-18-gate0-prereg.md:81-83,
  which said the same thing first.
- The field is called `audit_overall` and not `overall` precisely because this misreading is
  recurring: on 2026-07-28 a reviewer read `overall: NO_GO_INSUFFICIENT_WAKES` as the gate's
  ceiling and escalated that Gate 0 v2 was structurally unwinnable. It was false, and the rename
  exists so the next reader cannot make the same substitution by accident.
- SAME RULE FOR `no_leak` AND `peer_constancy`, which both emit the literal string "PASS" and are
  therefore easier to misquote, not harder. They are per-CHECK results scoped to this one arm --
  "the no-leak check passed", "the peer receipts agree" -- never a gate verdict. No scorer gates
  on either (neither name appears anywhere in eval/score_gate0.py), but both ARE quoted in banked
  prose: reports/2026-07-24-gate0-armR-verdict.md:165 prints `"no_leak": "PASS"` on the same line
  as `CONSTANCY_BREACH`. That is the misquote risk, live, in a banked verdict report.
  reports/2026-07-18-gate0-prereg.md:81-83 names `overall`, `no_leak` AND `wake_accounting`
  together: "do not quote them as the Gate 0 result." Only the first was renamed, because it was
  the one that collided with every real scorer's verdict field name.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


SERVER = "gate0_world"
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

    # WAKE ACCOUNTING STAYS FAIL-CLOSED BY DESIGN -- grounded, not a stub
    # (reports/2026-07-21-gate0-wake-grounding.md, PR #126). An earlier version of this function
    # set wakes = usage_events (one wake per turn.completed event with valid usage), reusing the
    # same loop as token accounting above. A real `codex exec --json` transcript falsified that: a
    # single turn.completed bundled >=2 real model decisions -- its usage is CUMULATIVE FOR THE
    # WHOLE TURN, not per-decision -- and no other event in Codex's JSONL schema marks a
    # per-model-call boundary (item.completed/item.started carry no usage and do not group by
    # originating model call). That is a >=2x undercount, not a rounding error. Do not substitute
    # tool calls, turns, or any other JSONL event for wakes (matches reports/2026-07-13-minimum-
    # north-star-gate-0-design.md L237-241's own caveat against exactly this substitution). wakes/
    # wake_accounting stay hardcoded until Codex ships a documented per-model-call boundary event:
    # any transcript, however clean, reports wakes=None / wake_accounting="INSUFFICIENT_WAKES", so
    # audit_overall can never reach "PASS" via a wake count. primitive_action_events (below,
    # counted in the same loop) is unaffected -- it counts actual allowlisted tool-call items, not
    # model decisions, and has no analogous undercount problem.
    if leak_failures:
        audit_overall, no_leak = "NO_LEAK", "NO_LEAK"
    elif constancy_failures:
        audit_overall, no_leak = "CONSTANCY_BREACH", "PASS"
    elif run_failures:
        audit_overall, no_leak = "NO_GO_RUN_FAILED", "PASS"
    elif accounting_failures:
        audit_overall, no_leak = "NO_GO_INSUFFICIENT_ACCOUNTING", "PASS"
    else:
        audit_overall, no_leak = "NO_GO_INSUFFICIENT_WAKES", "PASS"
    return {
        # 3 (was 2): the emitted verdict field was renamed "overall" -> "audit_overall" so it can
        # never again be misread as eval/score_gate0.py::score()'s own "overall" (module docstring).
        # The RUN RECEIPT's schema_version (_receipt_shape_failures above) is a DIFFERENT object and
        # deliberately stays 2.
        "schema_version": 3,
        "arm": expected_arm,
        "no_leak": no_leak,
        "audit_overall": audit_overall,
        "wakes": None,
        "wake_accounting": "INSUFFICIENT_WAKES",
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


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Audit ONE Gate 0 arm's Codex transcript against its frozen pins.",
        epilog="EXIT CODE: always 1, on purpose. It tracks audit_overall == \"PASS\", which can "
               "never happen: wakes are permanently fail-closed and deliberately non-gating, so "
               "even a perfectly clean run reads NO_GO_INSUFFICIENT_WAKES. This CLI therefore "
               "CANNOT signal a Gate 0 pass, and `check_gate0_codex.py ... && echo PASS` is a bug "
               "by construction rather than a green light. Read the printed JSON, not the exit "
               "status. The Gate 0 verdict comes from eval/score_gate0.py::score(), which reads "
               "leak_failures/constancy_failures/run_failures/accounting_failures and never reads "
               "audit_overall.")
    parser.add_argument("transcript", type=Path)
    parser.add_argument("receipt", type=Path)
    parser.add_argument("expected_pins", type=Path)
    parser.add_argument("artifacts_dir", type=Path)
    parser.add_argument("--arm", required=True, choices=sorted(TOOLS))
    parser.add_argument("--peer-receipt", type=Path)
    args = parser.parse_args()
    summary = audit(args.transcript, args.receipt, args.expected_pins, args.artifacts_dir,
                    args.arm, args.peer_receipt)
    print(json.dumps(summary, sort_keys=True))
    # Fail-closed by construction: audit_overall has no PASS branch, so this ALWAYS returns 1. That
    # is the point, not an oversight. audit() is an intermediate diagnostic; the verdict authority
    # is eval/score_gate0.py::score(). A CLI that exited 0 on a clean audit would put the
    # audit-verdict/gate-verdict conflation this module's docstring exists to prevent into
    # executable form -- one `... && echo PASS` away from a fabricated Gate 0 pass.
    return 0 if summary["audit_overall"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
