# MKDS lap-count oracle hardening — $0 offline

Hardens `2026-07-11-mkds-oracle-hunt.md`'s unverified `0x022C8090` (only ticked twice, no
full lap observed). **Progress oracle re-verified + a real semantics bug found. Lap-count
byte: NOT FOUND** (best lead below).

## Harness
Same pattern as the original hunt: `core.nds_emulator.DeSmuMEEmulator`, ROM
`roms/nds/Mario Kart DS (USA)...nds`, savestate `runs/nds3d_probe/mkds_race_start.state`.
Ran natively via `ai-pokemon-red/.venv-win/Scripts/python.exe` (py-desmume already installed
there, no Docker needed) — one emulator instance per process throughout (the known
py-desmume-SIGSEGVs-on-second-instance gotcha still applies). Reused the speed oracle from
today's `eval/mkds_latency_window.py` (`0x0237438C`, u32, 22 at rest / 2,031,638 at 50cc
top speed) as a live sanity check, smoke-tested fresh this session — matches exactly.

## Method
Blind scripted throttle wedges the kart against walls indefinitely (confirmed, again). Drove
via a vision-guided loop: short button bursts, inspect the saved top-screen AND
**bottom-screen minimap** (not used in the original hunt — shows kart position/heading
against the track outline, far more useful than the chase-cam for orientation), pick the
next input. Reverse (`B`) + steer to un-wedge, then accelerate. Covered far more track than
the original hunt: past the first bend, through the figure-8 crossing bridge, several more
curves, ~2:26 of race time, before time-boxing the drive.

## Progress oracle re-verified, semantics corrected
`0x022C8090` (u8) + companion `0x022C8094` (u8) both ticked **0→1→2**, each tick verified
against real minimap-confirmed forward progress (not RAM alone) — reproduced **byte-identical
prog90/prog94/speed values across an independent fresh-process replay** of the same input
sequence (frame-for-frame match on 3 checkpoints).

**New finding, not in the original report**: `0x022C8090` is **not monotonic**. Mid-drive it
dropped **2→0** while `0x022C8094` stayed at **1**. Screenshot at that exact frame shows a
**"WRONG WAY" U-turn icon on screen** — the kart had been driven backwards past a checkpoint
gate. This is the likely root cause of the original hunt's unexplained "companion `0x8094`
ticks once then stays flat, unlike `0x8090`'s second tick" — and of this session's own first
autopilot attempt (blind stall-recovery bursts drove it backwards, `0x8090` ticked 0→3 then
dropped to 1 with no lap change on screen, "LAP 1/3" throughout).

> **[PARTLY FALSIFIED 2026-07-28 — PR #177, `reports/2026-07-28-oracle-mkds-lap-v3.md`.]** The
> `0x022C8090` reading below stands. The `0x022C8094` reading does not: it **does** decrement
> (`0→1→3→1`), so it is not a "furthest checkpoint reached" or lap-adjacent counter. The lap
> counter is a per-racer array elsewhere in RAM (stride `0x8C`, base is per-race).

**Corrected semantics**: `0x022C8090` = checkpoint-index-within-lap, bidirectional
(increments forward, decrements/resets on confirmed wrong-way). `0x022C8094` did not
decrement on the same wrong-way event — a more promising, NOT-yet-confirmed lead for a
"furthest checkpoint reached" or lap-adjacent counter (single data point only).

## Lap-count byte: NOT FOUND
Never observed the on-screen "LAP 1/3" HUD advance to "LAP 2/3" in this session — despite
covering more track than the original hunt, a full lap was not completed before the drive
was time-boxed. No RAM diff was taken at a lap boundary because no lap boundary occurred.

## Best lead for the next attempt
> **[RESOLVED 2026-07-28 — PR #177, `reports/2026-07-28-oracle-mkds-lap-v3.md`.]** Lead 1 below was
> chased and is dead (`0x022C8094` decrements). The lap byte was found by a different route
> entirely: let the 7 CPU racers lap on their own and sweep all of RAM for monotone counters —
> no driving required.

1. `0x022C8094`'s wrong-way-resistant behavior (1 data point) — worth a dedicated bracket:
   drive to a wrong-way trigger, RAM-diff around it, confirm it truly never decrements.
2. The original report's unpursued "second, uncorrelated one-time-event" cluster
   (`0x0221C69B`/`0x0221C79B`/`0x022C8A3B`, ticked together once at frame 1560) — not
   re-examined this session.
3. The wiki `ptrCheckNum @ 0x021755FC` pointer chain (dead end for **Grand Prix**, per the
   original hunt) was reported live for **Time Trial** mode — untried here, GP was kept for
   consistency with the banked savestate.
4. Practical fix for future drives: the bottom-screen minimap (not used in 2026-07-11) makes
   vision-guided steering much more tractable than the chase-cam alone — use it from the
   start next time, and prefer reverse+re-align over persisting into a wall.

## Verified
- Speed oracle `0x0237438C`: confirmed live, values match `eval/mkds_latency_window.py`.
- Progress oracle `0x022C8090`/`0x022C8094`: 0→1→2 ticks reproduced fresh-process
  deterministic; bidirectional (wrong-way decrement) semantics newly confirmed via
  on-screen "WRONG WAY" indicator.
- Lap-count oracle: **NOT FOUND** — no lap boundary was reached this session.
