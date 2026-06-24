# 2026-06-24 — Cave Noire: the fixed-camera class + the foreground-motion primitive

Picked Cave Noire as the "cheap top-down follow-on" to Gauntlet. **Measure-first overturned that** and gave
us something better: a second pose model and the missing half of ego-motion.

## Finding 1 — Cave Noire is FIXED-camera, not follow-scroll (the recipe doesn't transfer)
`eval/find_ram_addr` on the existing `cavenoire_explore` recording (DMG, has `ram.bin`) found the player
tile registers **X=`0xC504`, Y=`0xC503`** (u8, 100% consistency). Checking `best_shift` against them:
**99% of real moves are camera-STATIC** (653/660) — the screen never scrolls; the player sprite moves on a
still board. So `best_shift` (camera motion) is blind and the Gauntlet "no scroll ⇒ wall" recipe would map
nothing. Cave Noire belongs to the **fixed-camera class** (with Space Invaders / Tetris), not the follow
class (Pokémon / Gauntlet). We are out of cheap follow-scroll games.

## Finding 2 — foreground motion recovers the camera-static moves (the missing complement)
`best_shift` = camera/background motion; its complement is **foreground** motion (the sprite). On a
camera-static step the camera-compensated residual is just the whole-frame diff. `eval/probe_foreground_motion`
asks: does that residual separate a real move from a wall-bump when the camera is blind?

| game | camera-static moves | residual MOVED vs STUCK | separation AUC |
|---|---|---|--:|
| gauntlet | 24% of moves | 6.2 vs 2.6 | 0.76 |
| cavenoire | 99% of moves | 2.9 vs 0.7 | **0.86** |

Yes — a **cheap** signal (camera-compensated frame-diff; no CLIP, no model). This is the missing half of
ego-motion: `move = camera scrolled (best_shift) OR foreground residual high`. It pays back BOTH games —
it's the only move signal for Cave Noire's fixed camera AND it catches Gauntlet's dead-zone 24% that
`best_shift` misses. **Two independent games need it ⇒ it earns a `core/` primitive** (the "second world
forces the abstraction" rule). Deferred-but-now-justified: we parked sprite-tracking earlier as one-regime;
the data flipped that.

## Build — CaveNoirePerceiver (fixed-camera, foreground-motion odometry)
`games/cave_noire/perceiver.py`: the Gauntlet structure with the move signal swapped to the foreground
residual (`best_diff >= _FG_MOVE=1.5`), direction from the COMMANDED button (Cave Noire is 4-dir turn-based,
so command == move), `best_shift`-scroll kept as a rarely-firing fallback, and the same persistent-wall
confirmation (`_WALL_CONFIRM=3`; idle animation is transient). Reuses `core.egomotion` + `core.modality`;
`core/` and the brain untouched.

**Offline validation** (`eval/replay_cave_noire_pose`, perceiver pose vs the `ram.bin` oracle): net-dir
**99% (W=1) → 85% (W=40)**, drift **0.06**. Cleaner per-step than Gauntlet (99% vs 57% at W=1) because
turn-based 4-dir gives an exact commanded direction. The fixed-camera pose model works.

## Status / next
- Perceiver + probe + offline validation here; `tests/test_cave_noire.py` locks the foreground-move logic.
  **Live closed-loop run is NOT done yet** (plugin/emulator/driver + `ExploreBrain`) — the real test that
  caught Gauntlet's dead-zone; Cave Noire's single-screen dungeon may stress frontier-exploration.
- **Live-run watch-items (the offline replay can't surface these):**
  - **False-MOVE asymmetry** (the inverse of Gauntlet's false-wall): a wall needs `_WALL_CONFIRM` persistent
    no-moves to seal, but a move is trusted on a *single* foreground frame, so a lone idle-animation flicker
    (AUC 0.86 → ~14% confusable) can false-step the pose into a phantom cell. Candidate fix at the live run:
    symmetric move-confirmation (persist the foreground 2 frames) or a higher `_FG_MOVE`, closed-loop validated.
  - **No-leak wall test must ship with the plugin** — `test_cave_noire.py` covers perceiver logic only (no
    plugin yet, so no leak surface). When `CaveNoirePlugin` lands it gets the same RAM-sentinel wall the
    Gauntlet plugin has (`watch` RAM → `oracle.jsonl` only).
- **Next (after the Gauntlet PR lands):** extract foreground-motion to a shared `core/` perceiver helper and
  migrate BOTH Gauntlet (fixing its dead-zone) and Cave Noire onto it — together, to avoid a one-user
  abstraction. (Both PR reviews converge on the same design: a shared occupancy-grid perceiver parameterized
  by a `move_signal(prev, cur, action) -> (moved, direction)` strategy.)

## Verification
- `uv run python -m eval.find_ram_addr runs/2026-06-23_cavenoire_explore` → the X/Y registers.
- `uv run python -m eval.probe_foreground_motion` → the AUC table.
- `uv run python -m eval.replay_cave_noire_pose` → pose vs oracle (99% / 0.06).
- `uv run pytest tests/test_cave_noire.py -q` → 3 green.
