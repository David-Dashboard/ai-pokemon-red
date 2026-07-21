# Gate 0: final readiness stamp v2 + signature package (supersedes PR #124) — 2026-07-21

**Supersedes:** `docs/gate0-stamping` (PR #124), which predates PR #125's Cheap = cost-per-task
amendment. This report is against current `main` at the frozen commit below, where the gate **can
now `PASS`**.

**Frozen commit this report is against:** `61abba7f295205d25511d1a26897d83078d5eb99` (merge of PR
#125, `feat/gate0-wake-accounting`). Worktree: own worktree at `docs/gate0-readiness-final-v2`,
branched from `origin/main` (fetched fresh); no existing checkout was written to. Human baselines
were read read-only from `ai-pokemon-red-prereg/runs/gate0_human_baseline/`; the pre-existing
`red-v4`/`miniwob-v3` free-handshake receipts were read read-only from the primary checkout
(`ai-pokemon-red/runs/gate0_readiness_2026-07-14/`) — see "A note on what this session could not
run," below, for why fresh receipts were read rather than regenerated.

**No `codex exec`, paid path, or held-out seed was touched at any point in this work.**

---

## 1. Nine-precondition status table (honest, no rounding)

| # | Precondition | Status | Evidence |
|---|---|---|---|
| 1 | R0/W0/C0 readiness all `GO` | **MET (mechanism-level)** | All of #2–#7,#9 below are now clear. `eval/score_gate0.py::score()` mechanically reaches `overall=PASS`/`readiness=GO` given clean, in-cap inputs — proven this session (§3, synthetic manifest). **Caveat:** no live paid or DEV-mode agent transcript has been produced (that requires an actual Codex exec, itself gated on David's signature + precondition 8) — this is proof the gate's PASS path is reachable, not a banked capability verdict. `LEDGER.md`'s literal `R0/W0/C0: INSUFFICIENT_SOURCE` text is stale (predates the 2026-07-21 human-baseline captures, PR #122's launch wiring, and PR #125's Cheap-basis amendment); this PR's LEDGER/HANDOFF update (§6) corrects it. |
| 2 | `eval/score_gate0.py` lands on `main` | **MET** | Present at `61abba7`; imported and exercised directly this session (§3, §4). |
| 3 | Frozen expected-pins JSON, independent of any receipt | **MET** | `eval/fixtures/gate0_expected_pins_red.json` / `_miniwob.json`, `schema_version=2`, all 20 `PIN_FIELDS` present, frozen 2026-07-19 against commit `b45b47f`, `planned_model` updated 2026-07-21 to `gpt-5.6-sol` per David's decision. Each file's own header states the INDEPENDENCE LAW (no value copied from an observed receipt). |
| 4 | Live breaker dry-run TRIP receipt | **MET** | Component: `reports/2026-07-19-gate0-live-breaker-dry-run.md` (deterministic dry-run TRIP, hash `27538b25...`). Full 4a–4d wiring: `reports/2026-07-21-gate0-wired-breaker-trip.md` — `-PaidExec`, `Confirm-PaidExecSignature`, `Invoke-BreakerSupervisedExec` (kill-on-close Job Object + unconditional `taskkill /T /F`), combined cross-arm ledger, all merged via PR #122 (`99c9fa7`, posted-review-gated per project convention). Wired-path zero-spend stub-emitter TRIP receipt: `status=PASS`, `credits_at_trip=252.0`, `child_still_alive_after_kill=false`. That report's own text says "pending re-review" because it was written mid-review; PR #122 **is** that reviewed revision and is already merged onto `main` — so precondition 4 is MET at current HEAD, not still pending. |
| 5 | Blank-agent wipe line | **MET (mechanism); unexercised in a live paid context** | Every `-OutputDir` must not exist or be empty (`tools/run_gate0_codex.ps1` `Test-Path`/`Get-ChildItem` guard); a fresh, isolated `codex-home` is created per run; `history.persistence="none"` and `features.memories=false` are forced in both `$BrainConfigText` and the effective `$Overrides` array. Verified present verbatim in the real `red-v4`/`miniwob-v3` `brain-config.toml` files this session. No live paid exec has run yet, so the wipe has never been exercised end-to-end against a real model call. |
| 6 | Human baselines recorded (who/when) | **MET** | Red: David, 2026-07-21, Option-A reconstruction (`reports/2026-07-21-gate0-red-baseline-reconstruction.md`) — `wall_clock_s=233.288`, `primitive_actions=271`, `success=true`. MiniWoB: David, 2026-07-21, 5 fresh DEV episodes, seeds `0..4`, `wall_clock_s=224.83`, `primitive_actions=18`, `success=true` (5/5). Both files re-verified present and loadable this session (§2). **Gap flagged, not fixed here:** `eval/fixtures/gate0_{readiness_dev,paid}_source_pins.json`'s `artifact_sha256.red_human`/`miniwob_human` are still the literal placeholder string `PENDING_NOT_YET_CAPTURED_...` — not yet re-frozen against these real captured files. Freezing those two hashes is a distinct, separate follow-up (out of this PR's DO list); flagged here so it isn't silently missed. |
| 7 | Codex CLI executability + auth receipt | **MET** | `codex --version` → `codex-cli 0.144.3`; `codex login status` → `Logged in using ChatGPT`; `OPENAI_API_KEY`/`CODEX_API_KEY` both unset — all reconfirmed this session. `Resolve-CodexExecutable` resolves to exactly one `.exe`. |
| 8 | Codex-pool quota check | **LAUNCH-TIME (by design)** | Must be confirmed immediately before **each** arm's launch (250-normalized-credit headroom); cannot be pre-satisfied ahead of the actual launch moment. See launch checklist, §6. |
| 9 | World images rebuilt from a clean checkout, post-merge | **MET** | `gb-mcp-world` → `sha256:5bfabc7513ce037ed077e955fd34445ef564a7b51037bd7fdddeef0cdb900d00`; `miniwob-world` → `sha256:8bb3358e1421dc97c72c07809fdef048f63d64bdfddb170c4d0188337fe6fd0f` — both reconfirmed via `docker image inspect` this session, exactly matching the frozen `world_image_id` pins. `host_code_sha256 == image_code_sha256` parity confirmed in both `red-v4`/`miniwob-v3` receipts. |

**Net:** 1–7, 9 MET; 8 is LAUNCH-TIME (quota). The gate can now `PASS` — proven mechanically in §3.

---

## 2. Human baselines — re-verified

Both files read from `ai-pokemon-red-prereg/runs/gate0_human_baseline/` (gitignored, read-only,
per the frozen source-pin loader's expected paths):

| Arm | Path | `wall_clock_s` | `primitive_actions` | `success` | SHA-256 (recomputed this session) |
|---|---|---|---|---|---|
| red | `runs/gate0_human_baseline/red/human_metrics.json` | `233.288` | `271` | `true` | `5144a5b36a29453c5f07ceba8336f3752055e0437e80f50d61418d61be686264` |
| miniwob | `runs/gate0_human_baseline/miniwob/human_metrics.json` | `224.83` | `18` (5/5 episodes) | `true` | `32b0c021be2a03215feca51e74a56285a561791f777a6300290860dfaf8f7dcf` |

Both load cleanly as JSON (`schema_version=1`, `role="human"`, `mode="readiness_dev"`), matching the
shape `eval.score_gate0._verify_sources` expects. As noted in §1 row 6, the source-pins files' own
`artifact_sha256` entries for these two keys are still unfrozen placeholders — the values above are
this session's independent recomputation, not yet written back into the pins file.

---

## 3. Readiness re-run end-to-end (`tools/check_gate0_codex.py`)

Ran against the **fresh** `red-v4`/`miniwob-v3` receipts — the latest free-handshake receipts on
disk, produced 2026-07-21 with the now-pinned model `gpt-5.6-sol` against the rebuilt images
(`reports/2026-07-21-gate0-fresh-handshakes.md`) — using this branch's current merged
`eval/fixtures/gate0_expected_pins_{red,miniwob}.json` and scorer code. No transcript exists for
either receipt (free handshake only, no `codex exec` ever ran), so a nonexistent transcript path
was passed deliberately — this correctly reports `transcript_unreadable`/`transcript_empty`, an
artifact of "no paid run happened yet," not a new finding.

**Red (verbatim):**
```json
{"accounting_failures": ["no_observable_token_usage"], "arm": "red", "constancy_failures": ["pin_mismatch:config_sha256", "pin_mismatch:codex_mcp_list_sha256"], "leak_failures": ["transcript_unreadable", "transcript_empty"], "no_leak": "NO_LEAK", "overall": "NO_LEAK", "peer_constancy": "PASS", "primitive_action_events": 0, "run_failures": [], "schema_version": 2, "token_usage": {"cached_input_tokens": 0, "input_tokens": 0, "output_tokens": 0, "reasoning_output_tokens": 0}, "token_usage_events": 0, "wake_accounting": "INSUFFICIENT_WAKES", "wakes": null}
```
Exit code: `1`.

**MiniWoB (verbatim):**
```json
{"accounting_failures": ["no_observable_token_usage"], "arm": "miniwob", "constancy_failures": ["pin_mismatch:config_sha256", "pin_mismatch:codex_mcp_list_sha256"], "leak_failures": ["transcript_unreadable", "transcript_empty"], "no_leak": "NO_LEAK", "overall": "NO_LEAK", "peer_constancy": "PASS", "primitive_action_events": 0, "run_failures": [], "schema_version": 2, "token_usage": {"cached_input_tokens": 0, "input_tokens": 0, "output_tokens": 0, "reasoning_output_tokens": 0}, "token_usage_events": 0, "wake_accounting": "INSUFFICIENT_WAKES", "wakes": null}
```
Exit code: `1`.

**Reading this:** `constancy_failures` reduces to exactly the two fields the pin files themselves
mark `CONSTRAINT:launch-invocation-dependent-recompute-at-signature` (`config_sha256`,
`codex_mcp_list_sha256` — both embed the launch `OutputDir`'s absolute mount paths, so no
pre-frozen value can ever match them by construction). All 18 other `PIN_FIELDS` match, including
`planned_model=gpt-5.6-sol`, `world_image_id`, and `host_code_sha256==image_code_sha256`.
`peer_constancy: "PASS"` for both arms — every `CONSTANCY_FIELDS` value is identical between the
red and miniwob receipts. `overall="NO_LEAK"` is the correct, expected reading for a receipt with no
real transcript, not a defect.

Receipt hashes reconfirmed this session (cross-checked against
`reports/2026-07-21-gate0-fresh-handshakes.md`, byte-for-byte match):
`red-v4/handshake-receipt.json` = `6051fcb759509cdf7adcd3ad90e93737d3e4081ef9ad0b7c36fc8149bc64cb5a`;
`miniwob-v3/handshake-receipt.json` = `b80af26a3986748a96c78c13cf95e85f74d60ae9b87c9d270fdcaa7ca96b9325`.

---

## 4. Proof the gate can now `PASS` (synthetic manifest through `eval/score_gate0.py::score()`)

Constructed the minimal synthetic **successful** manifest directly against `score()` (bypassing
`score_manifest()`'s on-disk pinned-path resolution, which is orthogonal to whether the scorer's
own PASS path is reachable): clean audits (no leak/constancy/run/accounting failures,
`peer_constancy: "PASS"`), a red oracle trace satisfying `_red_success` (fresh party 0→1, trainer
battle, ten-row sustained exit with HP never zero, free movement after), a miniwob oracle trace
with 5 successful `click-checkboxes` terminals at the paid seeds `1000..1004`, and metrics built
from the **real banked human baselines** (`233.288`/`271` red, `224.83`/`18` miniwob) with agent
numbers safely under the `2x` capability bar and under the Cheap cost/credit caps.

**Successful case — verdict (verbatim):**
```json
{
  "cheap_basis": "cost_per_task",
  "failures": {"capability": [], "cheap": [], "constancy": [], "infra": [], "leak": [], "source": []},
  "overall": "PASS",
  "readiness": "GO",
  "schema_version": 1,
  "spend_usd": 4.0,
  "wake_accounting": {
    "detail": {},
    "evidence": "reports/2026-07-21-gate0-wake-grounding.md",
    "reason": "no_per_model_decision_observable_in_codex_jsonl_stream",
    "status": "DEFERRED"
  }
}
```
**`overall=PASS`, `readiness=GO`, wakes deferred and non-gating** — exactly the claim this PR needed
to prove.

**Over-cost variant** (identical inputs, red arm `cost_usd` raised from `3.00` to `6.00`, over the
`$5.00` per-arm cap) — **verdict (verbatim):**
```json
{
  "cheap_basis": "cost_per_task",
  "failures": {"capability": [], "cheap": ["red:arm_cap"], "constancy": [], "infra": [], "leak": [], "source": []},
  "overall": "FAIL_CHEAP",
  "readiness": "NO_GO",
  "schema_version": 1,
  "spend_usd": 7.0,
  "wake_accounting": {"detail": {}, "evidence": "reports/2026-07-21-gate0-wake-grounding.md", "reason": "no_per_model_decision_observable_in_codex_jsonl_stream", "status": "DEFERRED"}
}
```
The cost bar bites exactly as designed: `FAIL_CHEAP`/`NO_GO` on a single-arm cost overrun, with
every other axis still clean.

---

## 5. Signature-time computations (current `main`, `61abba7`)

### 5a. The two launch-invocation-dependent hashes (`config_sha256`, `codex_mcp_list_sha256`)

These **cannot** be generically pre-pinned — both embed the launch invocation's absolute
`-OutputDir`/mount paths (documented in each expected-pins file's own
`_source_config_sha256`/`_source_codex_mcp_list_sha256`). This session could not itself invoke
`tools/run_gate0_codex.ps1` (see the note at the end of this report), but the recipe is
demonstrated end-to-end against the existing `red-v4`/`miniwob-v3` free-handshake receipts (same
recipe the launcher runs, cross-verified this session by independently re-hashing the saved
`launch/.codex/config.toml` and `codex-mcp-list.json` files byte-for-byte):

| Arm | `config_sha256` (for that receipt's own `OutputDir`) | `codex_mcp_list_sha256` |
|---|---|---|
| red (`red-v4`) | `e7c6b3cdd391aa760818a64862e4e410583322961f8d3ad0b971b78d1f299c00` | `891c45ef39d14a49d570a7b9d413858b86288e07a7cfd46be9e686b51461fcb1` |
| miniwob (`miniwob-v3`) | `760cdcf307c8b6ebb4e424223b37b64e4aab4e1c8e414718ec96895363f0264b` | `41c12ca4121035c215c04dcf7803640d9f5873486dae2b8beb93d2eca77749f5` |

**At actual signature time**, whoever launches must re-run the free-handshake path
(`tools/run_gate0_codex.ps1 -Arm <red|miniwob> -Model gpt-5.6-sol -OutputDir runs/gate0_paid/<arm>`,
no `-PaidExec`) from the exact reviewed/frozen checkout, and read `config_sha256`/
`codex_mcp_list_sha256` straight off that run's own `handshake-receipt.json` — the values above are
a worked proof of the recipe, not the final signature pins (those depend on the real
`runs/gate0_paid/<arm>` `OutputDir`, per `eval/fixtures/gate0_paid_source_pins.json`'s
`audit_paths`).

### 5b. The four safety-critical file hashes (canonical git blob at HEAD)

`tools/run_gate0_codex.ps1`'s `$Gate0SafetyCriticalFiles` currently names exactly these four files
(confirmed by reading the current script — unchanged in count since PR #122):

Recipe: `git diff --quiet HEAD -- <path> && git cat-file blob HEAD:<path> | sha256sum` (working tree
confirmed clean for all four at `61abba7` before hashing).

| File | Signature field | Canonical HEAD-blob SHA-256 |
|---|---|---|
| `tools/run_gate0_codex.ps1` | `expected_launcher_sha256` | `859b4c5d0bb5e98c027418cef8187003f31c63fe97b4283bbe1ee2c803284a3e` |
| `tools/gate0_credit_breaker.py` | `expected_credit_breaker_sha256` | `eb77f32253a699bfb2dbd5b784679d85fe4e8f15e4ae4323fbf8b4377b82e8db` |
| `tools/gate0_credit_accountant.py` | `expected_credit_accountant_sha256` | `03ee8d9c91821ab000d6c8036d516e4ee822b32a69fd222f1ef8b44c0bb6b3a9` |
| `tools/gate0_codex_credit_rate.py` | `expected_credit_rate_sha256` | `a34cc006dc3c3d36084545ed7ece2e9f67e37ea4f425deac060c486bf49a649f` |

These four values are **commit-pinned**, not launch-invocation-dependent — they hold for any launch
at commit `61abba7f295205d25511d1a26897d83078d5eb99` and only need recomputing if David signs a
*different* commit.

---

## 6. SIGNATURE PACKAGE FOR DAVID

The exact `eval/fixtures/gate0_signature.json` shape (schema per
`eval/fixtures/gate0_signature.example.json`), **one signed instance per arm** (the file is
per-launch — sign, launch Arm R, then re-sign for Arm W; see launch checklist below). Everything
computed this session is filled in; every field David alone can supply is marked `<-- DAVID`.

```json
{
  "schema_version": 1,
  "frozen_commit": "<-- DAVID: the commit you are signing at, e.g. 61abba7f295205d25511d1a26897d83078d5eb99 if signing against this report unchanged, or a later commit if more merges land first>",
  "arm": "<-- DAVID: \"red\" for the first launch, \"miniwob\" for the second (Arm R launches first)>",
  "planned_model": "gpt-5.6-sol",
  "signed_by": "<-- DAVID: your name>",
  "signed_at": "<-- DAVID: ISO 8601 timestamp at the moment you sign>",
  "expected_config_sha256": "<-- DAVID: recompute-at-signature -- run tools/run_gate0_codex.ps1 -Arm <arm> -Model gpt-5.6-sol -OutputDir runs/gate0_paid/<arm> (no -PaidExec) from the exact reviewed checkout, then copy handshake-receipt.json:config_sha256. Worked example this session for a DIFFERENT OutputDir: red e7c6b3cd..., miniwob 760cdcf3... -- do not reuse these, they are OutputDir-specific.>",
  "expected_codex_mcp_list_sha256": "<-- DAVID: same run, handshake-receipt.json:codex_mcp_list_sha256. Worked example (different OutputDir, do not reuse): red 891c45ef..., miniwob 41c12ca4...>",
  "expected_launcher_sha256": "859b4c5d0bb5e98c027418cef8187003f31c63fe97b4283bbe1ee2c803284a3e",
  "expected_credit_breaker_sha256": "eb77f32253a699bfb2dbd5b784679d85fe4e8f15e4ae4323fbf8b4377b82e8db",
  "expected_credit_accountant_sha256": "03ee8d9c91821ab000d6c8036d516e4ee822b32a69fd222f1ef8b44c0bb6b3a9",
  "expected_credit_rate_sha256": "a34cc006dc3c3d36084545ed7ece2e9f67e37ea4f425deac060c486bf49a649f",
  "credit_rate_pin": {
    "model": "gpt-5.6-sol",
    "rate_source": "<-- DAVID: see recipe below -- must be a real citation, not a guess>",
    "credits_per_usd": "<-- DAVID: see recipe below -- must satisfy 1 <= credits_per_usd <= 1000>",
    "usd_per_input_token": "<-- DAVID: see recipe below -- 0, or 1e-8 <= x <= 1e-2>",
    "usd_per_cached_input_token": "<-- DAVID: see recipe below -- 0, or 1e-8 <= x <= 1e-2>",
    "usd_per_output_token": "<-- DAVID: see recipe below -- 0, or 1e-8 <= x <= 1e-2>"
  },
  "notes": "<-- DAVID: optional signature-time context>"
}
```

### `credit_rate_pin` — exact recipe to read it from the ChatGPT/Codex usage page

`tools/gate0_codex_credit_rate.py`'s own investigation (2026-07-21, zero-spend, reading only
pre-existing local session rollouts) already established: **Codex CLI itself does not hand back a
usable per-token dollar rate for a ChatGPT-subscription auth session** —
`rate_limits.credits` is a balance/entitlement object (`{"has_credits": false, "unlimited": false,
"balance": "0"}` observed on this Plus-plan account), not a per-turn spend figure. So the rate
cannot be read off a Codex JSONL stream; it must come from the account's own usage/plan page:

1. Go to the ChatGPT/OpenAI account's usage or plan page (e.g. the ChatGPT web app's Settings →
   your plan, or `platform.openai.com/usage` if the Plus plan exposes an equivalent Codex/API usage
   view) while logged in as the account `codex login status` reports (`Logged in using ChatGPT`).
2. Find the number that prices the pinned model `gpt-5.6-sol`: either (a) an explicit $/token or
   $/million-token rate if the page shows one, or (b) the plan's credit-to-dollar equivalence (the
   design doc's own prior pin was "25 credits = $1.00" — confirm whether that still holds for this
   plan/model, or read the plan's current stated number).
3. Convert whatever units the page shows into the four required fields: `usd_per_input_token`,
   `usd_per_cached_input_token`, `usd_per_output_token` (each in **dollars per single token**, not
   per thousand or per million — divide accordingly), and `credits_per_usd` (credits per one
   dollar).
4. Write `rate_source` as a citation, not a guess: the exact page URL/name and the date you read it
   (e.g. `"ChatGPT Settings > My Plan, observed 2026-07-XX: <exact text/number shown>"`).
5. Before signing, sanity-check every nonzero `usd_per_*_token` field falls in
   **`[1e-8, 1e-2]` dollars per token** (i.e. `$0.01`–`$10,000` per million tokens — six orders of
   magnitude around real 2026-era frontier pricing; PR #122 Finding 3), and `credits_per_usd` falls
   in **`[1, 1000]`** credits per dollar. A field pinned to exactly `0` is allowed (a genuinely free
   tier), but a nonzero value outside those bands is refused by
   `tools/gate0_codex_credit_rate.py::load_credit_rate_pin` before any process spawns — if your
   observed number falls outside the band, stop and re-check units before signing (the bands exist
   specifically to catch a per-1K/per-1M-token price accidentally entered as per-token, or vice
   versa).

### Launch checklist

1. Confirm precondition 8 (quota): immediately before **each** arm's launch, check remaining
   ChatGPT/Codex subscription quota is sufficient for that arm's 250-normalized-credit hard ceiling.
   If insufficient, **wait** for the pool reset — do not switch brain/pool (that would require a new
   pre-registration).
2. **Arm R (red) launches first.** Sign a `gate0_signature.json` with `"arm": "red"`, run
   `tools/run_gate0_codex.ps1 -Arm red -Model gpt-5.6-sol -OutputDir runs/gate0_paid/red -PaidExec`.
3. Only after Arm R's attempt is banked (verdict printed, receipt saved — never an informal rerun):
   re-check quota, re-sign `gate0_signature.json` with `"arm": "miniwob"` (new `expected_config_sha256`/
   `expected_codex_mcp_list_sha256` for that arm's own handshake), and launch Arm W
   (`-OutputDir runs/gate0_paid/miniwob`). The combined credit ledger
   (`runs/gate0_live_breaker/combined_credit_ledger.json`) carries Arm R's consumed total into Arm
   W's budget check automatically — do not pass `-ResetCombinedLedger` for Arm W.
   "If Arm R alone reaches the combined ceiling, do not launch Arm W."
4. Score with `eval/score_gate0.py score_manifest()` against the real `runs/gate0_paid/<arm>`
   artifacts once both arms are banked. Bank the printed verdict — no informal rerun regardless of
   outcome.

---

## 7. A note on what this session could not run

This session attempted to regenerate fresh free-handshake receipts by invoking
`tools/run_gate0_codex.ps1` directly (no `-PaidExec` — the same $0, no-model-call path documented
throughout this repo). That invocation was blocked by this sandbox's own auto-mode permission
classifier (a harness-level restriction, separate from and in addition to this project's own
safety rules) before any process spawned. This turned out to be unnecessary: `reports/2026-07-21-
gate0-fresh-handshakes.md` (already on `main`) documents that `red-v4`/`miniwob-v3` were already
produced earlier the same day, exactly with the now-pinned model and rebuilt images — this report
uses those, read-only, from the primary checkout, and independently cross-verified every hash they
report (receipt hash, `config_sha256`, `codex_mcp_list_sha256`) rather than trusting the prose.
Flagging this here for transparency: if a future session needs a **new** free-handshake attempt
(e.g. after another merge changes the pins), running `tools/run_gate0_codex.ps1` may need to happen
outside this kind of sandboxed session, or with the classifier restriction lifted for that action.

---

## 8. Verification

Full suite (`UV_PROJECT_ENVIRONMENT=.venv-win-restamp UV_NATIVE_TLS=true uv run --frozen pytest -q`),
run against this branch's own worktree at `61abba7` plus this report — tail:

```
1386 passed, 16 skipped in 54.24s
```
