# MKDS lap-count oracle hunt v2 — $0 offline. Verdict: NOT FOUND

Continuation of `2026-07-23-oracle-mkds-lap.md` (checkpoint byte re-verified, lap-count byte
not found, drive time-boxed at ~2:26 without completing a lap). This session had the F3
latency-window report's open-loop spine (`2026-07-23-f3-latency-window.md`) as "the unlock"
and a live RAM checkpoint telemetry advantage the 07-23 hunt didn't use continuously. Net
result: **still NOT FOUND** — no `LAP 1/3 -> LAP 2/3` transition was observed — but the
checkpoint-byte model is materially more precise now, two of the named lead's disqualifying
behaviors were newly reproduced, and a genuine broad RAM search (not just the named lead) was
run at two real checkpoint-adjacent events. `eval/score_exam_mkds_lap.py`'s `ORACLE_PENDING`
stub is **left refusing, unchanged** — per the task's own rule, a wrong oracle is worse than
none, and this session did not clear the bar to ship one.

## Harness ($0, offline, no Docker, no paid LLM)
Same assets as prior hunts: ROM `roms/nds/Mario Kart DS (USA) (En,Fr,De,Es,It).nds`, savestate
`runs/nds3d_probe/mkds_race_start.state` (Figure-8 Circuit, 50cc, GP standing start), native
`.venv-win` py-desmume, `core.nds_emulator.DeSmuMEEmulator`. Worked in worktree
`../ai-pokemon-red-mkds` (branch `probe/mkds-lap-oracle`); ROM/state referenced by absolute
path in the primary checkout, never copied or committed. Respected the documented
one-DeSmuME-instance-per-process gotcha throughout (see Method).

## Method
**Ground truth.** David explicitly authorized eyes-on grading this session: LAP HUD state was
read directly off saved top-screen PNGs for every checkpoint in this hunt (dozens of frames).
**Every single one showed `LAP 1/3`.** This is the model-graded (Claude-read-the-screenshot),
pending-David's-validation ground truth this report rests on: **no lap transition ever
happened**, so no oracle candidate could be verified against a real lap boundary this session.

**Drive harness (`reports/probes/2026-07-25-mkds-lap/`).**
- `drive_lap.py` — a from-scratch, single-process, closed-loop driver: default reflex is the
  F3 spine (accel + pulse-left), with a speed-oracle-triggered reverse/steer recovery state
  machine and passive telemetry logging of the two known checkpoint bytes every frame. Smoke
  test (2000 frames) showed this fixed reflex+recovery alone stalls out near the very first
  bend (repeated wall contact within ~600-1600 frames, checkpoint byte never ticks) — the
  track requires per-turn adaptation the F3 spine (validated only through turn 1 in isolation)
  does not generalize to blindly.
- `step.py` — the tool actually used for the bulk of this session: loads a savestate, drives
  ONE fixed policy for N frames, saves a new savestate + a screenshot, and appends the exact
  per-frame commands to a running log. This turns "one emulator instance per process" from a
  constraint into a working method: each call is a new process (the gotcha is respected), and
  the emulator STATE persists across calls via the savestate file, letting a human-in-the-loop
  (here: the agent, reading screenshots) drive incrementally across many process invocations.
  Available policies: `pulse_left/right`, `full_left/right`, `straight`, `reverse`,
  `reverse_left/right`, `coast`, `wiggle`, `gun_wiggle`.
- `auto_recover.py` — when stuck, reloads the SAME stuck state repeatedly (one instance,
  `load_state` in a loop — not a second `DeSmuME()`, so still one-instance-per-process) to
  empirically test which short recovery policy actually regains speed, then commits to the
  winner for a longer follow-through. Useful but not sufficient alone (see Findings).
- `ram_diff.py` — dumps the full 4MB NDS main-RAM region (`0x02000000`-`0x023FFFFF`) from two
  savestates and diffs them, with an optional "boring" baseline pair to subtract the
  continuously-ticking noise floor (timers, per-frame physics/animation state for all 8
  racers). Used for the genuine broad search in Findings, not just spot-checking the named
  lead.
- `verify_continuous.py` / `verify_reload.py` — determinism and save/reload persistence
  checks; see Findings below.

**Piloting.** Roughly 60 driving decisions (`step.py`/`auto_recover.py` invocations) across a
main chain and several branches explored from mid-chain savestates (to retry a difficult
corridor with a different steering choice without re-driving from the start — safe because
`step.py` never re-instantiates DeSmuME, only reloads state files). Every decision was made
from the RAM speed/checkpoint oracles plus, whenever the outcome was ambiguous or a recovery
was needed, a screenshot (top chase-cam + bottom minimap). This is materially different from
the 07-23 hunt's pure vision-guided loop: RAM telemetry caught stalls and checkpoint events
between screenshots, so screenshots were pulled on-demand rather than every step.

## What was covered
- **Main chain** (`commands.json`, fully reproducible from `mkds_race_start.state`): **8,860
  frames** (~148 s of race time). Cleared turn 1 cleanly (matches F3's isolated >500f
  measurement), then required increasing manual correction through a recurring
  guardrail-lined corridor (visually identified by a repeating "SUPER MARIO"-banner texture
  and, separately, a "DANGEROUS"-banner texture — both are decorative wall skins reused at
  multiple points along the course, not one physical wall we kept teleporting back to; this
  was confirmed by minimap position differing at each encounter). Best checkpoint state
  reached on this chain: `ckpt90` (0x022C8090) transiently **4**, `ckpt94` (0x022C8094)
  stable at **1**.
- **Branch exploration** (`commands_alt/c/d/e/f/g/h/i.json`, each rooted at a named mid-chain
  savestate, individually reproducible but not concatenated into one from-origin log): a
  further ~6,000 frames of retries. Found a working steering choice (`pulse_right`, not
  `pulse_left`) through the first chokepoint, reaching a new clean high-speed state beyond it
  — then hit a second, similar chokepoint shortly after and did not clear it. `ckpt94` never
  advanced past **1** in any branch.
- Total: **~40 real driving decisions with screenshots inspected**, **~60 emulator
  invocations**, **~15,000 total frames of button input attempted** (with branch overlap, not
  15,000 frames of unique track distance). `LAP 1/3` the entire time.

## Findings (banked, verified this session)

**1. The F3 spine is real but local to turn 1, not a lap-spanning autopilot.** Confirmed
independently (fresh drive, not reusing 07-23's data): `accel + pulse-left` clears turn 1 and
holds top speed for the same >500f-scale window F3 measured. Beyond turn 1 it is actively
harmful — continuing pulse-left too long **caused** two of the wall strikes in this session
(the road straightens/reverses curvature after turn 1; a fixed bias overshoots). No fixed
open-loop policy survived more than ~100-250 frames anywhere past turn 1 without a steering
change; full-lap driving on this course requires per-segment adaptation, open-loop or closed
on speed alone is not enough.

**2. `0x022C8090`/`0x022C8094` semantics refined — and 0x022C8090 gets a SECOND, independent
disqualification.** The 07-23 report established `0x022C8090` = checkpoint-within-lap,
bidirectional (decrements on a confirmed wrong-way event) and flagged `0x022C8094` as the
best surviving lead (didn't decrement on that one wrong-way event). This session adds:
   - `0x022C8090` can jump by **more than 1** in a single step (observed 0→3, 3→4, i.e. not a
     simple ±1 tick), and — the new finding — **after a sustained stuck/off-track period
     (roughly 250-700+ frames unresponsive to all inputs), `0x022C8090` gets reset DOWN to
     EXACTLY match `0x022C8094`'s current value**, reproduced twice independently (4→1
     matching 94=1, both times) via a genuine broad RAM diff (Finding 3), not just the two
     addresses in isolation. This is consistent with `0x022C8094` = "last CONFIRMED
     checkpoint / respawn anchor" and `0x022C8090` = "current/tentative pointer," rolled back
     to the anchor on what looks like an off-track penalty. **This independently disqualifies
     `0x022C8090` as a lap oracle a second way** (beyond the already-known bidirectional
     wrong-way decrement): it is reset by a stuck-timeout mechanic unrelated to genuine lap
     completion, so a bare "did this byte wrap to 0" test would false-positive on a stuck
     recovery, not just a wrong-way drive.
   > **[FALSIFIED 2026-07-28 — PR #177, `reports/2026-07-28-oracle-mkds-lap-v3.md`. Original text
   > below left as written.]** The next two bullets are both wrong. `0x022C8094` reaches **3** and
   > then **decrements to 1** (`0→1@f1920 →3@f6210 →1@f10200` on a zero-input coast), so neither
   > "only values 0/1 were observed" nor "the non-decrement property is corroborated" survives. It
   > is a checkpoint/respawn anchor, not a lap-adjacent counter. The real lap byte is a separate
   > per-racer array (stride `0x8C`, base is per-race).

   - `0x022C8094` stayed flat at **1** across every one of these reset events in this session
     (multiple independent occurrences, not the single data point 07-23 had) — the
     non-decrement property is now corroborated, not just single-sampled. It also survived a
     save+reload round-trip unchanged (`verify_reload.py`: `ckpt90=1, ckpt94=1` before and
     after `save_state`→`load_state` in the same process).
   - **Not yet resolved: BCD vs plain-int.** Every value of `0x022C8094` observed this session
     was 0 or 1 — identical under both decodings. This is genuinely inconclusive, not silently
     assumed; a future session needs `0x022C8094` to reach ≥10 (plain) to distinguish `0x0A`
     from a BCD `10` (`0x10`).
   - **Not yet resolved: does `0x022C8094` continue past checkpoint 2, and does it wrap at a
     lap?** Only the single 0→1 transition was observed. Zero data on later ticks or a
     lap-boundary wrap.

**3. A genuine broad RAM search was run (not just the named lead) at two real checkpoint
events**, using savestates already captured at the event boundaries and diffing the full 4MB
NDS main-RAM region against a "boring" no-event baseline pair (to subtract per-frame physics/
animation noise, ~9,000 continuously-changing bytes regardless of any checkpoint activity):
   - At the `ckpt94: 0→1` tick: 2,648 event-specific candidate bytes survived the noise
     filter — the overwhelming majority sit in a `0x02173xxx` block that is almost certainly
     per-racer physics/animation state (8 racers' worth of continuously-updating structs), not
     progress counters. `0x022C8094`'s own change (`0x00→0x01`) is correctly captured by the
     method (sanity check passed). Other same-struct-neighborhood candidates worth a future
     look: `0x022C8074` (0→6), `0x022C8078` (4→2), `0x022C80A8` (0→2), `0x022C80B4` (13→2) —
     not characterized further this session.
   - At the `ckpt90: 4→1` reset event: `0x022C8094` correctly does NOT appear in the diff
     (confirms it held flat). New candidate: `0x022C8358` ticked `0→1` in BOTH captured events
     — its offset from `0x022C8094` (`+0x2C4` = 708 bytes) matches a plausible per-kart struct
     stride, so this is most likely **kart-1's copy of the same field**, not a new candidate
     for OUR kart's progress — flagged low-confidence, not pursued further (do not treat this
     as a second confirmed lead without checking it against a different kart's finishing
     order).
   - Also touched in the reset-event diff: `0x022C8A30`/`0x022C8A34`, in the same
     neighborhood as the original 2026-07-11 hunt's unpursued "second, uncorrelated one-time
     cluster" (`0x0221C69B`/`0x0221C79B`/`0x022C8A3B`, ticked together once at frame 1560).
     This corroborates that something in the `0x022C8A2x`-`0x022C8A4x` range is a real,
     reproducible checkpoint-adjacent signal worth a dedicated bracket next time — still
     unpursued, now with two independent sessions' evidence it's not noise.

**4. Savestate-chaining (one process per driving decision) is methodologically sound.**
Verified by replaying the full 8,860-frame main-chain command log in ONE continuous process
from the original `mkds_race_start.state` and comparing to the incrementally-chained result:
`ckpt90=4, ckpt94=1, speed=22` (last 5 frames) matched exactly in both. This rules out
savestate-chain accumulation drift as an explanation for the session's driving difficulty —
the difficulty is genuine navigation/physics difficulty on this course, not a harness bug.

## What was ELIMINATED
- **`0x022C8090` as a lap oracle: eliminated, now on two independent grounds** — (a) confirmed
  bidirectional / decrements on wrong-way (07-23 finding, not re-litigated) and (b) newly
  confirmed resettable-to-anchor after an off-track/stuck timeout, unrelated to lap
  completion. Do not ship a "wraps to 0" test on this byte.
- **A single fixed open-loop policy (any direction) as a full-lap autopilot: eliminated.**
  Every fixed policy tested (`pulse_left`, `pulse_right`, `full_left`, `full_right`,
  `straight`) survived at most ~100-250 frames past turn 1 before requiring a steering
  correction. The F3 spine's ">500f, no ruin" result does not extend past the section it was
  measured on.
- **`0x022C8358` as an independent second lead: not eliminated, but demoted to low-confidence**
  — plausible alternate explanation (another kart's struct copy) not yet ruled out.
> **[SUPERSEDED 2026-07-28 — PR #177, `reports/2026-07-28-oracle-mkds-lap-v3.md`.]** The bullet
> below is resolved and negative: `0x022C8094` was driven past 1 (reaches 3) and **decrements**
> back to 1. It is ELIMINATED as a lap oracle. The lap counter was found elsewhere entirely.

- **`0x022C8094` beyond value 1: UNVERIFIED, not eliminated.** Everything checked (non-
  decrement across multiple new reset events, save/reload persistence) is consistent with it
  being the right lead. It simply was not driven far enough this session to observe a second
  tick, let alone a lap wrap.

## Verdict
**NOT FOUND.** No `LAP 1/3 -> LAP 2/3` transition was observed this session (every screenshot
checked — dozens — read `LAP 1/3`; this is model-graded, pending David's validation, per his
authorization this session). `eval/score_exam_mkds_lap.py` is **left unchanged**, still
refusing unconditionally (`ORACLE_PENDING`, `main()` returns 1) — landing a real
`_mkds_lap_success` predicate remains a hard precondition for EX05 and was not cleared here.

## Next attempt — sharpened pin
1. Resume from this session's furthest clean state past the first chokepoint (steering
   choice: `pulse_right`, NOT `pulse_left`, immediately after clearing turn 1) rather than
   re-deriving it — the branch logs in `reports/probes/2026-07-25-mkds-lap/` are reproducible
   starting points.
2. Bracket the `0x022C8A2x`-`0x022C8A4x` cluster specifically (two independent sessions now
   show activity there) before any further blind full-RAM diffing.
3. Get `0x022C8094` past value 1 (even without finishing a lap) to settle the BCD-vs-plain-int
   question, then keep pushing for the actual lap-boundary wrap.
4. Consider whether a closed-loop steering signal from the minimap (not attempted this
   session or the 07-23 one) is worth building — the per-turn direction-guessing loop in this
   session (screenshot -> guess direction -> retry) is the main cost driver of both hunts so
   far.
