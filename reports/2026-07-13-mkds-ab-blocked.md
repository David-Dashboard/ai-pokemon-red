# MKDS continuous-time A/B - launch blocked by account cap (2026-07-13)

Status: **BLOCKED before any scored attempt**.

David explicitly authorized the paid MKDS A/B on 2026-07-13. Pre-launch checks passed:

- `runs/brain_mkds_armA/seamcheck.sh`: 3/3 PASS.
  - `NDS_SKILLS=1` exposed `define_skill` / `run_skill`.
  - `NDS_SKILLS` unset exposed no skill tools.
  - `KIRBY_SKILLS=1` alone exposed no skill tools.
- Docker image: `gb-mcp-world:latest` matched `sha256:dfd12eac87bb...`.
- Arm A/B launcher dirs had no prior `transcript.jsonl`, `run.exit`, or `world/` artifacts.
- Arm A `CLAUDE.md` / Arm B `CLAUDE.md` did not expose the RAM oracle address or score path.

## Arm A launch result

Arm A was launched first, per the pre-registration. It failed before the world connected:

Artifacts:

- `runs/brain_mkds_armA/transcript.jsonl`
- `runs/brain_mkds_armA/run.exit`
- `runs/brain_mkds_armA/run.err`

Observed facts:

- `run.exit`: `EXIT=1`
- `run.err`: empty
- No `runs/brain_mkds_armA/world/` directory was created.
- `transcript.jsonl` includes an MCP init event with `mcp_servers=[{"name":"mkds","status":"pending"}]`, but no world/tool interaction.
- Result event: `api_error_status=429`, `num_turns=1`, `duration_api_ms=0`, `total_cost_usd=0`, `is_error=true`.
- Rate-limit event: `rateLimitType=seven_day`, `overageStatus=rejected`, `overageDisabledReason=out_of_credits`.
- User-facing reset text: `You've hit your weekly limit - resets Jul 16, 8pm (Europe/Stockholm)`.

## Verdict

This is not an A/B verdict and not a scored Arm A attempt. It is an account-cap block before MCP/world connection and before any paid work reached the task.

Per `paid-run-harness` law 1, do not hammer, do not switch to account A, and do not use an API key. Arm B was not launched.

Next allowed action: wait until the account-B weekly limit resets at **2026-07-16 20:00 Europe/Stockholm** (same UTC offset as Europe/Berlin on this date), then relaunch Arm A first from the same pre-registered discipline unless David changes the plan.
