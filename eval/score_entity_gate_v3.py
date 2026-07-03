"""Entity-grounding gate scorer v3 -- repairs v2's arithmetically unreachable bar and adds two new
guards the Kirby skill port needs. Full pre-registration: `reports/2026-07-03-kirby-skill-port-entity-v3.md`
§5 (THE spec; this docstring restates it, the report is authoritative on any conflict).

This is a NEW file. `eval/score_entity_gate_v2.py` is untouched -- its FAIL (`b_k=0.812` made the bar
`q_k >= 1.112`, impossible since `q_k <= 1.0`) stays on the books as-is.

MACHINERY CARRIED OVER UNCHANGED FROM v2 (doc §5.1): BCD-identity hp oracle (the `_bcd()` decode is the
identity function for any raw byte in 0-9, so it works unchanged whether the underlying byte is truly
BCD (Cave Noire, 0xC120) or already a plain int in 0-9 (Kirby, 0xD086, per world_mcp.py:170-174's
verified-by-probe note) -- ONLY the watched address changes, not the decode); `WINDOW = 15`; the
watermark rule (revealed-step watermark from read_region/whats_changed `step=<N>` tokens only; bare
observe() does not advance it); dedupe (first-wins); `UNMATCHED_MAX_FRACTION = 0.05`;
`MALFORMED_MAX_FRACTION = 0.20`; `RETROACTIVE_MAX_FRACTION = 0.20`; `MIN_NEAR = 3`; `MIN_TOTAL_STEPS = 30`;
`MIN_SESSION_DROPS = 5`; the CONFLICTING-declaration guard.

THREE CHANGES FROM v2 (doc §5.2-§5.6):

1. THE REPAIRED BAR (§5.2). `GROUNDED` (threat) iff ALL FOUR, inclusive `>=`/`<=` throughout:
     - `q_k >= 0.80`                    (NEW absolute floor)
     - `q_k - b_k >= 0.15`              (margin, halved from v2's 0.30 -- see doc §5.2 "why 0.15")
     - `b_k <= 0.70`                    (B_K_CEILING precondition -- checked FIRST, see below)
     - `|N_k| >= MIN_NEAR` (3)          (unchanged)
   `b_k > 0.70` reports that entity `INSUFFICIENT_DATA` (camping -- session produced no exposure
   contrast) BEFORE the floor/margin/MIN_NEAR conditions are even evaluated -- order matters for the
   per-entity report, not for overall correctness (all four must hold for GROUNDED regardless of
   evaluation order, per doc §5.2). A benign/rejected entity `j` is correctly rejected iff it is
   scoreable (`|N_j| >= MIN_NEAR` AND `b_j <= 0.70`, same ceiling) AND NOT (`q_j >= 0.80` AND
   `q_j - b_j >= 0.15`). Overall: PASS = >=1 declared threat GROUNDED AND >=1 declared-benign/REJECTed
   entity correctly rejected (both arms required, restated unchanged from v2 per doc §5.2). The doc pins
   a correctness assertion: the repaired bar must be `<= 1.0` (satisfiable) for every `b_k` in the
   scoreable range `[0, 0.70]` -- checked in `_assert_bar_is_satisfiable_for_all_scoreable_b_k` below,
   run once at import time, not just argued in prose (doc §5.2, final bullet).

2. MACRO-INTERIOR EXCLUSION (§5.6). A NEAR/ENT claim naming step `n` is MACRO-INTERIOR (excluded from
   scoring, counted, reported) iff some `run_skill` record `r` in skills.jsonl satisfies
   `r.step - r.world_steps_used < n < r.step` (strict on both sides -- the span's START step
   `r.step - r.world_steps_used` and END step `r.step` remain claimable; only steps strictly inside are
   excluded). `MACRO_INTERIOR_MAX_FRACTION = 0.20` of all NEAR lines -> INSUFFICIENT_DATA (same shape as
   RETROACTIVE_MAX_FRACTION).

3. SKILL-MECHANISM GUARD (§5.4). Quoted verbatim from the doc (this is the exact pinned wording the
   guard implements):

     "Qualifying skill call (carried from rung 1): a run_skill call with logged
     executed_step_count >= 3 (eval/score_skill_rung1.py's QUALIFYING_MIN_EXECUTED_STEPS, reused
     verbatim, not re-derived).
     NEW: qualifying-conditional call. A qualifying call whose logged stop_reason shows the
     repeat_until's stop_when fired BEFORE max_iters was reached -- i.e. stop_reason matches one of
     move_blocked, move_succeeded, region_changed(...) fired (plus entity_count_changed if admitted per
     §3/§6 gate 3) -- world_mcp.py's _check_stop_when/repeat_until_summary shape
     (world_mcp.py:1653-1675, ported to Kirby's enum) -- NOT "reached max_iters=N without stop_when
     firing" and NOT steps_elapsed(n) alone (a pure step-count loop is conditional in NAME only -- it
     never actually branches on world state, so it does not count as conditional-half evidence; this
     mirrors why steps_elapsed is listed in §3 as a legitimate predicate for the RETREAT half but does
     not itself satisfy this guard). AND (review finding -- the single-iteration laundering hole): the
     firing repeat_until's logged iteration count must be >= 2 (the "iterations" field in the executed
     record, world_mcp.py:1675's "iterations": iters_done, carried unchanged into the Kirby log schema).
     A max_iters=1 skill whose move_blocked fires deterministically against a wall the brain already
     knows about is a pre-known one-shot dressed as a loop -- the same spirit-violation as bare
     steps_elapsed, laundered through a predicate name. iterations >= 2 means the loop genuinely
     re-checked its predicate at least once on world state the brain had not yet seen -- cheap,
     mechanical, checkable against the already-logged field.
     PINNED GATE: >= 1 qualifying-conditional call, or the run is INSUFFICIENT_DATA (skill-mechanism half
     untested) -- reported separately from, and prior to, the GROUNDED/FAIL computation. This gate must
     be checked FIRST: if it fails, the GROUNDED/rejection numbers are still computed and reported (for
     completeness/audit) but the overall verdict is INSUFFICIENT_DATA, not PASS/FAIL, exactly as v2's own
     MIN_SESSION_DROPS guard pre-empts a PASS/FAIL computation."

   AMBIGUITY FLAGGED (implemented STRICTER per this build's instructions -- see report): the doc names
   `stop_reason` (a string on the top-level run_skill log record, per world_mcp.py:1193-1195 --
   `executed[-1]["repeat_until_summary"]` copied up) as carrying the fired-predicate evidence, and
   separately names "the 'iterations' field in the executed record" -- but per world_mcp.py:1147
   (`executed.append({"repeat_until_summary": ..., "iterations": iters_done, ...})`), `iterations` lives
   on the INNER repeat_until sub-record inside `executed`, not on the top-level run_skill record (which
   has no `iterations` key at all -- only `stop_reason`/`executed_step_count`/`world_steps_used`/
   `executed`). A run_skill call's `executed` list can in principle contain MORE THAN ONE repeat_until
   block (doc's own macro example defines two single-block skills, but the schema does not forbid a
   skill with multiple repeat_until steps). The doc does not explicitly pin how to combine iteration
   counts across multiple repeat_until blocks in one call. STRICTER READING CHOSEN: a call qualifies as
   qualifying-conditional only if the LAST repeat_until sub-record in `executed` (the one whose
   `repeat_until_summary` was copied up to the top-level `stop_reason`, so the two are certain to be
   about the SAME loop) both (a) fired a real predicate (not max_iters exhaustion, not steps_elapsed
   alone) AND (b) has `iterations >= 2` on THAT SAME sub-record. This is stricter than e.g. treating ANY
   repeat_until sub-record's iterations as satisfying the guard (which could let an early, unrelated
   loop's iteration count paper over a laundered one-shot final loop) -- it ties the iteration check to
   the exact loop whose firing is being credited.

Usage:
    uv run python -m eval.score_entity_gate_v3 runs/<dir>
        (reads <dir>/transcript.jsonl, <dir>/world/oracle.jsonl, <dir>/world/skills.jsonl)
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

HP_ADDR = 0xD086   # kirby_dreamland's hp watch (plain int 0-5; world_mcp.py:170-178). _bcd() below is
                    # the SAME decode v2 uses -- identity for any raw byte in 0-9 -- carried unchanged.

_ENT_RE = re.compile(
    r"ENT\s+id=(-?\d+)\s+region=\((-?\d+),\s*(-?\d+),\s*(-?\d+),\s*(-?\d+)\)\s+step=(-?\d+)\s+"
    r"claim=(threat|benign)"
)
_NEAR_RE = re.compile(r"NEAR\s+id=(-?\d+)\s+step=(-?\d+)")
_DECLARE_THREAT_RE = re.compile(r"DECLARE\s+threat=(-?\d+)")
_DECLARE_BENIGN_RE = re.compile(r"DECLARE\s+benign=(-?\d+)")
_REJECT_RE = re.compile(r"REJECT\s+id=(-?\d+)\s+reason=(.*)")

# --- machinery carried over unchanged from v2 (doc §5.1) --------------------------------------------
WINDOW = 15
MIN_NEAR = 3
MIN_SESSION_DROPS = 5
MIN_TOTAL_STEPS = 30
UNMATCHED_MAX_FRACTION = 0.05
MALFORMED_MAX_FRACTION = 0.20
RETROACTIVE_MAX_FRACTION = 0.20

# --- v3: the repaired bar (doc §5.2) -----------------------------------------------------------------
Q_K_FLOOR = 0.80          # absolute floor on q_k, NEW in v3
MARGIN = 0.15             # q_k - b_k must clear this, halved from v2's 0.30 (see doc §5.2 rationale)
B_K_CEILING = 0.70        # b_k > this -> INSUFFICIENT_DATA for that entity, checked BEFORE floor/margin

# --- v3: macro-interior exclusion (doc §5.6) ---------------------------------------------------------
MACRO_INTERIOR_MAX_FRACTION = 0.20

# --- v3: skill-mechanism guard (doc §5.4) --------------------------------------------------------------
QUALIFYING_MIN_EXECUTED_STEPS = 3   # eval/score_skill_rung1.py's QUALIFYING_MIN_EXECUTED_STEPS, reused verbatim
QUALIFYING_MIN_ITERATIONS = 2       # the single-iteration laundering-hole fix (doc §5.4 review finding)

# stop_reason substrings that indicate a REAL predicate fired (not max_iters exhaustion, not bare
# steps_elapsed). Doc §5.4: "move_blocked, move_succeeded, region_changed(...) fired (plus
# entity_count_changed if admitted per §3/§6 gate 3)". entity_count_changed is included here as a
# forward-compatible name (it produces a stop_reason of the same "stop_when '...' fired after N
# press(es)" shape if the predicate is ever admitted) -- it is NOT excluded by name, only steps_elapsed
# is excluded by name per the doc's explicit carve-out.
_QUALIFYING_PREDICATE_NAMES = ("move_blocked", "move_succeeded", "region_changed", "entity_count_changed")


def _bcd(b: int) -> int:
    return (b >> 4) * 10 + (b & 0x0F)


def load_jsonl(path: str) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


# --- v2 machinery, carried over verbatim (not imported -- v2's own file is untouched) ----------------
_REVEALING_TOOL_SUFFIXES = ("__observe", "__read_region", "__whats_changed")
_STEP_IN_RESULT_RE = re.compile(r"step[\"'=:\\\s]+(\d+)")


def _max_step_in_result(block: dict) -> int | None:
    steps = [int(s) for s in _STEP_IN_RESULT_RE.findall(json.dumps(block))]
    return max(steps) if steps else None


def parse_remember_calls(transcript: list[dict]) -> list[tuple[str, int]]:
    """Copied from v2's parse_remember_calls verbatim (doc §5.1: watermark rule carried over
    unchanged)."""
    pending: dict[str, str] = {}
    pending_reveal: dict[str, bool] = {}
    revealed = -1
    out: list[tuple[str, int]] = []
    for msg in transcript:
        content = (msg.get("message") or {}).get("content")
        if not isinstance(content, list):
            continue
        for block in content:
            if not isinstance(block, dict):
                continue
            if block.get("type") == "tool_use":
                name = str(block.get("name", ""))
                if name.endswith("__remember"):
                    pending[block["id"]] = (block.get("input") or {}).get("lesson", "")
                elif name.endswith(_REVEALING_TOOL_SUFFIXES):
                    pending_reveal[block["id"]] = True
            elif block.get("type") == "tool_result":
                tool_use_id = block.get("tool_use_id")
                if tool_use_id in pending:
                    out.append((pending.pop(tool_use_id), revealed))
                elif pending_reveal.pop(tool_use_id, False):
                    step = _max_step_in_result(block)
                    if step is not None:
                        revealed = max(revealed, step)
    return out


def _oracle_hp_by_step(oracle: list[dict]) -> dict[int, int | None]:
    """step -> BCD-decoded hp. Range kept at v2's [0,10] (doc §5.1: "the v2 scorer's _bcd() needs no
    change" -- Kirby's true range is 0-5, a subset, so the wider bound is a harmless inherited
    constant, not a Kirby-specific repin)."""
    by_step: dict[int, int | None] = {}
    for rec in oracle:
        step = rec.get("step")
        if step is None:
            continue
        raw = (rec.get("watch") or {}).get("hp")
        if raw is None:
            by_step[int(step)] = None
            continue
        v = _bcd(int(raw))
        by_step[int(step)] = v if 0 <= v <= 10 else None
    return by_step


def _drop_steps(hp_by_step: dict[int, int | None]) -> tuple[set[int], int]:
    steps = sorted(hp_by_step)
    drops: set[int] = set()
    scoreable_with_prior = 0
    prev_hp = None
    for s in steps:
        hp = hp_by_step[s]
        if hp is None:
            prev_hp = None
            continue
        if prev_hp is not None:
            scoreable_with_prior += 1
            if hp < prev_hp:
                drops.add(s)
        prev_hp = hp
    return drops, scoreable_with_prior


# ---------------------------------------------------------------------------
# v3 NEW: macro-interior exclusion (doc §5.6)
# ---------------------------------------------------------------------------

def macro_spans(skills: list[dict]) -> list[tuple[int, int]]:
    """(start, end) pairs for every run_skill record, start = r.step - r.world_steps_used (exclusive),
    end = r.step (exclusive) -- doc §5.6: a claim naming step n is MACRO-INTERIOR iff
    start < n < end for some span. Boundary steps (n == start or n == end) are NOT interior."""
    spans = []
    for r in skills:
        if r.get("event") != "run_skill":
            continue
        end = r.get("step")
        used = r.get("world_steps_used")
        if end is None or used is None:
            continue
        spans.append((int(end) - int(used), int(end)))
    return spans


def _is_macro_interior(step: int, spans: list[tuple[int, int]]) -> bool:
    return any(start < step < end for start, end in spans)


# ---------------------------------------------------------------------------
# v3 NEW: skill-mechanism guard (doc §5.4)
# ---------------------------------------------------------------------------

def _repeat_until_records(executed: list) -> list[dict]:
    return [e for e in (executed or []) if isinstance(e, dict) and "repeat_until_summary" in e]


def _fired_real_predicate(stop_reason: str) -> bool:
    """True iff stop_reason shows a real stop_when predicate fired (not max_iters exhaustion, not
    steps_elapsed alone). Doc §5.4: 'NOT "reached max_iters=N without stop_when firing" and NOT
    steps_elapsed(n) alone'."""
    if "reached max_iters=" in stop_reason:
        return False
    if "steps_elapsed" in stop_reason:
        return False
    return any(name in stop_reason for name in _QUALIFYING_PREDICATE_NAMES)


def is_qualifying_conditional_call(rec: dict) -> bool:
    """A run_skill record is a qualifying-conditional call iff (doc §5.4, quoted in the module
    docstring):
      1. executed_step_count >= QUALIFYING_MIN_EXECUTED_STEPS (3) -- the "qualifying call" half.
      2. the LAST repeat_until sub-record in `executed` (the one whose repeat_until_summary was copied
         up to the top-level stop_reason -- see the module docstring's ambiguity note for why THIS
         sub-record, not any sub-record, is the stricter reading) fired a real predicate, not
         max_iters exhaustion and not bare steps_elapsed.
      3. that SAME sub-record's iterations >= QUALIFYING_MIN_ITERATIONS (2) -- the single-iteration
         laundering-hole fix.
    A call with no repeat_until block at all (a flat press-only skill) cannot qualify as conditional --
    there is no loop to have genuinely branched on world state."""
    if rec.get("event") != "run_skill":
        return False
    if (rec.get("executed_step_count") or 0) < QUALIFYING_MIN_EXECUTED_STEPS:
        return False
    ru_records = _repeat_until_records(rec.get("executed"))
    if not ru_records:
        return False
    last = ru_records[-1]
    if not _fired_real_predicate(str(last.get("repeat_until_summary", ""))):
        return False
    if (last.get("iterations") or 0) < QUALIFYING_MIN_ITERATIONS:
        return False
    return True


def skill_guard(skills: list[dict]) -> dict:
    run_rows = [r for r in skills if r.get("event") == "run_skill"]
    qualifying = [r for r in run_rows if (r.get("executed_step_count") or 0) >= QUALIFYING_MIN_EXECUTED_STEPS]
    qualifying_conditional = [r for r in run_rows if is_qualifying_conditional_call(r)]
    return {
        "n_run_skill_calls": len(run_rows),
        "n_qualifying_calls": len(qualifying),
        "n_qualifying_conditional_calls": len(qualifying_conditional),
        "guard_pass": len(qualifying_conditional) >= 1,
    }


# ---------------------------------------------------------------------------
# Parsing (ENT/NEAR/DECLARE/REJECT) -- v2's parser + v3's macro-interior exclusion layered on NEAR.
# ---------------------------------------------------------------------------

def parse_transcript(transcript: list[dict], oracle: list[dict], skills: list[dict] | None = None) -> dict:
    """Extract ENT/NEAR/DECLARE/REJECT lines, same as v2, with one new exclusion class layered on:
    a NEAR whose step is MACRO-INTERIOR (doc §5.6) is counted + reported + excluded, checked AFTER the
    v2 retroactive/dedupe/unmatched checks (order does not matter for which guard fires -- a step can be
    both retroactive per the old watermark rule and macro-interior; both are simply exclusion reasons a
    NEAR can carry, and macro-interior is recorded distinctly so its own fraction can be capped
    independently per §5.6)."""
    spans = macro_spans(skills or [])
    lessons = parse_remember_calls(transcript)
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
    seen_nears: set[tuple[int, int]] = set()

    n_lines = 0
    for lesson, revealed_at_log in lessons:
        m = _ENT_RE.search(lesson)
        if m:
            n_lines += 1
            eid, x0, y0, x1, y1, step, claim = m.groups()
            ent_claims.setdefault(int(eid), []).append(
                {"region": (int(x0), int(y0), int(x1), int(y1)), "step": int(step), "claim": claim})
            continue
        m = _NEAR_RE.search(lesson)
        if m:
            n_lines += 1
            eid, step = int(m.group(1)), int(m.group(2))
            if revealed_at_log > step:
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
            continue
        m = _DECLARE_THREAT_RE.search(lesson)
        if m:
            n_lines += 1
            declared_threats.add(int(m.group(1)))
            continue
        m = _DECLARE_BENIGN_RE.search(lesson)
        if m:
            n_lines += 1
            declared_benign.add(int(m.group(1)))
            continue
        m = _REJECT_RE.search(lesson)
        if m:
            n_lines += 1
            eid, reason = int(m.group(1)), m.group(2)
            rejected[eid] = reason.strip()
            continue
        if re.search(r"\b(ENT|NEAR|DECLARE|REJECT)\b", lesson):
            n_lines += 1
            malformed += 1

    return {"ent_claims": ent_claims, "nears": nears,
            "declared_threats": declared_threats, "declared_benign": declared_benign,
            "rejected": rejected, "malformed": malformed, "duplicates": duplicates,
            "retroactive": retroactive, "macro_interior": macro_interior, "n_lines": n_lines}


def _coverage(entries: list[dict], steps: set[int]) -> int:
    near_steps = sorted(e["step"] for e in entries if e["matched"])
    if not near_steps:
        return 0
    covered = 0
    for s in steps:
        lo = s - WINDOW
        if any(lo <= n <= s for n in near_steps):
            covered += 1
    return covered


def _assert_bar_is_satisfiable_for_all_scoreable_b_k() -> None:
    """Doc §5.2, final bullet: 'This property (bar strictly <= 1.0 for all admissible b_k) is the
    pinned correctness criterion for the repaired metric and must be checked into the scorer as an
    assertion, not just argued in prose.' Checked at import time over the full scoreable range
    [0, B_K_CEILING] at a fine step, plus the exact boundary b_k == B_K_CEILING."""
    b_k = 0.0
    step = 1e-4
    while b_k <= B_K_CEILING + 1e-9:
        required = max(Q_K_FLOOR, b_k + MARGIN)
        assert required <= 1.0 + 1e-9, f"bar unreachable at b_k={b_k}: requires q_k >= {required}"
        b_k += step


_assert_bar_is_satisfiable_for_all_scoreable_b_k()


def _grounded(eid: int, nears: dict[int, list[dict]], drops: set[int], non_drop_steps: set[int]) -> dict:
    """Doc §5.2's repaired bar. `b_k > B_K_CEILING` -> INSUFFICIENT_DATA for this entity, checked BEFORE
    the floor/margin/MIN_NEAR conditions (order affects only the per-entity report, per the doc: "all
    four must hold for GROUNDED regardless of evaluation order")."""
    entries = nears.get(eid, [])
    n_matched = sum(1 for e in entries if e["matched"])
    covered_drops = _coverage(entries, drops)
    covered_non_drops = _coverage(entries, non_drop_steps)
    q_k = covered_drops / len(drops) if drops else 0.0
    b_k = covered_non_drops / len(non_drop_steps) if non_drop_steps else 0.0

    ceiling_exceeded = b_k > B_K_CEILING
    insufficient_near = n_matched < MIN_NEAR
    # scoreable = has enough NEAR evidence AND is under the camping ceiling
    insufficient = insufficient_near or ceiling_exceeded
    floor_met = q_k >= Q_K_FLOOR
    margin_met = (q_k - b_k) >= MARGIN
    grounded = (not insufficient) and floor_met and margin_met

    return {"id": eid, "q_k": q_k, "b_k": b_k, "n_near": n_matched,
            "ceiling_exceeded": ceiling_exceeded, "insufficient_near": insufficient_near,
            "insufficient": insufficient, "floor_met": floor_met, "margin_met": margin_met,
            "grounded": grounded}


def score(transcript_path: str, oracle_path: str, skills_path: str) -> dict:
    transcript = load_jsonl(transcript_path)
    oracle = load_jsonl(oracle_path)
    skills = load_jsonl(skills_path) if os.path.exists(skills_path) else []

    parsed = parse_transcript(transcript, oracle, skills)
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

    # v3 NEW: macro-interior taint (doc §5.6). Denominator = all NEAR lines that reached this check
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
        result["reason"] = "no DECLARE threat=<id> line found" + conflict_note
        return result
    if not benign_ids:
        result["verdict"] = "NO_DECLARE"
        result["reason"] = ("no DECLARE benign=<id> or REJECT id=<id> line found -- arm (b) unexercised"
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

    # v3 NEW: skill-mechanism guard (doc §5.4), checked FIRST relative to the grounding verdict per the
    # doc's own wording ("This gate must be checked FIRST... the GROUNDED/rejection numbers are still
    # computed and reported (for completeness/audit) but the overall verdict is INSUFFICIENT_DATA").
    # The grounding numbers above are already computed, so "checked first" is expressed here as
    # overriding the final verdict, not skipping the computation.
    if not guard["guard_pass"]:
        result["verdict"] = "INSUFFICIENT_DATA"
        result["reason"] = (f"skill-mechanism guard failed: {guard['n_qualifying_conditional_calls']} "
                            "qualifying-conditional run_skill call(s) (need >= 1) -- conditional-half "
                            "evidence untested; grounding numbers above are reported for audit only")
        return result

    result["verdict"] = grounding_verdict
    return result


def format_report(r: dict) -> str:
    lines = ["=== Entity-grounding gate v3 score (repaired bar + macro-interior exclusion + skill guard) ==="]
    if r.get("malformed_lines"):
        lines.append(f"malformed protocol lines: {r['malformed_lines']}")
    if r.get("duplicate_lines"):
        lines.append(f"duplicate NEAR lines (repeat (id, step), first kept): {r['duplicate_lines']}")
    if r.get("retroactive_lines"):
        lines.append(f"RETROACTIVE NEAR lines (logged after a later step's outcome was observable, "
                     f"excluded): {r['retroactive_lines']}")
    if r.get("macro_interior_lines"):
        lines.append(f"MACRO-INTERIOR NEAR lines (name a step hidden inside a run_skill span, "
                     f"excluded): {r['macro_interior_lines']}")
    if r.get("conflicting_declarations"):
        lines.append(f"CONFLICTING declarations (id declared both threat AND benign/REJECTed, excluded "
                     f"from both arms): {r['conflicting_declarations']}")

    guard = r.get("skill_guard")
    if guard is not None:
        lines.append(f"\nskill-mechanism guard: {guard['n_run_skill_calls']} run_skill call(s), "
                     f"{guard['n_qualifying_calls']} qualifying (executed_step_count >= "
                     f"{QUALIFYING_MIN_EXECUTED_STEPS}), {guard['n_qualifying_conditional_calls']} "
                     f"qualifying-conditional (predicate fired before max_iters AND iterations >= "
                     f"{QUALIFYING_MIN_ITERATIONS}) -- guard {'PASS' if guard['guard_pass'] else 'FAIL'}")

    if r["verdict"] == "NO_DECLARE":
        lines.append(f"\ndeclared threats: {r.get('declared_threats')}  declared benign: "
                     f"{r.get('declared_benign')}  rejected: {list(r.get('rejected', {}))}")
        lines.append(f"\nVERDICT: NO_DECLARE ({r.get('reason')})")
        return "\n".join(lines)
    if r["verdict"] in ("INSUFFICIENT_DATA", "INSUFFICIENT_DROPS") and "total_scoreable_steps" not in r:
        lines.append(f"\nVERDICT: {r['verdict']} ({r.get('reason')})")
        return "\n".join(lines)

    lines.append(f"\nsession: {r['total_scoreable_steps']} scoreable steps, {r['session_drop_steps']} "
                f"drop step(s)")
    if r["verdict"] in ("INSUFFICIENT_DATA", "INSUFFICIENT_DROPS") and "threat_scores" not in r:
        lines.append(f"\nVERDICT: {r['verdict']} ({r.get('reason')})")
        return "\n".join(lines)

    def _tag(s: dict, *, is_threat: bool) -> str:
        if s["ceiling_exceeded"]:
            return "INSUFFICIENT_DATA (b_k ceiling exceeded -- camped)"
        if s["insufficient_near"]:
            return "INSUFFICIENT (too few NEAR events)"
        if is_threat:
            return "GROUNDED" if s["grounded"] else "not-grounded"
        return "WRONGLY-GROUNDED" if s["grounded"] else "correctly-rejected"

    lines.append("threat claims:")
    for eid, s in r["threat_scores"].items():
        lines.append(f"  id={eid}: q_k={s['q_k']:.3f} b_k={s['b_k']:.3f} n_near={s['n_near']}  "
                    f"[{_tag(s, is_threat=True)}]")
    lines.append("benign/rejected claims:")
    for eid, s in r["benign_scores"].items():
        reason = r["rejected"].get(eid)
        suffix = f"  reason={reason!r}" if reason else ""
        lines.append(f"  id={eid}: q_k={s['q_k']:.3f} b_k={s['b_k']:.3f} n_near={s['n_near']}  "
                    f"[{_tag(s, is_threat=False)}]{suffix}")

    if "arm_a" in r:
        lines.append(f"\nARM (a) grounds a threat (q_k >= {Q_K_FLOOR} AND q_k - b_k >= {MARGIN} AND "
                    f"b_k <= {B_K_CEILING}): {'PASS' if r['arm_a'] else 'FAIL'}")
        lines.append(f"ARM (b) rejects a decoy (stays below that bar, while scoreable): "
                    f"{'PASS' if r['arm_b'] else 'FAIL'}")

    lines.append(f"\nGATE: {r['verdict']}" + (f" ({r['reason']})" if r.get("reason") else ""))
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("run_dir", help="run directory containing transcript.jsonl and world/{oracle,skills}.jsonl")
    args = ap.parse_args(argv)
    transcript_path = os.path.join(args.run_dir, "transcript.jsonl")
    oracle_path = os.path.join(args.run_dir, "world", "oracle.jsonl")
    skills_path = os.path.join(args.run_dir, "world", "skills.jsonl")
    result = score(transcript_path, oracle_path, skills_path)
    print(format_report(result))
    return 0 if result.get("verdict") in ("PASS", "FAIL", "INSUFFICIENT_DROPS") else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
