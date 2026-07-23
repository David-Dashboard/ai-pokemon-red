# Emerald (GBA) RAM oracle hunt — $0, offline

Fills the gap flagged in `2026-07-22-graduation-exam-v1-definition.md` (EX03): `emerald_gba`'s
registry `watch` is `{}` — no GBA world has an oracle wired yet. **FOUND** (verified live).

## Harness / ROM
Drove `core.gba_emulator.GBAEmulator` (mgba) directly via a throwaway script (session scratchpad
only, not committed) — WSL `~/gba-spike` build (`reports/2026-06-29-gba-mgba-recipe.md`),
`LD_LIBRARY_PATH=~/gba-spike`, `PYTHONPATH=~/gba-spike/mgba-build/python/lib.linux-x86_64-3.8`.
ROM: `roms/gba/Pokemon - Emerald Version (U).gba` (copied from the main checkout's gitignored
`roms/gba/`, not committed). Scripted from power-on through the New Game intro (title → New Game →
Birch monologue → naming screen → moving-truck cutscene → exits into Littleroot Town → Mom's
dialogue → upstairs into the player's bedroom), screenshot-verified at every step (no blind
button-mashing past an unconfirmed screen).

## Method
Full-EWRAM (`0x02000000`-`0x0203FFFF`, 256 KB) snapshots at 4 known-*different* maps: the intro
truck interior, Littleroot Town (outside, right after exiting the truck), the player's house 1F,
and the house 2F bedroom — each sampled 2-4x (idle + after in-map movement) to reject anything that
merely *looked* stable by coincidence. A byte only counts as a map-id candidate if it is bit-exact
stable across every sample **within** a map and differs **across** the 4 maps.
A first raw scan (no address filter) returned 5884 such "candidates" — almost all in low EWRAM
(`0x02000000`-`0x02002000`), which is graphics/OAM-shadow noise, and a 256-byte-wide repeating
table at `0x02025FA0+` that is clearly a per-map tilemap/palette cache, not a scalar id. Restricting
to `>=0x02010000` and adding a 3rd/4th within-map sample (see Caveats: one candidate, `0x020249C1`,
looked perfect on 2 samples then drifted 59→60 on a 3rd bedroom revisit — **rejected**, same lesson
as the Cave Noire `0xD389` miss) narrowed to a small, well-behaved cluster.

## Verified: player position (x, y)
**`x @ 0x02037360`, `y @ 0x02037364`, both u8, tile-local.** Verified by direct action correlation
(not diffing): from a fixed savestate, pressing `right` once changed `0x02037360` by exactly +1 and
left `0x02037364` unchanged; pressing `down` once then changed `0x02037364` by +1 and left
`0x02037360` unchanged. Reproduced in two different maps (truck interior and Littleroot outside).

## Verified: map identity (mapGroup, mapNum)
Same struct neighborhood as the verified x/y (offsets -0x08/-0x24 from `x`), stable across **every**
one of 12 independent EWRAM snapshots incl. a deliberate 3rd bedroom revisit added specifically to
catch drift:

| field | address | width | truck | Littleroot (outside) | house 1F | bedroom (house 2F) |
|---|---|---|---|---|---|---|
| map_group | `0x02037340` | u8 | 0 | 2 | 2 | 2 |
| map_num   | `0x0203735C` | u8 | 9 | 10 | 15 | 14 |

`map_group=2` being shared by Littleroot's outdoor map and both of its buildings (with the special
intro/truck map at `group=0`) matches how pokeemerald-style engines group a town + its interiors;
`map_num` is a plausible small distinguishing index. This reading is **inferred from structural
adjacency + cross-map distinctness + repeat-sample stability**, not from disassembly/symbols — flag
as such, not as ground truth on par with the direct-action-verified x/y above.

## Party count (secondary) — NOT FOUND
Not attempted with confidence: the run never received a starter Pokémon (task doesn't require one
to reach Oldale), so there is no 0→1 transition available to diff against. Recommend the same
adjacency technique once a save with a non-empty party exists.

## Caveat / residual gap
Live confirmation that `map_num` changes sensibly Littleroot→Route101→Oldale was **not completed**
— Mom's NPC sprite occupies the single exit tile of the player's house and repeated attempts to
route around her (7+ direction combinations, screenshot-checked each time) did not clear the door;
stopped per the anti-thrash rule rather than repeat an 8th near-identical attempt. The map_group/
map_num fields above are verified across 4 real, distinct maps (special/truck, town, and 2
buildings) but the specific Littleroot→Route101→Oldale chain the exam task names is unconfirmed.

## Re-run receipts
Savestates + raw `.bin` EWRAM dumps + screenshots for every step are in this session's scratchpad
(not committed — throwaway harness per repo convention); re-derivable by replaying the intro
sequence above against the same ROM copy and mgba build.

## Proposed registry wiring (PROPOSE ONLY — not wired into `world_mcp.py`)
```python
"emerald_gba": {
    ...,
    "watch": {"map_group": 0x02037340, "map_num": 0x0203735C,
              "x": 0x02037360, "y": 0x02037364},
},
```
