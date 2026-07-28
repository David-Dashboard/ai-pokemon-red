# EX02 Kirby stage-oracle evidence (minimal, committed)

Backs the report claim "**`0xD03B` is Kirby's 0-indexed stage index**, the byte the game itself reads
to decide which stage to load; `0xD19F/0xD3A9/0xD3BA/0xD3CD` are **stale** *past Stage 1* latches that
do not track the current stage" (`reports/2026-07-26-oracle-kirby-gb-stage3.md`, header) so a reviewer
can re-derive the verdict from a clean checkout.

## Contents

**Leg 1 — the human run (observational)**

- `human_stage3_oracle.jsonl` — the `--watch` oracle log from `runs/2026-07-28_kirby_stage3_human/`
  (David's human play-through of Castle Lololo into Float Islands, 2026-07-28). **1,128 sampled rows
  across TWO recording segments**: the recorder was run twice against the same output dir and opens its
  logs in append mode, so the `step` index restarts `257 -> 0` at file row 258 and `step` is **not** a
  unique key (max `step` is 869). Index rows by **file row**, which is what `verify.py` does.
- `stage3_title_card.png` — 6-panel montage (`step810/818/822/824/828/840`) spanning the transition:
  the warp-star flight, the blanked frame at `step 824` where `0xD03B` flips `1 -> 2`, and the
  **"STAGE 3 FLOAT ISLANDS"** title card at `step 828`.

**Leg 2 — the 2026-07-28 follow-up probe (causal + sustained)**

- `causal_map.py`, `causal_map.png` — write `0xD03B = V`, force a game over, take CONTINUE, screenshot
  what loads. `0`→Green Greens, `1`→Castle Lololo, `2`→Float Islands, `3`→Bubbly Clouds,
  `4`→Mt. Dedede; the no-write control loads Castle Lololo. **This is the causal leg.**
- `test1b.py`, `test1b_v{0,2,3}.{jsonl,png}` — 300 samples over 9,000 frames of live play in
  Green Greens / Float Islands / Bubbly Clouds. **Performs no RAM writes at all.** Each row carries
  `hp`, `lives` and Kirby's `x` (`0xD051`) so liveness is provable from the log, not asserted.
  `v0` is the **reverse dissociation**: `0xD03B`=0 in Green Greens while all four latches read `1`.
- `freshboot.py`, `freshboot.png` — cold boot into genuine Green Greens, no writes. All five bytes
  read `0`; note `0xD03B` already reads `0` at frame 10 with `hp`=0/`lives`=0, i.e. **before the game
  is initialised**. This is why `== 0` is not a safe predicate.
- `test2_continue.py`, `test2_boss_fresh.png` — the "stage index vs stages cleared" test. **It did not
  discriminate** (KDL's CONTINUE restarts the same stage); kept because a null result is a result.
- `scan_states.py` — reads `0xD03B` out of every savestate in a directory. Used to establish that no
  Stage-3 state existed anywhere (1,098 scanned, all `1` but one). ⚠ That scratchpad corpus is **not
  committed** (`.gitignore:31` excludes `*.state`), so the script is auditable but the count is not
  re-derivable here.

- `verify.py` — re-derives everything log-based (Leg 1 + the `test1b` tables) from the committed files
  **alone**: no ROM, no savestate, no `ram.bin`. The causal leg needs the ROM and is not re-derivable
  from committed files.

## Column -> address mapping

| column | address | role |
|---|---|---|
| `c1` | `0xD03B` | ★ the stage counter |
| `c2` | `0xD19F` | latch candidate |
| `c3` | `0xD3A9` | latch candidate |
| `c4` | `0xD3BA` | latch candidate |
| `c5` | `0xD3CD` | latch candidate |
| `band` | `0xD052` | Kirby's vertical band / floor index (context only, not a candidate) |

⚠ **How this mapping is known, honestly.** The recorder did **not** persist `--watch` into `meta.json`
at the time of the run (that is now fixed — `record.py` writes `watch` and `watch_arg` into `meta.json`),
and the literal command line was not saved anywhere in the repo. The mapping above was **reconstructed**
from the candidate ordering used by every script in this probe dir (`CAND = (0xD03B, 0xD19F, 0xD3A9,
0xD3BA, 0xD3CD)`) and then **empirically confirmed** against the run's full WRAM dump: for each column,
the set of WRAM addresses whose per-step byte matches that column on **all 1,128 rows** was computed.

    c1   -> ['0xD03B']                              unique
    c2..c5 -> ['0xD19F','0xD3A9','0xD3BA','0xD3CD']  ambiguous as a set
    band -> ['0xD052']                              unique

So `c1 = 0xD03B` and `band = 0xD052` are **pinned by the data**. `c2..c5` cannot be told apart from each
other by this file, because all four of those bytes are constant `1` for the entire run — which is the
finding itself, and means the verdict does not depend on which of the four each column is.

## `ram.bin` is NOT committed

The full 8 KB-per-step WRAM dump (`runs/2026-07-28_kirby_stage3_human/ram.bin`, 9,240,576 bytes =
1,128 x 8 KB) lives under `runs/`, which `.gitignore:27` excludes. It is **not in this repo** and no
committed script reads it. Every report claim that rests on it — the whole-WRAM cross-check and the
"survives two deaths" falsification (HP byte `0xD086` -> `0` around file rows ~414 and ~766) — is
attributed to it explicitly in the report and **cannot be re-checked from this checkout**.

## Savestates are NOT committed either

The probe's resumed states (`resumed_D03B_{0,1,2,3,4,ctl}.state`) are excluded by `.gitignore:31`
(`*.state`) and were deliberately **not** force-added. Regenerate them from the ROM:

    # writes resumed_D03B_{0,1,2,3,4,ctl}.state into causal_map.py's OUT dir, and causal_map.png
    python causal_map.py 0,1,2,3,4,-1        # -1 = the no-write control

`causal_map.py` starts from a Castle Lololo savestate (`s2_start.state` in its `SRC` dir, itself a
scratch artifact). Any state inside Castle Lololo works — that is the only precondition. Then:

    python test1b.py <path>/resumed_D03B_2.state v2 9000     # -> test1b_v2.jsonl + .png
    python freshboot.py                                      # needs no state at all

## Reproduce (committed files only)

    uv run python reports/probes/2026-07-26-kirby-gb-stage3/evidence/verify.py

Actual output, 2026-07-28:

    == A. human run (2026-07-28), sampled oracle rows ==
    1128 rows | max step 869 | step index restarts at [258] -> 2 segments
      c1 = 0xD03B: values [1, 2]  transitions 1  at rows [1082]
      c2 = 0xD19F: values [1]  transitions 0  at rows []
      c3 = 0xD3A9: values [1]  transitions 0  at rows []
      c4 = 0xD3BA: values [1]  transitions 0  at rows []
      c5 = 0xD3CD: values [1]  transitions 0  at rows []
      band = 0xD052: values [1, 2, 3, 4, 5, 6, 7, 8, 9]  transitions 69  at rows [18, 21, 22, 25, 27, 28, 33, 34]
      -> c1 flips 1->2 once at row 1082 (step 824); 46 rows follow. Boss kill at row 1018 [NOT derivable here: read off run frames], so flip is 64 later.

    == B. sustained live play per stage (test1b, 300 samples / 9,000 frames each) ==
      Green Greens   D03B=[0] (0 transitions) | latches=[[1], [1], [1], [1]] | liveness: x takes 56 values, hp [0, 1, 2, 3, 4, 5, 6], lives [2, 3, 4, 5]
      Float Islands  D03B=[2] (0 transitions) | latches=[[1], [1], [1], [1]] | liveness: x takes 36 values, hp [0, 3, 4, 5, 6], lives [1, 2, 3, 4, 5]
      Bubbly Clouds  D03B=[0, 3] (1 transitions) | latches=[[0, 1], [0, 1], [0, 1], [0, 1]] | liveness: x takes 20 values, hp [0, 2, 3, 5, 6], lives [0, 1, 2, 3, 4]
      -> v0 is the REVERSE DISSOCIATION: D03B=0 (Green Greens) while all four latches read 1.
      -> v3's single transition in every column is the title-screen reset after lives ran out.

    VERDICT: 0xD03B tracks the current stage; the four latches do not. The causal leg (writing
    0/1/2/3/4 selects which stage loads) is in causal_map.png -- reproducing that needs the ROM.

⚠ **Setup caveat, stated plainly.** Float Islands and Bubbly Clouds were reached **by writing
`0xD03B`** (plus `0xD086`/`0xD089` to force game overs) — an input-only Lololo kill was never achieved
by automation. So "`0xD03B`==2 during Float Islands" is partly by construction. What is *not*
circular: the game **chose** Float Islands because of that value; it never overwrote the value across
9,000 frames of real play; and the four latches stayed at `1` through a full stage load. `test1b.py`
performs no writes — `0xD03B` was written only in setup, never during measurement.

## Re-collecting a fresh sample

Now that `record.py` persists the mapping, an equivalent capture is:

    .venv-win/Scripts/python.exe record.py --rom "roms/Kirby's Dream Land (USA, Europe).gb" \
      --name kirby_stage3_human --mode human --ram \
      --watch c1=0xD03B,c2=0xD19F,c3=0xD3A9,c4=0xD3BA,c5=0xD3CD,band=0xD052

⚠ The original run also used `--load-state` (both segments start already inside Castle Lololo with
`c1 == 1`); `record.py` does not persist `--load-state` into `meta.json` either, so the exact starting
savestate is not recoverable from the artifacts.

⚠ **A human `buttons.jsonl` is a record, not a script.** `record.py --mode human` stores the *union* of
buttons held across each 12-frame window, discarding their timing, so replaying it does not reproduce
the run — an attempted replay diverged by step 38. Do not build anything that assumes replayability.
