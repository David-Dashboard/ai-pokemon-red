"""Fail-closed offline scorer for the two-arm North Star Gate 0."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from tools.check_gate0_codex import audit as audit_codex


def _jsonl(path: str | Path) -> list[dict]:
    return [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines()
            if line.strip()]


def _red_success(rows: list[dict]) -> tuple[bool, list[str]]:
    failures: list[str] = []
    watches = [row.get("watch") for row in rows if isinstance(row.get("watch"), dict)]
    if not watches or watches[0].get("party") != 0:
        return False, ["red_not_fresh_party_zero"]
    party_idx = next((i for i, watch in enumerate(watches) if (watch.get("party") or 0) >= 1), None)
    if party_idx is None:
        failures.append("red_no_party_0_to_1")
        return False, failures
    battle_idx = next((i for i, watch in enumerate(watches)
                       if i > party_idx and watch.get("in_battle") == 2), None)
    if battle_idx is None:
        failures.append("red_no_trainer_battle_after_party_acquisition")
        return False, failures
    exit_idx = next((i for i in range(battle_idx + 1, max(battle_idx + 1, len(watches) - 9))
                     if all(w.get("in_battle") == 0 for w in watches[i:i + 10])), None)
    if exit_idx is None:
        failures.append("red_no_sustained_battle_exit")
        return False, failures
    hp_values = []
    for watch in watches[battle_idx:exit_idx + 1]:
        hi, lo = watch.get("party_hp_hi"), watch.get("party_hp_lo")
        if (isinstance(hi, bool) or isinstance(lo, bool) or not isinstance(hi, int)
                or not isinstance(lo, int) or not 0 <= hi <= 255 or not 0 <= lo <= 255):
            failures.append("red_missing_player_hp_oracle")
            break
        hp_values.append((hi << 8) | lo)
    if hp_values and min(hp_values) == 0:
        failures.append("red_player_hp_reached_zero")
    battle_map = watches[battle_idx].get("map")
    if battle_map is None or watches[exit_idx].get("map") != battle_map:
        failures.append("red_blackout_or_map_change_at_exit")
    post = [(w.get("x"), w.get("y")) for w in watches[exit_idx:] if w.get("x") is not None and w.get("y") is not None]
    if len(set(post)) < 2:
        failures.append("red_no_free_movement_after_exit")
    return not failures, failures


def _miniwob_success(rows: list[dict], expected_seeds: list[int]) -> tuple[bool, list[str]]:
    failures: list[str] = []
    successes = {}
    for row in rows:
        if row.get("done") is True and row.get("abandoned") is not True and row.get("reward") == 1.0:
            successes[row.get("episode")] = row.get("seed")
    observed = [successes.get(i) for i in range(len(expected_seeds))]
    if observed != expected_seeds:
        failures.append("miniwob_not_5_of_5_on_pinned_seeds")
    if any(row.get("seed") not in expected_seeds for row in rows):
        failures.append("miniwob_unexpected_seed")
    return not failures, failures


def _arm_metrics(arm: dict, capability: bool) -> tuple[list[str], list[str]]:
    capability_failures = [] if capability else ["task_predicate_failed"]
    source_failures: list[str] = []
    metrics = arm.get("metrics") or {}
    required = ("wall_clock_s", "primitive_actions", "human_wall_clock_s", "human_primitive_actions",
                "wakes", "cost_usd", "normalized_credits")
    for key in required:
        value = metrics.get(key)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
            source_failures.append(f"missing_or_invalid_metric:{key}")
    if source_failures:
        return capability_failures, source_failures
    if metrics["wall_clock_s"] > 2 * metrics["human_wall_clock_s"]:
        capability_failures.append("wall_clock_over_2x_human")
    if metrics["primitive_actions"] > 2 * metrics["human_primitive_actions"]:
        capability_failures.append("actions_over_2x_human")
    return capability_failures, source_failures


def score(manifest: dict, audits: dict[str, dict], oracles: dict[str, list[dict]]) -> dict:
    arms = manifest.get("arms") or {}
    failures = {"constancy": [], "leak": [], "infra": [], "capability": [], "cheap": [], "source": []}
    for name in ("red", "miniwob"):
        audit = audits.get(name) or {}
        failures["leak"].extend(f"{name}:{x}" for x in audit.get("leak_failures", []))
        failures["constancy"].extend(f"{name}:{x}" for x in audit.get("constancy_failures", []))
        failures["infra"].extend(f"{name}:{x}" for x in audit.get("run_failures", []))
    red_ok, red_fail = _red_success(oracles.get("red", []))
    expected_seeds = (arms.get("miniwob") or {}).get("expected_seeds", [0, 1, 2, 3, 4])
    mw_ok, mw_fail = _miniwob_success(oracles.get("miniwob", []), expected_seeds)
    failures["capability"].extend(f"red:{x}" for x in red_fail)
    failures["capability"].extend(f"miniwob:{x}" for x in mw_fail)
    for name, ok in (("red", red_ok), ("miniwob", mw_ok)):
        cap, source = _arm_metrics(arms.get(name) or {}, ok)
        failures["capability"].extend(f"{name}:{x}" for x in cap if f"{name}:{x}" not in failures["capability"])
        failures["source"].extend(f"{name}:{x}" for x in source)

    accounting = manifest.get("accounting") or {}
    if accounting.get("wake_boundary") != "exact_documented":
        failures["source"].append("no_exact_documented_wake_boundary")
    if accounting.get("live_credit_breaker") is not True:
        failures["source"].append("no_live_250_credit_breaker")
    if any(audits.get(name, {}).get("accounting_failures") for name in ("red", "miniwob")):
        failures["source"].append("codex_accounting_audit_failed")

    if not failures["source"]:
        metrics = {name: arms[name]["metrics"] for name in ("red", "miniwob")}
        limits = {"red": (90, 5.0, 125), "miniwob": (50, 2.0, 50)}
        for name, (wake_cap, cost_cap, credit_cap) in limits.items():
            if metrics[name]["wakes"] > wake_cap or metrics[name]["cost_usd"] > cost_cap or metrics[name]["normalized_credits"] > credit_cap:
                failures["cheap"].append(f"{name}:arm_cap")
        if (sum(m["wakes"] for m in metrics.values()) > 140
                or sum(m["cost_usd"] for m in metrics.values()) > 7.0
                or sum(m["normalized_credits"] for m in metrics.values()) > 175):
            failures["cheap"].append("combined_cap")
        if sum(m["normalized_credits"] for m in metrics.values()) > 250:
            failures["cheap"].append("hard_breaker_exceeded")

    if failures["leak"]:
        verdict, readiness = "NO_LEAK", "NO_GO"
    elif failures["constancy"]:
        verdict, readiness = "CONSTANCY_BREACH", "NO_GO"
    elif failures["infra"]:
        verdict, readiness = "INSUFFICIENT_DATA", "INSUFFICIENT_SOURCE"
    elif failures["source"]:
        verdict, readiness = "INSUFFICIENT_DATA", "INSUFFICIENT_SOURCE"
    elif failures["capability"]:
        verdict, readiness = "FAIL_CAPABILITY", "NO_GO"
    elif failures["cheap"]:
        verdict, readiness = "FAIL_CHEAP", "NO_GO"
    else:
        verdict, readiness = "PASS", "GO"
    return {"schema_version": 1, "readiness": readiness, "overall": verdict, "failures": failures,
            "spend_usd": sum((arms.get(name, {}).get("metrics") or {}).get("cost_usd", 0)
                             for name in ("red", "miniwob"))}


def score_manifest(path: str | Path) -> dict:
    manifest = json.loads(Path(path).read_text(encoding="utf-8"))
    audits, oracles = {}, {}
    for name in ("red", "miniwob"):
        arm = manifest["arms"][name]
        audit_args = arm["codex_audit"]
        audits[name] = audit_codex(Path(audit_args["transcript"]), Path(audit_args["receipt"]),
                                   Path(audit_args["expected_pins"]), Path(audit_args["artifacts_dir"]),
                                   name, Path(audit_args["peer_receipt"]))
        oracles[name] = _jsonl(arm["oracle"])
    return score(manifest, audits, oracles)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", type=Path)
    args = parser.parse_args()
    result = score_manifest(args.manifest)
    print(json.dumps(result, sort_keys=True))
    return 0 if result["readiness"] == "GO" else 1


if __name__ == "__main__":
    raise SystemExit(main())
