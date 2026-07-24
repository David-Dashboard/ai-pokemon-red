# Gate 0 — FIRST PAIRED verdict (Arm R + Arm W, codex app-server path, 2026-07-24)

**Status: $0 — docs + offline analysis only.** No re-run, no paid spend, no code/scorer/fixture
edits. This report re-verifies both arms' frozen predicates from the raw oracle logs, runs the
between-arms Constancy check (`tools/check_gate0_codex.py::compare_constancy`) for the first time
this project has ever run it, attempts the frozen end-to-end scorer (`eval/score_gate0.py
score_manifest`), and banks the combined verdict. Cross-references: `reports/2026-07-24-gate0-armR-verdict.md`
(PR #161, Arm-R-only, in depth — this report does not duplicate its Arm R analysis, only restates
the re-verified numbers needed for the paired picture), `reports/2026-07-24-gate0-prereg-amendment-appserver.md`,
`reports/2026-07-18-gate0-prereg.md`, `reports/2026-07-23-gate0-appserver-m1-confirmation.md`.
`runs/` is gitignored; the artifacts cited below are on-disk evidence in the primary checkout, with
the Arm W subset committed under `reports/2026-07-24-gate0-paired-verdict/` (see §6).

## 1. Banked verdict, stated plainly

| Axis | Result |
|---|---|
| **Capability** | **FAIL** — both arms fail their frozen predicates |
| **Generality** | **FAIL** — Gate 0's generality claim requires both arms to pass; they didn't |
| **Cheap** | **PASS** — combined `$1.4455` / `36.14` credits vs the `$7.00`/`175`-credit bar (see §2c) |
| **NO_LEAK** | **clean, both arms** (re-verified below) |
| **Constancy (between-arms identity check)** | **clean — first time this check has ever run** (see §3) |
| **`score_gate0.py score_manifest()` end-to-end verdict** | **`CONSTANCY_BREACH`** — but for reasons unrelated to the between-arms check; see §4 for why this is a pin-freeze/fixture-lifecycle artifact, not a real identity divergence |

This is a **spent, one-attempt-per-arm result** under the current pre-registration. It is banked
as-is, per the gate-methodology one-attempt rule. Nothing here is a re-run.

## 2. Frozen predicates, re-run verbatim

Both predicates were re-executed directly against the raw `world/oracle.jsonl` files
(`runs/gate0_paid/red/world/oracle.jsonl`, 438 watch rows; `runs/gate0_paid/miniwob/world/oracle.jsonl`,
41 rows), using the unedited `eval/score_gate0.py` functions, from a fresh Python process.

### 2a. Arm R — `_red_success(rows)`

```
(False, ['red_no_sustained_battle_exit'])
```

Matches the pre-supplied fact exactly. Independently re-confirmed from the oracle: party 0→1 at
watch-row index 333; `in_battle == 2` for 43 contiguous rows (indices 391-433). Full mechanical
diagnosis (why the exit-span predicate isn't satisfied, the brain's own final message declaring
victory and stopping) lives in the Arm-R-only verdict, PR #161 — not repeated here.

### 2b. Arm W — `_miniwob_success(rows, expected_seeds)`

```
expected_seeds for paid_gate0: [1000, 1001, 1002, 1003, 1004]
(False, ['miniwob_episode_1_terminal_not_success'])
```

Independently re-confirmed from the oracle — exactly 5 terminal rows, one per episode/seed, task
`click-checkboxes` throughout, `abandoned == False` on all five:

| episode | seed | reward | done | abandoned |
|---|---|---|---|---|
| 0 | 1000 | 1.0 | True | False |
| 1 | 1001 | 0.6666666666666666 | True | False |
| 2 | 1002 | 1.0 | True | False |
| 3 | 1003 | 1.0 | True | False |
| 4 | 1004 | 1.0 | True | False |

4/5 episodes terminated at the pinned success condition (`reward == 1.0`, `done is True`,
`abandoned is False`); episode 1 (seed 1001) terminated at `reward = 2/3`, which fails the
`reward == 1.0` equality the frozen predicate requires — the single predicate miss. 97 primitive
actions / 295.594s / `$1.02958` (25.7395 credits).

### 2c. Cheap — re-verified from `agent_metrics.json`, both arms

Red: `$0.41589` / `10.397275` credits (cap `$5.00`/`125`). MiniWoB: `$1.02958` / `25.7395` credits
(cap `$2.00`/`50`). Combined: `$1.44547` / `36.136775` credits vs the combined PASS bar
`$7.00`/`175` and the hard breaker `250`. Both individually and combined, comfortably under —
neither soft cap nor the hard breaker came close to tripping. This is a genuine, re-verified PASS
on the Cheap axis alone; it does not offset the Capability/Generality FAILs (Gate 0's axes are
independent, not averaged).

## 3. The between-arms Constancy check — run for the first time this project has ever run it

`tools/check_gate0_codex.py::compare_constancy(receipt, peer)` takes two receipt dicts and diffs
them over `CONSTANCY_FIELDS` — a 9-field subset of the full 20-field `PIN_FIELDS` vocabulary,
specifically: `readiness, paid_execution_enabled, auth_method, planned_model, codex_version,
codex_path, codex_executable_sha256, critical_config_transport, brain_config_sha256`. It also
requires `{receipt['arm'], peer['arm']} == {'red', 'miniwob'}`.

This function has existed since the pre-registration but had **never been invoked with a real
peer receipt before this report** — Arm R's own verdict (PR #161) explicitly could not run it
(`peer_constancy: "NOT_PROVEN"` — no Arm W receipt existed yet at that time). Both arms' receipts
now exist, so this is the first real run.

```
compare_constancy(red_receipt, miniwob_receipt) -> []
compare_constancy(miniwob_receipt, red_receipt) -> []   # symmetry check, same result
```

**Empty list — every one of the 9 CONSTANCY_FIELDS matches exactly between the two arms.**
Field-by-field (all MATCH):

| field | red | miniwob |
|---|---|---|
| `readiness` | `NO_GO_INSUFFICIENT_WAKES` | `NO_GO_INSUFFICIENT_WAKES` |
| `paid_execution_enabled` | `False` | `False` |
| `auth_method` | `chatgpt` | `chatgpt` |
| `planned_model` | `gpt-5.6-sol` | `gpt-5.6-sol` |
| `codex_version` | `codex-cli 0.144.3` | `codex-cli 0.144.3` |
| `codex_path` | `...\Codex\bin\codex.exe` | `...\Codex\bin\codex.exe` (identical string) |
| `codex_executable_sha256` | `e5dcc9f9...fcf6e3` | `e5dcc9f9...fcf6e3` (identical) |
| `critical_config_transport` | `explicit_cli_overrides` | `explicit_cli_overrides` |
| `brain_config_sha256` | `ab7e54c1...041fc3` | `ab7e54c1...041fc3` (identical) |

### What this proves, precisely

The **same Codex executable** (byte-identical, by hash), running the **same model**
(`gpt-5.6-sol`), authenticated the **same way** (ChatGPT subscription, not an API key), configured
via the **same transport discipline** (explicit CLI overrides, not fresh-project trust), and
launched from the **same brain-config content** (byte-identical developer-instructions/system
prompt, by hash — `brain_config_sha256` is deliberately arm-independent, so this hash matching is
exactly the "one fixed brain" claim at the byte level) drove two structurally different worlds: a
Game Boy emulator (Pokémon Red, `gb-mcp-world`) and a browser DOM environment (MiniWoB
`click-checkboxes`, `miniwob-world`). Only the world and its tool surface changed between arms —
everything CONSTANCY_FIELDS tracks about the brain/launch identity held fixed.

### What this does NOT prove

- **Not behavioral or performance equivalence.** Identical identity does not imply identical
  competence — Capability FAILed on both arms, by different mechanisms (§5). Constancy-of-identity
  and Capability are separate axes; this check speaks only to the former.
- **Not full-pin equality.** `CONSTANCY_FIELDS` is a deliberate 9-field subset of the 20 `PIN_FIELDS`
  — it excludes `task_sha256`, `mcp_servers_observed`, `mcp_tools_observed`, `world_image_tag`,
  `world_image_id`, `host_code_sha256`, `image_code_sha256`, `config_sha256`,
  `codex_mcp_list_sha256`, `tool_schema_sha256`, `arm` by design, because those fields are
  *supposed* to differ per-arm (different task, different tool allowlist, different world image) or
  are launch-invocation-dependent. This check is scoped correctly to "same brain," not "identical
  receipts."
- **Not a statement about the frozen expected-pins fixtures.** See §4 — the end-to-end scorer's
  `CONSTANCY_BREACH` verdict comes from a *different* check (receipt-vs-frozen-pin, not
  receipt-vs-peer) and is not evidence against the result in this section.

This is the **headline new evidence** of this report: direct, first-ever proof that one fixed brain
identity drove two different world classes in the same banked attempt.

## 4. The frozen end-to-end scorer — how far `score_manifest()` gets

A manifest was constructed with the exact path strings from `eval/fixtures/gate0_paid_source_pins.json`'s
own `audit_paths` (copied verbatim, not invented — this is the manifest shape
`score_manifest()`'s own tests use, see `tests/test_score_gate0.py`). This is not a bypass of the
frozen pins: `_verify_audit_paths()` refuses any manifest path that doesn't literally match the
pinned strings, so the only way to get past that gate at all is to supply exactly what's pinned.
The manifest file itself was written to the scratchpad (never inside either repo) — `score_manifest()`
resolves the relative path strings against `eval/score_gate0.py`'s own `ROOT`, so its location is
irrelevant to what it reads; nothing was written into `runs/`.

**Verbatim result:**

```json
{
  "cheap_basis": "cost_per_task",
  "failures": {
    "capability": [
      "red:red_no_sustained_battle_exit",
      "miniwob:miniwob_episode_1_terminal_not_success",
      "red:task_predicate_failed",
      "miniwob:task_predicate_failed"
    ],
    "cheap": [],
    "constancy": [
      "red:pin_mismatch:config_sha256",
      "red:pin_mismatch:codex_mcp_list_sha256",
      "red:pin_mismatch:tool_schema_sha256",
      "miniwob:pin_mismatch:config_sha256",
      "miniwob:pin_mismatch:codex_mcp_list_sha256",
      "miniwob:pin_mismatch:tool_schema_sha256"
    ],
    "infra": [],
    "leak": [],
    "source": [
      "red:missing_or_invalid_metric:wall_clock_s",
      "red:missing_or_invalid_metric:primitive_actions",
      "red:missing_or_invalid_metric:human_wall_clock_s",
      "red:missing_or_invalid_metric:human_primitive_actions",
      "red:missing_or_invalid_metric:cost_usd",
      "red:missing_or_invalid_metric:normalized_credits",
      "miniwob:missing_or_invalid_metric:wall_clock_s",
      "miniwob:missing_or_invalid_metric:primitive_actions",
      "miniwob:missing_or_invalid_metric:human_wall_clock_s",
      "miniwob:missing_or_invalid_metric:human_primitive_actions",
      "miniwob:missing_or_invalid_metric:cost_usd",
      "miniwob:missing_or_invalid_metric:normalized_credits",
      "frozen_seed_hash",
      "source_hash:red_agent",
      "source_hash:miniwob_agent",
      "source_unreadable:miniwob_human",
      "source_hash:wake_boundary",
      "source_unreadable:live_breaker",
      "wake_boundary_artifact",
      "live_breaker_artifact"
    ]
  },
  "overall": "CONSTANCY_BREACH",
  "readiness": "NO_GO",
  "schema_version": 1,
  "spend_usd": 0,
  "wake_accounting": {
    "detail": {},
    "evidence": "reports/2026-07-21-gate0-wake-grounding.md",
    "reason": "no_per_model_decision_observable_in_codex_jsonl_stream",
    "status": "DEFERRED"
  }
}
```

`score()`'s failure-category precedence puts `constancy` failures ahead of `source`/`capability`/
`cheap`, so `overall` reads `CONSTANCY_BREACH` even though (by the direct check in §3) the two arms'
brain identity is provably clean. **Do not read this line as contradicting §3** — it is a different
check with an overloaded name. Mechanical trace of every failure below, none fabricated or
smoothed over:

**The `constancy` failures (6 entries, 3 per arm) are `_expected_failures()` inside `audit()`** —
receipt-vs-*frozen-pin-fixture* comparisons (`eval/fixtures/gate0_expected_pins_red.json` /
`gate0_expected_pins_miniwob.json`, the pins this manifest's `audit_paths` point at — the
**non**-`.appserver.json` variant), not receipt-vs-peer. Diagnosed field by field:

- **`config_sha256`, `codex_mcp_list_sha256` (both arms):** the frozen fixture pins these to the
  literal sentinel string `"CONSTRAINT:launch-invocation-dependent-recompute-at-signature"` — by
  the fixture's own documented design, this was never meant to literal-match any real receipt; it's
  a placeholder for a recompute step the amendment build flagged as "PENDING: to be recomputed by
  the orchestrator at actual launch time" and never carried out before this attempt launched. This
  is a **known, pre-existing, structural gap in the pin lifecycle** — identical in both the exec-era
  and the appserver-era fixture (verified: both `gate0_expected_pins_red.json` and
  `gate0_expected_pins_red.appserver.json` pin the identical sentinel for these two fields) — not a
  new problem this attempt introduced, and not a real config divergence.
- **`tool_schema_sha256` (both arms):** a **genuine, not-previously-explained** mismatch. Verified
  by direct hash computation: the receipt's declared `tool_schema_sha256` matches the *actual*
  `mcp-tools.json` captured in the run's own artifacts directory exactly, both arms
  (red: `102e4cb3...c877c3e`; miniwob: `d3eb9d0f...d3d1c17` — zero `artifact_hash_mismatch`
  reported) — so the run is internally self-consistent and the live MCP tool inventory matched the
  allowlist. The mismatch is entirely against the *frozen* expected value captured 2026-07-19
  (red expected `e55bb819...7ffa71`; miniwob expected `6c3d4131...5647e805` — both different from
  the observed hashes above). This report reached that same diagnosis independently, by direct hash
  computation, before cross-checking PR #161 — whose own Arm-R analysis states the identical
  explanation: "PowerShell `ConvertTo-Json` hash vs the app-server's Python `json.dumps`
  serialization of the *same* verified 7-tool inventory."
  I.e., most likely a JSON-serialization-format difference between the original PS 5.1 capture
  recipe and the new Python app-server capture recipe (whitespace/key-order), not an actual change
  in the tool surface — **flagged, not fixed, not certain** (no byte-level diff of the two
  `mcp-tools.json` captures was performed in this report; that would be needed to fully close the
  gap).
- Crucially: **none of these 3 fields are in `CONSTANCY_FIELDS`** (§3's list). The scorer's
  `overall: "CONSTANCY_BREACH"` label is real but orthogonal to the between-arms identity claim —
  it is entirely a pin-freeze/fixture-lifecycle issue on launch-mechanics fields, not evidence that
  the same-brain claim (§3) is false.

**The `source` failures (20 entries) cascade from `_verify_sources()`'s artifact-hash pins, not
from anything wrong with the real files:**
- `red_agent` / `miniwob_agent`: the files **exist** and are well-formed (`agent_metrics.json`,
  read directly in §2c) — but `gate0_paid_source_pins.json`'s `artifact_sha256` for both is the
  literal placeholder `"PENDING_NOT_YET_CAPTURED_paid_attempt_not_run"`, frozen before the paid
  attempt existed. A real file's real hash can never equal that string — this pin was never
  re-frozen after the attempt completed (out of this report's $0/no-fixture-edit scope).
- `wake_boundary`: same shape — `runs/gate0_paid/wake_boundary.json` exists, hash pin is the
  placeholder `"PENDING_NOT_YET_CAPTURED_wake_accounting_not_built"`.
- `miniwob_human`: `runs/gate0_paid_human_baseline/miniwob/human_metrics.json` **does not exist on
  disk** — confirmed by direct listing. This is the expected, pre-registered PENDING state (§7).
- `live_breaker`: `runs/gate0_live_breaker/live_breaker_dry_run_trip.json` **does not exist on
  disk either** — confirmed by direct listing. What *does* exist at `runs/gate0_live_breaker/` is a
  differently-named, differently-shaped file, `combined_credit_ledger.json`
  (`kind: "gate0_combined_credit_ledger"`, not `"live_credit_breaker"`), and its content itself
  looks incomplete for this attempt — `consumed_normalized_credits: 0` with a single `red` entry
  showing `credits_before/after: 0`, which does not match the real ~36.14 combined credits spent
  (§2c). This is a **genuine artifact-tracking gap** in the live-breaker proof chain for this
  specific attempt, flagged here, not investigated or fixed further (out of scope).
- `missing_or_invalid_metric:*` (12 entries, 6 per arm): a pure cascade — `_arm_metrics()` reads
  `verified_sources["metrics"][arm]`, which `_verify_sources()` only populates when **both** that
  arm's `_agent` and `_human` artifact hashes validate; since `red_agent`/`miniwob_agent` (and
  `miniwob_human`) failed their hash checks above, `metrics["red"]`/`metrics["miniwob"]` were never
  populated, so every required key reads as missing. Not a second, independent problem — the same
  root cause reported once more downstream.
- `frozen_seed_hash`: diagnosed, not just flagged. On this Windows checkout,
  `eval/fixtures/gate0_miniwob_paid_seeds.json` materializes with CRLF line endings
  (`b'[\r\n  1000,\r\n  1001,\r\n  1002,\r\n  1003,\r\n  1004\r\n]\r\n'`) even though
  `.gitattributes` declares `eol=lf` for it (confirmed via `git check-attr eol` — the attribute
  itself is correct); this is exactly the Windows `autocrlf` trap the pins file's own
  `_source_frozen_seed_sha256` comment warns about. The raw-bytes hash is
  `8b83d4a8...d1989ce`; **LF-normalizing the same bytes (`\r\n` -> `\n`) yields
  `263aaed1...59e63` — an exact match to the pinned `frozen_seed_sha256`.** The seed *content*
  (`[1000, 1001, 1002, 1003, 1004]`, parsed) is exactly the pinned list — confirmed by direct JSON
  comparison. This is a **local-checkout line-ending artifact on this specific machine**, not a
  content divergence and not something this attempt's launch caused — but it does mean
  `eval.score_gate0._verify_sources()` genuinely fails this check when run from this checkout as-is,
  which is itself worth knowing (the frozen scorer is not currently portable across a Windows
  checkout with `core.autocrlf=true` for this file, despite the `.gitattributes` pin). Not fixed
  here (no fixture/repo-config edit in this $0 pass).

**Bottom line on §4:** the frozen scorer, run exactly as pre-registered with zero deviation, cannot
reach a clean `PASS`/`FAIL_CAPABILITY`/`FAIL_CHEAP` verdict today — it stops at `CONSTANCY_BREACH`
for reasons that are almost entirely pin-freeze bookkeeping (placeholders never updated after the
attempt completed) plus one unexplained-but-self-consistent hash format question, **not** a real
same-brain divergence. The per-component results this report CAN compute honestly are exactly
§§2-3 above, each verified independently of `score_manifest()`.

## 5. Arm W in detail

5/5 episodes played, exactly one terminal row each (no reopens, no duplicate terminals — the
`terminal_not_last_row` failure class never fired), all on task `click-checkboxes`, all
`abandoned == False`. 4/5 at `reward == 1.0`; episode 1 (seed 1001) at `reward == 0.6666...`. 97
primitive actions, 295.594s wall-clock, `$1.02958` / 25.7395 credits — well under the `$2.00`/`50`
Arm W cap alone.

## 6. What genuinely validated (precise, not oversold)

- The app-server launch path (`tools/gate0_appserver_arm.py`, the 2026-07-24 amendment) drove
  **two different world classes** — a Game Boy emulator and a browser DOM environment — with **one
  fixed brain/config identity**, now directly proven by §3's clean `compare_constancy` result
  (first time this check has run).
- **NO_LEAK held on both arms** — zero `leak_failures` in either arm's `audit_codex()` pass (visible
  in §4's verbatim output: `"leak": []`).
- **Cost came in ~5x under the combined bar** ($1.4455 vs $7.00; 36.14 vs 175 credits), with the
  250-credit hard breaker nowhere close.
- **Red beat the human baseline on both wall-clock and actions** (127.75s vs 233.288s; 142 vs 271
  actions) — even though the task predicate itself was not satisfied (§2a, and PR #161 in depth).
- **MiniWoB solved 4/5 held-out seeds perfectly** (reward 1.0, clean single terminal, not abandoned).

## 7. The two misses, mechanically — different failure modes

- **Red: a premature-stop / measurement-shaped miss.** The brain declared victory
  ("Obtained Charmander... defeated Gary...") and stopped acting once it believed the task done, so
  the anti-false-victory tail the frozen predicate requires (10 consecutive `in_battle == 0` rows,
  then movement) never had the chance to materialize in the oracle. The task was very likely
  actually accomplished in-game; it is **unproven by measurement**. Full diagnosis: PR #161.
- **MiniWoB: a genuine partial-capability miss.** Episode 1 (seed 1001) terminated with
  `done = True`, `abandoned = False`, but `reward = 0.6666...` — not a measurement artifact, a real
  scored outcome indicating some checkboxes were left wrong or unchecked on that one held-out seed.
- These are **independent failure modes** — one is an artifact of when the agent stopped acting
  relative to what the predicate demands to see; the other is the predicate correctly catching an
  actual partial performance. Fixing one does not fix the other, and neither should be waved away
  as "basically the same problem."

## 8. Honest bounds — what this does NOT license claiming

- **Capability is not proven**, on either arm, by the frozen bar. "Very likely accomplished
  in-game" (Red) and "4/5 perfect, 1 partial" (MiniWoB) are both short of the pre-registered PASS
  condition.
- **MiniWoB's `≤2×human` wall-clock/action bars are UNCOMPUTABLE today** —
  `human_wall_clock_s`/`human_primitive_actions` are `null` in `agent_metrics.json` (§2b/§4), because
  the paid-seed (1000-1004) human baseline has never been played. Until it exists, Arm W's
  `_arm_metrics()` source check can never even evaluate the `2x` caps, regardless of the predicate
  result.
- **Constancy (§3) proves identity, not quality.** Do not read "clean `compare_constancy`" as "the
  agent performed comparably well in both worlds" — it performed a genuine partial-success task in
  one and an unproven-by-measurement one in the other. The claim §3 supports is narrower and purely
  about launch/brain identity.
- **`score_manifest()`'s `CONSTANCY_BREACH` (§4) should not be read as a same-brain divergence** —
  see §4's diagnosis — but neither should its underlying pin-freeze gaps be considered closed. They
  are real, open, and would block a clean automated re-score even if both predicates had passed.
- **The live-breaker proof artifact for this specific attempt is missing** (§4) — the mechanism may
  well have worked (cost came in far under the hard cap regardless), but the pinned proof file
  (`live_breaker_dry_run_trip.json`) is not present to independently confirm it armed and held for
  this run.

## 9. What David must do next

1. **Play the paid-seed MiniWoB human baseline**, on the exact held-out seeds, only now that the
   agent's attempt is banked (per design-doc discipline — "DEV-seed human runs are readiness
   estimates, never the final denominator"), same container/mount shape as the DEV rig
   (`reports/2026-07-21-gate0-readiness-final-v2.md` §6 step 4, `DAVID_BASELINES.md`):
   ```
   docker run -it --rm -v "$PWD/tools:/app/tools" -v "$PWD/eval:/app/eval" -v "$PWD/runs:/app/runs" \
       --entrypoint python miniwob-mcp-world -m tools.capture_gate0_baseline_miniwob \
       --mode paid_gate0 --i-am-human
   ```
   (writes `runs/gate0_paid_human_baseline/miniwob/human_metrics.json`, the exact path
   `gate0_paid_source_pins.json`'s `artifact_paths.miniwob_human` already names). Once captured,
   **freeze** its hash into `artifact_sha256.miniwob_human` (currently the placeholder
   `PENDING_NOT_YET_CAPTURED_paid_seed_human_replay_tool_not_built`) — a separate, small,
   reviewed fixture-update PR, not done here. Only then do the `≤2×human` bars for Arm W and the
   full frozen `score_manifest()` verdict become computable.
2. Separately, someone should re-freeze `gate0_paid_source_pins.json`'s `artifact_sha256` for
   `red_agent`/`miniwob_agent`/`wake_boundary` against the now-real files, and resolve the
   `live_breaker` artifact-path gap (§4) — both are fixture/pin maintenance, out of this report's
   $0/no-fixture-edit scope, flagged for a follow-up PR.

## 10. vNext candidates — NOT decided, David's call

- **(a) Fresh pre-registration (v2), both arms**, whose brief forbids declaring the task done until
  state is stable / requires a few confirming actions after the agent believes it's finished. Note:
  the task text is a byte-frozen pin (`task_sha256`, both `PIN_FIELDS` and part of what a re-launch
  must reconstruct) — this needs a **new** pre-registration and a **re-freeze**, not a brief-only
  tweak under the current one.
- **(b) Bank as-is** and treat this paired attempt as the honest proof-floor baseline for Gate 0 —
  the first real evidence that the harness itself works end-to-end across two world classes, even
  though capability is unproven.
- **(c) Explicitly mark as METHODOLOGICALLY FORBIDDEN** any post-hoc loosening of the frozen
  predicates (`_red_success`, `_miniwob_success`) to retroactively convert either of these two
  results into a pass. Both misses are real, mechanically diagnosed above; loosening the bar after
  seeing the result is exactly the thing pre-registration exists to prevent.

None of (a)/(b)/(c) is selected by this report — they are listed for David to choose from, per the
gate-methodology rule that escalation-picking is never delegated to the report author.
