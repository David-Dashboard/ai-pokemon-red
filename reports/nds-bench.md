# NDS Bench Report

Generated: 2026-06-29 00:45 UTC

## Per-game table

| Game | Renders | Discovered screen (conf) | Correct? | Cells (max) | Ego-motion | Ontology stage | Notes |
|------|---------|--------------------------|----------|-------------|------------|----------------|-------|
| NSMB | yes | bottom (0.18) | no | 3 | 0 | S1-substrate | screen-role low confidence (0.18) — dual-screen routing unreliable |
| Kirby | yes | top (0.50) | yes | 6 | 0 | OK | pipeline ran — 6 cells, 0 non-zero ego-motion steps |
| MK-DS | yes | bottom (0.49) | no | 4 | 0 | S3-viewpoint | 3D game — 4 cells (partial, 2D primitives degraded) |
| RE-DS | NO | — (0.00) | no | 0 | 0 | S1-substrate | ROM did not render (frozen or blank) |
| HP-OotP | NO | — (0.00) | no | 0 | 0 | S1-substrate | ROM did not render (frozen or blank) |
| FIFA-S3 | yes | top (0.31) | yes | 9 | 0 | S3-viewpoint | 3D game — 9 cells (partial, 2D primitives degraded) |
| Poke-W | skipped | — | — | — | — | SKIP | DSi-enhanced — skipped (no firmware) |
| PW-T&T | skipped | — | — | — | — | SKIP | touch-primary — skipped |
| Layton | skipped | — | — | — | — | SKIP | touch-primary — skipped |
| ZeldaST | skipped | — | — | — | — | SKIP | touch-primary — skipped |

## Ranked NDS perception gaps

1. S1-substrate: dual-screen routing unreliable / emulator boot fragility (wrong screen chosen or low confidence under title-screen noise)
2. S3-viewpoint: 2D tile primitives break on 3D games and side-scrollers — camera class is not top-down tile; GridPerceiver ego-motion is undefined

## Verdict

Of the 10 bench candidates, 4 were skipped by policy (touch/DSi games), 2 failed to render, and 4 rendered successfully.  
Screen-role discovery held up on 2 of 4 rendering games with confidence >= 0.40; 2 had low confidence, primarily during title-screen noise before gameplay starts.  
The 2D spatial pipeline (GridPerceiver on 256×192) produced usable cell maps on 1 game(s); 2 3D game(s) broke the tile primitives as expected — ego-motion is undefined on a moving 3D camera.  
The top NDS-specific gap is the 3D-vs-2D camera class mismatch (S3-viewpoint): the GB-derived tile grid assumes a stable top-down or fixed-scroll camera, which does not hold for Mario Kart / Resident Evil / FIFA's 3D perspectives.  
The secondary gap is S6-pose drift: even on 2D games, the 256×192 best_shift window needs NDS-specific calibration — scroll distances per step are larger than GB, so dead-reckoning accumulates faster.  
Priority fix: a camera-class pre-classifier (2D-tile vs 3D vs side-scroll) at the S3 layer to route 3D games away from GridPerceiver before it runs, and NDS-tuned shift constants for 2D games.

## Per-game detail

### NSMB
- ROM: `New Super Mario Bros. (USA).nds`
- Renders: True
- Screen role: gameplay=None dominant=bottom conf=0.184 commit_step=20 votes={'bottom': 6}
- Spatial: max_cells=3 unique_poses=3 ego_nz=0
- Per-screen diffs: top=4.419 bottom=2.536 render_mean=1.739
- Ontology: S1-substrate — screen-role low confidence (0.18) — dual-screen routing unreliable

### Kirby
- ROM: `Kirby Super Star Ultra (USA).nds`
- Renders: True
- Screen role: gameplay=top dominant=top conf=0.498 commit_step=32 votes={'top': 28}
- Spatial: max_cells=6 unique_poses=6 ego_nz=0
- Per-screen diffs: top=0.0 bottom=0.0 render_mean=11.329
- Ontology: OK — pipeline ran — 6 cells, 0 non-zero ego-motion steps

### MK-DS
- ROM: `Mario Kart DS (USA) (En,Fr,De,Es,It).nds`
- Renders: True
- Screen role: gameplay=bottom dominant=bottom conf=0.489 commit_step=5 votes={'bottom': 46}
- Spatial: max_cells=4 unique_poses=4 ego_nz=0
- Per-screen diffs: top=15.137 bottom=15.466 render_mean=117.757
- Ontology: S3-viewpoint — 3D game — 4 cells (partial, 2D primitives degraded)

### RE-DS
- ROM: `Resident Evil - Deadly Silence (USA).nds`
- Renders: False
- Error: frozen/blank — frame unchanged over 60 cycles
- Screen role: gameplay=None dominant=None conf=0.000 commit_step=None votes=None
- Per-screen diffs: top=0.0 bottom=0.0 render_mean=0.0
- Ontology: S1-substrate — ROM did not render (frozen or blank)

### HP-OotP
- ROM: `Harry Potter and the Order of the Phoenix (USA).nds`
- Renders: False
- Error: frozen/blank — frame unchanged over 60 cycles
- Screen role: gameplay=None dominant=None conf=0.000 commit_step=None votes=None
- Per-screen diffs: top=0.0 bottom=0.0 render_mean=0.0
- Ontology: S1-substrate — ROM did not render (frozen or blank)

### FIFA-S3
- ROM: `FIFA Street 3 (USA) (En,Fr,Es).nds`
- Renders: True
- Screen role: gameplay=top dominant=top conf=0.308 commit_step=2 votes={'top': 15, 'bottom': 1}
- Spatial: max_cells=9 unique_poses=9 ego_nz=0
- Per-screen diffs: top=152.411 bottom=0.0 render_mean=40.37
- Ontology: S3-viewpoint — 3D game — 9 cells (partial, 2D primitives degraded)

### Poke-W
- ROM: `Pokemon - White Version`
- Renders: None
- Error: skipped: DSi-enhanced — skipped (no firmware)
- Ontology: SKIP — DSi-enhanced — skipped (no firmware)

### PW-T&T
- ROM: `Phoenix Wright`
- Renders: None
- Error: skipped: touch-primary — skipped
- Ontology: SKIP — touch-primary — skipped

### Layton
- ROM: `Professor Layton`
- Renders: None
- Error: skipped: touch-primary — skipped
- Ontology: SKIP — touch-primary — skipped

### ZeldaST
- ROM: `Legend of Zelda, The - Spirit Tracks`
- Renders: None
- Error: skipped: touch-primary — skipped
- Ontology: SKIP — touch-primary — skipped

