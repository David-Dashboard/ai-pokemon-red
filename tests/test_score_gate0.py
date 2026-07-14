import hashlib
import json

import eval.score_gate0 as scorer
from eval.score_gate0 import score
from games.pokemon_red.memory_map import ADDR_IS_IN_BATTLE, ADDR_PARTY_MON1, OFF_CUR_HP
import world_mcp


def _red(success=True):
    rows = [{"watch": {"party": 0, "in_battle": 0, "map": 38, "x": 3, "y": 7,
                       "party_hp_hi": 0, "party_hp_lo": 0}}]
    if not success:
        return rows
    rows += [{"watch": {"party": 1, "in_battle": 0, "map": 40, "x": 5, "y": 4,
                        "party_hp_hi": 0, "party_hp_lo": 20}},
             {"watch": {"party": 1, "in_battle": 2, "map": 40, "x": 6, "y": 4,
                        "party_hp_hi": 0, "party_hp_lo": 20}}]
    rows += [{"watch": {"party": 1, "in_battle": 0, "map": 40, "x": 6, "y": 4,
                        "party_hp_hi": 0, "party_hp_lo": 5}}
             for _ in range(10)]
    rows += [{"watch": {"party": 1, "in_battle": 0, "map": 40, "x": 6, "y": 5,
                        "party_hp_hi": 0, "party_hp_lo": 5}}]
    return rows


def _miniwob(success=True):
    rows = []
    for episode, seed in enumerate(range(5)):
        rows.append({"episode": episode, "seed": seed, "reward": 0.0, "done": False,
                     "abandoned": False})
        if success or episode < 4:
            rows.append({"episode": episode, "seed": seed, "reward": 1.0, "done": True,
                         "abandoned": False})
    return rows


def _manifest():
    return {
        "mode": "readiness_dev",
        "arms": {
            "red": {},
            "miniwob": {},
        },
    }


def _audits():
    clean = {"leak_failures": [], "constancy_failures": [], "run_failures": [],
             "accounting_failures": [], "wake_accounting": "PASS"}
    return {"red": {**clean, "wakes": 80}, "miniwob": {**clean, "wakes": 40}}


def _verified():
    return {
        "mode": "readiness_dev", "expected_seeds": list(range(5)),
        "metrics": {
            "red": {"wall_clock_s": 100, "primitive_actions": 100,
                    "human_wall_clock_s": 60, "human_primitive_actions": 60,
                    "wakes": 80, "cost_usd": 4.0, "normalized_credits": 100},
            "miniwob": {"wall_clock_s": 50, "primitive_actions": 20,
                        "human_wall_clock_s": 30, "human_primitive_actions": 12,
                        "wakes": 40, "cost_usd": 1.5, "normalized_credits": 40},
        },
    }


def _score(manifest=None, audits=None, red=None, miniwob=None, verified=True):
    return score(manifest or _manifest(), audits or _audits(),
                 {"red": red if red is not None else _red(),
                  "miniwob": miniwob if miniwob is not None else _miniwob()},
                 _verified() if verified else None)


def test_pokemon_red_battle_watch_uses_existing_constant():
    watch = world_mcp.GAMES["pokemon_red"]["watch"]
    assert watch["in_battle"] == ADDR_IS_IN_BATTLE
    assert watch["party_hp_hi"] == ADDR_PARTY_MON1 + OFF_CUR_HP
    assert watch["party_hp_lo"] == ADDR_PARTY_MON1 + OFF_CUR_HP + 1


def test_red_loss_that_exits_on_same_map_and_moves_still_fails():
    rows = _red()
    rows[2]["watch"]["party_hp_lo"] = 0
    result = _score(red=rows)
    assert result["overall"] == "FAIL_CAPABILITY"
    assert "red:red_player_hp_reached_zero" in result["failures"]["capability"]


def test_red_delayed_zero_during_sustained_exit_still_fails():
    rows = _red()
    rows[7]["watch"]["party_hp_lo"] = 0
    assert _score(red=rows)["overall"] == "FAIL_CAPABILITY"


def test_red_delayed_map_change_during_sustained_exit_still_fails():
    rows = _red()
    rows[7]["watch"]["map"] = 0
    result = _score(red=rows)
    assert result["overall"] == "FAIL_CAPABILITY"
    assert "red:red_map_changed_during_battle_exit_span" in result["failures"]["capability"]


def test_red_first_party_transition_must_be_exactly_zero_to_one():
    rows = _red()
    rows[1]["watch"]["party"] = 2
    assert _score(red=rows)["overall"] == "FAIL_CAPABILITY"


def test_pass_matrix():
    result = _score()
    assert result["readiness"] == "GO"
    assert result["overall"] == "PASS"


def test_arm_capability_failure():
    result = _score(red=_red(False))
    assert result["overall"] == "FAIL_CAPABILITY"
    assert result["readiness"] == "NO_GO"


def test_cheap_failure():
    verified = _verified()
    verified["metrics"]["red"]["wakes"] = 91
    assert score(_manifest(), _audits(), {"red": _red(), "miniwob": _miniwob()}, verified)["overall"] == "FAIL_CHEAP"


def test_infra_death_is_insufficient_data():
    audits = _audits()
    audits["red"]["run_failures"] = ["run_event:error"]
    result = _score(audits=audits)
    assert result["overall"] == "INSUFFICIENT_DATA"
    assert result["readiness"] == "INSUFFICIENT_SOURCE"


def test_constancy_breach_precedes_capability():
    audits = _audits()
    audits["red"]["constancy_failures"] = ["peer_mismatch:planned_model"]
    assert _score(audits=audits, red=_red(False))["overall"] == "CONSTANCY_BREACH"


def test_leak_precedes_constancy():
    audits = _audits()
    audits["red"]["leak_failures"] = ["forbidden_item:command_execution"]
    audits["red"]["constancy_failures"] = ["peer_mismatch:planned_model"]
    assert _score(audits=audits)["overall"] == "NO_LEAK"


def test_missing_wake_accounting_is_insufficient_source():
    audits = _audits()
    audits["red"]["accounting_failures"] = ["no_observable_wake_boundary"]
    result = _score(audits=audits)
    assert result["overall"] == "INSUFFICIENT_DATA"
    assert "codex_accounting_audit_failed" in result["failures"]["source"]


def test_miniwob_requires_all_five_pinned_successes():
    assert _score(miniwob=_miniwob(False))["overall"] == "FAIL_CAPABILITY"


def test_miniwob_abandoned_then_success_is_not_accepted():
    rows = _miniwob()
    rows.insert(1, {"episode": 0, "seed": 0, "reward": 0.0, "done": True, "abandoned": True})
    assert _score(miniwob=rows)["overall"] == "FAIL_CAPABILITY"


def test_bare_manifest_numbers_can_never_go():
    manifest = _manifest()
    manifest["arms"]["red"]["metrics"] = _verified()["metrics"]["red"]
    manifest["arms"]["miniwob"]["metrics"] = _verified()["metrics"]["miniwob"]
    result = _score(manifest=manifest, verified=False)
    assert result["readiness"] == "INSUFFICIENT_SOURCE"
    assert "unverified_source_artifacts" in result["failures"]["source"]


def test_zero_human_or_agent_metric_is_source_failure():
    verified = _verified()
    verified["metrics"]["red"]["human_wall_clock_s"] = 0
    result = score(_manifest(), _audits(), {"red": _red(), "miniwob": _miniwob()}, verified)
    assert result["readiness"] == "INSUFFICIENT_SOURCE"


def test_frozen_source_pins_load_exact_artifacts(monkeypatch, tmp_path):
    artifacts = {}
    payloads = {
        "red_agent": {"schema_version": 1, "arm": "red", "role": "agent", "mode": "readiness_dev",
                      "wall_clock_s": 100, "primitive_actions": 100, "wakes": 80,
                      "cost_usd": 4.0, "normalized_credits": 100},
        "red_human": {"schema_version": 1, "arm": "red", "role": "human", "mode": "readiness_dev",
                      "wall_clock_s": 60, "primitive_actions": 60},
        "miniwob_agent": {"schema_version": 1, "arm": "miniwob", "role": "agent", "mode": "readiness_dev",
                          "wall_clock_s": 50, "primitive_actions": 20, "wakes": 40,
                          "cost_usd": 1.5, "normalized_credits": 40},
        "miniwob_human": {"schema_version": 1, "arm": "miniwob", "role": "human", "mode": "readiness_dev",
                          "wall_clock_s": 30, "primitive_actions": 12},
        "wake_boundary": {"schema_version": 1, "kind": "exact_wake_boundary", "status": "PASS"},
        "live_breaker": {"schema_version": 1, "kind": "live_credit_breaker", "status": "PASS",
                         "limit_normalized_credits": 250},
    }
    hashes = {}
    for key, payload in payloads.items():
        path = tmp_path / f"{key}.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        artifacts[key] = str(path)
        hashes[key] = hashlib.sha256(path.read_bytes()).hexdigest()
    seed_path = scorer.MODES["readiness_dev"][0]
    pins = {"schema_version": 1, "mode": "readiness_dev",
            "frozen_seed_sha256": hashlib.sha256(seed_path.read_bytes()).hexdigest(),
            "artifact_paths": artifacts, "artifact_sha256": hashes}
    pins_path = tmp_path / "pins.json"
    pins_path.write_text(json.dumps(pins), encoding="utf-8")
    monkeypatch.setitem(scorer.SOURCE_PIN_FILES, "readiness_dev", pins_path)
    verified, failures = scorer._verify_sources(_manifest(), _audits())
    assert failures == []
    assert verified["expected_seeds"] == list(range(5))
    assert verified["metrics"] == _verified()["metrics"]
