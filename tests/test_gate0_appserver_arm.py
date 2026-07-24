"""$0, CI-safe tests for tools/gate0_appserver_arm.py. No real `codex` or `docker run <real image>`
process is spawned anywhere in this file -- --dry-run drives an in-process
MultiCallStubAppServerPeer, and every docker/codex subprocess call is monkeypatched. Mirrors the
mock-only discipline of tests/test_gate0_appserver_launch.py."""
from __future__ import annotations

import json
import subprocess

import pytest

import tools.check_gate0_codex as checker
from tools.check_gate0_codex import TOOLS
from tools.gate0_credit_breaker import LIMIT_NORMALIZED_CREDITS
import tools.gate0_appserver_arm as arm_mod
from tools.gate0_appserver_arm import (
    ARM_IMAGE_IDS,
    ARM_SOFT_CREDIT_CAPS,
    HARD_CREDIT_CAP,
    LAUNCH_INVOCATION_DEPENDENT_MARKER,
    MultiCallStubAppServerPeer,
    SoftCapWatcher,
    adapt_app_server_notifications_to_exec_shape,
    build_agent_metrics,
    build_docker_mcp_args,
    resolve_isolated_codex_home,
    resolve_expected_pins,
    ensure_wake_boundary_artifact,
    main,
    refuse_if_already_completed,
    render_brain_config_toml,
    render_full_config_toml,
    render_world_config_toml,
    run_gate0_arm_turn,
    task_text_for,
    verify_launch_signature_unchanged,
)
from tools.gate0_appserver_launch import ObservingGate0Client


_RATE_PIN = {
    "model": "gpt-5.6-sol", "rate_source": "test fixture, not a real price",
    "credits_per_usd": 1, "usd_per_input_token": 0.0001,
    "usd_per_cached_input_token": 0.00001, "usd_per_output_token": 0.0001,
}


# ---------------------------------------------------------------------------
# End-to-end --dry-run: manifest-shaped artifact set with the right keys.
# ---------------------------------------------------------------------------

def _run_dry(tmp_path, arm="red", call_count=3, scenario="completes"):
    out_dir = tmp_path / "out"
    argv = ["--arm", arm, "--out-dir", str(out_dir), "--dry-run",
            "--call-count", str(call_count), "--scenario", scenario]
    exit_code = main(argv)
    return exit_code, out_dir


def test_dry_run_produces_a_manifest_shaped_artifact_set(tmp_path):
    exit_code, out_dir = _run_dry(tmp_path, arm="red", call_count=3)
    assert exit_code == 0
    transcript = out_dir / "transcript.jsonl"
    agent_metrics = out_dir / "agent_metrics.json"
    wake_boundary = out_dir / "wake_boundary.json"
    assert transcript.is_file()
    assert (out_dir / "transcript.raw_appserver.jsonl").is_file()
    assert agent_metrics.is_file()
    assert wake_boundary.is_file()

    metrics = json.loads(agent_metrics.read_text(encoding="utf-8"))
    for key in ("schema_version", "arm", "role", "mode", "wall_clock_s", "primitive_actions",
                "human_wall_clock_s", "human_primitive_actions", "cost_usd", "normalized_credits"):
        assert key in metrics
    assert metrics["arm"] == "red"
    assert metrics["role"] == "agent"
    assert metrics["primitive_actions"] == 3

    wake = json.loads(wake_boundary.read_text(encoding="utf-8"))
    assert wake["schema_version"] == 1
    assert wake["kind"] == "exact_wake_boundary"
    assert wake["status"] == "DEFERRED"

    events = [json.loads(line) for line in transcript.read_text(encoding="utf-8").splitlines()]
    assert sum(1 for e in events if e["type"] == "item.completed") == 3
    assert sum(1 for e in events if e["type"] == "turn.completed") == 1


def test_dry_run_miniwob_arm_uses_the_pinned_tool_allowlist(tmp_path):
    exit_code, out_dir = _run_dry(tmp_path, arm="miniwob", call_count=2)
    assert exit_code == 0
    events = [json.loads(line) for line in
              (out_dir / "transcript.jsonl").read_text(encoding="utf-8").splitlines()]
    tool_calls = [e["item"]["tool"] for e in events if e["type"] == "item.completed"]
    assert tool_calls == [TOOLS["miniwob"][0]] * 2


def test_dry_run_denied_call_still_counts_as_a_primitive_action_not_a_leak(tmp_path):
    # check_gate0_codex.audit() counts every allowlisted item.completed(mcp_tool_call) regardless
    # of its status/error -- a cancelled call is still a real, on-allowlist tool-call event.
    exit_code, out_dir = _run_dry(tmp_path, arm="red", call_count=2, scenario="one_call_denied")
    assert exit_code == 0
    verdict = json.loads((out_dir / "dry_run_verdict.json").read_text(encoding="utf-8"))
    assert verdict["primitive_action_events"] == 2
    assert verdict["audit_leak_failures"] == []


# ---------------------------------------------------------------------------
# One-attempt guard.
# ---------------------------------------------------------------------------

def test_one_attempt_guard_refuses_a_second_run_in_the_same_out_dir(tmp_path):
    exit_code, out_dir = _run_dry(tmp_path)
    assert exit_code == 0
    with pytest.raises(SystemExit, match="one-attempt guard"):
        main(["--arm", "red", "--out-dir", str(out_dir), "--dry-run"])


def test_refuse_if_already_completed_is_a_noop_when_out_dir_is_fresh(tmp_path):
    refuse_if_already_completed(tmp_path / "fresh")  # must not raise


def test_one_attempt_guard_catches_a_crashed_after_spending_run_with_no_agent_metrics(tmp_path):
    # PR #157 review SHOULD-fix: a run that SPENDS then CRASHES mid-turn never writes
    # agent_metrics.json (only written at the very end of a successful run) -- simulate exactly
    # that: only transcript.raw_appserver.jsonl exists (written from the FIRST message onward,
    # long before agent_metrics.json would ever be written). A second launch into the same
    # out-dir must still be refused, or it would silently re-spend.
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    (out_dir / "transcript.raw_appserver.jsonl").write_text(
        '{"direction": "client_to_server", "message": {"id": 1, "method": "initialize"}}\n',
        encoding="utf-8")
    assert not (out_dir / "agent_metrics.json").exists()  # the exact hole the review found
    with pytest.raises(SystemExit, match="one-attempt guard"):
        main(["--arm", "red", "--out-dir", str(out_dir), "--dry-run"])
    with pytest.raises(SystemExit, match="one-attempt guard"):
        refuse_if_already_completed(out_dir)


def test_seam_check_is_exempt_from_the_one_attempt_guard(tmp_path, monkeypatch):
    # --seam-check never writes agent_metrics.json, so re-running it in the same dir (e.g. as a
    # repeated preflight probe) must not trip the completed-run guard.
    out_dir = tmp_path / "out"
    monkeypatch.setattr(arm_mod, "resolve_docker_path", lambda: "docker")
    monkeypatch.setattr(arm_mod, "docker_image_inspect_id",
                         lambda docker_path, image_ref: ARM_IMAGE_IDS["red"])
    for _ in range(2):
        exit_code = main(["--arm", "red", "--out-dir", str(out_dir), "--seam-check"])
        assert exit_code == 0


# ---------------------------------------------------------------------------
# The transcript adapter -- the core honesty-sensitive piece of this build.
# ---------------------------------------------------------------------------

def test_adapter_maps_a_captured_shape_mcp_tool_call_faithfully():
    # Copied verbatim (field names/values) from the REAL captured transcript quoted in
    # reports/2026-07-23-gate0-appserver-m1-confirmation.md.
    notifications = [
        {"method": "item/started", "params": {"item": {
            "id": "exec-ba4a53b9", "server": "gate0_stub", "tool": "ping",
            "status": "inProgress", "type": "mcpToolCall", "arguments": {}, "result": None}}},
        {"method": "item/completed", "params": {"item": {
            "id": "exec-ba4a53b9", "server": "gate0_stub", "tool": "ping", "status": "completed",
            "type": "mcpToolCall", "arguments": {}, "durationMs": 4, "error": None,
            "result": {"content": [{"type": "text", "text": "pong"}]}}}},
        {"method": "turn/completed", "params": {"turn": {"id": "t1", "status": "completed"}}},
    ]
    events = adapt_app_server_notifications_to_exec_shape(notifications)
    # item/started must be dropped (never translated) -- otherwise the same real tool call would
    # double-count in check_gate0_codex.audit()'s primitive_action_events.
    assert len(events) == 2
    assert events[0] == {"type": "item.completed", "item": {
        "id": "exec-ba4a53b9", "server": "gate0_stub", "tool": "ping", "status": "completed",
        "type": "mcp_tool_call", "arguments": {}, "durationMs": 4, "error": None,
        "result": {"content": [{"type": "text", "text": "pong"}]}}}
    assert events[1] == {"type": "turn.completed"}  # no usage observed in this fixture


def test_adapter_folds_token_usage_into_the_turn_completed_event():
    notifications = [
        {"method": "item/completed", "params": {"item": {
            "type": "mcpToolCall", "server": "gate0_world", "tool": "observe"}}},
        {"method": "thread/tokenUsage/updated", "params": {"tokenUsage": {"total": {
            "inputTokens": 10782, "cachedInputTokens": 0, "outputTokens": 380,
            "reasoningOutputTokens": 309, "totalTokens": 11162}}}},
        {"method": "turn/completed", "params": {}},
    ]
    events = adapt_app_server_notifications_to_exec_shape(notifications)
    turn_event = next(e for e in events if e["type"] == "turn.completed")
    assert turn_event["usage"] == {"input_tokens": 10782, "cached_input_tokens": 0,
                                    "output_tokens": 380, "reasoning_output_tokens": 309}


def test_adapter_uses_the_latest_cumulative_total_not_the_first():
    notifications = [
        {"method": "thread/tokenUsage/updated", "params": {"tokenUsage": {"total": {
            "inputTokens": 100, "cachedInputTokens": 0, "outputTokens": 10,
            "reasoningOutputTokens": 0, "totalTokens": 110}}}},
        {"method": "thread/tokenUsage/updated", "params": {"tokenUsage": {"total": {
            "inputTokens": 200, "cachedInputTokens": 0, "outputTokens": 20,
            "reasoningOutputTokens": 0, "totalTokens": 220}}}},
        {"method": "turn/completed", "params": {}},
    ]
    events = adapt_app_server_notifications_to_exec_shape(notifications)
    assert events[0]["usage"]["input_tokens"] == 200


def test_adapter_turn_failed_and_aborted_map_to_turn_failed():
    for method in ("turn/failed", "turn/aborted"):
        events = adapt_app_server_notifications_to_exec_shape([{"method": method, "params": {}}])
        assert events == [{"type": "turn.failed"}]


def test_adapter_passes_unmapped_item_types_through_verbatim_never_guessing():
    # No committed app-server Item/ThreadItem schema exists in this repo for anything but
    # "mcpToolCall" -- an unconfirmed type (e.g. a real reasoning/message item, or a genuine leak
    # like a shell/web item) must be passed through UNCHANGED, never silently relabeled into
    # audit()'s "reasoning"/"agent_message" skip-list or "mcp_tool_call".
    notifications = [{"method": "item/completed",
                       "params": {"item": {"type": "someUnconfirmedItemType", "foo": "bar"}}}]
    events = adapt_app_server_notifications_to_exec_shape(notifications)
    assert events == [{"type": "item.completed",
                        "item": {"type": "someUnconfirmedItemType", "foo": "bar"}}]


def test_adapter_never_double_counts_a_started_then_completed_call():
    notifications = [
        {"method": "item/started", "params": {"item": {"type": "mcpToolCall", "server": "s",
                                                        "tool": "t", "status": "inProgress"}}},
        {"method": "item/completed", "params": {"item": {"type": "mcpToolCall", "server": "s",
                                                          "tool": "t", "status": "completed"}}},
    ]
    events = adapt_app_server_notifications_to_exec_shape(notifications)
    completed_items = [e for e in events if e["type"] == "item.completed"]
    assert len(completed_items) == 1


def test_adapter_malformed_usage_never_fabricates_a_usage_dict():
    # A structurally invalid tokenUsage.total (missing a required field) must not silently
    # contribute a fabricated/partial usage dict to turn.completed -- audit() should see NO usage
    # key at all and report its own honest accounting_failures, not a made-up number.
    notifications = [
        {"method": "thread/tokenUsage/updated", "params": {"tokenUsage": {"total": {
            "inputTokens": 10}}}},  # missing cachedInputTokens/outputTokens/reasoningOutputTokens
        {"method": "turn/completed", "params": {}},
    ]
    events = adapt_app_server_notifications_to_exec_shape(notifications)
    assert events == [{"type": "turn.completed"}]  # no "usage" key


def test_adapter_usermessage_and_agentmessage_and_reasoning_never_leak():
    # Unit-level companion to the decisive real-transcript test below: userMessage is dropped
    # (no item.* line at all), agentMessage/reasoning translate/pass through to exactly the
    # audit() skip-list strings.
    notifications = [
        {"method": "item/started", "params": {"item": {"type": "userMessage", "id": "u0"}}},
        {"method": "item/completed", "params": {"item": {"type": "userMessage", "id": "u0"}}},
        {"method": "item/started", "params": {"item": {"type": "reasoning", "id": "r0"}}},
        {"method": "item/completed", "params": {"item": {"type": "reasoning", "id": "r0"}}},
        {"method": "item/started", "params": {"item": {"type": "agentMessage", "id": "a0"}}},
        {"method": "item/completed", "params": {"item": {"type": "agentMessage", "id": "a0"}}},
    ]
    events = adapt_app_server_notifications_to_exec_shape(notifications)
    types = [e["item"]["type"] for e in events]
    assert types == ["reasoning", "agent_message"]  # userMessage: no line emitted at all


def _fixture_for_audit(out_dir, arm="red"):
    """Minimal self-consistent receipt/expected-pins/artifacts_dir pair -- same style as
    tools.gate0_appserver_arm._run_dry_run's own fixture -- purely so audit() has a valid
    artifacts_dir/receipt to check leak_failures against. Constancy/accounting are NOT under
    test by the caller of this helper; only leak_failures is."""
    enabled_tools = TOOLS[arm]
    (out_dir / "launch" / ".codex").mkdir(parents=True, exist_ok=True)
    fake_codex = out_dir / "codex.exe"
    fake_codex.write_bytes(b"fixture-codex")
    brain_text = arm_mod.render_brain_config_toml("gpt-5.6-sol", arm_mod.DEVELOPER_INSTRUCTION)
    (out_dir / "brain-config.toml").write_text(brain_text, encoding="utf-8", newline="\n")
    task_text = arm_mod.task_text_for(arm)
    (out_dir / "launch" / "TASK.md").write_text(task_text, encoding="utf-8", newline="\n")
    world_text = arm_mod.render_world_config_toml(arm_mod.SERVER_NAME, "docker", ["run", "x"],
                                                   "/repo", enabled_tools)
    config_text = arm_mod.render_full_config_toml(brain_text, world_text)
    (out_dir / "launch" / ".codex" / "config.toml").write_text(config_text, encoding="utf-8",
                                                                newline="\n")
    (out_dir / "codex-mcp-list.json").write_text(json.dumps([{"name": arm_mod.SERVER_NAME}]) + "\n",
                                                  encoding="utf-8", newline="\n")
    (out_dir / "mcp-tools.json").write_text(
        json.dumps([{"name": t} for t in enabled_tools]) + "\n", encoding="utf-8", newline="\n")

    def _sha(path):
        import hashlib
        return hashlib.sha256(path.read_bytes()).hexdigest()

    receipt = arm_mod.build_handshake_receipt(
        arm=arm, model="gpt-5.6-sol", codex_version="codex-cli 0.0.0-test",
        codex_path=str(fake_codex), codex_executable_sha256=_sha(fake_codex),
        mcp_tools_observed=enabled_tools, brain_config_sha256=_sha(out_dir / "brain-config.toml"),
        task_sha256=_sha(out_dir / "launch" / "TASK.md"),
        config_sha256=_sha(out_dir / "launch" / ".codex" / "config.toml"),
        codex_mcp_list_sha256=_sha(out_dir / "codex-mcp-list.json"),
        tool_schema_sha256=_sha(out_dir / "mcp-tools.json"),
        host_code_sha256={"/app/world_mcp.py": "0" * 64, "/app/core/miniwob_world.py": "1" * 64},
        image_code_sha256={"/app/world_mcp.py": "0" * 64, "/app/core/miniwob_world.py": "1" * 64})
    receipt_path = out_dir / "handshake-receipt.json"
    expected_path = out_dir / "expected-pins.json"
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
    expected_path.write_text(json.dumps(receipt), encoding="utf-8")
    return receipt_path, expected_path


def test_adapter_over_the_real_m1_transcript_produces_zero_leak_failures(tmp_path):
    """THE DECISIVE REGRESSION TEST (PR #157 adversarial review, 2026-07-24 BLOCKING fix): runs
    the adapter over the REAL, committed capture
    (reports/2026-07-23-gate0-appserver-m1-confirmation/transcript.jsonl) -- not a hand-built
    fixture -- with the mcpToolCall's server/tool patched from the M1 stub's gate0_stub/ping to a
    Gate-0-allowlisted gate0_world/observe pair (the real capture is correct MECHANISM evidence
    but off-allowlist for Gate 0 itself), replayed through the exact same ObservingGate0Client
    classification logic that would run in production, then fed through the FROZEN, unmodified
    check_gate0_codex.audit(). Before the 2026-07-24 fix this asserted leak_failures == [] and
    FAILED (userMessage/agentMessage both flagged forbidden_item) -- proving the bug was real, not
    theoretical."""
    real_path = (arm_mod.REPO_ROOT / "reports" / "2026-07-23-gate0-appserver-m1-confirmation"
                 / "transcript.jsonl")
    client = ObservingGate0Client(send=lambda message: None)
    for line in real_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        entry = json.loads(line)
        if entry.get("direction") != "server_to_client":
            continue
        message = entry["message"]
        params = message.get("params")
        item = params.get("item") if isinstance(params, dict) else None
        if isinstance(item, dict) and item.get("tool") == "ping":
            item["tool"] = "observe"
            item["server"] = "gate0_world"
        client.handle_message(message)

    adapted = adapt_app_server_notifications_to_exec_shape(client.notifications)
    # Sanity: the real capture really does contain the four item types this fix concerns itself
    # with -- if this ever stops being true the test below would pass for the wrong reason.
    raw_types = {n.get("params", {}).get("item", {}).get("type")
                 for n in client.notifications if n.get("method") == "item/completed"}
    assert raw_types == {"userMessage", "reasoning", "mcpToolCall", "agentMessage"}

    transcript_path = tmp_path / "transcript.jsonl"
    from tools.gate0_appserver_arm import write_jsonl
    write_jsonl(transcript_path, adapted)
    receipt_path, expected_path = _fixture_for_audit(tmp_path, arm="red")

    from tools.check_gate0_codex import audit as check_audit
    result = check_audit(transcript_path, receipt_path, expected_path, tmp_path, "red")
    assert result["leak_failures"] == []
    assert result["primitive_action_events"] == 1  # the one real, now-allowlisted mcpToolCall


# ---------------------------------------------------------------------------
# Soft-cap warning (informational) vs the hard 250 breaker (imported, unmodified, sole kill
# authority). Both per-arm soft caps are exercised.
# ---------------------------------------------------------------------------

def test_hard_credit_cap_constant_matches_the_pinned_breaker_ceiling():
    assert HARD_CREDIT_CAP == LIMIT_NORMALIZED_CREDITS == 250


@pytest.mark.parametrize("arm,expected_cap", [("red", 125), ("miniwob", 50)])
def test_per_arm_soft_credit_caps_match_the_prereg_table(arm, expected_cap):
    assert ARM_SOFT_CREDIT_CAPS[arm] == expected_cap


def test_soft_cap_watcher_warns_once_crossing_the_arm_cap_never_kills():
    watcher = SoftCapWatcher(soft_cap=1.0, rate_pin=_RATE_PIN)
    assert watcher.warned is False
    # 10 output tokens * 0.0001 * 1 credit/$ = 0.001 -- under cap.
    watcher.observe({"method": "thread/tokenUsage/updated", "params": {"tokenUsage": {"total": {
        "inputTokens": 0, "cachedInputTokens": 0, "outputTokens": 10, "reasoningOutputTokens": 0,
        "totalTokens": 10}}}})
    assert watcher.warned is False
    # cumulative total now 20000 output tokens -> 2.0 credits, crosses the 1.0 soft cap.
    watcher.observe({"method": "thread/tokenUsage/updated", "params": {"tokenUsage": {"total": {
        "inputTokens": 0, "cachedInputTokens": 0, "outputTokens": 20000, "reasoningOutputTokens": 0,
        "totalTokens": 20000}}}})
    assert watcher.warned is True
    assert watcher.warned_at == pytest.approx(2.0)
    # Watcher has no kill mechanism at all -- it only ever sets `warned`/`warned_at`.
    assert not hasattr(watcher, "tripped")


def test_soft_cap_watcher_ignores_non_usage_messages_and_never_raises():
    watcher = SoftCapWatcher(soft_cap=1.0, rate_pin=_RATE_PIN)
    watcher.observe({"method": "item/completed", "params": {}})
    watcher.observe("not even a dict")
    watcher.observe({"method": "thread/tokenUsage/updated", "params": {}})  # malformed, no total
    assert watcher.warned is False


def test_soft_cap_watcher_with_no_rate_pin_never_warns():
    watcher = SoftCapWatcher(soft_cap=0.0, rate_pin=None)
    watcher.observe({"method": "thread/tokenUsage/updated", "params": {"tokenUsage": {"total": {
        "inputTokens": 999999, "cachedInputTokens": 0, "outputTokens": 0,
        "reasoningOutputTokens": 0, "totalTokens": 999999}}}})
    assert watcher.warned is False


def test_soft_warn_and_hard_kill_wire_together_exactly_like_run_real_combines_them():
    # Mirrors _run_real's `_combined_observer` (guard.observe(message); watcher.observe(message))
    # against the SAME message stream -- proves the soft (per-arm, informational) and hard
    # (imported tools/gate0_credit_breaker ceiling, kill-authoritative) paths coexist correctly:
    # the soft cap warns without killing anything, and only the imported, unmodified hard breaker
    # actually trips at its own ceiling.
    from tools.gate0_appserver_launch import LiveCreditGuard

    tripped = {"called": False}
    guard = LiveCreditGuard(limit=HARD_CREDIT_CAP, stall_timeout_s=2.0, rate_pin=_RATE_PIN,
                             on_trip=lambda exc: tripped.__setitem__("called", True))
    watcher = SoftCapWatcher(soft_cap=ARM_SOFT_CREDIT_CAPS["miniwob"], rate_pin=_RATE_PIN)
    guard.start()

    def _combined_observer(message):
        guard.observe(message)
        watcher.observe(message)

    # Crosses the miniwob soft cap (50) but stays far under the hard cap (250):
    # 600000 output tokens * 0.0001 $/token * 1 credit/$ = 60 credits.
    _combined_observer({"method": "thread/tokenUsage/updated", "params": {"tokenUsage": {"total": {
        "inputTokens": 0, "cachedInputTokens": 0, "outputTokens": 600000,
        "reasoningOutputTokens": 0, "totalTokens": 600000}}}})
    guard.finish()
    guard.join(timeout=5.0)

    assert watcher.warned is True
    assert watcher.warned_at == pytest.approx(60.0)
    assert guard.result["tripped"] is False  # 60 credits is nowhere near the 250 hard ceiling
    assert tripped["called"] is False


# ---------------------------------------------------------------------------
# TOML rendering -- byte-exact reconstruction of tools/run_gate0_codex.ps1's herestrings.
# Regression-pins the two frozen hashes this build hand-verified during development.
# ---------------------------------------------------------------------------

def test_brain_config_toml_matches_the_frozen_pin():
    import hashlib
    text = render_brain_config_toml(
        "gpt-5.6-sol",
        "Use only gate0_world MCP tools. Never use shell, files, web, tool search, connectors, "
        "or other MCP servers.")
    assert hashlib.sha256(text.encode("utf-8")).hexdigest() == (
        "ab7e54c1785f5d8be4352bbe0f85edb37cda68cf56df2128d61df025c1041fc3")


@pytest.mark.parametrize("arm,expected_sha", [
    ("red", "306751c34627f6d5c6a8c94ac2f714e358f0dcbc5867866c273e434de7f4b7c4"),
    ("miniwob", "845638c874df2f2de2adaebdd1d6c9318c689a46d0032fa76a9393e1e47512d1"),
])
def test_task_text_matches_the_frozen_pin(arm, expected_sha):
    import hashlib
    assert hashlib.sha256(task_text_for(arm).encode("utf-8")).hexdigest() == expected_sha


def test_world_config_toml_and_full_config_are_crlf_internal_lf_terminal():
    # Matches tools/run_gate0_codex.ps1's own herestring byte shape (verified during this build
    # via raw source-file byte inspection): internal lines joined by CRLF, one trailing bare LF.
    text = render_world_config_toml("gate0_world", "docker", ["run", "x"], "/repo", ["observe"])
    assert "\r\n" in text
    assert text.endswith("\n") and not text.endswith("\r\n\r\n")
    brain = render_brain_config_toml("gpt-5.6-sol", "x")
    full = render_full_config_toml(brain, text)
    assert full == brain + "\n" + text


def test_world_config_toml_sets_generous_timeouts_for_the_lazy_boot_world_server():
    # app-server-necessary addition (the exec path never needed this): gate0_world is lazy-boot --
    # the first real MCP tool call inside the paid turn boots PyBoy+ROM (~30-40s). codex's
    # per-call/startup default is otherwise null (unmeasured), so pin a generous, confirmed-real
    # 90s margin (codex-cli 0.144.3 mcp_servers.<name>.tool_timeout_sec/startup_timeout_sec).
    text = render_world_config_toml("gate0_world", "docker", ["run", "x"], "/repo", ["observe"])
    # Exact CRLF-joined lines within the [mcp_servers.gate0_world] block (matches the file's own
    # CRLF-internal/bare-LF-terminal join convention -- see the CRLF test above), not just any
    # substring match.
    assert "\r\ntool_timeout_sec = 90\r\nstartup_timeout_sec = 90\n" in text


# ---------------------------------------------------------------------------
# Docker MCP args -- per-arm mount/image shape (BY IMMUTABLE IMAGE ID).
# ---------------------------------------------------------------------------

def test_build_docker_mcp_args_red_uses_the_pinned_mounts_and_game(tmp_path):
    args = build_docker_mcp_args("red", ARM_IMAGE_IDS["red"], tmp_path / "world",
                                  repo_root=tmp_path)
    assert args[0:5] == ["run", "-i", "--rm", "--network", "none"]
    assert ARM_IMAGE_IDS["red"] in args
    assert "--game" in args and args[args.index("--game") + 1] == "pokemon_red"
    assert "--keep-frames" in args
    assert any("red_start.state,readonly" in a for a in args)


def test_build_docker_mcp_args_miniwob_uses_the_pinned_seeds_file(tmp_path):
    args = build_docker_mcp_args("miniwob", ARM_IMAGE_IDS["miniwob"], tmp_path / "world",
                                  repo_root=tmp_path)
    assert "--game" in args and args[args.index("--game") + 1] == "miniwob_click_checkboxes"
    assert any("seeds.json,readonly" in a for a in args)
    assert "--keep-frames" not in args


def test_build_docker_mcp_args_rejects_unknown_arm(tmp_path):
    with pytest.raises(ValueError):
        build_docker_mcp_args("chess", "sha256:" + "0" * 64, tmp_path / "world",
                               repo_root=tmp_path)


def test_build_docker_mcp_args_world_mount_source_is_absolute_for_a_relative_world_dir():
    # Regression (2026-07-24): docker on Windows rejects a relative bind-mount source
    # ("runs\\gate0_paid\\red\\world ... is not a valid Windows path"). A relative --out-dir
    # yields a relative world_dir; the /app/world mount source MUST be resolved to absolute.
    import os
    from pathlib import Path
    rel_world = Path("runs/gate0_paid/red/world")
    assert not rel_world.is_absolute()
    for arm in ("red", "miniwob"):
        args = build_docker_mcp_args(arm, ARM_IMAGE_IDS[arm], rel_world, repo_root=Path("."))
        world_mount = next(a for a in args if "target=/app/world" in a)
        src = world_mount.split("source=", 1)[1].rsplit(",target=", 1)[0]
        assert os.path.isabs(src), f"{arm}: world mount source not absolute: {src!r}"


def test_resolve_isolated_codex_home_is_absolute_for_a_relative_out_dir():
    # Regression (2026-07-24): the codex child runs with cwd=out_dir, so a relative CODEX_HOME
    # (out_dir/'codex-home') resolves against out_dir again -> "does not exist" -> codex exits ->
    # initialize times out. The derived home MUST be absolute.
    import os
    from pathlib import Path
    rel_out = Path("runs/gate0_paid/red")
    assert not rel_out.is_absolute()
    home = resolve_isolated_codex_home(None, rel_out)
    assert os.path.isabs(home), f"derived codex_home not absolute: {home!r}"
    assert home.replace("\\", "/").endswith("runs/gate0_paid/red/codex-home")
    # An explicit path is honored verbatim (caller's responsibility to pass absolute).
    assert resolve_isolated_codex_home("C:/x/home", rel_out) == "C:/x/home"


# ---------------------------------------------------------------------------
# CLI validation.
# ---------------------------------------------------------------------------

def test_model_required_for_a_real_run(tmp_path):
    with pytest.raises(SystemExit):
        main(["--arm", "red", "--out-dir", str(tmp_path / "out")])


def test_model_latest_alias_is_rejected(tmp_path):
    with pytest.raises(SystemExit):
        main(["--arm", "red", "--model", "gpt-5.6-sol-latest", "--out-dir", str(tmp_path / "out"),
              "--credit-rate-pin", str(tmp_path / "pin.json")])


def test_credit_rate_pin_required_for_a_real_run(tmp_path):
    with pytest.raises(SystemExit):
        main(["--arm", "red", "--model", "gpt-5.6-sol", "--out-dir", str(tmp_path / "out")])


def test_credit_rate_pin_rejected_for_dry_run(tmp_path):
    with pytest.raises(SystemExit):
        main(["--arm", "red", "--out-dir", str(tmp_path / "out"), "--dry-run",
              "--credit-rate-pin", str(tmp_path / "pin.json")])


def test_stall_timeout_may_only_tighten_never_loosen(tmp_path):
    with pytest.raises(SystemExit):
        main(["--arm", "red", "--out-dir", str(tmp_path / "out"), "--dry-run",
              "--stall-timeout-s", "999999"])


def test_wall_clock_may_only_tighten_never_loosen(tmp_path):
    with pytest.raises(SystemExit):
        main(["--arm", "red", "--out-dir", str(tmp_path / "out"), "--dry-run",
              "--wall-clock-s", "999999"])


def test_unknown_arm_is_rejected(tmp_path):
    with pytest.raises(SystemExit):
        main(["--arm", "chess", "--out-dir", str(tmp_path / "out"), "--dry-run"])


def test_validate_args_forces_out_dir_absolute(tmp_path, monkeypatch):
    # Regression (adversarial review of PR #163, correction 4): out_dir used to stay whatever
    # relative string argparse handed back, so build_docker_mcp_args' `world_dir.resolve()`
    # (world_dir is derived from out_dir) resolved against the PROCESS'S CURRENT cwd -- the same
    # launch spec run from a different cwd would silently render a DIFFERENT config.toml (a
    # different absolute mount source), the exact bug class the exec path's
    # Confirm-PaidExecSignature caught and this path did not.
    from pathlib import Path
    monkeypatch.chdir(tmp_path)
    parser = arm_mod.build_arg_parser()
    args = parser.parse_args(["--arm", "red", "--out-dir", "relative_out", "--dry-run"])
    assert not Path(args.out_dir).is_absolute()
    arm_mod._validate_args(parser, args)
    assert Path(args.out_dir).is_absolute()
    assert Path(args.out_dir) == (tmp_path / "relative_out").resolve()


def test_main_with_a_relative_out_dir_still_resolves_the_world_mount_absolutely(tmp_path, monkeypatch):
    # End-to-end companion to the --validate-args unit test above: the concrete symptom
    # correction 4 closes is build_docker_mcp_args' `world_dir.resolve()` (called from
    # --seam-check --with-tools-list and _run_real) anchoring on the process cwd instead of the
    # launch spec. Drive it through main() with a relative --out-dir and confirm the world mount
    # source captured by the (mocked) docker call is absolute and correct regardless of cwd.
    import os
    from pathlib import Path
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(arm_mod, "resolve_docker_path", lambda: "docker")
    monkeypatch.setattr(arm_mod, "docker_image_inspect_id",
                         lambda docker_path, image_ref: ARM_IMAGE_IDS["red"])
    captured_mcp_args = {}

    def _fake_tools_list(docker_path, mcp_args):
        captured_mcp_args["value"] = mcp_args
        return [{"name": t} for t in TOOLS["red"]]
    monkeypatch.setattr(arm_mod, "docker_tools_list", _fake_tools_list)

    exit_code = main(["--arm", "red", "--out-dir", "relative_out2", "--seam-check",
                       "--with-tools-list"])
    assert exit_code == 0
    world_mount = next(a for a in captured_mcp_args["value"] if "target=/app/world" in a)
    src = world_mount.split("source=", 1)[1].rsplit(",target=", 1)[0]
    assert os.path.isabs(src)
    assert Path(src) == (tmp_path / "relative_out2" / "world").resolve()


# ---------------------------------------------------------------------------
# agent_metrics.json builder -- human_* copy-vs-missing (the MiniWoB PENDING caveat).
# ---------------------------------------------------------------------------

def test_build_agent_metrics_copies_human_fields_when_present(tmp_path):
    human_path = tmp_path / "human_metrics.json"
    human_path.write_text(json.dumps({"wall_clock_s": 233.288, "primitive_actions": 271}),
                           encoding="utf-8")
    metrics = build_agent_metrics(arm="red", mode="paid_gate0", wall_clock_s=100.0,
                                   primitive_actions=50, cost_usd=1.0, normalized_credits=25.0,
                                   human_metrics_path=human_path)
    assert metrics["human_wall_clock_s"] == 233.288
    assert metrics["human_primitive_actions"] == 271


def test_build_agent_metrics_reports_missing_human_file_honestly_not_a_crash(tmp_path):
    # The MiniWoB paid-seed human baseline is PENDING (captured by David AFTER Arm W) -- this must
    # degrade to an honest null, never fabricate a number or raise.
    metrics = build_agent_metrics(arm="miniwob", mode="paid_gate0", wall_clock_s=10.0,
                                   primitive_actions=5, cost_usd=0.1, normalized_credits=2.5,
                                   human_metrics_path=tmp_path / "does-not-exist.json")
    assert metrics["human_wall_clock_s"] is None
    assert metrics["human_primitive_actions"] is None
    assert "not found" in metrics["human_source_note"]


def test_build_agent_metrics_with_no_human_path_at_all(tmp_path):
    metrics = build_agent_metrics(arm="red", mode="dry_run", wall_clock_s=1.0,
                                   primitive_actions=1, cost_usd=0.0, normalized_credits=0.0,
                                   human_metrics_path=None)
    assert metrics["human_wall_clock_s"] is None


# ---------------------------------------------------------------------------
# wake_boundary.json -- write-once, never clobbered by a second arm.
# ---------------------------------------------------------------------------

def test_ensure_wake_boundary_artifact_writes_once_and_is_idempotent(tmp_path):
    path = tmp_path / "wake_boundary.json"
    first = ensure_wake_boundary_artifact(path)
    written_bytes = path.read_bytes()
    second = ensure_wake_boundary_artifact(path)
    assert path.read_bytes() == written_bytes  # not rewritten
    assert first == second
    assert first["status"] == "DEFERRED"
    assert first["kind"] == "exact_wake_boundary"


# ---------------------------------------------------------------------------
# run_gate0_arm_turn against the MultiCallStubAppServerPeer directly (no CLI involved).
# ---------------------------------------------------------------------------

def test_run_gate0_arm_turn_collects_every_notification_across_many_tool_calls():
    peer = MultiCallStubAppServerPeer(tool_name="observe", call_count=4)
    client = ObservingGate0Client(send=peer.send)
    peer.client = client
    result = run_gate0_arm_turn(client, cwd="/tmp/x", task_text="do the thing", wall_clock_s=5.0)
    assert result["ended"] is True
    completed = [n for n in client.notifications if n.get("method") == "item/completed"]
    assert len(completed) == 4
    turn_completed = [n for n in client.notifications if n.get("method") == "turn/completed"]
    assert len(turn_completed) == 1


# ---------------------------------------------------------------------------
# Seam-check -- docker image inspect only, mocked. Never invokes a real docker process.
# ---------------------------------------------------------------------------

def test_seam_check_passes_when_image_id_matches_the_pin(tmp_path, monkeypatch):
    monkeypatch.setattr(arm_mod, "resolve_docker_path", lambda: "docker")
    monkeypatch.setattr(arm_mod, "docker_image_inspect_id",
                         lambda docker_path, image_ref: ARM_IMAGE_IDS["red"])
    out_dir = tmp_path / "out"
    exit_code = main(["--arm", "red", "--out-dir", str(out_dir), "--seam-check"])
    assert exit_code == 0
    result = json.loads((out_dir / "seam_check.json").read_text(encoding="utf-8"))
    assert result["ok"] is True
    assert result["checks"]["image_id_matches_pin"]["ok"] is True


def test_seam_check_fails_when_image_id_does_not_match_the_pin(tmp_path, monkeypatch):
    monkeypatch.setattr(arm_mod, "resolve_docker_path", lambda: "docker")
    monkeypatch.setattr(arm_mod, "docker_image_inspect_id",
                         lambda docker_path, image_ref: "sha256:" + "0" * 64)
    out_dir = tmp_path / "out"
    exit_code = main(["--arm", "red", "--out-dir", str(out_dir), "--seam-check"])
    assert exit_code == 1
    result = json.loads((out_dir / "seam_check.json").read_text(encoding="utf-8"))
    assert result["ok"] is False


def test_seam_check_fails_closed_when_docker_is_unavailable(tmp_path, monkeypatch):
    def _boom():
        raise RuntimeError("docker executable not found on PATH")
    monkeypatch.setattr(arm_mod, "resolve_docker_path", _boom)
    out_dir = tmp_path / "out"
    exit_code = main(["--arm", "red", "--out-dir", str(out_dir), "--seam-check"])
    assert exit_code == 1


def test_seam_check_with_tools_list_uses_the_mocked_handshake_never_real_docker(tmp_path, monkeypatch):
    monkeypatch.setattr(arm_mod, "resolve_docker_path", lambda: "docker")
    monkeypatch.setattr(arm_mod, "docker_image_inspect_id",
                         lambda docker_path, image_ref: ARM_IMAGE_IDS["red"])
    monkeypatch.setattr(arm_mod, "docker_tools_list",
                         lambda docker_path, mcp_args: [{"name": t} for t in TOOLS["red"]])

    def _boom(*a, **kw):
        raise AssertionError("real subprocess.run must never be called in this test")
    monkeypatch.setattr(subprocess, "run", _boom)

    out_dir = tmp_path / "out"
    exit_code = main(["--arm", "red", "--out-dir", str(out_dir), "--seam-check",
                       "--with-tools-list"])
    assert exit_code == 0
    result = json.loads((out_dir / "seam_check.json").read_text(encoding="utf-8"))
    assert result["checks"]["tools_list_matches_allowlist"]["ok"] is True


def test_seam_check_with_tools_list_writes_a_reproducible_mcp_tools_json_and_hash(tmp_path, monkeypatch):
    # 2026-07-25 fix (adversarial review of PR #163, correction 1): --seam-check --with-tools-list
    # used to only report tool NAMES inline and never write mcp-tools.json or compute any hash, so
    # the .appserver.json fixtures' provenance notes describing a reproducible tool_schema_sha256
    # recipe via this exact invocation were not actually true of this code. Now it must write
    # mcp-tools.json with the SAME serialization _run_real uses (json.dumps(tools) + "\n") and
    # record its sha256 in seam_check.json.
    import hashlib
    monkeypatch.setattr(arm_mod, "resolve_docker_path", lambda: "docker")
    monkeypatch.setattr(arm_mod, "docker_image_inspect_id",
                         lambda docker_path, image_ref: ARM_IMAGE_IDS["red"])
    tools = [{"name": t} for t in TOOLS["red"]]
    monkeypatch.setattr(arm_mod, "docker_tools_list", lambda docker_path, mcp_args: tools)

    out_dir = tmp_path / "out"
    exit_code = main(["--arm", "red", "--out-dir", str(out_dir), "--seam-check",
                       "--with-tools-list"])
    assert exit_code == 0

    mcp_tools_path = out_dir / "mcp-tools.json"
    assert mcp_tools_path.is_file()
    expected_bytes = json.dumps(tools) + "\n"
    assert mcp_tools_path.read_text(encoding="utf-8") == expected_bytes
    expected_sha = hashlib.sha256(expected_bytes.encode("utf-8")).hexdigest()

    result = json.loads((out_dir / "seam_check.json").read_text(encoding="utf-8"))
    assert result["tool_schema_sha256"] == expected_sha


def test_seam_check_without_tools_list_writes_no_mcp_tools_json_or_hash(tmp_path, monkeypatch):
    # Plain --seam-check (no --with-tools-list) must not claim a tool_schema_sha256 it never
    # derived.
    monkeypatch.setattr(arm_mod, "resolve_docker_path", lambda: "docker")
    monkeypatch.setattr(arm_mod, "docker_image_inspect_id",
                         lambda docker_path, image_ref: ARM_IMAGE_IDS["red"])
    out_dir = tmp_path / "out"
    exit_code = main(["--arm", "red", "--out-dir", str(out_dir), "--seam-check"])
    assert exit_code == 0
    assert not (out_dir / "mcp-tools.json").exists()
    result = json.loads((out_dir / "seam_check.json").read_text(encoding="utf-8"))
    assert "tool_schema_sha256" not in result


# ---------------------------------------------------------------------------
# Low-level docker/codex probe functions -- exercised with a monkeypatched subprocess.run, never a
# real process.
# ---------------------------------------------------------------------------

class _FakeCompleted:
    def __init__(self, stdout="", stderr="", returncode=0):
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode


def test_docker_image_inspect_id_parses_the_id(monkeypatch):
    monkeypatch.setattr(subprocess, "run",
                         lambda *a, **kw: _FakeCompleted(stdout="sha256:" + "a" * 64 + "\n"))
    result = arm_mod.docker_image_inspect_id("docker", "some-tag")
    assert result == "sha256:" + "a" * 64


def test_docker_image_inspect_id_times_out_cleanly(monkeypatch):
    def _boom(*a, **kw):
        raise subprocess.TimeoutExpired(cmd="docker", timeout=1)
    monkeypatch.setattr(subprocess, "run", _boom)
    with pytest.raises(RuntimeError, match="timed out"):
        arm_mod.docker_image_inspect_id("docker", "some-tag")


def test_docker_image_inspect_id_fails_closed_on_nonzero_exit(monkeypatch):
    monkeypatch.setattr(subprocess, "run",
                         lambda *a, **kw: _FakeCompleted(stdout="", stderr="no such image",
                                                          returncode=1))
    with pytest.raises(RuntimeError):
        arm_mod.docker_image_inspect_id("docker", "some-tag")


# ---------------------------------------------------------------------------
# Expected-pins resolution -- closes the app-server expected-pins gap: the first real Gate 0 Arm R
# app-server run reported a BENIGN CONSTANCY_BREACH (pin_mismatch on config_sha256/
# codex_mcp_list_sha256/tool_schema_sha256) because check_gate0_codex.audit() was handed the raw,
# static .appserver.json fixture -- whose two launch-invocation-dependent fields hold a literal
# CONSTRAINT marker string a real receipt can never equal -- directly as `expected_pins`.
# ---------------------------------------------------------------------------

def _load_real_appserver_fixture(arm):
    path = arm_mod.REPO_ROOT / "eval" / "fixtures" / f"gate0_expected_pins_{arm}.appserver.json"
    return json.loads(path.read_text(encoding="utf-8"))


def test_resolve_expected_pins_substitutes_only_the_two_launch_dependent_fields():
    base = {
        "schema_version": 2, "planned_model": "gpt-5.6-sol",
        "config_sha256": LAUNCH_INVOCATION_DEPENDENT_MARKER,
        "codex_mcp_list_sha256": LAUNCH_INVOCATION_DEPENDENT_MARKER,
        "tool_schema_sha256": "a" * 64,
    }
    resolved = resolve_expected_pins(base, config_sha256="b" * 64, codex_mcp_list_sha256="c" * 64)
    assert resolved["config_sha256"] == "b" * 64
    assert resolved["codex_mcp_list_sha256"] == "c" * 64
    assert resolved["tool_schema_sha256"] == "a" * 64  # untouched
    assert resolved["planned_model"] == "gpt-5.6-sol"  # untouched
    assert base["config_sha256"] == LAUNCH_INVOCATION_DEPENDENT_MARKER  # base dict not mutated


@pytest.mark.parametrize("arm", ["red", "miniwob"])
def test_resolve_expected_pins_works_against_the_real_committed_fixture(arm):
    base = _load_real_appserver_fixture(arm)
    resolved = resolve_expected_pins(base, config_sha256="d" * 64, codex_mcp_list_sha256="e" * 64)
    assert resolved["config_sha256"] == "d" * 64
    assert resolved["codex_mcp_list_sha256"] == "e" * 64
    # every other PIN_FIELD is the real, committed, independently-frozen value -- untouched:
    for field in checker.PIN_FIELDS:
        if field in ("config_sha256", "codex_mcp_list_sha256"):
            continue
        assert resolved[field] == base[field]


@pytest.mark.parametrize("field", ["config_sha256", "codex_mcp_list_sha256"])
def test_resolve_expected_pins_refuses_to_overwrite_an_already_real_value(field):
    # Defensive: if a future edit ever puts a real hash in the fixture instead of the documented
    # marker, this must fail loud, not silently stop checking that field.
    base = {"config_sha256": LAUNCH_INVOCATION_DEPENDENT_MARKER,
            "codex_mcp_list_sha256": LAUNCH_INVOCATION_DEPENDENT_MARKER}
    base[field] = "f" * 64
    with pytest.raises(ValueError, match="not the documented"):
        resolve_expected_pins(base, config_sha256="b" * 64, codex_mcp_list_sha256="c" * 64)


@pytest.mark.parametrize("arm", ["red", "miniwob"])
def test_resolved_real_fixture_produces_zero_pin_mismatches_for_a_matching_receipt(arm):
    """THE decisive POSITIVE proof: a receipt whose fields genuinely match the real, committed
    .appserver.json fixture (post-resolution for the two launch-dependent fields) audits clean
    against check_gate0_codex._expected_failures -- the exact check that produced the false
    CONSTANCY_BREACH on the real, completed Arm R app-server run before this fix."""
    base = _load_real_appserver_fixture(arm)
    receipt = {f: base[f] for f in checker.PIN_FIELDS
               if f not in ("config_sha256", "codex_mcp_list_sha256")}
    receipt["config_sha256"] = "1" * 64
    receipt["codex_mcp_list_sha256"] = "2" * 64
    resolved = resolve_expected_pins(base, config_sha256=receipt["config_sha256"],
                                     codex_mcp_list_sha256=receipt["codex_mcp_list_sha256"])
    assert checker._expected_failures(receipt, resolved) == []


@pytest.mark.parametrize("arm", ["red", "miniwob"])
def test_resolved_real_fixture_still_catches_a_genuinely_wrong_tool_inventory(arm):
    """THE decisive NEGATIVE proof (build-spec requirement 4): a genuinely different
    tool_schema_sha256 -- representing a real, different tool inventory, exactly the kind of drift
    this pin exists to catch -- MUST still produce pin_mismatch:tool_schema_sha256 against the
    fixed, real fixture. Proves the fix (re-deriving tool_schema_sha256 for the app-server's own
    serialization) did not make the check vacuous."""
    base = _load_real_appserver_fixture(arm)
    receipt = {f: base[f] for f in checker.PIN_FIELDS
               if f not in ("config_sha256", "codex_mcp_list_sha256")}
    receipt["config_sha256"] = "1" * 64
    receipt["codex_mcp_list_sha256"] = "2" * 64
    receipt["tool_schema_sha256"] = "9" * 64  # genuinely wrong -- a different tool inventory
    resolved = resolve_expected_pins(base, config_sha256=receipt["config_sha256"],
                                     codex_mcp_list_sha256=receipt["codex_mcp_list_sha256"])
    assert checker._expected_failures(receipt, resolved) == ["pin_mismatch:tool_schema_sha256"]


@pytest.mark.parametrize("arm", ["red", "miniwob"])
def test_resolved_real_fixture_still_catches_a_genuinely_wrong_model(arm):
    # A second, independent negative case (not just tool_schema_sha256): any of the 18
    # non-launch-dependent PIN_FIELDS still catches real drift too.
    base = _load_real_appserver_fixture(arm)
    receipt = {f: base[f] for f in checker.PIN_FIELDS
               if f not in ("config_sha256", "codex_mcp_list_sha256")}
    receipt["config_sha256"] = "1" * 64
    receipt["codex_mcp_list_sha256"] = "2" * 64
    receipt["planned_model"] = "gpt-wrong-model"
    resolved = resolve_expected_pins(base, config_sha256=receipt["config_sha256"],
                                     codex_mcp_list_sha256=receipt["codex_mcp_list_sha256"])
    assert checker._expected_failures(receipt, resolved) == ["pin_mismatch:planned_model"]


def test_full_audit_via_resolved_expected_pins_reports_zero_pin_mismatch(tmp_path):
    """Integration proof: resolve_expected_pins() plumbed through the real, unmodified
    check_gate0_codex.audit() end to end reports zero pin_mismatch:* constancy failures -- the
    exact three fields (config_sha256, codex_mcp_list_sha256, tool_schema_sha256) the real
    completed Arm R app-server run's first audit incorrectly flagged."""
    out_dir = tmp_path / "out"
    receipt_path, _ = _fixture_for_audit(out_dir, arm="red")
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))

    base_expected = dict(receipt)  # stand-in for the 18 real, independently-frozen pins
    base_expected["config_sha256"] = LAUNCH_INVOCATION_DEPENDENT_MARKER
    base_expected["codex_mcp_list_sha256"] = LAUNCH_INVOCATION_DEPENDENT_MARKER
    resolved = resolve_expected_pins(base_expected, config_sha256=receipt["config_sha256"],
                                     codex_mcp_list_sha256=receipt["codex_mcp_list_sha256"])
    resolved_path = out_dir / "expected-pins.resolved.json"
    resolved_path.write_text(json.dumps(resolved), encoding="utf-8")

    transcript_path = out_dir / "transcript.jsonl"
    transcript_path.write_text("", encoding="utf-8")  # no real transcript needed for this proof
    from tools.check_gate0_codex import audit as check_audit
    result = check_audit(transcript_path, receipt_path, resolved_path, out_dir, "red")
    pin_mismatches = [f for f in result["constancy_failures"] if f.startswith("pin_mismatch:")]
    assert pin_mismatches == []
    verify_launch_signature_unchanged(receipt, out_dir)  # must not raise -- artifacts untouched


def test_verify_launch_signature_unchanged_passes_when_artifacts_match_the_receipt(tmp_path):
    import hashlib
    (tmp_path / "launch" / ".codex").mkdir(parents=True)
    (tmp_path / "launch" / ".codex" / "config.toml").write_text("config", encoding="utf-8")
    (tmp_path / "codex-mcp-list.json").write_text("[]", encoding="utf-8")
    receipt = {
        "config_sha256": hashlib.sha256(b"config").hexdigest(),
        "codex_mcp_list_sha256": hashlib.sha256(b"[]").hexdigest(),
    }
    verify_launch_signature_unchanged(receipt, tmp_path)  # must not raise


def test_verify_launch_signature_unchanged_fails_loud_when_config_drifted(tmp_path):
    (tmp_path / "launch" / ".codex").mkdir(parents=True)
    (tmp_path / "launch" / ".codex" / "config.toml").write_text("config", encoding="utf-8")
    (tmp_path / "codex-mcp-list.json").write_text("[]", encoding="utf-8")
    receipt = {"config_sha256": "0" * 64, "codex_mcp_list_sha256": "0" * 64}  # stale/wrong
    with pytest.raises(SystemExit, match="launch signature mismatch"):
        verify_launch_signature_unchanged(receipt, tmp_path)


def test_verify_launch_signature_unchanged_fails_loud_when_mcp_list_drifted(tmp_path):
    import hashlib
    (tmp_path / "launch" / ".codex").mkdir(parents=True)
    (tmp_path / "launch" / ".codex" / "config.toml").write_text("config", encoding="utf-8")
    (tmp_path / "codex-mcp-list.json").write_text("[]", encoding="utf-8")
    receipt = {"config_sha256": hashlib.sha256(b"config").hexdigest(),
               "codex_mcp_list_sha256": "0" * 64}  # stale/wrong
    with pytest.raises(SystemExit, match="launch signature mismatch"):
        verify_launch_signature_unchanged(receipt, tmp_path)


# ---------------------------------------------------------------------------
# _finalize_real_run -- the ordering fix (PR #163 adversarial review, correction 5): a launch-
# signature mismatch must never leave a spent paid run with no agent_metrics.json/run-receipt.json
# (which would make it both unscorable AND unretryable, since refuse_if_already_completed already
# sees transcript.raw_appserver.jsonl on disk from the start of the turn).
# ---------------------------------------------------------------------------

def _finalize_kwargs(out_dir, receipt, receipt_path, transcript_path, human_path):
    return dict(receipt=receipt, receipt_path=receipt_path, transcript_path=transcript_path,
                out_dir=out_dir, arm="red", wall_clock_s=12.0, credits_result={},
                rate_pin=_RATE_PIN, watcher=SoftCapWatcher(soft_cap=100.0, rate_pin=None),
                auth_note="test", model="gpt-5.6-sol", human_path=human_path)


def test_finalize_real_run_writes_metrics_and_receipt_even_on_signature_mismatch(tmp_path, monkeypatch):
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    transcript_path = out_dir / "transcript.jsonl"
    transcript_path.write_text("", encoding="utf-8")
    receipt = {"config_sha256": "0" * 64, "codex_mcp_list_sha256": "0" * 64,
               "world_image_id": "sha256:" + "a" * 64}
    receipt_path = out_dir / "handshake-receipt.json"
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")

    def _boom(receipt, out_dir):
        raise SystemExit("launch signature mismatch: fixture-injected drift")
    monkeypatch.setattr(arm_mod, "verify_launch_signature_unchanged", _boom)

    kwargs = _finalize_kwargs(out_dir, receipt, receipt_path, transcript_path,
                               tmp_path / "missing_human.json")
    with pytest.raises(SystemExit, match="launch signature mismatch"):
        arm_mod._finalize_real_run(**kwargs)

    # The whole point of the fix: both artifacts exist despite the raised SystemExit.
    assert (out_dir / "agent_metrics.json").is_file()
    assert (out_dir / "run-receipt.json").is_file()
    run_receipt = json.loads((out_dir / "run-receipt.json").read_text(encoding="utf-8"))
    assert run_receipt["audit_overall"] == "LAUNCH_SIGNATURE_MISMATCH"
    # No expected-pins resolution was attempted against the drifted/tampered config.
    assert not (out_dir / "expected-pins.resolved.json").exists()


def test_finalize_real_run_success_path_still_resolves_pins_and_scores(tmp_path, monkeypatch):
    arm = "red"
    base = _load_real_appserver_fixture(arm)
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    receipt = {f: base[f] for f in checker.PIN_FIELDS
               if f not in ("config_sha256", "codex_mcp_list_sha256")}
    receipt["config_sha256"] = "1" * 64
    receipt["codex_mcp_list_sha256"] = "2" * 64
    receipt_path = out_dir / "handshake-receipt.json"
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
    transcript_path = out_dir / "transcript.jsonl"
    transcript_path.write_text("", encoding="utf-8")

    monkeypatch.setattr(arm_mod, "verify_launch_signature_unchanged", lambda receipt, out_dir: None)

    kwargs = _finalize_kwargs(out_dir, receipt, receipt_path, transcript_path,
                               tmp_path / "missing_human.json")
    result = arm_mod._finalize_real_run(**kwargs)

    resolved = json.loads((out_dir / "expected-pins.resolved.json").read_text(encoding="utf-8"))
    assert checker._expected_failures(receipt, resolved) == []
    run_receipt = json.loads((out_dir / "run-receipt.json").read_text(encoding="utf-8"))
    assert run_receipt["audit_overall"] != "LAUNCH_SIGNATURE_MISMATCH"
    assert (out_dir / "agent_metrics.json").is_file()
    assert result["run_receipt"] == run_receipt
