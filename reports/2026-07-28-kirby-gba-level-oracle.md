# Kirby GBA (EX04) level-oracle hunt — stage 1-1 CLEARED, one candidate, **not settled** (2026-07-28)

Status: **$0, offline, no paid run, no LLM, no network.** Supersedes the Kirby half of
`reports/2026-07-25-oracle-gba-exam-hunts.md` (PR #170), which ended NOT-FOUND with the level
unbeaten. Nothing is wired: `world_mcp.py`, every `watch` dict, `core/contracts.py`, tool schemas and
`eval/score_exam_kirby_gba_level1.py` are **untouched** — deliberately, per the task's hard
constraint (edits to `world_mcp.py` cascade into the frozen Gate-0 pins).

## Verdict in one line

**Candidate found, NOT confirmed as a counter.** `0x030023ec` (u8, IWRAM) reads **0** in every
observed stage-1-1 state and **1** in every observed stage-1-2 state, is the **only** index-shaped
address in either RAM region with that behaviour, and holds across 222 samples spanning ~15,700
frames of ordinary play — but only **TWO distinct values were reachable**, so the task's own
three-anchor rule is **not met**: a 1-bit "you are not in the level's first stage" flag is not
excluded.

## Game and ROM

`kirby_gba` in `world_mcp.py:182-186` → `roms/gba/Kirby - Nightmare in Dreamland (U) [!].gba`
(8 MiB, gitignored, read from the primary checkout; not committed). Structure: **Level 1 = Vegetable
Valley** (the HUD banner reads `LEVEL 1: VEGETABLE VALLEY`), containing numbered **stages** 1, 2, …
entered from a walkable world map. EX04's "Level 1-1" is Vegetable Valley **stage 1**.

## Did the GBA harness run on this Windows host? — **YES**

The WSL mgba spike from `reports/2026-06-29-gba-mgba-recipe.md` is intact and works here:
`~/gba-spike/{libmgba_patched.so.0.10.2, .venv/bin/python3, mgba-build/python/lib.linux-x86_64-3.8}`
all present; `core/gba_emulator.GBAEmulator` loads the ROM, ticks, reads RAM, screenshots and
round-trips savestates unmodified. Every number below came from real emulation on this machine.
(mgba still logs BIOS SWI chatter to **stdout**, interleaving with the driver's JSON — expected,
per the recipe.)

## New tooling (the reason this hunt got further than the last one)

1. **Savestate RAM layout — measured, not assumed.** An mgba raw GBA state is 0x61000 bytes. Both
   RAM regions sit at fixed file offsets, so every `.state` on disk is a complete RAM snapshot that
   can be swept **offline on Windows with no emulator at all**:

   | region | GBA address | savestate file offset | length |
   |---|---|---|---|
   | IWRAM | `0x03000000` | `0x19000` | `0x8000` |
   | EWRAM | `0x02000000` | `0x21000` | `0x40000` |

   Verified by reading 7 probe words live through `GBAEmulator.read()`
   (EWRAM `0x02000000/0x02020000/0x0203FFFC/0x02006020`, IWRAM `0x03000000/0x03004000/0x03007FFC`)
   and matching them byte-exact against the file at those bases. Two alternative IWRAM bases
   (`0x1000`, `0x800`) were tested and **rejected** — this is a measurement, not a guess.
   **Both regions were swept**, always.
2. **Button combos.** `reports/probes/2026-07-28-kirby-gba-level-oracle/kgba_drive.py` adds a
   `combo:` action driving `set_keys(raw=...)` with an OR-ed bitmask. The Emulator Protocol's
   `press()` is one button at a time, which cannot express "hold right while tapping A" — the only
   way Kirby crosses anything. This reaches into the private `_core` and is confined to the probe;
   `core/` is untouched, and no oracle claim depends on it (combos change **which** states we reach,
   never what RAM says once there).
3. **Offline sweeper** `kgba_ram.py` with a `cands` mode: given groups of states, keep addresses
   **constant within every group and distinct across groups**. Within-group variation kills timers,
   RNG, camera/physics scratch and animation counters with no hand-picked whitelist.

## The play breakthrough — the 2026-07-25 blocker was a door, not a hazard

PR #170 stopped at "a stationary dark object, likely a Gordo-type hazard" at score 2800 and
eliminated `right`, jumps at varied heights, and `down`. Loading that exact banked state
(`gbaexam0725_kirby/gr7.state`) and zooming shows the object is the room's **exit door** — a black
arch ringed with sparkles — sitting immediately to Kirby's **left**, with Kirby having walked past
it to the level's right boundary (evidence `01_...png`). Doors are entered with **`up` while
standing aligned with them**; the prior hunt tried `down` but never `up` at that spot, and its one
`up` test was from a position ~20px off. Walking left 22–34 frames then `up` transitions the room
every time (`02_...png`); 14–18 frames does not.

With that, stage 1-1 was played to completion for the first time in this project: 3 doors, the goal
door, the star/goal sequence, and the `LEVEL 1: VEGETABLE VALLEY` world map
(`03_...png`, `04_...png`). Stage 1-2 was then entered from the map (`05_...png`).

**Door detector, and its assumption tested separately.** Transitions were detected by counting
changed EWRAM 32-bit words between the pre-press and post-press states. The threshold was **not**
chosen to make the answer come out — it was calibrated first against four already-eyes-on-verified
presses:

| press | churn (changed EWRAM words) |
|---|---|
| door 1 entered | 1572 |
| door 1, 8px short — no entry | 2 |
| door 2 entered | 1452 |
| door 2, overshot — no entry | 14 |
| goal door entered | 3538 |
| goal door, overshot — no entry | 12 |

Three orders of magnitude of separation. **Where it fails, stated plainly:** churn cannot separate
"door" from "died and the room reloaded" — in the stage-1-2 sweep four presses scored 627–2970 and
turned out on inspection to be falls into a pit. The detector is a *screening* tool; every
transition claimed above was confirmed by looking at the frame.

## The candidate

**`0x030023ec` — u8, IWRAM.**

### Value trace

| anchor | scene | `0x030023ec` |
|---|---|---|
| stage 1-1, first playthrough (5 rooms, score 0→8800) | in-stage | **0** |
| stage 1-1 goal / star sequence | clear cutscene | **0** |
| Vegetable Valley map, immediately after clearing 1-1 | map | **0** |
| Vegetable Valley map, after a GAME OVER → CONTINUE | map | **0** |
| **stage 1-1 re-entered from the map after clearing it** | in-stage | **0** |
| stage 1-2 (entry, mid-stage, deep rooms, mini-boss arena) | in-stage | **1** |
| GAME OVER screen | menu | **0** |

The **re-entry row is the load-bearing one**: it eliminates the "past the first level" latch the task
warns about. A latch set by clearing 1-1 would still read 1 when 1-1 is replayed; this reads 0 again.
It also shows the address is a **current-stage index, not a stages-cleared count** — it is 0 on the
map *after* the clear.

### Uniqueness — the whole of both RAM regions, at three widths

Sweeping IWRAM + EWRAM for every address constant across 23 "should be 0" states (all stage-1-1
states incl. the post-clear replay, the goal sequence, both map states, the game-over screen) and
constant-but-different across 21 "should be 1" states (stage 1-2 across four independent
playthroughs incl. the mini-boss arena):

| width | addresses surviving | with an index-shaped `[0, 1]` signature |
|---|---|---|
| u8 | **4** | **1** — `0x030023ec` |
| u16 | 3 | 1 — `0x030023ec` |
| u32 | 2 | 1 — `0x030023ec` |

The other three u8 survivors are the three non-zero bytes of a single 32-bit field at `0x03006b28`
(`0x1600` → `0x1200`), not an index. So `0x030023ec` is **the unique index-shaped address in 288 KB
of RAM** under these anchors. For contrast: with only the two in-stage groups and no map/replay/
game-over states in the zero group, 402 u8 addresses survive — most of them one-way
"has-been-initialised" latches. Adding scenes from *later* in the session to the zero group is what
collapses 402 → 4.

### Sustained hold — 222 samples, not 4 frames

Not a transient title-card id. Every savestate in five dense chains of ordinary scripted play was
read:

| chain | scene | n | values seen |
|---|---|---|---|
| a1, a2, a3, a4 | stage 1-1, four consecutive room-crossing runs | 98 | `{0: 98}` |
| rp2 | stage 1-1 replayed after clearing | 9 | `{0: 9}` |
| c1 (two segments), c2, s12, bx | stage 1-2, four independent runs incl. mini-boss | 115 | `{1: 115}` |

222/222 consistent, spanning emulator frames 7,670 → 23,414 (~15,700 frames, ~4.4 min of gameplay),
across room changes, deaths, damage, a game-over/continue, and a mini-boss fight.

## What is NOT established — read this before trusting the address

1. **Only two distinct values were reached (0 and 1).** The task's three-anchor rule is **not met**.
   `0x030023ec` is consistent with a 0-indexed current-stage counter *and* with a 1-bit flag
   ("current stage is not the level's first"), and nothing here separates them. Calling it a
   counter now would repeat exactly the error the EX02 hunt made.
2. **Stage 1-3 was not reached** — it needs stage 1-2 cleared, and 1-2 was not cleared. Scripted
   play crossed 1-2's opening rooms, reached the Poppy-Bros-Sr.-type **mini-boss** (BOSS bar on
   screen), and died there. A greedy scripted search (10 macros/iteration, objective = Kirby's world
   X at `0x030021ce` u16, itself identified this session) walls at X=991 on 1-2's upper route.
   **This is the same wall PR #171 already named: the Kirby lane is gated on play capability, not on
   RAM hunting.** One stage of that gate has now been broken; the next has not.
3. **No "stages cleared" progress value was identified.** A separate sweep for a value that changes
   *because* 1-1 was cleared (before-group = pre-clear 1-1 states, after-group = map + 1-2 + replay +
   game-over) leaves **888 u8 candidates** — no identification. This design cannot exclude one-way
   initialisation latches, because the before-group is by construction all early states. Reported as
   NOT-FOUND rather than guessed.
4. **Consequence for the EX04 scorer.** Even if `0x030023ec` is confirmed, `== 1` means "currently
   inside stage 1-2", which entails 1-1 was cleared but is **not** true at the moment of clearing —
   it is 0 on the map right after the goal. A scorer built on it would require the agent to clear
   1-1 *and then enter* 1-2. That is a stricter task than EX04 as written, and is a decision for
   whoever freezes the exam, not for this probe.

### Alternative hypotheses this hunt could NOT exclude

| hypothesis | status |
|---|---|
| 1-bit "not the first stage of the level" flag | **NOT excluded** — the core gap; needs a stage-1-3 anchor |
| room index within a stage | **excluded** — held 0 across 5 distinct rooms of 1-1 and 1 across ≥4 distinct rooms of 1-2 |
| "past the first level" latch | **excluded** — reverts to 0 when 1-1 is replayed after being cleared |
| "levels cleared" counter | **excluded** — 0 on the map after 1-1 was cleared, and a game-over/continue did not change it |
| music track id | **not excluded** — 1-1 and 1-2 plausibly use different tracks; no music anchor was taken |
| tileset / graphics bank id | **weakened, not excluded** — 1-1 and 1-2 share the grass and rocky/waterfall tilesets and the value did not follow the tileset, but the value is also constant per stage, so a per-stage asset-set id is still consistent |
| checkpoint counter | **not excluded** — no mid-stage checkpoint was crossed twice |
| stack/scratch coincidence (IWRAM `0x030023ec`) | **not excluded** — it is IWRAM; a stable-looking value could be a live struct field rather than a persistent global |

## Reproduce

Scripts: `reports/probes/2026-07-28-kirby-gba-level-oracle/`
(`kgba_drive.py`, `run_kgba.sh`, `kgba_ram.py`). Curated frames: `.../evidence/`.
Savestates (443 of them) live in this session's throwaway scratch dir, per convention — not
committed, not under `runs/`.

```
# drive (WSL): wsl.exe -e bash run_kgba.sh --plan /mnt/c/.../plan.json
# sweep (Windows, no emulator):
python kgba_ram.py cands u8 "<zero-group states>" "<one-group states>"
python kgba_ram.py trace 0x030023ec:u8 <states...>
```

## Next step

Clear Vegetable Valley **stage 1-2** (mini-boss + the rooms past it + its goal door), enter stage
1-3, and read `0x030023ec` there. If it reads **2**, it is a stage counter and EX04 has an oracle.
If it reads 1 or 0, it is a flag and the hunt continues. Everything else — uniqueness, sustained
hold, latch elimination, both-region sweep — is already done and banked here.
