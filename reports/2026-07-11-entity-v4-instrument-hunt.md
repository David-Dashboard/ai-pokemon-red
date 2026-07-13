# Entity-gate v4 — $0 instrument hunt for a better gate room (2026-07-11)

Follow-up to `reports/2026-07-11-entity-v4-visibility-probe.md`. Read-only-except-for-this-file
survey: no branch switch, no commit, no existing file modified. $0 (local PyBoy). Script:
`C:/Users/Succe/AppData/Local/Temp/claude/.../scratchpad/v4_hunt_survey.py` (+ `v4_hunt_probe_start.py`,
`v4_hunt_pillar.py`), all throwaway. Frames: `.../scratchpad/v4_hunt_out/**` (gitignored temp, not
committed). Same load pattern as `reports/2026-07-05-entity-v4-d-probe.md`: `World(game="kirby_dreamland",
KIRBY_SKILLS=1)`, hp oracle `0xD086`, ROM `roms/Kirby's Dream Land (USA, Europe).gb`.

## Rooms surveyed

1. **`runs/kirby_probe/kirby_stage1.state`, `kirby_scout.state`, `kirby_scout2.state`, `kirby_walked.state`**
   — DEAD, not real gameplay. 30-40 presses of `right` (+6 of `start`, tested separately) produce **zero**
   screen change and **zero** hp change on all four; screenshots before/after are pixel-identical (a static
   level-intro/title tableau, "Sc:000000", Kirby motionless). Confirmed via direct screenshot diff, not MAD
   alone. Not usable as a gate-room seed.
2. **`runs/kirby_probe/kirby_final.state`** (hp=5, sc=800) and **`kirby_to_death.state`** (hp=3, sc=2000)
   — real gameplay, further along the SAME room chain as `kirby_entity2.state` (see next section), sitting
   just past a vertical-pillar wall. Walking `right` 30-40 more presses from `kirby_final.state` produces
   **zero** further hp/position change — Kirby is `move_blocked` here (confirmed visually: identical frame
   at press 1 and press 40).
3. **A door+enemy area reached from `kirby_to_death.state`** via `up`x2 then `right`+`a` hops (jumping over
   the pillar): reveals an "In" door with a hovering enemy near it, then a sub-room (`Sc` jumps 2000->2400
   on entry). Promising-looking (door = repeatable spawn point, item 1's wishlist) but **NOT characterized**
   — reached only at hp=2-3 (already took hits getting there), sub-room enemy behavior/retreat geometry
   unexplored, no benign candidate found. Flagged as an open lead, not adopted this session (budget).
4. **`runs/kirby_entity2.state` itself, continuous `right` (no retreat)**: re-measured for comparison.

## New finding that changes the papercheck's confidence, not just a new room

Pressing `right` continuously (hold_frames=30, the pinned `EXPECTED_WALK_FRAMES_PER_PRESS=46` recipe used
by `run_skill`/`check_seam_physics`) from `kirby_entity2.state`: the cluster-1 threat is visible at press 0
(screenshot `000_baseline.png`, enemy at frame's far-right edge) but **contact registers by press 2** (hp
6->5, `sc` 0->400; `001_right.png`/`002_right.png` show the enemy closing to adjacency then overlapping) —
**not press 8** as `reports/2026-07-11-entity-v4-visibility-probe.md` measured. Both probes used the same
state and the same nominal 46-frames/press cadence; the discrepancy is unresolved (possibly a different,
unstated hold_frames or an idle-wait-before-walking schedule in the earlier probe let the enemy's own AI
close distance differently). This is a **negative update**, not a positive one: it means cluster 1's "8
presses of honest lead" (which the coverage papercheck's case D/E/I leaned on to certify NEAR-at-step-1 as
"genuinely visible, not fabricated") may only hold under a specific press cadence, and under the canonical
run_skill cadence the real lead is closer to ~1-2 presses — tightening, not loosening, the papercheck's
already-thin margin. Continuing right past this contact, Kirby then sits `move_blocked` at the pillar wall
for 40+ more presses (matches `kirby_final.state` exactly, same score/hp/frame).

## Verdict vs the 5 wish-list items (all candidates)

| Room | (1) long-range visible lead | (2) on-screen retreat zone | (3) wall for move_blocked | (4) benign entity | (5) enemy supply for 5 drops/60 turns |
|---|---|---|---|---|---|
| `kirby_entity2.state` (existing) | ~1-2 presses (this probe) vs ~8 (prior probe) — unresolved, but ≤ existing instrument's own best case | cluster-1 only, per prior probe | YES, verified (d-probe: 3/3/6/7 presses, all `WALL_CONFIRM`-clean) | not found | YES — real v3.1 run banked exactly 5 drops here |
| stage1/scout/scout2/walked | N/A — frozen, no gameplay | N/A | N/A | N/A | N/A |
| final/to_death (past the wall) | not measured (Kirby blocked at final; to_death only reachable pre-damaged) | unclear | wall exists but blocks progress entirely (dead end without jumping) | not found | reaches hp=0 (death) within ~30 presses of jump+right hopping — WORSE supply margin than entity2 |
| door/sub-room past the pillar | visually promising, NOT measured | NOT measured | NOT measured | NOT found | NOT measured |

## Verdict: NONE BETTER — `kirby_entity2.state` stands

No candidate measured this session clears `kirby_entity2.state` on the wish list; the two rooms reached by
walking/jumping further (`kirby_final`/`kirby_to_death` chain) are worse (a hard wall, then a death spiral,
no measured retreat zone). The door+sub-room lead is the one genuinely new, potentially-good candidate
surfaced this session but is unverified — recommend a dedicated ~30-40min follow-up probe from a **fresh
hp=6 save right at the door** (would need a new savestate captured mid-approach, before the pillar-area
hits) before trusting it. No new savestate saved this session (no clear winner to anchor one to).

## Negative claims / paths checked

- `Glob **/kirby*.state`: 13 files total — `runs/kirby_entity.state`, `runs/kirby_entity2.state`,
  `runs/kirby_probe/{kirby_stage1,kirby_walked,kirby_scout,kirby_scout2,kirby_final,kirby_contact,
  kirby_atenemy,kirby_precise,kirby_more_hits,kirby_to_death,kirby_third_hit}.state`. No `kirby_entity3`
  or later exists (matches d-probe's own negative claim).
- `kirby_contact.state`, `kirby_atenemy.state`, `kirby_precise.state`, `kirby_more_hits.state`,
  `kirby_third_hit.state` were **not individually surveyed** (time-boxed at ~70min of the ~90min budget) —
  filename/timestamp order and sc/hp trend (00:53-00:58, hp descending 5->1 range) place them as
  intermediate checkpoints in the same single progression chain already characterized via `final`/
  `to_death`, not independently verified as different rooms.
- No `runs/**/*.state` outside `kirby_probe/` and the two top-level kirby states exist for this game
  (checked via the same glob).
