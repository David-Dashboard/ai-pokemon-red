# 2026-07-03 -- Entity-grounding gate v3 verdict: INSUFFICIENT_DATA (b_k repair VALIDATED; NEAR-discipline + adjacency-invocation diagnoses)

Verdict for the paid run pre-registered in `reports/2026-07-03-kirby-skill-port-entity-v3.md` (incl.
Amendment A1, 2026-07-03), scored by `eval/score_entity_gate_v3.py`. Built: Kirby GB port of
`define_skill`/`run_skill` on `World`, gated behind `KIRBY_SKILLS=1` (PR #93, 7/7 free pre-check gates
PASS -- gate 3 decided NOT_ADMITTED, which the doc's own §6 counts as a pass, not a NEEDS_ASSETS
non-decision); the v3 scorer itself (repaired bar, macro-interior exclusion, skill guard, PR #94 +
Amendment A1). Run evidence: `runs/brain_kirby_v3/` (`transcript.jsonl`, `world/oracle.jsonl`,
`world/skills.jsonl`). All numbers below verified directly against those raw files and against
`uv run --frozen python eval/score_entity_gate_v3.py runs/brain_kirby_v3`.

## The banked verdict

```
GATE: INSUFFICIENT_DATA (skill-mechanism guard failed: 0 qualifying-conditional run_skill call(s)
(need >= 1) -- conditional-half evidence untested; grounding numbers reported for audit only)
```

Per §5.5's one-attempt rule, this is banked as-is. **One attempt used under this pre-registration; no
re-run under it.** A second attempt requires a fresh, narrower pre-registration (flagged as an open
question in the source doc's §8, not pre-authorized here).

## Numbers (verified against the raw run + the scorer's own output)

**Skill-mechanism guard** (`eval/score_entity_gate_v3.py`, §5.4 + Amendment A1): 15 `run_skill` calls
logged in `world/skills.jsonl` (plus 3 `define_skill` + 2 `redefine_skill`), 2 qualifying
(`executed_step_count >= 3`), **0 qualifying-conditional** (a qualifying call whose final `repeat_until`
fired its `stop_when` before `max_iters` AND `iterations >= 2`) -- guard FAIL, gate fires
`INSUFFICIENT_DATA` before the GROUNDED/FAIL computation is authoritative.

**Grounding numbers (computed and reported for audit only, per the doc's own discipline):**

| | q_k | b_k | n_near | Arm result |
|---|---|---|---|---|
| threat id=1 | 0.400 | 0.585 | 3 | (a) FAIL -- floor `q_k>=0.80` not met (0.400), margin `q_k-b_k>=0.15` also not met |
| benign id=2 | 0.600 | 0.508 | 4 | (b) PASS -- correctly-rejected (`static arch cluster; Kirby stood adjacent 4x (steps 21,23,25,52) with zero life-drops, while every drop came from round mobile enemies (id=1)`) |

**Run facts** (`transcript.jsonl`, `world/oracle.jsonl`): 87 turns, **$4.3176** (~$4.32), `subtype:
success`, `is_error: False` -- clean completion, no infra death. 5 HP-drop events banked
(`watch.hp` steps 6, 35, 40, 61, 69: 6->5->4->3->2->1), brain survived the run at **1 life**. Skills:
5 define/redefine calls (3 `define_skill` + 2 `redefine_skill`), 15 `run_skill` calls
(12 `approach_suspect`, 2 `retreat_to_benign`, 1 flat `mount_step` with no `repeat_until`). Two
DIFFERENT pairs of calls matter for the guard -- do not conflate them (clarified per the PR #95
review): (i) the two `approach_suspect` calls that reached `iterations=2` (record steps 28 and 55)
still FAIL the qualifying floor, `executed_step_count=2 < 3`; the other ten approaches all fired
`region_changed` at `iterations=1`. (ii) The only two calls that DO meet `executed_step_count>=3`
are the two `retreat_to_benign` calls (record steps 20 and 51, esc=8) -- but their stop reason is
`steps_elapsed(8)`, which §5.4's own text excludes from qualifying-conditional (a pure step-count
loop never branches on world state). No call satisfies both clauses simultaneously: 0
qualifying-conditional.

**Pre-registration + infrastructure cited:**
- `reports/2026-07-03-kirby-skill-port-entity-v3.md` (incl. **Amendment A1**, 2026-07-03 -- the
  multi-`repeat_until` combination rule: only the FINAL `repeat_until` sub-record is evaluated for the
  qualifying-conditional test, never summed/OR'd across sibling blocks).
- PR #93 (Kirby skill port): **7/7 free pre-check gates PASS** (gate 1 dry executor, gate 2 per-press
  overhead 6.76ms/8.68ms recorded/live vs the 150ms budget, gate 3 entity-admission decided
  NOT_ADMITTED, gate 4 seam isolation, gate 5 tools freshness, gate 6 seam physics 46/36 frames per
  press verified live, gate 7 auditability).
- Seam validation (`_static_tools("kirby_dreamland")`, verified directly): flag OFF = **9 tools**
  (`observe, explore, goto, remember, read_region, whats_changed, press_button, press_sequence, wait`);
  flag ON = **11 tools** (adds `define_skill`, `run_skill`) -- exactly the ARC-precedent seam-isolation
  shape, confirmed pre-boot.

## What VALIDATED despite the verdict

1. **The exposure macro drove `b_k` down from v2's failure value to inside the ceiling.** v2's arm (a)
   observed `b_k = 0.812` (the brain camped near the threat 81% of ordinary time, the root cause v2's
   own FAIL synthesis named). v3's threat id=1 measured **`b_k = 0.585`**, comfortably under the
   `B_K_CEILING = 0.70` precondition. The camping mechanism the macro was built to fix is **fixed** --
   the alternating approach/retreat cycle mechanically forced away-time into the session exactly as
   §4/§5.3 predicted it should, and the ceiling that would have caught a repeat of v2's failure did not
   fire.
2. **The benign arm PASSed.** Id=2 (the static arch cluster) is correctly-rejected: scoreable
   (`n_near=4 >= MIN_NEAR`, `b_k=0.508 <= 0.70`) and NOT grounded (`q_k=0.600 < 0.80`). The scorer
   correctly distinguished a benign, stationary structure from the mobile threat that actually produced
   drops -- exactly the discrimination arm (b) exists to test.
3. **The skill guard worked exactly as designed.** It caught that no call satisfied both guard
   clauses at once: every `region_changed` fire came at `iterations=1` or `2` (the latter still
   under the `executed_step_count>=3` floor), and the only `esc>=3` calls were `steps_elapsed`
   retreats, excluded from qualifying-conditional by §5.4's own text -- i.e., every conditional fire
   was functionally a one-shot, not a genuine repeated check-and-loop. This is precisely the failure mode rung 1's own
   verdict flagged as untested and asked this port's gate to surface ("a future port's gate should
   consider pinning ... so the conditional half is verified, not just permitted"). The guard did that
   job: conditional-half evidence for the skill-compilation mechanism is **still absent**, and the gate
   said so instead of quietly reporting a clean PASS/FAIL on grounding numbers that would have obscured
   the gap.

## The mechanical diagnosis (corrected per the PR #95 adversarial review)

(a) **NEAR-discipline non-compliance -- the mandatory pre-approach NEAR (brief cycle step (i)) was
skipped or mistimed. Span geometry is NOT the cause.** An earlier draft of this report claimed drops
landed inside macro spans beyond `W=15` reach; the PR #95 review's span computation refuted that, and
it re-verifies: computing every `run_skill` span as `(r.step - r.world_steps_used, r.step]` per
§5.6's own formula, **all 5 drops (steps 6, 35, 40, 61, 69) land exactly on the END boundary of their
approach span** -- the moment `region_changed` fired -- which §5.6 explicitly keeps claimable; zero
drops are macro-interior. The actual starvation mechanism: only **3** `NEAR id=1` claims exist in the
entire run (steps 7, 38, 64), against 5 drops and 12 approach calls, and **each was logged AFTER its
nearest drop** (7 after drop 6; 38 after drop 35; 64 after drop 61). Coverage requires `n <= s`
(`_coverage`'s `s - 15 <= n <= s`), so a NEAR trailing its drop covers nothing -- the `q_k` numerator
is exactly 2 (drops 40 and 69, each covered by the NEAR that happened to precede it at distance 2 and
5). `W=15` was never the binding constraint: every approach span's start-to-drop distance is **1**
(spans are 1-2 world-steps), so a pre-approach NEAR logged at ANY span start would trivially have
covered its drop with 14 steps to spare. **`q_k` starved at 0.400 because the brain skipped the
brief's mandatory step (i) ("manual look + NEAR before every approach"), not because of window
geometry or span length** -- protocol adherence, not metric machinery.

(b) **`approach_suspect` was invoked only when already adjacent to the target** (independently
verified -- this half of the original diagnosis stands), so `region_changed` fired on the first (or
second) press almost every time -- `region_changed` after 1 press is not evidence of a genuine
repeated condition-check, it is a one-shot masquerading as a loop. Because the macro was never
invoked from a genuine distance, `region_changed` never got the chance to fire after several
iterations of walking, so no call ever qualified as **qualifying-conditional** (needs
`iterations >= 2` AND `executed_step_count >= 3` on the same call -- the two calls that hit
`iterations=2` still had only 2 executed steps, one short of the qualifying floor).

These are TWO INDEPENDENT failure modes, not one: (a) is claim timing (when NEARs were logged),
(b) is invocation geometry (where the brain stood when it called the macro). Fixing either does not
fix the other.

## The v3.1 design note (NOT a pre-registration -- the located questions only)

Two independent fixes, one per failure mode:

(i) **Pre-approach NEAR discipline (the coverage prong, fixes (a)).** The brief must make the
NEAR-before-`run_skill` ordering as loud and mechanical as v2's watermark warning -- the same shape
of miss (NEARs trailing their drops) also appears in v2 run 10
(`runs/brain_kirby_entity/run3_walled`: drops at steps 3 and 11 with zero preceding NEARs; the first
`NEAR id=1` lands at step 16), so this is a recurring brain-compliance failure, not a one-off. A
NEAR at any approach-span start covers its drop trivially (start-to-drop distance 1 vs `W=15`); the
protocol already demands it; the brief needs to enforce the ordering the way it enforces the
watermark rule. Brief/protocol emphasis fix -- machinery unchanged.

(ii) **Distance invocation (the conditional-guard prong, fixes (b)).** The macro must be invoked
from genuine distance, not adjacency -- several tiles of separation defines more iterations per call
(satisfying `executed_step_count>=3` and `iterations>=2` together, finally producing
qualifying-conditional evidence). Brief/protocol geometry fix -- machinery unchanged.

Neither fix touches the `stop_when` enum, the scorer, the skill guard, or `B_K_CEILING`; nothing
here proposes loosening any pinned constant.

## Honest bounds

- **One attempt, one game.** Per §5.5, this is the single paid attempt authorized under this
  pre-registration; no informal re-run. A second attempt, if pursued, needs its own pre-registration
  (open question flagged in the source doc's §8).
- **Both v3.1 fixes are untested, and (i) is a compliance problem, not a machinery problem.** The
  pre-approach-NEAR instruction already existed in this run's brief (cycle step (i)) and was skipped
  anyway -- a louder brief may or may not change that; only a run shows. (ii) is likewise untested:
  nothing proves a distance-invoked approach reliably reaches `iterations>=2` on real Kirby enemy
  movement (an enemy closing the gap fast could still fire `region_changed` on press 1).
- **The benign PASS and the b_k repair are not proof the macro is robust in general.** Both are one
  session's worth of evidence under one brief, one world, one target configuration.

## Files

- `runs/brain_kirby_v3/` -- verdict run artifacts: `transcript.jsonl`, `world/oracle.jsonl`,
  `world/skills.jsonl`.
- `eval/score_entity_gate_v3.py` -- the pinned v3 scorer used to compute the numbers above.
- `reports/2026-07-03-kirby-skill-port-entity-v3.md` (incl. Amendment A1) -- the pre-registration this
  verdict scores against.
- `reports/2026-07-03-skill-rung1-ab-verdict.md` -- the rung-1 verdict whose NEXT-implications section
  named this port and its conditional-half gap.
