# Exam-oracle synthesis: 4 blocked tasks are gated on play-capability, not RAM hunting

Status: **$0, docs only, no runs, no code/scorer/world_mcp/fixture edits.** Synthesizes four
2026-07-25 oracle-hunt reports plus their two 2026-07-23 predecessors, against the graduation-exam
v1 definition (PR #129, open/unmerged) and the eight `eval/score_exam_*.py` scorers on `main`
(`6966084`). Written to inform, not make, David's PR #129 (graduation-exam v1 freeze) decision.

**One framing correction up front:** the task brief that requested this report described
`reports/2026-07-22-graduation-exam-v1-definition.md` as "merged on main" alongside the other
source reports. It is not — `git merge-base --is-ancestor` confirms it is **not** an ancestor of
`main`; it lives only on the still-open `docs/exam-v1-definition` branch (PR #129 itself, read here
via `git show origin/docs/exam-v1-definition:reports/2026-07-22-graduation-exam-v1-definition.md`).
This is not a discrepancy worth alarm — PR #129 being unmerged is *exactly* what "v1-DRAFT, NOT
frozen" and "David's pending decision" mean — but every quote from that file below is sourced from
the open PR branch, not from `main`, and is flagged as such once here rather than repeatedly.

## 1. The scoreboard, precisely

Eight `eval/score_exam_*.py` files exist on `main` today for the 10-task v1-DRAFT battery (EX01-EX10).
Two tasks (EX06 Metroid Prime Hunters, EX10 Marble Madness) have **no scorer file at all** — both are
"RESERVE — never-touched" titles per the exam doc, blocked at a stage *before* oracle-hunting even
starts (no world-port exists yet). Of the eight that exist:

**4 are real, fail-closed predicates capable of returning PASS**, no different in kind from
`eval/score_gate0.py`:
- EX01 `score_exam_red_badge.py` — `badges` bit-0 flip, corroborated by an exact `party` 0->1
  transition and a real `in_battle==2` battle strictly before the flip.
- EX07 `score_exam_miniwob_focus_text.py`, EX08 `score_exam_miniwob_click_checkboxes.py` — shared
  `miniwob_task_success` predicate, reward==1.0 on pinned seed blocks.
- EX09 `score_exam_arc_wa30.py` — `levels_completed` monotonicity + state-validity checks.

**4 are `ORACLE_PENDING` stubs that refuse unconditionally** — `main()` always `return 1`, never
PASS, regardless of input (three of the four take no oracle file at all; the fourth, EX05, likewise
never returns anything but refusal). Their stated blockers, quoted verbatim from the module
docstring and the `failures` list each emits:

| task | file | quoted blocker |
|---|---|---|
| EX02 | `score_exam_kirby_stage3.py` | "no stage/level-counter RAM address is known for `kirby_dreamland` yet" / failure code `no_stage_counter_ram_address_known` |
| EX03 | `score_exam_emerald_oldale.py` | "`emerald_gba`'s registry `watch` is `{}` -- no GBA world has an oracle wired yet" / failure code `no_gba_map_id_oracle_wired` |
| EX04 | `score_exam_kirby_gba_level1.py` | "`kirby_gba`'s registry `watch` is `{}` -- same gap as `emerald_gba`" / failure code `no_gba_level_complete_oracle_wired` |
| EX05 | `score_exam_mkds_lap.py` | "the only candidate progress byte, `0x022C8090` ... is explicitly UNVERIFIED" (quoting the 2026-07-13 MKDS A/B verdict: "was not present in either run's `oracle.jsonl`... do not claim checkpoint/lap progress from RAM for this run") / failure code `mkds_progress_byte_unverified` |

Confirmed directly in `world_mcp.py` on `main`: `GAMES["kirby_gba"]["watch"]` and
`GAMES["emerald_gba"]["watch"]` are both still `{}` (lines 186, 191) — the stub docstrings'
"no oracle wired" claim is accurate as of `6966084`, not stale.

**Net: 4/10 scorable today, 4/10 blocked as ORACLE_PENDING (the subject of this report), 2/10
blocked earlier still (no world-port).** The four oracle-hunt reports below are exactly the four
ORACLE_PENDING rows — they do not touch EX06/EX10, which need new-world-port work first, a
different and larger gap than an oracle hunt.

## 2. The thesis, tested: four DIFFERENT walls, not one

The thesis under test: *the exam's oracle gaps are downstream of a play-capability gap, not a
RAM-hunting gap* — every hunt's RAM-hunting method worked fine; what stopped each one was the
driver's inability to reach the state that would disambiguate the candidate oracle. This **survives**
testing, with the bound stated in §3. The four walls are genuinely different capability classes and
should not be flattened into one "the agent is bad at games" claim:

| task | RAM-hunting status | what actually blocked completion | capability class |
|---|---|---|---|
| EX05 MKDS | 8 candidate addresses characterized (2 disqualified, 1 leading, 2 low-confidence, plus a corroborated unpursued cluster) | no fixed/open-loop policy survives more than ~100-250 frames past turn 1 anywhere on the course; ~15,000 frames of scripted+manually-corrected driving across two sessions never finished one lap | **continuous-control / closed-loop driving** — the course requires per-segment steering adaptation no open-loop policy generalizes to |
| EX02 Kirby GB | 8 survivors pinned (down from 11 candidates across two sessions), all 3 prior candidates eliminated with evidence | Castle Lololo's block-push/door puzzle resisted scripted and hand-tuned eyes-on play; Stage 3 was never reached, only one stage transition (1->2) was ever observed | **puzzle-solving** — the obstacle is a game-design puzzle, not a reflex/dexterity check |
| EX04 Kirby GBA | `world`/`score` addresses re-verified under continuous live play (stronger than prior snapshot evidence); `A` confirmed as jump/float | a stationary hazard at score 2800 resisted ~10 varied jump-height/timing/crouch attempts; the level's goal door was never reached | **precise platforming** — a single reflex/timing obstacle, not a puzzle or navigation problem |
| EX03 Emerald | `map_group`/`map_num`/`x`/`y` addresses found and (mostly) verified; Birch's Lab interior newly pinned at `(2,13)` | Route 101's only exit is permanently blocked by a fixed NPC whose dialogue never varies or advances regardless of approach angle, waiting, or prior Lab visit — reachable only by first completing the starter-Pokemon rescue quest | **a scripted game gate requiring prior task completion** — not a navigation, puzzle, or dexterity problem at all; the game itself refuses to let the run proceed |

Each row's "what blocked completion" is a different kind of gap: control-loop design, puzzle
inference, motor-timing precision, and quest-sequencing respectively. A single fix (e.g., "better
scripted play") would not obviously close all four — closed-loop vision-guided steering does
nothing for a fixed NPC gate, and clearing a game-story precondition does nothing for MKDS's
per-turn steering problem. This is the reason the thesis is stated as a **structural** finding
(each hunt independently hit a play-capability wall before it hit a RAM-hunting wall) rather than a
single named deficiency.

## 3. The honest bound: this measures the RIG, not (mostly) the brain

All four hunts were driven by **scripted policies or human-in-the-loop screenshot-stepping** — a
from-scratch Python driver picking fixed button sequences (MKDS's `drive_lap.py`/`step.py`), a
simple autopilot plus hand-tuned bursts (Kirby GB's `continue_stage2.py`/`nav_step.py`), or direct
scripted button sequences with eyes-on verification (Kirby GBA's `gba_drive.py`, Emerald's
manual routing). **None of the four hunts ran the paid brain** (no `claude -p`, no full-perception
agent loop, $0 across all four).

The correct claim, therefore, is about **what this project's current oracle-hunting rig can reach**
— not, except partially, about what the paid brain with full screen perception and its actual
reasoning loop can do. It would be an overreach to say "the brain cannot clear Castle Lololo" or
"the brain cannot beat the score-2800 obstacle" — that has not been measured for 3 of these 4 tasks.
Do not repeat those as brain-capability claims; they are rig-capability (scripted/manual-driver)
findings only.

**The one genuine brain datapoint is the Kirby GB long-haul run**, and even it only bears on EX02,
not the other three. Verified from `reports/2026-07-05-northstar-capability-map.md` and `HANDOFF.md`
(no dedicated verdict report exists for this run — both sources note that explicitly; there is no
`reports/*longhaul*` file in git history):
`runs/brain_kirby_longhaul/` (2026-07-04, gitignored, on-disk evidence only): `run.exit` EXIT=0,
transcript `subtype: success`, **316 turns**, **$42.98**, **52.1 min wall-clock**, **587 world
steps**, 72 `skills.jsonl` records. The brain's own closing report: it exercised the define/run-skill
loop thoroughly and made progress through Kirby Stage 1, but **did not clear the stage or beat a
boss** — i.e., even the one real paid-brain attempt at this exact game did not reach the Stage-2
transition this session's oracle hunt needed, corroborating (not proving) that Castle Lololo-class
obstacles are hard for more than just the scripted rig. This is one data point, not a controlled
comparison, and it predates the float-mechanic fix the 2026-07-25 hunt found (jump, then a second
`A` press mid-air to float) — it is unknown whether the brain would have used that technique or
gotten stuck the same way the scripted replay initially did.

For MKDS, Kirby GBA, and Emerald, there is **no paid-brain datapoint at all** in these reports. The
thesis for those three rests entirely on rig-level (scripted/manual-driver) evidence.

## 4. Implication for PR #129 — options (NOT decided; David's call)

Several v1-DRAFT tasks specify a terminal state — clear Stage 3, clear Level 1-1, finish a lap,
reach Oldale Town — that **nothing in this project has reached by any means yet** (not the oracle
hunts, and for EX02, not even the one paid brain attempt). A task whose success state has never
once been reached cannot have a verified oracle (there is nothing to check a candidate byte's
behavior against at the finish line), and an unverified oracle cannot be scored without risking
exactly the "wrong oracle is worse than none" failure the project's own norms warn against (see the
MKDS stub's and both 2026-07-25 reports' explicit refusal to ship an unverified byte). Freezing
these four tasks as-is means freezing tasks that, under the exam's own scoring design
(`tasks_passed/10`, "no averaging away a bad task"), can currently only ever emit `ORACLE_PENDING`
/ refusal — never a genuine PASS or FAIL_CAPABILITY — no matter how well or poorly a future attempt
plays.

Four options, laid out neutrally:

**(i) Freeze as-is; accept EX02-EX05 bank as ORACLE_PENDING/unscoreable.** Preserves the original
10-task, 5-console-class battery untouched. Costs: a phase-exit exam run would spend real budget
(the doc's own estimate: ~$4-10 each, ~$26 for these four) on tasks structurally guaranteed to
return a refusal rather than a verdict, until a separate oracle-hunt/readiness effort closes the
gap — which could be never, if a hunt keeps not reaching the terminal state.

**(ii) Re-scope the affected tasks to earlier, reachable, already-oracle-verifiable milestones**
(e.g., a checkpoint instead of a full lap for EX05; Birch's Lab `(2,13)` — already reached and
already the most solid Emerald reading — instead of Oldale for EX03). This makes the exam
objectively easier and must be an explicit, documented re-scoping in the frozen v1 text itself
(a new instruction string, a new end-state definition) — never a silent substitution of what
"success" means after the fact.

**(iii) Keep the current terminal-state tasks, but treat reaching-the-state as prerequisite
readiness work that must clear BEFORE freeze** — i.e., freeze only the tasks whose oracle is
already verified now (EX01, EX07, EX08, EX09), and hold EX02-EX05 out of the frozen v1 battery
until each one's own oracle-hunt reaches its terminal state at least once. This mirrors what the
v1-DRAFT document already says for itself about EX05 ("Verifying ... this oracle is a hard
precondition, not optional polish") and EX02 ("a $0 RAM hunt ... is readiness work before freeze")
— i.e., the draft's own text already anticipated this as a pre-freeze gate, not a post-freeze
scoring detail.

**(iv) Drop the affected tasks (EX02-EX05) from v1 entirely.** Guarantees a clean freeze with zero
unscoreable tasks, at the cost of losing the GBA (x2) and NDS coverage the exam was explicitly
designed to include ("Coverage: GB x3, GBA x2, NDS x2, browser x2 — every required world class
clears its `>=2` floor") — dropping EX03+EX04 removes GBA entirely, and dropping EX05 removes NDS
entirely (EX06 is reserve/never-touched and doesn't yet exist as a fallback).

**Recommendation (mine, not decided):** option (iii), applied per-task rather than as one blanket
rule, because the four walls in §2 are different distances from resolved and a single blanket
choice hides that:
- **EX02 (Kirby GB) and EX04 (Kirby GBA)** are the closest to resolved — both hunts identify a
  concrete, cheap next step (one human-played session with RAM sampled live for EX02; a more
  patient platforming pass or a save-state near the goal door for EX04) that could plausibly close
  the readiness gap in one more $0 session. Hold these out of the freeze pending that attempt
  rather than re-scoping them down.
- **EX05 (MKDS)** is the furthest from resolved: two full sessions and ~21,000 combined frames of
  scripted-plus-corrected driving have not cleared even the first of several chokepoints reliably,
  and the report's own read is that closing this gap needs a qualitatively different driver
  (closed-loop, vision-guided steering), not just more of the same technique. I'd re-scope this one
  now — option (ii), to a checkpoint-level milestone using the corroborated `0x022C8094` byte —
  rather than hold the freeze open indefinitely on a harder engineering problem.
- **EX03 (Emerald)** has two stacked blockers, not one: reaching Oldale needs the starter-Pokemon
  quest completed (a materially bigger task than intro-navigation), AND even a clean-looking
  reading there would be untrustworthy without re-running the outdoor-instability falsification
  battery (§5) at the destination. Given that stack, re-scoping to Birch's Lab `(2,13)` — reached,
  interior-stable, no double blocker — is the more pragmatic option (ii) pick over waiting on both
  readiness items to clear.

This recommendation is mine; the four options above are presented neutrally and the choice among
them (or a different one) is David's.

## 5. The #144 correction: outdoor Emerald `map_num` is not a stable location oracle

PR #144 (2026-07-23, per `HANDOFF.md`) merged the original Emerald oracle-hunt report claiming
`map_group`/`map_num` verified "across every one of 12 independent EWRAM snapshots" — but those 12
snapshots were interiors plus a single early outdoor sample; the outdoor reading was never varied
by location. Neither field was ever actually wired into `world_mcp.py` (`GAMES["emerald_gba"]
["watch"]` is still `{}` on `main` today) — the merge banked the finding, not a live oracle.

The 2026-07-25 hunt (`reports/2026-07-25-oracle-gba-exam-hunts.md`) re-tested the outdoor case
specifically and found it does **not** hold: standing in three different, visually-contiguous parts
of the *same* Littleroot Town exterior gave three different `map_num` readings (10 near the truck,
12 near the houses, 14 outside Birch's Lab) while `map_group` stayed `2` throughout — and the third
reading, `(2, 14)`, is a genuine collision against the upstairs bedroom interior's own `(2, 14)`
reading, confirmed by two independent, fully-settled screenshots (one unambiguously the bedroom,
one unambiguously outdoor grass). Each value was individually reproducible at its own location
(not frame noise) — the address is locally stable but not globally unique to "the current map."
This falsifies "map_num = current map" for outdoor areas and makes it unsafe to use as a location
oracle for Oldale (or anywhere else outdoors) without further work — a mechanism (nearest
warp/door target? a per-metatile value?) was considered but not tested this session.

This was caught **before** anything was wired into `world_mcp.py` or a scorer — the stub for EX03
still refuses unconditionally, so no live system trusted the collision-prone reading. It is the
**second instance** of the same pattern the Cave Noire HP oracle hit: `0xD389` looked right on too
few anchors and was wrong (the real HP byte, BCD-encoded, was `0xC120`, per PR #69 and this
project's memory notes); here, `map_num` looked right on too few (and too similar) anchors and was
wrong for the outdoor case. The lesson repeats: a plausible reading confirmed on a handful of
samples that happen to be similar to each other is not the same as a reading stress-tested against
genuinely varied conditions.

## 6. What each hunt banked (so the effort isn't re-done)

- **MKDS** (`reports/2026-07-25-oracle-mkds-lap-v2.md`): `0x022C8090` disqualified a *second*,
  independent way (resets to `0x022C8094`'s value after a stuck/off-track timeout, not just the
  already-known wrong-way decrement); `0x022C8094` remains the best lead but only a single `0->1`
  tick was ever observed (BCD-vs-plain-int still unresolved above value 1); two new low-confidence
  leads (`0x022C8358`, likely another kart's struct copy; the `0x022C8A2x`-`0x022C8A4x` cluster,
  now corroborated across two independent sessions but still unpursued); savestate-chaining
  (one emulator process per driving decision) proven drift-free by an exact full-replay match.
- **Kirby GB** (`reports/2026-07-25-oracle-kirby-gb-stage.md`): all 3 prior candidates
  (`0xD048`, `0xD052`, `0xD3EE`) eliminated with direct evidence (constant-never-changes, or
  volatile around the death/continue event); 8 survivors pinned (`0xC057`, `0xC073`, `0xC07B`,
  `0xD03B`, `0xD19F`, `0xD3A9`, `0xD3BA`, `0xD3CD`, all moving in lockstep — likely mirrors of one
  underlying value); the blocking pillar obstacle solved via Kirby's actual float mechanic
  (jump, then a second `A` press mid-air, then steer) rather than the prior session's mistaken
  mid-air-`B` attempt.
- **Kirby GBA** (`reports/2026-07-25-oracle-gba-exam-hunts.md`, Hunt 2): `world@0x02006014` and
  `score@0x02006020` re-verified under continuous live play (stronger than the prior session's
  disconnected snapshots); `A` confirmed as the jump/float button, `B` eliminated as having no
  effect without an inhale target.
- **Emerald** (`reports/2026-07-25-oracle-gba-exam-hunts.md`, Hunt 1): Birch's Lab interior newly
  pinned at `(map_group, map_num) = (2, 13)`; the outdoor `map_num` instability found (§5); the
  Route 101 NPC gate identified as a hard game-design blocker, not a navigation puzzle.

## Sources

`eval/score_exam_{arc_wa30,emerald_oldale,kirby_gba_level1,kirby_stage3,miniwob_click_checkboxes,
miniwob_focus_text,mkds_lap,red_badge}.py` (`main`, `6966084`); `world_mcp.py` lines 106, 182-191
(`main`); `reports/2026-07-25-oracle-mkds-lap-v2.md`; `reports/2026-07-25-oracle-kirby-gb-stage.md`;
`reports/2026-07-25-oracle-gba-exam-hunts.md`; `reports/2026-07-23-oracle-emerald-hunt.md`;
`reports/2026-07-23-oracle-kirby-hunt.md`; `reports/2026-07-05-northstar-capability-map.md`
(longhaul figures, lines ~15-44); `HANDOFF.md` (PR #143/#144/#145 merge note; #129 status);
`reports/2026-07-22-graduation-exam-v1-definition.md` (read from `origin/docs/exam-v1-definition`
— **not** on `main`, see framing correction above).
