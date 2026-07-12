# Entity-gate v4 — $0 visibility probe on `kirby_entity2.state` (2026-07-11)

Follow-up to `reports/2026-07-11-entity-v4-coverage-papercheck.md` §5's one unverified condition:
does the gate room actually let the brain SEE the threat early enough for an honest early NEAR?
Read-only measurement, no report/code changes besides this file. $0 (local PyBoy, no API calls).

## Setup
Same pattern as `reports/2026-07-05-entity-v4-d-probe.md`: in-process `world_mcp.World`,
`game="kirby_dreamland"`, `KIRBY_SKILLS=1`, `init_state=runs/kirby_entity2.state`,
`roms/Kirby's Dream Land (USA, Europe).gb`. `hp` read via `plugin.emu.read(0xD086)` == **6** at
load (matches d-probe's assert). Detection reused verbatim from the world's own primitives — no
new perception code: `whats_changed`'s MAD>=2.0 dead-zone logic (`world_mcp.py:1129-1130`) applied
directly to `emu.screen_ndarray()` crops, plus visual screenshot inspection (`read_region`'s own
crop mechanism). Script: `C:/Users/Succe/AppData/Local/Temp/claude/.../scratchpad/
entity_v4_visibility_probe.py` (throwaway, not committed). Frames saved to `.../scratchpad/
v4_vis_out/shots/` (gitignored temp dir, not committed).

## Measurements

**1. At load (0 presses):** the threat enemy IS on screen — visually confirmed
(`00_baseline.png`), positioned ~30-40px left of Kirby, inside the `right_third` box
`(100,40)-(155,104)`. With **zero button presses**, 8 rounds of `wait(5 frames)` show
`right_third` MAD = 7.1-13.9 (well over the 2.0 dead-zone) every round, while `left_third`/
`upper_band` stay at 0.0 — the enemy's own idle-approach motion is machine-detectable via
`whats_changed` before Kirby ever moves, and cleanly separable from background.

**2. Approach lead time — varies sharply by cluster, not uniform:**
- **Cluster 1 (session-boot enemy):** visible at press 0, contact confirmed by press 8 of a
  `right` approach (score 0->800, `rc_08_right.png`) — **~8 presses of honest lead time**.
- **Cluster 2 (post-retreat, 2nd enemy):** during a retreat(`left`x6)+reapproach(`right`x8) cycle,
  the enemy first becomes visible at re-approach press 3 (`rc_18_right.png`, score still 800) and
  contact hits at press 4 (`rc_19_right.png`, score 800->1200) — **only ~1 press of lead**.
- **Cluster 3:** contact already banked by press 6 of the same re-approach (score 1200->1600,
  `rc_20_right.png` shows no enemy yet at 1200; `rc_21_right.png` already shows 1600) —
  **~0 presses of lead at this sampling granularity** (contact within the same press-to-press gap).

**3. Retreat/reappear:** during the `left` retreat's scroll-heavy presses (1-5), `right_third` MAD
is dominated by camera-scroll noise (24-35, confounded, can't isolate enemy signal) — matches the
d-probe's own finding that scroll noise swamps region boxes during movement. Once retreat settles
(press 6), `right_third` MAD drops to **0.0** and the screenshot (`rc_14_left.png`) shows the
original enemy gone (consumed) with only a tiny, distant new sprite at the far screen edge —
confirms threats DO leave/re-enter frame across a retreat, and an early NEAR is impossible during
that gap until the next enemy re-enters.

**4. Currency conversion:** cluster 1's 8-press lead comfortably supports an honest early NEAR far
before its drop, matching case D/E/I's "earliest arithmetically valid step" placements in the
papercheck — that placement is now confirmed genuinely grounded, not fabricated. Clusters 2-3,
however, offer only 0-1 presses of honest lead in this synthetic retreat/reapproach schedule —
an honest NEAR for those clusters lands **at or after** the approach start, not "shortly before,"
shrinking (not eliminating) the forward-bleed slack the papercheck's `b_k<=0.70` ceiling needs.

## Verdict: PARTIAL

The ONLY-IF condition **holds for the first threat cluster** (genuinely visible ~8 presses before
contact, no fabrication needed) but is **not uniformly true** — later clusters, at least under this
probe's retreat/reapproach schedule, show 0-1 presses of real advance visibility, well short of
cluster 1's window. A brief instructing "NEAR as early as genuinely visible, one per cluster" is
honest advice for cluster 1 and weak-to-unusable advice for later clusters on this room.

## Negative claims / paths checked
- No separate "post-retreat" savestate exists (`Glob **/kirby*.state` — same 12 files as the
  d-probe's own negative claim); post-retreat positions here are simulated via `left`x6 press
  sequences from `kirby_entity2.state`'s single boot state, not independently-verified alternate
  states.
- This probe's press sequence (right x8, left x6, right x8) is a synthetic approach schedule, not
  a replay of the real v3.1 run's actual 5-drop room path — cluster correspondence to the real
  oracle's `{7,28,47,70,74}` drop steps is illustrative, not step-for-step verified.
