# MKDS skill-compilation A/B v2 — design response to the banked v1 FAIL

**Status: DRAFT — FOR DAVID / NOT AUTHORIZED.** Docs only, $0 spent, nothing run. This document is the
required pre-spend escalation per **gate-methodology**; the decision to spend again (or not) is
David's/the orchestrator's, not this document's.

**Recommendation up front (detail in §4): (e) — bank the v1 FAIL, do not design a v2 re-run of this
instrument.** A careful re-check of the raw artifacts (not just the banked verdict's prose) shows the
confound goes deeper than the verdict said, and none of (a)–(d) fixes it without either cheating the
comparison or requiring a perception climb this rung explicitly walled off. §5 corrects a claim in the
task briefing about the conditional-loop half — it turns out to be half-true, and the true half matters
for this recommendation.

## 1. What v1 actually measured vs. what it intended to measure

**Intended** (`reports/2026-07-04-mkds-continuous-time-build-plan.md` §7, `reports/2026-07-04-continuous-time-stopwhen-design.md`
§9): whether `define_skill`/`run_skill`'s `repeat_until`+`stop_when` apparatus gives **≥1.3x world-frames
per decision** over a no-skill-tools baseline on a continuous-time world, with a guard that the
mechanism's *conditional* half (a `stop_when` that fires from world state, not a ceiling timeout) gets
exercised at least once.

**What it actually measured**, verified against the raw on-disk artifacts (`runs/brain_mkds_armA_default/world/oracle.jsonl`,
`runs/brain_mkds_armB_default/world/skills.jsonl` in the primary checkout — gitignored, cited as
evidence, not reproduced here):

- Arm A was never a "no batching" baseline. `press_sequence` is a universal, always-on primitive on
  *every* button-driven world (`_make_press_tools`, `world_mcp.py:331-357`; same tool spec re-exported
  by `core/perception_plugin.py:147-154`) — it is not something introduced for this gate. Arm A's last 8
  of its 13 in-world decisions each called `press_sequence` with 12 `"a"` presses
  (`oracle.jsonl` steps 8-15, `"action": "a+a+a+a+a+a+a+a+a+a+a+a"`), and each such call advanced exactly
  **288 frames** (frame deltas 740→1028, 1028→1316, … all +288). That is `12 × 24` — `perception_plugin.py:174`
  hardcodes `hold=8` per press in a sequence, and the NDS press primitive settles for
  `hold_frames + settle_frames = 8 + 16 = 24` frames per press (`core/nds_emulator.py:74`, cited by the
  stopwhen design §2).
- Arm B's biggest, most-used skill (`"drive"`: `repeat_until(steps=[{button:a, hold_frames:40}],
  stop_when="elapsed_frames(280)", max_iters=8)`) advanced **280 frames per call** (5 iterations × 56
  frames each — `hold_frames=40` + the same 16-frame settle), confirmed verbatim from
  `runs/brain_mkds_armB_default/world/skills.jsonl` steps 2-5, 7-10 (8 of Arm B's 10 `run_skill` calls).
- **The two "batching" primitives are throughput-matched almost by construction.** `press_sequence`'s
  schema cap is `maxItems: 16` (`world_mcp.py:347`, `perception_plugin.py:151`) — at the same 24
  frames/press, its theoretical ceiling is `16 × 24 = 384` frames per call, which is *higher* than
  `run_skill`'s absolute frame ceiling `F = 300` (`_NDS_SKILL_MAX_WORLD_FRAMES`, `world_mcp.py:775`).
  Observed: Arm A 288f/call, Arm B 280f/call — both close to their own per-call ceilings, and close to
  each other. The 1.03x result is not a near-miss fluke; it is what you get when you race two batchers
  whose caps are the same order of magnitude.
- So v1 measured: *"does a skill-compilation batching primitive out-batch an already-available dumb
  batching primitive, by raw frames/decision, on this task?"* — no, essentially a tie. It did **not**
  cleanly measure *"is the loop's conditional branching valuable?"*, for two independent reasons: (i) the
  raw-frames/decision metric does not care whether a `stop_when` fired for a genuine world-state reason
  or a disguised fixed counter, and (ii) in the one paid attempt, the only genuinely world-state-branching
  predicate available (`idle_settled`) never actually fired (§5).

The banked verdict's own diagnosis ("Arm A had `press_sequence` available and used it heavily... That
made the baseline already batch") is correct as far as it goes. What it did not say, and what the raw
numbers above add: the two batchers are cap-matched almost exactly, so no amount of "using `press_sequence`
a bit less" would have produced a different qualitative outcome — the confound is structural, not a
one-off usage pattern.

## 2. Options, evaluated

### (a) Remove `press_sequence` from Arm A — **REJECT, this is the dangerous option, and it is dangerous**

Verdict: **strawman, not a control.** Take the position squarely: a no-`press_sequence` Arm A is not an
apples-to-apples isolation of the skill mechanism — it manufactures a mechanically guaranteed win that
proves nothing new.

Reasoning: `press_sequence` was never added *for* this gate — it is the baseline capability every world's
Arm A has always had, on every prior press-based A/B this project has run (there is no precedent anywhere
in this project's history of *removing* an existing tool from a baseline arm to widen a gap; the closest
analogue, ARC-AGI-3 rung-1, had a clean baseline *because ARC's action space never had a batching
primitive to begin with* — `act` is one grid-step, period. Nothing was removed there; it simply never
existed). Stripping `press_sequence` here would put Arm A down to one 24-frame press per decision against
Arm B's up-to-300-frame `run_skill` ceiling — a >12x ceiling-to-ceiling gap that guarantees a PASS
independent of whether `stop_when` ever branches on anything. That is the same *class* of error as
loosening a numeric bar: instead of loosening the passing threshold, it weakens the opponent until any
threshold clears. It would answer "is having *some* way to batch better than having *none*?" — a question
nobody is asking, since `press_sequence` itself already answers it trivially without any skill machinery.
It would not tell us anything about whether `stop_when`'s conditional apparatus is the thing worth the
extra tool-surface complexity. **Do not do this**, and the same critique kills any softened variant (e.g.
"just lower `press_sequence`'s cap this once") — it is still post-hoc weakening of an existing capability
to manufacture a result.

### (b) Change the metric — **insufficient alone, but the wake-accounting worry does not apply here**

Checked the specific concern in the brief: the project's DEFERRED wake-accounting problem
(`cheapness-skill-compilation` §1's Gate-0 caveat) is scoped to **Codex's** JSONL stream, which has no
per-model-decision observable. The MKDS path is `claude -p` over the NDS `World`/`Gateway`, and every
tool call that moves the world is already logged explicitly and distinctly in `skills.jsonl`
(`define_skill`/`run_skill` events) and `oracle.jsonl` (per-step `press_button`/`press_sequence`
actions) — "in-world decisions" in the banked verdict's table is already the *correct*, directly-
observable wake count, not a proxy. **The deferred wake problem does not apply to this path.** A
decisions-to-milestone metric is measurable here without new instrumentation for wake-counting.

But it does not fix the actual problem. Swapping "world-frames/decision" for, say, "decisions to reach
checkpoint N" (using the offline-verified but never-wired progress oracle `0x022C8090`/`0x022C8094`,
`reports/2026-07-11-mkds-oracle-hunt.md`, hardened `reports/2026-07-23-oracle-mkds-lap.md`) still races
the same two batchers against the same near-identical per-call ceilings (§1). Both arms would still reach
a fixed checkpoint in a similar number of decisions, for the same structural reason. A better-grounded
metric (real task progress instead of a frame-count proxy) is a good idea on its own merits, and if this
lane is ever reopened, wiring that oracle into `GAMES["nds"]["watch"]` (an additive, off-the-wire change,
mirroring every other world's `watch` dict, `world_mcp.py:997`) would be a fair prerequisite — but it is
not, by itself, a fix for this FAIL.

### (c) Change the task so fixed batching cannot substitute — **correctly diagnosed, not cheaply buildable now**

This is the right instinct: if the correct policy must *branch* on world state, a fixed-length primitive
(`press_sequence` or a `elapsed_frames`-gated skill body) is structurally insufficient, and only a
genuinely state-dependent `stop_when` could win. Two pieces of on-file evidence cut against an *easy*
version of this being available today, and I engaged with both rather than waving them off:

- **The f3 latency-window finding is direct counter-evidence for the early track.**
  `reports/2026-07-23-f3-latency-window.md` measured that a **fixed, open-loop** policy — accelerate +
  half-strength LEFT pulse, chosen once, never adjusted — clears turn 1 and holds top speed with **no
  ruin for >500 frames (>8.4s)**, on the exact savestate/task the v1 A/B used. That is a fixed reflex
  *out-surviving* the entire task horizon the v1 gate cared about ("reach lap 1 / first checkpoint"). If
  a hand-picked constant policy doesn't ruin, there is no forcing function requiring Arm B's branching —
  Arm A (with `press_sequence`, or even a dumber fixed skill) can just encode that same constant bias and
  win on batching alone, exactly as v1 showed.
- **But the oracle-hunt sessions found the opposite further down the track.** Blind, fixed throttle
  "wedges the kart against the wall indefinitely" past the first bend (`reports/2026-07-11-mkds-oracle-
  hunt.md`); getting past the figure-8 crossing and several more curves required an actively vision-
  guided, per-frame-adjusted steering loop (`reports/2026-07-23-oracle-mkds-lap.md`). So genuine
  branching necessity plausibly *does* exist later on this track — just not in the segment v1 tested.

The catch: **the current predicate enum cannot express what that later segment needs.** `elapsed_frames`
is a pure counter (never branches). `idle_settled` is a transition detector (fires on "the screen stopped
changing"), not a steering signal. Neither can express "turn left here, right there, depending on track
curvature" — that needs the foveated `region_*`/minimap-heading primitive, which
`reports/2026-07-04-continuous-time-stopwhen-design.md` §3 explicitly **defers to the 3D-perception
climb** and keeps out of this rung on purpose ("deliberately excludes... so the honest gate is a
batching-benefit bar... Tasks needing `region_*` are out of scope until 3D perception ships"). Building
that primitive is a perception project (rotating non-tile minimap, broken glyph cache — the same breaks
`FINDINGS.md` and `world-lanes-frontier` already flag as open), not an A/B redesign. It is a bigger,
riskier, differently-scoped piece of work than a $1.55 re-run.

**Verdict: (c) correctly identifies what's missing (a task where branching is load-bearing), but that
task is not reachable with today's perception-free predicate enum.** Pursuing it means opening the
3D-perception climb, not writing a v2 pre-registration.

### (d) Move the A/B to a different world — **directionally right, but it's a different, already-queued project, not a v2**

The one place in the roadmap where a *genuinely* branching, non-batching-prone predicate already exists
in design (not perception-free pixel magnitude, but a semantic one) is VizDoom's planned **scan-and-center
macro**: `repeat_until(turn_left, stop_when="mover_visible")` (`cheapness-skill-compilation` §5,
`world-lanes-frontier`). `mover_visible` genuinely depends on *what* is on screen, not a frame count or a
pixel-delta magnitude — a fixed-length turn sequence cannot reliably substitute for "keep turning until
you see something," which is exactly the shape (c) is looking for.

But per `world-lanes-frontier`'s own frontier table, this is **not spend-ready**: VizDoom's lane is
currently sitting on a banked GATE-3D **FAIL** (K=4.074 vs bar 5.61), with its own pinned next step being
brief/tolerance tightening and a re-run of *that* gate — the scan-and-center skill port is queued
*behind* that, and has never been built. Moving the MKDS budget there is not "redesign the MKDS A/B
differently" — it is "fund a different, larger, already-sequenced project item that happens to be a
better instrument for the conditional-loop claim." Worth doing, on its own timeline, not as a MKDS v2.

### (e) Accept the v1 FAIL as the lane's honest answer — **RECOMMENDED**

On this world, with this predicate enum, against a baseline that has always had (and will continue to
have) `press_sequence`: **open-loop fixed-length batching is genuinely competitive with skill-compilation
batching**, because both are bounded by similar per-call ceilings and the task doesn't (yet, provably)
require branching. That is a real, informative, bankable result — not a null result to paper over. See
§4 for what the money should buy instead.

## 3. (Not produced) — no v2 pre-registration

Per gate-methodology §1, a full pre-registration + v3 escalation ladder is required *if this document
recommends a v2 run*. It does not (§4 is (e), not a new attempt), so none is written. Producing one here
would be exactly the "reflexively design a re-run" the brief warned against. §5 below lists the two
concrete preconditions that would have to become true before this lane is worth reopening; that is not
an authorized escalation ladder, just an honest note of what's missing.

## 4. Recommendation: (e). What the money should buy instead

**(e), plainly: bank the FAIL, do not spend again on this instrument.** Reasoning in one paragraph: v1's
FAIL is not a measurement-surface bug to patch — the surface is honest, and every fix I can construct
either (a) cheats the baseline into a guaranteed win (rejected outright, same error class as bar-
loosening), (b) changes the metric formula without changing the structural fact that both arms can batch
to similar per-call ceilings, (c) needs a task segment that plausibly exists but is unreachable with the
perception-free predicate enum this rung deliberately shipped, or (d) is actually a different, larger,
already-queued project (VizDoom scan-and-center) mislabeled as "MKDS v2." None of these is a legitimate
$1.55-class fix. The instrument has hit its honest ceiling.

What the ~$1.55-and-up budget should buy instead, in priority order per the project's *own* existing
roadmap (not invented here):

1. **VizDoom brief/tolerance tightening**, already `world-lanes-frontier`'s pinned next step ahead of the
   scan-and-center port, and already ahead of any MKDS work in HANDOFF's `⇒ NEXT` ordering logic. This is
   the path that eventually gets a *fair* shot at the conditional-loop claim, because `mover_visible` is
   not vulnerable to the batching-parity problem MKDS hit.
2. **A $0 offline probe, before any future MKDS conditional-half attempt of any kind**: does `idle_settled`
   (or a successor predicate) fire reliably on *any* reachable, perception-free MKDS transition during
   real gameplay — not just the deterministic count-in? §5 explains why this is now a live open question,
   not a settled one. This is cheap due diligence that would have caught the "coast never fires" problem
   (§5) before the $1.55 was spent, and should gate any future attempt on this world specifically.
3. Otherwise, let David re-prioritize per HANDOFF's own `⇒ NEXT` list — this document does not pick the
   next spend, per `world-lanes-frontier`'s own stated division of labor ("the lane-priority question is
   David's when it involves spend").

## 5. Correcting the "conditional-loop half never fired" claim — verify, and the receipt

The task briefing states the v1 result "FALSIFIES the widely-repeated project claim that 'the conditional-
loop half has never fired in a paid run.'" I verified this against the raw file, not the verdict's
summary, and the honest answer is **half right, and the missed half changes what it means for this
design.**

The exact phrase being referenced traces to the ARC-AGI-3 rung-1 result specifically
(`world-lanes-frontier`: "Honest bound: only the BATCHING half validated; the conditional-loop half has
never fired in a paid run" — 0/15 `run_skill` calls in that gate used a genuine loop construct at all).

**Literal/mechanical reading — CONFIRMED FALSIFIED.** `runs/brain_mkds_armB_default/world/skills.jsonl`
(quoted verbatim, not paraphrased):

```
{"event": "run_skill", "step": 1, "name": "launch", ...,
 "stop_reason": "stop_when 'elapsed_frames(90)' fired after 93 frame(s) (3 iteration(s))",
 "world_frames_used": 93, "stop_when_fired": true}
{"event": "run_skill", "step": 2, "name": "drive", ...,
 "stop_reason": "stop_when 'elapsed_frames(280)' fired after 280 frame(s) (5 iteration(s))",
 "world_frames_used": 280, "stop_when_fired": true}
```
(steps 3, 4, 5, 7, 8, 9, 10 repeat the same `drive`/`elapsed_frames(280)` pattern — **9 of 10** `run_skill`
calls have `stop_when_fired: true`, matching the banked verdict's count exactly.) A `repeat_until` loop
absolutely did return early via its `stop_when`, 9 times, in a paid run. As a claim about "has a
`repeat_until`/`stop_when` loop ever returned before its ceiling," **this is false — it is falsified, with
a receipt.**

**But the deeper reading — "has a genuinely world-state-branching predicate ever fired" — is NOT
falsified, and the same file shows why.** All 9 firings above are `elapsed_frames(n)`: a pure, monotonic
frame counter with **no dependence on anything happening on screen**. This is structurally identical to
`steps_elapsed(n)`, which the project's own entity-gate lineage explicitly disqualifies as conditional
evidence for exactly this reason (`gate-methodology` gotcha #3: "`steps_elapsed(n)` loops do NOT count as
conditional evidence by design — a pure step-count loop never branches on world state"). `elapsed_frames`
is `steps_elapsed`'s time-unit twin (`continuous-time-stopwhen-design.md` §8's own reuse table: "Rethink →
`elapsed_frames(n)` (world-time)"); the same disqualification applies by the same logic. Every one of the
9 "conditional" firings is a fixed-length hold dressed as a `repeat_until` for budget bookkeeping — not a
branch.

The one call that *was* a genuinely world-state-branching predicate is right there in the same file, and
it is the one that **did not fire**:

```
{"event": "define_skill", "step": 6, "definition": {"name": "coast", "steps": [{"repeat_until":
 {"steps": [{"button": "none", "hold_frames": 4}], "stop_when": "idle_settled(0.012, 4)", "max_iters": 8}}]}}
{"event": "run_skill", "step": 6, "name": "coast", ...,
 "stop_reason": "repeat_until reached max_iters=8 without stop_when firing",
 "world_frames_used": 32, "stop_when_fired": false}
```

`idle_settled` — the one predicate in this world's enum that actually depends on what's on screen — burned
to its `max_iters=8` ceiling (32 sampled frames) without ever seeing 4 consecutive under-threshold samples,
and was abandoned; every subsequent call reverted to `drive`/`elapsed_frames`.

**Net correction:** the v1 result falsifies the *literal* claim ("a loop has never returned early") but
leaves the *substantive* claim ("a genuinely branching predicate has never fired") standing, and now with
one more data point supporting it: Kirby v3.1 (`steps_elapsed` only, per `cheapness-skill-compilation`
§5), ARC rung-1 (0/15 loop constructs at all), and now MKDS v1 (`elapsed_frames` only; the one
`idle_settled` attempt missed). **Zero paid runs across the whole project, to date, have had a
world-state-branching `stop_when` predicate actually fire.** This is the honest bound to carry forward,
and it is a stronger, more specific claim than either "never fired" or "now falsified" — it directly
informs §2(c) and §4: the conditional half's live-fire proof is still zero-for-N, and this design does not
manufacture a false positive by counting a disguised counter as a branch.

**Aside, verifying a smaller claim in the task briefing:** the build plan's §4 table (`s=24, k=10`) is
indeed stale versus the shipped code (`s=4`, `world_mcp.py:793`, with the arithmetic error explained
inline in a code comment at `world_mcp.py:777-792`) — but this is **already known and already corrected**
in `HANDOFF.md`, not a new finding. The briefing's line pointer (`HANDOFF.md:636`) is stale (line numbers
drift as the file grows); the actual note is currently at `HANDOFF.md:587`: *"plan doc §4's s=24/k=10 is
STALE — code pins s=4, world_mcp.py:749"* (that cited line number has also drifted since; the constant
is at `world_mcp.py:793` in the current tree). No action needed — flagging only because the task asked me
to verify every claim against `main`, and this one checks out with a minor stale-pointer correction.

## Sources (every claim above checked against the file cited, not memory)

- `reports/2026-07-13-mkds-ab-verdict.md` — the banked FAIL, run facts, Arm B conditional-evidence table.
- `reports/2026-07-04-mkds-continuous-time-build-plan.md` — v1 build/pre-reg, §4 pinned constants (with
  the stale s=24/k=10 vs shipped s=4 noted above).
- `reports/2026-07-04-continuous-time-stopwhen-design.md` — the stop_when bridge; §2 budget split; §3
  predicate family + why `region_*` is deferred; §7 degenerate guards; §8 reuse/rethink table.
- `reports/2026-07-23-f3-latency-window.md` — fixed open-loop policy survives turn 1 for >500 frames.
- `reports/2026-07-11-mkds-oracle-hunt.md`, `reports/2026-07-23-oracle-mkds-lap.md` — progress-oracle
  hunt; vision-guided steering needed past the first bend; oracle never wired into `GAMES["nds"]["watch"]`.
- `reports/2026-07-13-mkds-ab-blocked.md` — the earlier account-cap block (context only).
- `.claude/skills/cheapness-skill-compilation/SKILL.md`, `.claude/skills/gate-methodology/SKILL.md`,
  `.claude/skills/world-lanes-frontier/SKILL.md` — the Cheap claim, gate discipline (incl. gotcha #3 on
  `steps_elapsed` non-conditionality), and the per-lane frontier state (VizDoom queue order).
- `world_mcp.py` — `_make_press_tools` (`:331-357`), NDS skill port block (`:760-854`), `_NDS_SKILLS_WORLDS`/
  `_nds_skills_enabled` (`:847-854`), arm-isolation check (`:905`), `_parse_nds_stop_when` (`:1478`),
  `GAMES["nds"]` incl. `watch: {}` (`:168-172`).
- `core/perception_plugin.py` (`:135-187`) — `press_sequence` schema + `hold=8` hardcode, confirming the
  24-frame-per-press arithmetic against Arm A's raw `oracle.jsonl` frame deltas.
- `HANDOFF.md` — line ~587, the already-banked s=4 correction (briefing's `:636` pointer is stale).
- Raw run artifacts (gitignored, on-disk in the primary checkout, read but not modified):
  `runs/brain_mkds_armA_default/world/oracle.jsonl`, `runs/brain_mkds_armB_default/world/skills.jsonl`.
