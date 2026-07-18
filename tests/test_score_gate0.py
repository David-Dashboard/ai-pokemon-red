import hashlib
import json
import subprocess

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
                     "abandoned": False, "task": scorer.MINIWOB_TASK})
        if success or episode < 4:
            rows.append({"episode": episode, "seed": seed, "reward": 1.0, "done": True,
                         "abandoned": False, "task": scorer.MINIWOB_TASK})
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


def test_miniwob_bool_reward_is_not_accepted():
    # PR #114 review exploit "bool_reward": episode 4's terminal reward replaced with JSON `true`.
    # Python's `True == 1.0`, so the pre-fix code (which only checked `reward == 1.0`) scored this
    # PASS/GO. isinstance(reward, bool) must be rejected before the numeric comparison.
    rows = _miniwob()
    rows[-1]["reward"] = True
    result = _score(miniwob=rows)
    assert result["overall"] == "FAIL_CAPABILITY"
    assert "miniwob:miniwob_episode_4_terminal_not_success" in result["failures"]["capability"]


def test_miniwob_reopened_row_with_wrong_task_after_success_is_refused():
    # PR #114 review exploit "reopened_wrong_task": a done=false, task="wrong-task" row appended
    # after episode 0's real success (same episode/seed). The pre-fix code never read `task` and
    # only counted done/abandoned rows as terminals, so the extra row was silently ignored and the
    # manifest still scored PASS/GO.
    rows = _miniwob()
    rows.insert(2, {"episode": 0, "seed": 0, "reward": 0.0, "done": False,
                    "abandoned": False, "task": "wrong-task"})
    result = _score(miniwob=rows)
    assert result["overall"] == "FAIL_CAPABILITY"
    assert "miniwob:miniwob_wrong_task_row" in result["failures"]["capability"]


def test_miniwob_all_rows_wrong_task_is_refused():
    # PR #114 review exploit "wrong_task_field_ignored"/"reopened_wrong_task_field_ignored":
    # every row's task set to an entirely different task ("click-button"), otherwise a clean 5/5
    # success shape. The pre-fix code never checked `task` at all, so this scored PASS/GO.
    rows = _miniwob()
    for row in rows:
        row["task"] = "click-button"
    result = _score(miniwob=rows)
    assert result["overall"] == "FAIL_CAPABILITY"
    assert "miniwob:miniwob_wrong_task_row" in result["failures"]["capability"]


def test_verify_audit_paths_accepts_exact_pinned_locations(tmp_path, monkeypatch):
    expected_pins = tmp_path / "expected-pins.json"
    expected_pins.write_text(json.dumps({"schema_version": 2}), encoding="utf-8")
    pinned = {
        "transcript": str(tmp_path / "transcript.jsonl"),
        "receipt": str(tmp_path / "receipt.json"),
        "expected_pins": str(expected_pins),
        "artifacts_dir": str(tmp_path / "artifacts"),
        "peer_receipt": str(tmp_path / "peer-receipt.json"),
        "oracle": str(tmp_path / "oracle.jsonl"),
    }
    pins_doc = {
        "schema_version": 1, "mode": "readiness_dev",
        "audit_paths": {"red": pinned, "miniwob": pinned},
        "expected_pins_sha256": {
            "red": hashlib.sha256(expected_pins.read_bytes()).hexdigest(),
            "miniwob": hashlib.sha256(expected_pins.read_bytes()).hexdigest(),
        },
    }
    pins_path = tmp_path / "pins.json"
    pins_path.write_text(json.dumps(pins_doc), encoding="utf-8")
    monkeypatch.setitem(scorer.SOURCE_PIN_FILES, "readiness_dev", pins_path)
    manifest = {
        "mode": "readiness_dev",
        "arms": {
            "red": {"codex_audit": {k: v for k, v in pinned.items() if k != "oracle"},
                    "oracle": pinned["oracle"]},
            "miniwob": {"codex_audit": {k: v for k, v in pinned.items() if k != "oracle"},
                       "oracle": pinned["oracle"]},
        },
    }
    resolved, failures = scorer._verify_audit_paths(manifest)
    assert failures == []
    assert resolved["red"] == pinned
    assert resolved["miniwob"] == pinned


def test_score_manifest_rejects_substituted_expected_pins_and_oracle(monkeypatch, tmp_path):
    # PR #114 review finding: score_manifest() took codex_audit.{transcript,receipt,
    # expected_pins,artifacts_dir,peer_receipt} and arm["oracle"] verbatim from the manifest with
    # zero hash-pinning. This end-to-end test drives the real public score_manifest() entry point
    # (not _verify_sources()/score() directly, which the pre-fix test suite stopped at) and proves
    # a manifest that substitutes its own audit/oracle evidence for the pinned locations is refused
    # rather than scored. Pre-fix, score_manifest() has no path-pinning at all, so this substituted
    # manifest would instead proceed to (and likely crash or falsely score) the attacker files.
    attacker_dir = tmp_path / "attacker"
    attacker_dir.mkdir()
    attacker_transcript = attacker_dir / "transcript.jsonl"
    attacker_transcript.write_text("", encoding="utf-8")
    attacker_receipt = attacker_dir / "receipt.json"
    attacker_receipt.write_text("{}", encoding="utf-8")
    attacker_expected_pins = attacker_dir / "expected-pins.json"
    attacker_expected_pins.write_text("{}", encoding="utf-8")
    attacker_artifacts_dir = attacker_dir / "artifacts"
    attacker_artifacts_dir.mkdir()
    attacker_peer_receipt = attacker_dir / "peer-receipt.json"
    attacker_peer_receipt.write_text("{}", encoding="utf-8")
    attacker_oracle = attacker_dir / "oracle.jsonl"
    attacker_oracle.write_text(json.dumps({"episode": 0, "seed": 0, "reward": 1.0, "done": True,
                                           "abandoned": False, "task": scorer.MINIWOB_TASK}) + "\n",
                               encoding="utf-8")

    real_expected_pins = tmp_path / "real-expected-pins.json"
    real_expected_pins.write_text(json.dumps({"schema_version": 2}), encoding="utf-8")
    pinned = {
        "transcript": str(tmp_path / "real-transcript.jsonl"),
        "receipt": str(tmp_path / "real-receipt.json"),
        "expected_pins": str(real_expected_pins),
        "artifacts_dir": str(tmp_path / "real-artifacts"),
        "peer_receipt": str(tmp_path / "real-peer-receipt.json"),
        "oracle": str(tmp_path / "real-oracle.jsonl"),
    }
    pins_doc = {
        "schema_version": 1, "mode": "readiness_dev",
        "audit_paths": {"red": pinned, "miniwob": pinned},
        "expected_pins_sha256": {
            "red": hashlib.sha256(real_expected_pins.read_bytes()).hexdigest(),
            "miniwob": hashlib.sha256(real_expected_pins.read_bytes()).hexdigest(),
        },
    }
    pins_path = tmp_path / "pins.json"
    pins_path.write_text(json.dumps(pins_doc), encoding="utf-8")
    monkeypatch.setitem(scorer.SOURCE_PIN_FILES, "readiness_dev", pins_path)

    substituted_audit = {"transcript": str(attacker_transcript), "receipt": str(attacker_receipt),
                         "expected_pins": str(attacker_expected_pins),
                         "artifacts_dir": str(attacker_artifacts_dir),
                         "peer_receipt": str(attacker_peer_receipt)}
    manifest = {
        "mode": "readiness_dev",
        "arms": {
            "red": {"codex_audit": substituted_audit, "oracle": str(attacker_oracle)},
            "miniwob": {"codex_audit": substituted_audit, "oracle": str(attacker_oracle)},
        },
    }
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    result = scorer.score_manifest(manifest_path)
    assert result["readiness"] == "INSUFFICIENT_SOURCE"
    assert any(f.startswith("audit_path_mismatch:red:") for f in result["failures"]["source"])
    assert any(f.startswith("audit_path_mismatch:miniwob:") for f in result["failures"]["source"])


def test_code_sha256_hashes_canonical_git_blob_not_dirty_worktree_bytes(tmp_path):
    # PR #114 review finding: host_code_sha256/image_code_sha256 hashed raw working-tree bytes,
    # which differ by machine/OS line-ending config (CRLF vs LF) even for byte-identical tracked
    # content -- not portable/reproducible. code_sha256() must hash the canonical git blob at HEAD
    # instead, and refuse (never silently hash dirty bytes) when the working tree has diverged.
    subprocess.run(["git", "init", "--quiet", str(tmp_path)], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "config", "user.email", "test@example.com"], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "config", "user.name", "test"], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "config", "core.autocrlf", "false"], check=True)
    target = tmp_path / "sample.py"
    canonical = b"a = 1\nb = 2\n"
    target.write_bytes(canonical)
    subprocess.run(["git", "-C", str(tmp_path), "add", "sample.py"], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "commit", "--quiet", "-m", "init"], check=True)

    canonical_hash = world_mcp.code_sha256(target, repo_root=tmp_path)
    assert canonical_hash == hashlib.sha256(canonical).hexdigest()

    # The same logical content with CRLF endings hashes to a DIFFERENT value under raw-byte
    # hashing -- exactly the non-portability this fix closes.
    crlf_bytes = canonical.replace(b"\n", b"\r\n")
    assert hashlib.sha256(crlf_bytes).hexdigest() != canonical_hash

    # Write those CRLF bytes to disk without committing: the working tree now diverges from HEAD,
    # so code_sha256 must refuse rather than silently hash the dirty bytes.
    target.write_bytes(crlf_bytes)
    assert world_mcp.code_sha256(target, repo_root=tmp_path) == "UNHASHABLE"

    # Restore to match HEAD exactly: code_sha256 must return to the SAME canonical hash as before
    # -- it always reads the git-stored blob, never the working-tree bytes, which is what makes
    # the value portable across machines regardless of local checkout line-ending conventions.
    subprocess.run(["git", "-C", str(tmp_path), "checkout", "--", "sample.py"], check=True)
    assert world_mcp.code_sha256(target, repo_root=tmp_path) == canonical_hash


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
