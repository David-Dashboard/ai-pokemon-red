"""Entity-grounding gate scorer v4 -- replaces v3's freeform-prose input pipe (regex-over-`remember`-
lines) with a structured claims log. Full pre-registration: `reports/2026-07-05-entity-v4-design.md`
(THE spec; this docstring restates it, that report is authoritative on any conflict).

WHY v4 EXISTS: `eval/score_entity_gate_v3.py`'s `parse_transcript` scrapes freeform `remember` text with
brittle regexes -- it has FOUR failure modes and killed both prior paid runs (v3, v3.1) before the bar
was ever computed. v4 replaces the *input pipe only*: the brain now calls five typed claim tools
(`claim_entity`/`claim_near`/`declare`/`reject`/`note_reading`, `world_mcp.py`'s `KIRBY_CLAIMS`-gated
surface) that each append ONE typed JSON record to `world/claims.jsonl`. The scorer reads DATA, not
prose.

FROZEN: this file imports every constant and every math/guard function it needs from
`eval/score_entity_gate_v3.py` BYTE-IDENTICAL (never copy-pasted, never re-typed) -- `v3.py` itself is
untouched, and importing it re-fires its own import-time
`_assert_bar_is_satisfiable_for_all_scoreable_b_k()` assertion. The ONLY new logic in this file is:
  1. `parse_claims` -- dispatches on `record["event"]` (typed JSON, no regex / no if-elif-over-prose)
     and emits the exact same 11-key parsed dict v3's `parse_transcript` does, so every downstream v3
     function (`_grounded`, `_coverage`, `skill_guard`, ...) consumes it unmodified.
  2. `score()` -- reads `<dir>/world/claims.jsonl` (FAILS LOUD if absent -- never silently scores an
     absent file as NO_DECLARE) instead of `<dir>/transcript.jsonl`, and its body from the parse call
     down is a VERBATIM copy of v3's `score()` (doc: "UNAVOIDABLE DUPLICATION... do NOT refactor v3
     into a shared helper -- that edits the frozen file"), swapping only the parse call.

STEP SEMANTICS (doc "STEP SEMANTICS", the load-bearing decision): `claim_near`/`claim_entity` records
carry TWO fields -- `step` (BRAIN-SUPPLIED, the scored quantity, identical to how v3's watermark rule
works today) and `revealed_at` (SERVER-STAMPED `_obs_count` at call time, world_mcp.py). The retroactive
test stays the byte-identical `revealed_at > step` (v3's `revealed_at_log > step` check, same shape).

Usage:
    uv run python -m eval.score_entity_gate_v4 runs/<dir>
        (reads <dir>/world/claims.jsonl, <dir>/world/oracle.jsonl, <dir>/world/skills.jsonl)
"""
from __future__ import annotations

import argparse
import os
import sys

from eval.score_entity_gate_v3 import (
    B_K_CEILING,
    MACRO_INTERIOR_MAX_FRACTION,
    MALFORMED_MAX_FRACTION,
    MIN_NEAR,
    MIN_SESSION_DROPS,
    MIN_TOTAL_STEPS,
    RETROACTIVE_MAX_FRACTION,
    UNMATCHED_MAX_FRACTION,
    _drop_steps,
    _grounded,
    _is_macro_interior,
    _oracle_hp_by_step,
    format_report as _v3_format_report,
    load_jsonl,
    macro_spans,
    skill_guard,
)


# ---------------------------------------------------------------------------
# NEW: parse_claims -- dispatch on record["event"], typed fields, no regex. Emits the byte-identical
# 11-key dict v3's parse_transcript produces (doc: "score() consumes" this shape unmodified).
# ---------------------------------------------------------------------------

def parse_claims(claims: list[dict], oracle: list[dict], skills: list[dict] | None = None) -> dict:
    """Same exclusion/dedupe rules as v3's parse_transcript, applied to typed claims.jsonl records
    instead of freeform `remember` text: retroactive (`revealed_at > step`) checked BEFORE
    macro-interior (order mirrors v3's NEAR handling), then (id, step) dedupe (first-wins).
    `note_reading` records are audit-only and excluded from scoring entirely (doc: "EXCLUDED from
    parse_claims' scored dispatch") -- they do not feed `n_lines` or any other counter here.
    `malformed` stays at 0 by construction: out-of-enum / short args are rejected at TOOL time
    (world_mcp.py's claim handlers) and never written to claims.jsonl, so this dict's `malformed` key
    is imported-but-unreachable, matching the doc's "keep MALFORMED_MAX_FRACTION imported-but-
    unreachable" instruction."""
    spans = macro_spans(skills or [])
    hp_by_step = _oracle_hp_by_step(oracle)

    ent_claims: dict[int, list[dict]] = {}
    nears: dict[int, list[dict]] = {}
    declared_threats: set[int] = set()
    declared_benign: set[int] = set()
    rejected: dict[int, str] = {}
    malformed = 0
    duplicates = 0
    retroactive = 0
    macro_interior = 0
    macro_interior_ent = 0
    seen_nears: set[tuple[int, int]] = set()

    n_lines = 0
    for rec in claims:
        event = rec.get("event")
        if event == "claim_entity":
            n_lines += 1
            eid = int(rec["id"])
            x0, y0, x1, y1 = rec["region"]
            step = int(rec["step"])
            kind = rec["kind"]
            if _is_macro_interior(step, spans):
                macro_interior_ent += 1   # doc "NEAR/ENT claim" -- excluded even though descriptive-only today
                continue
            ent_claims.setdefault(eid, []).append(
                {"region": (int(x0), int(y0), int(x1), int(y1)), "step": step, "claim": kind})
        elif event == "claim_near":
            n_lines += 1
            eid = int(rec["id"])
            step = int(rec["step"])
            revealed_at = int(rec["revealed_at"])
            if revealed_at > step:
                retroactive += 1
                continue
            if _is_macro_interior(step, spans):
                macro_interior += 1
                continue
            key = (eid, step)
            if key in seen_nears:
                duplicates += 1
                continue
            seen_nears.add(key)
            matched = step in hp_by_step
            nears.setdefault(eid, []).append({"step": step, "matched": matched})
        elif event == "declare":
            n_lines += 1
            eid = int(rec["id"])
            kind = rec.get("kind")
            if kind == "threat":
                declared_threats.add(eid)
            elif kind == "benign":
                declared_benign.add(eid)
            else:
                malformed += 1   # unreachable in practice -- world_mcp.py rejects out-of-enum kind at tool time
        elif event == "reject":
            n_lines += 1
            eid = int(rec["id"])
            rejected[eid] = str(rec.get("reason", "")).strip()
        # "note_reading" and anything else: audit-only / unrecognized -- never scored, never counted.

    return {"ent_claims": ent_claims, "nears": nears,
            "declared_threats": declared_threats, "declared_benign": declared_benign,
            "rejected": rejected, "malformed": malformed, "duplicates": duplicates,
            "retroactive": retroactive, "macro_interior": macro_interior,
            "macro_interior_ent": macro_interior_ent, "n_lines": n_lines}


# ---------------------------------------------------------------------------
# score() -- VERBATIM copy of v3.score()'s body from its parse call down (doc: "UNAVOIDABLE
# DUPLICATION... do NOT refactor v3 into a shared helper"), swapping ONLY the parse call and the
# claims-file read (FAILS LOUD if absent, instead of v3's transcript.jsonl read).
# ---------------------------------------------------------------------------

def score(claims_path: str, oracle_path: str, skills_path: str) -> dict:
    if not os.path.exists(claims_path):
        raise FileNotFoundError(
            f"no claims.jsonl at {claims_path!r} -- v4 requires the structured-claims log "
            "(world_mcp.py's KIRBY_CLAIMS-gated tools); an absent file is a run-setup error, "
            "never silently scored as NO_DECLARE.")
    claims = load_jsonl(claims_path)
    oracle = load_jsonl(oracle_path)
    skills = load_jsonl(skills_path) if os.path.exists(skills_path) else []

    parsed = parse_claims(claims, oracle, skills)
    nears = parsed["nears"]
    declared_threats, declared_benign, rejected = (
        parsed["declared_threats"], parsed["declared_benign"], parsed["rejected"])
    n_malformed, n_duplicates, n_lines = parsed["malformed"], parsed["duplicates"], parsed["n_lines"]
    n_retroactive = parsed["retroactive"]
    n_macro_interior = parsed["macro_interior"]

    guard = skill_guard(skills)

    result: dict = {
        "declared_threats": sorted(declared_threats), "declared_benign": sorted(declared_benign),
        "rejected": rejected, "entities_seen": sorted(parsed["ent_claims"]),
        "malformed_lines": n_malformed, "duplicate_lines": n_duplicates,
        "retroactive_lines": n_retroactive, "macro_interior_lines": n_macro_interior,
        "macro_interior_ent_lines": parsed["macro_interior_ent"],
        "skill_guard": guard,
    }

    if n_lines and n_malformed and (n_malformed / n_lines) >= MALFORMED_MAX_FRACTION:
        result["verdict"] = "INSUFFICIENT_DATA"
        result["reason"] = (f"{n_malformed}/{n_lines} protocol lines are malformed "
                            f"(>= {MALFORMED_MAX_FRACTION:.0%} -- must stay below)")
        return result

    n_accepted_nears = sum(len(v) for v in nears.values())
    # NEAR pool for the retroactive-fraction check = accepted + retroactive (macro-interior lines are a
    # SEPARATE exclusion class with its own cap below, doc §5.6 -- not merged into this denominator).
    n_near_pool = n_accepted_nears + n_retroactive
    if n_near_pool and n_retroactive and (n_retroactive / n_near_pool) >= RETROACTIVE_MAX_FRACTION:
        result["verdict"] = "INSUFFICIENT_DATA"
        result["reason"] = (f"{n_retroactive}/{n_near_pool} NEAR lines are RETROACTIVE (logged "
                            f"after a later step's outcome was already observable) "
                            f"(>= {RETROACTIVE_MAX_FRACTION:.0%} -- must stay below)")
        return result

    # v3 macro-interior taint (doc §5.6). Denominator = all NEAR lines that reached this check
    # (accepted + macro-interior) -- the same "fraction of all NEAR lines" shape as RETROACTIVE.
    n_macro_pool = n_accepted_nears + n_macro_interior
    if n_macro_pool and n_macro_interior and (n_macro_interior / n_macro_pool) >= MACRO_INTERIOR_MAX_FRACTION:
        result["verdict"] = "INSUFFICIENT_DATA"
        result["reason"] = (f"{n_macro_interior}/{n_macro_pool} NEAR lines are MACRO-INTERIOR (claim a "
                            f"step hidden inside a run_skill span) "
                            f"(>= {MACRO_INTERIOR_MAX_FRACTION:.0%} -- must stay below)")
        return result

    benign_ids = declared_benign | set(rejected)
    conflicting = declared_threats & benign_ids
    result["conflicting_declarations"] = sorted(conflicting)
    declared_threats = declared_threats - conflicting
    benign_ids = benign_ids - conflicting
    conflict_note = (f" ({len(conflicting)} id(s) excluded as CONFLICTING: declared both threat and "
                     f"benign/REJECTed: {sorted(conflicting)})") if conflicting else ""
    if not declared_threats:
        result["verdict"] = "NO_DECLARE"
        result["reason"] = "no declare(kind='threat') call found" + conflict_note
        return result
    if not benign_ids:
        result["verdict"] = "NO_DECLARE"
        result["reason"] = ("no declare(kind='benign') or reject(...) call found -- arm (b) unexercised"
                            + conflict_note)
        return result

    hp_by_step = _oracle_hp_by_step(oracle)
    drops, n_scoreable_total = _drop_steps(hp_by_step)
    result["total_scoreable_steps"] = n_scoreable_total
    result["session_drop_steps"] = len(drops)

    if n_scoreable_total < MIN_TOTAL_STEPS:
        result["verdict"] = "INSUFFICIENT_DATA"
        result["reason"] = f"only {n_scoreable_total} scoreable oracle steps (< {MIN_TOTAL_STEPS})"
        return result

    if len(drops) < MIN_SESSION_DROPS:
        result["verdict"] = "INSUFFICIENT_DROPS"
        result["reason"] = (f"session has {len(drops)} drop step(s) (< {MIN_SESSION_DROPS}) -- too few "
                            "consequences to attribute against; no PASS/FAIL computed")
        return result

    steps_sorted = sorted(hp_by_step)
    scoreable_steps: set[int] = set()
    prev_defined = False
    for s in steps_sorted:
        if hp_by_step[s] is not None and prev_defined:
            scoreable_steps.add(s)
        prev_defined = hp_by_step[s] is not None
    non_drop_steps = scoreable_steps - drops

    all_entries = [e for entries in nears.values() for e in entries]
    n_near_lines = len(all_entries)
    n_unmatched_total = sum(1 for e in all_entries if not e["matched"])
    result["near_lines"] = n_near_lines
    result["unmatched_lines"] = n_unmatched_total
    if n_near_lines and n_unmatched_total and (n_unmatched_total / n_near_lines) >= UNMATCHED_MAX_FRACTION:
        result["verdict"] = "INSUFFICIENT_DATA"
        result["reason"] = (f"{n_unmatched_total}/{n_near_lines} NEAR lines reference steps with "
                            f"no oracle row (>= {UNMATCHED_MAX_FRACTION:.0%} -- must stay below)")
        return result

    threat_scores = {eid: _grounded(eid, nears, drops, non_drop_steps) for eid in declared_threats}
    benign_scores = {eid: _grounded(eid, nears, drops, non_drop_steps) for eid in benign_ids}
    result["threat_scores"] = threat_scores
    result["benign_scores"] = benign_scores

    threats_grounded = [s for s in threat_scores.values() if s["grounded"]]
    threats_with_evidence = [s for s in threat_scores.values() if not s["insufficient"]]
    benigns_scoreable = [s for s in benign_scores.values() if not s["insufficient"]]
    benigns_correctly_rejected = [s for s in benigns_scoreable if not s["grounded"]]

    if not threats_with_evidence or not benigns_scoreable:
        result["verdict"] = "INSUFFICIENT_DATA"
        result["reason"] = (f"need a scoreable declared threat (|N_k|>={MIN_NEAR}, b_k<={B_K_CEILING}) "
                            "AND a scoreable declared-benign/rejected entity to compute a verdict")
        return result

    arm_a = len(threats_grounded) > 0
    arm_b = len(benigns_correctly_rejected) > 0
    result["arm_a"] = arm_a
    result["arm_b"] = arm_b
    grounding_verdict = "PASS" if (arm_a and arm_b) else "FAIL"

    # skill-mechanism guard (v3 §5.4), checked FIRST relative to the grounding verdict per the doc's own
    # wording -- the grounding numbers above are already computed, so "checked first" is expressed here
    # as overriding the final verdict, not skipping the computation.
    if not guard["guard_pass"]:
        result["verdict"] = "INSUFFICIENT_DATA"
        result["reason"] = (f"skill-mechanism guard failed: {guard['n_qualifying_conditional_calls']} "
                            "qualifying-conditional run_skill call(s) (need >= 1) -- conditional-half "
                            "evidence untested; grounding numbers above are reported for audit only")
        return result

    result["verdict"] = grounding_verdict
    return result


def format_report(r: dict) -> str:
    """Reuses v3's format_report UNMODIFIED (the verdict dict shape is byte-identical -- doc: same 11-
    key parsed dict, same score() body) -- only the header line is swapped so a v4 report doesn't claim
    to be v3's."""
    return _v3_format_report(r).replace(
        "Entity-grounding gate v3 score (repaired bar + macro-interior exclusion + skill guard)",
        "Entity-grounding gate v4 score (structured claims; v3 bar math imported byte-identical)",
    )


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("run_dir", help="run directory containing world/{claims,oracle,skills}.jsonl")
    args = ap.parse_args(argv)
    claims_path = os.path.join(args.run_dir, "world", "claims.jsonl")
    oracle_path = os.path.join(args.run_dir, "world", "oracle.jsonl")
    skills_path = os.path.join(args.run_dir, "world", "skills.jsonl")
    result = score(claims_path, oracle_path, skills_path)
    print(format_report(result))
    return 0 if result.get("verdict") in ("PASS", "FAIL", "INSUFFICIENT_DROPS") else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
