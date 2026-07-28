"""Fail-closed offline scorer for the two-arm North Star Gate 0."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from tools.check_gate0_codex import audit as audit_codex


ROOT = Path(__file__).resolve().parents[1]
MODES = {
    "readiness_dev": (ROOT / "eval" / "fixtures" / "gate0_miniwob_dev_seeds.json", [0, 1, 2, 3, 4]),
    "paid_gate0": (ROOT / "eval" / "fixtures" / "gate0_miniwob_paid_seeds.json", [1000, 1001, 1002, 1003, 1004]),
    # Gate 0 v2's FRESH held-out block (prereg §4.1/P9, reports/2026-07-25-gate0-v2-prereg.md).
    # Purely ADDITIVE: paid_gate0 above is byte-untouched, so the banked (void-as-printed) v1 result
    # stays scoreable exactly as it was. v2 needs its own seeds because 1000..1004 are SPENT — the v1
    # Arm W transcript, including the correct checkbox answers, is committed at
    # reports/2026-07-24-gate0-paired-verdict/oracle.jsonl and is greppable by any agent with repo
    # access, so a re-attempt on them could not be reported as held-out generalization.
    "paid_gate0_v2": (ROOT / "eval" / "fixtures" / "gate0_miniwob_paid_v2_seeds.json",
                      [417545, 662948, 660918, 981149, 558952]),
}
SOURCE_PIN_FILES = {
    "readiness_dev": ROOT / "eval" / "fixtures" / "gate0_readiness_dev_source_pins.json",
    "paid_gate0": ROOT / "eval" / "fixtures" / "gate0_paid_source_pins.json",
    "paid_gate0_v2": ROOT / "eval" / "fixtures" / "gate0_paid_v2_source_pins.json",
}
# The one MiniWoB task Gate 0 pins for every mode (dev seeds 0-4, paid seeds 1000-1004, paid-v2 the
# §4.1-derived fresh block) — see
# reports/2026-07-13-minimum-north-star-gate-0-design.md "MiniWoB click-checkboxes".
MINIWOB_TASK = "click-checkboxes"
# score_manifest()'s caller-supplied per-arm paths that must be bound to a frozen pin, never
# taken from the manifest at face value.
AUDIT_PATH_KEYS = ("transcript", "receipt", "expected_pins", "artifacts_dir", "peer_receipt", "oracle")


def _jsonl(path: str | Path) -> list[dict]:
    return [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines()
            if line.strip()]


def _red_success(rows: list[dict]) -> tuple[bool, list[str]]:
    failures: list[str] = []
    watches = [row.get("watch") for row in rows if isinstance(row.get("watch"), dict)]
    if not watches or watches[0].get("party") != 0:
        return False, ["red_not_fresh_party_zero"]
    party_idx = next((i for i in range(1, len(watches))
                      if watches[i].get("party") != watches[i - 1].get("party")), None)
    if party_idx is None:
        failures.append("red_no_party_0_to_1")
        return False, failures
    if watches[party_idx - 1].get("party") != 0 or watches[party_idx].get("party") != 1:
        failures.append("red_first_party_transition_not_exactly_0_to_1")
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
    # A one-tick corrupted RAM read, never a real state. MECHANISM (established 2026-07-28 by
    # offline reproduction, not inferred): roms/PokemonRed.gb carries CGB flag 0xC0 in its header,
    # so PyBoy runs it in CGB mode, where 0xD000-0xDFFF is WRAM-BANK-SWITCHED by SVBK (0xFF70).
    # Pokemon Red is DMG code and never manages SVBK, but transiently stomps it (values 2-7 observed
    # live). EVERY watched address (0xD057/0xD163/0xD16C/0xD16D/0xD356/0xD35E/0xD361/0xD362) lies in
    # that banked window, so a stomped tick reads ALL EIGHT fields out of the wrong WRAM bank at
    # once, and the next sample is back on bank 1 -- hence "sandwiched between identical, consistent
    # neighbor rows". 358/358 stomped ticks diverged from truth in a 150k-frame mid-battle scan.
    #
    # The alternate bank holds only residue, so the corrupt row reads party/in_battle/HP all 0 with
    # the four D3xx fields all showing one repeated residue byte. All-zero is the common case (an
    # untouched bank); a DIRTY bank gives the identical shape with a NON-ZERO byte. Both variants
    # sit in committed traces: all-zero at eval/fixtures/gate0_red_human_attempt1_no_movement.jsonl
    # row 624 and gate0_red_human_attempt2_completion.jsonl row 494 (BOTH mid-battle, in_battle==2
    # on both neighbors -- so this artifact demonstrably lands inside THIS span); the non-zero
    # variant {x/y/map/badges=1, rest=0} at gate0_red_human_attempt2_completion.jsonl row 363 and
    # reports/2026-07-24-gate0-armR-verdict/oracle.jsonl rows 335/347. ~1800 offline reproductions
    # across boot and mid-battle savestates produced this signature and no other shape. The former
    # all-zero-only predicate was this same signature with a clean bank; widening it closes the gap
    # reports/2026-07-25-gate0-v2-prereg.md §5.4 C8 pre-registered as a live risk to this exact span
    # (deviation recorded in reports/2026-07-28-gate0-v2-deviations.md).
    #
    # Still deliberately narrow (PR #121 review Major 1): a filter keyed on `party` alone would also
    # drop a row with a genuinely-corrupted party byte AND a real HP=0 or real map-change on the very
    # same row, silently erasing a real failure. This predicate fires only on the full eight-field
    # signature, never on a single stray field. It additionally requires party == 0, and this span
    # exists only after `party_idx` proved an exact 0->1 party transition -- so every GENUINE row in
    # it has party >= 1, which makes a genuine death, a genuine map change and a genuine badge all
    # unreachable by this filter by construction. Any non-int (or bool) field keeps the row.
    def _is_corrupt_glitch_row(w):
        vals = [w.get(k) for k in ("x", "y", "map", "badges",
                                   "party", "in_battle", "party_hp_hi", "party_hp_lo")]
        if any(isinstance(v, bool) or not isinstance(v, int) for v in vals):
            return False
        x, y, map_, badges, party, in_battle, hp_hi, hp_lo = vals
        return party == in_battle == hp_hi == hp_lo == 0 and x == y == map_ == badges

    safety_span = [w for w in watches[battle_idx:exit_idx + 10] if not _is_corrupt_glitch_row(w)]
    hp_values = []
    battle_map = watches[battle_idx].get("map")
    for watch in safety_span:
        hi, lo = watch.get("party_hp_hi"), watch.get("party_hp_lo")
        if (isinstance(hi, bool) or isinstance(lo, bool) or not isinstance(hi, int)
                or not isinstance(lo, int) or not 0 <= hi <= 255 or not 0 <= lo <= 255):
            failures.append("red_missing_player_hp_oracle")
            break
        hp_values.append((hi << 8) | lo)
        if battle_map is None or watch.get("map") != battle_map:
            failures.append("red_map_changed_during_battle_exit_span")
            break
    if hp_values and min(hp_values) == 0:
        failures.append("red_player_hp_reached_zero")
    post = [(w.get("x"), w.get("y")) for w in watches[exit_idx:]
            if w.get("x") is not None and w.get("y") is not None and not _is_corrupt_glitch_row(w)]
    if len(set(post)) < 2:
        failures.append("red_no_free_movement_after_exit")
    return not failures, failures


def _miniwob_success(rows: list[dict], expected_seeds: list[int]) -> tuple[bool, list[str]]:
    failures: list[str] = []
    expected = dict(enumerate(expected_seeds))
    if any(row.get("episode") not in expected or row.get("seed") != expected.get(row.get("episode"))
           for row in rows):
        failures.append("miniwob_extra_episode_or_seed_conflict")
    # Every row must carry the manifest-pinned task. A row with any other task value is a hard
    # scorer refusal (a malformed/tampered manifest), never silently ignored, regardless of
    # whether that row happens to be a terminal.
    if any(row.get("task") != MINIWOB_TASK for row in rows):
        failures.append("miniwob_wrong_task_row")
    for episode, seed in expected.items():
        episode_rows = [row for row in rows if row.get("episode") == episode and row.get("seed") == seed]
        terminal_idx = [i for i, row in enumerate(episode_rows)
                        if row.get("done") is True or row.get("abandoned") is True]
        if len(terminal_idx) != 1:
            failures.append(f"miniwob_episode_{episode}_terminal_count")
            continue
        idx = terminal_idx[0]
        terminal = episode_rows[idx]
        reward = terminal.get("reward")
        # JSON `true`/`false` decode to Python bool, and `True == 1.0` — reject bool explicitly
        # before the numeric check so a boolean can never stand in for the pinned float reward.
        success = (terminal.get("done") is True and terminal.get("abandoned") is False
                  and terminal.get("task") == MINIWOB_TASK
                  and not isinstance(reward, bool) and isinstance(reward, (int, float))
                  and reward == 1.0)
        if not success:
            failures.append(f"miniwob_episode_{episode}_terminal_not_success")
        elif idx != len(episode_rows) - 1:
            # A row for this episode/seed was logged after its success terminal (reopened,
            # duplicated, or otherwise) — the terminal must be the last thing this episode did.
            failures.append(f"miniwob_episode_{episode}_terminal_not_last_row")
    return not failures, failures


def _arm_metrics(metrics: dict, capability: bool) -> tuple[list[str], list[str]]:
    capability_failures = [] if capability else ["task_predicate_failed"]
    source_failures: list[str] = []
    # "wakes" is intentionally NOT required here (2026-07-21 Cheap-basis amendment -- see score()
    # and reports/2026-07-13-minimum-north-star-gate-0-design.md's AMENDMENT block): Codex's JSONL
    # stream has no documented per-model-decision boundary, so a wake count can never be trusted.
    # wakes is still read/reported (see _verify_sources' wake_info) but never gates -- Cheap rests
    # on cost_usd/normalized_credits, required below exactly as strict as before.
    required = ("wall_clock_s", "primitive_actions", "human_wall_clock_s", "human_primitive_actions",
                "cost_usd", "normalized_credits")
    for key in required:
        value = metrics.get(key)
        minimum = 0 if key in {"cost_usd", "normalized_credits"} else 0
        if (isinstance(value, bool) or not isinstance(value, (int, float))
                or value < minimum or (key not in {"cost_usd", "normalized_credits"} and value <= 0)):
            source_failures.append(f"missing_or_invalid_metric:{key}")
    if source_failures:
        return capability_failures, source_failures
    if metrics["wall_clock_s"] > 2 * metrics["human_wall_clock_s"]:
        capability_failures.append("wall_clock_over_2x_human")
    if metrics["primitive_actions"] > 2 * metrics["human_primitive_actions"]:
        capability_failures.append("actions_over_2x_human")
    return capability_failures, source_failures


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _resolve_root(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def _verify_audit_paths(manifest: dict) -> tuple[dict[str, dict], list[str]]:
    """Bind score_manifest()'s caller-supplied `codex_audit.*`/`oracle` paths to the same
    frozen, mode-specific source pins `_verify_sources` uses for everything else.

    These paths point at per-attempt evidence (a live transcript/receipt/oracle) whose CONTENT
    necessarily differs run to run, so (unlike the metric/wake/breaker artifacts) they cannot be
    content-hash-pinned in advance -- only their exact LOCATION can be. `expected_pins` is the
    one component that IS frozen ahead of a run (it is the pre-registered expected values), so
    its content is additionally hash-pinned. A manifest whose arm doesn't point at exactly the
    pinned locations -- or whose `expected_pins` file doesn't match the pinned hash -- is refused
    for that arm: score_manifest() never reads an unpinned path.
    """
    failures: list[str] = []
    mode = manifest.get("mode")
    if mode not in SOURCE_PIN_FILES:
        return {}, ["unknown_or_missing_gate0_mode"]
    try:
        pins = json.loads(SOURCE_PIN_FILES[mode].read_text(encoding="utf-8"))
    except Exception:
        return {}, ["audit_source_pins_unreadable"]
    if pins.get("schema_version") != 1 or pins.get("mode") != mode:
        return {}, ["audit_source_pins_schema_or_mode"]

    audit_paths = pins.get("audit_paths") or {}
    expected_hashes = pins.get("expected_pins_sha256") or {}
    arms = manifest.get("arms") or {}
    resolved: dict[str, dict] = {}
    for arm in ("red", "miniwob"):
        pinned = audit_paths.get(arm)
        if (not isinstance(pinned, dict) or set(pinned) != set(AUDIT_PATH_KEYS)
                or any(not isinstance(pinned[k], str) or not pinned[k] for k in AUDIT_PATH_KEYS)):
            failures.append(f"audit_paths_pin_missing:{arm}")
            continue
        codex_audit = (arms.get(arm) or {}).get("codex_audit")
        codex_audit = codex_audit if isinstance(codex_audit, dict) else {}
        supplied = {key: codex_audit.get(key) for key in AUDIT_PATH_KEYS if key != "oracle"}
        supplied["oracle"] = (arms.get(arm) or {}).get("oracle")
        arm_ok = True
        for key in AUDIT_PATH_KEYS:
            if supplied.get(key) != pinned[key]:
                failures.append(f"audit_path_mismatch:{arm}:{key}")
                arm_ok = False
        expected_hash = expected_hashes.get(arm)
        if not isinstance(expected_hash, str) or len(expected_hash) != 64:
            failures.append(f"expected_pins_hash_pin_missing:{arm}")
            arm_ok = False
        elif arm_ok:
            try:
                if _sha256(_resolve_root(pinned["expected_pins"])) != expected_hash:
                    failures.append(f"expected_pins_hash_mismatch:{arm}")
                    arm_ok = False
            except Exception:
                failures.append(f"expected_pins_unreadable:{arm}")
                arm_ok = False
        if arm_ok:
            resolved[arm] = dict(pinned)
    return resolved, failures


def _verify_sources(manifest: dict, audits: dict[str, dict]) -> tuple[dict, list[str]]:
    failures: list[str] = []
    mode = manifest.get("mode")
    if mode not in MODES:
        return {}, ["unknown_or_missing_gate0_mode"]
    if any("expected_seeds" in (manifest.get("arms", {}).get(name) or {}) for name in ("red", "miniwob")):
        failures.append("manifest_seed_override_forbidden")
    if "source_pins" in manifest or "source_artifacts" in manifest:
        failures.append("manifest_source_override_forbidden")
    try:
        pins_path = SOURCE_PIN_FILES[mode]
        pins = json.loads(pins_path.read_text(encoding="utf-8"))
    except Exception:
        return {}, failures + ["source_pins_unreadable"]
    if pins.get("schema_version") != 1 or pins.get("mode") != mode:
        failures.append("source_pins_schema_or_mode")
    seed_path, exact_seeds = MODES[mode]
    try:
        if json.loads(seed_path.read_text(encoding="utf-8")) != exact_seeds:
            failures.append("frozen_seed_contents")
        if pins.get("frozen_seed_sha256") != _sha256(seed_path):
            failures.append("frozen_seed_hash")
    except Exception:
        failures.append("frozen_seed_source_unreadable")

    source_paths = pins.get("artifact_paths") or {}
    pin_hashes = pins.get("artifact_sha256") or {}
    loaded = {}
    for key in ("red_agent", "red_human", "miniwob_agent", "miniwob_human",
                "wake_boundary", "live_breaker"):
        try:
            path = Path(source_paths[key])
            if not path.is_absolute():
                path = ROOT / path
            if pin_hashes.get(key) != _sha256(path):
                failures.append(f"source_hash:{key}")
                continue
            loaded[key] = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            failures.append(f"source_unreadable:{key}")

    metrics = {}
    # Wakes-per-task is DEFERRED for Gate 0 (2026-07-21 amendment: reports/2026-07-13-minimum-
    # north-star-gate-0-design.md AMENDMENT block + reports/2026-07-21-gate0-wake-grounding.md,
    # PR #126). Codex's JSONL stream has no documented per-model-decision boundary event, so
    # tools/check_gate0_codex.py::audit() is permanently fail-closed on this axis by design
    # (wake_accounting="INSUFFICIENT_WAKES", wakes=None) -- it can never report "PASS". wakes/
    # wake_accounting are still computed and carried into the verdict payload below (informational,
    # see score()'s "wake_accounting" field) but they NEVER gate the verdict. Cheap now rests on
    # cost_usd/normalized_credits only -- those checks (below, in score()) are untouched.
    wake_info: dict[str, object] = {}
    for arm in ("red", "miniwob"):
        agent, human = loaded.get(f"{arm}_agent"), loaded.get(f"{arm}_human")
        if not isinstance(agent, dict) or not isinstance(human, dict):
            continue
        if (agent.get("schema_version"), agent.get("arm"), agent.get("role"), agent.get("mode")) != (1, arm, "agent", mode):
            failures.append(f"agent_metric_identity:{arm}")
        if (human.get("schema_version"), human.get("arm"), human.get("role"), human.get("mode")) != (1, arm, "human", mode):
            failures.append(f"human_metric_identity:{arm}")
        metrics[arm] = {
            "wall_clock_s": agent.get("wall_clock_s"), "primitive_actions": agent.get("primitive_actions"),
            "human_wall_clock_s": human.get("wall_clock_s"),
            "human_primitive_actions": human.get("primitive_actions"), "wakes": agent.get("wakes"),
            "cost_usd": agent.get("cost_usd"), "normalized_credits": agent.get("normalized_credits"),
        }
        audit = audits.get(arm) or {}
        wake_info[arm] = {"wakes": agent.get("wakes"), "wake_accounting": audit.get("wake_accounting")}
    wake = loaded.get("wake_boundary") or {}
    breaker = loaded.get("live_breaker") or {}
    # Structural pin only (present, correctly shaped) -- `status` is the SAME deferred wake axis as
    # the per-arm check above, so it is reported (below) but no longer required to be "PASS".
    if wake.get("schema_version") != 1 or wake.get("kind") != "exact_wake_boundary":
        failures.append("wake_boundary_artifact")
    else:
        wake_info["exact_wake_boundary_status"] = wake.get("status")
    if (breaker.get("schema_version") != 1 or breaker.get("kind") != "live_credit_breaker"
            or breaker.get("status") != "PASS" or breaker.get("limit_normalized_credits") != 250):
        failures.append("live_breaker_artifact")
    return {"mode": mode, "expected_seeds": exact_seeds, "metrics": metrics, "wake_info": wake_info}, failures


def score(manifest: dict, audits: dict[str, dict], oracles: dict[str, list[dict]],
          verified_sources: dict | None = None, source_failures: list[str] | None = None) -> dict:
    arms = manifest.get("arms") or {}
    failures = {"constancy": [], "leak": [], "infra": [], "capability": [], "cheap": [], "source": []}
    for name in ("red", "miniwob"):
        audit = audits.get(name) or {}
        failures["leak"].extend(f"{name}:{x}" for x in audit.get("leak_failures", []))
        failures["constancy"].extend(f"{name}:{x}" for x in audit.get("constancy_failures", []))
        failures["infra"].extend(f"{name}:{x}" for x in audit.get("run_failures", []))
    red_ok, red_fail = _red_success(oracles.get("red", []))
    verified_sources = verified_sources or {}
    expected_seeds = verified_sources.get("expected_seeds")
    if expected_seeds is None:
        mode = manifest.get("mode")
        expected_seeds = MODES.get(mode, (None, []))[1]
    mw_ok, mw_fail = _miniwob_success(oracles.get("miniwob", []), expected_seeds)
    failures["capability"].extend(f"red:{x}" for x in red_fail)
    failures["capability"].extend(f"miniwob:{x}" for x in mw_fail)
    for name, ok in (("red", red_ok), ("miniwob", mw_ok)):
        cap, source = _arm_metrics((verified_sources.get("metrics") or {}).get(name, {}), ok)
        failures["capability"].extend(f"{name}:{x}" for x in cap if f"{name}:{x}" not in failures["capability"])
        failures["source"].extend(f"{name}:{x}" for x in source)

    failures["source"].extend(source_failures or (["unverified_source_artifacts"] if not verified_sources else []))
    if any(audits.get(name, {}).get("accounting_failures") for name in ("red", "miniwob")):
        failures["source"].append("codex_accounting_audit_failed")

    if not failures["source"]:
        metrics = verified_sources["metrics"]
        # Cheap bar rests on cost-per-task only (2026-07-21 amendment, reports/2026-07-13-minimum-
        # north-star-gate-0-design.md AMENDMENT block): the $/credit caps below are UNCHANGED from
        # the original design (design doc "Cheap bar" table) -- the wake-per-task caps (90/50/140
        # wakes) that used to sit alongside them are dropped from gating because no per-decision
        # wake count is observable (see _verify_sources' wake_info comment). Wakes stay reported,
        # never gating (see the "wake_accounting" field on the returned verdict, below).
        limits = {"red": (5.0, 125), "miniwob": (2.0, 50)}
        for name, (cost_cap, credit_cap) in limits.items():
            if metrics[name]["cost_usd"] > cost_cap or metrics[name]["normalized_credits"] > credit_cap:
                failures["cheap"].append(f"{name}:arm_cap")
        if (sum(m["cost_usd"] for m in metrics.values()) > 7.0
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
            # Cheap is grounded on cost-per-task (2026-07-21 amendment). wake_accounting is
            # informational only -- computed/reported for the record, never gating -- until Codex
            # ships a per-model-decision boundary event (reports/2026-07-21-gate0-wake-grounding.md).
            "cheap_basis": "cost_per_task",
            "wake_accounting": {
                "status": "DEFERRED",
                "reason": "no_per_model_decision_observable_in_codex_jsonl_stream",
                "evidence": "reports/2026-07-21-gate0-wake-grounding.md",
                "detail": verified_sources.get("wake_info", {}),
            },
            "spend_usd": sum((verified_sources.get("metrics", {}).get(name, {}) or {}).get("cost_usd", 0)
                             for name in ("red", "miniwob"))}


def score_manifest(path: str | Path) -> dict:
    manifest = json.loads(Path(path).read_text(encoding="utf-8"))
    pinned_paths, path_failures = _verify_audit_paths(manifest)
    audits, oracles, oracle_failures = {}, {}, []
    for name in ("red", "miniwob"):
        pins = pinned_paths.get(name)
        if pins is None:
            continue   # unpinned/mismatched source: never read a manifest-chosen path
        audits[name] = audit_codex(_resolve_root(pins["transcript"]), _resolve_root(pins["receipt"]),
                                   _resolve_root(pins["expected_pins"]), _resolve_root(pins["artifacts_dir"]),
                                   name, _resolve_root(pins["peer_receipt"]))
        # A run that dies before writing its oracle is a MISSING SOURCE, not a scorer crash: this
        # read used to raise FileNotFoundError straight out of the public entry point, handing the
        # operator a stack trace where a verdict belongs (the exact misdiagnosis .claude/skills/
        # diagnose-a-run exists to prevent). Fail closed through the same machinery every other
        # missing source already uses -- `source_unreadable:*` -> INSUFFICIENT_DATA/
        # INSUFFICIENT_SOURCE -- exactly as _verify_sources does for its six pinned artifacts.
        # EXACTLY TWO conditions are caught, and they are deliberately DISTINCT because triage acts
        # on them differently:
        #   OSError                            -> the path could not be opened/read AT ALL (absent,
        #                                         permissions, is-a-directory). Points at plumbing.
        #   JSONDecodeError/UnicodeDecodeError -> the file IS there but its BYTES do not decode as
        #                                         JSONL (half-written by a killed run, truncated
        #                                         mid-line, wrong encoding). The partial trace may
        #                                         still be worth reading.
        # Nothing else is caught, and that is a deliberate limit, not an oversight. An oracle whose
        # lines decode as valid JSON but are the WRONG SHAPE (e.g. `5\n7\n` -- ints, not objects)
        # still crashes downstream in _red_success with AttributeError, because that is a claim
        # about CONTENT, and content is what the predicates exist to judge; quietly converting it
        # into "no oracle" would let a structurally-wrong trace masquerade as an absent one. A bare
        # `except Exception` here would do exactly that AND hide real scorer bugs behind a
        # plausible-looking verdict -- worse than the crash being fixed. See
        # core/perception_plugin.py:302-306 for the swallow this is refusing to duplicate.
        try:
            oracles[name] = _jsonl(_resolve_root(pins["oracle"]))
        except OSError:
            oracle_failures.append(f"source_unreadable:oracle:{name}")
        except (json.JSONDecodeError, UnicodeDecodeError):
            oracle_failures.append(f"source_malformed:oracle:{name}")
    verified, source_failures = _verify_sources(manifest, audits)
    return score(manifest, audits, oracles, verified,
                 (source_failures or []) + path_failures + oracle_failures)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", type=Path)
    args = parser.parse_args()
    result = score_manifest(args.manifest)
    print(json.dumps(result, sort_keys=True))
    return 0 if result["readiness"] == "GO" else 1


if __name__ == "__main__":
    raise SystemExit(main())
