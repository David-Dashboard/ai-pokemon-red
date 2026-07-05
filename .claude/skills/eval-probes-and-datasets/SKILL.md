---
name: eval-probes-and-datasets
description: Probe-first measurement in practice — the eval/ toolkit map, the ground-truth labeling pipeline, the held-out law, and the invariant tripwire tests. Invoke before designing any experiment/probe, adding a scorer, labeling data, or touching a held-out game.
---

# Eval probes and datasets

Thesis (`reports/CONTEXT-BRIEFING.md:74`): **probe = capability prediction; paid run = capability
proof; minimize proof, maximize prediction, keep the predictor calibrated.** This skill is the FREE
end — everything you can measure offline, for $0, before anyone spends real money. **gate-methodology**
owns the paid end (pre-register → one attempt → frozen scorer → banked verdict). If you're about to
design a probe, add a scorer, label frames, or touch a held-out game, you're in this skill; if you're
about to spend on a live `claude -p` run, cross over to **gate-methodology**.

## 1. eval/ toolkit map

Run any tool with `uv run python -m eval.<name>` (`eval/README.md:3`). On the Windows host the env
prefix is `UV_PROJECT_ENVIRONMENT=.venv-win UV_NATIVE_TLS=true uv run --frozen python -m eval.<name>`
in a bash-style shell; in native PowerShell use `$env:UV_PROJECT_ENVIRONMENT=".venv-win";
$env:UV_NATIVE_TLS="true"; uv run --frozen python -m eval.<name>` (the form gate-methodology §5
shows). "Invocation" cells below give the entry point + arg shape, not a full paste-ready line.
**`eval/README.md`'s own index (32 lines) covers only ~24 of the 45 files actually in `eval/`** — it
never mentions any `score_entity_gate*`, `score_gate3d`/`ceiling_gate3d`/`score_a3_precheck`,
`score_skill_rung1`/`score_kirby_skill_precheck`, `score_hud_grounding`/`score_gate_run`,
`score_static_objects`/`score_text_regions`/`score_glyph_cache`, `score_localize`/`validate_localizer`/
`compare_localizers`/`probe_avatar_localize`/`probe_entities`, or `nds_bench` (verified: none of these
16 names appear, checked in full). Those are the **gate scorers** — one per pre-registered gate,
documented in the gate's own report, not the README. Rule: **the gate's pre-reg names its scorer;
never pick a gate scorer by vibes.**

**Perception / perceiver** (`eval/README.md:6-13`):
| tool | measures | invocation |
|---|---|---|
| `probe_camera_model` | classify camera class (fixed/follow/scroll) from pixels+buttons, no RAM feature | `probe_camera_model.py:23` no args |
| `probe_egomotion` | recover self-motion direction cross-game (RAM-grounded scoring only) | `probe_egomotion.py:12` |
| `probe_foreground_motion` | foreground-motion move signal, fixed-camera games | `probe_foreground_motion.py:14` |
| `probe_tilemap` | tile→function map recurrence/robustness (centerpiece) | `probe_tilemap.py:20` `runs/fix2 [runs/fix4]` |
| `cross_game` | cross-game generalization: wall-recall + fail-safe (see §3) | `cross_game.py:7` `--store <dirs> --test <dir>` |
| `replay_tilemap` | end-to-end tilemap validation on real frames | `replay_tilemap.py:10` |
| `verify_heldout` | held-out verification of the camera-model classifier (see §3) | `verify_heldout.py:8` |

**Scoring / ops** (`eval/README.md:15-19`):
| tool | measures | invocation |
|---|---|---|
| `score_perception` | a perceiver's SymbolicState vs the RAM oracle | `score_perception.py:11` `runs/percep_bench/oracle.jsonl` |
| `score_red_task` | the It1 "get the starter" task from a brain run's oracle+transcript | `score_red_task.py:10` |
| `tune_threshold` | pick move/area frame-diff thresholds from logged runs | `tune_threshold.py:10` |
| `index_runs` | catalog `runs/` into a scannable index | `index_runs.py:11` |

**Capture / calibration / labeling** (`eval/README.md:21-26`):
| tool | measures | invocation |
|---|---|---|
| `capture_modes`/`capture_dialog`/`capture_battle` | capture mode/dialog/battle frames for calibration | `capture_dialog.py:14`, `capture_battle.py:13` |
| `calibrate_font`/`calibrate_battle` | build the Gen-1 glyph table from captured frames | `calibrate_font.py:9`, `calibrate_battle.py:10` |
| `verify_battle_settle` | validates the battle-settle path on real pixels | `verify_battle_settle.py:7` |
| `label_frames` | interactive hand-label GUI (entities/regions/mode/OCR) | §2 below |
| `snapshot_labels` | freeze the hand-label corpus into a versioned dataset | §2 below |

**Support modules** — imported, not run directly (`eval/README.md:28-30`): `dataset_split` (§3),
`probe_phantom_move`, `probe_pose_drift`, `vizdoom_flow_ceiling`, `_modality_probe_run` (needs
`.venv-probe4`), `report_run` (per-run report scaffold).

**Gate & fixture scorers** (undocumented in README, §above — group by family):
| family | what it scores | invocation |
|---|---|---|
| `score_entity_gate{,_v2,_v3}.py` | entity-grounding gate (v1 forward-contact FAILED; v2 arithmetically-unreachable-bar FAILED, `b_k=0.812`; v3 current, repairs bar + macro-interior exclusion + skill guard) | v3: `score_entity_gate_v3.py:671` positional `run_dir` (reads `<dir>/transcript.jsonl` + `<dir>/world/{oracle,skills}.jsonl`); v1/v2: positional `transcript oracle` |
| `score_gate3d.py` / `ceiling_gate3d.py` / `score_a3_precheck.py` | GATE-3D-A1(+A2) live scorer / free scripted-optimum ceiling / A3 onset-rule precheck | `score_gate3d.py:373-376` positional `oracle grounding seeds baselines`; `ceiling_gate3d.py:301-307` `--seeds-file --out --gate-bar`; `score_a3_precheck.py:247-250` `--score-only GROUNDING_JSONL` \| `--replay` |
| `score_skill_rung1.py` / `score_kirby_skill_precheck.py` | free pre-checks gating a paid skill-compilation run BEFORE scheduling it | `score_skill_rung1.py:244-247` `--dry` (default) \| `--score-only SKILLS_JSONL`; `score_kirby_skill_precheck.py:737-745` `--dry`\|`--all`\|`--measure-overhead`\|`--check-entities`\|`--seam-physics` |
| `score_hud_grounding.py` / `score_gate_run.py` | ADR-002 HUD-grounding gate: hand-detector vs RAM `hp` oracle / the live-brain HYP-DECLARE-REJECT counterpart | `score_hud_grounding.py:31` `--run eval/fixtures/cavenoire_hp_oracle --oracle-from-ram` |
| `score_static_objects.py` / `score_text_regions.py` / `score_glyph_cache.py` | fixture-scored referential-grounding / glyph-read gates (see §4) | `score_static_objects.py:22-23`, `score_text_regions.py:22-23`, `score_glyph_cache.py:35-36` |
| `score_localize.py` / `validate_localizer.py` / `compare_localizers.py` / `probe_avatar_localize.py` / `probe_entities.py` | avatar-localization + entity-detector precision/recall vs `datasets/labels/v2` hand labels | `score_localize.py:13` no args; `validate_localizer.py:10-11` `[game-substring]`; `probe_entities.py:15-16` `[game filter]` |
| `nds_bench.py` | NDS ROM ontology sweep, subprocess fan-out | `nds_bench.py:6-7` `--roms-dir roms/nds --steps 150 [--report ...]` |

## 2. Ground-truth pipeline

```
# 1. Record raw frames + buttons (+ optional RAM dump, oracle only — never an agent input)
uv run python record.py --rom roms/Kirby's...gb --name kirby_auto --mode auto --steps 3000 [--ram]
uv run python play_record.py --rom roms/PokemonRed.gb --load-state start.state --name kanto1

# 2. Hand-label a sample of frames (GUI: tkinter, needs a display)
python -m eval.label_frames runs/kirby_auto --n 50        # resumable: runs/<game>/frame_labels.json

# 3. Freeze the current corpus into a committed, versioned snapshot
uv run python -m eval.snapshot_labels --version v2
```

`label_frames.py` uses farthest-point sampling on an 8x8 signature (`:52-67`) so the ~N
picked frames are visually diverse, not N near-duplicates from a static run. Per-frame record keys:
`frame, mode, avatar[], enemy[], item[], text[], health[], exit[], npc[]` (7 box categories +
`mode` ∈ gameplay/menu/dialog/battle/transition/title/other). Boxes are `[x0,y0,x1,y1]` over the
native 160x144 frame; `text`/`health` boxes carry a **5th element** — the ground-truth OCR string
(verified: `datasets/labels/v1/2026-06-23_red_resume.json` records have `["x0","y0","x1","y1",""]`
5-tuples for `text`/`health`, plain 4-tuples for `avatar`).

Committed snapshots: `datasets/labels/v1/` = 7 games / 110 frames / 600 boxes / 48 read-values;
`datasets/labels/v2/` = 13 games / 250 frames / 1146 boxes / 48 read-values, **OCR coverage sparse**
(48/661 text+health boxes = 7%, concentrated in early games — `datasets/labels/v2/manifest.md:4`
explicitly flags this as "not yet cross-world"). Frames themselves live in gitignored `runs/`; the
labeled JSON + auto-generated `manifest.md` under `datasets/labels/vN/` are the **committed artifact**
(raw `runs/` data is append-only per **safety-invariants** law 2 — never hand-edit a label JSON's
source frames, only the label boxes).

## 3. THE HELD-OUT LAW

`eval/dataset_split.py:3-6` — **HARD RULE: never develop, tune, calibrate, or pick thresholds against
the HELD-OUT games. They are touched ONLY at final verification.** Data may be collected for them; it
is never looked at while building.

`HELDOUT` (`:30-36`), one game per perception axis (`:9-14`) so one verification run stresses all four
camera/view challenges at once:
| axis | held-out game |
|---|---|
| follow (real-time, 8-way diagonal) | Crystalis |
| flip-screen / static | Zelda: Link's Awakening |
| side-scroll | Super Mario Land |
| pseudo-3D / other view | F-1 Race |
| 3D / first-person | Doom (ViZDoom `my_way_home`) |

`is_heldout_rom`/`is_heldout_run`/`partition` (`:39-66`) match substrings case-insensitively against
`meta.json`'s ROM name **and** the run-dir name (some recorders, e.g. ViZDoom, write no meta ROM).
Cave Noire is **deliberately DEV**, not held out (`:19-22`) — its camera never scrolls (single-screen
rooms), so holding it out too would double-count a `fixed` unit as both dev and test (silent leakage).

**The two sanctioned consumers**, both zero-shot against `HELDOUT`:
- `eval/cross_game.py --store <dev runs> --test <heldout run>` (`:7`) — builds the tile→function map
  on STORE runs, scores WALL-RECALL on TEST: on tiles never seen, does the hash fail safe (low
  coverage → "novel, explore") rather than confidently mispredicting a wall as walkable?
- `eval/verify_heldout.py` (`:1-9`) — zero-shot classifies each held-out game's camera model from a
  classifier built only on the dev corpus, reporting where it lands (`HELDOUT_RUNS`, `:23-28`).

Violating this silently converts every generalization claim in this project into overfitting — there
is no scorer that catches a threshold quietly tuned against Crystalis before the "held-out" run.

## 4. Fixture discipline

`eval/score_static_objects.py:1-5`: **the fixture is built FIRST, before the detector is tuned against
it**, so the detector cannot be fit to the grader by construction. Same discipline in
`score_text_regions.py:4-8` ("built BEFORE the detector was scored against it").

| fixture | consumer(s) |
|---|---|
| `cavenoire_hp_oracle/` | `score_hud_grounding.py` (`--run eval/fixtures/cavenoire_hp_oracle --oracle-from-ram`) |
| `starter_cutscene_pose/` (20 frames) | `tests/test_patience.py`, `tests/test_perceiver_pose_stability.py` |
| `kirby_title_menu/` (2 frames) | `tests/test_patience.py`, `tests/test_perception_plugin_render.py` |
| `static_objects_pokeball/` (20 PNGs: 8 lab target + 12 distractor — grown from the docstring's stated 5+9 as the gate was reconfirmed; verified on disk) | `score_static_objects.py` |
| `text_regions/` (labels.json + hand-labeled PNGs across 6 GBA sweep games + distractors) | `score_text_regions.py`; `tests/test_score_text_regions.py` uses a synthetic in-file fixture instead (CI-safe, no dependency on the real hand-labeled set) |
| `vizdoom_movers/` (42 files, curated pairs) | `tests/test_stationary_movers.py` |
| `vizdoom_yaw/` (60 files incl. `known_limits/`) | `tests/test_yaw_flow.py` (regression floor + a pinned known-failure subset, `:7-17,85`) |
| `gate3d_seeds.json` / `gate3d_baselines.json` / `gate3d_ceiling_results.json` | `score_gate3d.py`, `ceiling_gate3d.py`, `score_a3_precheck.py`, `tests/test_gate3d_baselines.py:30`, `tests/test_score_gate3d.py:31` |
| `skill_rung1_push_macro.json` | `score_skill_rung1.py` (`--dry` mode, canned grid-sequence scenarios) |

Committed fixtures under `eval/fixtures/` get a regression-pin test (a test that asserts a specific
measured number on the committed data, e.g. `test_yaw_flow.py:67`'s pinned values) — a fixture without
a pinning test can silently drift with no red build to catch it.

## 5. Tripwire tests (drift detectors)

Cross-ref **session-start**'s gate-first mindset: these are the tests that fire when someone edits the
frozen layers instead of following the change process.

- **`tests/test_contract_frozen.py`** — `PINNED_SHA256` (`:33`) over `core/contracts.py`'s bytes and
  golden vectors `contracts/golden_vectors_v1.json` round-trip through every pinned dataclass. A red
  here means the wire contract changed; the fix is CONTRACT.md's process (human approval, version
  bump, new hash, new golden vectors, DECISIONS.md entry) — **never** a casual edit to make it pass
  (`:1-12` says this explicitly, addressed to AI assistants).
- **`tests/test_no_ram_leak.py`** — plants RAM sentinel values, asserts none of them (and no key
  containing a forbidden substring: `ram, wram, oracle, map_id, true_, gt_, ground_truth, watch`,
  `:21`) crosses into what the agent's `Observation` actually sees. This is ADR-001's non-leaking
  oracle wall (**safety-invariants** law 2, "oracle never on the wire") made executable.
- **`tests/test_import_boundaries.py`** — `core/` never imports `games/`; nothing imports `aria`/
  `ai_aria` (the brain is a decoupled HTTP service); a game package never imports a sibling game
  package; a lean game (anything but `pokemon_red`) may not carry its own `emulator.py`/`plugin.py`,
  and its `perceiver.py` must stay ≤80 lines of thin config, not an inlined body (`:104-108`). "Do NOT
  edit this test to make it pass" (`:4`) — the fix is always in the offending import, not the test.

## 6. Honesty norms

A probe that says **no** is a successful probe — a banked FAIL stays on the books, it is not
"fixed" by re-tuning until it passes:
- `core/static_objects.py`'s general R0 detector: **KILL CHEAP**, recall 0.0 / precision 0.0 /
  **154 phantoms** (`HANDOFF.md:456`; live-reproduced 2026-07-05 by running
  `uv run python -m eval.score_static_objects` against the committed fixture — the module
  docstring's own "236-341" figure (`static_objects.py:19-22`) does NOT reproduce under any swept
  config and should not be trusted) — GB tile-art is full of naturally-repeating equal blobs, so
  "distinct blob" fires everywhere. A color-saturation-gated variant hit 0.86/0.76/0 but was
  explicitly rejected as non-generalizing (palette-specific).
- `core/text_regions.py`'s R0 edge-density detector: **FAIL**, recall 0.27 vs the pinned 0.85 bar
  (`HANDOFF.md:187`) — textured backdrops defeat plain edge-density; an R1 cache-driven candidate is
  queued, not yet built.

Never tune a detector until the fixture says it fails, then tune only within the fixture's own bar.
`eval/cross_game.py`'s metric of record is **wall-recall**, not aggregate accuracy — it matches the
real downstream cost: a false "walkable" sends the agent into a wall, a false "novel" just costs one
extra exploratory step. An unseen tile must predict `None` ("novel → explore"), never a confident
wrong wall call — the same fail-safe-over-recall rule as the static-object/text-region phantom-count
metrics above.

## 7. Adding a new probe or scorer

- Follow `eval/README.md`'s existing conventions (module-runnable, `uv run python -m eval.<name>`,
  a usage line in the module docstring).
- **Commit the fixture first** — before the detector exists, so it cannot be fit to the grader
  (§4). Hand-label with `label_frames.py` + `snapshot_labels.py` if it's a general-purpose fixture;
  build a small standalone one (à la `static_objects_pokeball/`) if it's gate-specific.
  Cross-check any new fixture against the **held-out law** (§3) — never build/tune it from a
  held-out game's runs.
- **Add a regression-pin test for the fixture** (§4: a fixture without a pinning test "can silently
  drift with no red build to catch it") — a test that asserts the measured numbers on the committed
  data, à la `tests/test_yaw_flow.py`.
- Pin every threshold/constant in the scorer file itself (a docstring section naming each number),
  same style as `score_gate3d.py`'s "copied from those sections, not re-derived or re-tuned here."
- Add its one-line entry to `eval/README.md` under the matching section — the gate scorers above
  show what happens when this step is skipped (16 files with zero README trace).
- If the probe's question gets answered (pass or kill), move it to `eval/_archive/` — imports only
  the active `eval/` modules, run via `python -m eval._archive.<name>` if ever needed
  (`eval/_archive/README.md`).

## Sources
- `reports/CONTEXT-BRIEFING.md:65-77` (probe-first slogan)
- `eval/README.md` (full file, 32 lines — verified it omits the 16 gate-scorer/probe names listed above)
- `eval/dataset_split.py` (full file, 66 lines — HARD RULE, `HELDOUT`, `is_heldout_rom/run`, `partition`)
- `eval/cross_game.py:1-45`, `eval/verify_heldout.py:1-28`
- `eval/label_frames.py:1-70`, `eval/snapshot_labels.py` (full file), `record.py:116-139`, `play_record.py:77-81`
- `datasets/labels/v1/manifest.md`, `datasets/labels/v2/manifest.md`, `datasets/labels/v1/2026-06-23_red_resume.json`
- `eval/score_static_objects.py:1-40`, `eval/score_text_regions.py:1-20`, `eval/fixtures/static_objects_pokeball/` (dir listing, 20 PNGs)
- `eval/fixtures/{vizdoom_movers,vizdoom_yaw,starter_cutscene_pose,kirby_title_menu,text_regions}/` (dir listings)
- `tests/test_contract_frozen.py:1-53`, `tests/test_no_ram_leak.py` (full file), `tests/test_import_boundaries.py` (full file)
- `HANDOFF.md:187,446-456` (static-object KILL CHEAP, text-region R0 FAIL, exact numbers)
- Cross-reference (do not duplicate): `.claude/skills/gate-methodology/SKILL.md` (the paid end this
  skill feeds), `.claude/skills/safety-invariants/SKILL.md` (law 2 append-only oracle logs, law 7
  constancy — mirrored, not restated, in §5/§6 above), `.claude/skills/session-start/SKILL.md` (the
  probe-first slogan's canonical statement).
