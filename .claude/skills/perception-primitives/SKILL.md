---
name: perception-primitives
description: The core/ perception toolbox map — what signal already exists, what question it answers, and the rules for extending it. Invoke when perception breaks on any world, when a new world's perceiver needs a signal, or BEFORE writing any new perception code — the sin this prevents is bespoke duplicated perception code and fabricated outputs.
---

# Perception primitives — the core/ toolbox map

Perception, not planning, is this project's bottleneck (`reports/CONTEXT-BRIEFING.md` "Background":
the closest comparable system, Cradle, fails on screen-object localization, not reasoning — see
**architecture-and-seam**'s claim that every prior game's ceiling was world-side perception, never
the brain). `core/` already holds ~25 perception primitives covering ego-motion, localization,
segmentation, tilemap learning, text/glyph routing, modality, and the System-2 escalation ladder.
Before writing a single line of new perception code, know what exists (the inventory below) and the
constitution it must follow — otherwise you re-derive a worse copy of something already lifted, or
you fabricate a value the rest of the system will trust as truth.

## The constitution digest (`reports/north-eye-perception-constitution.md`)

Four layers, meaning flowing upward (:48-54): **L0 sensors** (raw frame/buttons) → **L1 signals,
meaning-free** (frame-diff, ego-shift, blob, hash — numbers, not nouns) → **L2 grounded structures**
(pose, a tracked entity, a localized avatar — L1 + the action↔sensor loop) → **L3 semantics** ("that
region is my HP" — the brain *hypothesizes*, behaviour *grounds*; never hand-asserted at L1).

Every primitive must fill the **seven-slot contract** (:63-77) or it is mis-designed; the two that
matter most day to day:
- **Output contract (slot 5):** value + confidence + an explicit `None`/"can't tell". **Fabrication is
  the cardinal sin** (:72-73) — returning a made-up value when the signal is absent is what
  dead-reckoning did wrong. The `MoveSignal` hand-picked-per-world design is the canonical violation
  named in the doc (:75-76, :116-120): a hard verdict with no confidence, selected by a human label
  instead of grounding payoff.
- **Grounding (slot 2):** calibrated/validated by **action↔sensor correlation against truth**, not
  appearance or magnitude — "the avatar is not the brightest or biggest mover; it is the thing your
  buttons move" (`core/localize.py:2-3`).

**The Realizer Ladder** (:87-99) is the project's technology budget for slot 4 (implementation), and
is explicitly swappable without touching slots 1-3: **R0** cheap pixel ops (numpy/PIL — most of
`core/` lives here) → **R1** classical CV + tiny fine-tunable model → **R2** a small fine-tuned neural
net → **R3** off-the-shelf zero-shot/VLM, used sparingly. **Climb only on a measured failed bar**
(:101-105) — fidelity rising, a probe proving the cheap rung can't separate the signal, or the
question being genuinely L3-semantic. Never climb on preference.

## The inventory — every core/ perception primitive

| Primitive | Answers | Key symbol:line | Live consumers | Gotcha |
|---|---|---|---|---|
| `egomotion.py` | how did the camera move (2D shift) | `best_shift:23`, `direction:51` | `grid_perceiver.py:23`, `games/pokemon_red/perceiver.py:28-29`, `localize_scroll.py:21` | DIRECTION reliable, metric distance NOT (:8); **silently wrong** on 190/200 tics of real 3D rotation (`yaw_flow.py:10-11`) — use `yaw_flow` for any 3D world |
| `yaw_flow.py` | am I turning, which way, how fast (3D ego-rotation, replaces `egomotion` in 3D) | `yaw_band_flow:146`, `YawReading:56`, `calibrate:189` | `world_mcp.py:1950,2081` (P1 for ViZDoom), `stationary_movers.py:58`, `eval/score_a3_precheck.py:175` | `MAX_SHIFT=64:38`, `BAND=(84,156):39`, `NCC_FLOOR=0.2:40`; three-valued honesty — direction `"none"` (confidently stationary) vs `None` (can't tell) — **never collapse the two** (:15-18) |
| `localize.py` | where is the avatar (control-grounded L2 track) | `AvatarLocalizer:51` | `games/cave_noire/perceiver.py:23`, `localize_bayes.py:24`, `eval/probe_avatar_localize.py:158` | grounded by what YOUR buttons move, not brightness/size (:2-3); `_DECAY=0.7:25`, `_PEAK=2.6:26`, `_JUMP=30:27`; `None` when never localized — never fabricates |
| `localize_bayes.py` / `localize_blob.py` / `localize_scroll.py` | alternate R0/R1 realizers of the same localize contract | `BayesAvatarLocalizer:59`; `BlobContingencyLocalizer:84` (`_PROJ_THRESH=0.3:31`); `ScrollingLocalizer:58` (`_MAX_SHIFT=16:24`, ego-motion-compensated wrapper) | all four (incl. `AvatarLocalizer`) compared side by side in `eval/compare_localizers.py:30-34` | pick by **measured** fit on your world, not preference — this table IS the Realizer Ladder in practice |
| `blob.py` | what moved (segmentation/tracking substrate) | `segment_blobs:102`, `RollingBg:58`, `associate_blobs:165`, `_label_bfs:21` | most-reused L1 body in `core/`: `entities.py:17`, `localize_blob.py:22`, `text_regions.py:42`, `static_objects.py:46`, `nds_perceiver.py:41` (`connected_components`), `stationary_movers.py:57` (`_label_bfs`) | check here before writing ANY new segmentation code — it is almost certainly a `blob.py` gap, not a new module |
| `tilemap.py` | what does this tile DO (online, behaviour-labelled appearance→function) | `TileFunctionMap:80`, `fingerprint:94` | `grid_perceiver.py:28`, `games/pokemon_red/perceiver.py:31`, `glyph_cache.py:41` | a perceptual **hash beats CLIP** for recurrence (:9-13) but **neither** predicts a wall in a genuinely new tileset (:14-17) — never a cross-tileset oracle; behaviour (a real bump) stays the authority |
| `grid.py` | cardinal-direction shared constants | `DIRS/DELTA/BACK:11-13`, `EGO2DIR/DIR2EGO:14-15` | `grid_perceiver.py:28` | "lifted the second time the body was needed" (:5-6) — the canonical lift-to-core example, cite it when arguing to lift something else |
| `grid_perceiver.py` | the whole lean occupancy-grid body (walls/frontiers/pose) + the `MoveSignal` protocol | `GridPerceiver:217`, `MoveSignal:120`, `CameraScrollSignal:131`, `ForegroundSignal:149`, `FollowCameraPerceiver:515` | every lean game (`gauntlet`, `cave_noire`, NDS) subclasses/wraps this | `WALL_CONFIRM=3:30` (seal a wall only after 3 persistent no-moves); a new lean world **subclasses this**, never reimplements it |
| `entities.py` | what discrete foreground things are on screen | `EntityDetector:29`, `detect:66` | `grid_perceiver.py:24,230` (default `entity_detector`) | filters the avatar cell + HUD region + sub-`min_area` blobs; built on `core.blob`, not a reimplementation |
| `glyph_cache.py` | have I seen this exact glyph bitmap, brain-confirmed (R1 recognition) | `GlyphCache:46`, `fingerprint:61` | **design-only** — `eval/score_glyph_cache.py` + tests; no live perceiver wires it yet (verified: no other `import` hit in the tree) | blank every run, no cross-run persistence (learning-boundary law, :11-13); reuses `TileFunctionMap.fingerprint` verbatim (:15-16) |
| `text_regions.py` | where on the frame is glyph-shaped content (routing hint) | `TextRegionDetector:83`, `detect:96` | **design-only** — no live perceiver wires it (verified: only `core/text_regions.py` itself matches); scored by `eval/score_text_regions.py:34` | NOT a recognizer, never emits a character (:3-4); R0 gate **FAILED** on the fixture and is **banked as a documented FAIL**, not tuned further to pass (:26-27) |
| `screen_role.py` | (NDS) which screen is gameplay vs symbolic, from behaviour | `ScreenRoleDiscovery:66` | `nds_perceiver.py:44` (`discovery()`) | `_CONF_THRESHOLD=0.40:42`; discovered per-run, no top/bottom prior baked in |
| `static_objects.py` | what static salient objects sit on this tile-grid | `StaticObjectDetector:146`, `detect:160` | **none in the live tree** (verified: only its own file + tests import it) | **GATE VERDICT: KILL CHEAP** — recall 0.0, 236-341 phantoms across 12 frames (:19-22). Kept as a documented-honest failure; do not resurrect without a new realizer and a fresh measured bar |
| `stationary_movers.py` | what's moving in a 3D scene, given that I am not | `stationary_movers:112` | `world_mcp.py:1948,1953,2057` (P2 for ViZDoom) | only valid on ego-**stationary** pairs — gated by P1's own `YawReading`, else returns `None` (:10-17); `PIX_T=25.0:60`, `MIN_AREA=30:61` |
| `novelty.py` | have I been in this exact state before | `NoveltyMemory:28`, `observe:35` | `core/brains.py:30` | counts VISITS, not raw occurrences — only a **rising edge** (a key that differs from the immediately-preceding one) counts (:13-16) |
| `outcome.py` | did this (situation, action) do anything last time | `OutcomeMemory:41`, `state_signature:21` | `core/brains.py:31` | `state_signature` deliberately excludes `screen_text` (`novelty.py` exists to cover that gap) |
| `patience.py` | can I auto-advance this screen for free (System-1 reflex) | `Patience:142`, `AdvanceLearner:88`, `classify:73` | wired via `PerceptionPlugin`'s `patience=` kwarg, default OFF | fail-safe default: unsure / `"static"` / any unrecognized context → `"choice"` (**WAKE**), never auto-advance (:76-85); only DECODER-BACKED labels (`dialog`/`battle_text`) are gated by default |
| `disconfirm.py` | how long since anything NEW happened (surprise note) | `DisconfirmDetector:26`, `fired:52` | `core/brains.py:29` | a bookkeeping signal, not a perceiver output — feeds the stuck-breaker, not `SymbolicState` |
| `vision_client.py` | HTTP client for the local OCR/caption/CLIP-grid service | `VisionClient:23` | **only** `eval/_archive/_vision_smoke.py` (verified: no other importer in the tree) | degrades to an empty result if the service is down/errors, never raises (:5-7) — keeps the fast pixel perceiver alive |
| `vision_escalation.py` | ground a STUCK screen via a strong VLM, at most 8x/run | `VisionEscalator:33`, `ground:47` | `core/brains.py:393` (`self.escalator`) | `max_calls=8:38`, cached per `state_key`; description-never-decision (:11); a healthy run makes **ZERO** calls (:13-15) |
| `modality.py` | is this frame static / gameplay / menu (motion-only classifier) | `detect_modality:101` | `grid_perceiver.py:26`, `screen_role.py:31`, `autoplay.py:31` | `STATIC_EPS=1.2:40`, `GAMEPLAY_FRAC=0.30:43`; `"static"` is a **motion** label, not a semantics label — `patience.py` depends on this distinction (:20-23) |
| `perception.py` | the frozen output contract itself | `SymbolicState:23`, `Perceiver` Protocol`:60`, `StubPerceiver:71` | every perceiver in the tree | pose / spatial_memory / affordances / context / screen_text / last_action / confidence — the seven fields every perceiver must fill |
| `perception_plugin.py` | MCP tool wiring for a `Perceiver` (buttons, observe, oracle logging) | `PerceptionPlugin:63`, `observe:189`, `_log_oracle:290` | `world_mcp.py`'s `GAMES` registry wraps a `Perceiver` in this | RAM only ever reaches `world/oracle.jsonl` via `_log_oracle`, **never** `Observation.data` — the no-leak invariant (see **architecture-and-seam**) |
| `nds_perceiver.py` / `nds_perception_plugin.py` | NDS perceiver routing `GridPerceiver` to the discovered gameplay screen + touch targets | `NDSPerceiver:126`, `_detect_touch_targets:56`; `NDSPerceptionPlugin:32` | `world_mcp.py` NDS games | touch-target detection reuses `blob.connected_components:41`, not a new detector |

## The three perceiver tiers

1. **Rich, per-world** — `games/pokemon_red/perceiver.py:OverworldPerceiver`. Imports only three
   primitives from `core/` (`egomotion.py:28-29`, `perception.py:30`, `tilemap.py:31`); the rest is
   Pokémon-specific (battle/menu decoding, BCD HUD reads). This is the *most* framework a world should
   need, and only because Pokémon was the first world.
2. **Lean, thin-config** — `core/grid_perceiver.py:GridPerceiver`/`FollowCameraPerceiver` plus a
   per-world `MoveSignal`. `games/gauntlet/perceiver.py:GauntletPerceiver` wires `CameraScrollSignal`
   (`gauntlet/perceiver.py:15`); `games/cave_noire/perceiver.py` wires `ForegroundSignal` +
   `AvatarLocalizer` (`cave_noire/perceiver.py:21,23`). Both are tens of lines, not hundreds.
3. **NDS** — `core/nds_perceiver.py:NDSPerceiver` routes `GridPerceiver` to whichever screen
   `ScreenRoleDiscovery` finds is gameplay, plus blob-based touch targets.

**A new world should start from tier 2** (subclass `GridPerceiver`, supply/write one `MoveSignal`) —
see **new-world-port** for the mechanical registry/launcher steps. Only reach for tier-1-style bespoke
code when a world's genre genuinely has nothing in common with the occupancy-grid model (turn-based
menus/battle text, as Pokémon did).

## Decision guide — "my perceiver can't see X"

**Probe before you write code.** Every row below has a free offline probe; run it and read the number
before touching a primitive (see **eval-probes-and-datasets** for the full toolkit and
**diagnose-a-run** RULE 0 — replay before you blame the perceiver). Invocation shape (Linux/WSL;
Windows PowerShell prefix in **eval-probes-and-datasets** §1):

```
uv run python -m eval.probe_entities            # optional game-substring filter arg
uv run python -m eval.probe_tilemap runs/fix2 runs/fix4
```

| Symptom | Primitive to check first | Probe to run |
|---|---|---|
| Camera/pose drifts or direction looks wrong (2D) | `egomotion.py` | `eval/probe_camera_model.py:38`, `eval/probe_pose_drift.py:31` |
| Turning/rotation looks wrong (3D) | `yaw_flow.py` | `eval/score_a3_precheck.py:175` |
| Avatar position is lost or jumps | `localize.py` (+ Bayes/blob/scroll variants) | `eval/probe_avatar_localize.py:158`, `eval/compare_localizers.py:30-34` |
| Tile walkability/interactability is wrong or slow to learn | `tilemap.py` | `eval/probe_tilemap.py:32` |
| An enemy/item/entity isn't detected | `entities.py` or `blob.py` | `eval/probe_entities.py:30` |
| Glyph/HUD-digit reads are flaky | `glyph_cache.py` | `eval/score_glyph_cache.py:47` |
| Need to route `read_region` to the right spot | `text_regions.py` | `eval/score_text_regions.py:34` (already FAILED once — read the gotcha above before re-trying) |
| Static-object candidates (Pokéballs, chests) | `static_objects.py` | `eval/score_static_objects.py:35` (already KILL CHEAP — read the gotcha above first) |
| Frame classified static/gameplay/menu wrong | `modality.py` | `eval/_modality_probe_run.py:23` |
| Localizer choice for a new world | any localizer | `eval/validate_localizer.py:23` |

If the probe shows the cheap rung genuinely can't separate the signal, that is the Realizer Ladder's
climb trigger (§ above) — write up the failed bar before reaching for R2/R3.

## The escalation ladder (cheap first, VLM last)

1. **`modality.py`** classifies the frame (static/gameplay/menu) for free every step.
2. **`patience.py`** decides whether a gated-static screen can be auto-advanced without waking the
   brain — **unsure always defaults to WAKE** (`patience.py:76-85`); only decoder-backed labels are
   gated by default.
3. **The stuck-breaker** (`core/brains.py:380-394`) tracks a seen-states set; when a state persists it
   hands the bare "stuck" fact up.
4. **`VisionEscalator`** (`vision_escalation.py:33`) is the last resort: at most `max_calls=8` per run,
   cached per state, called ONLY on a stuck wake, and it **describes, never decides** — the cheap agent
   still acts on the description. A healthy run calls it zero times (:13-15).
5. **`VisionClient`** (`vision_client.py:23`) degrades to an empty result if the underlying service is
   down — never a raised exception, never a fabricated OCR/caption.

## Extension rules

- **Lift to `core/` on the SECOND use**, not the first (`grid.py:5-6` is the canonical citation) —
  writing it twice per-game is the ossification this toolbox exists to prevent.
- **Fitness tests enforce this mechanically** (`tests/test_import_boundaries.py`, docstring "do NOT
  edit this test to make it pass" at line 4):
  - `test_lean_games_do_not_carry_their_own_infra` (:96-101) — a lean game package may not carry its
    own emulator/plugin; `_INFRA_OK = {"pokemon_red"}` (:86) is the sole grandfathered exception.
  - `test_lean_perceivers_are_thin_config_not_an_inlined_body` (:111-121) — `_LEAN_PERCEIVER_MAX_LINES
    = 80` (:108). A lean `perceiver.py` over 80 lines is, by construction, an inlined copy of the
    shared body, not config — the fix is to lift the shared part, never to raise the cap.
  - `test_core_is_world_agnostic` (:49) — nothing in `core/` may import `games/`.
- **Behaviour = truth, always.** `tilemap.py:16-17`: appearance (hash OR embedding) can never predict
  function in a genuinely new tileset; a real bump/interaction stays the authority over any advisory
  appearance match. Never let an L1 hash or L3 VLM description silently override an observed action↔
  effect result.
- **Never hand-assert semantics at L1.** "That region is my HP" / "that's an enemy" is an L3 label the
  brain hypothesizes and behaviour grounds (ADR-002) — it is never baked into an L1 primitive's code
  as a constant or a hand-picked class (the `MoveSignal` sin, constitution :75-76).

## Cross-refs

- **architecture-and-seam** — why the perceiver is the only thing that legitimately changes per world;
  the no-leak/oracle invariant `perception_plugin.py` enforces.
- **new-world-port** — the mechanical steps (registry entry, launcher, first constancy audit) for
  wiring a tier-2 lean perceiver into a new world.
- **eval-probes-and-datasets** — the full probe/scorer toolkit referenced in the decision guide above.
- **diagnose-a-run** — RULE 0: replay a run's own frames/oracle before concluding a primitive is wrong.
- **cheapness-skill-compilation** — the System-1/System-2 split this escalation ladder is one instance
  of (patience → stuck-breaker → VisionEscalator mirrors the skill-promotion discipline).

## Sources

- `reports/north-eye-perception-constitution.md` — L0-L3 stack (:48-54), six questions (:43-45),
  seven-slot contract (:63-77), Realizer Ladder + climb triggers (:87-105).
- `reports/CONTEXT-BRIEFING.md` "Background" (:40-51) — perception-is-the-bottleneck thesis.
- All `core/*.py` files named above — docstrings and line numbers verified directly against the
  worktree on 2026-07-04 (not taken from a lead sheet without opening the file).
- `tests/test_import_boundaries.py` — fitness-test names/lines verified (:1-4 docstring, :49, :86,
  :96-101, :108, :111-121).
- Consumer/no-consumer claims verified by `grep -rl` for the primitive's class/module name across the
  tree at the time of writing; `glyph_cache.py`, `text_regions.py`, and `static_objects.py` are flagged
  **design-only** because that grep found no importer outside their own file, tests, and `eval/score_*`
  — re-check before relying on this if the tree has since changed.
