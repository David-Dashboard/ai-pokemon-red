"""Entity-grounding gate scorer — generalizes the ADR-002 SS9 HUD-grounding gate
(`eval/score_gate_run.py`) from a HUD/life SCALAR to ENTITIES: a brain hypothesizes "entity K is a THREAT"
(contact with it drops my life) and grounds it by behaviour; a decoy entity-claim (a claimed-benign or
explicitly-rejected visible thing) must NOT show that correlation. Full protocol + the pinned metric's
statistical rationale: `reports/2026-07-03-entity-gate-plan.md`.

PROTOCOL (machine-parseable `remember` lines, same style as HYP/DECLARE/REJECT):

    ENT id=<k> region=(x0,y0,x1,y1) step=<n> claim=threat|benign
    CONTACT id=<k> step=<n>
    DECLARE threat=<k>
    DECLARE benign=<k>
    REJECT id=<k> reason=<...>

`ENT` is purely descriptive (an entity may get several as its box moves / its claim is revised) — the
scorer never reads a claim off `ENT`; final claims come ONLY from `DECLARE`/`REJECT` lines, so there is
never ambiguity about "which claim is final." `REJECT id=<k>` is scored identically to `DECLARE
benign=<k>` (both mean "claimed not a threat").

THE PINNED METRIC (base-rate comparison, decided BEFORE any paid run — see the report for the full
rationale, incl. why an absolute margin over a formal significance test):

  * A "drop step" is an oracle-recorded step whose hp is LOWER than the immediately preceding
    oracle-recorded step's hp (both in-range).
  * `p_base` = (# drop steps) / (# oracle steps with a defined prior) — the session's unconditional
    damage-step rate.
  * For an entity's deduped, oracle-matched `CONTACT` steps C: `p_k` = (# steps in C that are drop
    steps) / |C|.
  * GROUNDED (threat) iff `p_k >= p_base + MARGIN` AND `|C| >= MIN_CONTACTS`.
  * A benign/rejected entity correctly REJECTED iff it does NOT clear that same bar.
  * PASS = at least one declared threat is GROUNDED AND at least one declared-benign/REJECTed entity is
    correctly rejected. Both arms required (mirrors SS9's letter).

DEGENERATE/INSUFFICIENT guards (pinned before the run, carried over from the HUD gate's variation-guard
lesson — PR #56 invalidated a technically-passing but degenerate live run):
  * `MIN_TOTAL_STEPS` scoreable oracle steps overall, else INSUFFICIENT_DATA (too little session data).
  * `MIN_SESSION_DROPS` >= 1: a session with ZERO drop steps anywhere makes `p_base == 0`, which would let
    ANY entity with even one contact-on-a-drop-step trivially "ground" — DEGENERATE_NO_DAMAGE, no verdict.
  * `MIN_CONTACTS` per entity: fewer deduped contacts than this is INSUFFICIENT_DATA for that entity (not
    scored as grounded OR rejected).
  * `UNMATCHED_MAX_FRACTION`: too many CONTACT/ENT lines pointing at steps with no oracle row refuses a
    verdict outright (excluding inconvenient lines from the denominator must not be able to inflate a
    correlation).
  * Malformed ENT/CONTACT/DECLARE/REJECT lines (unparseable id/region/step) are counted, never silently
    dropped; `MALFORMED_MAX_FRACTION` too many -> INSUFFICIENT_DATA.
  * Duplicate (id, step) CONTACT encodings dedupe: first occurrence wins, repeats counted and reported,
    never double-counted toward an entity's contact set.

Usage:
    uv run python -m eval.score_entity_gate runs/brain_cn_entity/transcript.jsonl runs/brain_cn_entity/world/oracle.jsonl
"""
from __future__ import annotations

import argparse
import json
import re
import sys

HP_ADDR = 0xC120   # same Cave Noire life oracle as the HUD gate (BCD; see world_mcp.py GAMES["cave_noire"])

_ENT_RE = re.compile(
    r"ENT\s+id=(-?\d+)\s+region=\((-?\d+),\s*(-?\d+),\s*(-?\d+),\s*(-?\d+)\)\s+step=(-?\d+)\s+"
    r"claim=(threat|benign)"
)
_CONTACT_RE = re.compile(r"CONTACT\s+id=(-?\d+)\s+step=(-?\d+)")
_DECLARE_THREAT_RE = re.compile(r"DECLARE\s+threat=(-?\d+)")
_DECLARE_BENIGN_RE = re.compile(r"DECLARE\s+benign=(-?\d+)")
_REJECT_RE = re.compile(r"REJECT\s+id=(-?\d+)\s+reason=(.*)")

# Pinned thresholds (see module docstring + reports/2026-07-03-entity-gate-plan.md). Stricter-only from here.
MARGIN = 0.30                     # p_k must clear p_base by at least this many probability points
MIN_CONTACTS = 3                  # fewer deduped contacts for an entity -> INSUFFICIENT_DATA for it
MIN_SESSION_DROPS = 1             # a session with 0 drop steps anywhere -> DEGENERATE_NO_DAMAGE
MIN_TOTAL_STEPS = 10              # fewer scoreable oracle steps overall -> INSUFFICIENT_DATA
UNMATCHED_MAX_FRACTION = 0.05     # unmatched CONTACT/ENT steps must stay STRICTLY below this fraction
MALFORMED_MAX_FRACTION = 0.20     # malformed lines at/above this fraction of all lines -> INSUFFICIENT_DATA


def _bcd(b: int) -> int:
    return (b >> 4) * 10 + (b & 0x0F)


def load_jsonl(path: str) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def parse_remember_calls(transcript: list[dict]) -> list[str]:
    """Walk the transcript for `remember` tool calls; return each call's `lesson` text, in transcript
    order, counting only calls whose `tool_result` actually arrived (the call completed). Identical
    logic to score_gate_run.py::parse_remember_calls."""
    pending: dict[str, str] = {}
    out: list[str] = []
    for msg in transcript:
        content = (msg.get("message") or {}).get("content")
        if not isinstance(content, list):
            continue
        for block in content:
            if not isinstance(block, dict):
                continue
            if block.get("type") == "tool_use" and str(block.get("name", "")).endswith("__remember"):
                lesson = (block.get("input") or {}).get("lesson", "")
                pending[block["id"]] = lesson
            elif block.get("type") == "tool_result":
                tool_use_id = block.get("tool_use_id")
                if tool_use_id in pending:
                    out.append(pending.pop(tool_use_id))
    return out


def _oracle_hp_by_step(oracle: list[dict]) -> dict[int, int | None]:
    """step -> BCD-decoded hp (None = row exists but hp missing / out-of-range transition garbage).
    Identical discipline to score_gate_run.py::_oracle_hp_by_step."""
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
    (the oracle logs once per observe())."""
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
    """Extract ENT/CONTACT/DECLARE/REJECT lines. CONTACT lines are deduped by (id, step); malformed
    lines (unparseable) are counted, never silently dropped."""
    lessons = parse_remember_calls(transcript)
    hp_by_step = _oracle_hp_by_step(oracle)

    ent_claims: dict[int, list[dict]] = {}          # id -> [{"region","step","claim"}] (descriptive only)
    contacts: dict[int, list[dict]] = {}            # id -> [{"step","matched"}]
    declared_threats: set[int] = set()
    declared_benign: set[int] = set()
    rejected: dict[int, str] = {}
    malformed = 0
    duplicates = 0
    seen_contacts: set[tuple[int, int]] = set()     # (id, step) pairs already counted

    n_lines = 0
    for lesson in lessons:
        m = _ENT_RE.search(lesson)
        if m:
            n_lines += 1
            eid, x0, y0, x1, y1, step, claim = m.groups()
            ent_claims.setdefault(int(eid), []).append(
                {"region": (int(x0), int(y0), int(x1), int(y1)), "step": int(step), "claim": claim})
            continue
        m = _CONTACT_RE.search(lesson)
        if m:
            n_lines += 1
            eid, step = int(m.group(1)), int(m.group(2))
            key = (eid, step)
            if key in seen_contacts:
                duplicates += 1
                continue
            seen_contacts.add(key)
            matched = step in hp_by_step
            contacts.setdefault(eid, []).append({"step": step, "matched": matched})
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
        # protocol line (e.g. a truncated/garbled ENT/CONTACT/DECLARE/REJECT) -- counted, not ignored.
        if re.search(r"\b(ENT|CONTACT|DECLARE|REJECT)\b", lesson):
            n_lines += 1
            malformed += 1

    return {"ent_claims": ent_claims, "contacts": contacts,
            "declared_threats": declared_threats, "declared_benign": declared_benign,
            "rejected": rejected, "malformed": malformed, "duplicates": duplicates, "n_lines": n_lines}


def _contact_rate(entries: list[dict], hp_by_step: dict[int, int | None],
                   drops: set[int]) -> tuple[float, int, int]:
    """(p_k, |C_k| scoreable, n_unmatched) for one entity's contact entries. A contact step is
    "scoreable" if it has a defined oracle hp AND a defined immediately-preceding oracle hp (i.e. it
    could in principle be a drop step) -- unscoreable steps (no prior, or hp missing) are excluded from
    the rate's denominator, same as the HUD gate excludes unmatched readings."""
    steps_sorted = sorted(hp_by_step)
    has_prior: set[int] = set()
    prev_defined = False
    for s in steps_sorted:
        if hp_by_step[s] is not None and prev_defined:
            has_prior.add(s)
        prev_defined = hp_by_step[s] is not None
    n_unmatched = sum(1 for e in entries if not e["matched"])
    scoreable = [e["step"] for e in entries if e["matched"] and e["step"] in has_prior]
    n = len(scoreable)
    if n == 0:
        return 0.0, 0, n_unmatched
    hits = sum(1 for s in scoreable if s in drops)
    return hits / n, n, n_unmatched


def score(transcript_path: str, oracle_path: str) -> dict:
    transcript = load_jsonl(transcript_path)
    oracle = load_jsonl(oracle_path)
    parsed = parse_transcript(transcript, oracle)
    contacts = parsed["contacts"]
    declared_threats, declared_benign, rejected = (
        parsed["declared_threats"], parsed["declared_benign"], parsed["rejected"])
    n_malformed, n_duplicates, n_lines = parsed["malformed"], parsed["duplicates"], parsed["n_lines"]

    result: dict = {
        "declared_threats": sorted(declared_threats), "declared_benign": sorted(declared_benign),
        "rejected": rejected, "entities_seen": sorted(parsed["ent_claims"]),
        "malformed_lines": n_malformed, "duplicate_lines": n_duplicates,
    }

    if n_lines and n_malformed and (n_malformed / n_lines) >= MALFORMED_MAX_FRACTION:
        result["verdict"] = "INSUFFICIENT_DATA"
        result["reason"] = (f"{n_malformed}/{n_lines} protocol lines are malformed "
                            f"(>= {MALFORMED_MAX_FRACTION:.0%} -- must stay below)")
        return result

    benign_ids = declared_benign | set(rejected)
    if not declared_threats:
        result["verdict"] = "NO_DECLARE"
        result["reason"] = "no DECLARE threat=<id> line found"
        return result
    if not benign_ids:
        result["verdict"] = "NO_DECLARE"
        result["reason"] = "no DECLARE benign=<id> or REJECT id=<id> line found -- arm (b) unexercised"
        return result

    hp_by_step = _oracle_hp_by_step(oracle)
    drops, n_scoreable_total = _drop_steps(hp_by_step)
    result["total_scoreable_steps"] = n_scoreable_total
    result["session_drop_steps"] = len(drops)

    if n_scoreable_total < MIN_TOTAL_STEPS:
        result["verdict"] = "INSUFFICIENT_DATA"
        result["reason"] = f"only {n_scoreable_total} scoreable oracle steps (< {MIN_TOTAL_STEPS})"
        return result

    # DEGENERATE guard (mirrors the HUD gate's variation-guard lesson, PR #56): a session with zero drop
    # steps makes p_base == 0, which would let ANY entity with even one contact-on-a-drop-step trivially
    # "ground" -- the flip side of "all readings constant."
    if len(drops) < MIN_SESSION_DROPS:
        result["verdict"] = "DEGENERATE_NO_DAMAGE"
        result["reason"] = (f"session has {len(drops)} drop step(s) (< {MIN_SESSION_DROPS}) -- no hp "
                            "variation to ground anything against")
        return result

    p_base = len(drops) / n_scoreable_total
    result["p_base"] = p_base

    all_entries = [e for entries in contacts.values() for e in entries]
    n_contact_lines = len(all_entries)
    n_unmatched_total = sum(1 for e in all_entries if not e["matched"])
    result["contact_lines"] = n_contact_lines
    result["unmatched_lines"] = n_unmatched_total
    if n_contact_lines and n_unmatched_total and (n_unmatched_total / n_contact_lines) >= UNMATCHED_MAX_FRACTION:
        result["verdict"] = "INSUFFICIENT_DATA"
        result["reason"] = (f"{n_unmatched_total}/{n_contact_lines} CONTACT lines reference steps with "
                            f"no oracle row (>= {UNMATCHED_MAX_FRACTION:.0%} -- must stay below)")
        return result

    def _grounded(eid: int) -> dict:
        entries = contacts.get(eid, [])
        p_k, n, n_unm = _contact_rate(entries, hp_by_step, drops)
        insufficient = n < MIN_CONTACTS
        grounded = (not insufficient) and (p_k >= p_base + MARGIN)
        return {"id": eid, "p_k": p_k, "n_contacts": n, "insufficient": insufficient, "grounded": grounded}

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
        result["reason"] = (f"need >= {MIN_CONTACTS} contacts for at least one declared threat AND one "
                            "declared-benign/rejected entity to compute a verdict")
        return result

    arm_a = len(threats_grounded) > 0
    arm_b = len(benigns_correctly_rejected) > 0
    result["arm_a"] = arm_a
    result["arm_b"] = arm_b
    result["verdict"] = "PASS" if (arm_a and arm_b) else "FAIL"
    return result


def format_report(r: dict) -> str:
    lines = ["=== Entity-grounding gate score ==="]
    if r.get("malformed_lines"):
        lines.append(f"malformed protocol lines: {r['malformed_lines']}")
    if r.get("duplicate_lines"):
        lines.append(f"duplicate CONTACT lines (repeat (id, step), first kept): {r['duplicate_lines']}")
    if r["verdict"] == "NO_DECLARE":
        lines.append(f"declared threats: {r.get('declared_threats')}  declared benign: "
                     f"{r.get('declared_benign')}  rejected: {list(r.get('rejected', {}))}")
        lines.append(f"\nVERDICT: NO_DECLARE ({r.get('reason')})")
        return "\n".join(lines)
    if r["verdict"] in ("INSUFFICIENT_DATA", "DEGENERATE_NO_DAMAGE") and "p_base" not in r:
        lines.append(f"\nVERDICT: {r['verdict']} ({r.get('reason')})")
        return "\n".join(lines)
    lines.append(f"session: {r['total_scoreable_steps']} scoreable steps, {r['session_drop_steps']} "
                f"drop step(s), base rate p_base={r.get('p_base', 0):.3f}")
    if r["verdict"] in ("INSUFFICIENT_DATA", "DEGENERATE_NO_DAMAGE"):
        lines.append(f"\nVERDICT: {r['verdict']} ({r.get('reason')})")
        return "\n".join(lines)
    lines.append("threat claims:")
    for eid, s in r["threat_scores"].items():
        tag = "INSUFFICIENT" if s["insufficient"] else ("GROUNDED" if s["grounded"] else "not-grounded")
        lines.append(f"  id={eid}: p_k={s['p_k']:.3f} n_contacts={s['n_contacts']}  [{tag}]")
    lines.append("benign/rejected claims:")
    for eid, s in r["benign_scores"].items():
        tag = "INSUFFICIENT" if s["insufficient"] else ("WRONGLY-GROUNDED" if s["grounded"] else "correctly-rejected")
        reason = r["rejected"].get(eid)
        suffix = f"  reason={reason!r}" if reason else ""
        lines.append(f"  id={eid}: p_k={s['p_k']:.3f} n_contacts={s['n_contacts']}  [{tag}]{suffix}")
    lines.append(f"\nARM (a) grounds a threat (some threat's p_k >= p_base + {MARGIN}): "
                f"{'PASS' if r['arm_a'] else 'FAIL'}")
    lines.append(f"ARM (b) rejects a decoy (some benign's p_k stays below that bar): "
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
    return 0 if result.get("verdict") in ("PASS", "FAIL", "DEGENERATE_NO_DAMAGE") else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
