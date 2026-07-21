"""End-to-end proof of the 2026-07-21 Cheap-basis amendment (David's decision, recorded in
reports/2026-07-13-minimum-north-star-gate-0-design.md's AMENDMENT block and
reports/2026-07-18-gate0-prereg.md's AMENDMENT block): Gate 0's Cheap axis is grounded on
COST-PER-TASK; wakes-per-task is DEFERRED and no longer gates the verdict.

Background (reports/2026-07-21-gate0-wake-grounding.md, PR #126): a real `codex exec --json`
transcript showed a single turn.completed bundles >=2 real model decisions (cumulative usage for
the whole turn), with no per-decision boundary event anywhere in Codex's JSONL schema to count
instead. So tools/check_gate0_codex.py::audit() reverted PR #125's `wakes = usage_events`
definition (which undercounted by >=2x) back to the fail-closed `wakes=None` /
`wake_accounting="INSUFFICIENT_WAKES"` hardcode -- correctly honest, but pre-amendment this also
made eval/score_gate0.py's verdict permanently unable to reach PASS on ANY run, however clean,
because the scorer required `wake_accounting == "PASS"`.

These tests drive the REAL audit_codex() (permanently fail-closed on wakes, unchanged by this
amendment) all the way through the real scorer, proving:

1. `test_synthetic_successful_run_within_cost_caps_now_passes_wakes_deferred` -- a fully clean,
   leak/constancy/run/accounting-free synthetic transcript per arm, with cost/credits WITHIN the
   unchanged $/credit caps, now reaches PASS/GO even though audit()'s wake_accounting is (and
   stays) "INSUFFICIENT_WAKES" throughout -- wakes are reported in the verdict payload
   (`wake_accounting.status == "DEFERRED"`, `cheap_basis == "cost_per_task"`) but never gate.
2. `test_synthetic_run_over_cost_cap_still_fails_cheap_even_with_wakes_deferred` -- the SAME clean/
   wakes-deferred setup, but with cost pushed over the unchanged per-arm cap, still fails
   FAIL_CHEAP -- proving the cost bar's strictness is completely unchanged by this amendment.
3. `test_all_arms_refuse_a_real_wake_count` (below, unmodified) -- the writer-level guarantee
   (build_agent_metrics() itself still refuses to write a "wakes" number from a non-PASS audit)
   is untouched by this amendment; it is orthogonal to whether the SCORER gates on wakes.

Everything here is $0 and synthetic -- no codex exec, no paid run.
"""
from __future__ import annotations

import hashlib
import json

import pytest

import eval.score_gate0 as scorer
import tools.check_gate0_codex as checker
import tools.gate0_credit_breaker as breaker
import tools.gate0_wake_boundary as wake_boundary
from tools.check_gate0_codex import SERVER, TOOLS, audit as audit_codex

DECISIONS = {"red": 10, "miniwob": 5}
_USAGE = {"input_tokens": 12, "cached_input_tokens": 4, "output_tokens": 5, "reasoning_output_tokens": 1}
# Modeling an external bypass of our own fail-closed writer (build_agent_metrics refuses this --
# see test_all_arms_refuse_a_real_wake_count below). The exact numbers don't matter: audit()'s
# wake_accounting stays "INSUFFICIENT_WAKES" regardless, which alone fails the scorer's cross-check.
FABRICATED_WAKES = {"red": 10, "miniwob": 5}


def _write(path, data: bytes) -> str:
    path.write_bytes(data)
    return hashlib.sha256(data).hexdigest()


def _build_arm_transcript(tmp_dir, arm: str):
    """Same shape as tests/test_check_gate0_codex.py's `_fixture()` helper -- a clean, self-
    consistent receipt/expected-pins/artifacts_dir plus a transcript with DECISIONS[arm] real
    turn.completed events, each preceded by an allowlisted mcp_tool_call. No peer_receipt is
    exercised here (peer cross-arm constancy is a separate, already-tested mechanism and orthogonal
    to the wake-accounting question this test proves)."""
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
    for _ in range(DECISIONS[arm]):
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


def _build_sources_with_fabricated_wakes(tmp_path, audits: dict[str, dict],
                                          agent_cost: dict | None = None) -> tuple[dict, dict]:
    """Write red_agent/miniwob_agent/red_human/miniwob_human/wake_boundary/live_breaker.json.

    The agent metrics files are hand-written directly (NOT via build_agent_metrics, which
    correctly refuses -- see test_all_arms_refuse_a_real_wake_count) to model the one remaining
    way a wake number could reach agent_metrics.json: someone bypasses our writer entirely. Under
    the 2026-07-21 Cheap-basis amendment this "wakes" number is purely informational (reported in
    the verdict payload, never gating) -- it can never manufacture a PASS by itself, and it can
    never manufacture a FAIL_CHEAP by itself either; only cost_usd/normalized_credits gate Cheap
    now (see eval/score_gate0.py::score()). `agent_cost` lets callers push cost over/under the
    unchanged per-arm cap ($5.00 red / $2.00 miniwob) to test that axis specifically.
    """
    agent_wall_clock = {"red": 20.0, "miniwob": 10.0}
    agent_primitive_actions = {"red": 10, "miniwob": 5}
    agent_cost = agent_cost or {"red": 1.0, "miniwob": 0.5}
    agent_credits = {"red": 20.0, "miniwob": 10.0}
    human_wall_clock = {"red": 15.0, "miniwob": 8.0}
    human_primitive_actions = {"red": 8, "miniwob": 4}

    paths, hashes = {}, {}
    for arm in ("red", "miniwob"):
        agent = {
            "schema_version": 1, "arm": arm, "role": "agent", "mode": "readiness_dev",
            "wall_clock_s": agent_wall_clock[arm],
            "primitive_actions": agent_primitive_actions[arm],
            "wakes": FABRICATED_WAKES[arm],
            "cost_usd": agent_cost[arm], "normalized_credits": agent_credits[arm],
        }
        human = {"schema_version": 1, "arm": arm, "role": "human", "mode": "readiness_dev",
                 "wall_clock_s": human_wall_clock[arm],
                 "primitive_actions": human_primitive_actions[arm]}
        for key, payload in ((f"{arm}_agent", agent), (f"{arm}_human", human)):
            path = tmp_path / f"{key}.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            paths[key] = str(path)
            hashes[key] = hashlib.sha256(path.read_bytes()).hexdigest()

    # The real mechanism-demo artifact: status is permanently "FAIL" today (see
    # tools/gate0_wake_boundary.py's docstring) -- an independent, second line of defense.
    wake_boundary_artifact = wake_boundary.dry_run_synthetic()
    assert wake_boundary_artifact["status"] == "FAIL"
    assert wake_boundary_artifact["fail_closed_regression_guard_holds"] is True
    wb_path = tmp_path / "wake_boundary.json"
    wb_path.write_text(json.dumps(wake_boundary_artifact), encoding="utf-8")
    paths["wake_boundary"] = str(wb_path)
    hashes["wake_boundary"] = hashlib.sha256(wb_path.read_bytes()).hexdigest()

    # Live breaker is a real, independent mechanism (unaffected by the wake-grounding finding) --
    # kept legitimately PASS so the proof below isolates its refusal to the wake axis only.
    live_breaker_artifact = breaker.dry_run_synthetic()
    assert live_breaker_artifact["status"] == "PASS"
    lb_path = tmp_path / "live_breaker.json"
    lb_path.write_text(json.dumps(live_breaker_artifact), encoding="utf-8")
    paths["live_breaker"] = str(lb_path)
    hashes["live_breaker"] = hashlib.sha256(lb_path.read_bytes()).hexdigest()

    return paths, hashes


def test_all_arms_refuse_a_real_wake_count(tmp_path):
    """Sanity check ahead of the main proof: even the maximally clean transcript per arm (zero
    leak/constancy/run/accounting failures -- exactly the shape that, pre-#126, would have earned
    a PASS wake count) still reports the fail-closed hardcode, and our own writer refuses it."""
    for arm in ("red", "miniwob"):
        transcript, receipt, expected, artifacts_dir = _build_arm_transcript(tmp_path, arm)
        result = audit_codex(transcript, receipt, expected, artifacts_dir, arm)
        assert result["leak_failures"] == []
        assert result["constancy_failures"] == []
        assert result["run_failures"] == []
        assert result["accounting_failures"] == []
        assert result["overall"] == "NO_GO_INSUFFICIENT_WAKES"
        assert result["wake_accounting"] == "INSUFFICIENT_WAKES"
        assert result["wakes"] is None
        with pytest.raises(ValueError, match="audit_not_clean"):
            checker.build_agent_metrics(result, arm, "readiness_dev",
                                        wall_clock_s=20.0, cost_usd=1.0, normalized_credits=20.0)


def _audit_clean_arms(tmp_path):
    audits = {}
    for arm in ("red", "miniwob"):
        transcript, receipt, expected, artifacts_dir = _build_arm_transcript(tmp_path, arm)
        audits[arm] = audit_codex(transcript, receipt, expected, artifacts_dir, arm)
        assert audits[arm]["overall"] == "NO_GO_INSUFFICIENT_WAKES"
        assert audits[arm]["wake_accounting"] == "INSUFFICIENT_WAKES"
        assert audits[arm]["wakes"] is None
    return audits


def _score_with_fabricated_sources(tmp_path, monkeypatch, audits, agent_cost=None):
    artifact_paths, artifact_hashes = _build_sources_with_fabricated_wakes(tmp_path, audits, agent_cost)
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
    return scorer.score(manifest, audits, oracles, verified, source_failures)


def test_synthetic_successful_run_within_cost_caps_now_passes_wakes_deferred(tmp_path, monkeypatch):
    """Scenario (a): clean run, within cost caps, wakes accounting INSUFFICIENT -> PASS/GO.

    Drives the REAL audit_codex() (permanently fail-closed on wakes: overall=
    NO_GO_INSUFFICIENT_WAKES, wake_accounting=INSUFFICIENT_WAKES, wakes=None for both arms,
    confirmed above) all the way through the real scorer. Cost ($1.00 red / $0.50 miniwob) and
    credits (20/10) are well within the unchanged per-arm and combined caps. Pre-amendment this
    configuration could never leave INSUFFICIENT_DATA (audited_wake_boundary:<arm> +
    wake_boundary_artifact); post-amendment it must reach PASS, with wakes/wake_accounting
    reported informationally, never gating.
    """
    audits = _audit_clean_arms(tmp_path)
    result = _score_with_fabricated_sources(tmp_path, monkeypatch, audits)

    assert result["overall"] == "PASS", result
    assert result["readiness"] == "GO", result
    # Isolation: every failure bucket is empty -- capability/leak/constancy/infra/source/cheap all
    # clear, so this PASS is not masking anything on another axis.
    for bucket in ("leak", "constancy", "infra", "capability", "source", "cheap"):
        assert result["failures"][bucket] == [], (bucket, result)
    # The deferred-wake bookkeeping is present and honest: still INSUFFICIENT_WAKES per arm.
    assert result["cheap_basis"] == "cost_per_task"
    assert result["wake_accounting"]["status"] == "DEFERRED"
    for arm in ("red", "miniwob"):
        assert result["wake_accounting"]["detail"][arm]["wake_accounting"] == "INSUFFICIENT_WAKES"


def test_synthetic_run_over_cost_cap_still_fails_cheap_even_with_wakes_deferred(tmp_path, monkeypatch):
    """Scenario (b): SAME clean/wakes-deferred setup as above, but red's cost pushed to $5.01
    (over the unchanged $5.00 per-arm cap) -> FAIL_CHEAP. Proves the cost bar's strictness is
    completely unchanged by the 2026-07-21 amendment -- only the wake axis stopped gating.
    """
    audits = _audit_clean_arms(tmp_path)
    result = _score_with_fabricated_sources(tmp_path, monkeypatch, audits,
                                             agent_cost={"red": 5.01, "miniwob": 0.5})

    assert result["overall"] == "FAIL_CHEAP", result
    assert result["readiness"] == "NO_GO", result
    assert "red:arm_cap" in result["failures"]["cheap"]
    # Still isolated to cheap -- capability/leak/constancy/infra/source stay clear.
    for bucket in ("leak", "constancy", "infra", "capability", "source"):
        assert result["failures"][bucket] == [], (bucket, result)
