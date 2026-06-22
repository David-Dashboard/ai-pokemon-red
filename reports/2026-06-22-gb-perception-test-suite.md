# GB/GBC perception & odometry test suite (2026-06-22)

A curated, web-fact-checked catalog of Game Boy / GBC games chosen to stress **different
perception+odometry challenges** for a screen-only agent, so we can prove (or break) generalization
beyond Pokémon. Built by a 12-agent survey workflow (propose by axis → web-verify camera model →
rank by test-value). **We already own** Pokémon Red, Pokémon Gold, Zelda: Link's Awakening, Kirby's
Dream Land. Pair this with the data-collection strategy: record the **raw (frame, buttons, next-frame)
substrate** game-agnostically and defer odometry/labeling to offline replay.

The axes that vary per game (the perceiver's job): self-localization/odometry, affordance vocabulary,
mode detection, OCR, entity detection, action/motion contract. The brain (decision-taking) is the
invariant we're protecting — success = how little it changes across these.

## Recommended acquisition order (each adds ONE new axis; cheapest-new-challenge first)
1. **Adventures of Lolo** — fixed-screen top-down, zero scroll + stateful affordances. Cleanest
   "self-motion from a still screen," closest to our grid → cheapest new axis. (Min baseline alt: **Boxxle**.)
2. **Zelda: Oracle of Seasons/Ages** — cleanest **flip-screen** overworld; attacks our #1 weakness
   (spatial memory across map transitions) while keeping walkable/blocked.
3. **Final Fantasy Adventure (Seiken Densetsu)** — flip-screen **+ real-time** (live world during the hard cut).
4. **Crystalis** — same follow-camera, but **real-time + 8-way diagonal** continuous odometry.
5. **Metroid II** — **side-view** version of the map-transition problem (multidirectional, non-linear 2D).
6. **Q*bert** — **isometric** projection; diagonal-hop input + iso depth. An axis nothing else touches.
7. **F-1 Race** — **pseudo-3D** road; self-motion from scenery scaling, no tile grid (on-ramp to driving/FPS rungs).
8. **The Sword of Hope II** — **first-person**, menu-issued movement; the extreme "no continuous flow" case.

Optional: **Tetris/Dr. Mario** as a *negative control* (no avatar/camera) — confirms the perceiver
doesn't hallucinate a moving camera.

## By axis (highlights; TV = test-value 1–5)
**A · top-down-follow (what we already train on):** Crystalis (real-time/8-way, TV4), Azure Dreams
(procedural floors, TV4), Micro Machines (continuous analog motion, TV3). Skip the RPG duplicates
(Crystal, Gold/Silver, DWM, Lufia, FFL2 — TV1–2).

**B · top-down-static / flip-screen (our biggest gap):** Zelda Oracle (clean flip, TV5), FF Adventure
(flip+real-time, TV5), Mole Mania (dual-layer surface/underground, TV4), Cave Noire (turn-grid, TV3 ⚠
confidence 0.55 — verify on emulator).

**C · side-scroller:** Metroid II (hardest odometry: 2D non-linear + room transitions, TV5), Super Mario
Land (irreversible forward-only camera + forced-scroll stages, TV4). Wario Land / SML2 are Kirby/Metroid
duplicates — skip.

**D · other views (zero coverage today):** Lolo (fixed-screen, TV5), Boxxle (Sokoban control, TV4),
Q*bert (iso, TV5), F-1 Race (pseudo-3D, TV5), Sword of Hope II (first-person, TV5), Kwirk (toggleable
top-down↔oblique, TV4), 1942 (vertical forced-scroll: world moves while you hold still, TV4).

## Corrections / flags from verification
- **Gauntlet II (GB)** — DROP for the flip-screen slot: the GB *port* is top-down-**follow** (only the
  arcade original is flip-screen).
- **Pokémon TCG (GBC)** — not a walking-avatar world; traversal is a cursor/node map (a discrete
  node-select "motion" stressor, TV3) — niche.
- **Cave Noire** — static-vs-flip is inferred (conf 0.55); confirm on emulator before relying on it.
- **Top Gear Pocket** ≈ F-1 Race; **Solar Striker** ≈ 1942 — keep one of each pair.
