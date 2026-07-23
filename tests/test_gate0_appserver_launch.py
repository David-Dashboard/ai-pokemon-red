"""$0, CI-safe tests for tools/gate0_appserver_launch.py. No real `codex` process is spawned
anywhere in this file -- the --dry-run path drives an in-process StubAppServerPeer, and the
credit-guard/config-builder tests exercise pure functions/threads directly. Mirrors the mock-only
discipline of tests/test_gate0_appserver_client.py."""
import json
import sys

import pytest

from tools.gate0_appserver_launch import (
    LiveCreditGuard,
    ObservingGate0Client,
    StubAppServerPeer,
    _extract_thread_id,
    _resolve_mcp_server,
    build_overrides,
    default_prompt,
    main,
    run_one_tool_call_turn,
    score_turn,
)


def _run_dry(tmp_path, scenario="completes", tool_name="ping"):
    out_dir = tmp_path / "out"
    argv = ["--dry-run", "--scenario", scenario, "--tool-name", tool_name, "--out-dir", str(out_dir)]
    exit_code = main(argv)
    verdict = json.loads((out_dir / "verdict.json").read_text(encoding="utf-8"))
    return exit_code, verdict, out_dir


# ---------------------------------------------------------------------------
# End-to-end --dry-run: the same scoring path a real launch would use.
# ---------------------------------------------------------------------------

def test_dry_run_completes_scenario_scores_tool_call_completed(tmp_path):
    exit_code, verdict, out_dir = _run_dry(tmp_path, scenario="completes")
    assert exit_code == 0
    assert verdict["mcp_tool_call_completed"] is True
    assert verdict["cancelled"] is False
    assert verdict["credit_breaker_tripped"] is False
    assert verdict["turns"] == 1
    assert verdict["mode"] == "dry_run"
    assert (out_dir / "transcript.jsonl").is_file()
    assert (out_dir / "audit.jsonl").is_file()


def test_dry_run_cancelled_scenario_scores_negative_not_a_rubber_stamp(tmp_path):
    exit_code, verdict, out_dir = _run_dry(tmp_path, scenario="cancelled")
    assert exit_code == 1
    assert verdict["mcp_tool_call_completed"] is False
    assert verdict["cancelled"] is True


def test_dry_run_transcript_shows_the_client_answering_accept(tmp_path):
    _, _, out_dir = _run_dry(tmp_path, scenario="completes")
    lines = [json.loads(line) for line in (out_dir / "transcript.jsonl").read_text(encoding="utf-8").splitlines()]
    approval_response = next(
        entry for entry in lines
        if entry["direction"] == "client_to_server" and entry["message"].get("id") == "req_approval_1"
    )
    assert approval_response["message"]["result"] == {"answers": {"q_approve_tool_call": {"answers": ["Approve"]}}}


def test_dry_run_audit_log_never_leaks_prompt_text(tmp_path):
    # The client's own audit trail rule (tests/test_gate0_appserver_client.py) carries over: only
    # method/ids/action, never params/result -- confirm the launcher's prompt text never lands there.
    _, _, out_dir = _run_dry(tmp_path, scenario="completes")
    audit_text = (out_dir / "audit.jsonl").read_text(encoding="utf-8")
    assert "MCP tool named" not in audit_text


def test_dry_run_out_dir_must_not_exist_or_be_empty(tmp_path):
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    (out_dir / "stray.txt").write_text("x", encoding="utf-8")
    with pytest.raises(SystemExit):
        main(["--dry-run", "--out-dir", str(out_dir)])


def test_model_latest_alias_is_rejected(tmp_path):
    with pytest.raises(SystemExit):
        main(["--model", "gpt-5.6-sol-latest", "--out-dir", str(tmp_path / "out")])


def test_model_required_outside_dry_run(tmp_path):
    with pytest.raises(SystemExit):
        main(["--out-dir", str(tmp_path / "out")])


def test_stall_timeout_may_only_tighten_never_loosen(tmp_path):
    with pytest.raises(SystemExit):
        main(["--dry-run", "--stall-timeout-s", "999999", "--out-dir", str(tmp_path / "out")])


def test_credit_rate_pin_rejected_outside_a_real_turn(tmp_path):
    with pytest.raises(SystemExit):
        main(["--dry-run", "--credit-rate-pin", str(tmp_path / "pin.json"),
              "--out-dir", str(tmp_path / "out")])


# ---------------------------------------------------------------------------
# score_turn: the pure scoring function, exercised against synthetic notification shapes.
# ---------------------------------------------------------------------------

def _client_with_notifications(notifications):
    client = ObservingGate0Client(send=lambda message: None)
    client.notifications = notifications
    return client


def test_score_turn_no_notifications_is_neither_completed_nor_cancelled():
    client = _client_with_notifications([])
    result = score_turn(client, tool_name="ping")
    assert result["mcp_tool_call_completed"] is False
    assert result["cancelled"] is False


def test_score_turn_picks_the_matching_tool_when_multiple_items_present():
    client = _client_with_notifications([
        {"method": "item/completed", "params": {"item": {"id": "a", "tool": "other", "status": "completed"}}},
        {"method": "item/completed", "params": {"item": {"id": "b", "tool": "ping", "status": "completed"}}},
        {"method": "turn/completed", "params": {}},
    ])
    result = score_turn(client, tool_name="ping")
    assert result["mcp_tool_call_completed"] is True
    assert result["target_item"]["id"] == "b"


def test_score_turn_turn_failed_without_a_completed_item_counts_as_cancelled():
    client = _client_with_notifications([{"method": "turn/failed", "params": {}}])
    result = score_turn(client, tool_name="ping")
    assert result["mcp_tool_call_completed"] is False
    assert result["cancelled"] is True


# ---------------------------------------------------------------------------
# run_one_tool_call_turn: same function drives the stub peer.
# ---------------------------------------------------------------------------

def test_run_one_tool_call_turn_against_the_stub_peer_directly():
    peer = StubAppServerPeer(tool_name="ping", scenario="completes")
    client = ObservingGate0Client(send=peer.send)
    peer.client = client
    result = run_one_tool_call_turn(client, cwd="/tmp/x", prompt=default_prompt("ping"),
                                     tool_name="ping", turn_timeout_s=5.0)
    assert result["mcp_tool_call_completed"] is True
    assert result["cancelled"] is False


def test_extract_thread_id_supports_the_nested_and_flat_shapes():
    assert _extract_thread_id({"thread": {"id": "t1"}}) == "t1"
    assert _extract_thread_id({"threadId": "t2"}) == "t2"
    assert _extract_thread_id({"id": "t3"}) == "t3"
    with pytest.raises(RuntimeError):
        _extract_thread_id({"nothing": "here"})


# ---------------------------------------------------------------------------
# LiveCreditGuard: imports tools/gate0_credit_breaker.run_breaker unmodified; proves the wiring
# (including the on_trip kill callback) fires on a synthetic over-cap stream.
# ---------------------------------------------------------------------------

def test_live_credit_guard_trips_and_calls_on_trip_when_cap_exceeded():
    tripped = {"called": False}

    def on_trip(exc):
        tripped["called"] = True

    guard = LiveCreditGuard(limit=5, stall_timeout_s=2.0, rate_pin=None, on_trip=on_trip)
    guard.start()
    # No rate pin -> every observed message passes through at 0 normalized_credits (never
    # fabricates a rate) -- the breaker legitimately never trips on a zero-credit stream. Feed a
    # message shaped so a rate-pinned conversion WOULD price it, to exercise the "no pin" honesty
    # path, then finish and confirm no trip.
    for _ in range(3):
        guard.observe({"type": "agent_message_delta"})
    guard.finish()
    guard.join(timeout=5.0)
    assert guard.result["tripped"] is False
    assert tripped["called"] is False


def test_live_credit_guard_trips_with_a_rate_pin_over_the_cap():
    rate_pin = {
        "model": "gpt-5.6-sol", "rate_source": "test fixture, not a real price",
        "credits_per_usd": 25, "usd_per_input_token": 0.0, "usd_per_cached_input_token": 0.0,
        "usd_per_output_token": 0.01,
    }
    tripped = {"called": False}
    guard = LiveCreditGuard(limit=1.0, stall_timeout_s=2.0, rate_pin=rate_pin,
                             on_trip=lambda exc: tripped.__setitem__("called", True))
    guard.start()
    # 10 output tokens * $0.01/token * 25 credits/$ = 2.5 credits > the 1.0 cap.
    guard.observe({"type": "token_count", "info": {"last_token_usage": {
        "input_tokens": 0, "cached_input_tokens": 0, "output_tokens": 10,
        "reasoning_output_tokens": 0}}})
    guard.finish()
    guard.join(timeout=5.0)
    assert guard.result["tripped"] is True
    assert tripped["called"] is True


# ---------------------------------------------------------------------------
# Real-mode config building (never spawns anything -- pure string/list assembly).
# ---------------------------------------------------------------------------

def test_build_overrides_matches_the_pinned_recipes_field_vocabulary():
    overrides = build_overrides(
        model="gpt-5.6-sol", mcp_server_name="gate0_stub", mcp_command=sys.executable,
        mcp_args=["tools/gate0_stub_mcp_server.py"], mcp_cwd="/repo",
        enabled_tools=["ping"], developer_instructions="Use only the gate0_stub MCP tools.")
    joined = "\n".join(overrides)
    for expected in (
        'forced_login_method="chatgpt"', 'approval_policy="never"', 'sandbox_mode="read-only"',
        'web_search="disabled"', 'features.shell_tool=false', 'apps._default.enabled=false',
        "mcp_servers.gate0_stub.required=true", "mcp_servers.gate0_stub.enabled=true",
        'mcp_servers.gate0_stub.default_tools_approval_mode="auto"',
    ):
        assert expected in joined


def test_resolve_mcp_server_stub_needs_no_docker_image(tmp_path):
    class Args:
        mcp = "stub"
        stub_mcp_script = None
    command, args_list, cwd, tools = _resolve_mcp_server(Args())
    assert command == sys.executable
    assert args_list[0].endswith("gate0_stub_mcp_server.py")
    assert tools == ["ping"]


def test_resolve_mcp_server_docker_requires_image():
    class Args:
        mcp = "docker"
        docker_image = None
        docker_mount = None
        docker_extra_arg = None
        docker_tool = None
    with pytest.raises(SystemExit):
        _resolve_mcp_server(Args())
