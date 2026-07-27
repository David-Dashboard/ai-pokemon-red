# Kirby's Dream Land (GB) stage-counter oracle hunt (2026-07-25)

Status: **$0 local probe only, offline PyBoy, NO LLM, NO Docker, NO paid run.** Worktree
`probe/kirby-gb-stage-oracle` (`../ai-pokemon-red-kirbygb`). Per EX02
(`reports/2026-07-22-graduation-exam-v1-definition.md`, branch `docs/exam-v1-definition`
— PR #129 / v1-DRAFT, not frozen) and the stub docstring in `eval/score_exam_kirby_stage3.py`.
Starting point: `reports/2026-07-23-oracle-kirby-hunt.md`'s three commented-out candidates
(`0xD048`, `0xD052`, `0xD3EE`), all NOT-FOUND there (no stage transition was ever reached).

**Verdict: PARTIAL / NOT-FOUND-FOR-EX02.** Found and heavily verified a set of RAM bytes that
cleanly flip from `0` to `1` exactly at the Green Greens -> Castle Lololo boundary and stay
rock-stable on both sides across ~1,800 RAM samples, several independent savestates, different
rooms, and a death+continue event. But because only ONE stage transition was ever reached
(Stage 1 -> Stage 2), I cannot rule out these bytes being a one-time "left Stage 1" / "boss 1
defeated" latch rather than a genuine incrementing per-stage index — the two hypotheses are
indistinguishable without a Stage-3 sample. EX02 needs to detect *clearing Stage 3* specifically,
which requires discriminating stage index 2 from 3 from 4; a binary "past Stage 1" flag cannot do
that. All three of the prior hunt's candidates (`0xD048`, `0xD052`, `0xD3EE`) are affirmatively
**eliminated** with evidence (see below) — this hunt banks a strictly better negative result plus
a promising but incomplete lead, not a ready-to-wire oracle.

## Method

1. **Ground truth via a recorded human playthrough.** `D:/ai_pokemon_runs/2026-06-23_kirby_play/`
   (a prior human-played session, `meta.json: {"mode": "human", "ram": false}`) has 1,939 saved
   frame PNGs + a `buttons.jsonl` input log, ending at `checkpoint_01.state` (score 39460). Reading
   the frame PNGs directly (no emulation needed) with a binary-search scan found the **STAGE 2
   CASTLE LOLOLO title card at frame index 1738** (`frame` field 20872, `runs/2026-06-23_kirby_play/
   frame_001738.png`), with the pre-transition Green Greens scene still showing at **step 1732**
   (score 34160, `frame` 20800) and a blank/white transition screen at steps 1734/1736. This pins
   the exact stage-1->2 boundary in a real successful playthrough. `checkpoint_01.state` (score
   39460, step 1938, ~200 steps into Castle Lololo) is therefore a **confirmed Stage-2 savestate**
   obtainable with zero additional scripted play.
2. **Exact input replay did not reproduce the human run.** Attempted replaying `buttons.jsonl`
   through `core.gb_emulator.PyBoyEmulator` two ways — per-step `press(hold=8,settle=16)` matching
   `meta.json` (`replay_dump2.py`) and run-length-merged continuous holds (`replay_dump.py`) — both
   diverged early and got stuck at the same "tall pillar" obstacle the 2026-07-23 hunt reported
   (confirms that finding; the recorder's polling format loses timing fidelity a scripted replay
   needs). **Abandoned exact replay.**
3. **Solved the pillar with Kirby's actual float mechanic.** `float_try.py` (from a
   `reach_pillar.py` checkpoint at the pillar's base) confirmed: `A` (jump), `A` again while
   airborne (puff up/float), then `up`+`right` taps ascends and drifts Kirby clear over the
   obstacle — this is the real fix the 2026-07-23 hunt was missing (it tried a mid-air `B` tap,
   not the jump-then-second-`A` float). `combined_drive.py` spliced this sequence into the
   RLE-compiled human log and produced a genuine **575-step Stage-1 trajectory** (fresh boot
   through the pillar to score 3400), all captured with a full WRAM(`0xC000-0xE000`)+HRAM
   (`0xFF80-0x10000`) snapshot + screenshot per step.
4. **Extended the Stage-2 side from the checkpoint.** `continue_stage2.py` drove forward from
   `checkpoint_01.state` with a simple autopilot (right-biased, periodic jump/inhale), producing
   a **1,200-step Stage-2 trajectory** through several visually distinct Castle Lololo rooms,
   including one full death -> game-over -> continue cycle (lives `04->00`, then reset to `04`
   with a lower score) — a good free non-stage-event falsification case.
5. **Manual eyes-on navigation past the death loop.** `nav_step.py` (10 short hand-tuned bursts,
   screenshotted after each) got a fresh run from `checkpoint_01.state` through the moat room,
   over a second wall (float again), and through one door into a new sub-room. This confirmed the
   candidate bytes hold across a genuine door/room transition too, but did **not** reach the
   Castle Lololo boss (Lololo & Lalala) or a Stage-3 transition — Castle Lololo's block-push/door
   puzzle design resisted further blind/scripted progress within this session's budget.
6. **Full-WRAM+HRAM diff** (`ram_diff_states.py`) across 3 independently-confirmed Stage-1
   savestates (`kirby_entity.state`, `kirby_entity2.state`, `kirby_ramplay/checkpoint_01.state` —
   all screenshot-verified Green Greens) vs. the confirmed Stage-2 savestate, filtered to
   plausible small-int scalars, seeded the candidate list. `extract_addrs.py` then re-checked
   every candidate across the full 575-step Stage-1 and 1,200-step Stage-2 trajectories to catch
   anything that only looked stable in the thin 4-state sample (the Cave Noire "2-anchor" trap).

## Candidate table

| Address | Stage-1 (n=3 states + 575-step traj.) | Stage-2 (n=1 state + 1,200-step traj.) | Verdict |
|---|---|---|---|
| `0xC057`, `0xC073`, `0xC07B` | constant `0` | constant `1` | **survives** |
| `0xD03B` | constant `0` | constant `1` | **survives** |
| `0xD19F` | constant `0` | constant `1` | **survives** |
| `0xD3A9` | constant `0` | constant `1` | **survives** |
| `0xD3BA` | constant `0` | constant `1` | **survives** |
| `0xD3CD` | constant `0` | constant `1` | **survives** |
| `0xC033` | mostly `1` | jumps to `97` mid-trajectory | ELIMINATED (unstable, tile-buffer-like) |
| `0xD165`, `0xD18B`, `0xD414` | constant `0`/`1` in short (300-step) Stage-2 sample | **flips within Stage 2** once the trajectory is extended to 1,200 steps | ELIMINATED (unstable) |
| `0xD18C` | constant `0` | `1` for the first ~500 steps, then flips to `0` around step 650, back to `1`, then `0` again from ~700 on | ELIMINATED (unstable within Stage 2) |
| `0xD34D` | constant `0` | constant `1` through step 800, then **flips to `0`** at step ~850 (coincides with the death/continue event) and stays `0` | ELIMINATED (changes on a non-stage event) |
| `0xD048` (2026-07-23 candidate) | constant `1` | **constant `1`** (never changes, in either stage) | ELIMINATED — not stage-related at all |
| `0xD052` (2026-07-23 candidate) | constant `1` | mostly `5`, but **drops to `1`** around the death/continue event (step ~850) and briefly elsewhere | ELIMINATED — volatile, not a stage index |
| `0xD3EE` (2026-07-23 candidate) | constant `1` | identical behavior to `0xD052` (moves in lockstep — likely a mirror of the same value) | ELIMINATED — same reasoning as `0xD052` |

Both BCD and plain-int decoding are identical for the 8 survivors (values are only ever `0`/`1`,
so `(b>>4)*10+(b&0xF)` == `b`) — the BCD-vs-plain-int question the Cave Noire lesson raised does
not distinguish anything here; it will matter once a Stage-3+ sample shows a two-digit value.

## Additional falsification checks (the 8 survivors, using `0xD19F`/`0xD3A9`/`0xD3BA`/`0xD3CD` as
representatives in `final_checks.py`)

- **Pausing** (`start` to open/close the pause menu on a Stage-2 state): no change.
- **Save/reload round-trip** (save state in one `PyBoyEmulator` instance, load in a brand new
  instance): value survives unchanged.
- **Fresh boot / title screen** (no state loaded): reads `0` — sane baseline (pre-game = "world 0").
- **Death + game-over + continue** (naturally captured in the 1,200-step Stage-2 trajectory):
  the 8 survivors held at `1` through the whole event; `0xD052`/`0xD3EE`/`0xD18C`/`0xD34D` did NOT
  (see table) — this is exactly the kind of event the previous hunt's candidates would have
  silently failed against had a transition ever been reached.
- All 8 survivors move in perfect lockstep across every sample gathered (most likely several are
  mirrors of the same underlying value, kept in sync by the game for different subsystems — HUD
  digit, palette select, music track, etc.). No disassembly was consulted; this is inferred purely
  from behavioral correlation.

## Why this is NOT a FOUND verdict for EX02

EX02 needs "clear Stage 3", i.e. an oracle that can tell stage index 3 (or the 3->4 transition)
apart from 2 and 4. Every survivor here is proven only to encode **"is it Stage 1, or not"**
(reading `0` pre-transition, `1` post-transition, 0-indexed) from a single observed transition.
Two hypotheses fit 100% of the collected evidence and cannot be distinguished without a Stage-3
sample:
1. It's the real stage/world index (0,1,2,3,4 for Green Greens..Mt. Dedede) — the wanted oracle.
2. It's a one-time latch (e.g. "left the first stage" / "Whispy Woods defeated") that sets once
   and never changes again for the rest of the game.

Reaching Stage 3 requires clearing Castle Lololo's boss (Lololo & Lalala), which needs
block-pushing puzzle solving that blind/scripted play could not reliably do within this session's
$0 budget (see step 5 above — got through ~3 rooms via hand-tuned bursts, still deep in Castle
Lololo when the session was time-boxed). Per the project's honesty norms, a banked partial result
with eliminations is reported rather than guessing which hypothesis is true.

## Stage-transition frame indices observed

- Human recording (`D:/ai_pokemon_runs/2026-06-23_kirby_play/buttons.jsonl` / frame PNGs):
  step **1732** = last confirmed Green Greens frame (score 34160); steps **1734, 1736** = blank
  transition frames; step **1738** = "STAGE 2 CASTLE LOLOLO" title card confirmed on-screen
  (**model-graded / eyes-on read of the saved PNGs, pending David's validation**).
- My own `combined_drive.py` trajectory: pillar reached and cleared by RLE-step ~200-211 (the
  hand-tuned float sequence), Stage 1 continues to step 574 (score 3400) without a second
  transition (never reached the Whispy Woods boss in this branch of the drive).
- My own `continue_stage2.py` / `nav_step.py` trajectories: entirely within Stage 2 (Castle
  Lololo), score 39460 -> ~48160 across ~1,200 autopilot steps + 10 manual bursts; one death +
  game-over + continue cycle observed (~step 650-850 of `continue_s2_long`); no Stage-3
  transition reached.

## Files (probe scripts, committed; scratch RAM dumps/screenshots stayed in the session scratchpad
per the 2026-07-23 hunt's convention, nothing under `runs/`)

`reports/probes/2026-07-25-kirby-gb-stage/`:
`inspect_states.py` (dump candidate bytes + screenshots for existing savestates),
`replay_dump.py` / `replay_dump2.py` (the two failed exact-replay attempts, kept for the record),
`reach_pillar.py` + `float_try.py` (the float-over-the-pillar fix), `combined_drive.py` (prefix +
float + resume, full WRAM/HRAM+screenshot dump per step), `continue_stage2.py` (Stage-2 autopilot
from the checkpoint), `nav_step.py` (manual eyes-on burst navigation), `ram_diff_states.py` (the
systematic 4-state WRAM+HRAM diff), `extract_addrs.py` (read specific addresses out of a `ram.bin`
dump across step ranges), `final_checks.py` (pause / save-reload / fresh-boot checks).

## Next step (not done here — wiring is a separate, later PR)

Do **not** wire any of the 8 survivors into `world_mcp.py` or `eval/score_exam_kirby_stage3.py`
yet. The next $0 session should continue from `D:/ai_pokemon_runs/2026-06-23_kirby_play/
checkpoint_01.state` (or a fresh checkpoint saved further in) with either (a) more patient
eyes-on manual navigation through the rest of Castle Lololo to the Lololo & Lalala boss, or
(b) a real human play session (fastest path — a human can solve the block puzzles in a few
minutes) recorded with `"ram": true` this time so RAM is sampled during play, removing the need to
replay/reconstruct it afterward. Either way, the goal is one clean Stage-2 -> Stage-3 sample to
test whether any of the 8 survivors reads `2` there (confirming a real incrementing stage index)
or stays at `1` (confirming the one-time-latch hypothesis and sending the hunt back to square
one for a *different* byte).
