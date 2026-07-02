# 2026-07-03 — Entity-grounding gate v2: consequence-anchored backward attribution (pre-registered)

## v1 FAIL recap (the causal-model mismatch)

Entity gate v1 (`eval/score_entity_gate.py`, PR #59, one paid run in `runs/brain_cn_entity/`) scored
**FAIL**: the declared threat's contact-conditional drop rate was `p_k=0.000` over 3 clean contacts against
`p_base=0.017` — arm (b) passed, arm (a) did not. Per `HANDOFF.md`'s diagnosis, this was not a scorer bug:
the two hp drops (steps 37, 89) landed 4-14 steps from any logged `CONTACT`, because Cave Noire enemies act
on their own initiative and damage can arrive without the avatar ever touching anything the brain logged —
**forward contact-logging is the wrong causal model** for a world that delivers consequences from enemy
initiative, not from player-perceived adjacency. v1's FAIL stays on the books; this is not a re-run of v1,
it is a different metric on a different (out-of-sample) run.

## The causal-model argument: forward prediction -> backward attribution

v1 asked the brain to predict a consequence FROM a touch (`CONTACT id=k step=n` -> "did hp drop at/near
n?"). That only works if damage is causally downstream of a logged touch at a knowable step. Cave Noire's
actual causal structure is the reverse: an hp drop is a ground-truth EVENT the oracle hands us for free, and
the question worth asking is "what was near the avatar, per the brain's own reporting, in the steps
immediately BEFORE this event?" — i.e. attribute the consequence backward onto whichever entity's reported
presence best explains it, rather than have the brain forward-predict which of its touches will matter.
This is a strict extension of ADR-002 SS9's hypothesize-and-ground loop (still "does behaviour/consequence
data ground the brain's own claim"), just anchored on the consequence (the drop) instead of on the claimed
event (the touch) — which is also why it stays under the "stricter-only" constraint of v1's HP oracle,
watermark, dedupe, and fraction-cap machinery: none of that changes, only what a logged NEAR event is asked
to predict, and when it counts as covering a drop.

## Protocol (machine-parseable `remember` lines)

```
ENT id=<k> region=(x0,y0,x1,y1) step=<n> claim=threat|benign   (unchanged from v1, purely descriptive)
NEAR id=<k> step=<n>       (replaces CONTACT: entity k observed near/adjacent to the avatar at step n)
DECLARE threat=<k> / DECLARE benign=<k> / REJECT id=<k> reason=<...>   (unchanged; REJECT scored as benign)
```

`ENT` stays purely descriptive, exactly as in v1 — the scorer never reads a claim off it, only off
`DECLARE`/`REJECT`. `NEAR` is logged prospectively (the brain reports what it sees near itself as it plays,
the same "log now, don't wait for the outcome" discipline as v1's `CONTACT`) — the difference from v1 is
entirely in how the scorer uses these events (backward window over drop steps), not in when or how the
brain logs them.

## The pinned metric (every constant, exact)

**Oracle / drop-step machinery — identical to v1:**
- hp is BCD-decoded at `0xC120`, in-range `[0, 10]`; `None` = out-of-range/transition garbage, same as
  `score_entity_gate.py::_oracle_hp_by_step`.
- A **drop step** `s` is an oracle row whose hp is strictly lower than the immediately preceding
  *oracle-recorded* row's hp (both in-range) — v1's `_drop_steps`, copied verbatim (reused logic, not
  imported, per the guardrail against touching `score_entity_gate.py`).
- A **scoreable step** is an oracle row with a defined immediate predecessor (i.e. it could in principle be
  a drop step).

**Watermark rule — identical to v1's retroactive-CONTACT guard, applied to NEAR:** the scorer walks the
transcript in order, maintaining a revealed-step watermark = the highest world step any
`observe`/`read_region`/`whats_changed` tool_result has reported so far. A `NEAR id=k step=n` counts ONLY if,
at the moment it was logged, the watermark was `<= n` (strictly-greater watermark => RETROACTIVE). v1's
`parse_remember_calls`/`_max_step_in_result` machinery is copied into the v2 module (not imported), per the
guardrail that v1's file is untouched.
- Retroactive NEARs are counted, reported, and excluded from scoring.
- `RETROACTIVE_MAX_FRACTION = 0.20` of all NEAR lines (accepted + retroactive) taints the log ->
  `INSUFFICIENT_DATA`.

**Dedupe / unmatched / malformed — identical shape to v1:**
- `(id, step)` NEAR pairs dedupe first-wins; duplicates counted and reported, never double-counted.
- Unmatched NEAR (a step with no oracle row) is excluded from scoring, counted, and reported;
  `UNMATCHED_MAX_FRACTION = 0.05`.
- Malformed protocol lines (unparseable `ENT`/`NEAR`/`DECLARE`/`REJECT`) are counted, never silently
  dropped; `MALFORMED_MAX_FRACTION = 0.20`.

**Attribution (the new part) — backward window:**
- `WINDOW W = 15` world steps.
- A drop step `s` is **COVERED** by entity `k` iff there exists an accepted (deduped, matched,
  non-retroactive) `NEAR id=k step=n` with `s - 15 <= n <= s`. (`n == s` covers; `n == s - 15` covers;
  `n == s - 16` does not.)
- `q_k` = (# drop steps covered by `k`) / (# drop steps).
- `b_k` = (# NON-DROP scoreable steps covered by `k`) / (# non-drop scoreable steps) — the base presence
  rate. The denominator deliberately EXCLUDES drop steps (cleaner than v1's `p_base`, which measured "how
  often does ANY drop happen" — `b_k` here measures "how often is `k` around regardless of outcome," so
  `q_k` vs `b_k` is a clean coverage-of-consequences-vs-coverage-of-ordinary-time comparison for the SAME
  entity, not a per-entity rate against a session-wide constant).

**Grounding test:**
- `MARGIN = 0.30`. `MIN_NEAR = 3` accepted NEAR events per entity, else that entity is `INSUFFICIENT` (not
  scored either way, neither grounded nor correctly-rejected).
- **GROUNDED (threat)** iff `q_k >= b_k + 0.30` AND `|N_k| >= 3` (accepted NEAR count for `k`).
- A benign/rejected entity `j` is **correctly rejected** iff it is scoreable (`|N_j| >= 3`) AND NOT
  (`q_j >= b_j + 0.30`).

**Session guards:**
- `MIN_TOTAL_STEPS = 30` scoreable steps overall, else `INSUFFICIENT_DATA`.
- `MIN_SESSION_DROPS = 5` drop steps, else verdict `INSUFFICIENT_DROPS` (NOT computed as PASS/FAIL below
  this). This directly targets v1's own starvation failure — the FAIL run had only 2 drops in 116 steps,
  nowhere near enough to exercise arm (a) meaningfully; 5 is the pre-registered floor for run 2's launcher
  brief to aim above (push sustained melee / a lower starting hp), not a number chosen after seeing run 2's
  data.

**PASS** = `>= 1` declared threat GROUNDED AND `>= 1` declared-benign/REJECTed entity correctly rejected.
Both arms required. `NO_DECLARE` if either declaration side is missing entirely. Verdict vocabulary
otherwise mirrors v1: `PASS / FAIL / INSUFFICIENT_DATA / INSUFFICIENT_DROPS / NO_DECLARE`.

## Anti-gaming analysis

- **Watermark (retroactive guard):** identical rationale to v1 — without it, a brain that feels the hit
  first could back-tag `NEAR` lines onto exactly the drop steps for its chosen threat with zero predictive
  content. Carried over unchanged.
- **Spam self-defeats:** the obvious exploit against a coverage metric is "log `NEAR id=<threat>` at EVERY
  step." This does not work here: if `k` is reported near on every scoreable step, `b_k -> 1.0` (its
  non-drop-step coverage saturates too), and `q_k - b_k` collapses toward 0 — the margin of 0.30 cannot
  clear when the denominator of "ordinary time coverage" is also maxed out. Spamming NEAR buys `q_k = 1.0`
  but at the cost of `b_k = 1.0` too, so the GROUNDED test fails. This is the core reason `b_k`'s denominator
  is the non-drop steps specifically (not the whole session): it directly prices in "were you around ALL
  the time, or specifically around consequence windows."
- **Benign-omission requires real prediction:** the only way to make a benign/rejected entity `j` pass as
  "correctly rejected" while gaming the metric would be to selectively OMIT `NEAR` for `j` near drop steps.
  But doing that reliably — logging `j` near the avatar on ordinary steps while never logging it near a drop
  step — requires the brain to actually be able to tell, at logging time (before knowing the outcome, per
  the watermark), which steps are heading toward a drop. That is not a loophole; that IS grounding. A brain
  that can selectively avoid tagging the benign entity near real damage windows has, by construction,
  learned something true about which entity's presence predicts consequences.
- **Window width (`W=15`) is generous but bounded:** wide enough to tolerate the brain's own latency in
  observing-then-logging (v1's drops sat 4-14 steps from any CONTACT — `W=15` comfortably covers that same
  slack for a NEAR reported shortly before the drop), but bounded so a NEAR logged in a totally different
  part of the session cannot retroactively "explain" an unrelated drop.

## Stricter-only clause

This pass changes ONLY the causal model (backward attribution replacing forward prediction) and the
constants that model requires (`WINDOW`, `q`/`b`/`MARGIN`, `MIN_NEAR`, `MIN_SESSION_DROPS`). Every
discipline v1 already pinned — BCD oracle, in-range guard, watermark/retroactive rule, dedupe, unmatched
cap, malformed cap — is carried over unchanged, not loosened. v1's FAIL stays on the books as a real,
informative result about forward contact-logging; it is not retracted, superseded in spirit, or re-scored
under v2's metric. Run 2 (the first paid run scored under this v2 metric) is genuinely **out-of-sample**:
this metric, every constant in it, and this document are pinned before that run happens, not fitted to it
afterward. Any future tightening of this metric may only be stricter, never looser, following the same
discipline that governed v1's own PR #56 (variation guard) and PR #59 (retroactive guard) tightenings.
