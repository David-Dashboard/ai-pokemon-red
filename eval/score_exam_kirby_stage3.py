"""Fail-closed OFFLINE oracle scorer for graduation-exam v1 EX02 -- Kirby's Dream Land: clear Stage 3.

Oracle: `stage` @ `0xD03B`, the game's 0-INDEXED stage SELECTOR (0=Green Greens, 1=Castle Lololo,
2=Float Islands, 3=Bubbly Clouds, 4=Mt. Dedede), wired into `GAMES["kirby_dreamland"]["watch"]`
alongside `hp` (0xD086, a plain 0-5 HP int) by PR #180. Established CAUSALLY -- writing the byte
before a stage load determines which stage the game loads -- in
reports/2026-07-26-oracle-kirby-gb-stage3.md. Reads only `oracle.jsonl` `watch` rows: never the
transcript, never a model self-report. Mirrors `eval/score_gate0.py` / `eval/score_exam_red_badge.py`
fail-closed shape (corrupt-glitch-row filter, then refuse rather than guess on anything malformed).

THE PREDICATE, in plain language: PASS iff somewhere in the run there are at least two CONSECUTIVE
non-glitch oracle rows whose `stage` is >= 3 while `hp` is >= 1. That is: Stage 3 (Float Islands) was
CLEARED and the game loaded Bubbly Clouds or deeper, with Kirby alive there for more than a single
sample.

  Why EXISTENTIAL (`any`), not a final-value read. `0xD03B` selects the CURRENT stage; it is NOT a
  monotone "stages cleared" counter. It was directly observed going 3 -> 0 when lives ran out and the
  title screen reset it (`test1b_v3.jsonl`, the Bubbly Clouds run). So a run that genuinely clears
  Float Islands and then dies out ends at 0, and a final-value read would score that FAIL -- worse,
  its final row would be indistinguishable from "never started". For the same reason this scorer
  deliberately does NOT refuse on a decrease: unlike `score_exam_arc_wa30.py`'s `levels_completed`,
  going backwards here is normal, documented behaviour, not a corruption signal.

  Why NOT `== 0`. `0` is Green Greens, but it is ALSO the uninitialized cold-boot value (at frame 10
  `0xD03B`=0 with hp=0 and lives=0) and the post-game-over title-screen value. `0` cannot distinguish
  progress from never-having-started, so no predicate keyed on it is meaningful.

  Why `>= 3` and not `== 3`. Equality would reject a run that overshoots into Mt. Dedede (`4`), which
  has plainly also cleared Stage 3. `>=` is the right shape for a stage index.

  Why NOT `>= 2`. `2` is Float Islands -- Stage 3 ITSELF, i.e. merely REACHING it, one stage short of
  the task's "advancing past Stage 3". `>= 2` is the looser bar that the evidence we happen to hold
  supports best, and choosing it FOR that reason would be exactly the post-hoc bar adjustment this
  project's gate methodology exists to prevent. If the bar is wrong it gets changed deliberately in
  the exam document, not quietly in a scorer.

  Why the two-consecutive-row floor. In real play the value is extremely sticky: 9,000 frames held at
  2 in Float Islands and 4,740 at 3 in Bubbly Clouds, with 0 spurious transitions. A lone row at >= 3
  surrounded by lower rows is therefore anomalous -- a substituted/corrupted sample, not a stage. Two
  consecutive rows means the value survived at least one whole observe interval. `hp >= 1` is the
  "game actually in play" gate the oracle report asks for (it names `lives > 0`; `lives` is not in
  this world's `watch`, `hp` is, and hp=0 is exactly the boot/dead signature).

** BAR PROVENANCE -- WHERE `>= 3` COMES FROM, AND THE ONE THING A PASS WOULD NOT ESTABLISH.
The bar is `>= 3` because reports/2026-07-22-graduation-exam-v1-definition.md (merged) words EX02's
end state as "a stage/level counter ... advancing PAST Stage 3". Past Stage 3 == Bubbly Clouds ==
index 3. Value 3 is itself well established, CAUSALLY: writing `0xD03B = 3` before a stage load makes
the game load Bubbly Clouds, and the value then held 4,740 frames of live play through deaths and a
CONTINUE prompt before the title screen reset it.

!! But state this plainly, because a PASS here will otherwise be read as more than it is: **the
`2 -> 3` increment has NEVER been observed in natural play.** Every `3` on record was produced by
WRITING memory. The only increment ever seen from the game itself is `1 -> 2`, once, in a human run.
The fourth retraction in reports/2026-07-26-oracle-kirby-gb-stage3.md covers exactly this, and the
bound it names -- *observe `0xD03B` transition `2 -> 3` across a real Stage-3 -> Stage-4 completion,
with no memory write anywhere in the run* -- is **STILL OPEN**. Nobody has cleared Float Islands.

So: the scorer is sound (the byte is the stage selector, causally, and `3` means Bubbly Clouds), but
EX02's bar rests on a transition only ever produced by construction. A future session MUST NOT read a
PASS here as also discharging that bound. A PASS would be the first natural observation of the
increment, which makes such a run worth inspecting on its own -- it is not a substitute for the
bound's own evidence.

!! Not usable on `runs/2026-07-28_kirby_stage3_human/`: that capture predates the wiring, so its
oracle rows carry `c1`..`c5`/`band` columns (raw candidate addresses), not `stage`/`hp`. It is a
column-name mismatch, not a data problem -- this scorer correctly refuses it rather than guessing
that `c1` is `stage`. (That run reached Float Islands only, i.e. `2`, so it would not clear this bar
even with the column names fixed.)

Usage: `uv run python -m eval.score_exam_kirby_stage3 <oracle.jsonl>`
"""
from __future__ import annotations

from eval._exam_common import run_cli

TASK_ID = "EX02"
STAGE_INDEX_TARGET = 3      # Bubbly Clouds == past Stage 3, 0-indexed (see BAR PROVENANCE above)
_MAX_STAGE_INDEX = 4        # Mt. Dedede; KDL has five stages, so a higher value is not a stage index
_MIN_CONSECUTIVE_ROWS = 2   # a lone row at the target is a transient, not a stage
# The full watch dict this world logs (world_mcp.py GAMES["kirby_dreamland"]["watch"]) -- used only
# to detect the corrupted-glitch-row signature, mirroring score_gate0.py's _is_corrupt_glitch_row.
_WATCHED_KEYS = ("hp", "stage")


def _is_corrupt_glitch_row(watch: dict) -> bool:
    return all(watch.get(k) == 0 for k in _WATCHED_KEYS)


def _plain_int(value: object) -> bool:
    """True only for a genuine RAM-byte-shaped int -- bool explicitly excluded (`True == 1` would
    otherwise pass a numeric check meant for a real byte; same reasoning as score_exam_red_badge)."""
    return not isinstance(value, bool) and isinstance(value, int)


def _kirby_stage3_success(rows: list[dict]) -> tuple[bool, list[str]]:
    watches = [row.get("watch") for row in rows if isinstance(row.get("watch"), dict)]
    if not watches:
        return False, ["kirby_stage3_no_watch_rows"]

    kept = [w for w in watches if not _is_corrupt_glitch_row(w)]
    if not kept:
        # Every row was the all-fields-zero signature: a cold-boot-only trace and the PyBoy
        # polling-sampler glitch look identical here, and neither is evidence of any stage.
        return False, ["kirby_stage3_all_rows_corrupt_glitch"]

    stages = [w.get("stage") for w in kept]
    hps = [w.get("hp") for w in kept]
    if any(not _plain_int(s) or not 0 <= s <= _MAX_STAGE_INDEX for s in stages):
        return False, ["kirby_stage3_missing_or_invalid_oracle_field"]
    if any(not _plain_int(h) or not 0 <= h <= 255 for h in hps):
        return False, ["kirby_stage3_missing_or_invalid_oracle_field"]

    at_target = [s >= STAGE_INDEX_TARGET for s in stages]
    if not any(at_target):
        return False, ["kirby_stage3_never_cleared_stage_3"]

    in_play = [t and h >= 1 for t, h in zip(at_target, hps)]
    if not any(in_play):
        # The byte claims Bubbly Clouds while Kirby has 0 HP on every such row -- the boot/dead
        # signature, not a stage that was played. Refuse rather than credit it.
        return False, ["kirby_stage3_cleared_only_while_not_in_play"]

    streak = best = 0
    for ok in in_play:
        streak = streak + 1 if ok else 0
        best = max(best, streak)
    if best < _MIN_CONSECUTIVE_ROWS:
        return False, ["kirby_stage3_cleared_only_as_single_row_transient"]

    return True, []


def score(rows: list[dict]) -> dict:
    ok, failures = _kirby_stage3_success(rows)
    return {"schema_version": 1, "task_id": TASK_ID, "task": "kirby_dreamland_clear_stage_3",
            "overall": "PASS" if ok else "FAIL_CAPABILITY", "failures": failures}


def main() -> int:
    return run_cli(TASK_ID, score)


if __name__ == "__main__":
    raise SystemExit(main())
