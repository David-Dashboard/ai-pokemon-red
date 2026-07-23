# Graduation-exam v1 — scorers, readiness index (2026-07-23)

Status: **$0, offline, no paid run.** Builds one fail-closed OFFLINE oracle scorer per
graduation-exam v1 task — task definitions per **DRAFT exam v1** (`reports/2026-07-22-graduation-
exam-v1-definition.md`, PR #129, still OPEN — the doc's own status line: "v1-DRAFT, NOT FROZEN...
Freeze requires David's sign-off") — that has a WORKING oracle today, mirroring
`eval/score_gate0.py`'s fail-closed pattern (refuse on malformed/missing input, never a guessed
PASS). Every scorer is fixture-tested with SYNTHETIC traces only — no ROM, no held-out/
reserve-title content, CI-safe. This does not run, launch, or pre-register any paid attempt;
that's a separate, later step per `gate-methodology`. **These scorers finalize once David freezes
PR #129** — today's numbers (EX01 badge bit, EX08 seed block, EX02-05 gaps, EX06/EX10 reserve
picks) match the draft as written, but a title/quota/seed change in that review would need a
matching update here before anything is frozen for real.

## Scorable now (real oracle wired today)

| task | scorer | oracle | test |
|---|---|---|---|
| EX01 — Red: first badge | `eval/score_exam_red_badge.py` | `badges` RAM bit 0 (0xD356, `world_mcp.py:177` — same field `score_gate0.py::_red_success` already reads) | `tests/test_score_exam_red_badge.py` |
| EX07 — MiniWoB `focus-text` | `eval/score_exam_miniwob_focus_text.py` | `reward==1.0` on 5 fresh episodes, seeds 0-4 (the harness's own deterministic unseeded counter — no `--seeds-file` path exists for this task) | `tests/test_score_exam_miniwob_focus_text.py` |
| EX08 — MiniWoB `click-checkboxes` (exam-own seeds) | `eval/score_exam_miniwob_click_checkboxes.py` | `reward==1.0` on 5 pinned episodes, seeds 5000-5004 (disjoint from Gate 0's dev 0-4 / paid 1000-1004 blocks) | `tests/test_score_exam_miniwob_click_checkboxes.py` |
| EX09 — ARC-AGI-3 `wa30`: reach level 3 | `eval/score_exam_arc_wa30.py` | `levels_completed >= 3` from `ArcAgi3Session`'s oracle-only log (`world_mcp.py:2502-2505`) | `tests/test_score_exam_arc_wa30.py` |

Shared plumbing (not scorers themselves): `eval/_exam_common.py` (fail-closed jsonl loader +
`python -m eval.score_exam_*` CLI wrapper), `eval/_exam_miniwob_common.py` (the EX07/EX08 success
predicate, mirroring `score_gate0.py::_miniwob_success`, parameterized on task name + seed block so
it isn't duplicated across the two MiniWoB scorers).

## ORACLE_PENDING (oracle still being hunted — stub only, no address fabricated)

| task | scorer | why pending |
|---|---|---|
| EX02 — Kirby's Dream Land: clear Stage 3 | `eval/score_exam_kirby_stage3.py` | `kirby_dreamland`'s only wired oracle is `hp` (0xD086); no stage-counter address identified yet |
| EX03 — Emerald: reach Oldale Town | `eval/score_exam_emerald_oldale.py` | `emerald_gba` registry `watch` is `{}`; GBA oracle hunt running separately (worktree `ai-pokemon-red-oracle-emerald`) |
| EX04 — Kirby (GBA): clear Level 1-1 | `eval/score_exam_kirby_gba_level1.py` | `kirby_gba` registry `watch` is `{}`; same GBA-oracle gap as EX03 |
| EX05 — MKDS: finish one lap | `eval/score_exam_mkds_lap.py` | candidate byte `0x022C8090` is explicitly UNVERIFIED (`reports/2026-07-13-mkds-ab-verdict.md`: "do not claim checkpoint/lap progress from RAM for this run"); oracle-hunt running separately (worktree `ai-pokemon-red-oracle-mkds`) |

Each stub's `score()` always returns `overall: "ORACLE_PENDING"`, exits nonzero, and cites (in its
module docstring) the future oracle-hunt report that must land before it can be replaced with a
real predicate. `tests/test_score_exam_oracle_pending_stubs.py` pins that all four always refuse.

## Explicitly excluded (HELD-OUT LAW)

**EX06 (Metroid Prime Hunters)** and **EX10 (Marble Madness)** are the exam's two reserve/
never-touched titles (`reports/2026-07-22-graduation-exam-v1-definition.md` §1 "Reserve titles").
No scorer, stub, or fixture was built for either — even a refusing stub would be reserve-title
CONTENT committed ahead of the exam's own one attempt, which the held-out law (this project's HARD
LAW: "no held-out/reserve-title content in scorers/fixtures") forbids. These two tasks stay
completely untouched pending David's title sign-off and the exam's own attempt.

## PR #139 review fixes (adversarial review REVISE, addressed 2026-07-23)

1. **False-PASS hole in `score_exam_red_badge.py`.** The original predicate PASSed on a bare
   `badges` bit-0 flip with no corroboration — the reviewer reproduced a false PASS on (a) a badge
   flip with `in_battle` never reaching `2` anywhere, and (b) a badge flip with `party` staying `0`
   for the entire trace (physically impossible). Fixed by mirroring `score_gate0.py::_red_success`'s
   full corroboration chain, not just its corrupt-row filter: the flip must now be preceded by an
   exact `party` 0->1 transition (a starter exists) AND a real battle (`in_battle == 2`, at or after
   the starter exists) strictly before the badge bit flips. Both repro traces are now pinned
   regression tests (`test_repro_badge_flip_without_any_battle_is_refused`,
   `test_repro_badge_flip_with_party_always_zero_is_refused` in
   `tests/test_score_exam_red_badge.py`) that must REFUSE.
2. **Frozen-citation wording.** Every file cited `reports/2026-07-22-graduation-exam-v1-definition.md`
   without flagging that it's PR #129, still OPEN and explicitly not frozen. Fixed by adding a
   "(PR #129 -- v1-DRAFT, NOT frozen; task bars pending David's freeze of that PR)" qualifier to
   every citation (all 4 real scorers, all 4 stubs, both shared helper modules, `eval/README.md`,
   and this report's own status line above).

## Suite

Full repo suite green after this change (2026-07-23):
```
1441 passed, 16 skipped in 55.56s
```

Full repo suite green after the PR #139 review fixes above (2026-07-23):
```
1447 passed, 16 skipped in 54.78s
```
