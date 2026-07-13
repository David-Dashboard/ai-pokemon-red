# Entity-gate v5 bar redesign - design only (2026-07-13)

Status: **design doc only**. Cost: **$0**. No paid v5 run is scheduled here. This
report requests no code, scorer, tool-schema, or run-artifact change; session
bookkeeping may still update `HANDOFF.md` and `LEDGER.md` separately.

## Decision

v5 is a **new gate**, not a stricter v4. The v3/v4 forward-only coverage window
`[n, n+15]` is retired for v5 because it made honest NEAR logging fight the
camping ceiling in the Kirby room:

- v3.1's real NEARs: `b_k = 0.855`.
- NEAR at or just before each drop: `b_k = 0.710`, just over the `0.70` ceiling.
- NEAR at real approach-span starts: `b_k = 0.768`.
- The only scorer-verified PASS used early/minimal NEAR placement, not natural
  brief-following behavior.

The v5 bar should be **consequence-anchored backward coverage**:

> A consequence at drop step `d` is attributed to entity `k` only if the brain
> made a non-reactive `claim_near(k, n)` before that consequence, with
> `d - W <= n <= d - 1`.

Recommended fixed window for the first v5 pre-registration: **`W = 6` scoreable
world steps / press-equivalent observations**.

Why `W = 6`:

- It is short enough to stop the v4 failure mode where a broad forward window
  mostly measured non-drop time after an honest claim.
- It is long enough for the validated `move_blocked` conditional scale in the
  real gate room (`3-7` presses, with no 1-2 press false firing).
- It forces the candidate world/room to supply real pre-contact visibility.
  Kirby's known room only partly does: one probe saw cluster 1 at about 8
  presses lead, later clusters at about 0-1; the local-only instrument hunt
  raised an unresolved cadence discrepancy that makes the best case weaker.

If a v5 pre-registration wants a different `W`, that is not a tweak. It must
rerun the free paper check and visibility/cadence probes against the proposed
number before the pre-reg is frozen.

## Source status

Required sources read for this design:

- `CODEX_HANDOFF.md` Task 2.
- `reports/2026-07-11-entity-v4-verdict.md`.
- `reports/2026-07-11-entity-v4-coverage-papercheck.md`.
- `reports/2026-07-11-entity-v4-visibility-probe.md`.
- `reports/2026-07-05-entity-v4-d-probe.md`.
- `reports/2026-07-05-northstar-capability-map.md`.

Local-only source used cautiously:

- `reports/2026-07-11-entity-v4-instrument-hunt.md` exists locally but is
  untracked and absent from `origin/main` as of this session. This doc uses it
  only as a non-canonical warning about press-cadence risk and the unverified
  door/sub-room lead. A v5 pre-registration must either avoid depending on it,
  include it as a tracked receipt, or rerun the relevant $0 probe.

## Inherited instrument

v5 inherits the reviewed #102 typed-claims instrument **as-is**:

- `claim_entity`
- `claim_near`
- `declare`
- `reject`
- `note_reading`

Do not redesign the claim tools for v5. Keep the claim tools gated, acks-only,
and oracle-off-wire. `note_reading` stays audit-only and unscored.

The v5 scorer may reinterpret how scored `claim_near` records are evaluated,
but the tool schema itself is not part of this redesign.

## Proposed v5 bar

Inputs:

- Typed claims from the #102 instrument.
- Oracle consequence trace for scoring only, never on the wire.
- Pinned action cadence and scoreable-step definition in the pre-registration.
- One pre-registered candidate world/room or state.

Definitions:

- `drop d`: an oracle HP/consequence drop step.
- `valid NEAR(k, n)`: a `claim_near` for entity `k` whose brain-supplied step
  is non-retroactive and whose server `revealed_at` is before the consequence
  it is used to explain.
- `covered drop`: a drop `d` with at least one valid `NEAR(k, n)` satisfying
  `d - 6 <= n <= d - 1`.
- `productive NEAR`: a valid NEAR followed by at least one drop in
  `[n + 1, n + 6]`.
- `unproductive NEAR`: a valid NEAR not followed by a drop in that interval.
- `q_k = covered_drops(k) / total_drops`.
- `p_k = productive_nears(k) / valid_nears(k)`.
- `u_k = unproductive_nears(k) / valid_nears(k)`.
- `candidate exposure`: a scoreable step where the entity is visible/near enough
  that an honest brain could file a `claim_near`.

Threat arm:

- At least `5` total scoreable drops in the run.
- At least `30` total scoreable steps.
- A declared threat entity `k` has at least `3` valid NEARs.
- `q_k >= 0.80`.
- `u_k <= 0.40`.
- NEAR cadence cap is respected.

Benign/rejection arm:

- At least one declared-benign or rejected entity is scoreable with at least
  `3` valid NEARs.
- The benign/rejected entity must be a **plausible comparator**, not a distant
  non-interacting prop. The pre-registration must freeze evidence that:
  - it is visible in the same run segment and same action regime as the threat,
  - it has at least `3` candidate exposures,
  - at least `2` of those exposures occur within `6` scoreable steps of a
    threat candidate exposure, and
  - at least one exposure occurs during an approach/retreat phase where a
    mistaken brain could reasonably suspect it.
- It is correctly rejected only if both are true:
  - `q_j <= 0.40` and `p_j <= 0.40`.
  - the best declared threat beats it by at least `0.30` on drop coverage:
    `q_threat_best - q_j >= 0.30`.
- Its NEARs must not be merely time-overlapped with the threat's drop windows,
  but they must be opportunity-overlapped with the threat enough to make the
  decoy plausible.
- The pre-registration must name the decoy/benign opportunity and show in a
  free precheck that it satisfies the plausible-comparator evidence above.

Mechanism guard:

- Retain the qualifying-conditional requirement. For Kirby, `move_blocked` is
  the primary predicate; `region_changed` is disallowed in the known gate room
  because the d-probe showed press-1 scroll/walk-animation firing on every
  candidate box tested.

Overall PASS:

- Threat arm passes.
- Benign/rejection arm passes.
- Mechanism guard passes.
- No pre-registered invalidation condition fires.

Overall FAIL:

- The run is scoreable and one of the required arms fails.

INSUFFICIENT_DATA:

- Minimum drops/steps are not met.
- The claim stream violates same-step or cadence rules.
- The pre-registered cadence or candidate-world assumptions are not met.
- The benign arm is not scoreable.

## Mandatory brief clauses

Any v5 run brief must include these clauses in plain language:

1. **No reactive same-step NEARs.** A `claim_near` made at the same step as a
   hit/drop, or after the hit/drop is visible, is not scoreable. The brain must
   claim proximity before the consequence.
2. **NEAR cadence is capped.** For the same entity, make at most one scoreable
   `claim_near` per 6 scoreable steps, and at most 6 total scoreable NEARs in
   the gate run unless the pre-registration freezes a different cap after a
   free paper check.
3. **No backdating.** The brain must not use `claim_near` to reconstruct a
   past contact after seeing the result. Scoring should require the
   brain-supplied step and server `revealed_at` to support a pre-consequence
   claim.
4. **Typed claims only.** Freeform prose does not score as entity, NEAR,
   declare, reject, or reading evidence.

## Press cadence

Pin the first v5 attempt, if it is ever pre-registered, to the canonical
`run_skill` cadence used by the Kirby physics probes:

- `hold_frames = 30`
- `EXPECTED_WALK_FRAMES_PER_PRESS = 46`

Probe numbers do not transfer across cadence. If the chosen v5 world/room uses
any other cadence, or if the run mixes direct button presses with skill-held
presses, the pre-registration must first include a free cadence probe that
measures:

- frames per press/action,
- visible lead time before each scripted drop,
- whether NEAR windows remain inside `[d - 6, d - 1]`,
- whether the same drop sequence still supplies at least 5 scoreable drops.

## Free prechecks before any v5 pre-registration

Do all of these before freezing a pre-registration. They are not paid runs.

1. **Cadence precheck.** Pin the cadence and show the candidate room's lead
   times under that exact cadence.
2. **Visibility precheck.** Show that at least 4 of 5 scripted drops have a
   genuinely visible/near threat opportunity in `[d - 6, d - 1]`, not only at
   `d`.
3. **Consequence supply precheck.** Show at least 5 drops, at least 30
   scoreable steps, and no death spiral that makes the gate depend on perfect
   pathing.
4. **Benign/decoy precheck.** Identify the benign/rejected entity and prove it
   is a plausible comparator: same run segment/action regime as the threat,
   at least 3 candidate exposures, at least 2 exposures within 6 scoreable
   steps of a threat candidate exposure, and at least one exposure during an
   approach/retreat phase where a mistaken brain could reasonably suspect it.
   A far-away prop or temporally isolated harmless sprite does not exercise the
   rejection arm.
5. **Mechanism precheck.** Show at least one qualifying conditional call with
   the pre-registered predicate. For Kirby, use `move_blocked` primary and avoid
   `right_third` as a watch box because the d-probe found idle enemy motion
   there even before movement.
6. **Paper-score precheck.** Run synthetic typed claims over the real scripted
   oracle trace under the proposed v5 bar. Include both an honest schedule and
   an adversarial/gaming schedule. The bar is not ready if PASS only exists for
   a narrow schedule taught by the brief.
7. **Source-status check.** If retaining Kirby and using the door/sub-room lead,
   first create a fresh hp=6 state near that door and characterize enemy lead,
   retreat geometry, wall availability, benign candidates, and respawn/drop
   supply. Do not depend on the current local-only instrument-hunt note alone.

## Non-goals

- No paid v5 run is authorized or scheduled by this doc.
- No scorer implementation is requested here.
- No typed-claim tool redesign.
- No attempt to relabel v4 as PASS/FAIL under v5.
- No "stricter-only" argument from v3/v4. v5 is a fresh gate with a fresh
  pre-registration.
- No held-out game tuning.
- No dependence on RAM/oracle data on the brain wire.
- No automatic mutation of identity/persona or learned skills.

## North Star capability bought

Primary capability bought: **A2 spatial reasoning / named layer, object-side
addressability** from the capability map.

The narrow claim is not "can play Kirby better." The claim is:

> From screen-only evidence, the fixed brain can bind a visible entity to a
> later consequence, reject a plausible decoy, and do so before the consequence
> is known.

That is the object/consequence-attribution subproblem needed for referential
grounding: the brain needs stable things it can point at and reason about, not
just coordinates.

Secondary evidence, if the mechanism guard remains, touches **A5 compiled
conditional reflexes** because the run must include a real qualifying
conditional predicate. But v5 should not be sold as an A5 gate. Its main
capability purchase is A2 object grounding under temporal credit assignment.

If a proposed v5 pre-registration would only prove that the brief taught the
brain when to schedule NEAR claims, or that it can reject an implausible decoy,
it buys no North Star capability and should not be run.

## Recommendation

Use the backward-window bar above as the default v5 design. Do not pre-register
until the free prechecks pass under the pinned cadence. If Kirby is retained,
the known `kirby_entity2.state` room is a weak candidate; the door/sub-room lead
needs a fresh hp=6 probe before it can carry a paid gate. A world or room with
slower, visible-at-range threats is probably the cleaner v5 candidate.
