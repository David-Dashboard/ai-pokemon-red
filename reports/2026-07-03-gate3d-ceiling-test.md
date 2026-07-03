# 2026-07-03 -- GATE-3D scripted-optimum ceiling test (free, no LLM)

Purpose (`HANDOFF.md` top block, 2026-07-05 day-close bullet): arm (a-1) of GATE-3D-A1 as amended by
AMENDMENT A2 (`reports/2026-07-04-vizdoom-3d-floor-design.md` SS A2.2) requires the brain's mean final
oracle `KILLCOUNT` **K >= 5.61** (`= max(D+1.5, 1.15*D)`, `D=4.11` from the `spinner_multihot` decoy,
`eval/fixtures/gate3d_baselines.json`). The best paid brain run (`runs/brain_gate3d/run3_v_FAIL`)
achieved **K = 4.074** -- at spinner level, per HANDOFF. Before spending on another paid run, this test
asks the prior question: **can a PERFECT policy even reach 5.61 under the exact episode constraints the
gate pins?** If not, the bar is unreachable and is a design error to re-pin, not a brain failure to
re-run against.

This is a ceiling measurement of the *instrument* (episode/action-space), not an agent. `eval/score_gate3d.py`,
`eval/fixtures/gate3d_seeds.json`, `eval/fixtures/gate3d_baselines.json`, `core/`, and `scenarios/` are
all **untouched** -- the gate of record stands as-is. New files only: `eval/ceiling_gate3d.py` (the
script) and `eval/fixtures/gate3d_ceiling_results.json` (raw per-seed / per-tolerance output).

## Method

`eval/ceiling_gate3d.py` builds its own `vizdoom.DoomGame` matching `core/vizdoom_world.py`'s
`VizdoomWorld.__init__` verbatim -- same `scenarios/dtc_gate.cfg`, same button set (`TURN_LEFT,
TURN_RIGHT, ATTACK` -- the **same three actions the brain had**, no `MOVE_*`), same `RES_320X240` /
`RGB24`, same `tics=4`-per-action grain (`core.vizdoom_world.TICS_PER_STEP`), same `episode_timeout=1000`
tics (= 250 action-steps), same 26-round ammo budget (dtc ships `AMMO2=26`, no pickups) -- plus one
privileged addition explicitly licensed by the task brief: `set_labels_buffer_enabled(True)`, giving
this eval-only script server-side ground truth about enemy screen position (never available to the
brain or to `core/vizdoom_world.py`'s adapter). It does **not** import `world_mcp.py` or touch the agent
wire.

Policy per step (a privileged azimuth-seeker):
1. Read the labels buffer; drop the `DoomPlayer` label; keep whichever enemy labels remain (dtc's label
   buffer simply omits a killed monster's label on the next frame -- confirmed live with the probe
   capture in Appendix Table 1).
2. Among remaining enemies, pick the **nearest** by Euclidean world-XY distance to the player (the
   player is fixed at the arena center in `defend_the_center`, confirmed `(0,0)` throughout every probe
   run -- Appendix Table 1).
3. Compute that enemy's azimuth as a **screen-space pixel offset**: `bbox_center_x - 160` (screen width
   320, so center = 160), read directly from the labels buffer rather than estimated.
4. If `|offset| <= tolerance` and ammo remains: fire. Otherwise turn toward the target (`TURN_RIGHT` if
   the target's offset is positive / right-of-center, else `TURN_LEFT` -- sign convention verified live,
   trace in Appendix Table 1: 77 tics of continuous `TURN_LEFT`, zero wrong-sign steps).
5. If no enemy label is visible: turn right one step to scan (costs no ammo) -- the same "nothing to aim
   at, keep turning" fallback any perceiver needs.

All 30 pinned seeds (`eval/fixtures/gate3d_seeds.json`, seeds 1000-1029), one attempt each, identical
250-step / 1000-tic timeout to the gate. Per-episode kills = final oracle `KILLCOUNT`; shots =
`ammo2_first - ammo2_last`, same formula `eval/score_gate3d.py`'s `_brain_kps` and
`tools/gate3d_baselines.py`'s decoy runner use (any ammo2 increase, impossible in dtc, would exclude the
episode from both sums -- zero exclusions occurred at any tolerance tested).

Run inside the existing `vizdoom-world` Docker image (`docker images` confirmed it present, built from
`Dockerfile.vizdoom`, `vizdoom==1.3.0`); repo mounted read/write at `/work`, ran as:

```
docker run --rm -v "$PWD:/work" -w /work --entrypoint python vizdoom-world \
    eval/ceiling_gate3d.py --seeds-file eval/fixtures/gate3d_seeds.json \
    --tolerances 3,5,7,8,9,10,11,13,25 --out eval/fixtures/gate3d_ceiling_results.json
```

No `.mcp.json` / launcher directory existed under `runs/brain_gate3d/` in this worktree (`runs/` is
gitignored and not present locally) -- the image name and run recipe were instead confirmed directly
from `Dockerfile.vizdoom`'s header comment and cross-checked against `docker images` (`vizdoom-world:latest`
present) and `tools/run_gate3d_baselines.sh` (the existing baseline driver, same image, same mount
pattern). Nothing was blocked; this is noted only because the brief named that file as one path to the
image name and it wasn't present to read.

## Results

Nine tolerances swept (25px -- the number the paid run's brief used as its "centered enough" guidance --
always included, plus a fine sweep from 3px up, informed by a small 3-seed pilot that showed a hitscan
cliff somewhere between 13px and 15px). The (a-2) column checks each tolerance's KPS against the gate's
other discriminator, `1.5 x KPS_spinner = 0.2375` (`eval/fixtures/gate3d_baselines.json`,
`_derived_at_this_measurement.arm_a2_bar`) -- the gate of record requires BOTH arms:

| tolerance (px) | mean K | clears (a-1) K>=5.61? | mean KPS | clears (a-2) KPS>=0.2375? | min K | max K |
|---:|---:|:---:|---:|:---:|---:|---:|
| 3  | 5.267 | no  | 0.6960 | yes | 1  | 14 |
| 5  | 6.233 | yes | 0.6233 | yes | 1  | 14 |
| 7  | 6.300 | yes | 0.5067 | yes | 1  | 13 |
| **8**  | **7.333** | **yes** | 0.4857 | yes | 2  | 15 |
| 9  | 7.000 | yes | 0.3896 | yes | 3  | 16 |
| 10 | 6.967 | yes | 0.3814 | yes | 1  | 16 |
| 11 | 5.800 | yes | 0.3204 | yes | 1  | 14 |
| 13 | 6.267 | yes | 0.3023 | yes | 1  | 13 |
| **25** | **3.433** | **no** | 0.1656 | **no** | 1  | 11 |

- **Best-tuned tolerance (8px):** mean K = **7.333**, mean KPS = 0.4857, min/max 2/15 -- clears the (a-1)
  bar by +1.72 kills (31%) and the (a-2) KPS bar by 2x.
- **At this script's 25px tolerance:** mean K = **3.433**, mean KPS = 0.1656 -- fails BOTH of the gate's
  discriminators, (a-1) and (a-2). (See Limitations: this 25px is measured on a different instrument
  than the brief's 25px and the two are not directly comparable.)
- Every tolerance from 5px to 13px clears both arms; 3px clears (a-2) but narrowly misses (a-1)
  (over-tight aim spends steps re-aiming that could have been shots).
- Zero KPS-exclusion episodes at any tolerance (dtc's monotonic no-pickup ammo held throughout, as
  expected).

Full per-seed killcounts, shots, and per-tolerance detail: `eval/fixtures/gate3d_ceiling_results.json`.
(Field note: `bullets_fired` is actual rounds consumed, ammo-delta-derived and bounded by the 26-round
budget; `attack_decisions` counts steps that *chose* ATTACK and can legitimately exceed 26 -- at the
pinned tics=4 grain the pistol's ~14-tic refire cycle means most 4-tic ATTACK windows consume no
bullet. KPS everywhere uses the ammo-delta shot count, identical to the scorer's formula.)

## Limitations -- what this ceiling does and does not measure

**(a) Same units, different instrument.** The paid run's brief (`runs/brain_gate3d/CLAUDE.md`) defined
"centered enough" as ~25px on a **P2 `StationaryMovers` centroid** -- a frame-diff blob estimate that is
noisy, is only available when the previous step was ego-stationary, and goes `null` for the entire
duration of any turn. This script's 25px is applied to the **ground-truth labels-buffer bbox center** --
noiseless and available every step. The two "25px" numbers share units but not an instrument; comparing
them directly is qualitative at best, and nothing in this report should be read as "the brain at 25px
equals the ceiling at 25px."

**(b) The ceiling is optimistic by construction.** This policy gets a fresh, exact target position every
single 4-tic step, with zero reaction latency and no blind window. The brain's tool contract forces an
observe -> turn (blind, movers `null`) -> re-stabilize -> observe loop, with decisions gated on discrete
tool calls. The ceiling removes an entire source of error (perception latency/blindness) that the
brain's contract imposes, independent of any tolerance question. The 7.333 and 3.433 numbers are
therefore an upper bound on what tolerance-tuning alone could achieve -- they are not evidence that
closing the tolerance gap is sufficient, only that it is necessary-if-anything-is.

**(c) The paid-run gap is not decomposed by this test.** The brain's shortfall (4.074 vs 5.61) may be
firing-tolerance guidance, P2 centroid noise, blind-window reaction latency, or any mix of these. This
ceiling test cannot separate those contributions; it only establishes that the bar itself is not the
problem.

## Verdict

**Is K >= 5.61 reachable by a perfect azimuth-seeker? YES** -- at the best-tuned tolerance (8px), the
ceiling is K = 7.333, comfortably above the 5.61 bar (and its KPS = 0.4857 clears arm (a-2)'s 0.2375 bar
as well). The bar is **not** physically unreachable under the pinned episode constraints (30 seeds, 250
steps, 26 rounds, `TURN_LEFT/TURN_RIGHT/ATTACK` only). **No re-pin is needed; the bar stands.**

Within this script's own (ground-truth) instrument, tolerance choice alone swings mean K from 3.433
(25px, fails both arms) to 7.333 (8px, clears both) -- so "fire only when tightly centered" is a real
and large lever *for a policy with perfect perception*. Whether the paid brain's shortfall was mostly
its loose firing tolerance is **one hypothesis, not this test's conclusion** -- per Limitations (a)-(c),
the brain's 25px lived on a noisier, laggier instrument, and P2 noise or blind-window latency could
account for much of the same gap.

## Recommendation

- **Bar re-pin: NO.** The ceiling clears 5.61 with a 31% margin; the bar is reachable and stands as
  pinned (stricter-only discipline never permitted loosening anyway -- this test confirms there is no
  design-error case for a documented re-pin either).
- **Paid A3 re-run as-is: not yet.** Before paying, the cheapest lever to try is **brief-side**: tighten
  the firing-tolerance guidance (fire only when the azimuth reading is very close to zero, rather than
  "roughly centered" / ~25px). This is the cheapest thing to try *but it is unproven* -- this test shows
  tight tolerance is necessary for a perfect perceiver to clear the bar, not that it is sufficient for
  the brain, whose P2 centroid noise and turn-blind windows are error sources the ceiling does not model
  (Limitations b/c). If a brief-tightened run is attempted and still falls short, the remaining suspects
  are P2 centroid precision and reaction latency -- primitive-level findings for the design doc, not
  bar problems.

## Appendix -- Table 1: labels-buffer probe (field schema + sign-convention verification)

Free probe run inside the `vizdoom-world` image before the policy was written (same DoomGame config as
the ceiling script; seed 1000, `dtc_gate` physics). Two things verified:

**Label field schema** (fields available per label in `vizdoom==1.3.0`):
`height, object_angle, object_category, object_id, object_name, object_pitch, object_position_x,
object_position_y, object_position_z, object_roll, object_velocity_x, object_velocity_y,
object_velocity_z, value, width, x, y`. Enemy labels observed in dtc: `MarineChainsawVzd`, `Demon`;
the player appears as `DoomPlayer` (excluded by name). A killed monster's label is absent from the
next frame's list. Game variables order confirmed `HEALTH, AMMO2, KILLCOUNT` = `[100, 26, 0]` at
episode start.

**Sign-convention trace** -- continuous `TURN_LEFT` at tics=4 for 20 steps (tics 1-77), player fixed at
`(0,0)` throughout; for the labeled enemy: `px_offset` = bbox-center-x - 160, `rel_angle` = analytic
bearing minus player `ANGLE` (positive = target is to the LEFT of view center). `TURN_LEFT` increases
`ANGLE`; a tracked target's `px_offset` grows rightward/positive as the view rotates left past it --
sign agreement between `px_offset` and `-rel_angle` held on every row (zero wrong-sign steps):

| tic | player ANGLE (deg) | target | bbox_cx | px_offset | rel_angle (deg) |
|---:|---:|---|---:|---:|---:|
| 1  | 0.00   | MarineChainsawVzd | 159.0 | -1.0   | 0.00   |
| 9  | 3.52   | MarineChainsawVzd | 168.5 | +8.5   | -3.52  |
| 13 | 17.58  | MarineChainsawVzd | 210.5 | +50.5  | -17.58 |
| 17 | 31.64  | MarineChainsawVzd | 258.5 | +98.5  | -31.64 |
| 21 | 45.70  | MarineChainsawVzd | 318.5 | +158.5 | -45.70 |
| 25 | 59.77  | Demon             | 115.5 | -44.5  | +15.39 |
| 29 | 73.83  | Demon             | 154.0 | -6.0   | +2.22  |
| 33 | 87.89  | Demon             | 190.5 | +30.5  | -10.91 |
| 41 | 116.02 | Demon             | 280.0 | +120.0 | -37.00 |
| 49 | 144.14 | MarineChainsawVzd | 156.0 | -4.0   | +1.07  |
| 57 | 172.27 | MarineChainsawVzd | 240.0 | +80.0  | -26.80 |
| 65 | 200.39 | Demon             | 130.5 | -29.5  | +10.16 |
| 69 | 214.45 | Demon             | 172.5 | +12.5  | -4.55  |
| 77 | 242.58 | Demon             | 268.5 | +108.5 | -34.16 |

Consequence for the policy: a target with **positive** `px_offset` (right of screen center) needs
`TURN_RIGHT` to bring `bbox_cx` toward 160, and vice versa -- exactly the branch
`eval/ceiling_gate3d.py` implements.

## Files

- `eval/ceiling_gate3d.py` -- the ceiling script (new).
- `eval/fixtures/gate3d_ceiling_results.json` -- raw per-seed / per-tolerance results (new).
- Untouched, as required: `eval/score_gate3d.py`, `eval/fixtures/gate3d_seeds.json`,
  `eval/fixtures/gate3d_baselines.json`, `core/`, `scenarios/`.
