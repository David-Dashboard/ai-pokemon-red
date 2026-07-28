# Graduation exam v1 — definition (2026-07-22)

> ## ⚠ MERGING THIS PR DOES NOT FREEZE THE EXAM
>
> **Read this before treating anything below as settled.**
>
> 1. **Merge ≠ freeze.** This PR is merged for ONE reason: `main` already carries eight
>    `eval/score_exam_*.py` files that cite this document *by filename* while the document itself
>    does not exist on `main` — a dangling reference. Merging repairs that reference. It does
>    **not** approve, ratify, adopt, or freeze the exam.
> 2. **The freeze is a separate, explicit, signed act.** It happens only when David says, in
>    writing and unambiguously, "the v1 exam is frozen." Until that sentence exists, every task
>    definition, quota, bar and reserve title below is a **draft open to revision**. No later
>    session may infer the freeze from this file's presence on `main`, from a merge commit, from a
>    green CI run, or from the existence of the scorers.
> 3. **As of 2026-07-28 the exam cannot render a verdict at all.** Only **4 of 10** tasks have a
>    working oracle (EX01, EX07, EX08, EX09). Four (EX02, EX03, EX04, EX05) are `ORACLE_PENDING`
>    stubs whose `main()` unconditionally returns `1` and can never emit PASS; two (EX06, EX10)
>    have no scorer file at all because no world-port exists. See
>    `reports/2026-07-25-exam-oracle-capability-synthesis.md` §1 and `HANDOFF.md` item 2.
>    **A battery that cannot score 6 of its 10 tasks is not a freezable exam.**
> 4. **No pass bar exists** (§3). Freezing an exam whose pass bar is unset would allow the bar to
>    be chosen after the result is known.
>
> Corrections applied 2026-07-28 to stale claims in the original 2026-07-22 draft are marked
> **[UPDATED 2026-07-28]** inline. The body below otherwise stands as drafted.

Status: **v1-DRAFT, NOT FROZEN.** This is the B1 "graduation exam" definition pinned as a NEXT
item in `reports/2026-07-05-northstar-capability-map.md` (~lines 138-155) and its companion F10
reserve-quarantine (~lines 226-232). `$0` design work: no paid run, no Codex exec, no brain run,
no scorer or tool built. Sketches the 10-task battery, names candidate reserve titles, and states
the scoring/baseline protocol Gate 0 already validated at smaller scale
(`reports/2026-07-13-minimum-north-star-gate-0-design.md`). Freeze requires David's sign-off after
his own baseline plays; nothing here is banked yet.

The exam answers one question the per-gate method can't: **has the North Star actually arrived**,
not just cleared one more isolated capability gate. It exercises all four claims in `HANDOFF.md`
§1 (Capability, Constancy, Generality, Cheap) across a battery large enough that no single
lucky/unlucky task decides the verdict, run ONLY at phase exits — never per-gate, never tuned on
(B1's rules, restated in "Scoring" below).

## 1. The battery — 10 tasks

Summary (world / harness key already registered in `world_mcp.py::GAMES` unless marked RESERVE —
never-touched, quarantined until the exam's own attempt):

| id | world (console / harness) | claim(s) | reserve? |
|---|---|---|---|
| EX01 | GB — Pokemon Red (`pokemon_red`) | Capability, Constancy, Cheap | no (dev-banked) |
| EX02 | GB — Kirby's Dream Land (`kirby_dreamland`) | Capability, Constancy, Cheap | no (dev-banked) |
| EX03 | GBA — Pokemon Emerald (`emerald_gba`) | Capability, Constancy, Generality, Cheap | no (dev-banked) |
| EX04 | GBA — Kirby: Nightmare in Dream Land (`kirby_gba`) | Capability, Constancy, Generality, Cheap | no (dev-banked) |
| EX05 | NDS — Mario Kart DS (`nds` + MKDS ROM) | Capability, Constancy, Generality, Cheap | no (dev-banked, probe-only) |
| EX06 | NDS — Metroid Prime Hunters | Capability, Constancy, Generality, Cheap | **YES — never-touched** |
| EX07 | Browser — MiniWoB `focus-text` (`miniwob_focus_text`) | Capability, Constancy, Generality, Cheap | no (harness banked, task variant new) |
| EX08 | Browser — MiniWoB `click-checkboxes`, exam-own seeds (`miniwob_click_checkboxes`) | Capability, Constancy, Generality, Cheap | no (harness banked, seeds new) |
| EX09 | ARC-AGI-3 — `wa30` (`arcagi3`) | Capability, Constancy, Generality, Cheap | no (dev-banked) |
| EX10 | GB — Marble Madness | Capability, Constancy, Generality, Cheap | **YES — never-touched** |

Coverage: GB x3, GBA x2, NDS x2, browser x2 — every required world class clears its `>=2` floor;
ARC included because it fits (a fifth, already-banked world class, cheap marginal evidence). Two
reserve tasks (EX06, EX10) satisfy the `>=2` NEVER-TOUCHED floor.

### Per-task detail

**EX01 — Red: first badge.** Instruction: *"From the fresh bedroom start, earn your first Gym
Badge."* End state: RAM oracle `badges` (`0xD356`, already wired in `world_mcp.py:177`) bit 0 flips
`0->1` (Boulder Badge) — same oracle field the Gate 0 scorer already reads, one step further than
Gate 0's "win the rival battle." Quota: **~$8, ~250 decisions.**

**EX02 — Kirby's Dream Land: clear Stage 3.** Instruction: *"Clear Stage 3."* End state: a
stage/level counter or overworld stage-select cursor advancing past Stage 3. The only oracle
currently wired for this world is `hp` (`0xD086`, plain int, entity-gate v2 target).

**[UPDATED 2026-07-28 — the original draft said the stage-counter address was "not yet identified"
and scheduled a `$0` RAM hunt. That was true on 2026-07-22 and is now stale; but the replacement is
a CANDIDATE, not a settled oracle.]** A candidate stage-counter
address — **`0xD03B`** — was identified in **PR #173**, which is **OPEN and unmerged** as of
2026-07-28. Nothing is wired: `eval/score_exam_kirby_stage3.py` is untouched and still refuses
unconditionally with `ORACLE_PENDING`, and `world_mcp.py` is deliberately not edited (registry
edits cascade into the frozen Gate-0 host/image pins — `HANDOFF.md` item 9). The address is
**0-indexed**: `0` = Green Greens, `1` = Castle Lololo, `2` = Float Islands. PR #173 also
eliminated the four rival candidates (`0xD19F`, `0xD3A9`, `0xD3BA`, `0xD3CD`) as one-time
"past Stage 1" latches — all four still read `1` *inside* Stage 3, so an oracle wired on any of
them would have silently passed EX02 the moment Kirby left Green Greens.

**Two limits keep this OFF the settled list:**
- The Stage-3 observation window is **short — the last ~46 oracle rows of a 1,128-row capture,
  one observed `1 -> 2` transition**. That is enough to separate an already-incremented counter
  from four bytes that never moved; it is **not** confirmation that `0xD03B` holds correctly
  during sustained Stage-3 gameplay.
- **`0xD03B` has never been observed reading `3`.** PR #173 states the precondition explicitly:
  *confirm `0xD03B` reads `3` at the Stage-3 → Stage-4 boundary before wiring.* Since EX02's
  success condition IS "advance past Stage 3," the exact transition the task depends on is the
  one still unobserved.

This lane has been burned three times by too-few-anchors readings (Cave Noire `0xD389`, Emerald
outdoor `map_num`, PR #169's own lockstep claim). Treat `0xD03B` as the best lead, not as the
oracle. Confirming the Stage-4 boundary reading, then wiring it in the batched `watch` PR,
remains readiness work before freeze. Quota: **~$4, ~120 decisions.**

**EX03 — Emerald: reach Oldale Town.** Instruction: *"From the fresh start in your bedroom, reach
the first town outside Littleroot."* End state: a map-ID transition (Littleroot -> Route 101 ->
Oldale). **Gap:** `emerald_gba`'s registry `watch` is `{}` — no GBA world has an oracle wired yet
(`world_mcp.py:187-191`). A GBA memory-map oracle hunt is required readiness work, mirroring Red's
`memory_map.py`.

**[UPDATED 2026-07-28 — the obvious candidate oracle has been FALSIFIED; see `HANDOFF.md:112-121`
(item 10).]** The 2026-07-22 draft assumed a map-ID transition was a straightforward oracle once
GBA memory was mapped. It is not. **Outdoor `map_num` is UNSTABLE and is unsafe as a location
oracle** — three visually-contiguous parts of the *same* Littleroot Town exterior read three
different values (`10` near the truck, `12` near the houses, `14` outside Birch's Lab) while
`map_group` stayed `2` throughout; worse, the third reading `(2, 14)` **collides** with the
upstairs bedroom's own `(2, 14)` interior reading, confirmed on two independent fully-settled
screenshots. "`map_num` = current map" is **FALSE outdoors**. Since EX03's end state is precisely
an *outdoor* Littleroot → Route 101 → Oldale transition, the naive map-ID oracle is disqualified;
a different or composite signal is required. This was caught before any wiring happened (#144
partially falsified) and is the second instance of the Cave Noire too-few-anchors pattern.
Quota: **~$6, ~150 decisions.**

**EX04 — Kirby (GBA): clear Level 1-1.** Instruction: *"Clear the first level."* End state: a
level-complete/door-transition signal. Same gap as EX03 — `kirby_gba` also has `watch: {}`; needs
its own oracle hunt. Quota: **~$6, ~150 decisions.**

**EX05 — MKDS: finish one lap.** Instruction: *"Finish one lap of a Time Trial, any time."*
(Matches the capability-map sketch's "finish a race, any place.") End state: the candidate progress
byte `0x022C8090` from `reports/2026-07-04-mkds-continuous-time-build-plan.md` — **explicitly
unverified**: the 2026-07-13 MKDS A/B report states this byte "was not present in either run's
`oracle.jsonl`... do not claim checkpoint/lap progress from RAM for this run." Verifying (or
replacing) this oracle is a hard precondition, not optional polish.

**[UPDATED 2026-07-28 — `0x022C8090` is now DISQUALIFIED, not merely unverified; see
`HANDOFF.md:123-129` (item 11, MKDS / PR #168).]** The byte was disqualified a **second,
independent way**: it **RESETS to match `0x022C8094`'s value** after a stuck/off-track timeout —
on top of the already-known bidirectional wrong-way decrement. A progress oracle that both counts
down and silently resnaps to another byte cannot ground a "finished one lap" claim. **The current
best lead is `0x022C8094`**, and it is a lead only: **only the values `0` and `1` were ever
observed**, so BCD-vs-plain-int remains inconclusive and no lap-boundary reading is confirmed. Two
further low-confidence leads exist (`0x022C8358`, likely another kart's struct copy; the
`0x022C8A2x`-`0x022C8A4x` cluster, corroborated across two independent sessions). EX05's oracle
is therefore still OPEN — the candidate changed, the gap did not close. Quota: **~$10, ~200
decisions** (continuous-time worlds need more `stop_when` loop iterations).

**EX06 — Metroid Prime Hunters (RESERVE, never-touched).** Instruction: *"Reach the door at the end
of the starting corridor and open it."* End state: a room/waypoint transition, oracle TBD (never
touched in dev, no memory map exists). Fills F10's noted gap: no fresh, never-touched first-person
3D title exists in the corpus — this is a genuinely new, non-ViZDoom first-person 3D game on a
console (NDS) already in the harness. Highest-risk/most-expensive task (3D perception is the
hardest lane; GATE-3D's own FAIL cost $82.86 for a much longer run) — capped short-leash. Quota:
**~$15, ~150 decisions.**

> **[UPDATED 2026-07-28 — the "Doom is already burned" premise is WITHDRAWN as a settled fact.]**
> The 2026-07-22 draft justified EX06 partly by asserting that Doom "is already burned" for
> 3D-primitive claims via GATE-3D's `defend_the_center` dev use, treating that dev use as a
> completed, legitimate fact. **That is now an OPEN INTEGRITY QUESTION, not a settled premise —
> see `HANDOFF.md:70-82` (item 5).** VizDoom is **OFF-LIMITS pending David's explicit sign-off**:
> Doom is on the held-out list (`eval/dataset_split.py:30-36`, confirmed verbatim), this repo's
> `CLAUDE.md` STOP condition is unqualified ("Never touch Crystalis/Zelda-LA/SML/F-1/Doom during
> development"), and **no carve-out for the GATE-3D lane exists anywhere**. The unresolved question
> is whether the GATE-3D dev use was a held-out violation in the first place — the lane already
> calibrated on it (`core/yaw_flow.py:4-7` pins its P1 floors from `runs/vizdoom_precheck/`), and
> two prior sessions independently routed around Doom on held-out grounds.
>
> **Consequence for EX06:** the case for EX06 does **not** depend on this premise and stands
> without it — the corpus contains no fresh, never-touched first-person 3D title regardless of how
> the Doom question resolves. The premise is dropped rather than repaired. **Do not cite "Doom is
> burned" as settled anywhere downstream, and do not resolve the question by touching VizDoom.**

**EX07 — MiniWoB `focus-text` (typing).** Instruction: exactly the on-screen MiniWoB task
utterance (a form field to fill and submit) — matches the capability map's "computer-use — MiniWoB
form-with-typing episode set." End state: reward `1.0` on N fresh episodes, oracle-side only (mirror
`_miniwob_success` in `eval/score_gate0.py`). This world class variant is registered
(`world_mcp.py:199`) but has never had a full brain run (`world-lanes-frontier`: "Open: harder
tasks — checkboxes, forms, typing"). Quota: **~$2, ~40 decisions.**

**EX08 — MiniWoB `click-checkboxes`, exam-own seeds.** Instruction: on-screen checkbox-selection
utterance. Same task TYPE Gate 0 uses, but on a **fresh, exam-only seed block** (proposed `5000-5004`
— distinct from Gate 0's dev `0-4` and paid held-out `1000-1004`, never overlapping, quarantined
until the exam's own attempt, same discipline as `gate0_miniwob_paid_seeds.json`). Quota: **~$2,
~40 decisions.**

**EX09 — ARC-AGI-3 `wa30`: reach level 3.** Instruction: none beyond the game's own on-screen
signal — ARC games are figured out cold, same as the banked skill-compilation rung-1 result
(2/9 levels, Arm B). One level past that banked result. End state: `levels_completed` from the
oracle-only `arcagi3` session log (never on the wire, `world_mcp.py:228-234`). Quota: **~$10,
~60 decisions.**

**EX10 — Marble Madness (RESERVE, never-touched).** Instruction: *"Complete the first course."*
End state: a course-complete/course-transition signal, oracle TBD (new world-port work). Fills
F10's other noted corpus gap: **no isometric-view game exists anywhere in the corpus**
(`reports/2026-07-05-northstar-capability-map.md` F10) — Marble Madness is a classic isometric
GB title, never referenced anywhere in this repo. Quota: **~$6, ~150 decisions.**

### Reserve titles — candidates for David's final pick

F10 calls for 2-3 quarantined never-touched titles, named now, treated exactly like `HELDOUT`
(`eval/dataset_split.py`) but as a **separate list for a separate purpose** — never developed
against, never data-collected-and-inspected before the exam's own one attempt:

1. **Metroid Prime Hunters (NDS)** — primary pick for EX06 (non-ViZDoom first-person 3D).
   *Alternate:* Splinter Cell: Chaos Theory (NDS) if touch-screen mechanics don't fit the harness.
2. **Marble Madness (GB)** — primary pick for EX10 (isometric). *Alternate:* Q*bert (GB) if
   Marble Madness's physics-heavy ball control is a bad match for discrete button input.

**[CORRECTED 2026-07-28 — the original claim here was FALSE. It read: "None of these four appear
anywhere in `HANDOFF.md`, `eval/dataset_split.py`'s `HELDOUT`, the GBA probe sweep
(dbz/ffvi/mk/naruto), or any `datasets/labels/` manifest — verified by grep before proposing
them." The verifying grep missed `HANDOFF.md` entirely for Q\*bert and did not cover
`reports/_archive/`.]**

Re-run 2026-07-28 across the whole repo including `reports/_archive/` (`rg -i` over the full
working tree). **Actual results, per title:**

| title | hits outside this document | verdict |
|---|---|---|
| **Marble Madness** (EX10 primary) | **none** | clean — never referenced anywhere in the repo |
| **Metroid Prime Hunters** (EX06 primary) | **none** | clean (note: plain "Metroid II" is a *different*, dev-used GB game — do not confuse them) |
| **Splinter Cell: Chaos Theory** (EX06 alt) | **none** | clean |
| **Q\*bert** (EX10 alt) | **6 hits across 4 files** | **NOT clean — see below** |

Q\*bert's actual hits:
- `HANDOFF.md:2134` — the ROM acquisition ladder: *"acquisition order Lolo→Zelda-Oracle→
  FF-Adventure→Crystalis→Metroid-II→Q\*bert→F-1-Race→Sword-of-Hope-II"*
- `reports/_archive/2026-06-22-gb-perception-test-suite.md:22` and `:43`
- `reports/_archive/2026-06-22-decision-log.md:93` — the same acquisition ladder, marked `[OPEN]`
- `reports/_archive/2026-06-22-cross-game-phase-plan.md:41` and `:69`

**Why this matters more than a missed grep.** Q\*bert was not merely mentioned in passing — it was
**pre-designated as *the* isometric probe world**, on exactly the axis EX10 exists to test. The
2026-06-22 perception test suite names it as *the* isometric entry ("**isometric** projection;
diagonal-hop input + iso depth. An axis nothing else touches"), and it sits at a fixed slot in the
acquisition ladder chosen so each title isolates ONE new perception axis. A title that the project
already selected, on the record, as its isometric probe is **not** a never-touched reserve in the
sense F10 requires — it has been reasoned about, ranked, and pre-committed against the very axis it
would be scored on. Whether that is disqualifying is **David's call**, but it must be made
knowingly, not on the strength of a false "appears nowhere" claim.

**Net effect on reserve integrity:** EX10's *primary* pick (Marble Madness) is genuinely clean, so
the `>=2` NEVER-TOUCHED floor still holds **as long as the primaries are used**. The floor is at
risk only if the Q\*bert *alternate* is exercised. EX06's primary and alternate are both clean.

**No `RESERVE` constant exists anywhere in the codebase** — `rg RESERVE` returns hits only inside
this document (3 occurrences: §1's table legend and the EX06/EX10 headings). Unlike `HELDOUT`,
which is a real enforced list in `eval/dataset_split.py`, reserve-title quarantine is currently
**enforced by convention only, not by code**: nothing mechanically prevents a future session from
developing against Metroid Prime Hunters or Marble Madness.

**Final title selection is David's** (§5).

## 2. Human baseline protocol

Same law as Gate 0 (`reports/2026-07-13-minimum-north-star-gate-0-design.md`): David (or any
human) plays **each task once, cold**, from the exact same fresh state the agent will use.
Human-grade = agent succeeds within **~2x** the recorded human wall-clock time (and, mirroring
Gate 0's capability bar, `<=2x` human primitive-action count). One cold attempt is the baseline —
a genuine-but-mediocre baseline is not retaken to chase a better number (`DAVID_BASELINES.md`'s
"re-run rule," restated for the exam).

**Reuse where a rig already exists:**
- EX01 (Red) — `tools/capture_gate0_baseline_red.py` already captures exactly this shape
  (`human_metrics.json`: `schema_version`, `role=human`, `wall_clock_s`, `primitive_actions`); only
  the stop condition (badge, not rival-win) changes.
- EX07/EX08 (MiniWoB) — `tools/capture_gate0_baseline_miniwob.py` already captures this shape per
  episode; needs pointing at the exam's own task/seed block instead of Gate 0's.

**New capture tooling needed (not built here — design-only per this doc's scope):**
- EX02/EX03/EX04/EX05/EX10 — no oracle is wired for these end-states yet (see per-task gaps
  above), so no rig can time a "success" it can't detect. Oracle-hunt first, then a thin
  baseline-capture script per the `capture_gate0_baseline_*.py` pattern (structurally, not a new
  design).
- EX06 (Metroid Prime Hunters) — needs a wholly new world-port (`new-world-port` skill) before any
  baseline capture is possible; the single largest piece of NEW harness work the exam implies.
- EX09 (ARC `wa30`) — no capture tool exists for a human ARC session; likely a thin stopwatch
  wrapper around the existing `arcagi3_world.py` REST client, structurally trivial but not written.

## 3. Scoring

One fail-closed, offline oracle scorer per task, mirroring `eval/score_gate0.py`'s pattern exactly:
a `_<task>_success(rows) -> (bool, list[str])` predicate per task reading only append-only
`oracle.jsonl` rows (never the transcript, never a model self-report); a `_verify_sources` step
that hash-pins oracle/baseline artifacts before trusting them (`score_gate0.py::_verify_audit_paths`'s
"never read an unpinned path" discipline); an `_arm_metrics`-style check requiring the success
predicate AND the `<=2x` wall-clock/action bars AND the cost/credit cap to all clear before a task
counts PASS; and failures bucketed the way Gate 0 does (`leak`/`constancy`/`infra`/`source`/
`capability`/`cheap`) so a scorer refusal (`INSUFFICIENT_DATA`) is never confused with an honest
FAIL (`eval-probes-and-datasets` §6's fail-closed-over-confident-wrong norm).

**Battery scorecard:** `tasks_passed / 10`, reported as-is in `HANDOFF.md` even (especially) when
embarrassing — no averaging away a bad task, no re-weighting after the fact.

### Battery pass bar — **OPEN — pass bar not yet set.**

**There is no threshold on `tasks_passed / 10` that constitutes graduation, and this document does
not invent one.** The v1 draft defined the scorecard and the per-task `~2x human` bars but never
stated what total score means "the North Star has arrived." That gap is recorded here rather than
papered over: **a number chosen without the inputs below would be a guess wearing the costume of a
bar**, and a guessed bar is worse than an admitted gap, because everything downstream would treat
it as pre-registered.

**Hard rule: the bar MUST be set BEFORE any exam attempt is run.** Not before scoring — before the
*attempt*. If the bar is set after any task has run, it can be chosen (consciously or not) to match
the result already in hand, which converts the exam from a test into a post-hoc narrative. This is
the same discipline as Gate 0's R0/W0/C0 pre-registration phase and the `A2.2` rule that a bar may
only ever move **stricter**, never softer. **Setting the bar is David's act, not a session's.**

**Inputs required before the bar can honestly be set:**
1. **All 10 oracles working.** As of 2026-07-28 only 4/10 tasks can return PASS at all (banner,
   §top). A bar over a scorecard where 6 tasks are structurally incapable of passing is
   meaningless — the maximum achievable score today is `4/10`.
2. **All 10 human baselines captured** (§2). Until David has played each task once cold, the
   per-task `~2x human` bar has no value on 8 of 10 tasks, so `tasks_passed` is not yet defined
   per task, let alone in aggregate.
3. **A stated position on partial credit.** Is the bar a simple count (`>=N/10`), or does it
   require specific tasks? A flat count lets 10 easy passes substitute for the hard lanes.
4. **A stated position on the reserve tasks (EX06, EX10) and the per-claim floors.** The battery
   asserts four claims (Capability, Constancy, Generality, Cheap) and a `>=2` never-touched floor.
   The bar must say whether failing *both* reserve tasks, or every task carrying a given claim,
   is independently disqualifying regardless of the total.
5. **A stated failure-bucket policy.** Gate 0's buckets (`leak`/`constancy`/`infra`/`source`/
   `capability`/`cheap`) already distinguish an honest capability FAIL from an `infra` FAIL or an
   `INSUFFICIENT_DATA` refusal. The bar must say whether an `infra`-bucketed loss counts against
   `tasks_passed` or voids the attempt.

Until all five are settled and the bar is written down and signed, **the exam is not freezable**
(banner, §top) — and this section, not silence, is the reason.

### Known design defect — **Constancy is unmeasurable as specified (UNRESOLVED)**

Every one of the 10 tasks in §1's table carries a **Constancy** claim. But the "one-attempt" rule
below grants each task **exactly one attempt per phase-exit run**. Constancy is a claim about
*repeatability* — the same fixed brain behaving consistently across repeated exposure — and a
single attempt per task produces exactly one sample, from which no repeatability can be measured.
**The exam as specified therefore cannot measure the Constancy claim it assigns to all 10 tasks:
it is unmeasurable by construction, not by accident of the oracle gaps.**

This is recorded as a **known, unresolved design defect**. It is deliberately **not** fixed here —
resolving it means either relaxing the one-attempt rule (which would weaken the strongest
anti-tuning protection the exam has) or redefining what Constancy means at battery scale (perhaps
as cross-*task* consistency of one frozen config rather than within-task repetition), and both are
exam-design decisions for David, not a documentation edit. **Whoever sets the pass bar (above) must
resolve this first**, because a bar that counts Constancy is currently counting something the
battery does not measure.

**Frozen-once-pinned / one-attempt / banked-verbatim** (B1's rules, restated): once David signs
off on this doc (or a revised version), the 10 task definitions are frozen — additions are a new
exam version (`v2`), never a silent edit to `v1`. Each task gets exactly one attempt per phase-exit
run; all ten run in the same window (or a documented short pause between the cheap and long groups,
§4) with the SAME frozen brain/harness config across all ten, artifacts banked verbatim regardless
of outcome. The exam runs ONLY at phase exits (never per-gate) — this is what keeps it from being
tuned on.

## 4. Cost estimate

| group | tasks | rough total |
|---|---|---:|
| Cheap/short (GB + GBA + browser) | EX01, EX02, EX03, EX04, EX07, EX08 | ~$28 |
| Long/expensive (NDS + 3D-reserve + ARC + isometric-reserve) | EX05, EX06, EX09, EX10 | ~$41 |
| **Total** | 10 | **~$69** |

Within the capability map's `~$50-100` estimate (B1). Pacing: the cheap group is one short window
(all six tasks `<=$8` each, existing harnesses); the long group runs as its own window — EX06
(reserve, 3D, `$15`) shouldn't share a window with anything else, given GATE-3D's precedent of
3D-lane runs blowing past budget. These are **rough, pre-readiness estimates** — pre-registration
(mirroring Gate 0's R0/W0/C0 phase) pins exact `$`/credit caps per task once each oracle gap above
is closed.

## 5. What's OUT / open for David

This is v1-DRAFT, **not frozen**. Explicitly left to David:
- **Reserve-title final selection** — pick among Metroid Prime Hunters / Splinter Cell: Chaos
  Theory for EX06, and Marble Madness / Q*bert for EX10 (§1's "Reserve titles" list); ROMs must be
  legally obtained per this project's existing ROM policy (`roms/README.md`).
- **Per-task baseline plays** — David plays all 10 tasks once, cold (§2); this doc only defines the
  protocol, it does not capture a single baseline number.
- **Freeze sign-off** — this document is a draft for review; nothing here is banked until David
  approves it (or a revised task list), at which point it becomes the frozen `v1` exam.
- **Not attempted here:** any oracle hunt (Kirby GB stage counter, GBA map-ID for Emerald/Kirby
  GBA, MKDS progress-byte verification), any new-world-port work (Metroid Prime Hunters, Marble
  Madness / their alternates), any scorer code, any baseline-capture tooling, any paid run. All of
  that is readiness work for AFTER this draft is approved, run with the same `$0`-first discipline
  Gate 0's R0/W0/C0 phase used.
