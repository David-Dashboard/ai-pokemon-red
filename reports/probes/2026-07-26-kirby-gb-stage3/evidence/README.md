# EX02 Kirby stage-oracle evidence (minimal, committed)

Backs the report claim "**`0xD03B` is Kirby's 0-indexed stage counter**; `0xD19F/0xD3A9/0xD3BA/0xD3CD`
are one-time *past Stage 1* latches" (`reports/2026-07-26-oracle-kirby-gb-stage3.md`, header) so a
reviewer can re-derive the verdict from a clean checkout.

## Contents

- `human_stage3_oracle.jsonl` — the `--watch` oracle log from `runs/2026-07-28_kirby_stage3_human/`
  (David's human play-through of Castle Lololo into Float Islands, 2026-07-28). **1,128 sampled rows
  across TWO recording segments**: the recorder was run twice against the same output dir and opens its
  logs in append mode, so the `step` index restarts `257 -> 0` at file row 258 and `step` is **not** a
  unique key (max `step` is 869). Index rows by **file row**, which is what `verify.py` does.
- `stage3_title_card.png` — 6-panel montage (`step810/818/822/824/828/840`) spanning the transition:
  the warp-star flight, the blanked frame at `step 824` where `0xD03B` flips `1 -> 2`, and the
  **"STAGE 3 FLOAT ISLANDS"** title card at `step 828`.
- `verify.py` — re-derives the verdict from `human_stage3_oracle.jsonl` **alone**.

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

## Reproduce

    uv run python reports/probes/2026-07-26-kirby-gb-stage3/evidence/verify.py

Actual output, 2026-07-28:

    1128 rows | max step 869 | step-index restarts at row(s) [258] -> 2 recording segment(s)
      c1 = 0xD03B: values [1, 2]  transitions 1  at rows [1082]
      c2 = 0xD19F: values [1]  transitions 0  at rows []
      c3 = 0xD3A9: values [1]  transitions 0  at rows []
      c4 = 0xD3BA: values [1]  transitions 0  at rows []
      c5 = 0xD3CD: values [1]  transitions 0  at rows []
      band = 0xD052: values [1, 2, 3, 4, 5, 6, 7, 8, 9]  transitions 69  at rows [18, 21, 22, 25, 27, 28, 33, 34] ...

    c1/0xD03B: 1 -> 2 once, at row 1082 (step 824, frame 9904); 46 rows observed with c1==2 (inside Stage 3)
    c2..c5: constant 1 over every row incl. that Stage-3 window: True

    VERDICT: 0xD03B is the stage counter; the other four are 'past Stage 1' latches.
    BOUND: the Stage-3 window is only the last 46 rows, and Stage 1 (value 0) is NOT in this file -- that anchor is PR #169's.

## Re-collecting a fresh sample

Now that `record.py` persists the mapping, an equivalent capture is:

    .venv-win/Scripts/python.exe record.py --rom "roms/Kirby's Dream Land (USA, Europe).gb" \
      --name kirby_stage3_human --mode human --ram \
      --watch c1=0xD03B,c2=0xD19F,c3=0xD3A9,c4=0xD3BA,c5=0xD3CD,band=0xD052

⚠ The original run also used `--load-state` (both segments start already inside Castle Lololo with
`c1 == 1`); `record.py` does not persist `--load-state` into `meta.json` either, so the exact starting
savestate is not recoverable from the artifacts. The Stage-3 -> Stage-4 confirmation the report requires
before wiring needs a fresh play-through anyway.
