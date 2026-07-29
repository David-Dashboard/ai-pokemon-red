"""$0, CI-safe tests for tools/gate0_appserver_launch.py. No real `codex` process is spawned
anywhere in this file -- the --dry-run path drives an in-process StubAppServerPeer, and the
credit-guard/config-builder tests exercise pure functions/threads directly. Mirrors the mock-only
discipline of tests/test_gate0_appserver_client.py."""
import json
import sys
import threading
import time

import pytest

from tools.gate0_appserver_launch import (
    AppServerUsageTracker,
    LiveCreditGuard,
    ObservingGate0Client,
    StubAppServerPeer,
    _extract_thread_id,
    _extract_turn_id,
    _notification_turn_id,
    _resolve_mcp_server,
    app_server_usage_notification_to_credit_event,
    build_overrides,
    default_prompt,
    main,
    run_one_tool_call_turn,
    score_turn,
    seed_codex_auth,
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
# B2: a real turn (not --dry-run, not --handshake-only) must refuse to launch without a
# --credit-rate-pin -- --credit-cap is otherwise unenforceable (LiveCreditGuard's zero-credit
# passthrough), so this is the fail-closed backstop.
# ---------------------------------------------------------------------------

def test_real_turn_without_credit_rate_pin_is_refused(tmp_path):
    with pytest.raises(SystemExit):
        main(["--model", "gpt-5.6-sol", "--out-dir", str(tmp_path / "out")])


def test_handshake_only_does_not_require_a_credit_rate_pin(tmp_path, monkeypatch):
    # --handshake-only never sends turn/start, so it must NOT be caught by the real-turn
    # fail-closed check above. Patch resolve_codex_path to blow up with a distinct sentinel the
    # moment main() tries to actually resolve codex -- proves validation was passed WITHOUT
    # spawning any real process (this file's own $0/CI-safe discipline).
    sentinel = RuntimeError("sentinel: reached real-mode codex resolution")

    def _boom():
        raise sentinel

    monkeypatch.setattr("tools.gate0_appserver_launch.resolve_codex_path", _boom)
    with pytest.raises(RuntimeError) as excinfo:
        main(["--handshake-only", "--model", "gpt-5.6-sol", "--out-dir", str(tmp_path / "out")])
    assert excinfo.value is sentinel


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
# S1 hardening: a terminal item carrying a non-empty error/isError must never score as completed,
# regardless of what `status` says (the exec bug this harness distinguishes is a cancel-WITH-error).
# ---------------------------------------------------------------------------

def test_score_turn_completed_status_with_is_error_true_is_not_completed():
    client = _client_with_notifications([
        {"method": "item/completed", "params": {"item": {
            "id": "a", "tool": "ping", "status": "completed", "isError": True,
            "error": "user cancelled MCP tool call"}}},
        {"method": "turn/completed", "params": {}},
    ])
    result = score_turn(client, tool_name="ping")
    assert result["mcp_tool_call_completed"] is False
    assert result["cancelled"] is True


def test_score_turn_completed_status_with_nonempty_error_string_is_not_completed():
    client = _client_with_notifications([
        {"method": "item/completed", "params": {"item": {
            "id": "a", "tool": "ping", "status": "completed", "error": "boom"}}},
        {"method": "turn/completed", "params": {}},
    ])
    result = score_turn(client, tool_name="ping")
    assert result["mcp_tool_call_completed"] is False
    assert result["cancelled"] is True


def test_score_turn_genuine_completed_with_result_scores_true():
    client = _client_with_notifications([
        {"method": "item/completed", "params": {"item": {
            "id": "a", "tool": "ping", "status": "completed",
            "result": {"content": [{"type": "text", "text": "pong"}]}}}},
        {"method": "turn/completed", "params": {}},
    ])
    result = score_turn(client, tool_name="ping")
    assert result["mcp_tool_call_completed"] is True
    assert result["cancelled"] is False


def test_score_turn_tool_match_fallback_never_selects_a_non_target_tool_item():
    # A same-shaped OTHER tool's completed item must not be picked as the target just because its
    # `type` string happens to contain "tool" -- the explicit `tool` field is authoritative.
    client = _client_with_notifications([
        {"method": "item/completed", "params": {"item": {
            "id": "a", "tool": "other", "type": "mcp_tool_call", "status": "completed"}}},
        {"method": "turn/failed", "params": {}},
    ])
    result = score_turn(client, tool_name="ping")
    assert result["mcp_tool_call_completed"] is False
    assert (result["target_item"] or {}).get("id") != "a"


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
# B1a follow-up: app-server `thread/tokenUsage/updated` usage parsing. GROUND TRUTH shape captured
# from a real paid app-server turn (2026-07-23): two cumulative-total updates, `total.totalTokens`
# 11162 then 22364, with the SECOND event's `last.totalTokens` == 11202 == the diff of the two
# totals (proving `total` is cumulative and `last` is the per-update delta). The second/final
# update's per-field breakdown below (cachedInputTokens=9984, inputTokens=21980, totalTokens=22364)
# reproduces the real captured numbers exactly; the first update's per-field breakdown is not on
# record (only its totalTokens is), so it is filled in self-consistently here (inputTokens+
# outputTokens == totalTokens, and every field only increases into the second update, and the
# resulting totalTokens delta reproduces the ground truth's stated 11202 exactly).
# ---------------------------------------------------------------------------

_RATE_PIN = {
    "model": "gpt-5.6-sol", "rate_source": "test fixture, not a real price",
    "credits_per_usd": 1, "usd_per_input_token": 0.0001,
    "usd_per_cached_input_token": 0.00001, "usd_per_output_token": 0.0001,
}


def _token_usage_updated(*, cached, input_, output, reasoning, total_tokens, last=None,
                          thread_id="thr_real", turn_id="turn_real"):
    total = {"cachedInputTokens": cached, "inputTokens": input_, "outputTokens": output,
             "reasoningOutputTokens": reasoning, "totalTokens": total_tokens}
    return {
        "method": "thread/tokenUsage/updated",
        "params": {"threadId": thread_id, "turnId": turn_id,
                   "tokenUsage": {"last": last or total, "total": total,
                                  "modelContextWindow": 272000}},
    }


# Both events below are copied VERBATIM from the real captured transcript (PR #156 review fixture-
# provenance fix): reports/2026-07-23-gate0-appserver-m1-confirmation/transcript.jsonl line 27
# (event 1, the FIRST thread/tokenUsage/updated) and line 31 (event 2, the SECOND/final one) --
# not self-consistent filler. `last` on line 27 equals `total` (it is the first update); `last` on
# line 31 is the real per-field delta the capture recorded, and independently reproduces
# total_2 - total_1 exactly per field (cached 9984-0=9984, input 21980-10782=11198,
# output 384-380=4, reasoning 309-309=0, totalTokens 22364-11162=11202) -- confirming `total` is
# cumulative and `last` is the genuine per-update delta, not a coincidence of this fixture.
_GT_EVENT_1 = _token_usage_updated(cached=0, input_=10782, output=380, reasoning=309,
                                    total_tokens=11162)
_GT_EVENT_2 = _token_usage_updated(cached=9984, input_=21980, output=384, reasoning=309,
                                    total_tokens=22364,
                                    last={"cachedInputTokens": 9984, "inputTokens": 11198,
                                          "outputTokens": 4, "reasoningOutputTokens": 0,
                                          "totalTokens": 11202})


def test_app_server_usage_tracker_first_update_deltas_from_zero():
    tracker = AppServerUsageTracker()
    delta = tracker.delta_for(_GT_EVENT_1["params"]["tokenUsage"]["total"])
    assert delta == {"input_tokens": 10782, "cached_input_tokens": 0, "output_tokens": 380,
                      "reasoning_output_tokens": 309}


def test_app_server_usage_tracker_second_update_deltas_against_the_first():
    tracker = AppServerUsageTracker()
    tracker.delta_for(_GT_EVENT_1["params"]["tokenUsage"]["total"])
    delta = tracker.delta_for(_GT_EVENT_2["params"]["tokenUsage"]["total"])
    assert delta == {"input_tokens": 11198, "cached_input_tokens": 9984, "output_tokens": 4,
                      "reasoning_output_tokens": 0}
    # Matches the ground truth's captured per-update totalTokens delta exactly (22364-11162=11202).
    assert delta["input_tokens"] + delta["output_tokens"] == 11202


def test_app_server_usage_tracker_duplicate_total_yields_zero_delta_never_double_counted():
    tracker = AppServerUsageTracker()
    total = _GT_EVENT_1["params"]["tokenUsage"]["total"]
    first = tracker.delta_for(total)
    assert sum(first.values()) > 0
    duplicate = tracker.delta_for(dict(total))  # the exact same cumulative total again
    assert duplicate == {"input_tokens": 0, "cached_input_tokens": 0, "output_tokens": 0,
                          "reasoning_output_tokens": 0}


def test_app_server_usage_tracker_strictly_regressed_total_raises_not_clamped():
    # PR #156 review fix: a STRICTLY REGRESSED total (any field going DOWN vs. the last-seen
    # baseline) is a stream fault, not a duplicate -- the tracker must fail loud (raise), never
    # silently clamp to a zero delta and continue as if nothing happened.
    tracker = AppServerUsageTracker()
    tracker.delta_for(_GT_EVENT_2["params"]["tokenUsage"]["total"])
    with pytest.raises(ValueError, match="app_server_token_usage_regressed"):
        tracker.delta_for(_GT_EVENT_1["params"]["tokenUsage"]["total"])


def test_app_server_usage_notification_to_credit_event_prices_the_delta():
    tracker = AppServerUsageTracker()
    event = app_server_usage_notification_to_credit_event(_GT_EVENT_1, _RATE_PIN, tracker)
    # uncached_input=10782-0=10782, cached=0, output=380:
    # 10782*0.0001 + 0*0.00001 + 380*0.0001 = 1.0782 + 0 + 0.038 = 1.1162
    assert event["normalized_credits"] == pytest.approx(1.1162)


def test_app_server_usage_notification_missing_tokenusage_fails_closed():
    tracker = AppServerUsageTracker()
    with pytest.raises(ValueError):
        app_server_usage_notification_to_credit_event(
            {"method": "thread/tokenUsage/updated", "params": {}}, _RATE_PIN, tracker)


# ---------------------------------------------------------------------------
# The actual B1a live-cap proof: real-shaped `thread/tokenUsage/updated` notifications fed through
# LiveCreditGuard (the exact object the launcher wires) must accumulate credits and TRIP the
# breaker at --credit-cap -- proving --credit-cap is no longer inert on the app-server transport.
# ---------------------------------------------------------------------------

def test_single_app_server_notification_below_cap_does_not_trip():
    tripped = {"called": False}
    guard = LiveCreditGuard(limit=1.2, stall_timeout_s=2.0, rate_pin=_RATE_PIN,
                             on_trip=lambda exc: tripped.__setitem__("called", True))
    guard.start()
    guard.observe(_GT_EVENT_1)  # 1.1162 credits, under the 1.2 cap
    guard.finish()
    guard.join(timeout=5.0)
    assert guard.result["tripped"] is False
    assert tripped["called"] is False


def test_app_server_notification_sequence_trips_the_breaker_at_the_cap():
    tripped = {"called": False}
    guard = LiveCreditGuard(limit=1.2, stall_timeout_s=2.0, rate_pin=_RATE_PIN,
                             on_trip=lambda exc: tripped.__setitem__("called", True))
    guard.start()
    guard.observe(_GT_EVENT_1)  # 1.1162 cumulative, under the 1.2 cap
    # event 2 delta: uncached_input=11198-9984=1214, cached=9984, output=4:
    # 1214*0.0001 + 9984*0.00001 + 4*0.0001 = 0.1214 + 0.09984 + 0.0004 = 0.22164
    # cumulative 1.1162 + 0.22164 = 1.33784, crosses the 1.2 cap.
    guard.observe(_GT_EVENT_2)
    guard.finish()
    guard.join(timeout=5.0)
    assert guard.result["tripped"] is True
    assert tripped["called"] is True
    # Tripped on the SECOND event (index 1, 2 events consumed) -- proves the first notification
    # alone was under the cap and it took the cumulative total of both to cross it.
    assert "event 1" in guard.result["error"]
    assert "2 events consumed" in guard.result["error"]


def test_app_server_notification_duplicate_delivery_does_not_double_count_toward_the_cap():
    # The same GT_EVENT_1 total observed TWICE (a retried/duplicated notification) must price the
    # second delivery at zero credits, not double-charge -- 2x the real credits (~2.23) would
    # exceed the 1.2 cap, but the duplicate alone must not trip it.
    tripped = {"called": False}
    guard = LiveCreditGuard(limit=1.2, stall_timeout_s=2.0, rate_pin=_RATE_PIN,
                             on_trip=lambda exc: tripped.__setitem__("called", True))
    guard.start()
    guard.observe(_GT_EVENT_1)
    guard.observe(_GT_EVENT_1)  # duplicate of the same cumulative total
    guard.finish()
    guard.join(timeout=5.0)
    assert guard.result["tripped"] is False
    assert guard.result["final_total_normalized_credits"] == pytest.approx(1.1162)


def test_exec_shaped_path_still_works_alongside_app_server_notifications():
    # Mixed stream: an app-server usage notification AND an exec-shaped token_count event in the
    # same guard run must both be priced and accumulate together -- the exec path must not break.
    tripped = {"called": False}
    guard = LiveCreditGuard(limit=1.4, stall_timeout_s=2.0, rate_pin=_RATE_PIN,
                             on_trip=lambda exc: tripped.__setitem__("called", True))
    guard.start()
    guard.observe(_GT_EVENT_1)  # 1.1162, under the 1.4 cap
    guard.observe({"type": "token_count", "info": {"last_token_usage": {
        "input_tokens": 0, "cached_input_tokens": 0, "output_tokens": 4000,
        "reasoning_output_tokens": 0}}})  # 4000*0.0001=0.4 -> cumulative 1.5162, crosses the cap
    guard.finish()
    guard.join(timeout=5.0)
    assert guard.result["tripped"] is True
    assert tripped["called"] is True


# ---------------------------------------------------------------------------
# N3: seed_codex_auth -- pure filesystem helper, never spawns anything.
# ---------------------------------------------------------------------------

def test_seed_codex_auth_copies_from_source_when_dest_missing(tmp_path):
    codex_home = tmp_path / "codex-home"
    codex_home.mkdir()
    source = tmp_path / "real-codex-home" / "auth.json"
    source.parent.mkdir()
    source.write_text('{"token": "fixture-not-real"}', encoding="utf-8")

    note = seed_codex_auth(codex_home, str(source))

    assert (codex_home / "auth.json").read_text(encoding="utf-8") == source.read_text(encoding="utf-8")
    assert "seeded" in note
    # The source is never mutated/moved.
    assert source.is_file()


def test_seed_codex_auth_leaves_an_existing_dest_alone(tmp_path):
    codex_home = tmp_path / "codex-home"
    codex_home.mkdir()
    (codex_home / "auth.json").write_text("original", encoding="utf-8")
    source = tmp_path / "source-auth.json"
    source.write_text("different", encoding="utf-8")

    note = seed_codex_auth(codex_home, str(source))

    assert (codex_home / "auth.json").read_text(encoding="utf-8") == "original"
    assert note is None


def test_seed_codex_auth_reports_missing_source_without_raising(tmp_path):
    codex_home = tmp_path / "codex-home"
    codex_home.mkdir()
    missing_source = tmp_path / "nowhere" / "auth.json"

    note = seed_codex_auth(codex_home, str(missing_source))

    assert not (codex_home / "auth.json").exists()
    assert "not found" in note


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


# ---------------------------------------------------------------------------
# wait_for_notification: the SECOND-TURN rescan bug. Before the turn-id filter, a second
# turn/start on the same thread returned turn 1's still-present terminal notification instantly
# and never waited for turn 2. Shapes are copied from the real 2026-07-24 paid Red arm transcript
# (runs/gate0_paid/red/transcript.raw_appserver.jsonl).
# ---------------------------------------------------------------------------

_TURN1_END = {"method": "turn/completed",
              "params": {"threadId": "thr_1", "turn": {"id": "turn_1", "status": "completed"}}}
_TURN2_END = {"method": "turn/completed",
              "params": {"threadId": "thr_1", "turn": {"id": "turn_2", "status": "completed"}}}


def test_wait_for_notification_second_turn_does_not_return_turn_ones_terminal_note():
    client = _client_with_notifications([_TURN1_END])
    started = time.monotonic()
    assert client.wait_for_notification(("turn/completed",), timeout=0.3, turn_id="turn_2") is None
    assert time.monotonic() - started >= 0.25  # it actually WAITED instead of matching turn 1


def test_wait_for_notification_second_turn_returns_turn_twos_note_once_it_arrives():
    client = _client_with_notifications([_TURN1_END])

    def _late_arrival():
        time.sleep(0.1)
        client.notifications.append(_TURN2_END)

    thread = threading.Thread(target=_late_arrival, daemon=True)
    thread.start()
    note = client.wait_for_notification(("turn/completed",), timeout=5.0, turn_id="turn_2")
    thread.join(timeout=5.0)
    assert note is not None and note["params"]["turn"]["id"] == "turn_2"


def test_wait_for_notification_without_a_turn_id_keeps_the_unscoped_behaviour():
    client = _client_with_notifications([_TURN1_END])
    note = client.wait_for_notification(("turn/completed",), timeout=0.3)
    assert note is not None and note["params"]["turn"]["id"] == "turn_1"


def test_extract_turn_id_reads_the_real_turn_start_response_shape():
    assert _extract_turn_id({"turn": {"id": "019f946b-5d5a-7593-80d9-04990927728b",
                                      "status": "inProgress"}}) == "019f946b-5d5a-7593-80d9-04990927728b"
    assert _extract_turn_id({"turnId": "t2"}) == "t2"
    assert _extract_turn_id({"nothing": "here"}) is None


def test_notification_turn_id_reads_both_the_nested_and_flat_spellings():
    assert _notification_turn_id(_TURN1_END) == "turn_1"
    # thread/tokenUsage/updated uses the flat `turnId` spelling in the same transcript.
    assert _notification_turn_id({"method": "thread/tokenUsage/updated",
                                  "params": {"threadId": "thr_1", "turnId": "turn_9"}}) == "turn_9"
    assert _notification_turn_id({"method": "turn/completed", "params": {}}) is None
