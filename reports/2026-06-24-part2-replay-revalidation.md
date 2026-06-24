# 2026-06-24 — part-2 refactor: replay re-validation + the live closed-loop finding

Committed evidence for the two claims the part-2 PR (#12) makes about behavior. Both replay scripts read
**gitignored corpora** (on D:, not in CI), so "tests green" cannot prove them — this file records the
actual post-refactor output so the numbers are reproducible by anyone with the corpus, and corrects an
over-claim the PR body originally made about the false-MOVE asymmetry.

## 1. Behavior-preserving — replay oracles re-run AFTER the `core/` extraction

The refactor moved the occupancy-grid body into `core/grid_perceiver.py` (shared `GridPerceiver` +
`MoveSignal`) and rewired Gauntlet + Cave Noire as thin config. The two offline replays compare the
perceiver's dead-reckoned pose to the RAM oracle; matching the pre-refactor numbers is the
behavior-preserving proof. Verbatim output, run 2026-06-24 on the post-refactor branch:

```
$ uv run python -m eval.replay_gauntlet_pose
=== GauntletPerceiver offline pose vs RAM oracle (2026-06-23_gauntlet_ramplay, n=947) ===
  net-dir (perceiver pose vs oracle): W=1:373/659=57%  W=5:112/160=70%  W=10:64/87=74%  W=20:35/45=78%  W=40:19/23=83%
  drift err/path (perceiver pose, k=5.1px/cell): 25%:0.14  50%:0.09  75%:0.03  100%:0.02

$ uv run python -m eval.replay_cave_noire_pose
=== CaveNoirePerceiver offline pose vs RAM oracle (runs/2026-06-23_cavenoire_explore, n=4000) ===
  net-dir (perceiver pose vs oracle): W=1:651/660=99%  W=5:287/296=97%  W=10:148/161=92%  W=20:114/124=92%  W=40:67/79=85%
  drift (warp-segmented, k=1.0px/cell): 0.06 over 1 seg(s) (worst 0.06)
```

These match the pre-refactor figures (Gauntlet 57→83% / 0.02; Cave Noire 99→85% / 0.06) ⇒ the extraction
is behavior-preserving on the offline oracle. NOTE: this is the OFFLINE replay only; it does not (and
cannot) prove closed-loop behavior — see §2, where closed-loop reveals a real defect the replay masks.

## 2. The false-MOVE asymmetry DID bite in closed loop (correcting the PR's N=4 claim)

The PR body originally said the live run's "4/4 RAM-real, 0 phantom" meant the asymmetry "did not bite,
so NO symmetric-confirmation change was made." **That was wrong on two counts and is retracted:**
- **N=4 is statistical noise.** At the probe's ~14% confusable rate (AUC 0.86), P(0 phantoms in 4 moves)
  ≈ 0.86⁴ ≈ 0.55 — you'd see zero in over half of all 4-move runs even with the bug fully present.
- **Longer runs show it bites hard.** Two ExploreBrain runs from in-cavern save-states, scored against the
  RAM oracle (`x=0xC504 y=0xC503`):

  | run | geometry | perceiver "moved" | RAM-real | **phantom** |
  |---|---|--:|--:|--:|
  | `cn_explore_live2` | open corridor | 70 | 5 | **65** |
  | `cn_explore_human` | tight pocket | 3 | 1 | **2** |

  In the corridor the brain pressed `up` into a wall ~190 times; idle animation intermittently pushed the
  foreground residual over `_FG_MOVE=1.5`, minting 65 phantom cells and dead-reckoning the pose to
  `[0,-70]` while the player never moved past the wall. Severity is geometry-dependent (a tight pocket
  lets wall-confirmation catch up when the brain switches direction; a straight corridor does not).

### Why it's not a quick threshold (the probe that kills the easy fixes)
Residual magnitude per move step (real = RAM-moved, phantom = RAM-still):

| run | REAL residual | PHANTOM residual |
|---|---|---|
| corridor | 2.1 – 6.9 (med 6.0) | ~3.8 |
| pocket | 2.5 | 56.9 (gameplay) / 70.7 (menu) |

The classes **invert and interleave**: real `{2.1, 2.5}` < idle-phantom `{3.8}` < real `{6.0}` ≪
big-event phantom `{57, 71}`. No static `_FG_MOVE` threshold or band separates them; a `context==gameplay`
gate catches only the one `menu` phantom (71), not the corridor runaway (all `gameplay`). The only reliable
discriminator is **structural** — a real move is a coherent translation into new territory; idle flicker is
in-place toggling that returns to the same view — which needs a directional/translation check or
move-persistence confirmation (the twin of wall-confirmation). That is a dedicated follow-up with its own
probe + closed-loop validation, deliberately NOT slipped into the refactor PR.

**Lesson (recurring):** the offline replay overstates (99%/0.06); the closed loop reveals the defect —
same pattern as Gauntlet's dead-zone. Offline pose accuracy ≠ closed-loop soundness.

## 3. "Constancy" scope (correcting the PR wording)
The live run shows the unchanged `ExploreBrain`/`core/` *ran the Cave Noire stack end-to-end in-cavern* —
i.e. the architectural constraint (brain code untouched when adding a world) holds, which is true by
construction. It does NOT show task-level success: the brain made a handful of confirmed moves, then either
dead-ended in a pocket or ran away on phantom cells. Task-level constancy on Cave Noire is OPEN, gated on
the §2 fix + an actual navigation goal.

## Reproduce
- `uv run python -m eval.replay_gauntlet_pose` / `... replay_cave_noire_pose` (needs the gitignored corpora).
- Live: `uv run python play_cave_noire.py --steps 200 --brain explore --init-state <in-cavern.state>`,
  then score `runs/<out>/oracle.jsonl` `perceived.outcome=="moved"` vs the `watch` x/y delta.
