# MKDS continuous-time A/B — $0 launch surface

Builds the machinery for the pre-registered gate (`2026-07-04-mkds-continuous-time-build-plan.md` §7).
No paid run launched — David's go is still required.

## What was built
1. **Docker image rebuilt.** `gb-mcp-world:latest` predated the NDS_SKILLS merge (0 occurrences of
   `NDS_SKILLS` in the shipped `world_mcp.py`). Rebuilt from the current repo (`docker build -t
   gb-mcp-world .` in WSL); layers cached except the final `COPY world_mcp.py`. New image
   `sha256:dfd12eac87bb...` (Created 2026-07-11T10:25:17Z). Receipt: `grep -c NDS_SKILLS` inside the
   built image = **16**, `_NDS_SKILL_SAMPLE_STRIDE` present = **True**. (An unrelated `gb-mcp-world:ndsct`
   tag already existed, presumably from the other active session — untouched, `latest` is the only tag
   this task moved.)
2. **Launcher dirs**: `runs/brain_mkds_armA/` (baseline) and `runs/brain_mkds_armB/` (NDS_SKILLS=1),
   each with `run.sh` (account-B, blank-agent memory wipe, trust-dialog pre-accept, `--max-turns 90`
   hard cap) and `.mcp.json` (server `mkds`, `--game nds`, `--rom "roms/nds/Mario Kart DS (USA)
   (En,Fr,De,Es,It).nds"`, `--init-state runs/nds3d_probe/mkds_race_start.state`, `--keep-frames`).
   **Deviation from the Kirby template: no `--record`** — `world_mcp.py` raises `SystemExit` if
   `--record` is combined with a non-GB world (NDS/GBA recording isn't wired), so only `--keep-frames`
   (per-step PNGs) is used for either arm.
3. **`seamcheck.sh`** (`runs/brain_mkds_armA/seamcheck.sh`) — free `tools/list` probe, no claude
   account, run against the fresh image.
4. **Briefs** — arm-specific `CLAUDE.md`, not conditional-generic: Arm A never mentions skills at all;
   Arm B documents `define_skill`/`run_skill` with the two pinned predicates
   (`elapsed_frames(n)`, `0<n<=300`; `idle_settled(threshold,k)`, `0.005<threshold<0.06`, `k>=1`,
   `k*4<=300` since `s=4`) and the conditional-half objective ("aim for at least one `run_skill` call
   whose stop_when actually FIRES"). Both briefs warn hard that `observe`'s pose/walls/frontier (and
   `explore`/`goto`) come from a top-down GB-dungeon perceiver that does not understand this 3D scene —
   IGNORE them; steering is out of scope (`region_*` deferred), a straight hold-forward through the
   count-in is the intended solution. No RAM/oracle/lap address anywhere on the wire or in either brief.
   Both pin `--max-turns 90` and a "cap ~30 decisions" pacing note, kept symmetric across arms.

## seamcheck output (verbatim, against the fresh image, 2026-07-11)
```
== a_NDS_SKILLS_on
['define_skill', 'run_skill'] | total: 11
== b_NDS_SKILLS_off
NO-SKILL-TOOLS | total: 9
== c_KIRBY_SKILLS_only
NO-SKILL-TOOLS | total: 9
```
All three `.err` captures were 0 bytes (no stderr/errors). Assertions:
- (a) `--game nds` + `NDS_SKILLS=1` → skill tools PRESENT — **PASS**
- (b) `NDS_SKILLS` unset → skill tools ABSENT — **PASS**
- (c) `KIRBY_SKILLS=1` alone on `--game nds` → skill tools ABSENT (cross-flag isolation) — **PASS**

## Build-plan doc discrepancy (use CODE, not the doc)
Plan §4 says `s=24, k=10`. The plan's own arithmetic was wrong for the shorter measured count-in hold
(22 frames): at `s=24` at most 1 sample lands below threshold inside it, so `idle_settled` could never
reach `k=10`. The **shipped code** (`world_mcp.py:749`, comment block above it) pins **`s=4`** instead
(margin: floor(22/4)=5, floor(37/4)=9 samples inside the two measured holds), with `F=300`, `max_iters
<=8`, threshold strictly in `(0.005, 0.06)`. This report and both briefs use the code values throughout;
the plan doc itself is untouched (not a tracked file I was allowed to edit).

## What remains before any spend
- **David's explicit go** to launch — not authorized by this task, `claude -p` was not run.
- **Oracle hunt**: the plan's own §7 defers "exact task-progress oracle (checkpoint/lap from RAM) ...
  pinned in the build PR from an offline oracle hunt" — **not done here**, out of this task's scope.
  Without it the A/B has no offline scorer; do that before spending.
- **Agent-count/cost heads-up**: 2 agents (Arm A, Arm B), one attempt each, Arm A first (inherited
  discipline). `--max-turns 90` is the budget per arm; per the harness skill's own note ("90 turns ≈
  $5-class run") and this task's much lighter brief (~30-decision cap, no multi-cycle claim protocol),
  expect materially cheaper than the $5 Kirby v3.1 run per arm — plan for **≲$5/arm, ≲$10 total** as a
  ceiling, actual likely lower since the task is a single straight-hold segment, not a multi-cycle gate.
- Seam check passed on a genuinely fresh image — safe to launch once the above two items land.
