# 2026-06-26 — AvatarLocalizer: control-grounded avatar localization (first North Eye L2 primitive)

## Why
Dead-reckoning drifts (the Cave Noire strand); motion-centroid finds whatever moves most, which is the avatar
in almost no game (`eval/score_localize`: `avatar=mover` 2–5% in 9 of 10 games). The fix is the North Eye
binding principle: **the avatar is the thing your buttons move** — ground localization in action↔motion
correlation, not appearance or motion magnitude.

## What (`core/localize.py`, R0 numpy)
Each commanded step, accumulate a per-cell heatmap of the motion **explained by the commanded direction**
(`min`-residual after shifting the previous frame by `k·DELTA[dir]`); the peak is the avatar (enemies/animation
move uncommanded → wash out). The heatmap **decays** (memory ~3–5 steps) so it tracks the *current* position
and self-corrects — no unbounded drift. No recent commanded motion ⇒ avatar stationary ⇒ **hold** the last fix.
Output = `(col,row,confidence)` or `None` (North Eye contract: never fabricate).

A first TLD-style version (NCC template track + re-ID gallery) was built and **rejected by measurement**: it
locked early and drifted (Cave Noire 0% in-box / 58px, 3 min/game). A diagnostic showed the *action-correlation
peak itself* is 1–15px from the avatar — so the tracker was the problem, not the signal. The decaying-heatmap
version (no NCC) is simpler, faster (7s/game), and far better. The Realizer Ladder working as intended.

## Validation vs the hand-label dataset (`datasets/labels/v2`, `eval/validate_localizer`)
Driven continuously per game with the recorded button stream; scored at GT gameplay frames.

| game | camera | in-box | px | | game | camera | in-box | px |
|---|---|--:|--:|---|---|---|--:|--:|
| **cavenoire** | fixed | **59%** | **4** | | kirby | side | 12% | 31 |
| **sml** | side | **42%** | **9** | | crystalis | follow | 8% | 58 |
| metroid | side | 38% | 37 | | zelda | follow | 6% | 70 |
| gold | follow | 29% | 32 | | gauntlet | follow-scroll | 0% | 69 |
| ffa | follow | 20% | 28 | | spaceinv | fixed/multi-mover | 0% | 109 |

(baseline motion-centroid: Cave Noire 41%/12px.)

## The camera-class result (honest scope)
- **Works where the avatar moves on screen** — fixed-camera (Cave Noire 4px) and side-scrollers where the
  avatar isn't perfectly pinned (SML 9px).
- **Fails on follow-camera** (crystalis/zelda/gauntlet): the command **scrolls the whole screen**, so
  "motion explained by the command" is the *background*, not the avatar (which sits static at center). That is
  the dual — follow-camera **world-position is ego-motion** (`core.egomotion.best_shift`), not avatar-screen
  localization. Don't conflate the two.
- **spaceinv**: fixed camera but the aliens dominate motion and the ship moves 1-D — a known hard multi-mover case.

## Next
- **Wire into the Cave Noire perceiver** as an absolute pose source (replace the drift-prone dead-reckoned
  cursor) and **closed-loop on `cn_open.state`** — this is the strand fix the whole thread was chasing (4px,
  bounded → no drift, no strand).
- **Follow-camera dual** (deferred): localize the avatar as the region that *stayed put while the background
  scrolled* (anti-correlation) + a center prior; world-position there stays `best_shift`.
- If a primitive ever needs sub-cell appearance tracking, that's the R1 climb (template) — measured, not assumed.
