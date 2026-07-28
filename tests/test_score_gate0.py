import hashlib
import json
import subprocess

import eval.score_gate0 as scorer
from eval.score_gate0 import _red_success, score
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


def test_red_corrupted_party_byte_does_not_mask_a_real_death():
    # PR #121 review Major 1 PoC #1: a `party`-only filter (the PR's original fix) would drop ANY
    # row whose party byte alone misreads, regardless of what its other fields say -- so a row that
    # is a GENUINE HP=0 death, with only the unrelated `party` byte corrupted (x/y/map/in_battle all
    # still legitimate, in-battle-map), got silently erased: `ok=True, failures=[]`. The correct
    # filter only drops a row when EVERY watched field simultaneously reads 0 (the actual observed
    # corruption signature in the real traces) -- a lone corrupted `party` byte alongside a real
    # death must still fail.
    rows = _red()
    rows[7]["watch"]["party_hp_lo"] = 0
    rows[7]["watch"]["party"] = 2
    result = _score(red=rows)
    assert result["overall"] == "FAIL_CAPABILITY"
    assert "red:red_player_hp_reached_zero" in result["failures"]["capability"]


def test_red_corrupted_party_byte_does_not_mask_a_real_map_change():
    # PR #121 review Major 1 PoC #2: same exploit against the map-continuity check -- a row with a
    # GENUINE map change (the whiteout-teleport-home case red_map_changed_during_battle_exit_span
    # exists to catch) plus a merely-corrupted `party` byte must still fail, not be silently
    # dropped by a party-keyed filter.
    rows = _red()
    rows[7]["watch"]["map"] = 99
    rows[7]["watch"]["party"] = 2
    result = _score(red=rows)
    assert result["overall"] == "FAIL_CAPABILITY"
    assert "red:red_map_changed_during_battle_exit_span" in result["failures"]["capability"]


def test_red_first_party_transition_must_be_exactly_zero_to_one():
    rows = _red()
    rows[1]["watch"]["party"] = 2
    assert _score(red=rows)["overall"] == "FAIL_CAPABILITY"


def _load_oracle_fixture(name):
    path = scorer.ROOT / "eval" / "fixtures" / name
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_red_single_glitched_watch_row_does_not_block_a_real_completion():
    # Regression for the Gate 0 Red rig missing a genuine human completion (David's second
    # human-baseline attempt, 2026-07-21): a real oracle.jsonl trace of a human who obtained the
    # starter, won the rival battle, and then walked out of the lab across several tiles -- a
    # textbook success -- never printed "[TASK COMPLETE]". The real trace (trimmed to end well
    # before this same session's later wild-battle rows, so success here can only come from the
    # rival-battle-and-walk-out section) contains a SINGLE corrupted watch row mid-battle where
    # PyBoy's polling sampler caught x/y/map/party/badges/in_battle/hp all bounced to 0 for one
    # tick, sandwiched between otherwise-consistent rows. Pre-fix, that lone glitch row tripped
    # BOTH "red_map_changed_during_battle_exit_span" and "red_player_hp_reached_zero" and the
    # predicate could never recover, no matter how much genuine, later data arrived -- this is a
    # scorer bug, not a live-capture-loop wiring bug: this test drives eval.score_gate0._red_success
    # directly, offline, on the complete real trace, with no capture rig involved.
    rows = _load_oracle_fixture("gate0_red_human_attempt2_completion.jsonl")
    ok, failures = _red_success(rows)
    assert ok, failures
    assert failures == []


def test_red_real_incomplete_attempt_without_post_exit_movement_still_fails():
    # Sibling of the above, from the SAME incident: David's first human-baseline attempt (also
    # archived, also never detected) shows the identical single-tick corruption artifact mid-battle
    # (proving it's a recurring real PyBoy/RAM-read glitch, not a one-off), but this trace is
    # trimmed to end before the human resumed walking after the battle -- so it must still
    # correctly refuse (no >=2 distinct post-exit tiles yet). Guards against the fix in
    # eval/score_gate0.py overcorrecting into accepting *any* trace with a glitch row, rather than
    # specifically filtering rows matching the full corruption signature (every watched field 0).
    rows = _load_oracle_fixture("gate0_red_human_attempt1_no_movement.jsonl")
    ok, failures = _red_success(rows)
    assert not ok
    assert failures == ["red_no_free_movement_after_exit"]


def test_pass_matrix():
    result = _score()
    assert result["readiness"] == "GO"
    assert result["overall"] == "PASS"


def test_arm_capability_failure():
    result = _score(red=_red(False))
    assert result["overall"] == "FAIL_CAPABILITY"
    assert result["readiness"] == "NO_GO"


def test_capability_over_2x_human_still_fails_unaffected_by_wake_amendment():
    # The 2x-human wall-clock/action bar (design doc "Capability bar") is untouched by the
    # 2026-07-21 Cheap-basis amendment -- a task success that took too long/too many actions vs.
    # the human baseline must still fail capability even though wakes are now non-gating.
    verified = _verified()
    verified["metrics"]["red"]["wall_clock_s"] = 2 * verified["metrics"]["red"]["human_wall_clock_s"] + 1
    result = score(_manifest(), _audits(), {"red": _red(), "miniwob": _miniwob()}, verified)
    assert result["overall"] == "FAIL_CAPABILITY"
    assert "red:wall_clock_over_2x_human" in result["failures"]["capability"]


def test_cheap_failure():
    # 2026-07-21 amendment: Cheap now rests on cost-per-task, not wakes-per-task (wakes/task is
    # deferred -- reports/2026-07-13-minimum-north-star-gate-0-design.md AMENDMENT block,
    # reports/2026-07-21-gate0-wake-grounding.md). A wake overrun alone must NOT gate FAIL_CHEAP
    # anymore -- only a $/credit cap breach does. See test_wake_cap_alone_no_longer_blocks_pass
    # and test_gate0_wake_accounting_integration.py for the wakes-non-gating proof.
    verified = _verified()
    verified["metrics"]["red"]["cost_usd"] = 5.01
    result = score(_manifest(), _audits(), {"red": _red(), "miniwob": _miniwob()}, verified)
    assert result["overall"] == "FAIL_CHEAP"
    assert "red:arm_cap" in result["failures"]["cheap"]


def test_wake_cap_alone_no_longer_blocks_pass():
    # The pre-amendment per-arm wake cap (<=90/<=50) and combined cap (<=140) are dropped from
    # gating -- a wake count far over the OLD caps must not affect the verdict as long as cost/
    # credit caps clear. Wakes still ride along in the verdict payload, informational only.
    verified = _verified()
    verified["metrics"]["red"]["wakes"] = 9999
    verified["metrics"]["miniwob"]["wakes"] = 9999
    result = score(_manifest(), _audits(), {"red": _red(), "miniwob": _miniwob()}, verified)
    assert result["overall"] == "PASS"
    assert result["cheap_basis"] == "cost_per_task"
    assert result["wake_accounting"]["status"] == "DEFERRED"


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


def test_score_manifest_missing_or_corrupt_oracle_is_a_verdict_not_a_crash(monkeypatch, tmp_path):
    # Launch blocker: score_manifest() read each arm's pinned oracle.jsonl unguarded, so a run that
    # died before writing it raised FileNotFoundError straight out of the public entry point --
    # a stack trace where a verdict belongs. Both arms are driven in one call to prove the two
    # cases stay DISTINGUISHABLE: red's oracle is absent, miniwob's is present but not JSONL.
    expected_pins = tmp_path / "expected-pins.json"
    expected_pins.write_text(json.dumps({"schema_version": 2}), encoding="utf-8")
    corrupt_oracle = tmp_path / "corrupt-oracle.jsonl"
    corrupt_oracle.write_text('{"episode": 0, "seed": 0, "done": tru', encoding="utf-8")

    def _pinned(oracle):
        return {"transcript": str(tmp_path / "transcript.jsonl"),
                "receipt": str(tmp_path / "receipt.json"),
                "expected_pins": str(expected_pins),
                "artifacts_dir": str(tmp_path / "artifacts"),
                "peer_receipt": str(tmp_path / "peer-receipt.json"),
                "oracle": oracle}

    pinned = {"red": _pinned(str(tmp_path / "absent" / "oracle.jsonl")),
              "miniwob": _pinned(str(corrupt_oracle))}
    expected_hash = hashlib.sha256(expected_pins.read_bytes()).hexdigest()
    pins_path = tmp_path / "pins.json"
    pins_path.write_text(json.dumps({
        "schema_version": 1, "mode": "readiness_dev", "audit_paths": pinned,
        "expected_pins_sha256": {"red": expected_hash, "miniwob": expected_hash},
    }), encoding="utf-8")
    monkeypatch.setitem(scorer.SOURCE_PIN_FILES, "readiness_dev", pins_path)

    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps({"mode": "readiness_dev", "arms": {
        arm: {"codex_audit": {k: v for k, v in pins.items() if k != "oracle"},
              "oracle": pins["oracle"]}
        for arm, pins in pinned.items()}}), encoding="utf-8")

    result = scorer.score_manifest(manifest_path)
    assert "source_unreadable:oracle:red" in result["failures"]["source"]
    assert "source_malformed:oracle:miniwob" in result["failures"]["source"]


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
