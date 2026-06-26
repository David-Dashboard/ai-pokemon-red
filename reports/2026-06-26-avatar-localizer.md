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
| **cavenoire** | fixed | **56%** | **4** | | kirby | side | 12% | 31 |
| **sml** | side | **42%** | **9** | | crystalis | follow | 8% | 58 |
| metroid | side | 38% | 37 | | zelda | follow | 6% | 70 |
| gold | follow | 29% | 32 | | gauntlet | follow-scroll | 0% | 69 |
| ffa | follow | 20% | 28 | | spaceinv | fixed/multi-mover | 0% | 109 |

(baseline motion-centroid: Cave Noire 41%/12px.) Numbers are the **shipped** code: Cave Noire in-box is
**56%** — the F2 per-commanded-step-decay fix shifted it ~1 frame from the 59% first measured (review F-headline).

## The camera-class result (honest scope)
- **Works where the avatar moves on screen** — fixed-camera (Cave Noire 4px) and side-scrollers where the
  avatar isn't perfectly pinned (SML 9px).
- **Fails on follow-camera** (crystalis/zelda/gauntlet): the command **scrolls the whole screen**, so
  "motion explained by the command" is the *background*, not the avatar (which sits static at center). That is
  the dual — follow-camera **world-position is ego-motion** (`core.egomotion.best_shift`), not avatar-screen
  localization. Don't conflate the two.
- **spaceinv**: fixed camera but the aliens dominate motion and the ship moves 1-D — a known hard multi-mover case.

## Strand fix — wired + validated (live A/B)
Wired into `games/cave_noire/perceiver.py` (`LocalizedForegroundSignal`): the base `GridPerceiver` SNAPS the
cursor to the localizer's cell (pose = f(current frame) → no dead-reckoning integral → no drift → no strand),
falling back to dead-reckon when unlocked.

**Result** — a real System-2 `claude -p` brain over MCP (`world_mcp.py`), same world + brain + 20-decision
brief, swapping ONLY the perceiver (Cave Noire, `cn_open.state`):

| perceiver | distinct RAM tiles, 3 samples |
|---|---|
| localizer (snap) | **15, 16, 17** |
| dead-reckon (control) | **7, 7, 7** |

**Why 7 is a deterministic ceiling (not coincidence):** from a fixed save-state the dead-reckon perceiver is
deterministic (same pixels → same move-signal verdicts → same drift → same false-wall sealing), and the
ExploreBrain frontier BFS is deterministic too — so every run from `cn_open.state` walks the identical path
into the same self-inflicted box. 7 is the fixed-point reachable set before the drift corrupts the map; the
localizer removes the drift so the box never forms (~2.3× coverage).

**Durable artifact** (one A/B pair's `oracle.jsonl` distinct tiles — `runs/` is gitignored, so the counts live here):
- localizer: 15 — `(1,6)(2,1)(2,3)(2,4)(2,5)(2,6)(3,1)(3,2)(3,3)(4,1)(4,3)(5,1)(5,2)(5,3)(5,4)`
- dead-reckon: 7 — `(2,1)(2,2)(2,3)(2,4)(3,1)(3,2)(3,3)` (a small connected blob — the strand box)

Harness + reproduction in `reports/2026-06-26-mcp-claude-p-runbook.md`. (Caveat: N=3; the live MCP+Docker+WSL
harness isn't reproducible in a code-only review.)

## Next / deferred
- **Follow-camera dual** (deferred): localize the avatar as the region that *stayed put while the background
  scrolled* (anti-correlation) + a center prior; world-position there stays `best_shift`.
- If a primitive ever needs sub-cell appearance tracking, that's the R1 climb (template) — measured, not assumed.
