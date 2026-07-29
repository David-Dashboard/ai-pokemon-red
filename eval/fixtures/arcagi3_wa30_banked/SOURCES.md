# Banked ARC-AGI-3 `wa30` oracle fixture -- provenance

Backs `tests/test_score_exam_arc_wa30.py`'s EX09 regression tests (PR #190): a REAL oracle log,
written by `world_mcp.py::ArcAgi3Session._log_oracle` during the banked 2026-07-03 ARC run, scored
directly instead of paraphrased into a synthetic dict. The synthetic `_rows()` helper in that test
file agrees with the scorer by construction and therefore cannot detect the scorer disagreeing with
reality -- which is exactly the defect (`game_id == "wa30"` vs the real `"wa30-ee6fef47"`) that
shipped. This file is the evidence that closes that hole, so its byte-identity IS the point.

Same pattern as `eval/fixtures/cavenoire_hp_oracle/README.md`: a slice of a gitignored `runs/`
recording, committed so a reviewer can verify the claim from a clean checkout.

## The committed file

| | |
|---|---|
| File | `run1_L1of9_oracle.jsonl` |
| Source (gitignored, `runs/` is read-only) | `runs/brain_arcagi3/run1_L1of9/world/oracle.jsonl` |
| Copied | 2026-07-28, PR #190 |
| Size | 7524 bytes |
| sha256 | `651e82ca3fce6ee660dfeacd6fefc0545e0ce773b72826f86fb451493dde77fa` |
| Rows | 48 |
| `game_id` (all rows) | `wa30-ee6fef47` |
| max `levels_completed` | 1 (against `LEVEL_TARGET = 3` -- this trace does NOT pass EX09) |

`.gitattributes` pins `eval/fixtures/arcagi3_wa30_banked/*.jsonl text eol=lf` so autocrlf cannot
rewrite the evidence.

**Why the digest is recorded here.** `_log_oracle` opens the source with mode `"a"` and APPENDS
(`world_mcp.py:2691`). If that run directory is ever re-entered, the source grows while the copy
does not -- and without a recorded digest nobody could tell whether a later re-copy had silently
swapped the fixture for a longer, different trace. `tests/test_score_exam_arc_wa30.py::
test_banked_fixture_matches_recorded_digest` reads the sha256 out of THIS file and asserts the
committed bytes still hash to it, so the prose and the bytes cannot drift apart. It deliberately
does not compare against the source path: `runs/` is gitignored and absent from a clean checkout.

Verify by hand:

    sha256sum eval/fixtures/arcagi3_wa30_banked/run1_L1of9_oracle.jsonl

## Census of ARC oracle logs on disk (2026-07-28)

Six files under `runs/brain_*`, but **five distinct traces** -- rows 3 and 4 are byte-identical
duplicates of each other:

| # | File | Bytes | sha256 (first 16) | Rows | max `levels_completed` |
|---|---|---|---|---|---|
| 1 | `runs/brain_arcagi3/run1_L1of9/world/oracle.jsonl` (**this fixture's source**) | 7524 | `651e82ca3fce6ee6` | 48 | 1 |
| 2 | `runs/brain_arcagi3/run2_memory_datapoint/world/oracle.jsonl` | 8466 | `00b01b6956697575` | 54 | 1 |
| 3 | `runs/brain_arcagi3/run3_L1_completion_framed/world/oracle.jsonl` | 17380 | `c5bb2287f32f4bc7` | 111 | 1 |
| 4 | `runs/brain_arcagi3/world/oracle.jsonl` | 17380 | `c5bb2287f32f4bc7` | 111 | 1 |
| 5 | `runs/brain_skill_ab_armA/world/oracle.jsonl` | 7995 | `494bd679d703acf4` | 51 | 1 |
| 6 | `runs/brain_skill_ab_armB/world/oracle.jsonl` | 20586 | `2a5f238e3de6a5f6` | 131 | 2 |

**Rows 3 and 4 are the duplicate pair** (`cmp` clean, identical sha256). Counting them as two
independent traces would overstate the banked evidence by one run.

Five FURTHER oracle logs carry a `game_id` and are excluded on purpose, not by oversight --
they are synthetic rung-1 harness fixtures, not ARC runs (`game_id: "fixture-push"`,
`win_levels: 254`), and this scorer correctly refuses them as a foreign family:

    runs/skill_rung1_precheck/{ceiling_hit,illegal_action_failure,max_iters_capout,
                               mid_loop_fire,push_delivery}/oracle.jsonl

Eleven `game_id`-bearing oracle logs total. Re-derive the whole census with:

    grep -rl '"game_id"' runs/ --include=oracle.jsonl

**No banked trace reaches `levels_completed >= 3`.** EX09 capability evidence is zero; nothing in
this directory is or implies a PASS.
