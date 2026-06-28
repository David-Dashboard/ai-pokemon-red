# Relocalization — fix, status, and next steps (2026-06-29)

Tilemap-based loop-closure in `core/grid_perceiver.py`: when the agent re-enters mapped territory, re-anchor
the drifted dead-reckoned cursor to the remembered cell. Added to fix the measured #1 task-progress blocker
(dead-reckoning drift, surfaced by the reasoning-brain bench).

## The fix (this commit)
- **Match-before-record (the dead-code bug).** The original code wrote `place_sigs[sig] = (x, y)` *before* the
  match lookup, so `place_sigs.get(sig)` always returned the just-written current position and the re-anchor
  guard `match_cell != (x, y)` was always false — **relocalization never fired.** Reordered: look up the prior
  recording, re-anchor, *then* overwrite.
- **Skip when an absolute localizer exists.** Now gated `not hasattr(move_signal, "absolute_cell")`. A world
  with an `absolute_cell` localizer (Cave Noire's `LocalizedForegroundSignal`) already gets a per-frame
  ground-truth fix — there is no drift to recover, and running both would make two snap mechanisms fight over
  the cursor (a real review finding). This correctly scopes relocalization to **pure dead-reckoning
  fixed-camera worlds**, which are the only ones that need it.

## Where it is (and isn't) used end-to-end
- **Fires in:** `play_generic.py` / `bench_generic.py` (the ExploreBrain bench) for **fixed-camera games that
  use a plain `ForegroundSignal`** (no localizer) — e.g. Crystalis, Zelda LA.
- **Does NOT fire in the reasoning-brain harness.** `world_mcp.py` wires only Cave Noire (has a localizer →
  skips relocalization) and Gauntlet (follow-camera → gated off). So **no `claude -p` end-to-end run currently
  exercises relocalization.** To validate it with a real brain, a pure-dead-reckoning fixed-camera game
  (Crystalis / Zelda) must be wired into `world_mcp.py`.
- **Does NOT touch follow-camera worlds** (Kirby/Metroid/Gold) — fixed-screen signatures are meaningless when
  the world scrolls every frame.

## Next steps (ranked)
1. **Bench-validate it.** Re-run `bench_generic.py` before/after on the pure-dead-reckoning fixed-camera
   cluster (Crystalis, Zelda LA) and report cells-explored + stall-mode delta. **It is currently UNMEASURED —
   we do not yet know whether it helps.** This is the gate before claiming the drift fix works.
2. **Identical-room false positives.** Exact 12-tile signatures cannot distinguish a real loop-closure from
   two identically-templated rooms (common in Cave Noire / dungeon-crawlers) → a wrong re-anchor teleports the
   cursor. Mitigations to evaluate: gate on motion-consistency (re-anchor distance must be plausible given the
   recent dead-reckoned path), or a uniqueness-over-map check (refuse to re-anchor on a signature ever recorded
   at ≥2 distinct cells — but note this also suppresses legitimate closures, so measure the trade-off).
3. **Signature fragility (false negatives).** An animated sprite/tile crossing one of the 12 sampled crops
   corrupts the exact match → misses a real closure. Consider k-of-12 partial matching or sampling
   sprite-free regions. Trade-off: looser matching raises false positives (#2).
4. **Wire a non-localizer fixed-camera game into `world_mcp.py`** so relocalization is exercised by a reasoning
   brain (the only end-to-end loop that reads the resulting confidence/pose).
5. **Confidence restore is unconditional.** A match restores `pose_confidence` to `_CONF_BASE`; if the match is
   wrong (#2), it falsely restores confidence. Tie the restored confidence to match quality once #2/#3 land.
6. **Follow-camera drift is still unsolved** — the bigger problem (Kirby/Metroid/Gold). Needs world-position
   relocalization (ego-motion-integrated), not fixed-screen signatures. Separate, harder build.
