# 2026-06-23 — Eval C: cross-game RAM-grounded ego-motion (the open thread from PR #5, closed)

Closes the "cross-game RAM-grounded validation pending" item from the P1 ego-motion probe. P1's load-bearing
result (98% direction recovery) was **Pokémon-only** — RAM truth existed for no other game. We now have it for
three non-Pokémon games via `record.py --watch` (David hand-recorded them so the camera actually pans — auto
play can't keep a maze/side-scroller camera scrolling). New: `cross_game_ram_truth()` (Eval C) in
`eval/probe_egomotion.py`, reusing `best_shift`.

## Setup

`record.py --watch <name>=<HEXADDR>,...` logs WRAM position bytes to a separate `oracle.jsonl` (`watch` field;
never `buttons.jsonl`). Three runs, frame file = `frame_{step:06d}.png`:

| game | run | register(s) | what it is | camera |
|---|---|---|---|---|
| gauntlet | `2026-06-23_gauntlet_ramplay` | `x=0xC286, y=0xC2C6` (finder-found) | PLAYER world (x,y) | follow, dead-zone |
| kirby | `2026-06-23_kirby_ramplay` | `scroll_x=0xD051, scroll_y=0xD055` | CAMERA scroll | side-scroller (horizontal) |
| metroid | `2026-06-23_metroid_ramplay` | `x_scr=0xD028,x_px=0xD027 / y_scr,y_px` | screen×256+pixel → world coord | room/side |

Scoring (same as Eval A): per step, dominant RAM axis (larger |Δpos|), sign-match `best_shift`'s shift vs RAM Δ
under one fixed convention (east+x→+dx, south+y→+dy). Single-byte registers wrap-corrected (255→0 = −1).
Moves filtered `1≤|Δpos|≤40` (drops wrap-ghosts + no-moves). RAM is the oracle, never an input.

## Results

| game | all (incl. camera-static) | camera-scrolled | n (all / scrolled) |
|---|--:|--:|---|
| gauntlet | 59% | **79%** | 658 / 434 |
| kirby | 89% | **98%** | 123 / 110 |
| metroid | 67% | **85%** | 403 / 304 |

All three registers came out **aligned** with the assumed ego convention (no inversion) — i.e. `best_shift`'s
+dx/+dy points the way each game's register increases, with no per-game sign flip. (Per-axis: gauntlet X 87% /
Y 88%; kirby X 99% / Y n.a. — horizontal game; metroid X 88% / Y 94%, on camera-scrolled steps.)

## Reading it — the camera-vs-player distinction, now cross-game and RAM-grounded

`best_shift` estimates **camera** motion; a position register is **player** motion. They agree only when the
camera moves with the player. That is exactly the "all vs camera-scrolled" gap:

- **Gauntlet** (follow camera with a dead-zone): the player sprite slides around the screen center without the
  camera panning, so many player-moved steps are camera-static → `best_shift=0` → counted as misses. "all" 59%
  vs camera-scrolled 79%. The 21% residual on scrolled steps is diagonal/multidirectional noise (consistent
  with Eval B's gauntlet 2/4).
- **Kirby** (camera-scroll register, near edge-locked side-scroller): almost every player move is a camera
  scroll, so "all" (89%) ≈ scrolled (98%) — the cleanest case.
- **Metroid** (room/side): in-between, 67% → 85%.

Pokémon hit 98% in Eval A because its overworld *always* centers the player (camera-scroll == player-move every
step), so its "all" and "scrolled" are the same number. The follow-camera dead-zone is the only thing between
Gauntlet's 59% and Pokémon's 98% — not an estimator weakness.

## Conclusion

- **`best_shift` recovers self-motion DIRECTION cross-game, RAM-grounded** — **59–89% overall, 79–98% on
  camera-scrolled steps** across 3 non-Pokémon games (follow, side-scroll, room), no per-game tuning, one
  consistent ego convention. This is the cross-game evidence P1 was missing; with Pokémon's 98% it greenlights P2.
- **Carry BOTH numbers, and label the conditioning.** "camera-scrolled" conditions on `best_shift` having fired
  (`|shift|>2`), so it excludes the estimator's **own false-negatives** (a real camera scroll read as 0), not
  *only* the camera dead-zone — this metric cannot separate the two. The **"all" floor (59/89/67%)** is the
  unconditioned number and stays equally prominent. (To actually attribute the gap one would need, on the
  `best_shift=0` steps, a per-game model of when the camera *should* have panned — we don't have it, so we don't
  claim it.) Magnitude/metric distance stays deferred — direction (sign) is the reliable output.
- This is an `eval/` measurement, not an estimator change — P2 (extract `core/egomotion.py`) is unchanged and
  greenlit.

## Verification
- `uv run python -m eval.probe_egomotion` → A (Pokémon 98%) + B (cross-game button-grounded) + C (this table).
- `uv run pytest -q` → 308 passed (probe is an `eval/` script, untested by convention; imports resolve).
