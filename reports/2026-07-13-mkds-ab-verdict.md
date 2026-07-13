# MKDS continuous-time A/B verdict (2026-07-13)

Status: **FAIL on primary batching bar; conditional-half PASS.**

The first account-B launch hit a weekly-limit 429 before MCP/world connection and is banked separately
in `reports/2026-07-13-mkds-ab-blocked.md`. David then explicitly authorized using the default
`~/.claude` account/config. To preserve the account-B artifacts, the scored default-account runs used
separate launcher dirs:

- Arm A: `runs/brain_mkds_armA_default/`
- Arm B: `runs/brain_mkds_armB_default/`

Pre-launch seamcheck passed 3/3 before spending: `NDS_SKILLS=1` exposed `define_skill` / `run_skill`;
unset exposed no skill tools; `KIRBY_SKILLS=1` alone exposed no skill tools. The default-account
launchers unset `CLAUDE_CONFIG_DIR`, wiped only this repo's default Claude auto-memory paths, and wrote
world artifacts under the `_default` dirs.

## Frozen bar

From `reports/2026-07-04-mkds-continuous-time-build-plan.md` section 7:

- Arm A: no skill tools.
- Arm B: `NDS_SKILLS=1`, adding `define_skill` / `run_skill`.
- Primary metric: world frames advanced per decision; PASS requires **Arm B >= 1.3x Arm A**.
- Guard: Arm B must show **>=1 qualifying-conditional `run_skill` call** whose `stop_when` fired before
  hitting `F=300` / `max_iters=8`.

## Run facts

| Arm | Raw dir | Exit | Claude turns | Cost | In-world decisions | Oracle frames | Frames / decision |
|---|---|---:|---:|---:|---:|---:|---:|
| A | `runs/brain_mkds_armA_default/` | `EXIT=0` | 17 | `$0.77483` | 13 | 60 -> 3044 = 2984 | 229.538 |
| B | `runs/brain_mkds_armB_default/` | `EXIT=0` | 19 | `$0.7740115` | 10 | 60 -> 2425 = 2365 | 236.500 |

Primary ratio: `236.500 / 229.538 = 1.030x`.

Total default-account cost: `$1.5488415`. Account-B blocked launch cost: `$0`.

## Arm B conditional evidence

`runs/brain_mkds_armB_default/world/skills.jsonl` is authoritative, not the brain's final summary.

- `define_skill`: 3
- `run_skill`: 10
- `stop_when_fired=true`: 9
- `stop_when_fired=false`: 1 (`coast`, `idle_settled`, max_iters timeout)
- Sum of `world_frames_used`: 2365

The guard passes. Examples:

```text
launch: stop_when 'elapsed_frames(90)' fired after 93 frame(s)
drive: stop_when 'elapsed_frames(280)' fired after 280 frame(s)
```

## Verdict

**FAIL**. Arm B satisfied the conditional-half guard, but missed the primary batching bar:

```text
required: Arm B >= 1.300x Arm A
observed: Arm B = 1.030x Arm A
```

## Caveats / diagnosis

- The offline checkpoint/progress byte (`0x022C8090`) was not present in either run's `oracle.jsonl`.
  The NDS registry has `watch={}`, so these artifacts contain frame/perception logs but not the
  verified RAM progress byte. Do not claim checkpoint/lap progress from RAM for this run.
- Arm A had `press_sequence` available and used it heavily (`6 x 12` accelerate presses). That made
  the baseline already batch many emulator frames per LLM wake, compressing the advantage available
  to Arm B's skill tools.
- Arm B did prove the continuous-time conditional mechanism works: repeated `elapsed_frames(...)`
  predicates fired before the ceiling. The failed claim is not "conditional skills do not work"; it is
  "this A/B surface did not produce >=1.3x frames-per-decision over the baseline."
