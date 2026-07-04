# MKDS continuous-time skill build + A/B pre-registration

Implements the merged design `reports/2026-07-04-continuous-time-stopwhen-design.md` (PR #98) for the
first continuous-time world: **Mario Kart DS** (`--game nds --rom <mkds>`). The design's §4 prerequisite
— an offline in-gameplay idle measurement — is **done** (free probe, `runs/nds3d_probe/idle_measurement.md`);
its numbers are pinned below. This doc is the build spec + the pre-registration for the eventual paid A/B.

## §1 Architecture — mirror the Kirby skill port

The `nds` game runs through the generic **`World`** class (`world_mcp.py:705`), the same class Kirby uses.
Kirby's skills were added to `World`'s tool surface + `World.call` dispatch, gated by `KIRBY_SKILLS=1`,
scoped to `_KIRBY_SKILLS_WORLDS = {"kirby_dreamland"}` (`world_mcp.py:556-663, 943-1300`). The NDS build
mirrors this exactly, one flag per world (design of record):

- New env flag **`NDS_SKILLS=1`**, scoped to a new `_NDS_SKILLS_WORLDS = {"nds"}` (mirror `_kirby_skills_enabled()` at `:618`).
- A `--game nds` session with `KIRBY_SKILLS`/`ARC_SKILLS` set but not `NDS_SKILLS` sees NO skill tools, and vice versa (arm isolation, verified by the seam check §5).
- Skills live only within the run (`World`-local dict, never persisted — same lifetime as ArcAgi3Session.skills).

## §2 The predicate enum (this world's closed set) — perception-free only

Per design §3, the first rung ships ONLY the two perception-free predicates. Foveated `region_*` is
deferred to the 3D-perception climb and is NOT in this enum.

- **`elapsed_frames(n)`** — fires when `emu.frame - start_frame >= n`. Uses `DeSmuMEEmulator.frame`
  (`core/nds_emulator.py:124`), the hardware frame counter.
- **`idle_settled(threshold, k)`** — fires when whole-frame **mean-abs pixel-change fraction**
  `< threshold` for `k` consecutive samples. Computed from `emu.screen_ndarray("both")`
  (`core/nds_emulator.py:100`) — the (384,256,3) buffer — with the SAME metric the probes use (mean
  |Δ| / 255 across the frame). Purely world-side; nothing reaches the agent wire.

`_parse_nds_stop_when` mirrors `_parse_kirby_stop_when` (`world_mcp.py:943`): a closed enum, raise
loudly on anything else, including the define-time satisfiability checks in §4.

## §3 Budget model — decision budget split from frame budget (design §2/§5)

- **Decision budget:** `max_iters ≤ 8` inner actions (reuse `_SKILL_MAX_ITERS`, unchanged).
- **Resolution `r`:** one inner NDS `press()` advances `hold_frames + settle_frames` frames
  (`core/nds_emulator.py:74`, default 8+16 = **24**). Pin `r = 24` (or the skill's chosen hold/settle);
  the executor reads `emu.frame` deltas rather than assuming, so `r` is descriptive, not load-bearing.
- **Frame ceiling `F`:** absolute per-`run_skill` world-time bound (reinterpret `_SKILL_MAX_WORLD_STEPS`
  as frames for this world). Pin **`F = 300`** (~5 s at 59.83 fps) — comfortably covers the ≤72-frame
  count-in hold with margin, and bounds a runaway idle-wait.
- **Sample stride `s`:** evaluate predicates every `s` frames; pin **`s = r`** (once per action) for the
  first build — the probe's settle runs (37 and 22 consecutive count-in frames) are long relative to a
  24-frame action, so per-action sampling catches them. (`s < r` intra-action sampling is a later option.)

## §4 Pinned constants (from the free probe — `runs/nds3d_probe/idle_measurement.md`)

Measured on `runs/nds3d_probe/mkds_race_start.state`, count-in→GO→race, metric identical to the
12.22%/33.23% on record. **A fixed threshold is valid** — count-in floor ~0.3% vs active-play floor
6.77% are two orders apart; window-relative NOT needed.

| constant | value | basis |
|---|---|---|
| `idle_settled` threshold | **0.01** (1.0%) | inside the clean band [~0.5%, ~6%]; above count-in floor 0.3%, below active-play floor 6.77% |
| `idle_settled` dwell `k` | **15** samples | count-in holds run 37 & 22 consecutive frames; k·s = 360 > F is rejected, so k·s ≤ F pins k ≤ 12 at s=24… → **use s such that k·s ≤ F**; with F=300, s=24 ⇒ k ≤ 12, so pin **k = 10** |
| frame ceiling `F` | **300** | ≥ 90 (design floor) with margin |
| resolution `r` | **24** | NDS press hold+settle |
| sample stride `s` | **24** | = r |
| `max_iters` | **8** | inherited |

**Correction to self:** with `s = r = 24` and `F = 300`, the satisfiability rule `k·s ≤ F` gives
`k ≤ 12`. Pin **`k = 10`** (240 frames ≈ 4 s of settle, well under F, comfortably inside the 37-frame
hold at 24-frame spacing → needs the hold to persist ~10 samples; if that proves too strict against the
37+22 frame holds, the build may drop `s` to 12 — flagged for the implementer to verify against the
probe trace, not guess).

## §5 Degenerate guards + define-time checks (design §7)

- **Conditional-half gate** (the A/B scores on this, not the code): a run counts as skill-evidence only
  if **≥1 `run_skill` call had its `stop_when` fire before `F`/`max_iters`** (a real predicate branch,
  not a ceiling timeout), evaluated at skill granularity. This is the rung-1 verdict's own stricter
  proposal (`reports/2026-07-03-skill-rung1-ab-verdict.md:104-110`).
- **Define-time satisfiability** (mirror `world_mcp.py:963-971`, raise loudly): `s ≤ r`;
  `F ≤ max_iters · r` is NOT required (F is an absolute cap, may be < iters·r); every predicate must be
  reachable — `elapsed_frames(n)` needs `n ≤ F`; `idle_settled(…,k)` needs `k·s ≤ F`. Reject at define, not runtime.
- **Clean abort:** no `stop_when` within `F` ⇒ end + log reason (mirror Kirby `:1108`), never a hang.

## §6 Seam check (free, before any spend)

Mirror `runs/brain_kirby_v3_1/seamcheck.sh`: tools/list against the exact `--game nds` docker command.
Assert: `NDS_SKILLS=1` ⇒ `define_skill`/`run_skill` present; unset ⇒ absent; `KIRBY_SKILLS=1` alone on a
`--game nds` session ⇒ skill tools ABSENT (arm isolation). Must pass before the A/B.

## §7 Pre-registered A/B gate (the eventual paid run — NOT authorized here)

Same shape as the rung-1 skill A/B (`reports/2026-07-03-skill-rung1-ab-verdict.md`):
- **Arm A (baseline):** `press_button`/`observe`/`wait`/`remember` only — NO skill tools.
- **Arm B:** `NDS_SKILLS=1` — adds `define_skill`/`run_skill` with the §2 enum.
- **Task (hold/time-reachable only, per design §8):** from `mkds_race_start.state`, "launch cleanly off
  the start line and reach lap 1 / first checkpoint" — a task where holding accelerate through the GO
  edge and timed inputs help, and steering-by-minimap (needs deferred `region_*`) is NOT required.
- **Pinned metric:** world-frames advanced per decision (batching leverage), bar **≥ 1.3×** Arm A (the
  rung-1 bar), AND Arm B must show **≥1 qualifying-conditional call** (§5). Exact task-progress oracle
  (checkpoint/lap from RAM, off the agent wire) pinned in the build PR from an offline oracle hunt.
- **Discipline (inherited, non-negotiable):** account-B only, blank-agent wipe, one attempt, oracle/RAM
  off the wire, `--max-turns` = budget, Arm A first. **This paid run needs David's explicit go + a cost/
  agent-count heads-up; the build PR lands the machinery, not the spend.**

## §8 Honest bounds

- One game, one savestate; count-in→GO validated, a lap/results banner not separately measured (design
  §3 notes the method transfers). The A/B task is scoped to avoid needing that.
- `region_*` / minimap steering explicitly out of scope until 3D perception ships.
- The `k`/`s` pin (§4) is the one number the implementer must re-check against the probe trace rather
  than take on faith — a too-strict dwell would make `idle_settled` never fire on the real 37/22-frame holds.

## Sources
- `reports/2026-07-04-continuous-time-stopwhen-design.md` (PR #98) — the design this implements.
- `runs/nds3d_probe/idle_measurement.md` — the free in-gameplay idle probe (threshold band, k/s basis).
- `world_mcp.py` — `World` class (`:705`), Kirby skill port to mirror (`:556-663` gating, `:943` parser,
  `:1018` define, `:1155` run, `:963-971` define-time checks, `:1108` clean-abort), `_NDS_WORLDS` (`:65`),
  `nds` GAMES entry (`:128`).
- `core/nds_emulator.py` — `press`(`:74`)/`tick`(`:86`)/`screen_ndarray`(`:100`)/`frame`(`:124`).
- `reports/2026-07-03-skill-rung1-ab-verdict.md` — the A/B shape + the conditional-half gate (`:104-110`).
