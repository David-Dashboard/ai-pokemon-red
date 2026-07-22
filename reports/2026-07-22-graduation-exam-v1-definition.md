# Graduation exam v1 — definition (2026-07-22)

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
currently wired for this world is `hp` (`0xD086`, plain int, entity-gate v2 target) — the
stage-counter address is **not yet identified**; a `$0` RAM hunt (same discipline that found
`hp@0xD086`) is readiness work before freeze. Quota: **~$4, ~120 decisions.**

**EX03 — Emerald: reach Oldale Town.** Instruction: *"From the fresh start in your bedroom, reach
the first town outside Littleroot."* End state: a map-ID transition (Littleroot -> Route 101 ->
Oldale). **Gap:** `emerald_gba`'s registry `watch` is `{}` — no GBA world has an oracle wired yet
(`world_mcp.py:187-191`). A GBA memory-map oracle hunt is required readiness work, mirroring Red's
`memory_map.py`. Quota: **~$6, ~150 decisions.**

**EX04 — Kirby (GBA): clear Level 1-1.** Instruction: *"Clear the first level."* End state: a
level-complete/door-transition signal. Same gap as EX03 — `kirby_gba` also has `watch: {}`; needs
its own oracle hunt. Quota: **~$6, ~150 decisions.**

**EX05 — MKDS: finish one lap.** Instruction: *"Finish one lap of a Time Trial, any time."*
(Matches the capability-map sketch's "finish a race, any place.") End state: the candidate progress
byte `0x022C8090` from `reports/2026-07-04-mkds-continuous-time-build-plan.md` — **explicitly
unverified**: the 2026-07-13 MKDS A/B report states this byte "was not present in either run's
`oracle.jsonl`... do not claim checkpoint/lap progress from RAM for this run." Verifying (or
replacing) this oracle is a hard precondition, not optional polish. Quota: **~$10, ~200
decisions** (continuous-time worlds need more `stop_when` loop iterations).

**EX06 — Metroid Prime Hunters (RESERVE, never-touched).** Instruction: *"Reach the door at the end
of the starting corridor and open it."* End state: a room/waypoint transition, oracle TBD (never
touched in dev, no memory map exists). Fills F10's noted gap: Doom is already "burned" for
3D-primitive claims (GATE-3D's `defend_the_center` dev use, `world-lanes-frontier` skill) so it
can't also be a *fresh* reserve title — this is a genuinely new, non-ViZDoom first-person 3D game
on a console (NDS) already in the harness. Highest-risk/most-expensive task (3D perception is the
hardest lane; GATE-3D's own FAIL cost $82.86 for a much longer run) — capped short-leash. Quota:
**~$15, ~150 decisions.**

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

None of these four appear anywhere in `HANDOFF.md`, `eval/dataset_split.py`'s `HELDOUT`, the GBA
probe sweep (dbz/ffvi/mk/naruto), or any `datasets/labels/` manifest — verified by grep before
proposing them. **Final title selection is David's** (§5).

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
