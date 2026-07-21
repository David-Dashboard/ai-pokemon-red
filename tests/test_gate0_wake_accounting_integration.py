"""End-to-end proof that fixing tools/check_gate0_codex.py::audit()'s wake accounting actually
unblocks eval/score_gate0.py's verdict (reports/2026-07-21-gate0-readiness-final.md section 4:
"a genuinely successful paid run, launched today, would still score INSUFFICIENT_DATA/
INSUFFICIENT_SOURCE -- not PASS -- regardless of brain performance"). Builds a minimal synthetic
transcript per arm, runs the REAL audit() (not a hand-typed stand-in), writes agent_metrics.json/
human_metrics.json/wake_boundary.json/live_breaker.json via the actual tools this PR ships
(build_agent_metrics, gate0_wake_boundary.dry_run_synthetic, gate0_credit_breaker.dry_run_synthetic),
pins them exactly like a real gate0_*_source_pins.json manifest would, and drives
eval.score_gate0._verify_sources()/score() for real. Everything is $0 and synthetic -- no codex
exec, no paid run -- per the wake-accounting gap's own ruling: the MECHANISM is closable and
testable today, only the numeric value for a real arm's run is a post-run output.
"""
from __future__ import annotations

import hashlib
import json

import eval.score_gate0 as scorer
import tools.check_gate0_codex as checker
import tools.gate0_credit_breaker as breaker
import tools.gate0_wake_boundary as wake_boundary
from tools.check_gate0_codex import SERVER, TOOLS, audit as audit_codex

WAKES = {"red": 10, "miniwob": 5}
_USAGE = {"input_tokens": 12, "cached_input_tokens": 4, "output_tokens": 5, "reasoning_output_tokens": 1}


def _write(path, data: bytes) -> str:
    path.write_bytes(data)
    return hashlib.sha256(data).hexdigest()


def _build_arm_transcript(tmp_dir, arm: str):
    """Same shape as tests/test_check_gate0_codex.py's `_fixture()` helper -- a clean, self-
    consistent receipt/expected-pins/artifacts_dir plus a transcript with WAKES[arm] real
    turn.completed decisions, each preceded by an allowlisted mcp_tool_call. No peer_receipt is
    exercised here (peer cross-arm constancy is a separate, already-tested mechanism -- PR #96's
    compare_constancy -- and orthogonal to the wake-accounting fix this test proves)."""
    artifacts = tmp_dir / arm
    (artifacts / "launch" / ".codex").mkdir(parents=True)
    codex = artifacts / "codex.exe"
    files = {
        codex: b"synthetic-codex",
        artifacts / "brain-config.toml": b"model='gpt-5.6-sol'\n",
        artifacts / "launch" / "TASK.md": b"synthetic task\n",
        artifacts / "launch" / ".codex" / "config.toml": b"synthetic config\n",
        artifacts / "codex-mcp-list.json": b'[{"name":"gate0_world"}]\n',
        artifacts / "mcp-tools.json": (json.dumps([{"name": name} for name in TOOLS[arm]]) + "\n").encode(),
    }
    hashes = {path: _write(path, data) for path, data in files.items()}
    receipt = {
        "schema_version": 2, "arm": arm,
        "readiness": "NO_GO_INSUFFICIENT_WAKES", "paid_execution_enabled": False,
        "auth_method": "chatgpt", "planned_model": "gpt-5.6-sol",
        "codex_version": "codex-cli 0.144.3", "codex_path": str(codex),
        "codex_executable_sha256": hashes[codex],
        "critical_config_transport": "explicit_cli_overrides",
        "mcp_servers_observed": [SERVER], "mcp_tools_observed": TOOLS[arm],
        "brain_config_sha256": hashes[artifacts / "brain-config.toml"],
        "task_sha256": hashes[artifacts / "launch" / "TASK.md"],
        "config_sha256": hashes[artifacts / "launch" / ".codex" / "config.toml"],
        "codex_mcp_list_sha256": hashes[artifacts / "codex-mcp-list.json"],
        "tool_schema_sha256": hashes[artifacts / "mcp-tools.json"],
        "world_image_tag": "miniwob-world" if arm == "miniwob" else "gb-mcp-world",
        "world_image_id": "sha256:" + "0" * 64,
        "host_code_sha256": {"/app/world_mcp.py": "1" * 64, "/app/core/miniwob_world.py": "2" * 64},
        "image_code_sha256": {"/app/world_mcp.py": "1" * 64, "/app/core/miniwob_world.py": "2" * 64},
    }
    receipt_path = artifacts / "handshake-receipt.json"
    expected_path = artifacts / "expected-pins.json"
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
    expected_path.write_text(json.dumps(receipt), encoding="utf-8")
    events = [{"type": "thread.started"}]
    for _ in range(WAKES[arm]):
        events.append({"type": "item.completed", "item": {
            "type": "mcp_tool_call", "server": SERVER, "tool": "observe"}})
        events.append({"type": "turn.completed", "usage": dict(_USAGE)})
    transcript_path = artifacts / "transcript.jsonl"
    transcript_path.write_text("".join(json.dumps(e) + "\n" for e in events), encoding="utf-8")
    return transcript_path, receipt_path, expected_path, artifacts


def _red_oracle():
    return [
        {"watch": {"party": 0, "in_battle": 0, "map": 38, "x": 3, "y": 7,
                   "party_hp_hi": 0, "party_hp_lo": 0}},
        {"watch": {"party": 1, "in_battle": 0, "map": 40, "x": 5, "y": 4,
                   "party_hp_hi": 0, "party_hp_lo": 20}},
        {"watch": {"party": 1, "in_battle": 2, "map": 40, "x": 6, "y": 4,
                   "party_hp_hi": 0, "party_hp_lo": 20}},
        *[{"watch": {"party": 1, "in_battle": 0, "map": 40, "x": 6, "y": 4,
                     "party_hp_hi": 0, "party_hp_lo": 5}} for _ in range(10)],
        {"watch": {"party": 1, "in_battle": 0, "map": 40, "x": 6, "y": 5,
                   "party_hp_hi": 0, "party_hp_lo": 5}},
    ]


def _miniwob_oracle():
    rows = []
    for episode, seed in enumerate(range(5)):
        rows.append({"episode": episode, "seed": seed, "reward": 0.0, "done": False,
                     "abandoned": False, "task": scorer.MINIWOB_TASK})
        rows.append({"episode": episode, "seed": seed, "reward": 1.0, "done": True,
                     "abandoned": False, "task": scorer.MINIWOB_TASK})
    return rows


def _build_sources(tmp_path, audits: dict[str, dict]) -> tuple[dict, dict]:
    """Write red_agent/miniwob_agent/red_human/miniwob_human/wake_boundary/live_breaker.json using
    the ACTUAL producing tools (build_agent_metrics + both dry_run_synthetic mechanism proofs),
    pin their real sha256, and return (artifact_paths, artifact_sha256) ready to drop into a
    gate0_*_source_pins.json-shaped manifest."""
    agent_wall_clock = {"red": 20.0, "miniwob": 10.0}
    agent_cost = {"red": 1.0, "miniwob": 0.5}
    agent_credits = {"red": 20.0, "miniwob": 10.0}
    human_wall_clock = {"red": 15.0, "miniwob": 8.0}
    human_primitive_actions = {"red": 8, "miniwob": 4}

    paths, hashes = {}, {}
    for arm in ("red", "miniwob"):
        agent = checker.build_agent_metrics(
            audits[arm], arm, "readiness_dev",
            wall_clock_s=agent_wall_clock[arm], cost_usd=agent_cost[arm],
            normalized_credits=agent_credits[arm])
        human = {"schema_version": 1, "arm": arm, "role": "human", "mode": "readiness_dev",
                 "wall_clock_s": human_wall_clock[arm],
                 "primitive_actions": human_primitive_actions[arm]}
        for key, payload in ((f"{arm}_agent", agent), (f"{arm}_human", human)):
            path = tmp_path / f"{key}.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            paths[key] = str(path)
            hashes[key] = hashlib.sha256(path.read_bytes()).hexdigest()

    wake_boundary_artifact = wake_boundary.dry_run_synthetic()
    assert wake_boundary_artifact["status"] == "PASS"
    wb_path = tmp_path / "wake_boundary.json"
    wb_path.write_text(json.dumps(wake_boundary_artifact), encoding="utf-8")
    paths["wake_boundary"] = str(wb_path)
    hashes["wake_boundary"] = hashlib.sha256(wb_path.read_bytes()).hexdigest()

    live_breaker_artifact = breaker.dry_run_synthetic()
    assert live_breaker_artifact["status"] == "PASS"
    lb_path = tmp_path / "live_breaker.json"
    lb_path.write_text(json.dumps(live_breaker_artifact), encoding="utf-8")
    paths["live_breaker"] = str(lb_path)
    hashes["live_breaker"] = hashlib.sha256(lb_path.read_bytes()).hexdigest()

    return paths, hashes


def test_synthetic_successful_run_now_passes_where_it_could_not_before(tmp_path, monkeypatch):
    audits = {}
    for arm in ("red", "miniwob"):
        transcript, receipt, expected, artifacts_dir = _build_arm_transcript(tmp_path, arm)
        audits[arm] = audit_codex(transcript, receipt, expected, artifacts_dir, arm)
        # Sanity: the real, fixed audit() actually earned a clean wake count for this transcript.
        assert audits[arm]["overall"] == "PASS"
        assert audits[arm]["wake_accounting"] == "PASS"
        assert audits[arm]["wakes"] == WAKES[arm]

    artifact_paths, artifact_hashes = _build_sources(tmp_path, audits)
    seed_path = scorer.MODES["readiness_dev"][0]
    pins = {
        "schema_version": 1, "mode": "readiness_dev",
        "frozen_seed_sha256": hashlib.sha256(seed_path.read_bytes()).hexdigest(),
        "artifact_paths": artifact_paths, "artifact_sha256": artifact_hashes,
    }
    pins_path = tmp_path / "source_pins.json"
    pins_path.write_text(json.dumps(pins), encoding="utf-8")
    monkeypatch.setitem(scorer.SOURCE_PIN_FILES, "readiness_dev", pins_path)

    manifest = {"mode": "readiness_dev", "arms": {"red": {}, "miniwob": {}}}
    oracles = {"red": _red_oracle(), "miniwob": _miniwob_oracle()}

    verified, source_failures = scorer._verify_sources(manifest, audits)
    assert source_failures == [], source_failures

    after = scorer.score(manifest, audits, oracles, verified, source_failures)
    assert after["overall"] == "PASS", after
    assert after["readiness"] == "GO", after
    assert after["failures"] == {"constancy": [], "leak": [], "infra": [], "capability": [],
                                 "cheap": [], "source": []}

    # BEFORE: reproduce exactly what the old, hardcoded audit() unconditionally returned for the
    # SAME clean transcript (wakes=None, wake_accounting="INSUFFICIENT_WAKES" -- the only fields
    # this PR's fix changes; everything else the loop computes is untouched by the fix). Feeding
    # that through the SAME real _verify_sources()/score() pipeline demonstrates the gate was
    # structurally unable to PASS before, regardless of how clean the transcript was.
    audits_before = {arm: {**audits[arm], "wakes": None, "wake_accounting": "INSUFFICIENT_WAKES"}
                     for arm in audits}
    verified_before, failures_before = scorer._verify_sources(manifest, audits_before)
    assert any(f.startswith("audited_wake_boundary:") for f in failures_before), failures_before

    before = scorer.score(manifest, audits_before, oracles, verified_before, failures_before)
    assert before["overall"] == "INSUFFICIENT_DATA", before
    assert before["readiness"] == "INSUFFICIENT_SOURCE", before
