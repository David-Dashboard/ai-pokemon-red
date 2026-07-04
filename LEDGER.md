# Ledger — entity-gate v3.1 pre-registration (ai-pokemon-red)

<!-- SCOPE SPLIT (2026-07-04): This file is CURRENT-RUN task state ONLY — the single task in
     flight, its checkboxes, and a one-line handoff. The cross-session narrative and multi-day
     history live in HANDOFF.md; do not restate them here. The ledger hooks (rehydrate.py /
     ledger_gate.py) re-inject THIS file after every compaction and gate the Stop on open tasks,
     so keep it short, current, and truthful. HANDOFF = durable story; LEDGER = current run. -->

## Goal
North-star NEXT #1: write the entity-gate **v3.1 pre-registration** — the two brief/protocol
discipline fixes the v3 INSUFFICIENT_DATA verdict located (pre-approach NEAR discipline +
distance invocation), machinery frozen. Done when the pre-reg doc is on a branch, PR'd, and one
adversarial Sonnet review is triaged. NOT done here: the paid run (David authorizes) or merge (David).

## Handoff (update before every stop)
- State: v3 banked INSUFFICIENT_DATA (skill-guard: 0 qualifying-conditional; b_k repair VALIDATED
  0.812→0.585). Two INDEPENDENT diagnosed failures: (a) NEARs trailed their drops → q_k starved 0.400;
  (b) approach_suspect invoked at adjacency → region_changed fired in 1 press. v3.1 fixes both in the
  brief only; scorer `eval/score_entity_gate_v3.py` + enum + ceiling + guard inherited unchanged.
- Next: write `reports/2026-07-04-entity-v3.1-prereg.md`, PR, send 1 Sonnet adversarial reviewer, triage.
- Blocked: nothing. (Paid run + merge are David's gates, not blockers on the doc.)

## Constraints
- Machinery FROZEN: no edit to `eval/score_entity_gate_v3.py`, the `stop_when` enum, `B_K_CEILING`,
  the skill-mechanism guard, or the macro-interior exclusion. v3.1 is brief/protocol deltas only.
- Stricter-only: v3.1 may only tighten. The pre-registered v3.2 mechanical-guard escalation is the
  ONLY code-touching path, and it fires only IF this brief-only attempt fails on prong (a) again.
- One paid attempt under this pre-reg; no informal re-run. Paid run needs David's OK (account-B).

## Decisions
- [2026-07-04] v3.1 stays brief-only (machinery frozen), faithful to the v3 verdict's own scoping —
  NOT a mechanical guard yet. Anti-thrash is satisfied by (i) a materially-restructured brief that
  names the exact v3 failure + consequence, (ii) fix (b) changing the cycle geometry, and (iii) a
  pre-registered v3.2 mechanical escalation if prong (a) fails a second time. Flagged for David @ review.

## Tasks
- [x] Read v3 verdict + v3 pre-reg + v3 brief; locate the two failure modes  · evidence: reports/2026-07-03-entity-v3-verdict.md §diagnosis (a)+(b); runs/brain_kirby_v3/CLAUDE.md step 3(i)
- [ ] Write `reports/2026-07-04-entity-v3.1-prereg.md` (brief deltas + inherited machinery + escalation ladder)  · evidence: <pending>
- [ ] Open PR off `docs/entity-v3.1-prereg`; post 1 Sonnet adversarial review; triage findings  · evidence: <pending>
- [ ] Update HANDOFF §NEWEST with the v3.1 pre-reg block; flag the fork for David  · evidence: <pending>
