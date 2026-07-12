# Entity-gate v4 — $0 coverage-vs-camping paper check (barrier 4) (2026-07-11)

Read-only analysis. No code/report changes besides this file. Source of truth: `eval/score_entity_gate_v3.py`
(frozen), and the REAL oracle/skills logs on disk at `runs/brain_kirby_v3_1/world/` and `runs/brain_kirby_v3/world/`
(untracked but present). Synthetic-trace scripts (throwaway, not committed):
`C:/Users/Succe/AppData/Local/Temp/claude/.../scratchpad/build_and_score.py` + `inspect_oracle.py`.

## 1. Formulas, from the code (not memory)

- `_coverage(entries, steps)` (v3:402-411): a step `s` is covered iff some matched NEAR at step `n`
  satisfies `s-15 <= n <= s`, i.e. **a NEAR at step `n` covers the forward window `[n, n+15]` (16 steps)**
  — it does NOT cover anything before `n`. This is the load-bearing fact: NEAR timing only buys forward
  coverage, so a NEAR placed close-before a drop unavoidably also "covers" up to 15 non-drop steps
  *after* the drop unless the window truncates against session end (or overlaps another NEAR's window).
- `q_k = covered_drops / len(drops)`, `b_k = covered_non_drops / len(non_drop_steps)` (v3:436-439).
- GROUNDED (`_grounded`, v3:430-452) iff ALL: `b_k <= 0.70` (else per-entity `INSUFFICIENT_DATA`,
  checked first), `n_near_matched >= 3`, `q_k >= 0.80`, `q_k - b_k >= 0.15`.
- Overall PASS = arm (a) >=1 declared threat GROUNDED AND arm (b) >=1 declared-benign/REJECTed entity
  scoreable (`n_near>=3`, `b_k<=0.70`) and NOT grounded.
- Session gates that must also clear: `MIN_SESSION_DROPS=5`, `MIN_TOTAL_STEPS=30`, skill-mechanism guard
  (>=1 `run_skill` call with `executed_step_count>=3` AND last `repeat_until`'s predicate fired for real
  AND `iterations>=2`) — checked independently, overrides grounding verdict if it fails.

## 2. Method: real oracle, synthetic claims, real scorer

`runs/brain_kirby_v3_1/world/oracle.jsonl` is v3.1's genuine, physics-derived HP trace (74 scoreable
steps, drops at **{7, 28, 47, 70, 74}** — verified via the frozen `_oracle_hp_by_step`/`_drop_steps`, not
assumed). Fabricated `transcript.jsonl` (typed `remember` calls with `NEAR`/`DECLARE` lines) and
`skills.jsonl` (one synthetic `move_blocked`-primary qualifying-conditional call at step 90, magnitudes
taken from the real d-probe: 7 presses/7 iterations, per `reports/2026-07-05-entity-v4-d-probe.md`),
placed after step 75 so it cannot taint the coverage numbers. Ran through the unmodified `score()`.

## 3. Results (all against the SAME real drop set {7,28,47,70,74}, non_drop_steps=69)

| Case | NEAR placement (id=1) | q_k | b_k | margin | verdict |
|---|---|---|---|---|---|
| A/B: NEAR at/just before each drop (design-doc's cited `{7,28,47,70}`) | 1.000 | **0.710** | 0.290 | INSUFFICIENT_DATA (ceiling exceeded) |
| G: v3.1's REAL logged NEARs (2,5,25,42,50,72 — 6 claims, genuine brain behavior) | 0.800 | **0.855** | -0.055 | INSUFFICIENT_DATA (camped) |
| H: NEAR at nearest real `run_skill` approach-span start (3,26,44,66) | 1.000 | **0.768** | 0.232 | INSUFFICIENT_DATA (camped) |
| D: NEAR pushed to earliest valid step for cluster 1 (1,28,47,70) | 1.000 | 0.696 | 0.304 | GROUNDED |
| E/I: NEAR at earliest valid step, all 4 clusters (1,13,32,70) | 1.000 | **0.638** | 0.362 | GROUNDED |
| I, full session: threat E-placement + benign (16,37,58) | 1.0/0.600 | 0.638/0.652 | 0.362 | **GATE: PASS** |

Case I is a genuine, scorer-verified PASS (`ARM (a): PASS, ARM (b): PASS, GATE: PASS`) — arithmetic
reachability is confirmed, not hypothetical. Case G (real v3.1 brain behavior) reproduces the design
doc's cited "-0.043" margin closely (-0.055 here; same sign and order of magnitude — the small gap is
plausibly a slightly different real NEAR set than what I reconstructed from the verdict's prose list).

## 4. Why coverage and camping ARE antagonistic here, precisely

A NEAR only buys *forward* coverage (`[n, n+15]`). Placing it "shortly before the approach" (the brief's
own honest instruction, and what a real brain naturally does — cases A/B/H) leaves 15 steps of unavoidable
forward bleed into non-drop time per isolated drop-cluster; with 5 drops in 4 non-mergeable clusters
(drops >15 steps apart merge; here only the last two, 70&74, are close enough), that is enough to push
`b_k` to 0.71-0.77 — **just over the 0.70 ceiling**, not by a landslide. Any *additional* honest NEAR
checks (case G's natural "keep glancing" behavior, 6 claims instead of 4) blow it further (`b_k=0.855`).
The only placements that clear 0.70 (D/E/I) require claiming NEAR at the **earliest arithmetically valid
step for each cluster** (as early as session step 1 for the first cluster) — i.e. deliberately gaming the
window's forward-only shape and the scoreable-steps edge exclusion, not "NEAR shortly before each
approach" as v3/v3.1's own fix language recommended (that recommendation, case H, still fails at 0.768).

## 5. Stress factors

- **Enemy-death-on-contact / respawn:** does not change the arithmetic above; it only explains why v3 and
  v3.1 both banked *exactly* 5 drops with zero slack above `MIN_SESSION_DROPS=5` — no margin exists on the
  drop-count side either, compounding the risk (design doc's own guard-rail, confirmed, not re-derived here).
- **~60-decision budget:** the winning placements (D/E/I) use only 3-4 NEAR claims total per entity —
  cheap in decision budget, not the binding constraint.
- **v4's `revealed_at` guard:** `claim_near`'s `step` is brain-supplied and must (per the design's optional
  hardening) match the wire-legal frame the brain was just shown — it **cannot be backdated**. This means
  the gamed early-step placements (D/E/I place the first threat NEAR at step≈1) are only *honestly*
  achievable if the entity is genuinely near-visible at session boot. **Not verified in this paper check**
  — would need one cheap visual check of the gate-room boot frame, not a further $0/$5 spend, before
  trusting the brief can rely on it.

## 6. VERDICT: REACHABLE-ONLY-IF

Arithmetically/geometrically reachable (case I is a scorer-verified full PASS on real drop timing), but
**NOT under natural, brief-following NEAR-logging behavior** — every "honest timing" placement tested
(A/B/G/H) fails the camping ceiling, with the closest honest miss at `b_k=0.710` (only 0.010 over).
Conditions for a real run to have a realistic shot:
1. Cap total threat-entity NEAR claims at **4** (one per non-mergeable drop-cluster on this room's drop
   spacing — more, as in the brain's real 6-claim v3.1 behavior, drives `b_k` to 0.855).
2. Each NEAR must be logged as early as the entity is genuinely visible/near for that cluster, not
   "shortly before approach" — the brief needs this reframed from timing-precision to
   timing-*earliness*, and it must be independently checked that the entity really is near-visible that
   early (unverified here, cheap follow-up).
3. Same discipline applies to the benign/decoy entity (keep it at `MIN_NEAR=3`, non-clustered) or its own
   `b_k` risks the ceiling too (untested combinations could wrongly-ground it, as flagged in Case F,
   dropped from the table for space — 3-NEAR benign at steps overlapping mid-session gave `WRONGLY-GROUNDED`).
4. This is a brief-only lever (no machinery change), consistent with the design doc's framing, but the
   margin for error is much thinner than "5,760 placements clear the bar" suggested — most of that
   solution space corresponds to unnatural, front-loaded NEAR timing, not organic play.

## Negative claims / paths checked

- No `runs/brain_kirby_v3_1/world/claims.jsonl` exists (v4 claim tools not yet built/run) — checked via
  `ls runs/brain_kirby_v3_1/world/`. Confirms v4's structured-claims scorer has never scored a real run;
  this check is necessarily synthetic-on-real-oracle, not real-claims end-to-end.
- No other `oracle.jsonl` with >=5 drops and >=30 scoreable steps found under `runs/brain_kirby*` besides
  `brain_kirby_v3` and `brain_kirby_v3_1` (both inspected above).
