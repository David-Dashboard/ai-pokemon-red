# Entity-gate v4 — the $0 (d) probe: move_blocked vs region_changed on the real gate room (2026-07-05)

Pre-registration: [reports/2026-07-05-entity-v4-design.md](2026-07-05-entity-v4-design.md) §Barrier 3.
Cost: $0 (local PyBoy only, no claude/API calls, no Docker). Scripts: throwaway, not committed —
`C:/Users/Succe/AppData/Local/Temp/claude/.../scratchpad/entity_v4_d_probe.py` (+ `_repro.py`).
Probe output (gitignored, not committed): `runs/kirby_v4_d_probe/` (`skills.jsonl`, `oracle.jsonl`,
`_probe_result.json`), `runs/kirby_v4_d_probe_repro/`.

## Setup
- State: `runs/kirby_entity2.state` — exists (confirmed by Glob; sibling `runs/kirby_entity.state` and
  10 states under `runs/kirby_probe/` also exist but were NOT used — the design doc names
  `kirby_entity2.state` as the actual gate room).
- ROM: `roms/Kirby's Dream Land (USA, Europe).gb` (pinned by `world_mcp.py`'s `kirby_dreamland` registry
  entry, line 177).
- Loader: `world_mcp.World(args)` with `game="kirby_dreamland"`, `KIRBY_SKILLS=1` — same pattern as
  `eval/score_kirby_skill_precheck.py::check_seam_physics`.
- Oracle: `watch.hp` at `0xD086` (plain int, per `world_mcp.py:170-178`) — **read 6 at load, matches the
  design's `assert hp==6`.**
- Frame shape: `(144, 160, 4)` (H, W, C) — standard GB resolution.

## Measurements

### (b) move_blocked — 4 independent trials, each reset to the post-load baseline savestate
| dir | executed_step_count | iterations | stop_reason |
|---|---|---|---|
| right | 7 | 7 | `move_blocked` fired after 7 press(es) |
| left | 6 | 6 | `move_blocked` fired after 6 press(es) |
| up | 3 | 3 | `move_blocked` fired after 3 press(es) |
| down | 3 | 3 | `move_blocked` fired after 3 press(es) |

None fired before press 3 (the `WALL_CONFIRM=3` hard floor, `core/grid_perceiver.py:30`) — **no
erratic 1-2-press firing observed on this savestate**, contra the design doc's caution. Ran the frozen
`eval/score_entity_gate_v3.is_qualifying_conditional_call` directly against these 4 records (not
inferred): **all 4 return `True`; `skill_guard` on just these 4 calls reports
`guard_pass: True, n_qualifying_conditional_calls: 4`.** Reproducibility: re-ran `down` in a fresh
process from the same baseline — identical result (3 presses, 3 iterations).

### (a) region_changed on a box ahead of Kirby (stationary target, walking `right` toward its wall)
Tested 6 candidate box placements (`center_wide`, `right_third`, `left_third`, `lower_band`,
`upper_band`, `full_minus_hud`) across the 7-press approach to the `right` wall. **Every candidate's
MAD crosses the pinned ≥2.0 dead-zone already on press 1** (MAD 23.9–37.9, roughly 10-20x the
threshold) — region_changed is degenerate here too, but for a DIFFERENT reason than v3.1: it isn't a
converging enemy, it's Kirby's own walk animation / camera scroll changing the whole screen on every
press. Several boxes stay elevated for 4+ presses before settling (`right_third` never drops below 2.0
across all 7 presses tested). **No candidate box gives an honest ≥2-iteration region_changed approach
in this room.** This generalizes the v3.1 finding: region_changed is unsound against ANY approach here,
not just enemy-chase.

### Perceiver noise (idle, no button presses — 6x `wait(5 frames)` from baseline, ~30 emulator frames)
5 of 6 candidate boxes: **0/6 false fires** (MAD 0.0, or 0.6–1.0 for `full_minus_hud`, below the 2.0
dead-zone). One box, `right_third` (100,40,155,104): **6/6 fired** (MAD 3.7–5.9) from non-avatar causes
alone — flagging that specific placement as unsafe regardless of predicate choice.

## Verdict: GO for (d), via move_blocked as PRIMARY — reverses the design doc's stated preference order

The design's GO bar ("some predicate reaches `iterations>=2` AND `executed_step_count>=3` AND
`guard_pass=True` in `kirby_entity2.state`") is met, verified against the frozen scorer function, in
the actual gate-room state with `hp==6` asserted. **move_blocked is the correct PRIMARY predicate; drop
region_changed entirely for this room** — it fires press-1 on every box tested, worse than the
converging-enemy case, with no rescue via box placement. The design doc's tentative order ("(a)
region_changed PRIMARY, (b) move_blocked fallback... the probe settles the order") is settled the
OTHER way.

**Not tested here (scope of this probe):** compatibility of a move_blocked-primary approach with the
drop-banking path (banking ≥5 contact drops while also walling 3+ presses in some direction) — that
needs a brief/design pass, not a further $0 probe. Flag as the next open item before spending.

**Negative claims / paths checked:** no `**/kirby*.state` other than the 12 listed above exist in the
repo (Glob `**/kirby*.state`); no `kirby_entity3` or later state exists.
