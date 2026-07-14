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
        "arms": {
            "red": {"metrics": {"wall_clock_s": 100, "primitive_actions": 100,
                                  "human_wall_clock_s": 60, "human_primitive_actions": 60,
                                  "wakes": 80, "cost_usd": 4.0, "normalized_credits": 100}},
            "miniwob": {"expected_seeds": list(range(5)),
                         "metrics": {"wall_clock_s": 50, "primitive_actions": 20,
                                     "human_wall_clock_s": 30, "human_primitive_actions": 12,
                                     "wakes": 40, "cost_usd": 1.5, "normalized_credits": 40}},
        },
        "accounting": {"wake_boundary": "exact_documented", "live_credit_breaker": True},
    }


def _audits():
    clean = {"leak_failures": [], "constancy_failures": [], "run_failures": [],
             "accounting_failures": []}
    return {"red": dict(clean), "miniwob": dict(clean)}


def _score(manifest=None, audits=None, red=None, miniwob=None):
    return score(manifest or _manifest(), audits or _audits(),
                 {"red": red if red is not None else _red(),
                  "miniwob": miniwob if miniwob is not None else _miniwob()})


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


def test_pass_matrix():
    result = _score()
    assert result["readiness"] == "GO"
    assert result["overall"] == "PASS"


def test_arm_capability_failure():
    result = _score(red=_red(False))
    assert result["overall"] == "FAIL_CAPABILITY"
    assert result["readiness"] == "NO_GO"


def test_cheap_failure():
    manifest = _manifest()
    manifest["arms"]["red"]["metrics"]["wakes"] = 91
    assert _score(manifest=manifest)["overall"] == "FAIL_CHEAP"


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
    manifest = _manifest()
    manifest["accounting"]["wake_boundary"] = None
    result = _score(manifest=manifest)
    assert result["overall"] == "INSUFFICIENT_DATA"
    assert "no_exact_documented_wake_boundary" in result["failures"]["source"]


def test_miniwob_requires_all_five_pinned_successes():
    assert _score(miniwob=_miniwob(False))["overall"] == "FAIL_CAPABILITY"
