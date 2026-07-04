---
name: cheapness-skill-compilation
description: The "Cheap" North Star claim (#4) and its mechanism — the System-1/System-2 split and how a System-2 routine is compiled into a promoted System-1 reflex ONLY on held-out proof. Invoke when advancing the cost axis, designing/porting skill tools, or explaining why the agent gets cheaper as it learns.
---

# Cheapness via System-2 → System-1 skill compilation

The fourth North Star claim. This skill explains the framework, the promotion gate, and the invariant
that guards it — so a junior can advance the "cheap" axis without re-deriving it. For gate mechanics
(pre-register → one attempt → banked verdict) see the **gate-methodology** skill; this skill is the
*why* and the *what*, that one is the *how you run it*.

## 1. The claim (do not paraphrase-drift it)

Claim #4 of the four North Star claims, pinned in `HANDOFF.md` §1 (line ~437) and the **session-start**
skill:

> **Cheap.** Free fast System 1 does routine work; the costly System 2 (LLM) wakes only at decisions.
> **Measured as cost/task and wakes/task, held low.** (`HANDOFF.md` §1 claim 4, verbatim.)

Those two metrics — **cost/task** and **wakes/task** — are the numbers this axis holds low. A "wake"
= one LLM decision. In the harness a wake is counted as `self.decisions` (`world_mcp.py` ~line 765,
commented: "your LLM wakes (press/goto/explore) — the cost the north star keeps LOW"). The claim is
FALSIFIED if constancy is bought by needing a new hand-written System-1 per genre (`HANDOFF.md` §1
"Falsified if"); a general cheap agent, not a pile of per-game controllers.

## 2. The System-1 / System-2 split (already embodied, then generalized)

Cost is not "call the LLM less" — it is a **division of labor** (`reports/INSIGHTS.md` §5):

- **System 2 (the LLM):** slow, expensive, general. Sets *intent*. Wakes only at genuine decisions.
- **System 1 (the harness):** fast, free, narrow. *Executes* routine work with no LLM call.

Two places already do this (INSIGHTS §5):
- **Navigation:** LLM names a target (`GOTO: x y`); a free autopilot BFS-pathfinds there; the brain is
  re-woken only when the autopilot is **stuck**. "One decision walks many tiles for free."
- **Dialog:** plain text is auto-advanced for free (press A); the LLM is woken only at real **choices**.

The forward idea (INSIGHTS §6, "System 2 → System 1: skill compilation" / cognitive *production
compilation*): "wake at decisions" is today **static** (wake at every menu). It should become
**adaptive** — the wake rate should *drop as the agent learns the game*, not stay flat. You do not beat
a 10,000-step game with 10,000 LLM calls. The pattern:
1. First few times a situation recurs, System 2 deliberates step-by-step.
2. From those decisions a reusable **routine** is distilled.
3. A cheap System-1 executor runs it, one decision = N world steps.
4. System 2 re-wakes only on **novelty** (the routine is out of its depth).

## 3. Skill compilation = discover in System 2, promote to System 1 — ONLY on held-out proof

A "skill" is a compiled routine. The design surveys three lifetimes it can live in
(`reports/2026-07-03-skill-compilation-design.md` §2):

| Design-space | Lifetime | Status |
|---|---|---|
| **(i)** Brief-carried macros — brain writes `define_skill`/`run_skill` THIS RUN, they die at run end | within-run, discarded | **Built (rung 1).** Lowest risk; only rung with a validated mechanism precedent (the glyph cache) |
| **(ii)** World-side library — hand-audited, versioned macros exposed as seam tools across runs | cross-run, human-curated | The promotion target. NOT built — revisit only after rung 1 shows WHICH macros are worth curating |
| **(iii)** Harness-side compilation — transcripts mined offline, promoted via PR + gate | cross-run, from mined runs | The promotion *path*. Strictly downstream of (i); nothing to mine without transcripts |

**The compilation arc: System-2 discovers a routine (i) → a human promotes it into a System-1 library
(ii) via a reviewed PR + a held-out gate (iii). NEVER auto-promoted. NEVER from across-run training.**
This is not optional discipline — it is forced by the invariant in §4.

## 4. The invariant that guards it — the learning-boundary law

Pinned in `reports/INSIGHTS.md` §7 and the session-start skill:

> No across-run training — **the agent starts blank each run**; skills are promoted to the library only
> on **held-out proof**.

- **Across-run learning = harness/code updates ONLY.** The only way knowledge crosses runs is a
  *developer* changing the harness (perception, brains, detectors, or a **promoted** policy compiled
  into code). aria's persistent memory is archived + wiped before each run.
- **Within-run learning lives in the harness and is discarded at run end:** the `LESSON:` buffer,
  `OutcomeMemory`, the disconfirm detector — and rung-1 skills. Design-space (i) "slots exactly here"
  (INSIGHTS §7): a compiled skill is within-run, harness-owned, dead at run end → law-compliant.
  OPEN QUESTION (not settled law): whether a segmented multi-session chain counts as ONE run for
  this law — the **long-horizon-runs** ferry design argues yes, but that reading is untested and is
  David's to ratify at the pilot's pre-registration. Until then, "run" here means one `claude -p`
  invocation.
- **Promotion is the ONLY across-run channel, and it is gated** (plan → branch → Sonnet → PR →
  adversarial review → held-out gate → **David merges**). A skill that *seems* to generalize is a
  *candidate* for hand-curation into (ii), never mechanically carried forward
  (`...design.md` §6 non-goals: "No auto-promotion", "No cross-run persistence").

Why so strict: auto-promoting a brain-authored routine into harness code would smuggle un-audited,
LLM-authored behavior across the boundary — the same concern the persona/identity law exists to prevent
(see the **safety-invariants** skill, §3). Held-out proof (a fresh pre-registered gate, §5) is what
earns the promotion; a good-looking run does not.

## 5. The rung-1 result — the worked proof

The A/B gate pre-registered in `...design.md` §4, scored in
`reports/2026-07-03-skill-rung1-ab-verdict.md`. Built: `define_skill`/`run_skill` seam tools on
`ArcAgi3Session` (PR #89), arm-isolated behind the `ARC_SKILLS` env flag (PR #90, default OFF); #86 is
the design PR that opens the #86–#90 series, not a build PR (per the verdict).
Instrument: ARC-AGI-3 wa30 (cheapest in the fleet; external un-tunable ARC scorecard).

**What was measured — task progress per paid decision** (a "decision" = one `act`/`run_skill` call, NOT
one world-step):

| | Arm A (baseline) | Arm B (skill tools) |
|---|---|---|
| Tools | `act`,`observe`,`remember`,`reset_game` | + `define_skill`,`run_skill` |
| Decisions (`act`+`run_skill`) | 50 | 34 |
| Raw world steps | 50 (1:1) | 130 (~3.8/decision) |
| `levels_completed` (oracle) | **1 / 9** | **2 / 9** |
| Cost | $7.78 | $8.83 |

- Metric `levels_completed / (decisions/100)`: Arm A = `1/(50/100)` = **2.00**; Arm B = `2/(34/100)` =
  **5.88**. Ratio = **5.88 / 2.00 = 2.94**.
- Pinned PASS bar: **≥ 1.3x**. `2.94 ≥ 1.3` → **PASS.**
- Degenerate-strategy guard (a qualifying `run_skill` = logged `executed_step_count ≥ 3`): **15 of 16**
  calls qualified → guard satisfied, not `INSUFFICIENT_DATA`.

This is the **first level-2 completion on wa30 under any framing** — the L2 wall, unbroken across five
prior runs (three brief-framings $6.69/$8.89/$20.82 + both A/B baseline arms), FELL. HANDOFF's own
diagnosis had been "the boundary is multi-step spatial-planning depth, not perception" — a compiled push
macro turned "push this block toward that container" from N decisions into 1, multiplying how many
sub-goals fit in the same `--max-turns` budget. **The capability lever and the cost lever are the same
lever** (`skill-compilation-gate-pass.md`).

**Honest bound you MUST carry forward (verdict "Honest bounds", 1st bullet):** all 15 skills were flat
fixed-length step lists — `repeat_until`/`stop_when` never fired (0/15). **This PASS validates the
BATCHING half only (N primitives per decision), NOT the conditional-loop half.** The loop half is
untested in any paid run. The two named next ports (Kirby exposure-control macro `approach k / retreat
k`; doom scan-and-center `repeat_until(turn_left, stop_when="mover_visible")`) both REQUIRE the loop
construct — so each port's gate must explicitly require the loop half to fire. (The Kirby port has SINCE
shipped and run `repeat_until` in a paid run (`runs/brain_kirby_v3_1`), but every loop there fired a bare
`steps_elapsed` counter — the *conditional* (world-state-branching) half still has NOT passed a gate; see
**diagnose-a-run**'s worked example.) One game, one attempt per arm, no variance estimate (accepted trade
for cost + pre-registration cleanliness).

## 6. `define_skill` / `run_skill` — the mechanics a brain uses in a run

World-side seam tools (live next to `remember`/`observe` in `world_mcp.py`, NOT in `core/` brain code —
**no brain edits, ever**, per the constancy law; see **safety-invariants** §7). Rung 1 shipped ONE
executor: the `ArcAgi3Session` port (`...design.md` §3, §6); the Kirby port has since landed as a second
per-world executor (its own `_define_skill`/`_run_skill` at `world_mcp.py:1018`/`:1155`, gated behind
`KIRBY_SKILLS=1`, exercised by `runs/brain_kirby_v3_1`) per the gate-first plan — never a multi-world generic one.

- **`define_skill(name, steps, stop_when)`** — `steps` is a list of EXISTING world primitives (for ARC:
  `act` payloads like `{"action":"ACTION1"}`). Definitions are logged verbatim to the transcript at
  creation (auditable). No step can do anything a primitive call couldn't.
- **`repeat_until(steps, stop_when, max_iters)`** — the ONE bounded loop construct. `max_iters`
  schema-capped at **8**, **no nesting**, absolute ceiling **50 world steps per `run_skill` call**.
  Terminates by construction; executed iteration count logged.
- **`run_skill(name, args)`** — executes the steps against the live world, checks `stop_when` after each
  step, returns early with the reason if it fires. Returns ONE `observe`-shaped result — **one LLM
  decision, N world steps.**
- **`stop_when`** is a small closed **PER-WORLD** enum of cheap predicates computed WORLD-SIDE from data
  already on that world's wire. Pinned for ARC (rung 1): `grid_changed_in_region(x0,y0,x1,y1)`,
  `grid_unchanged_for(k)` (k≤8), `steps_elapsed(n)` (n≤50). **Never an oracle/RAM/score field** — the
  no-new-channel claim holds because each is a diff/counter over grids `observe` already returns.
- Skills are **discarded at run end** — same lifetime as `remember()` lessons and the glyph cache.

**Porting to a new world (per the design's later rungs, gate-first):** each world is its OWN build PR
that pins its OWN `stop_when` enum from that world's wire — never a multi-world generic executor
(`skill-compilation-gate-pass.md` "How to apply"). Gate the arm behind an env flag, default OFF; the A/B
arm isolation MUST be seam-validated (`tools/list` shows the baseline arm cannot see the skill tools)
before any paid arm launches. Run the paid A/B via the **gate-methodology** discipline (pre-register the
bar and guards, one attempt per arm, bank the verdict as-is) and the **paid-run-harness** laws
(account-B, blank-agent wipe, oracle off the wire).

## 7. Non-negotiables (rung-1 non-goals — do not cross without a fresh design + PR)

`...design.md` §6:
- **No cross-run persistence** — every skill dies at run end.
- **No auto-promotion** — nothing in a run writes to `core/` or `games/`; promotion to (ii) is a
  separate human-reviewed design + PR + held-out gate.
- **No learned policies** — `stop_when` is a fixed closed enum, evaluated exactly, never fit/trained.
- **No reward-driven anything** — no skill is scored/reinforced/selected by an oracle or score signal at
  runtime; the no-leak law stands. The gate evaluates the mechanism *offline, from logs, after the fact.*

## Sources

- `reports/2026-07-03-skill-compilation-design.md` (design-space (i)/(ii)/(iii); §3 mechanism; §4 pinned gate; §6 non-goals)
- `reports/2026-07-03-skill-rung1-ab-verdict.md` (PASS 2.94x; per-arm numbers; batching-vs-loop honest bound)
- `reports/INSIGHTS.md` §5 (division of labor), §6 (System-2→System-1 compilation), §7 (learning-boundary law)
- `HANDOFF.md` §1 (the four claims; claim 4 "Cheap"; "Falsified if")
- `world_mcp.py` (~line 765 `self.decisions` = wakes; `define_skill`/`run_skill`/`ARC_SKILLS` on `ArcAgi3Session`)
- `C:/Users/Succe/.claude/projects/E--AI-Personas-10-pokemon-and-chess-and-office/memory/skill-compilation-gate-pass.md`
- Cross-refs: skills `gate-methodology`, `paid-run-harness`, `safety-invariants` (§3 identity law, §7 no-brain-edits), `session-start` (the four claims)
