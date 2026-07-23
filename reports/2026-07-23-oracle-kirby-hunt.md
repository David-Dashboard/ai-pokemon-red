# Kirby oracle hunt: GB stage-counter + GBA level-oracle (2026-07-23)

Status: **$0 local probe only**. No paid run, scorer edit, tool-schema edit, or world_mcp.py edit.
Scratch scripts + RAM dumps live outside the repo (session scratchpad); nothing committed under
`runs/`. Per `reports/2026-07-22-graduation-exam-v1-definition.md` EX02/EX04 readiness gaps.

## Method

Scripted play via a direct PyBoy/mgba driver (savestate round-trip across steps, no LLM brain, no
paid tokens) + RAM-diff/RAM-search against the live emulator, mirroring `record.py --watch`'s
discipline (oracle never touched code, offline only). GB: local PyBoy, ROM
`roms/Kirby's Dream Land (USA, Europe).gb`. GBA: WSL `~/gba-spike` mgba build (per
`reports/2026-06-29-gba-mgba-recipe.md`), ROM `roms/gba/Kirby - Nightmare in Dreamland (U) [!].gba`,
via `core.gba_emulator.GBAEmulator` directly.

## (a) GB — Kirby's Dream Land stage counter: **NOT CONFIRMED** (candidates only)

Could not reach an actual Stage-1→2 transition: a tall solid-wall obstacle early in Green Greens
resisted scripted flight (jump apex only ~14px; a `B`-press mid-air gave an isolated ~16-18px lift
in one OAM slot but did not reproduce on the dedicated player-Y mirror `0xD05D`, i.e. not a real
sustained float). This matches the prior **paid 587-decision brain run** (`runs/brain_kirby_longhaul`,
$43, Opus) which also never beat Stage 1's Whispy Woods — corroborating evidence this wall is a
genuinely hard obstacle, not a scripting gap.

Fell back to RAM-diff across 7 diverse Stage-1 samples (title card through score 2000, hp 6→3,
multiple screens): intersected all bytes reading a constant small int. Eliminated `0xD02D` (reads 5
at the title screen, 1 in gameplay — not stable) and the `0xD088/89/8A` cluster (6/5/5, likely
max-HP/lives, not stage-shaped). Three survivors, constant `=1` from the title card through every
Stage-1 sample gathered: **`0xD048`, `0xD052`, `0xD3EE`**. None was ever observed to increment (no
Stage 2 was reached), so these are candidates, not a verified oracle — reporting as NOT CONFIRMED
per the project's honesty norms (a probe that says "not yet" is a valid result).

## (b) GBA — Kirby: Nightmare in Dream Land level oracle: **FOUND (world index)**

Booted → File Select → Start Game → One Player → world map ("LEVEL 1: VEGETABLE VALLEY" banner,
entrance icon showing digit "1") → warp pad → Level 1-1 gameplay (verified via screenshots).

Anchored the player-stats struct by searching raw little-endian score matches across 3 gameplay
samples (score 0 / 1600 / 2600) — unique hit at **`0x02006020`** (32-bit score, confirmed exact
across all three). Adjacent byte **`0x02006014`** reads constant `=1` across all 5 samples spanning
the world map, the star/level-select screen, and 3 gameplay points (score 0→2600, hp 6→2) — matches
the visible "LEVEL 1" text and the star icon's "1" digit. Isolated single byte (not part of a
repeating table, unlike the GB candidates). **Not verified to increment** (World 2 unreached; the
"-1" sub-stage component of "1-1" was not separately isolated — only one world/sub-stage was
reachable this session).

## Proposed wiring (propose only — NOT applied to `world_mcp.py`)

```python
# kirby_dreamland (GB) — candidates only, NOT a confirmed oracle; verify by finally reaching Stage 2
# "watch": {"hp": 0xD086, "stage_candidate_a": 0xD048, "stage_candidate_b": 0xD052,
#           "stage_candidate_c": 0xD3EE},

# kirby_gba — world index candidate (score is free bonus, exact-confirmed)
# "watch": {"world": 0x02006014, "score": 0x02006020},
```

## Verdict

GB: **NOT-FOUND** (candidates banked, no confirmed increment). GBA: **FOUND** for the world
component only; sub-stage component open. Next useful $0 step for GB: retry the wall with a fresh
float-timing sweep or find an alternate route (down/under) before spending a paid run. Next for
GBA: reach the end of Level 1-1 (or find File 2/3 differently seeded) to observe an actual
world/sub-stage transition and confirm `0x02006014` plus locate the sub-stage byte.
