# Entity-gate v5 bar redesign — status confirmation (2026-07-23)

Status: **design doc only, $0**. No code, scorer, tool-schema, or paid-run change.

## Prior-art flag (read first)

This deliverable already exists, **merged on `main`**:
`reports/2026-07-13-entity-v5-bar-redesign.md` (PR #106) +
`reports/2026-07-13-entity-v5-candidate-shortlist.md` (PR #109). Both evaluate
the same three v4-verdict candidates and land on the same answer.
`HANDOFF.md`'s top block has carried zero entity-v5 news since 2026-07-13 (all
recent entries are Gate 0). This report does not re-derive the design — that
duplicates banked work — it re-verifies the 07-13 decision against today's
mandatory clauses and states what is still open.

## Candidate evaluation (re-checked against v4 verdict, answer unchanged)

- **(a) Backward window `[n-W,n]` anchored on drops — chosen.** Matches the
  consequence-anchored intent; kills the forward-window camping trap (v3.1
  real NEARs `b_k=0.855`; NEAR-at-drop `0.710`; span-start `0.768` — all near
  or over the 0.70 ceiling).
- **(b) Exposure-normalized `b_k`** — folded into the benign-arm plausible-
  comparator requirement, not used as the primary fix (needs an unbuilt
  approach-phase detector; would trade one unbuilt instrument for another).
- **(c) Visible-at-range instrument** — right long-run direction, not this
  attempt's instrument. Kirby is kept only to prove bar geometry cheaply;
  07-13 already flags the Kirby room dead for an actual v5 run (no plausible
  comparator) and points at Cave Noire as the top range-visible candidate.

## Bar (unchanged): backward window, W=6

`covered drop d`: >=1 valid `claim_near(k,n)`, `d-6<=n<=d-1`.
`q_k=covered_drops(k)/total_drops`; threat arm `q_k>=0.80`. Benign arm needs a
plausible comparator (>=3 exposures, >=2 within 6 steps of a threat exposure),
rejected via `q_j<=0.40` and `q_threat_best-q_j>=0.30`. Full definitions live
in the 07-13 doc, not reproduced twice.

## Mandatory inherited-math clauses (confirmed present)

1. **No reactive same-step NEARs** — a claim at/after a visible drop doesn't score.
2. **NEAR cadence capped** — <=1 per entity per 6 steps, <=6 total, absent a
   fresh paper check for a different cap.
Both already mandatory in 07-13's brief clauses; not loosened here.

## Press cadence (pinned) / fresh gate

`hold_frames=30`, `EXPECTED_WALK_FRAMES_PER_PRESS=46`; any other world/cadence
needs a fresh free cadence probe before pre-reg. v5 is a new gate vs
v3/v3.1/v4: no partial credit, cannot be satisfied by re-labeling old runs.

## North Star capability bought

**A2 — spatial reasoning / named layer, object-side addressability**
(`reports/2026-07-05-northstar-capability-map.md`). Secondary: A5 conditional
reflexes, only if `move_blocked` fires.

## $0 pre-checks before ANY spend (status today)

1. Cadence precheck — done for Kirby; fresh probe needed for any other world.
2. Visibility precheck (>=4/5 drops, lead in `[d-6,d-1]`) — **fails on Kirby**;
   **not yet run on any other candidate**.
3. Consequence-supply precheck (>=5 drops, >=30 steps, no death spiral) — open.
4. Benign/decoy precheck — no plausible Kirby comparator found; open elsewhere.
5. Mechanism precheck (`move_blocked`) — validated on Kirby only (4/4).
6. Paper-score precheck (honest + adversarial schedule) — done for the retired
   forward-window bar, **not yet done for this backward-window bar**.

**New finding this session:** 07-13's shortlist named Cave Noire (`0xC120` HP
oracle, fixed-camera, dev game) as the top candidate for a multi-route
source-status probe covering checks 2-5 — that probe was never run; no PR or
`codex/cave-noire-*` merge exists on `main`. That is the real next $0 step,
not another bar rewrite.

## Recommendation

Entity-v5 stays **SUSPENDED**, unchanged from 07-13. Do not pre-register until
a Cave Noire (or equivalent) source-status probe clears checks 2, 3, 4, 6. No
spend authorized here.
