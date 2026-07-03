# 2026-07-05 — P1 (YawBandFlow) redesign: failure analysis + re-pin GATE-3D-A3

Design + gate plan only — **no primitives are built by this pass**. Scope discipline: ADR-002 §11,
the North Eye constitution, Realizer Ladder R0-first, and the house pre-registration style of the
`dtc_gate` amendments in `reports/2026-07-04-vizdoom-3d-floor-design.md` (A1/A2). Evidence base: the
GATE-3D FAIL verdict run (`runs/brain_gate3d/run3_v_FAIL/world/{grounding,oracle}.jsonl`, 27/30
completed episodes, 2942 grounding rows / 1483 commanded-turn rows / 956 scored) plus the existing
offline fixtures (`eval/fixtures/vizdoom_yaw/`, `core/yaw_flow.py`, `core/stationary_movers.py`).

## 0. The question this doc answers

HANDOFF.md's GATE-3D verdict block asserted the ARM (b) miss (in-run sign-agreement 0.774 vs the 0.90
bar, vs 0.964 on clean-scene fixtures) was **"YawBandFlow's R0 realizer degrades in busy combat
scenes"** and named "turn-estimation under dynamic clutter" as the located gap. That framing is the
starting hypothesis, not a proven finding — this doc tests it against run3's own logs before
proposing a fix, per the brief's instruction not to assume clutter.

**Verdict of the analysis: clutter is real but is the MINORITY driver of the 0.774. The MAJORITY
driver is a previously-undocumented turn-onset regime: on the onset tics of a held turn (measured
hardest at the second consecutive tic, `run_pos=1`), the dx distribution is bimodal with a spike at
exactly 0 — the world GENUINELY rotates ~0 px on that tic (ViZDoom's turn-rate ramp at the pinned
tics=4 action grain). P1 reporting `"none"` there is CORRECT perception; the disagreement is
manufactured by scoring that correct reading against a wrong expectation (`commanded` != physically
rotated on that tic). This is a SCORING-DEFINITION defect in how ARM (b) counts onset tics, not a P1
perception defect — and it is fixed by a pinned scoring rule (§3.1), not by an estimator redesign.
The clutter mechanism, by contrast, is a real P1 degradation and does need the redesign (§2).
Neither mechanism is a pairing/logging bug.**

## 1. Failure analysis (free, from run3's own logs)

### 1.1 Setup

`world_mcp.py::DoomDtcSession._do_action` computes P1 fresh on every action sub-step, diffing the
frame immediately before against the frame immediately after that one sub-step — confirmed by reading
the source (`world_mcp.py` lines ~1184-1210): `prev_gray`/`cur_gray` roll forward one sub-step at a
time, `_log_grounding` is called every sub-step, and `_last_pair_gray` is explicitly kept separate
from the P2-facing rolling pair specifically to avoid a self-diff bug. **This rules out a repeat-batch
pairing/misalignment artifact as the cause** — the mechanism the brief asked to check first. (The
known one-frame misalignment documented in `eval/fixtures/vizdoom_yaw/README.md` affects only the
now-retired 2026-07-02 probe capture, never run3's live data, which the source code shows is paired
correctly by construction.)

Baseline recomputed directly from `run3_v_FAIL`'s `grounding.jsonl`:

| | value |
|---|---|
| total grounding rows | 2942 |
| commanded-turn rows | 1483 |
| scored (P1 non-None) turn rows | 956 (None-rate 0.355) |
| sign-agreement (matches the 0.774 in HANDOFF) | 740/956 = **0.7741** |

### 1.2 Mechanism 1 (majority): turn-onset ramp — correct perception scored against a wrong expectation

Classifying every scored turn row by its position within a run of consecutive same-direction commands
(`run_pos` = 0 for the first tic of a fresh/reversed turn, incrementing while the direction is held):

| run_pos | n scored | mean\|dx\| | median\|dx\| | local sign-agreement | `direction=="none"` rate |
|---|---|---|---|---|---|
| 0 (fresh turn) | 70 | 30.0 | 31.5 | 0.643 | 0.114 |
| **1 (2nd held tic)** | **178** | **20.6** | **4.0** | **0.500** | **0.337** |
| 2 | 106 | 38.1 | 42.0 | 0.783 | 0.057 |
| 3 | 109 | 36.7 | 40.0 | 0.853 | 0.000 |
| 4 | 82 | 36.9 | 41.0 | 0.890 | — |
| 5 | 86 | 36.5 | 38.0 | 0.872 | — |
| 6+ | 325 | 36.7 | 42.0 | 0.868 | 0.034 |

`run_pos=1` is a distinct, reproducible regime: the dx distribution is **bimodal with a spike at
exactly 0** — median `|dx|=4px` (vs 40px at every other position), sign-agreement collapses to a coin
flip (0.500), and — critically — the `direction=="none"` rate (0.337) is **not** a confidence-floor
artifact: only 6.2% of run_pos=1 rows sit near `PROM_FLOOR=0.02` (confidence < 0.04); the median
confidence on these rows is 0.168, comfortably inside the "trust this reading" range. Of run_pos=1's
89 disagreements, 60 are `direction=="none"` at healthy confidence and only 29 are opposite-sign
reads (and when the true rotation is ~0 px, the sign of a ±1-4px residual is jitter, not a
directional claim that can be meaningfully wrong).

**The honest reading of this evidence (reviewer finding, adopted): the world genuinely rotates ~0 px
on that tic.** The correlation peak lands cleanly at zero because there is nothing to correlate away
from zero — ViZDoom's turn-rate ramp at the pinned tics=4 action grain delivers near-zero net
horizontal shift on the onset tic(s) of a held turn. P1's `"none"` there is *correct perception*
(three-valued honesty working exactly as designed: confidently stationary, because the camera
effectively was). The disagreement is manufactured downstream: ARM (b)'s scoring counts every
commanded-turn row as "the camera must have visibly rotated this tic," an expectation the world's own
physics does not meet at turn onset. **Mechanism 1 is therefore a scoring-definition defect, not a P1
defect** — the fix belongs in how A3 defines a scored turn step (§3.1's pinned onset rule), not in
the estimator.

The pattern is stable across every episode inspected (identical tic cadence at identical step numbers
across all 27 episodes, because dtc's opening sequence is deterministic) and is present from the very
first episode step — i.e. before any monster has closed distance or entered a busy state; it is
scene-independent, as ramp physics predicts. It accounts for roughly half of the 216 total scored
disagreements (60 of the 89 run_pos=1 disagreements are the `dx≈0` signature alone; run_pos=0's lower
agreement, 0.643, with its 0.694 None-rate, is the same off-steady-state regime measured one tic
earlier — partially rotated, partially ambiguous).

### 1.3 Mechanism 2 (real, secondary): degradation over episode duration even with the timing artifact controlled out

Restricting to `run_pos>=2` only (the "safe" positions, which cannot be explained by mechanism 1) and
bucketing by step-in-episode:

| episode step | agree | disagree | agreement (run_pos>=2 only) |
|---|---|---|---|
| 0-19 | 133 | 0 | 1.000 |
| 20-39 | 96 | 16 | 0.857 |
| 40-59 | 114 | 26 | 0.814 |
| 60-79 | 113 | 14 | 0.890 |
| 80-99 | 70 | 13 | 0.843 |
| 100-119 | 54 | 21 | 0.720 |
| 120-139 | 20 | 9 | 0.690 |
| 140-159 | 6 | 3 | 0.667 |

Even with mechanism 1 controlled out, agreement genuinely declines from 1.000 in the first 20 steps to
~0.67-0.72 by step 100+. This is not a single-episode artifact: 18/27 episodes reach step 100+, so the
decline is a broad pattern, not one outlier run. This is the part of the picture consistent with the
clutter hypothesis: `dtc_gate`'s monsters spawn at the perimeter and walk toward the player over the
episode, so later steps have more, closer, larger on-screen movers — directly corroborated by a
second, independent check: on `commanded=None` (ATTACK) rows — where the camera provably does not
turn — P1 still reports an apparent `left`/`right` direction 309/991 = 31% of the time it produces a
scored reading (median `|dx|`=13px), i.e. scene motion alone measurably fakes ego-motion in this
primitive when movers are on screen, exactly the mechanism clutter would predict. (These ATTACK rows
are correctly excluded from ARM (b) scoring — `commanded` isn't "left"/"right" — but they are direct,
independent evidence that clutter injects apparent horizontal flow.)

I also checked whether the episode-phase decline was an artifact of shorter turn bursts appearing more
often later (which would inflate the run_pos<=1 fraction, not scene content) — the risky-position
fraction by step bucket is noisy but not monotonically increasing (0.184 -> 0.364 -> 0.209 -> ... ->
0.407 -> 0.202), so it does not track the phase decline; the run_pos>=2-only table above already
removes this confound directly.

### 1.4 Ruled out

- **Repeat-batch / pairing errors**: ruled out by source inspection (§1.1) — every sub-step is diffed
  against its true immediate predecessor, logged every sub-step, independently of `observe()` timing.
- **Search-range saturation** (the `best_shift` failure mode this primitive was built to fix): checked
  directly — only 5/216 disagreements have `|dx|>=60` (near the `MAX_SHIFT=64` cap), vs 62/740 of the
  agreeing rows sit near the cap (large, correctly-signed turns routinely approach the cap — that's
  expected behavior, not saturation-driven failure). Disagreements are **not** concentrated at the
  search boundary; §1.2/1.3 fully account for them.
- **A confidence-floor mis-calibration** (i.e. the pinned `NCC_FLOOR`/`PROM_FLOOR` are simply too
  permissive): the confidence-bucket table shows local agreement rising monotonically with confidence
  (0.634 at <0.03, up to 0.891 at >=0.2) — the floors are doing real, monotone work; a stricter floor
  would trade sign-agreement for a worse None-rate (already 0.355, most of it legitimately absorbed by
  run_pos=0's honest abstention — None-rate 0.694 at run_pos=0 vs near-zero at run_pos>=3). Raising the
  floor is not the fix; it converts wrong answers to abstentions at a cost the None-rate bar (<=0.50)
  cannot absorb everywhere, and does nothing for mechanism 1's specific timing signature.

### 1.5 Summary verdict

| Mechanism | Share of the 216 disagreements (approx.) | P1 defect? | Where the fix belongs |
|---|---|---|---|
| Turn-onset ramp (run_pos 0-1, world genuinely rotates ~0; P1's `"none"` is correct) | majority (~half is the run_pos=1 dx=0 signature alone; run_pos=0 adds more of the same regime) | **No** — correct perception scored against a wrong expectation; a scoring-definition defect | §3.1's pinned onset rule (scoring), NOT the estimator |
| Late-episode degradation under sustained turning (run_pos>=2, step>=100) | secondary but real (agreement 1.00 -> ~0.70) | **Yes** — clutter genuinely corrupts the band correlation; corroborated independently by ATTACK-row apparent-motion leakage | §2(a)'s estimator redesign |

Neither the pure-clutter framing in HANDOFF.md nor a "the fixtures were wrong" alternative fully
explains the run — **it is two distinct, additive mechanisms of different KINDS**: one mis-scoring of
correct perception (fix the scoring definition), one genuine perception degradation (fix the
estimator). Quantified split, computed on run3's data: applying the §3.1 onset exclusion alone to the
UNCHANGED R0-v1 estimator lifts sign-agreement 0.7741 -> **0.8559** (708 scored steps, None-rate
0.320) — a large step, but still short of the 0.90 bar. **The residual ~0.044 gap is mechanism 2's,
and the estimator redesign (§2) remains load-bearing for it.** Both numbers stay on the record so the
improvement attribution of any future fix is visible per-mechanism.

## 2. Redesign candidates, ranked by the evidence

### (a) Multi-band voting with outlier rejection — RECOMMENDED, build this

Replace the single mid-screen band with **N=3 horizontal bands** (e.g. rows centered at 0.40H, 0.50H,
0.60H, each the current 0.30H-tall window, still excluding the weapon sprite/ceiling), compute
`_best_shift_1d` independently per band, and combine with a **trimmed vote**: take the median `dx`
across bands whose individual confidence clears the existing floor; if fewer than 2 bands clear the
floor, fall back to today's single-band result (never regress below current behavior); report
`direction=None` if the surviving bands disagree in sign by more than one band (outlier rejection).

**Scope (amended after review): this redesign is justified by and targeted at mechanism 2 (clutter)
ONLY.** Mechanism 1 is not an estimator defect (§1.2) — the world genuinely rotates ~0 on onset tics,
all vertically-offset bands see the same genuine near-zero shift, and no amount of voting changes a
correct answer. Mechanism 1 is handled entirely by §3.1's pinned scoring rule. The evidence for (a)
against mechanism 2:

- **Clutter (late-episode)**: bands closer to the top/bottom of the current window are less likely to
  simultaneously contain the same mover's silhouette at the same horizontal offset (movers are
  vertically compact relative to the screen), so outlier rejection directly suppresses a single band
  corrupted by a mover without needing to know where the mover is. The ATTACK-row leakage evidence
  (§1.3 — scene motion faking ego-motion 31% of the time P1 scores a non-turn pair) is exactly a
  single-band-corruption signature.
- **Cost**: same R0 rung (numpy only), ~3x the correlation cost of today (still cheap — 1D
  cross-correlation over ±64px is the whole point of P1's original design), no new grounding
  mechanism, no change to the output contract's three-valued shape (still `dx_px`/`direction`/
  `confidence`, now `confidence` = agreement-weighted, e.g. min band confidence among the surviving
  set, or the vote's own margin — pin this in PR-F's fixture work, not here).
- **Risk**: the mechanism-2 gap it must close is measured at ~0.044 (0.8559 with the onset rule ->
  0.90 bar, §1.5). If a mover silhouette spans all three bands at the same offset (large, close
  monster), voting won't help — that residual case is what §2(b) exists for, measured in the same
  fixture pass (§4 PR-G).

### (b) Mover-band exclusion (P2's last-known mover bboxes mask the correlation bands) — SECOND candidate, not first

Use P2's most recent mover bbox list (even if stale from the last ego-stationary gate-open moment) to
blank/exclude the horizontal column range under a mover's bbox from P1's band profile before
correlating.

- Targets the same mechanism as (a) — mechanism 2 (clutter) — but requires knowing where the movers
  are, where (a) needs no mover knowledge at all. (Mechanism 1 needs no estimator change from either
  candidate — it is handled by §3.1's scoring rule.)
- Structural complication: P2 is *gated on P1 reporting `"none"`* (`core/stationary_movers.py`
  line 140: `if yaw_reading.direction != "none": return None`). During a turn (exactly when P1 most
  needs help), P2 by construction returns `None` — there is no live mover list to mask with. The
  design would have to consume P2's **last mover list from the most recent ego-stationary moment**,
  which is explicitly a staleness/extrapolation step this codebase has so far avoided (the "never
  fabricate" ethos). Worth a fixture-level experiment, but it is not free of new grounding questions
  the way (a) is.
- Verdict: worth prototyping ALONGSIDE (a) in PR-G's replay pass (cheap — same replay, an extra
  code path), reached for only if (a) alone leaves the §1.5 residual gap open, not as the primary fix.

### (c) Search-range/regime handling

§1.4 ruled this out directly — disagreements are not concentrated near the `MAX_SHIFT=64` cap (only
5/216). No regime/search-range redesign is justified by this run's evidence. **Not pursued.**

### (d) R1 climb (small learned flow)

Per the Realizer Ladder, an R1 climb (Farnebäck/Lucas-Kanade) is justified only once R0 options are
argued dead. §2(a) is a same-rung (R0, numpy-only) fix targeted at the one mechanism that is actually
an estimator defect (mechanism 2), and it has not been tried; the other mechanism needs no estimator
at all (§3.1). **R1 is not justified yet** — propose it again only if (a)+(b), scored under the
pinned onset rule on the run3-replay (§3), still miss the 0.90 bar.

## 3. Pre-registered GATE-3D-A3

Appended per the house stricter-only discipline: `reports/2026-07-04-vizdoom-3d-floor-design.md` and
its Amendments A1/A2 stand as written; this section is the A3 pre-registration referenced by
HANDOFF.md's "fresh pre-registration required" note. **ARM (a) (both discriminators, §A2.2) and all
degenerate guards are UNCHANGED from A2 — they were not the problem (run3 in fact PASSED arm a-2 and
was close on a-1; only arm (b) failed). Do not touch them.**

### 3.0 Standing of this pre-registration (stated plainly, per review)

**GATE-3D (as amended by A2) FAILED and that verdict stays on the books unchanged** — nothing in this
section revisits, re-scores, or excuses run3. A3 is a **fresh pre-registration for the NEXT attempt**,
made before any build or paid run, and its one scoring change (the onset rule below) is defined
against **measured world physics** (§1.2: the world's own turn-rate ramp delivers ~0 net rotation on
onset tics, so `commanded` is not a valid proxy for "physically rotated" there). This is not
loosening a pending gate — no gate is pending; it is pinning the next gate's scoring so that it
measures what it claims to measure (P1's perception honesty) rather than an expectation the world
provably does not meet. The rule is pinned HERE, before any build, precisely so it cannot be invented
after a marginal result.

### 3.1 What's new: the pinned onset rule + an offline pre-check on the SAME failing data

> **Onset rule (pinned, GATE-3D-A3).** For A3's ARM (b)-analog scoring, a commanded-turn grounding
> row is a **scored turn step** only if its in-run position `run_pos >= 2`, where `run_pos` counts
> from 0 at the first row of a maximal run of consecutive same-direction turn commands, and a run is
> broken by any non-turn action (`commanded == null`), any direction change, or an episode boundary.
> Rows at `run_pos <= 1` (the onset tics) are excluded from the sign-agreement numerator and
> denominator AND from the None-rate computation, because the measured turn-rate ramp (§1.2) shows
> the world's net rotation on those tics is near zero (run_pos=1 median |dx| = 4px vs ~40px at
> steady state; steady state measured from run_pos=2 onward: `direction=="none"` rate falls 0.337 ->
> 0.057 -> 0.000). The >= 20 scored-turn-steps minimum applies AFTER this exclusion — no vacuous
> pass. The rule is fixed at `run_pos <= 1` by the measurement above and may not be widened
> (excluding more positions = loosening; forbidden).

**Why exclusion, not pairing-across-the-onset (the two options considered, one chosen):** the
alternative — pairing frames across a 2-tic window at run start so the reading reflects the full
commanded turn — was rejected because it changes the live primitive's contract, not just the scoring:
P1-computed-and-logged-every-sub-step is a load-bearing seam invariant (the PR #73 review finding,
cited in `world_mcp.py::DoomDtcSession`'s docstring — the brain must not be able to influence when P1
runs), and a variable-latency multi-frame pairing would smear readings across action boundaries and
reintroduce exactly the alignment ambiguity class that A1.5 retired. The exclusion keeps the
primitive and the seam byte-identical and moves the correction entirely into the scorer, where the
wrong expectation lives. P1's `"none"` on an onset tic remains logged, visible, and honest — it is
simply no longer scored against a commanded-direction expectation the physics contradicts.

> **Pre-check GATE-3D-A3-PC (binding, before any build is merged).** The redesigned P1 (multi-band
> voting per §2(a), optionally combined with §2(b)'s mover-band exclusion if it measurably helps in
> the same replay pass) is run **offline, in replay**, against `runs/brain_gate3d/run3_v_FAIL/world/
> grounding.jsonl`'s own commanded-turn sequence — i.e. the exact in-distribution data that caused
> the R0-v1 FAIL — reconstructing frame pairs from a fresh instrumented replay of the same 27
> episodes' seeds (the pinned seeds in `eval/fixtures/gate3d_seeds.json`; run3's raw PNGs were not
> retained, so this requires one free re-run of `dtc_gate.cfg` under the pinned seeds with frame
> capture enabled — free, Docker CPU only, no paid brain session).
>
> **PASS bar: the redesigned P1, scored WITH the pinned onset rule above, must reach sign-agreement
> >= 0.90, None-rate <= 0.50, over >= 20 scored turn steps** (ARM (b)'s numeric bars, verbatim,
> applied to the A3 scored-step definition). **BOTH numbers are reported: with the onset rule and
> without it** (the raw all-positions number), so the improvement attribution is visible
> per-mechanism — how much came from the scoring rule (mechanism 1, already measured at
> 0.7741 -> 0.8559 on the UNCHANGED estimator, §1.5) and how much from the estimator redesign
> (mechanism 2, the residual ~0.044+). A redesign that only looks good under the exclusion has not
> fixed mechanism 2 and does not pass. **This must PASS before PR-H wires the redesigned P1 into any
> live seam, and before any paid run is scheduled.** If it does not pass, iterate offline (more
> bands, different combination rule, §2(b), or escalate to R1 per §2(d)) rather than spend a paid run
> finding out again.
>
> The existing offline fixture bars are UNCHANGED and still apply as a regression floor:
> `eval/fixtures/vizdoom_yaw/` (main set: sign-agreement 1.0 curated-floor regression, known_limits/
> exhaustive documented failures) continue to be required to pass/document exactly as before — the
> redesign must not silently fix a known_limits pair without that pair being explicitly promoted out
> of `known_limits/` per its own test (`test_known_limits_document_the_r0_failure_modes`), and must
> not newly fail any currently-passing main-set pair (stricter-only: the limits can shrink, never grow
> unnoticed).

### 3.2 Why replay run3's own data, not just fresh fixtures

The whole point of this analysis (§1) is that R0-v1's clean-fixture numbers (0.964) and its in-run
number (0.774) diverged — a new set of clean fixtures could pass while missing whatever run3 actually
hit. Scoring the redesign against **the identical commanded-turn sequence that produced the FAIL** is
the only test that directly answers "does this fix the thing that actually happened," rather than "is
this a generically better estimator on data we picked." This is the same discipline as PC-2's original
fixture-first approach, aimed at the specific run that failed instead of a fresh sample.

### 3.3 The live re-run conditions (unchanged from A2 — restated for completeness, not re-derived)

Once GATE-3D-A3-PC passes offline: the paid re-run uses the **identical** `dtc_gate.cfg` scenario, the
identical 30 pinned seeds, the identical N=30/40-decisions/tics=4/1000-tic budget, the identical ARM
(a) bars ((a-1) `K >= max(D+1.5, 1.15*D)`, (a-2) `KPS_brain >= 1.5*KPS_spinner`, both read from
`eval/fixtures/gate3d_baselines.json` unchanged), and the identical degenerate guards (completion
floor, variation guard, one-attempt-per-seed, alignment-by-index-only, oracle law). **What changes for
A3: (1) the P1 implementation (§2(a)); (2) ARM (b)-analog scoring applies the §3.1 pinned onset rule
to define scored turn steps** (its numeric bars — 0.90 / >=20 scored steps / None-rate <=0.50 — are
unchanged and apply after the exclusion). `eval/score_gate3d.py::_arm_b` gains the onset-rule
implementation for A3 scoring, with the raw all-positions number also computed and printed alongside
(both-numbers reporting, §3.1) — the rule's constants come from THIS document only, amendable
stricter-only like every other pinned constant.

## 4. Build plan — smallest PR sequence

| PR | Contents | Gate on it |
|---|---|---|
| **PR-E (this)** | `reports/2026-07-05-p1-clutter-redesign.md` — docs only | review = does the failure analysis hold up and does the A3 pre-check bind correctly |
| **PR-F** | `core/yaw_flow.py`: add multi-band voting (§2(a)) behind the existing `yaw_band_flow` signature (new optional params, default band count preserves today's exact behavior for any caller not opting in — no silent behavior change to existing callers); extend `eval/fixtures/vizdoom_yaw/` only if the existing 28+6 pairs turn out insufficient to exercise multi-band disagreement (check first — likely sufficient since bands are just re-slicing the same PNGs); new unit tests pin the vote/outlier-rejection rule on synthetic band-disagreement cases. **No live ViZDoom dependency.** | existing `eval/fixtures/vizdoom_yaw/` bars must still pass (regression); new synthetic tests pin the voting rule |
| **PR-G** | (1) `eval/score_gate3d.py::_arm_b` gains the §3.1 pinned onset rule for A3 scoring, computing and printing BOTH numbers (with/without exclusion), with unit tests pinning the rule's boundaries (run_pos=1 excluded / run_pos=2 included, run broken by attack/direction-change/episode-boundary, >=20-minimum applied post-exclusion); (2) free offline re-run: `dtc_gate.cfg` under the 30 pinned seeds with frame capture enabled (Docker, no brain, no cost beyond CPU), producing a fresh grounding-equivalent replay scored by the redesigned P1 against the ORIGINAL commanded-turn sequence from `run3_v_FAIL` — this is GATE-3D-A3-PC (§3.1). Report both numbers in an addendum to this doc BEFORE PR-H. | GATE-3D-A3-PC PASS is the literal gate on PR-H existing |
| **PR-H** | Wire the redesigned P1 into `world_mcp.py::DoomDtcSession` (replaces today's single-band call site only; P2/`stationary_movers.py` untouched unless §2(b)'s mover-band exclusion also measured a win in PR-G's replay, in which case it ships here too, documented as a second, explicitly-labeled change) | `assert_action_tools_fresh` + a scripted smoke episode |
| **paid run** | one live Claude-over-MCP session (account B), 30 episodes, scored under GATE-3D-A2's ARM (a) (unchanged) + ARM (b) (unchanged bar, new P1) | GATE-3D-A3 verdict; results PR appends the verdict — never edits this doc's constants |

Every PR through the standard loop: plan -> branch -> Sonnet implements -> <5 adversarial reviewers ->
triage -> David merges.

## 5. Anti-drift table

| Drift | Guard |
|---|---|
| **Assume clutter and build mover-exclusion first** (the framing this doc was asked to interrogate) | §1's per-run_pos breakdown is the falsification test; it is now on record that the onset-ramp mis-scoring is the larger share and is not an estimator defect at all. §2 scopes (a) to mechanism 2 only, on that evidence. |
| **Score the redesign only on fresh clean fixtures** | §3.1's GATE-3D-A3-PC binds specifically to a replay of run3's own failing sequence — a fresh-fixture-only pass that never touches run3's data cannot close this gate. |
| **Quietly loosen ARM (b)'s bar because 0.774 is "close"** | Bar stays 0.90/20/0.50, verbatim, per the A2 loosening-forbidden precedent. The §3.1 onset rule is not a bar change: it redefines which rows are valid ground truth, against measured world physics, pinned BEFORE any build — and the GATE-3D FAIL it would have affected stays on the books unchanged (§3.0). |
| **Widen the onset exclusion later to rescue a marginal result** | The rule is fixed at `run_pos <= 1` by §1.2's measurement and explicitly may not be widened (§3.1: "excluding more positions = loosening; forbidden"). |
| **Report only the with-exclusion number** | §3.1 pins both-numbers reporting (with and without the onset rule) in the pre-check AND the scorer (§3.3), so mechanism-1 vs mechanism-2 attribution stays visible; a redesign that only looks good under the exclusion does not pass. |
| **Touch ARM (a) or the degenerate guards while "fixing" ARM (b)** | Explicitly out of scope (§3, opening line) — they measured correctly last time; only P1 changes. |
| **R1 climb before measuring the R0 multi-band fix** | §2(d): R1 is only justified if GATE-3D-A3-PC fails with (a)+(b) at R0. Realizer Ladder discipline, unchanged. |
| **Silently fix (or silently keep failing) a `known_limits/` pair** | `known_limits/`'s own pinned test (`test_known_limits_document_the_r0_failure_modes`) must still pass or be explicitly updated with the pair promoted out, documented — never a quiet diff. |
| **Change the multi-band default for OTHER callers of `yaw_band_flow`** | PR-F's signature change must preserve today's exact single-band output for any caller not opting into multi-band — no blast radius outside `DoomDtcSession`. |
| **Spend a paid run before GATE-3D-A3-PC passes offline** | §3.1, §4: PR-G's free replay is a hard gate on PR-H/the paid run existing at all — same shape as A2's "measure decoys before the paid run" discipline. |

## 6. Decided vs open

- **DECIDED (this doc):** the failure decomposes into two additive mechanisms of different kinds —
  turn-onset ramp mis-scoring (majority; correct perception scored against a wrong expectation, NOT a
  P1 defect) and late-episode clutter (secondary, real, a genuine P1 defect); the §3.1 pinned onset
  rule (`run_pos <= 1` excluded from A3's scored turn steps, exclusion chosen over
  pairing-across-onset, not widenable) handles mechanism 1 in the scoring definition; multi-band
  voting with outlier rejection (§2(a)) is the lead estimator candidate for mechanism 2 only,
  evaluated ahead of mover-band exclusion (§2(b)); search-range saturation is ruled out (§1.4/§2(c));
  R1 is not yet justified (§2(d)); GATE-3D-A3-PC (§3.1) as the binding offline pre-check, replaying
  run3's own sequence, reporting BOTH with/without-exclusion numbers; ARM (a) and all degenerate
  guards carry over from A2 unchanged; the GATE-3D FAIL verdict stays on the books unchanged (§3.0).
- **OPEN (free, before any live re-run):** whether multi-band voting closes the measured ~0.044
  residual (0.8559 with the onset rule -> the 0.90 bar) on run3's replayed sequence, or needs (b)'s
  mover-band exclusion added, or needs the R1 escalation of §2(d).
- **OPEN (the eventual paid run answers):** unchanged from A2 — does perception beat the best blind
  policy on kills AND ammo, now with a P1 that has cleared its own in-distribution failure offline
  first.
