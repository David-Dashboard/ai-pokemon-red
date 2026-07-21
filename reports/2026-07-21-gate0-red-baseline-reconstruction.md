# Gate 0: Option-A reconstruction of the cold Red human baseline (2026-07-21)

## Why Option A

David's first (2026-07-21) capture with `tools/capture_gate0_baseline_red.py` was a genuinely COLD
attempt -- one shot, per the DAVID_BASELINES.md "one cold attempt per task" exam law. The live rig
detects completion by running `eval.score_gate0._red_success` after every sampled row; at the time,
its glitch-row filter was too narrow (fixed on `main` by PR #121, same day: "narrow the glitch-row
filter to the full corruption signature"), so the live detector never fired even though David had, in
fact, completed the task. The session was archived as `human_metrics.INCOMPLETE_1784593974.json`
instead of the canonical baseline, and David played a second, no-longer-cold attempt.

David decided (2026-07-21) on **Option A**: reconstruct attempt 1's true completion numbers offline
against the now-fixed `_red_success`, rather than bank attempt 2 (not cold) or discard genuinely cold
data over a scorer bug. `tools/reconstruct_gate0_red_baseline.py` replays the archived trace; it never
plays or invents a single input.

## Method

Replay the trace row by row; after each row, call the real, imported `_red_success` over every row
seen so far (never copied) -- the same growing-prefix check the live rig performs. The first
succeeding prefix pins the completion row (`t_done` = that row's `t`). Clock start mirrors the rig
(timer starts on first keypress): `t_first_input` = `input_event_times[0]`, cross-checked against the
INCOMPLETE artifact's own `started_at` (must agree within 0.01s -- the rig sets both in one loop
iteration). `wall_clock_s = t_done - t_first_input`; `primitive_actions` = count of
`input_event_times <= t_done`; `input_event_times` themselves are trimmed to `<= t_done`.

## Result

- **completion_row_index = 939** (of 1043 rows)
- **wall_clock_s = 233.288**, **primitive_actions = 271**
- `started_at` 2026-07-21T00:28:34.739147+00:00, `completed_at` 2026-07-21T00:32:28.026671+00:00

The archived INCOMPLETE artifact (timed until David gave up, under the buggy detector) recorded
259.519s / 273 actions -- both higher: he'd already finished ~26s and 2 presses earlier than the live
detector noticed. The reconstructed numbers are strictly lower, i.e. a *harder*, not inflated,
baseline.

Written to `runs/gate0_human_baseline/red/human_metrics.json` (refuses if that file already exists).
Carries the live rig's exact schema plus provenance fields (`reconstructed`,
`reconstruction_method`, `reconstruction_source_trace_sha256`,
`reconstruction_source_incomplete_sha256`, `reconstructed_at`, `completion_row_index`). These extra
keys are not rejected: `eval.score_gate0._verify_sources` only pulls a named-key allow-list off the
human artifact (verified by `tests/test_reconstruct_gate0_red_baseline.py::
test_reconstructed_artifact_passes_frozen_verify_sources`, reproducing
`test_score_gate0.py::test_frozen_source_pins_load_exact_artifacts`'s check against the real
reconstructed artifact).

## Hashes (every input + the output)

| artifact | sha256 |
|---|---|
| attempt-1 trace (`attempt_archive/oracle.incomplete1_1784594056.jsonl`) | `3bf9bc75ce6c382fcfea1090cfcb35e0929b75e6d873ec11def83b8d4bce2366` |
| attempt-1 INCOMPLETE marker (`attempt_archive/human_metrics.INCOMPLETE_1784593974.json`) | `35d62b72db912b8a1f8bc2ec2414206468877ad4858a3189610a52632642e1a1` |
| ROM (`roms/PokemonRed.gb`, carried) | `0602291f922443faf9d6b3a31948e37607a5f487ed8927892f926f86f4105700` |
| savestate (`runs/red_start.state`, carried) | `a968b0b35cf49892e49178766f0e5ad7d38b689b0f1c4e248ceed4eea7d112ef` |
| **reconstructed output** (`runs/gate0_human_baseline/red/human_metrics.json`) | `5144a5b36a29453c5f07ceba8336f3752055e0437e80f50d61418d61be686264` |

## Disclosure

Both attempts exist, fully archived, and both attempts' LIVE detection failed from the same
now-fixed bug:

- **Attempt 1** (`attempt_archive/`): the reconstruction source above -- `_red_success` (post-#121)
  finds completion at row 939; the live (pre-#121) detector never fired.
- **Attempt 2** (`oracle.jsonl` + `human_metrics.INCOMPLETE_1784594491.json`, still at the live
  canonical paths, untouched by this work): its own live artifact recorded `success: false`
  (HP-reached-zero, map-changed-during-exit) under the pre-#121 detector. Running the post-#121
  `_red_success` offline over attempt 2's own full archived trace *also* finds a completion (row 821
  -- the same row PR #121's regression fixture `gate0_red_human_attempt2_completion.jsonl` pins),
  consistent with the same bug producing a spurious later failure instead of the real earlier
  success. Reported as an observation, not diagnosed further: attempt 2 is reference material only,
  per David's decision to bank attempt 1. Nothing under attempt 2's files was read for, or fed into,
  the reconstructed artifact.

## Verification

- Ran `tools/reconstruct_gate0_red_baseline.py` for real against the archived attempt-1 evidence,
  producing the artifact and hash above.
- `tests/test_reconstruct_gate0_red_baseline.py` (15 cases): completion-row search, wall-clock/
  primitive-actions arithmetic and `<=` boundary trimming, clock-start cross-check, all refusal
  paths (never-completes trace, empty input events, clock inversion, started_at mismatch, existing
  output file), frozen-loader compatibility -- built on the already-committed
  `gate0_red_human_attempt2_completion.jsonl` / `gate0_red_human_attempt1_no_movement.jsonl`
  fixtures (CI-safe; never the private evidence dir).
- Full suite: `1297 passed, 16 skipped`
  (`UV_PROJECT_ENVIRONMENT=.venv-win-recon UV_NATIVE_TLS=true uv run --frozen pytest -q`).
