# Gate 0 Arm R (Pokémon Red) verdict — first completed real run, app-server path (2026-07-24)

**BANKED VERDICT: task success NOT proven by the frozen predicate.** One paid attempt, scored
verbatim by `eval.score_gate0._red_success`, per gate-methodology §4/§5 (one attempt, verdict banked
as printed). `_red_success` returns `(False, ['red_no_sustained_battle_exit'])` — see §2. This is the
permanent record for this attempt; it is not a "try again."

This is Arm R only. Arm W (MiniWoB) has not completed a paid run (`runs/gate0_paid/miniwob/` holds
only handshake/launch artifacts, no `transcript.jsonl`, no `agent_metrics.json`, no oracle) —
Generality and the full two-arm `score_gate0.score()` verdict remain open. See §5.

## 1. Run facts

**Launch command** (pre-registered in `reports/2026-07-24-gate0-prereg-amendment-appserver.md`
§"Orchestrator commands (c)", app-server transport):
```
python -m tools.gate0_appserver_arm --arm red --model gpt-5.6-sol \
    --out-dir runs/gate0_paid/red --credit-rate-pin <path-to-signed-rate-pin.json>
```

- **Model:** `gpt-5.6-sol`, `codex-cli 0.144.3`, auth `chatgpt`.
- **EXIT:** 0 (`run-receipt.json`: `kind: gate0_appserver_arm_run_receipt`).
- **wall_clock_s:** 127.75. **primitive_actions:** 142 (agent) vs **human_wall_clock_s:** 233.288 /
  **human_primitive_actions:** 271 (`agent_metrics.json`).
- **cost_usd:** 0.41589099999999996. **normalized_credits:** 10.397274999999999.
- **credit_breaker_tripped:** false. **soft_cap_warned:** false.
- **world_image_id:** `sha256:5bfabc7513ce037ed077e955fd34445ef564a7b51037bd7fdddeef0cdb900d00` —
  matches the frozen pin in `eval/fixtures/gate0_expected_pins_red.appserver.json`.

**Three prior $0 infra deaths on this exact Arm R launch, all fixed and merged before this run, no
tokens spent on any of them** (verified via `gh pr view` against `David-Dashboard/ai-pokemon-red`):

- **PR #158** (`fix/arm-world-mount-absolute`, merged as `e40b36e`) — "Arm R died at the pre-flight
  `docker tools/list` (before any codex turn / spend) because the `/app/world` bind-mount source was
  **relative** ... Docker on Windows requires an absolute source." $0, pre-turn.
- **PR #159** (`fix/appserver-stderr-drain`, merged as `c75e88c`) — `_StdioTransport` piped the codex
  child's stderr but nothing read it; if codex wrote enough to fill the OS pipe buffer, its own
  `write()` blocks and it stops servicing stdio — "indistinguishable from an `initialize` hang."
  Fixed by draining stderr on a background thread + a `handshake_timeout` as insurance. $0, pre-turn
  (root cause "not force-reproducible," so this is a deadlock-risk fix, not a confirmed single
  incident).
- **PR #160** (`fix/arm-codex-home-absolute`, merged as `b770efa`, current `main` HEAD) — "3rd
  relative-path bug, now visible thanks to #159's stderr capture: `codex.stderr.log` showed `Error:
  CODEX_HOME points to "runs\gate0_paid\red\codex-home", but that path does not exist`" — the codex
  child runs with `cwd=out_dir`, so a relative `CODEX_HOME` re-resolved against `out_dir` and wasn't
  found, so codex exited and `initialize` timed out. $0, pre-turn.

Each PR body states it "unblocks Arm R" — these are relaunch-after-infra-death events under law 6
(bounded-steps: an infra death before any turn/spend permits a relaunch; a completed run is final).
This run is **launch #4**, the first to clear all three and reach a real codex turn.

## 2. BANKED VERDICT — the frozen predicate, verbatim

Re-run directly against this run's oracle (not the scorer's cached summary), from a clean checkout on
`docs/gate0-armR-verdict` (`eval/score_gate0.py` untouched):

```
$ python -c "
import sys, json
sys.path.insert(0, '.')
from eval.score_gate0 import _red_success
rows = [json.loads(l) for l in open(r'runs/gate0_paid/red/world/oracle.jsonl', encoding='utf-8') if l.strip()]
print('total oracle rows:', len(rows))
print('RESULT:', _red_success(rows))
"
total oracle rows: 438
RESULT: (False, ['red_no_sustained_battle_exit'])
```

**Per the frozen scorer, Arm R's task success is NOT proven.** This is not softened by anything
below — `_red_success` returns `False`, single failure reason `red_no_sustained_battle_exit`.

## 3. What DID validate

Equally important, equally honest — this run is not a wash:

- **The brain obtained the starter and survived the rival battle, in fewer actions and less time
  than the human baseline.** Independently recomputed from `oracle.jsonl`'s 438 rows:
  - `party` transitions 0→1 exactly once, at row index 333 (`Counter({0: 335, 1: 103})`) —
    satisfies `red_not_fresh_party_zero` / `red_no_party_0_to_1` / `red_first_party_transition_not_exactly_0_to_1`.
  - `in_battle` reaches 2 (trainer battle) for **43 contiguous rows, 391–433**
    (`Counter({0: 395, 2: 43})`) — satisfies `red_no_trainer_battle_after_party_acquisition`.
  - Player HP: **19 → 1 during the battle, never 0** (min across the battle span is 1, at rows
    427–428) — the battle was actually fought and survived, not skipped or lost
    (`red_player_hp_reached_zero` does not fire).
- **Beat the human baseline on both axes, comfortably inside the ≤2× caps:** 127.75s / 142 actions
  vs human 233.288s / 271 actions → well under the 466.576s / 542-action ceilings
  (`_arm_metrics`'s `wall_clock_over_2x_human` / `actions_over_2x_human` do not fire).
- **Cheap bar cleared:** cost $0.4159 ≤ $5.00 arm cap; 10.397 ≤ 125 credit arm cap (`score()`'s
  `limits["red"] = (5.0, 125)`). Breaker never tripped, soft cap never warned.
- **NO_LEAK: PASS.** Recomputed directly via `tools.check_gate0_codex.audit()` against this run's
  `transcript.jsonl` / `handshake-receipt.json`: `"no_leak": "PASS"`, `"leak_failures": []`. No
  tool-allowlist or protocol violation; the app-server transcript adapter held.
- **The app-server launch path worked end-to-end**, real turn, real approval RPC, real result — the
  thing PRs #147/#151/#158–#160 built toward.
- **Cross-check on the predicate itself:** the human baseline for this exact task
  (`runs/gate0_human_baseline/red/human_metrics.json`, `success: true`) was independently reconstructed
  by replaying David's archived attempt through this same `_red_success` and finding the first
  passing prefix — i.e. a real human trace *does* satisfy this predicate, including its 10-row exit
  tail. The bar is achievable; this run's miss is not an artifact of an impossible predicate.

## 4. Mechanical diagnosis of the miss

The brain's own final message (`transcript.jsonl` tail, `phase: "final_answer"`):

```
"Obtained Charmander from Professor Oak and defeated Gary in the first rival battle."
```

immediately followed by `turn.completed` — no further tool calls. It declared victory and **stopped
acting**. The run brief (`runs/gate0_paid/red/launch/TASK.md`, `task_sha256` matches the frozen pin)
reads: *"...Begin by observing. Stop when the stated task is complete."* — the brain followed that
instruction literally and stopped the instant it believed the objective was met.

`_red_success`'s exit check requires **10 consecutive `in_battle == 0` rows** after the battle
(`eval/score_gate0.py:52-53`) plus at least 2 distinct post-exit `(x, y)` positions
(`red_no_free_movement_after_exit`, line 87-88). Verified directly against the oracle: `in_battle`
goes `[..., 2, 0, 0, 0, 0]` from index 433 to the recording's end at index 437 (438 total rows) —
only **4** trailing zero rows exist, and `(x, y)` is `(5, 6)` on every one of them (no movement at
all). The predicate's bounded search window (`range(battle_idx+1, max(battle_idx+1, len(watches)-9))`)
never even reaches index 434, because fewer than 10 rows remain after the battle ends — the episode
was too short by design of the stop-on-completion instruction, not because the exit didn't happen.

**This predicate is not "wrong."** It exists specifically to guard against false-victory /
battle-bounce declarations — a brain that *claims* victory one tick after a battle flag flips (before
the game engine has actually released control, or before a loss disguised as a win) would look
identical to a real win without a sustained, observed tail. Distinguish carefully:

- **In-game, the task was almost certainly accomplished** — starter obtained, rival battle fought and
  survived, HP never hit 0, the brain's own narration matches the oracle facts exactly.
- **By the frozen measurement, it is unproven** — the predicate demanded evidence the run never
  produced, because the brief told the brain to stop the moment it believed it was done.

## 5. Honest bounds

- **This is ONE arm.** The North Star's Generality claim needs both Red and MiniWoB scored together;
  Arm W has not run to completion (`runs/gate0_paid/miniwob/` has launch/handshake artifacts only —
  no transcript, no oracle, no `agent_metrics.json`). The paired `score_gate0.score()` verdict cannot
  be computed from this run alone.
- **Constancy between arms is UNPROVEN.** `compare_constancy` never ran — there is no peer receipt
  (confirmed below, §6: `"peer_constancy": "NOT_PROVEN"`).
- **Capability is suggestive but unproven by the frozen bar.** The Cheap and cost/action-efficiency
  bars are real, independently-verified PASSes. The capability predicate is a real, verified FAIL.
  Neither claim licenses the other — "beat the human on time/actions" is not "passed the task."
- This run does **not** license claiming Gate 0 as passed, partially passed, or "morally passed."
  The banked verdict per the frozen scorer is what it is (§2).

## 6. CONSTANCY_BREACH — diagnosis (scoring-infra fixture issue, not a code/brain/seam change)

`run-receipt.json` records `audit_overall: CONSTANCY_BREACH`. Recomputed directly, read-only, via
`tools.check_gate0_codex.audit()` against this run's own artifacts (transcript, handshake receipt,
the app-server expected-pins fixture `eval/fixtures/gate0_expected_pins_red.appserver.json`, no peer
receipt):

```
{
  "schema_version": 2, "arm": "red", "no_leak": "PASS", "overall": "CONSTANCY_BREACH",
  "wakes": null, "wake_accounting": "INSUFFICIENT_WAKES", "peer_constancy": "NOT_PROVEN",
  "leak_failures": [],
  "constancy_failures": [
    "pin_mismatch:config_sha256",
    "pin_mismatch:codex_mcp_list_sha256",
    "pin_mismatch:tool_schema_sha256"
  ],
  "accounting_failures": [], "run_failures": [],
  "primitive_action_events": 142
}
```

Three single-arm `pin_mismatch` failures, no leak, no cross-arm comparison (never ran):

- **`config_sha256`, `codex_mcp_list_sha256`** — the `.appserver` expected-pins fixture pins these to
  literal `"CONSTRAINT:launch-invocation-dependent-recompute-at-signature"` strings (verified in
  `eval/fixtures/gate0_expected_pins_red.appserver.json`, fields never a real hash — by the fixture's
  own documented design, since both values depend on the launch `-OutputDir`'s absolute paths).
  A `CONSTRAINT:` placeholder can never equal a live hash, so this mismatch is unavoidable by
  construction of the pin, not evidence of a real launch-identity divergence.
- **`tool_schema_sha256`** — the fixture pins `e55bb8193f0c3ecb531519db2b93a3a597dbd97d9cb42468e63334c1ae7ffa71`,
  computed (per `eval/fixtures/gate0_expected_pins.SOURCES.md`) by serializing the same live
  `tools/list` handshake through **PowerShell 5.1 `ConvertTo-Json -Depth 20 -Compress`** against the
  exec-era launcher. This run's actual value, `102e4cb37c4b5412c149c706c5862f412934bee7d10c105478afa2db5c877c3e`,
  is the SHA-256 of `runs/gate0_paid/red/mcp-tools.json` as written by the app-server launcher
  (`tools/gate0_appserver_arm.py`, `json.dumps(tools)` in Python) — independently confirmed by
  hashing that exact file. `mcp_tools_observed` in both the pin and this run's `handshake-receipt.json`
  list the **identical 7 tools** (`observe, explore, goto, remember, press_button, press_sequence,
  wait`) with identical descriptions/schemas — this is a **serialization-format mismatch** (PowerShell
  vs Python JSON encoding of the same content), not a tool-inventory divergence.

**Conclusion: NOT a real identity divergence, NOT a between-arms mismatch.** `compare_constancy`
never ran (no Arm W peer receipt exists yet — `peer_constancy: "NOT_PROVEN"` above). The fix is a
scoring-infra fixture change (freeze a Python-`json.dumps`-based `tool_schema_sha256` value and/or a
signature-time recompute step for the two `CONSTRAINT:` fields on the `.appserver` fixture) — it does
not touch `eval/score_gate0.py`, the brain, or the world seam. Being fixed separately in a pins PR
(this report changes none of it).

## 7. vNext candidates — NOT decided, David's call

- **(a) Red-v2 fresh pre-registration** whose brief/task text requires the agent to keep
  observing/moving briefly after declaring the objective met (e.g. an explicit "after you believe the
  task is done, continue observing for several more turns before stopping" instruction). **This
  requires a new pre-registration and a fresh `task_sha256` freeze** — task text is a byte-frozen pin
  (`tools/gate0_appserver_arm.py::task_text_for()`, hash-matched against the expected-pins fixture),
  so this is not an editable tweak to the current pin, it is a new gate attempt.
- **(b) A scorer-side alternative** (e.g. shortening the required exit-tail window, or scoring on
  in-game state alone without the tail guard). **NOT recommended without David.** Changing a frozen
  predicate post-hoc to fit a run that already happened is exactly the loosening the gate methodology
  forbids (§2, "changes to scoring machinery are allowed only if stricter-only"). If pursued at all,
  it should be argued and pre-registered as a *new*, tighter-or-orthogonal predicate for a *future*
  gate, never as a retroactive re-grade of this attempt.
- **(c) Bank as-is** and let Arm R stand as FAIL_CAPABILITY-by-predicate while Arm W (and the paired
  two-arm verdict) remain the open next step.

## 8. Cross-references

- `reports/2026-07-24-gate0-prereg-amendment-appserver.md` — the app-server transport pre-reg
  amendment this run executed (launch command, pin verification, frozen-pin independence).
- `reports/2026-07-23-gate0-appserver-m1-confirmation.md` — the M1 confirmation that the app-server
  approval round-trip works end-to-end (stub MCP, $0.08 real turn), which this run extends to the
  real Docker `gb-mcp-world` and a full task.
- `reports/2026-07-18-gate0-prereg.md` — the original Gate 0 two-arm pre-registration (scorer,
  bars, one-attempt rule).
- `eval/fixtures/gate0_expected_pins.SOURCES.md` — full source citations for every pinned field,
  including the `CONSTRAINT:` recompute-at-signature fields and the `tool_schema_sha256` derivation
  discussed in §6.
- `runs/` is gitignored — the on-disk evidence this report cites
  (`runs/gate0_paid/red/{transcript.jsonl,transcript.raw_appserver.jsonl,world/oracle.jsonl,
  agent_metrics.json,handshake-receipt.json,run-receipt.json,codex.stderr.log,mcp-tools.json}`,
  `runs/gate0_human_baseline/red/human_metrics.json`) exists only on the machine that ran it; the
  key artifacts this report depends on are copied, append-only, into
  `reports/2026-07-24-gate0-armR-verdict/` alongside this file.

## Evidence filed

- `reports/2026-07-24-gate0-armR-verdict/agent_metrics.json` — copied verbatim.
- `reports/2026-07-24-gate0-armR-verdict/handshake-receipt.json` — copied verbatim.
- `reports/2026-07-24-gate0-armR-verdict/oracle.jsonl` — copied verbatim (438 rows, ~200KB), the
  source this report's §2/§3/§4 numbers were independently recomputed from.
