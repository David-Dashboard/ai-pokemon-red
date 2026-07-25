---
name: world-lanes-frontier
description: The per-lane frontier map — for each world class beyond plain GB (ARC-AGI-3, VizDoom/3D, NDS/continuous-time, MiniWoB/computer-use, glyph/text) what is BANKED, what is OPEN, and the pinned next step. Invoke when a session is pointed at any non-GB lane, when a NEW environment class arrives, or when choosing which lane advances Generality next.
---

# World-lanes frontier map

Generality (North Star claim #3, **session-start**) runs on two axes: the embodiment ladder
(2D → 3D → sim robot → robot) and the computer-use track (mouse+keyboard+screen). Each lane below is
one rung. The law that binds them all: a lane advances by PERCEIVER/WORLD-side work only — the brain
is never edited to win a lane (**architecture-and-seam**; constancy already spans five world classes
with zero brain edits, `HANDOFF.md`). This skill exists so a cheap session does not re-derive lane
state from 200KB of HANDOFF, or re-run an experiment whose verdict is already banked. Verify the
"pinned next" lines against HANDOFF's newest `⇒ NEXT` list — this map was frozen 2026-07-04 and
**refreshed 2026-07-25** (glyph R1 ran and was KILLED; the MKDS A/B ran and is banked FAIL; the
ARC/NDS "conditional-loop half never fired" bound was falsified and corrected; ARC breadth was cut
from the critical path 2026-07-05; VizDoom's held-out conflict is now flagged. MiniWoB was not
re-verified this pass). The numbered `⇒ NEXT (N)` references below that predate 2026-07-25 are from
a 2026-07-05 snapshot and are superseded — check HANDOFF's CURRENT top-of-file `⇒ NEXT` block, not
the number.

| Lane | Banked headline | Open | Pinned next |
|---|---|---|---|
| ARC-AGI-3 | skill rung-1 A/B PASS 2.94x | breadth **cut from the critical path** (2026-07-05) | none — do not buy more wa30 runs without a new mechanism |
| VizDoom/3D | GATE-3D **FAIL** K=4.074; ceiling says bar reachable (7.333); A3-PC PASSED offline | **HELD-OUT conflict unresolved** (no carve-out exists); tolerance brief edit | brief edit + David sign-off, then paid A3 re-run (pre-registered, HELD) |
| NDS/continuous | MKDS A/B **RAN, banked FAIL** (1.030x vs 1.3x bar); conditional-half guard passed | perception breaks; a fresh A/B surface | none standing — one-attempt rule spent, David's call for vNext |
| MiniWoB | 5/5 episodes, $1.36, pixels-only | harder tasks | unscheduled |
| Glyph/text | R0 FAIL banked; **R1 ran and is KILLED** at its own bar (PR #103) | R1.1 NOT decided (3 candidates) | none — David picks among vNext candidates |

## ARC-AGI-3 (abstract grid; the skill-compilation proving ground)

- **Adapter:** `core/arcagi3_world.py` — thin REST client for three.arcprize.org; the returned grid
  IS the symbolic state (no perceiver); `levels_completed` is oracle-only, never on the wire
  (`:13-16`); 250ms client throttle (`:49`); actions `ACTION1..7`, `ACTION6` takes coordinates.
  Skill tools gated behind `ARC_SKILLS=1` (`world_mcp.py:585`). **Live-run caveat:** the ARC API key
  is sourced WSL-side only (`runs/brain_arcagi3/.mcp.json` → `source /home/nvidia/.env`), not
  reachable from the Windows checkout.
- **Banked:** skill-compilation rung-1 A/B **PASS 2.94x** vs pinned 1.3x bar
  (`reports/2026-07-03-skill-rung1-ab-verdict.md`): Arm A 1/9 levels, 50 decisions, $7.78; Arm B 2/9
  levels, 34 decisions, $8.83 — the wa30 level-2 wall fell. **Honest bound, corrected 2026-07-25:**
  ARC rung-1 itself validated the BATCHING half only (0/15 skills used `repeat_until` in that run).
  The conditional-loop-FIRING half has since fired in a paid run — the NDS MKDS A/B (2026-07-13,
  `reports/2026-07-13-mkds-ab-verdict.md` §"Arm B conditional evidence": `run_skill`=10,
  `stop_when_fired=true`=9/10) satisfied that build's own pre-registered "conditional-half gate"
  (`reports/2026-07-04-mkds-continuous-time-build-plan.md` §5: "a real predicate branch, not a
  ceiling timeout"). **Still open, stated precisely:** every firing observed on any lane so far
  (Kirby's `steps_elapsed`, NDS's `elapsed_frames(n)`) is a bare elapsed-time/count predicate, not a
  world-state-branching one (e.g. `idle_settled`, `grid_changed_in_region`, `mover_visible`) — see
  **cheapness-skill-compilation** §5, which draws the same distinction for Kirby. Any NEW port's gate
  should still require the loop half explicitly, and should prefer a world-state predicate if it
  wants to retire this stricter reading.
- **Open:** breadth — one game (wa30), one attempt per arm. **Cut from the critical path 2026-07-05**
  (`reports/2026-07-05-northstar-capability-map.md:266-268`: "More levels buy ~nothing against
  A1-A6. Idle-capacity work at most.") — `HANDOFF.md:851`: "Do not buy more wa30 runs without a new
  mechanism." ARC does not appear in HANDOFF's current top-of-file `⇒ NEXT` block.
- **Pinned next:** none standing — idle-capacity work only, David's call, not on the priority path.

## VizDoom / 3D (the embodiment rung)

- **⚠ HELD-OUT CONFLICT — no carve-out exists, flagged prominently 2026-07-25.**
  `eval/dataset_split.py:30-36` lists `"Doom"` in `HELDOUT` ("3D first-person (ViZDoom) -- matches
  the `vizdoom_*` run dir"); this project's `CLAUDE.md` STOP condition is unqualified ("Never touch
  Crystalis/Zelda-LA/SML/F-1/Doom during development"); **eval-probes-and-datasets** §3 names only
  `eval/cross_game.py` and `eval/verify_heldout.py` as sanctioned held-out consumers. Yet the lane
  already calibrated on it — `core/yaw_flow.py:4-7` pins its P1 floors from `runs/vizdoom_precheck/`
  — and `reports/2026-07-05-northstar-capability-map.md:233` states "Doom is burned for 3D-primitive
  claims." Two later sessions explicitly routed AWAY from Doom on held-out grounds
  (`reports/2026-07-05-entity-v4-design.md:129`: "NOT doom — doom is HELD-OUT per PR #101's CLAUDE.md
  / eval-probes-and-datasets §3"; `reports/2026-07-13-entity-v5-candidate-shortlist.md`'s
  Doom/VizDoom row: "Do not use for v5 development"). **No documented carve-out exempting the
  GATE-3D lane from the held-out law exists.** Treat this as: VizDoom work requires David's explicit
  sign-off; a cold session must NOT start it unattended.
- **Adapter:** `core/vizdoom_world.py` (TURN_LEFT/TURN_RIGHT/ATTACK, 4-tic steps). Perception
  primitives: `core/yaw_flow.py` (P1 ego-rotation, R0-validated: sign-agreement 0.964, None-rate
  0.201, `:1-8`) and `core/stationary_movers.py` (P2, only valid on ego-stationary pairs — see
  **perception-primitives**). Free probes: `eval/vizdoom_flow_ceiling.py`, `eval/ceiling_gate3d.py`.
- **Banked:** paid GATE-3D run **FAIL, K = 4.074 vs bar 5.61** (`runs/brain_gate3d/run3_v_FAIL` —
  also the most expensive run ever, $82.86; see **long-horizon-runs**). The free ceiling test then
  answered the prior question: a perfect azimuth-seeker reaches **K = 7.333** at 8px tolerance —
  "**No re-pin is needed; the bar stands**" (`reports/2026-07-03-gate3d-ceiling-test.md:128,:130`);
  at 25px tolerance even the ceiling fails (K = 3.433), so tolerance is the lever. The onset-scoring
  fix (A3-PC) already **PASSED offline** (`HANDOFF.md:843`, 2026-07-05: "A3-PC PASS"); the paid A3
  re-run is pre-registered (`reports/2026-07-05-p1-clutter-redesign.md:312-325`) but still HELD
  pending David's go (`HANDOFF.md:842-846`) — no paid A3 attempt has run as of 2026-07-25.
- **The "tolerance tightening" knob is a BRIEF edit, not a code parameter:**
  `runs/brain_gate3d/CLAUDE.md:37`, the hunt-loop's `|x-160| ≲ 25` centering tolerance, `25` → `~8`.
  **A2.2 forbids softer re-runs**: "loosening is forbidden, period... never a softer bar"
  (`reports/2026-07-04-vizdoom-3d-floor-design.md:526-528`) — the tightening only ever moves the bar
  stricter.
- **Open:** closing the 4.074 → 5.61 gap is brief/tolerance work, not perception work; AND the
  held-out conflict above must be resolved with David before any further Doom work.
- **Pinned next:** brief-side tolerance tightening (the `CLAUDE.md:37` edit above) BEFORE any paid
  re-run; then the doom scan-and-center macro port — its gate must require the conditional-loop half
  (see the ARC section's corrected bound above). Both require David's explicit sign-off given the
  unresolved held-out conflict.

## NDS / continuous time (the hardest perception frontier)

- **Adapter:** `core/nds_emulator.py` + `core/nds_perceiver.py` (ScreenRoleDiscovery routes the
  grid perceiver to the discovered gameplay screen; touch tools via `core/nds_perception_plugin.py`).
  NDS skill tools (`define_skill`/`run_skill`) are gated behind `NDS_SKILLS=1`, scoped to
  `_NDS_SKILLS_WORLDS` (gate fn `world_mcp.py:847-854`, checked at `:905`).
- **Banked:** the 3D probe (`runs/nds3d_probe/FINDINGS.md`, on-disk) — MKDS race reached
  vision-guided; savestate `mkds_race_start.state` banked; **idle change 12.22%/frame mean vs 33.23%
  accelerating** (`:329-330`) — the world changes without input, breaking the discrete-step
  assumption; three perception breaks documented (free-form non-tile font/HUD, rotating minimap
  kills tile-grid, continuous chase-cam roll kills discrete-facing). The `stop_when` bridge design
  (`reports/2026-07-04-continuous-time-stopwhen-design.md`) and the MKDS build spec + A/B
  pre-registration (`reports/2026-07-04-mkds-continuous-time-build-plan.md`) both merged 2026-07-04.
- **The paid A/B RAN 2026-07-13 and is banked FAIL** (`reports/2026-07-13-mkds-ab-verdict.md`; the
  first account-B launch hit a weekly cap 429 at $0 before MCP connect, banked separately in
  `reports/2026-07-13-mkds-ab-blocked.md`; David then authorized the default-account relaunch).
  **Primary batching bar: FAIL — 1.030x observed vs 1.300x required** (Arm A 229.538 frames/decision
  @ $0.77483; Arm B 236.500 @ $0.7740115; total $1.5488415). **Diagnosis of record:** Arm A had
  `press_sequence` available and used it heavily (6 × 12 accelerate presses), so the baseline already
  batched many frames per LLM wake, compressing the advantage available to Arm B's skill tools. The
  build's own pre-registered conditional-half guard PASSED (`run_skill`=10, `stop_when_fired`=9/10 —
  see the ARC section above for the honest caveat on what kind of predicate actually fired). The
  build plan's §4 `s=24/k=10` sizing is **STALE — shipped code pins `_NDS_SKILL_SAMPLE_STRIDE=4`**
  (`world_mcp.py:793`; noted in `HANDOFF.md:587`).
- **No open MKDS PR and no build in flight — re-verified 2026-07-25** (`gh pr list --state open`: no
  MKDS-related PR; `git worktree list`: a checkout `ai-pokemon-red-mkds` exists on branch
  `probe/mkds-lap-oracle` but is clean and sitting exactly at `origin/main` tip — idle, not a
  mid-build parallel session). The old "a parallel session owns the build" warning is stale; a cold
  session should re-run both checks itself rather than trust this line.
- **Open:** the three perception breaks (each needs a primitive, not a hack —
  **perception-primitives** extension rules); whether a different A/B surface (e.g. an Arm A without
  `press_sequence`, or a task less amenable to input-batching) would surface the skill-tool
  advantage the 2026-07-13 run did not find.
- **Pinned next:** none standing — the pre-registered A/B is spent (one-attempt rule,
  **gate-methodology** §4). A vNext A/B surface needs its own fresh pre-registration; that is
  David's call, not a default next action.

## MiniWoB / computer-use (the second Generality axis)

- **Adapter:** `core/miniwob_world.py` — Selenium/Chromium; DOM withheld, pixels + task utterance
  only; reward is oracle-side (`:1-12`). Image pinned in `Dockerfile.miniwob`.
- **Banked:** first brain run **5/5 click-button episodes, reward 1.0 each, $1.36, pixels-only**
  (`runs/brain_miniwob/`; `HANDOFF.md:283`) — the browser rung of "constancy spans five world
  classes" (`HANDOFF.md:242`).
- **Open:** harder tasks (checkboxes, forms, typing — `HANDOFF.md:289`); not in the current top-5
  NEXT list, so it waits unless David re-prioritizes.

## Glyph / text (reading, the cross-cutting perception lane)

- **State:** R0 text-region detector **FAILED its gate and the FAIL is banked** (recall 0.27,
  precision 0.49, 5 phantom boxes vs pinned 0.85/0.70/0 — `reports/2026-07-03-glyph-r1-cache-driven-
  detection.md:5`; the module stays as a documented-honest failure, **perception-primitives**).
  `core/glyph_cache.py` (Gate 2, the cache-hit mechanism) PASSED at 96.9% frac_free and is unaffected
  by the R1 result below — it remains reusable on its own.
- **R1 build RAN and is banked KILL, 2026-07-11** (`reports/2026-07-11-glyph-r1-verdict.md`, PR
  #103, $0 — an offline scoring attempt against an existing fixture, no paid brain run). Pooled
  **precision 0.283 ≤ the 0.49 kill floor** (R0's own failed precision; pooled recall also 0.283).
  All 4 qualifying GBA games (DBZ, FFVI, Zelda Minish Cap, SMA2) individually verdict KILL. Per the
  verdict doc: "no attempt 2 permitted by the stricter-only amendment rule (a kill is not 'missed the
  bar,' it's the floor)." **Mechanism:** GBA's anti-aliased fonts blow the confirmed-glyph vocabulary
  to 191–989 keys from just 5 warmup frames (vs Gen-1's 46 keys, the configuration under which Gate 2
  passed) — under Hamming≤4 tolerant matching, R0's collision-mode failure returns. The detector code
  is merged but **UNWIRED** — do not lift `core/text_regions_r1.py` into a wired path; the harness +
  fixture stay banked as a reusable R2 bar. **The fallback of record is brain-driven `read_region`,
  unassisted** (no detector).
- **Open:** whether to pursue an R1.1 at all — **NOT decided, David's call.** Three vNext candidates
  are listed in the verdict doc (`...verdict.md:163-171`): (1) score against a crisp-font game (Gen-1
  Pokémon) to isolate the anti-aliasing diagnosis from the small-warmup-sample variable; (2) a
  stricter Hamming tolerance (a stricter-only amendment, needs its own dated doc, counts against the
  2-attempt cap); (3) accept the fallback and do not pursue R1.1. NDS caveat unchanged: the cache
  does not transfer to DS free-form fonts (`runs/nds3d_probe/FINDINGS.md`).
- **Pinned next:** none standing — R1 is spent (KILL, one-attempt cap effectively reached per the
  verdict's own reading). Wait for David to pick among the vNext candidates above before any further
  glyph-lane build.

## Also live (not owned here)

The first long-horizon run (`runs/brain_kirby_longhaul/`, 2026-07-04, 316 turns / $42.98) is a
LENGTH experiment on the GB lane, not a new world class — **long-horizon-runs** owns it.

## Picking a lane / handling a NEW environment class

- Default: HANDOFF's `⇒ NEXT` priority order — take (1) unless David redirects (**session-start**).
- Strategic companion: `reports/2026-07-05-northstar-capability-map.md` — the six capabilities the
  North Star still requires, each with its falsifier and cheapest probe; every gate pre-reg should
  name which capability it buys evidence about. Lanes = where each WORLD stands (this skill);
  the map = what each spend should be FOR.
- A genuinely NEW environment class (new console, new input modality, new world shape) gets the
  **new-world-port** treatment: binding spike → registry → free probes → constancy audit. Then add
  a lane section HERE in the same PR (this map must not rot — a lane missing from this file will be
  re-derived expensively by the next cold session).
- Before ANY paid spend in a lane: check its "Banked" row — re-running a banked experiment without a
  fresh pre-registration violates the one-attempt rule (**gate-methodology** §4).
- The lane-priority question is David's when it involves spend; your job is to surface the frontier
  state, not to pick the spend.

## Sources

- `core/arcagi3_world.py`, `core/vizdoom_world.py`, `core/miniwob_world.py`, `core/nds_emulator.py`,
  `core/glyph_cache.py`, `core/yaw_flow.py`, `world_mcp.py` (`:585` ARC_SKILLS, `:847-854`/`:905`
  NDS_SKILLS arm isolation, `:793` `_NDS_SKILL_SAMPLE_STRIDE`) — adapters/flags/line numbers
  re-verified 2026-07-25 (previous pin of `:541`/`:629-632` had drifted).
- `reports/2026-07-03-skill-rung1-ab-verdict.md`, `reports/2026-07-03-gate3d-ceiling-test.md`,
  `reports/2026-07-03-glyph-r1-cache-driven-detection.md`,
  `reports/2026-07-04-continuous-time-stopwhen-design.md`,
  `reports/2026-07-04-mkds-continuous-time-build-plan.md`,
  `reports/2026-07-04-vizdoom-3d-floor-design.md` (A2.2 no-softening rule, `:526-528`),
  `reports/2026-07-05-p1-clutter-redesign.md` (A3 re-run conditions, `:312-325`),
  `reports/2026-07-05-northstar-capability-map.md` (ARC cut from critical path, `:266-268`; "Doom is
  burned", `:233`), `reports/2026-07-11-glyph-r1-verdict.md` (R1 KILL, PR #103),
  `reports/2026-07-13-mkds-ab-blocked.md`, `reports/2026-07-13-mkds-ab-verdict.md` (MKDS A/B FAIL),
  `reports/2026-07-05-entity-v4-design.md:129`, `reports/2026-07-13-entity-v5-candidate-shortlist.md`
  (both route away from Doom on held-out grounds) — banked verdicts/designs.
- `eval/dataset_split.py:30-36` (`HELDOUT` includes Doom); **eval-probes-and-datasets** §3 (the
  sanctioned held-out consumers, `cross_game.py`/`verify_heldout.py`).
- `runs/nds3d_probe/FINDINGS.md`, `runs/brain_miniwob/`, `runs/brain_gate3d/run3_v_FAIL/`,
  `runs/brain_gate3d/CLAUDE.md:37` (the tolerance-tightening knob), `runs/brain_arcagi3/.mcp.json`
  (ARC API key sourced WSL-side only) — on-disk, gitignored; present only in the main checkout, not
  in worktrees cut from origin.
- `E:/AI_Personas/10_pokemon_and_chess_and_office/ai-pokemon-red/HANDOFF.md` (`:213`, `:242`, `:283`,
  `:289`, `:587` code pins `s=4` vs the build plan's `s=24`, `:842-851` ARC cut + A3-PC PASS + A3
  HELD). The numbered `⇒ NEXT (N)` this map cited before 2026-07-25 are from the 2026-07-05
  snapshot and are superseded — read HANDOFF's CURRENT top-of-file `⇒ NEXT` block, not a number.
- Cross-refs: **architecture-and-seam** (constancy law), **new-world-port** (mechanics),
  **gate-methodology** (one-attempt), **cheapness-skill-compilation** (loop-half bound, corrected
  2026-07-25), **perception-primitives** (primitive extension rules), **long-horizon-runs** (the
  length axis).
