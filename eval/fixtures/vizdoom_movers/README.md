# ViZDoom StationaryMovers fixtures (curated, committed)

20 frame pairs backing `tests/test_stationary_movers.py` for `core/stationary_movers.py` (P2
`StationaryMovers`, `reports/2026-07-04-vizdoom-3d-floor-design.md` S1.2 + AMENDMENT A1). Sampled from
`runs/vizdoom_precheck/dtc_mixed/` (gitignored, the free pre-check's fresh action-log-aligned
`defend_the_center` capture — AMENDMENT A1.5: the only valid fixture source; the older 2026-07-02
probe capture has a known one-frame action<->frame misalignment and is not used anywhere).

## Contents

- `mover{00..07}_a.png` / `_b.png` — `category: stationary_movers`. IDLE action pairs where a walking
  monster's motion clears `pix_t=25/min_area=30` (>=1 diff component). 8 pairs.
- `empty{00..05}_a.png` / `_b.png` — `category: stationary_empty`. IDLE action pairs with genuinely
  zero components >= `min_area` (confidently nothing moving). 6 pairs.
- `turn{00..05}_a.png` / `_b.png` — `category: turning`. TURN_LEFT/TURN_RIGHT action pairs (P1 reports
  a real direction), spread across both directions and both the burst and single-turn regimes present
  in `dtc_mixed/`. 6 pairs.
- `manifest.json` — one record per pair: `frame_a`/`frame_b`, `category`, `action` (commanded action
  for that step), `src_pair` (source frame filenames, for provenance), and `top_component_areas` (the
  diff-component areas at derivation time, informational — the tests recompute live).

## pix_t / min_area derivation (recorded here, not just in the module docstring)

A sweep over ALL 110 consecutive frame pairs of `dtc_mixed/` (37 IDLE, 73 TURN, by the logged action),
at 4-connectivity:

| pix_t | min_area | stationary comp-count median | turning comp-count median |
|---|---|---|---|
| 15 | 30 | 1.0 | 24.0 |
| 20 | 30 | 1.0 | 16.0 |
| **25** | **30** | **1.0** | **13.0** |
| 30 | 30 | 1.0 | 3.0 |

`pix_t=25, min_area=30` (the design doc's own S1.2 starting point) reproduces a >10x separation
between stationary and turning component counts on this independent, alignment-clean capture — close
to the design's S1.3 probe numbers (stationary median 4.5 vs turning median 19, on a *different*,
since-superseded dtc capture). This is the floor pinned in `core/stationary_movers.py`.

**Known artifact, not filtered:** ATTACK is "ego-stationary" by AMENDMENT A1.3's own definition (it
doesn't turn the camera), but ATTACK pairs in `dtc_mixed/` show large diff components from the
weapon's own muzzle-flash brightening the frame (mean jumps ~75->81) — an ego-generated artifact, not
a world "mover". P2 cannot and does not distinguish this (meaning-free blob reporting, per the
design's anti-drift table); the committed `stationary_movers`/`stationary_empty` categories are drawn
only from IDLE pairs so this artifact doesn't contaminate the fixture derivation.

## Provenance / regeneration

Not reproducible from a clean checkout alone (`runs/vizdoom_precheck/dtc_mixed/` is gitignored output
from a live Docker + `vizdoom==1.3.0` capture). To regenerate: re-run
`runs/vizdoom_precheck/capture_dtc_mixed.py` (see `PRECHECK_REPORT.md` for the recipe), then re-derive
the pix_t/min_area sweep and re-curate this directory (the selection was a one-off hand-picked
subset across the categories above, not a committed sampler script — the 20-pair manifest here is the
artifact of record).
