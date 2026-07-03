# 2026-07-03 -- Skill-compilation rung-1 A/B verdict: PASS (2.94x, L2 wall fell)

Verdict for the paid A/B pre-registered in `reports/2026-07-03-skill-compilation-design.md` §4 (the
"skill gate"). Built: `define_skill`/`run_skill` seam tools on `ArcAgi3Session` (PR #89), gated behind
`ARC_SKILLS` for arm isolation (PR #90). Run evidence: `runs/brain_skill_ab_armA/` (baseline),
`runs/brain_skill_ab_armB/` (skill tools). All numbers below verified directly against
`transcript.jsonl` / `world/oracle.jsonl` / `world/skills.jsonl` in both run directories, and against
`eval/score_skill_rung1.py --score-only` for the qualifying-call count.

## The pinned gate, restated verbatim (design doc §4.1)

> **Metric:** `sub_goal_events / (decisions / 100)` -- sub_goal_events = levels_completed... a "turn" =
> one LLM decision (i.e. one `act`/`run_skill` call, NOT one primitive world-step).
>
> **PASS bar:** Arm B's metric `>= 1.3x` Arm A's metric.
>
> **Zero-denominator rule:** if Arm A's primary metric is 0, the ratio is not computed; Arm B PASSes
> only by clearing the absolute floor `levels_completed >= 2`.
>
> **Degenerate-strategy guard:** a QUALIFYING `run_skill` call = logged EXECUTED step count `>= 3`. If
> Arm B's qualifying-call count is 0, the verdict is `INSUFFICIENT_DATA`, not PASS/FAIL.
>
> **`--max-turns`:** 80 per arm, pinned, the only mechanical budget enforcement. Launch order: Arm A
> first; if Arm A's spend exceeds $10, only Arm B's cap may be tightened (never raised), never after
> the fact.
>
> **One attempt per arm**, pinned; a completed arm's result is banked, never informally re-attempted.

## Per-arm numbers (verified against the raw run directories)

| | Arm A (baseline) | Arm B (skill tools) |
|---|---|---|
| `ARC_SKILLS` | off | on |
| Tools available | `act`, `observe`, `remember`, `reset_game` | + `define_skill`, `run_skill` |
| `act` calls | 50 | 18 |
| `run_skill` calls | -- | 16 |
| `define_skill` calls | -- | 15 |
| Decisions (act + run_skill, per §4.1) | 50 | 34 |
| Raw world steps (oracle action rows; step-0 RESET excluded) | 50 (1:1 with decisions) | 130 (18 via `act` + 112 summed `world_steps_used` over the 16 `run_skill` calls) |
| Total tool calls (all types) | 57 | 62 |
| `num_turns` (claude -p) | 58 | 63 |
| `levels_completed` (oracle, max) | 1 / 9 | 2 / 9 |
| Cost | $7.780309 | $8.826826 |
| Exit | success (0), natural completion | success (0), natural completion |

**Qualifying calls** (`executed_step_count >= 3`, the degenerate-strategy guard), from
`eval/score_skill_rung1.py --score-only runs/brain_skill_ab_armB/world/skills.jsonl`:

```
define_skill records:   15
run_skill records:      16
qualifying calls (executed_step_count >= 3): 15
auditable: YES
```

15 of 16 `run_skill` calls qualify. The guard is satisfied -- the mechanism was genuinely exercised,
not primitive-spam wearing a skill-shaped wrapper. `INSUFFICIENT_DATA` does not apply. (Scope note:
what the guard certifies is multi-step execution, not conditional execution -- all 15 qualifying calls
were flat fixed-length lists; see Honest bounds, first bullet.)

## The pinned metric

- Arm A: `levels_completed / (decisions/100)` = `1 / (50/100)` = **2.00**.
- Arm B: `2 / (34/100)` = **5.88**.
- Ratio: `5.88 / 2.00` = **2.94**.
- Bar: `>= 1.3x`.

**2.94 >= 1.3 -> PASS.**

Arm A's primary metric is 1 (not 0), so the zero-denominator rule is not triggered and the ratio is
the governing computation (not the fallback absolute floor). Arm B's `levels_completed = 2` also
clears the pinned absolute floor (`>= 2`) independently, so the result would stand even under the
zero-denominator branch had Arm A come in at 0.

## Verdict

**PASS.** Arm B's task-progress-per-decision metric beats Arm A's by 2.94x, comfortably clearing the
pre-registered 1.3x bar, with the degenerate-strategy guard satisfied (15/16 qualifying calls) and the
launch discipline followed exactly as pinned (Arm A first, Arm A's spend $7.78 < $10 so Arm B's cap
was left untouched, one attempt per arm, `--max-turns 80` both, blank-agent memory wipe in both
launchers, and a seam-validation transcript confirming Arm A could not see the skill tools at all).

This is the first level-2 completion recorded on ARC-AGI-3 wa30 under any framing. Five prior runs (the
three brief-framing runs from `reports/2026-07-04`/`2026-07-05` HANDOFF entries: discovery $6.69,
memory-carrying $8.89, completion-framed $20.82; plus Arm A and Arm B's own baseline arm) all end, or
would have ended, at 1/9 without the skill tools. It is also the first paid-gate PASS for a
*capability mechanism* (as opposed to a grounding/perception gate) since the ADR-002 §9 HUD gate.

## Honest bounds

- **The conditional-loop half of the formalism was never exercised (disclosure, per PR #91 review
  finding 1).** All 15 of Arm B's skill definitions are flat, fixed-length step lists (verified by
  scanning every `define_skill` record in `skills.jsonl` for `repeat_until`/`stop_when`: 0 of 15
  contain either), and all 16 `run_skill` calls ended with the trivial stop reason
  `"all top-level steps executed"` -- no skill ever halted early on a world condition. The design
  doc's §3 called `stop_when` "load-bearing" ("push until the target cells change" instead of
  guessing N exactly); in this run the brain never used it -- it wrote skills like keyboard macros:
  record N keystrokes, replay them. **This PASS therefore validates the BATCHING half of the
  mechanism (multiple primitives per paid decision), NOT the conditional-loop half
  (`repeat_until`/`stop_when`) -- that half remains untested in any paid run**, and exercising it
  should be a stated objective of the next port's gate (the Kirby exposure macro and the doom hunt
  macro both REQUIRE the loop construct, so those ports cannot pass without finally testing it).
- **Guard gap identified (a candidate stricter amendment for the NEXT gate -- a future
  pre-registration note, NOT a retroactive change to this verdict).** The pinned >=3-executed-steps
  qualifying guard was built to catch *short* degenerate calls; it cannot distinguish a conditional,
  condition-checked macro from a hardcoded fixed-length replay (a flat 18-step list qualifies as
  easily as a real loop). This run's guard did exactly what it was pinned to do and the PASS stands
  on it as written; but a future port's gate should consider pinning something like "at least 1
  qualifying call whose `stop_when` fired before max steps" so the conditional half is verified,
  not just permitted. Stricter-only, to be pinned fresh in that port's own pre-registration.
- **The raw world-step asymmetry is the intended causal lever, stated plainly.** Within the same
  80-turn cap, Arm B executed 130 world steps across 34 decisions (~3.8 steps/decision) vs Arm A's
  50 world steps across 50 decisions (1:1) -- 2.6x the raw world steps. That is not a confound; it
  is exactly the mechanism §3 was built to buy (one paid decision, N world steps) and the pinned
  decisions-denominator metric is precisely the pre-registered way of scoring it. The raw counts are
  in the table above so an auditor does not have to reconstruct them from `skills.jsonl`.
- **Same-brief claim, evidenced.** `diff runs/brain_skill_ab_armA/run.sh runs/brain_skill_ab_armB/run.sh`
  shows the two launchers differ only in the arm label (comment lines), the `ARC_SKILLS` export, the
  `LAUNCH` path, and the arm-name entry in a sys.path list -- the brief content itself is identical
  (independently verified by the PR #91 adversarial reviewer as well).
- **One game, one world class, one attempt per arm.** This is a single A/B on a single ARC-AGI-3 game
  (wa30) under one brief framing. There is no variance estimate -- no repeated trials, no
  confidence interval, no test of whether a second Arm-B attempt would also clear 1.3x. The pinned
  design (one-attempt-per-arm, banked on completion) trades variance information for cost and
  pre-registration cleanliness; that trade is a known, accepted limitation, not an oversight.
- **The milestone fallback (M1-M7) was not needed.** Both arms produced a clean levels_completed
  signal (1 vs 2, no tie), so the pinned fallback metric and its corroboration/watermark/dedupe
  machinery were never invoked. It remains untested as a mechanism in this run.
- **Decision-definition sensitivity, noted honestly.** The pinned decision unit is `act + run_skill`
  calls (34 for Arm B), which is the number the gate's own metric is built on and the number that
  produces the 2.94x PASS. A robustness check using ALL tool calls as the denominator (including
  `remember`, `observe`, `ToolSearch` -- 57 for Arm A, 62 for Arm B) gives Arm A = 1.75, Arm B = 3.23,
  ratio = **1.84x** -- still clears the 1.3x bar under this alternative accounting, so the PASS is not
  an artifact of exactly which calls count as "decisions." This robustness figure is non-pinned
  (informational only, computed after the pinned metric, never substituted for it).
- **Cost, not just levels, moved.** Arm B cost $1.05 more than Arm A ($8.83 vs $7.78, +13%) for double
  the levels at fewer decisions -- the mechanism bought more progress per decision, not per dollar
  directly, though the two are correlated (fewer decisions per level tends to mean fewer tokens
  overall; the $1.05 delta is well inside the run-to-run cost variance already observed across the
  three prior wa30 framings, $6.69/$8.89/$20.82).
- **The brain's own accounting is corroborating, not just the oracle.** Arm B's final summary
  independently describes solving level 1 (3-slot container), level 2 (6-slot container, "routing
  around already-filled slots that act as walls"), and mapping level 3 (partially, budget-exhausted)
  -- consistent with the oracle's `levels_completed: 2` at the final logged step and with 15
  `define_skill` calls plus 16 `run_skill` calls appearing in the transcript at the points the summary
  describes using push/drag macros.

## NEXT implications

- **Ports to other worlds, per the design doc's later rungs.** Rung 1 shipped exactly one executor
  (`ArcAgi3Session`); what this PASS validates is the batching half of the mechanism (flat multi-step
  skills, verbatim logging, one decision = N world steps) -- enough to justify the two ports the
  design doc names as illustrations, not deliverables: the Kirby entity-v3 exposure-control macro
  (`approach k tiles, retreat k tiles` via `repeat_until`) and the GATE-3D doom scan-and-center hunt
  macro (`repeat_until(turn_left, stop_when="mover_visible")`). Both port macros REQUIRE the
  conditional-loop construct this run never exercised (Honest bounds, first bullet), so each port's
  gate should explicitly require the loop half to fire -- the ports are where that half finally gets
  tested. Each port pins its own `stop_when` enum from that world's own wire data in its own build
  PR -- nothing here pre-approves a specific enum for either world.
- **Feeds the continuous-time lane.** The MKDS probe (same day, `runs/nds3d_probe/FINDINGS.md`)
  measured a world that changes every frame with zero player input (idle mean 12.22%, accelerating
  mean 33.23%) -- the opposite of ARC's and GB's turn-based idle assumption. A `stop_when` predicate
  keyed on a continuous-time signal (e.g. "N frames elapsed" or a threshold-crossing diff) is a
  plausible bridge between rung 1's discrete-step formalism and a continuous-time world, but this is
  flagged as an open design question for whichever session tackles the MKDS/continuous-time doc next,
  not resolved or pre-designed here.
- **No promotion triggered.** Per the design doc's non-goals (§6), this PASS does not itself write
  anything to a world-side skill library (design-space (ii)) or mine transcripts for cross-run
  promotion (design-space (iii)). It is evidence that rung 1's mechanism works, which is the
  precondition §2 named before either later rung is worth starting -- it does not by itself authorize
  building them.

## Files

- `runs/brain_skill_ab_armA/` -- Arm A (baseline) run artifacts: `transcript.jsonl`, `world/oracle.jsonl`.
- `runs/brain_skill_ab_armB/` -- Arm B (skill tools) run artifacts: `transcript.jsonl`,
  `world/oracle.jsonl`, `world/skills.jsonl`.
- `eval/score_skill_rung1.py` -- the pinned §4.0 free pre-check + `--score-only` auditability scorer
  used above to compute the qualifying-call count.
- `reports/2026-07-03-skill-compilation-design.md` -- the design doc + pre-registered gate this verdict
  scores against.
