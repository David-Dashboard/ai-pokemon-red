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
"pinned next" lines against HANDOFF's newest `⇒ NEXT` list — this map was frozen 2026-07-04.

## ARC-AGI-3 (abstract grid; the skill-compilation proving ground)

- **Adapter:** `core/arcagi3_world.py` — thin REST client for three.arcprize.org; the returned grid
  IS the symbolic state (no perceiver); `levels_completed` is oracle-only, never on the wire
  (`:13-16`); 250ms client throttle (`:49`); actions `ACTION1..7`, `ACTION6` takes coordinates.
  Skill tools gated behind `ARC_SKILLS=1` (`world_mcp.py:541`).
- **Banked:** skill-compilation rung-1 A/B **PASS 2.94x** vs pinned 1.3x bar
  (`reports/2026-07-03-skill-rung1-ab-verdict.md`): Arm A 1/9 levels, 50 decisions, $7.78; Arm B 2/9
  levels, 34 decisions, $8.83 — the wa30 level-2 wall fell. **Honest bound:** only the BATCHING half
  validated; the conditional-loop half has never fired in a paid run (**cheapness-skill-compilation**
  §5 carries this bound — any port's gate must require the loop half explicitly).
- **Open:** breadth — one game (wa30), one attempt per arm.
- **Pinned next:** ARC breadth / sweep stage-2 (HANDOFF `⇒ NEXT` (5)).

## VizDoom / 3D (the embodiment rung)

- **Adapter:** `core/vizdoom_world.py` (TURN_LEFT/TURN_RIGHT/ATTACK, 4-tic steps). Perception
  primitives: `core/yaw_flow.py` (P1 ego-rotation, R0-validated: sign-agreement 0.964, None-rate
  0.201, `:1-8`) and `core/stationary_movers.py` (P2, only valid on ego-stationary pairs — see
  **perception-primitives**). Free probes: `eval/vizdoom_flow_ceiling.py`, `eval/ceiling_gate3d.py`.
- **Banked:** paid GATE-3D run **FAIL, K = 4.074 vs bar 5.61** (`runs/brain_gate3d/run3_v_FAIL` —
  also the most expensive run ever, $82.86; see **long-horizon-runs**). The free ceiling test then
  answered the prior question: a perfect azimuth-seeker reaches **K = 7.333** at 8px tolerance —
  "**No re-pin is needed; the bar stands**" (`reports/2026-07-03-gate3d-ceiling-test.md:128,:130`);
  at 25px tolerance even the ceiling fails (K = 3.433), so tolerance is the lever.
- **Open:** closing the 4.074 → 5.61 gap is brief/tolerance work, not perception work.
- **Pinned next:** brief-side tolerance tightening BEFORE any paid re-run (ceiling report
  "Implications"); then the doom scan-and-center macro port (HANDOFF `⇒ NEXT` (4)) — its gate must
  require the conditional-loop half (the bound above).

## NDS / continuous time (the hardest perception frontier)

- **Adapter:** `core/nds_emulator.py` + `core/nds_perceiver.py` (ScreenRoleDiscovery routes the
  grid perceiver to the discovered gameplay screen; touch tools via `core/nds_perception_plugin.py`).
- **Banked:** the 3D probe (`runs/nds3d_probe/FINDINGS.md`, on-disk) — MKDS race reached
  vision-guided; savestate `mkds_race_start.state` banked; **idle change 12.22%/frame mean vs 33.23%
  accelerating** (`:329-330`) — the world changes without input, breaking the discrete-step
  assumption; three perception breaks documented (free-form non-tile font/HUD, rotating minimap
  kills tile-grid, continuous chase-cam roll kills discrete-facing).
- **Moved since the probe (merged to main 2026-07-04):** the `stop_when` bridge design
  (`reports/2026-07-04-continuous-time-stopwhen-design.md` — design only, "no code, no paid run",
  resolves HANDOFF NEXT #2's design half) and the MKDS build spec + A/B pre-registration
  (`reports/2026-07-04-mkds-continuous-time-build-plan.md` — the §4 idle-measurement prerequisite is
  DONE, numbers pinned; NDS skill tools gated behind `NDS_SKILLS=1` with arm-isolation, see
  `world_mcp.py:629-632` and `tests/test_nds_skill_port.py`). Read both before touching this lane —
  a parallel session owns the build.
- **Open:** the paid MKDS A/B itself; the three perception breaks (each needs a primitive, not a
  hack — **perception-primitives** extension rules).
- **Pinned next:** execute the MKDS build plan / its pre-registered A/B (HANDOFF `⇒ NEXT` (2)).

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
  detection.md:5`; the module stays as a documented-honest failure, **perception-primitives**). The
  R1 redesign inverts to cache-driven re-finding; its Gate-2 half already PASSED (cache 96.9%
  frac_free); `core/glyph_cache.py` is built, within-run only, blank each run.
- **Pinned gate for the R1 build:** recall ≥ 0.85, precision ≥ 0.90, 0 phantoms, same-game
  warm/measure split (`...glyph-r1...md:307`).
- **Open:** the R1 build itself — design merged, build NOT started. NDS caveat: the cache does not
  transfer to DS free-form fonts (`runs/nds3d_probe/FINDINGS.md`).
- **Pinned next:** glyph R1 build against its pinned gate (HANDOFF `⇒ NEXT` (3)).

## Also live (not owned here)

The first long-horizon run (`runs/brain_kirby_longhaul/`, 2026-07-04, 316 turns / $42.98) is a
LENGTH experiment on the GB lane, not a new world class — **long-horizon-runs** owns it.

## Picking a lane / handling a NEW environment class

- Default: HANDOFF's `⇒ NEXT` priority order — take (1) unless David redirects (**session-start**).
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
  `core/glyph_cache.py`, `world_mcp.py` (`:541` ARC_SKILLS, `:629-632` NDS_SKILLS arm isolation) —
  adapters/flags verified 2026-07-04.
- `reports/2026-07-03-skill-rung1-ab-verdict.md`, `reports/2026-07-03-gate3d-ceiling-test.md`,
  `reports/2026-07-03-glyph-r1-cache-driven-detection.md`,
  `reports/2026-07-04-continuous-time-stopwhen-design.md`,
  `reports/2026-07-04-mkds-continuous-time-build-plan.md` — banked verdicts/designs.
- `runs/nds3d_probe/FINDINGS.md`, `runs/brain_miniwob/`, `runs/brain_gate3d/run3_v_FAIL/` — on-disk
  run evidence (`runs/` is gitignored).
- `E:/AI_Personas/10_pokemon_and_chess_and_office/ai-pokemon-red/HANDOFF.md` (`:213`, `:242`, `:283`,
  `:289`, newest `⇒ NEXT` list).
- Cross-refs: **architecture-and-seam** (constancy law), **new-world-port** (mechanics),
  **gate-methodology** (one-attempt), **cheapness-skill-compilation** (loop-half bound),
  **perception-primitives** (primitive extension rules), **long-horizon-runs** (the length axis).
