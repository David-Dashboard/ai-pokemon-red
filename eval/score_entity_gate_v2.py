"""Entity-grounding gate scorer v2 — CONSEQUENCE-ANCHORED BACKWARD ATTRIBUTION, replacing v1's forward
contact-prediction (`eval/score_entity_gate.py`, FAILED live: `HANDOFF.md` diagnosed the two hp drops in
that run as 4-14 steps from any logged `CONTACT` -- Cave Noire enemies act on their own initiative, so
"predict a drop from a touch" is the wrong causal model). v1's FAIL stays on the books; this is a
pre-registered, out-of-sample metric, not a re-score of v1's run. Full rationale + every pinned constant:
`reports/2026-07-03-entity-gate-v2-plan.md`.

PROTOCOL (machine-parseable `remember` lines):

    ENT id=<k> region=(x0,y0,x1,y1) step=<n> claim=threat|benign   (unchanged from v1, purely descriptive)
    NEAR id=<k> step=<n>       (replaces CONTACT: entity k observed near/adjacent to the avatar at step n)
    DECLARE threat=<k> / DECLARE benign=<k> / REJECT id=<k> reason=<...>   (unchanged; REJECT == benign)

`ENT` is purely descriptive (never read for its claim); final claims come ONLY from `DECLARE`/`REJECT`.

THE PINNED METRIC (backward attribution over a window before each hp-drop event):

  * Oracle / drop-step machinery is IDENTICAL to v1: hp is BCD @ 0xC120, in-range [0,10]; a "drop step" is
    an oracle row whose hp is strictly lower than the immediately preceding oracle-recorded row's hp (both
    in-range); a "scoreable step" is an oracle row with a defined immediate predecessor.
  * WATERMARK RULE identical to v1's retroactive-CONTACT guard, applied to NEAR: a `NEAR id=k step=n`
    counts ONLY if, at the moment it was logged, no observe/read_region/whats_changed tool_result had yet
    reported a world step STRICTLY GREATER than n. Retroactive NEARs are counted, reported, and excluded;
    `RETROACTIVE_MAX_FRACTION` at/above 20% of NEAR lines taints the log -> INSUFFICIENT_DATA. v1's
    parse_remember_calls/_max_step_in_result machinery is copied here (not imported -- v1's own file is
    untouched, its FAIL stands as-is).
  * Dedupe: (id, step) NEAR pairs first-wins; duplicates counted + reported. Unmatched NEAR (step has no
    oracle row) excluded + reported; `UNMATCHED_MAX_FRACTION = 0.05`. Malformed protocol lines counted;
    `MALFORMED_MAX_FRACTION = 0.20`.
  * ATTRIBUTION: `WINDOW = 15` world steps. A drop step `s` is COVERED by entity `k` iff there exists an
    accepted (deduped, matched, non-retroactive) NEAR for `k` at step `n` with `s - WINDOW <= n <= s`.
  * `q_k` = (# drop steps covered by k) / (# drop steps).
  * `b_k` = (# NON-DROP scoreable steps covered by k) / (# non-drop scoreable steps) -- the base presence
    rate; the denominator EXCLUDES drop steps (cleaner than v1's p_base: this prices "coverage of
    consequences" against "coverage of ordinary time" for the SAME entity).
  * `MARGIN = 0.30`. `MIN_NEAR = 3` accepted NEAR events per entity, else that entity is INSUFFICIENT (not
    scored either way).
  * GROUNDED (threat) iff `q_k >= b_k + MARGIN` AND `|N_k| >= MIN_NEAR`.
  * A benign/rejected entity `j` is correctly rejected iff it is scoreable (`|N_j| >= MIN_NEAR`) AND NOT
    (`q_j >= b_j + MARGIN`).
  * PASS = >=1 declared threat GROUNDED AND >=1 declared-benign/REJECTed entity correctly rejected. Both
    arms required. NO_DECLARE if either declaration side missing.
  * CONFLICTING declarations (an id appearing in BOTH declared_threats AND benign/REJECT) are excluded
    from both arms, counted, and reported; if the exclusion leaves either arm with no declared id, the
    verdict is NO_DECLARE (a self-contradictory declaration cannot supply either arm). Tightening added
    at review (PR #61 finding 4) -- stricter-only, pre-run.

SESSION GUARDS:
  * `MIN_TOTAL_STEPS = 30` scoreable steps overall, else INSUFFICIENT_DATA.
  * `MIN_SESSION_DROPS = 5` drop steps, else verdict INSUFFICIENT_DROPS (v1's 2-drop session starved arm
    (a) -- this is the fix; no PASS/FAIL is computed below 5 drops).

ANTI-GAMING (see the plan report for the full analysis):
  * Spamming NEAR for the chosen threat at every step self-defeats: b_k -> 1.0 too (its non-drop coverage
    saturates), so q_k - b_k collapses and the margin can't clear.
  * Selectively omitting NEAR for the benign entity near drop steps, to fake correct-rejection, requires the
    brain to actually predict (at logging time, pre-outcome, per the watermark) which steps are heading
    toward a drop -- that capability IS grounding, not a loophole.

Usage:
    uv run python -m eval.score_entity_gate_v2 runs/<dir>/transcript.jsonl runs/<dir>/world/oracle.jsonl
"""
from __future__ import annotations

import argparse
import json
import re
import sys

HP_ADDR = 0xC120   # same Cave Noire life oracle as v1 (BCD; see world_mcp.py GAMES["cave_noire"])

_ENT_RE = re.compile(
    r"ENT\s+id=(-?\d+)\s+region=\((-?\d+),\s*(-?\d+),\s*(-?\d+),\s*(-?\d+)\)\s+step=(-?\d+)\s+"
    r"claim=(threat|benign)"
)
_NEAR_RE = re.compile(r"NEAR\s+id=(-?\d+)\s+step=(-?\d+)")
_DECLARE_THREAT_RE = re.compile(r"DECLARE\s+threat=(-?\d+)")
_DECLARE_BENIGN_RE = re.compile(r"DECLARE\s+benign=(-?\d+)")
_REJECT_RE = re.compile(r"REJECT\s+id=(-?\d+)\s+reason=(.*)")

# Pinned thresholds (see module docstring + reports/2026-07-03-entity-gate-v2-plan.md). Stricter-only from here.
WINDOW = 15                       # backward-attribution window, in world steps, before a drop step
MARGIN = 0.30                     # q_k must clear b_k by at least this many probability points
MIN_NEAR = 3                      # fewer accepted NEAR events for an entity -> INSUFFICIENT for it
MIN_SESSION_DROPS = 5             # fewer drop steps overall -> INSUFFICIENT_DROPS, no PASS/FAIL computed
MIN_TOTAL_STEPS = 30              # fewer scoreable oracle steps overall -> INSUFFICIENT_DATA
UNMATCHED_MAX_FRACTION = 0.05     # unmatched NEAR steps must stay STRICTLY below this fraction
MALFORMED_MAX_FRACTION = 0.20     # malformed lines at/above this fraction of all lines -> INSUFFICIENT_DATA
RETROACTIVE_MAX_FRACTION = 0.20   # retroactive NEARs at/above this fraction of NEAR lines -> tainted


def _bcd(b: int) -> int:
    return (b >> 4) * 10 + (b & 0x0F)


def load_jsonl(path: str) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


# World-observation tools whose results reveal a step's on-screen outcome to the brain. A tool_result
# from any of these carrying a step number ADVANCES the "revealed step" watermark used by the
# retroactive-NEAR guard below. Copied from v1 (score_entity_gate.py) -- not imported, v1's file is
# untouched per the guardrail.
_REVEALING_TOOL_SUFFIXES = ("__observe", "__read_region", "__whats_changed")
# NB: the block is matched as json.dumps(block), where nested quotes arrive escaped (\") -- hence the
# backslash in the delimiter class.
_STEP_IN_RESULT_RE = re.compile(r"step[\"'=:\\\s]+(\d+)")


def _max_step_in_result(block: dict) -> int | None:
    """Extract the highest world step mentioned in a tool_result block (read_region/whats_changed report
    `step=<N>` in their text; observe's payload carries `"step": N`). None if no step is present."""
    steps = [int(s) for s in _STEP_IN_RESULT_RE.findall(json.dumps(block))]
    return max(steps) if steps else None


def parse_remember_calls(transcript: list[dict]) -> list[tuple[str, int]]:
    """Walk the transcript for `remember` tool calls; return (lesson text, revealed_step_at_log) pairs
    in transcript order, counting only calls whose `tool_result` actually arrived (the call completed).
    `revealed_step_at_log` is the highest world step any observe/read_region/whats_changed tool_result
    had reported BEFORE this remember call completed (-1 if none yet) -- the retroactive-NEAR guard's
    input. Copied from v1's parse_remember_calls (score_entity_gate.py), same logic verbatim."""
    pending: dict[str, str] = {}            # remember tool_use_id -> lesson text
    pending_reveal: dict[str, bool] = {}    # observe/read_region/whats_changed tool_use_id -> True
    revealed = -1                           # highest world step revealed so far
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
    """step -> BCD-decoded hp (None = row exists but hp missing / out-of-range transition garbage).
    Identical discipline to score_entity_gate.py::_oracle_hp_by_step."""
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
    """Return (set of drop steps, count of steps with a defined prior). A "drop step" is an
    oracle-recorded step whose hp is strictly lower than the immediately PRECEDING oracle-recorded
    step's hp (both in-range) -- consecutive in oracle-row order, not necessarily consecutive raw frames
    (the oracle logs once per observe()). Identical to v1's _drop_steps."""
    steps = sorted(hp_by_step)
    drops: set[int] = set()
    scoreable_with_prior = 0
    prev_hp = None
    for s in steps:
        hp = hp_by_step[s]
        if hp is None:
            prev_hp = None   # a gap in the oracle breaks the "immediately preceding" chain
            continue
        if prev_hp is not None:
            scoreable_with_prior += 1
            if hp < prev_hp:
                drops.add(s)
        prev_hp = hp
    return drops, scoreable_with_prior


def parse_transcript(transcript: list[dict], oracle: list[dict]) -> dict:
    """Extract ENT/NEAR/DECLARE/REJECT lines. NEAR lines are deduped by (id, step); malformed lines
    (unparseable) are counted, never silently dropped.

    RETROACTIVE-NEAR GUARD (identical rule to v1's retroactive-CONTACT guard, applied to NEAR): a
    `NEAR id=k step=n` counts ONLY if, at the moment it was logged, no observe/read_region/whats_changed
    tool_result had yet reported a world step STRICTLY GREATER than n. The result that reports step n
    itself is allowed (it is what gives the brain the step number to log at all); a NEAR logged after a
    later step's outcome was already observable is post-hoc outcome-matching -- counted + reported as
    RETROACTIVE and excluded from the metric."""
    lessons = parse_remember_calls(transcript)
    hp_by_step = _oracle_hp_by_step(oracle)

    ent_claims: dict[int, list[dict]] = {}          # id -> [{"region","step","claim"}] (descriptive only)
    nears: dict[int, list[dict]] = {}               # id -> [{"step","matched"}]
    declared_threats: set[int] = set()
    declared_benign: set[int] = set()
    rejected: dict[int, str] = {}
    malformed = 0
    duplicates = 0
    retroactive = 0
    seen_nears: set[tuple[int, int]] = set()     # (id, step) pairs already counted

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
                retroactive += 1     # logged after a later step's outcome was already observable
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
        # A `remember` lesson that mentions our keywords but didn't match any pattern is a malformed
        # protocol line (e.g. a truncated/garbled ENT/NEAR/DECLARE/REJECT) -- counted, not ignored.
        if re.search(r"\b(ENT|NEAR|DECLARE|REJECT)\b", lesson):
            n_lines += 1
            malformed += 1

    return {"ent_claims": ent_claims, "nears": nears,
            "declared_threats": declared_threats, "declared_benign": declared_benign,
            "rejected": rejected, "malformed": malformed, "duplicates": duplicates,
            "retroactive": retroactive, "n_lines": n_lines}


def _coverage(entries: list[dict], steps: set[int]) -> int:
    """Count how many of `steps` are COVERED by this entity's accepted, matched NEAR entries -- a step
    `s` is covered iff some NEAR step `n` satisfies `s - WINDOW <= n <= s`."""
    near_steps = sorted(e["step"] for e in entries if e["matched"])
    if not near_steps:
        return 0
    covered = 0
    for s in steps:
        lo = s - WINDOW
        if any(lo <= n <= s for n in near_steps):
            covered += 1
    return covered


def score(transcript_path: str, oracle_path: str) -> dict:
    transcript = load_jsonl(transcript_path)
    oracle = load_jsonl(oracle_path)
    parsed = parse_transcript(transcript, oracle)
    nears = parsed["nears"]
    declared_threats, declared_benign, rejected = (
        parsed["declared_threats"], parsed["declared_benign"], parsed["rejected"])
    n_malformed, n_duplicates, n_lines = parsed["malformed"], parsed["duplicates"], parsed["n_lines"]
    n_retroactive = parsed["retroactive"]

    result: dict = {
        "declared_threats": sorted(declared_threats), "declared_benign": sorted(declared_benign),
        "rejected": rejected, "entities_seen": sorted(parsed["ent_claims"]),
        "malformed_lines": n_malformed, "duplicate_lines": n_duplicates,
        "retroactive_lines": n_retroactive,
    }

    if n_lines and n_malformed and (n_malformed / n_lines) >= MALFORMED_MAX_FRACTION:
        result["verdict"] = "INSUFFICIENT_DATA"
        result["reason"] = (f"{n_malformed}/{n_lines} protocol lines are malformed "
                            f"(>= {MALFORMED_MAX_FRACTION:.0%} -- must stay below)")
        return result

    # RETROACTIVE-NEAR taint (identical rule to v1's retroactive-CONTACT guard): too many NEARs logged
    # after their step's outcome was already observable means the NEAR log as a whole cannot be trusted
    # as predictive -> no verdict. Denominator = accepted unique nears + retroactive.
    n_accepted_nears = sum(len(v) for v in nears.values())
    n_near_pool = n_accepted_nears + n_retroactive
    if n_near_pool and n_retroactive and (n_retroactive / n_near_pool) >= RETROACTIVE_MAX_FRACTION:
        result["verdict"] = "INSUFFICIENT_DATA"
        result["reason"] = (f"{n_retroactive}/{n_near_pool} NEAR lines are RETROACTIVE (logged "
                            f"after a later step's outcome was already observable) "
                            f"(>= {RETROACTIVE_MAX_FRACTION:.0%} -- must stay below)")
        return result

    benign_ids = declared_benign | set(rejected)
    # CONFLICTING-DECLARE guard (PR #61 finding 4, stricter-only): an id declared BOTH threat and
    # benign/REJECTed is self-contradictory -- excluded from both arms, counted, reported. It must not
    # be scored as if the declarations were consistent.
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

    # scoreable steps = oracle rows with a defined immediate predecessor (same set _drop_steps counted).
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

    def _grounded(eid: int) -> dict:
        entries = nears.get(eid, [])
        n_matched = sum(1 for e in entries if e["matched"])
        insufficient = n_matched < MIN_NEAR
        covered_drops = _coverage(entries, drops)
        covered_non_drops = _coverage(entries, non_drop_steps)
        q_k = covered_drops / len(drops) if drops else 0.0
        b_k = covered_non_drops / len(non_drop_steps) if non_drop_steps else 0.0
        grounded = (not insufficient) and (q_k >= b_k + MARGIN)
        return {"id": eid, "q_k": q_k, "b_k": b_k, "n_near": n_matched,
                "insufficient": insufficient, "grounded": grounded}

    threat_scores = {eid: _grounded(eid) for eid in declared_threats}
    benign_scores = {eid: _grounded(eid) for eid in benign_ids}
    result["threat_scores"] = threat_scores
    result["benign_scores"] = benign_scores

    threats_grounded = [s for s in threat_scores.values() if s["grounded"]]
    threats_with_evidence = [s for s in threat_scores.values() if not s["insufficient"]]
    benigns_scoreable = [s for s in benign_scores.values() if not s["insufficient"]]
    benigns_correctly_rejected = [s for s in benigns_scoreable if not s["grounded"]]

    if not threats_with_evidence or not benigns_scoreable:
        result["verdict"] = "INSUFFICIENT_DATA"
        result["reason"] = (f"need >= {MIN_NEAR} accepted NEAR events for at least one declared threat "
                            "AND one declared-benign/rejected entity to compute a verdict")
        return result

    arm_a = len(threats_grounded) > 0
    arm_b = len(benigns_correctly_rejected) > 0
    result["arm_a"] = arm_a
    result["arm_b"] = arm_b
    result["verdict"] = "PASS" if (arm_a and arm_b) else "FAIL"
    return result


def format_report(r: dict) -> str:
    lines = ["=== Entity-grounding gate v2 score (backward attribution) ==="]
    if r.get("malformed_lines"):
        lines.append(f"malformed protocol lines: {r['malformed_lines']}")
    if r.get("duplicate_lines"):
        lines.append(f"duplicate NEAR lines (repeat (id, step), first kept): {r['duplicate_lines']}")
    if r.get("retroactive_lines"):
        lines.append(f"RETROACTIVE NEAR lines (logged after a later step's outcome was observable, "
                     f"excluded): {r['retroactive_lines']}")
    if r.get("conflicting_declarations"):
        lines.append(f"CONFLICTING declarations (id declared both threat AND benign/REJECTed, excluded "
                     f"from both arms): {r['conflicting_declarations']}")
    if r["verdict"] == "NO_DECLARE":
        lines.append(f"declared threats: {r.get('declared_threats')}  declared benign: "
                     f"{r.get('declared_benign')}  rejected: {list(r.get('rejected', {}))}")
        lines.append(f"\nVERDICT: NO_DECLARE ({r.get('reason')})")
        return "\n".join(lines)
    if r["verdict"] in ("INSUFFICIENT_DATA", "INSUFFICIENT_DROPS") and "total_scoreable_steps" not in r:
        lines.append(f"\nVERDICT: {r['verdict']} ({r.get('reason')})")
        return "\n".join(lines)
    lines.append(f"session: {r['total_scoreable_steps']} scoreable steps, {r['session_drop_steps']} "
                f"drop step(s)")
    if r["verdict"] in ("INSUFFICIENT_DATA", "INSUFFICIENT_DROPS"):
        lines.append(f"\nVERDICT: {r['verdict']} ({r.get('reason')})")
        return "\n".join(lines)
    lines.append("threat claims:")
    for eid, s in r["threat_scores"].items():
        tag = "INSUFFICIENT" if s["insufficient"] else ("GROUNDED" if s["grounded"] else "not-grounded")
        lines.append(f"  id={eid}: q_k={s['q_k']:.3f} b_k={s['b_k']:.3f} n_near={s['n_near']}  [{tag}]")
    lines.append("benign/rejected claims:")
    for eid, s in r["benign_scores"].items():
        tag = "INSUFFICIENT" if s["insufficient"] else ("WRONGLY-GROUNDED" if s["grounded"] else "correctly-rejected")
        reason = r["rejected"].get(eid)
        suffix = f"  reason={reason!r}" if reason else ""
        lines.append(f"  id={eid}: q_k={s['q_k']:.3f} b_k={s['b_k']:.3f} n_near={s['n_near']}  [{tag}]{suffix}")
    lines.append(f"\nARM (a) grounds a threat (some threat's q_k >= b_k + {MARGIN}): "
                f"{'PASS' if r['arm_a'] else 'FAIL'}")
    lines.append(f"ARM (b) rejects a decoy (some benign's q_k stays below that bar): "
                f"{'PASS' if r['arm_b'] else 'FAIL'}")
    lines.append(f"\nGATE: {r['verdict']}")
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("transcript", help="path to transcript.jsonl (stream-json from `claude -p`)")
    ap.add_argument("oracle", help="path to world/oracle.jsonl (the RAM hp oracle; scoring only)")
    args = ap.parse_args(argv)
    result = score(args.transcript, args.oracle)
    print(format_report(result))
    return 0 if result.get("verdict") in ("PASS", "FAIL", "INSUFFICIENT_DROPS") else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
