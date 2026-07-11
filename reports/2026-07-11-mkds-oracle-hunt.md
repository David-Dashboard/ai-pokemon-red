# MKDS task-progress oracle hunt — $0 offline

Fills the gap flagged in `2026-07-11-mkds-launch-surface.md` ("Oracle hunt ... not done here")
and `2026-07-04-mkds-continuous-time-build-plan.md` §7. **FOUND** (verified live, see caveats).

## Harness / ROM
Direct-drove `core.nds_emulator.DeSmuMEEmulator` inside `gb-mcp-world:latest` (py-desmume, no
MCP), same pattern as `runs/nds3d_probe/idle_probe.py`. ROM: `roms/nds/Mario Kart DS (USA)
(En,Fr,De,Es,It).nds` (serial `NTR-AMCE-USA`, crc `D47555BE`) — matches the launch surface's
`--rom`. Savestate: `runs/nds3d_probe/mkds_vision/mkds_race_start.state`, byte-identical (`cmp`)
to `runs/nds3d_probe/mkds_race_start.state`, the one `--init-state` actually points at. Scripts
throwaway, session scratchpad only, not committed. **Gotcha**: py-desmume SIGSEGVs on a second
`DeSmuMEEmulator` in one process — one instance per `docker run`.

## Candidate 1 (wiki): TASVideos "MKDS Info.lua" pointer chain — DEAD END for GP mode
`ptrCheckNum @ 0x021755FC` (deref → struct) `+0x46` (u8 checkpoint) / `+0x38` (s8 lap). Version
probe (`read_u32(0x02000B54) - 0x0216F320`) resolved to **exactly 0** for this ROM — address is
version-correct. But the resolved struct (base `0x0236A7A4`), and the sibling `ptrRacerData`
struct (`0x0217ACF8` → `0x0236E6AC`, incl. position), is **frozen** across ~125s of live GP racing
with real, visually-confirmed forward kart movement (screenshots, race clock incrementing).
Conclusion: Time-Trial/ghost-mode-specific, inert during Grand Prix (our savestate: Mushroom Cup,
50cc GP) — not usable for the GP-mode scorer the build plan needs.

## Method: live RAM-diff hunt (per task fallback)
Blind `press(A)` alone (or `A+RIGHT`) wedges the kart against the wall at the first Figure-8
Circuit bend **indefinitely** (screenshots at 1000+ held frames: frozen camera/scenery).
`A+LEFT` for ~1300 post-count-in frames clears the bend (screenshot-confirmed: kart past the
wall, new corridor). Full 4MB main-RAM (`0x02000000`-`0x02400000`) byte snapshots at count-in
start/end and 7 accel checkpoints out to frame 7500 under this steering. Filtered for bytes
stable across count-in, monotonic non-decreasing, small int (≤80), and NOT moving in the earlier
*unsteered* (stuck) control run — i.e. tied to real progress, not a race-elapsed timer.

## Verified oracle
**`0x022C8090`, u8, absolute address (no pointer chase).**

Trace (50-frame sampling): **0** for frames 60–1910 (count-in + kart still clearing the first
bend) → **1** at frame 1960 (just past the bend) → flat → **2** at frame 2960 → flat through
7500+ (matches the kart re-stalling in the corridor, screenshot-confirmed). Reproduced
**byte-identical** across two independent fresh-process re-runs — deterministic. Silent
(constant 0) through the full 200-frame count-in.

**Read recipe:** `emu.read(0x022C8090)` (u8), 0 at race start, +1 per progress event observed.
Treat `value > 0` as "left the start box / passed a gate" for the build plan's success criterion.

## Caveats
- Semantics inferred from timing correlation (silent when stuck, ticks only on confirmed forward
  progress), not disassembly — not 100% pinned as the "official" checkpoint index. Companion
  `0x022C8094` ticks once (→1, same frame 1960) then stays flat, unlike `0x8090`'s second tick;
  relationship uncharacterized. `0x0221C69B`/`0x0221C79B`/`0x022C8A3B` tick together once (frame
  1560, 0→2) then flat — second, uncorrelated one-time-event lead, not pursued.
- Only 2 gate events observed (kart re-stalled before lap 1); full-lap confirmation needs better
  scripted steering or a short vision-guided drive (same limitation the earlier menu-nav probe
  hit, see `FINDINGS.md`) — out of scope for a blind $0 probe.
- Verified only for this exact savestate (Mushroom Cup, Figure-8, 50cc, this kart/character).

## Oracle-spec addition (report-only, no world code touched)
```
mkds_checkpoint_progress:
  address: 0x022C8090
  width: u8
  read: absolute (no pointer chase)
  rom: NTR-AMCE-USA (Mario Kart DS USA)
  semantics: monotonic small-int, 0 at race start/count-in, +1 on confirmed forward-progress
             events; not yet confirmed against the game's true checkpoint-index field
  verified_via: runs/nds3d_probe/mkds_vision/mkds_race_start.state, 2 deterministic re-runs
```
