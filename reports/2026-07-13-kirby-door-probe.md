# Kirby door/sub-room probe - v5 source-status check (2026-07-13)

Status: **$0 local probe only**. No paid run, scorer edit, tool-schema edit, or
pre-registration. Fresh ignored output:
`runs/kirby_door_probe_2026-07-13/`.

## Question

Can the door+enemy lead from
`reports/2026-07-11-entity-v4-instrument-hunt.md` plausibly carry an entity-gate
v5 attempt?

## Method

- Loader: local PyBoy via `world_mcp.World(game="kirby_dreamland")`.
- Cadence: `hold_frames=30`, observed `46` emulator frames per press in the
  traces.
- Oracle used offline only: `hp` at `0xD086`.
- Visual receipts: screenshot mosaics under the run directory.
- Mechanism receipt: official `define_skill`/`run_skill` with
  `stop_when="move_blocked"`; summary at
  `runs/kirby_door_probe_2026-07-13/move_blocked/summary.json`.

## Findings

1. **The door is real, but it starts damaged.** From `kirby_to_death.state`
   (hp=3), `up, up, right...` reaches an "In" door and then the door/sub-room
   chain. Visual screenshots show score moving from 2000 to 2400/2800/3200 in
   the route, but HP falls to 1 before the segment has useful slack.
2. **No hp=6 near-door seed was found.** Checked the exact state chain:
   `kirby_final.state`, `kirby_contact.state` (hp=5);
   `kirby_atenemy.state`, `kirby_precise.state` (hp=4);
   `kirby_more_hits.state`, `kirby_third_hit.state`,
   `kirby_to_death.state` (hp=3). For each, tested `right12`,
   right/a alternating x12, `up2_right12`, and `up2` plus right/a alternating
   x12. The hp5 starts do not cleanly reach the door; the door-adjacent starts
   are already hp4 or worse.
3. **Visibility lead exists but is thin.** On the hp4 door seed, `right20`
   shows a threat visible by about press 2 and the first HP drop at press 5
   (roughly 3 scoreable presses of lead). That is better than the old room's
   worst clusters, but below the v5 design's desired 4-of-5 robust pre-drop
   opportunities.
4. **Consequence supply fails.** The best no-rescue door-seed route seen
   (`ra30`) gives 3 non-death HP drops, then hp reaches 0 at step 35. Other
   door-entry variants give 0-2 drops. This does not meet v5's "5+ drops
   without a death spiral" precheck.
5. **Retreat geometry is poor.** Retreat/re-approach variants from the hp4 door
   seed still lose HP during retreat or re-entry (`right5_left10_right20` ends
   hp=1; `left10_right25` ends hp=2). There is no clean on-screen reset lane.
6. **`move_blocked` is available.** Official `run_skill` checks from two stable
   door-area hp3 wall states fired `move_blocked` after 4 canonical right
   presses with HP unchanged. A third hp4 doorway state fired after 5 presses
   but crossed a transition/reset-like HP change, so treat the two hp3 checks as
   the cleaner mechanism receipt.
7. **No plausible benign comparator was found.** The door/plant/background props
   are visible near the threat, but they are static scenery, not a convincing
   mistaken-threat comparator under the v5 benign/rejection arm.

## Verdict

**Do not use this Kirby door/sub-room lead for v5 as-is.** It improves the
visual story over the old room, and it has a usable `move_blocked` wall, but it
fails the source-status checks that matter: no full-health near-door seed, no
5-drop no-death supply, weak retreat geometry, and no plausible benign
comparator.

If Kirby stays in scope, the next useful free action is to manually capture a
fresh hp=6 state immediately before the door, then rerun only the consequence
supply and benign-comparator checks. Otherwise pick a cleaner room/world for v5.
