# eval/ — measurement & data tools

Run any tool with `uv run python -m eval.<name>`. These are the **active** rigs; concluded one-off
investigation probes live in [`_archive/`](_archive/) (kept for the record, not day-to-day).

## Perception / perceiver (the cross-game pose backbone)
- `probe_camera_model` — classify a game's camera class (fixed / follow / scroll) from frames.
- `probe_egomotion` — recover self-motion direction across games (RAM-grounded).
- `probe_foreground_motion` — foreground-motion move signal for fixed-camera games.
- `probe_tilemap` — measure tile→function map recurrence/robustness (centerpiece).
- `cross_game` — cross-game generalization harness.
- `replay_tilemap` — end-to-end tilemap-learning validation on real frames.
- `verify_heldout` — held-out verification gate for the camera-model classifier.

## Scoring / ops
- `score_perception` — score a perceiver's SymbolicState vs the RAM oracle.
- `score_red_task` — score the It1 task (get the starter) from a `claude -p` MCP run's oracle+transcript.
- `tune_threshold` — pick move/area frame-diff thresholds from logged runs.
- `index_runs` — catalog `runs/` into a scannable index.

## Capture / calibration / labeling (asset + dataset tools)
- `capture_modes` · `capture_dialog` · `capture_battle` — capture mode/dialog/battle frames.
- `calibrate_font` · `calibrate_battle` — build the Gen-1 glyph table from frames.
- `verify_battle_settle` — validate the battle-settle path on real pixels.
- `label_frames` — interactive hand-label tool (entities/regions/modes).
- `snapshot_labels` — freeze the hand-label dataset into a versioned snapshot.

## Support modules (imported by the above — not run directly)
`dataset_split` (DEV/held-out split) · `probe_phantom_move` · `probe_pose_drift` ·
`vizdoom_flow_ceiling` (3D flow proxies) · `_modality_probe_run` · `report_run` (per-run report scaffold).

> Fixtures + probe deps: `fixtures/`, `requirements-probe.txt`, `collect_corpus.md`.
