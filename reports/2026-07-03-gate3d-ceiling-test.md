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
   buffer simply omits a killed monster's label on the next frame -- confirmed live with a probe capture
   before writing the policy).
2. Among remaining enemies, pick the **nearest** by Euclidean world-XY distance to the player (the
   player is fixed at the arena center in `defend_the_center`, confirmed `(0,0)` throughout every probe
   run).
3. Compute that enemy's azimuth as a **screen-space pixel offset**: `bbox_center_x - 160` (screen width
   320, so center = 160) -- the same "px-equivalent" quantity the brief's tolerance describes, read
   directly from the labels buffer rather than estimated.
4. If `|offset| <= tolerance` and ammo remains: fire. Otherwise turn toward the target (`TURN_RIGHT` if
   the target's offset is positive / right-of-center, else `TURN_LEFT` -- sign verified live against 70+
   tics of continuous turning, zero wrong-sign steps).
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

Nine tolerances swept (25px -- the brief's exact value -- always included, plus a fine sweep from 3px
up, informed by a small 3-seed pilot that showed a hitscan cliff somewhere between 13px and 15px):

| tolerance (px) | mean K | mean KPS | min K | max K |
|---:|---:|---:|---:|---:|
| 3  | 5.267 | 0.6960 | 1  | 14 |
| 5  | 6.233 | 0.6233 | 1  | 14 |
| 7  | 6.300 | 0.5067 | 1  | 13 |
| **8**  | **7.333** | 0.4857 | 2  | 15 |
| 9  | 7.000 | 0.3896 | 3  | 16 |
| 10 | 6.967 | 0.3814 | 1  | 16 |
| 11 | 5.800 | 0.3204 | 1  | 14 |
| 13 | 6.267 | 0.3023 | 1  | 13 |
| **25** | **3.433** | 0.1656 | 1  | 11 |

- **Brief's exact 25px tolerance:** mean K = **3.433**, mean KPS = 0.1656 -- **does NOT clear** the 5.61
  bar (and is even below the best paid brain run's 4.074).
- **Best-tuned tolerance (8px):** mean K = **7.333**, mean KPS = 0.4857, min/max 2/15 -- clears the bar
  by +1.72 kills (31%).
- Every tolerance from 3px to 13px clears 5.61; only the wide 25px tolerance fails to. The tighter
  tolerances also show a KPS/K trade-off in the expected direction (tighter aim -> higher KPS, fewer
  wasted rounds at 3px, but fewer total shots taken per episode before ammo runs out at the widest
  useful window; 8px balances the two best in this sweep).
- Zero KPS-exclusion episodes at any tolerance (dtc's monotonic no-pickup ammo held throughout, as
  expected).

Full per-seed killcounts, shots, and per-tolerance detail: `eval/fixtures/gate3d_ceiling_results.json`.

## Verdict

**Is K >= 5.61 reachable by a perfect azimuth-seeker? YES** -- at the best-tuned tolerance (8px), the
ceiling is K = 7.333, comfortably above the 5.61 bar. The bar is **not** physically unreachable under the
pinned episode constraints (30 seeds, 250 steps, 26 rounds, `TURN_LEFT/TURN_RIGHT/ATTACK` only).

**But the brief's own reference tolerance (25px) does NOT clear it (3.433 < 5.61)** -- this separates the
two possible failure stories cleanly:
- "Bar unreachable" -- **ruled out**. A perfect policy with a well-tuned aiming tolerance clears 5.61 by
  a wide margin (7.333, +31% over bar).
- "Brain's aiming tolerance too loose" -- **plausible and consistent with the data**. The gap between
  25px (3.433) and 8px (7.333) is over 2x in mean kills, and the brain's own primitive (`YawBandFlow`,
  P1) reports pixel/degree readings whose *effective* aiming precision was never tuned against this
  scenario's actual hit geometry -- it was tuned for sign-agreement (ARM b), not for how close to
  dead-center a shot needs to be to land. A brain firing on a 25px-or-looser "close enough" heuristic is
  ceiling-capped well under the bar for reasons that have nothing to do with its perception being wrong
  (ARM (b) can PASS at any of these tolerances -- turning toward the target and getting sign right is a
  separate question from firing only once truly centered).

## Recommendation

**Re-pin the bar? No -- the ceiling comfortably clears 5.61, so the bar itself is not the problem.**

**Paid A3 re-run as-is? Not recommended yet.** The brain achieved K=4.074 with (by construction) some
aiming tolerance; this ceiling test shows that tolerance choice alone swings mean kills from 3.4 to 7.3
on an otherwise-identical policy shape (turn-to-azimuth-then-fire). Spending another paid run without
first tightening how the brain decides "centered enough to fire" risks repeating the same shortfall for
a reason this test just isolated for free. Recommended next step, still free: check whether the gap is
fixable by brief/prompt guidance alone (tell the brain to fire only when its own azimuth reading is very
close to zero, not just "roughly centered") before spending on a fourth paid attempt -- if a brief-only
change is plausible, try it; if the brain's own P1 signal's resolution genuinely cannot support an 8px-
equivalent decision (e.g. its `deg_per_step` granularity floors out above what 8px represents), that is a
primitive-precision finding for the design doc, not a bar problem.

## Files

- `eval/ceiling_gate3d.py` -- the ceiling script (new).
- `eval/fixtures/gate3d_ceiling_results.json` -- raw per-seed / per-tolerance results (new).
- Untouched, as required: `eval/score_gate3d.py`, `eval/fixtures/gate3d_seeds.json`,
  `eval/fixtures/gate3d_baselines.json`, `core/`, `scenarios/`.
