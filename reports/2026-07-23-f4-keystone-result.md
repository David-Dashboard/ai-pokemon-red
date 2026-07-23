# F4 keystone fingerprint — banked GO/NO-GO result (2026-07-23)

_Status: **NO-GO, killer forced**. Pre-registered per
`reports/2026-07-23-f4-keystone-followup-design.md` §4. Run ONCE per seed, scored UNCHANGED, banked
as-is — not tuned. This converts PR #135's UNCERTAIN into a falsified verdict for A2 (content-based
whole-frame place re-identification, at the tile-fingerprint's existing tolerance, as the online
place-graph re-id mechanism)._

## 1. What was built

- `core/tilemap.py`: new `TileFunctionMap.fp_match(fp_a, fp_b, *, tol=_DEFAULT_TOL) -> bool` —
  reuses `_split`/`_hamming`/`_INTEN_TOL`/`_DEFAULT_TOL` verbatim (the same tolerant compare
  `_matches` already used internally against a tally); no new compare logic.
- `games/pokemon_red/perceiver.py`:
  - `m.setdefault("place_fp", {})` registered alongside the other per-run memory defaults.
  - One fingerprint per place captured at first stable visit (`m["place_fp"].setdefault(place_id,
    TileFunctionMap.fingerprint(frame))`), placed after the transit/mint block so it fires for the
    initial place 0, a fresh/reused `_transit` destination, and a fresh/re-bound recovery anchor —
    one guarded line, no duplication.
  - The `was_unknown` recovery branch (perceiver.py ~398-423) now fingerprints the settled arrival
    frame and checks it against every stored `place_fp`, at the SAME fixed `_DEFAULT_TOL`, before
    minting: exactly one match → re-bind to that place id (its accumulated cells stay in
    `m["places"]`, keyed by id — nothing to "restore" separately); zero or ≥2 matches → mint fresh,
    unchanged from before. No per-place/per-map tolerance, no template, no `map_id` tiebreak.

## 2. Tests added

- `tests/test_tilemap.py`: `test_fp_match_identical_frames_match`,
  `test_fp_match_unrelated_scenes_do_not_match_at_default_tolerance`,
  `test_fp_match_survives_small_noise_perturbation` — all appended after the existing fingerprint
  pins (:24/:31/:35/:48/:57/:115/:145 untouched, still pass).
- `tests/test_perception.py`: `test_lost_recovery_onto_a_known_place_rebinds_instead_of_minting`
  (a settled revisit of an unchanged, previously-anchored scene re-binds to the existing place id,
  no new mint, cells intact) and `test_lost_recovery_onto_an_unseen_scene_still_mints_fresh` (an
  unrelated settled scene still mints — the fail-safe).
- The canary `test_scene_cut_without_a_fade_goes_lost_then_reanchors_fresh`
  (`tests/test_perception.py:252`) and the golden replay
  `tests/test_perceiver_pose_stability.py::test_cutscene_recovers_with_exactly_one_fresh_reanchor`
  both still pass unmodified — an unrelated scene (synthetic random-noise texture in the canary;
  Oak's-lab interior vs. outdoor Pallet Town in the golden replay) does not fingerprint-match at
  `_DEFAULT_TOL=8`, so both still re-anchor fresh as required.
- Full suite: **1479 passed, 16 skipped** (pre-existing skips, unrelated to this change) —
  `UV_PROJECT_ENVIRONMENT=../ai-pokemon-red/.venv-win UV_NATIVE_TLS=true uv run --frozen --no-sync
  python -m pytest -q`.

## 3. The experiment — run exactly as pre-registered

`reports/probes/2026-07-23-f4/f4_drive.py` (unchanged) and `f4_score.py` (unchanged), 4000 steps,
seeds 3 and 7, against the patched perceiver, `roms/PokemonRed.gb` + `runs/red_start.state` (both
present, gitignored, copied in from the primary worktree for this run only). Same fp crop
(whole settled frame) and tolerance (`_DEFAULT_TOL=8`, unmodified) both seeds; `map_id` used by the
scorer only, never inside the match step.

### Seed 3 (`runs/f4_esc_s3/trace.jsonl`)

```
frames=4000 transitions=7 distinct_maps=[0, 37, 38, 40]
map_seq=[38, 37, 0, 37, 38, 37, 0, 40]
SPLIT (map->coined areas, >1 = re-mint): {38: [0, 1, 3], 37: [0, 1, 2, 3], 0: [2, 4], 40: [4, 5, 6]}
MERGE (coined area->maps, >1 = collision): {0: [37, 38], 1: [37, 38], 2: [0, 37], 3: [37, 38], 4: [0, 40]}
V-measure: homogeneity(no-merge)=0.903 completeness(no-split)=0.803 V=0.850
resolution accuracy: 1/7 returns; after >=5 transitions: 1/3
```

### Seed 7 (`runs/f4_esc_s7/trace.jsonl`)

```
frames=4000 transitions=10 distinct_maps=[0, 37, 38, 40]
map_seq=[38, 37, 0, 40, 0, 40, 0, 40, 0, 40, 0]
SPLIT (map->coined areas, >1 = re-mint): {37: [0, 1], 0: [2, 4, 6], 40: [2, 3, 4, 5]}
MERGE (coined area->maps, >1 = collision): {0: [37, 38], 2: [0, 40], 4: [0, 40]}
V-measure: homogeneity(no-merge)=0.993 completeness(no-split)=0.583 V=0.734
resolution accuracy: 2/10 returns; after >=5 transitions: 0/6
```

### Combined against the pre-registered bar (design §4)

| Metric | Bar | Seed 3 | Seed 7 | Combined |
|---|---|---|---|---|
| resolution@≥5 | ≥8/14 | 1/3 | 0/6 | **1/9** |
| completeness | ≥0.7 | 0.803 | 0.583 | fails on seed 7 |
| homogeneity | ≥0.95, no new MERGE | 0.903 (MERGE present) | 0.993 (MERGE present) | **MERGE present, both seeds** |

## 4. Verdict: NO-GO, killer forced

**MERGE appears in both seeds** at the unmodified, pre-registered tolerance — no tuning was
performed. Seed 3: coined areas 0, 1, 3 each bind to BOTH real map 37 and map 38; area 2 binds to
both map 0 and map 37; area 4 binds to both map 0 and map 40. Seed 7: area 0 binds to maps 37 and
38; areas 2 and 4 each bind to both map 0 and map 40. This is exactly the design's named falsifier
(§4): *"any MERGE appears (a confident-wrong bound bought the completeness gain)"* — a re-bind that
is confidently WRONG, not merely a re-mint that is honestly conservative. Before this fix, MERGE was
structurally impossible (every recovery unconditionally minted a fresh id, so no id was ever shared
across two real maps); this fix introduces it. The keystone hypothesis — that a whole-frame
perceptual-hash fingerprint, at the SAME tolerance already proven for 16×16 tile recurrence, can
serve as the online place-graph re-identification signal — **is falsified as specified**, not
merely inconclusive: Pokémon Red's overworld/interior maps recur in a way that fools this
tile-tolerance at whole-frame scale (plausibly the same repeats-constantly GB tile-art property
that KILL-CHEAP'd the `static_objects.py` R0 detector, `HANDOFF.md:456`) — content similarity within
one tileset does not reliably discriminate rooms at this tolerance.

Per the hard pre-registration discipline, no per-place/per-map tolerance, template, or `map_id`
tiebreak was introduced to chase a pass — the result is banked as measured.

## 5. Assumption vs. verified fact

- **Verified fact**: full test suite green (1479/1479, 16 pre-existing skips) after the change; the
  canary and golden-replay tests pass unmodified; both seeds ran 4000 steps to completion with no
  exception; the SPLIT/MERGE/V-measure/resolution numbers above are the scorer's raw stdout,
  unedited.
- **Verified fact**: MERGE was structurally impossible under the pre-fix code (every recovery
  unconditionally minted fresh) — so its appearance here is attributable to this change, not a
  pre-existing scorer artifact.
- **Assumption**: the specific mechanism (which GB tile-art repeats across which two real maps
  caused each merge) was not traced frame-by-frame; the report states the observed SPLIT/MERGE
  pairs from the scorer output, not a per-frame root-cause trace.

## Sources

`reports/2026-07-23-f4-keystone-followup-design.md` (design of record) ·
`games/pokemon_red/perceiver.py:291-299,398-423,478-484` (the change) ·
`core/tilemap.py:111-122` (`fp_match`) · `runs/f4_esc_s3/trace.jsonl`, `runs/f4_esc_s7/trace.jsonl`
(raw traces, gitignored) · `.claude/skills/perception-primitives/SKILL.md` (recurrence-proven, not a
cross-tileset oracle — the same caution this result confirms at whole-frame scale).
