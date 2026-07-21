# Gate 0 final readiness stamping + signature package — 2026-07-21

## Verdict up front

**Gate 0 is NOT fully launch-ready.** Eight of the nine pre-reg preconditions are `MET`; one
(#8) is inherently launch-time. But this stamping pass found a **new, closable-at-$0 gap that the
prior reports did not call out as launch-blocking**: `tools/check_gate0_codex.py::audit()`
hardcodes `"wakes": None` / `"wake_accounting": "INSUFFICIENT_WAKES"` **unconditionally** — this
is not "unobserved until a real run," it is code that has never been written. No tool anywhere in
the repo produces the `agent_metrics.json` / `wake_boundary.json` artifacts
`eval/score_gate0.py::_verify_sources()` requires for a paid-mode score (confirmed:
`eval/fixtures/gate0_paid_source_pins.json` itself says
`"wake_boundary": "PENDING_NOT_YET_CAPTURED_wake_accounting_not_built"`). Traced through
`eval/score_gate0.py:331-332` (`elif failures["source"]: verdict, readiness = "INSUFFICIENT_DATA",
"INSUFFICIENT_SOURCE"`): **a genuinely successful paid run, launched today, would still score
`INSUFFICIENT_DATA`/`INSUFFICIENT_SOURCE` — not `PASS` — regardless of brain performance.**
Signing and launching before this is fixed risks burning the one pre-registered attempt on a
scorer-side gap, not a real result. See "New finding" below for the full ruling and evidence.

Session-tooling note: this session's Bash/PowerShell auto-mode classifier refused to run
`tools/run_gate0_codex.ps1` (spawns `docker`/`codex.exe` subprocesses) twice, from two different
tool paths. Per safety-invariants law 9, that denial was not routed around. Everything below that
did **not** require that specific script — git introspection, the 4 safety-file hashes, the full
pytest suite, hash-verifying the human baselines — was completed directly.

## 1. The 9-precondition table (`reports/2026-07-18-gate0-prereg.md`), re-verified against `main`@`99c9fa7`

| # | Precondition | Status | Evidence (this pass, 2026-07-21) |
|---|---|---|---|
| 1 | R0/W0/C0 readiness all `GO` | **SUPERSEDED** by items 2-9 below (finer-grained than the 2026-07-14 R0/W0/C0 framing) | R0 (Red predicate + human baseline) and W0 (MiniWoB predicate + DEV seeds + human baseline) are each covered by rows 3/6/9 below; C0 is covered by rows 3/4/5/7/9 plus the **new wake-accounting gap** (not `GO` — see below) |
| 2 | `eval/score_gate0.py` lands on `main` | **MET** | present at `HEAD 99c9fa7`; imported cleanly by `tools/check_gate0_codex.py` consumers and the test suite (`tests/test_score_gate0.py`); full suite green (below) |
| 3 | Frozen expected-pins JSON, independent of the observed receipt | **MET** | `eval/fixtures/gate0_expected_pins_{red,miniwob}.json`, frozen 2026-07-19, model pin updated 2026-07-21 (`gpt-5.6-sol`); INDEPENDENCE LAW documented per-field in `eval/fixtures/gate0_expected_pins.SOURCES.md`. Re-verified fresh today: `world_mcp.py` canonical HEAD-blob sha256 `967866ab5ddcfcef17747aab1d83070a95a32c2cb05bc0b6252defce7b519fc9` and `core/miniwob_world.py` `f98b0dc9846bff0fceb96c8f77eee8b4261b9db894abd793a8d7b1145a23ce54` — both match the pin exactly, computed on a clean tree at `99c9fa7` |
| 4 | Live breaker dry-run TRIP receipt | **MET** (credit/cost side only — see new finding for the separate wake-count side) | PR #118 (4a-4d) + PR #122 review-fix round (4 MAJORs, all fixed) merged into `main` at `99c9fa7`: `tools/gate0_credit_breaker.py`, `tools/gate0_credit_accountant.py`, `-PaidExec`/`Confirm-PaidExecSignature`/Job-Object kill/combined ledger all landed; wired-path TRIP receipt against a zero-spend stub emitter banked in `reports/2026-07-21-gate0-wired-breaker-trip.md` |
| 5 | Blank-agent wipe line (Codex form) | **MET** | fresh empty `OutputDir` + new isolated `codex-home` per launch, `history.persistence="none"`, `features.memories=false` forced (`tools/run_gate0_codex.ps1`); mechanism exercised across every free-handshake run to date, including this session's parity checks |
| 6 | Human baselines recorded (who/when) | **MET** | see §2 below — both artifacts exist, load, hash-verified |
| 7 | Codex CLI executability + auth receipt | **MET** | re-confirmed fresh this session: `codex --version` → `codex-cli 0.144.3`; `codex login status` → "Logged in using ChatGPT"; `OPENAI_API_KEY`/`CODEX_API_KEY` both unset |
| 8 | David's Codex-pool quota check (immediately before EACH arm's launch) | **LAUNCH-TIME, by design** | cannot be pre-verified by any session; see launch checklist |
| 9 | World images rebuilt from a clean checkout after #114, C0 parity | **MET** | re-confirmed fresh this session: `docker image inspect gb-mcp-world` → `sha256:5bfabc7513ce037ed077e955fd34445ef564a7b51037bd7fdddeef0cdb900d00`; `miniwob-world` → `sha256:8bb3358e1421dc97c72c07809fdef048f63d64bdfddb170c4d0188337fe6fd0f` — both match the frozen pins exactly; host/image code parity re-verified (row 3) |

## 2. Human baselines (precondition 6) — both loaded and hash-verified

Both artifacts live at `runs/gate0_human_baseline/` (gitignored, in the primary checkout
`ai-pokemon-red-prereg`, read read-only this session). Both load cleanly and carry the fields
`eval/score_gate0.py`'s frozen source-pin loader (`_verify_sources`) requires.

| Arm | player | wall_clock_s | primitive_actions | result | sha256 (this pass, freshly computed) |
|---|---|---:|---:|---|---|
| Red | David | 233.288 | 271 | success (Option-A reconstruction, `reports/2026-07-21-gate0-red-baseline-reconstruction.md`) | `5144a5b36a29453c5f07ceba8336f3752055e0437e80f50d61418d61be686264` |
| MiniWoB | David | 224.83 | 18 | 5/5 reward, played live | `32b0c021be2a03215feca51e74a56285a561791f777a6300290860dfaf8f7dcf` |

Corroborating facts checked: Red's `rom_sha256` (`0602291f922443faf9d6b3a31948e37607a5f487ed8927892f926f86f4105700`)
and `savestate_sha256` (`a968b0b35cf49892e49178766f0e5ad7d38b689b0f1c4e248ceed4eea7d112ef`) inside
`human_metrics.json` were independently reproduced this session by hashing the actual
`roms/PokemonRed.gb` and `runs/red_start.state` files — exact match. Note: these paths currently
sit under `eval/fixtures/gate0_readiness_dev_source_pins.json`'s `red_human`/`miniwob_human`
pointers as the intended sources for a future scored run, per `DAVID_BASELINES.md`.

## 3. Signature-time hashes — computed where possible, quoted verbatim

### 3a. The 4 safety-critical file hashes (canonical git-blob-at-HEAD, PR #122 Finding 1)

Computed fresh this session directly via `git diff --quiet HEAD -- <path>` (clean tree confirmed)
+ `git cat-file blob HEAD:<path> | sha256sum`, at `main`@`99c9fa7` on branch `docs/gate0-stamping`
— no launcher subprocess needed for these, so the tool-permission block above did not affect them:

| Signature field | File | sha256 (frozen commit `99c9fa7`) |
|---|---|---|
| `expected_launcher_sha256` | `tools/run_gate0_codex.ps1` | `859b4c5d0bb5e98c027418cef8187003f31c63fe97b4283bbe1ee2c803284a3e` |
| `expected_credit_breaker_sha256` | `tools/gate0_credit_breaker.py` | `eb77f32253a699bfb2dbd5b784679d85fe4e8f15e4ae4323fbf8b4377b82e8db` |
| `expected_credit_accountant_sha256` | `tools/gate0_credit_accountant.py` | `03ee8d9c91821ab000d6c8036d516e4ee822b32a69fd222f1ef8b44c0bb6b3a9` |
| `expected_credit_rate_sha256` | `tools/gate0_codex_credit_rate.py` | `a34cc006dc3c3d36084545ed7ece2e9f67e37ea4f425deac060c486bf49a649f` |

These are **valid for `frozen_commit: 99c9fa7970d967500cb7ba939d2a4feaab064844` only** — if David
signs against a later commit (e.g. after this PR merges), all four must be recomputed against
that new HEAD with the same recipe.

### 3b. `config_sha256` / `codex_mcp_list_sha256` — CONSTRAINT fields, genuinely not pre-freezable

Both `eval/fixtures/gate0_expected_pins_{red,miniwob}.json` already mark these
`"CONSTRAINT:launch-invocation-dependent-recompute-at-signature"` — they embed the launch
`-OutputDir`'s absolute mount paths inside `config.toml`/`codex mcp list --json` output, so no
single value can ever be pre-frozen; a fresh value is produced automatically as a side effect of
the free-handshake run itself (`tools/run_gate0_codex.ps1`'s ordinary, non-`-PaidExec` path writes
them into `handshake-receipt.json`).

This session attempted to reproduce that free handshake (against the same pinned images/model
already confirmed identical on this machine — §1 row 9, row 7) purely to demonstrate the recipe
still runs cleanly, but the harness's auto-mode classifier refused to run
`tools/run_gate0_codex.ps1` (twice, via two different tool paths — PowerShell tool and
`powershell.exe` via Bash) because it spawns `docker`/`codex.exe` subprocesses. Per
safety-invariants law 9 this was not routed around. **This does not newly block anything**: these
two fields were never going to be pre-frozen regardless of what ran today — the last committed
proof that the recipe runs cleanly against the current pinned images is
`reports/2026-07-21-gate0-fresh-handshakes.md` (same calendar day; `red-v4`/`miniwob-v3`, all
5 previously-stale fields cleared). Every input that report depended on was independently
reconfirmed unchanged on this machine this session (image IDs, codex version, ROM/state hashes,
world code parity). **Action for David/whoever launches:** run
`tools/run_gate0_codex.ps1 -Arm <red|miniwob> -Model gpt-5.6-sol -OutputDir <the real paid
OutputDir>` once, read `config_sha256`/`codex_mcp_list_sha256` off the resulting
`handshake-receipt.json`, and paste those into the signature — this is unavoidable regardless of
tooling permissions, since the values are a function of the OutputDir actually chosen for the paid
launch, which does not exist yet.

## 4. New finding: the wake-accounting mechanism does not exist (ruling, as requested)

`tools/check_gate0_codex.py::audit()`'s return statement (lines ~270-276) hardcodes:
```python
"wakes": None,
"wake_accounting": "INSUFFICIENT_WAKES",
```
**unconditionally** — nothing in the function's transcript-parsing loop ever computes a wake
count; this is not a side effect of no run having happened, it is that the counting logic was
never written. This is intentional-by-omission, not a bug: `tests/test_check_gate0_codex.py`
pins it by name — `test_exact_observed_pins_are_still_no_go_until_wakes_exist`. Both
`eval/fixtures/gate0_readiness_dev_source_pins.json` and `gate0_paid_source_pins.json` already
self-document this: `"wake_boundary": "PENDING_NOT_YET_CAPTURED_wake_accounting_not_built"`, and
neither has any `red_agent`/`miniwob_agent` artifact-writer tool either (`tools/` has no script
that turns a transcript into `agent_metrics.json`).

**Traced to the actual verdict path** (`eval/score_gate0.py`): `_verify_sources()` requires a
`wake_boundary.json` with `status=PASS` (line 277-278) and cross-checks
`audit.get("wake_accounting") == "PASS"` (line 273) — both permanently unsatisfiable today.
`score()`'s dispatch (lines 325-338) routes any `failures["source"]` entry to
`verdict, readiness = "INSUFFICIENT_DATA", "INSUFFICIENT_SOURCE"` **before** capability/cheap are
ever evaluated. **Concretely: launched today, a Red run that flawlessly completes the starter +
rival battle, and a MiniWoB run that scores 5/5, would both still print `INSUFFICIENT_DATA`/
`INSUFFICIENT_SOURCE` — never `PASS` — because of this gap alone.**

**Ruling on the task's question** ("is a real wake count only observable DURING the paid run, so
it can't gate the launch, only post-run scoring?"): **No — that framing is wrong.** A wake count
is a deterministic function of an already-completed transcript's turn/event structure, exactly
like the token-usage accounting `audit()` already computes in the same loop over the same
`turn.completed` events. Nothing about counting wakes requires being computed live/mid-run; it is
just as offline-computable as every other Cheap-bar metric, and it is fully testable today with
$0 using synthetic transcripts or the existing free-handshake artifacts as fixtures — no paid run
is needed to build or test it. **The actual, correct distinction is: the MECHANISM (how to count a
wake + a frozen `exact_wake_boundary` proof artifact + an `agent_metrics.json` writer) is a
today-closable precondition, not launch-time-only; only the numeric VALUE for a specific arm's run
is necessarily a post-run output** (same as `cost_usd`/`wall_clock_s`, which are also unknown
before a run happens but whose *measurement mechanism* is already built and tested).

**Recommendation:** close this before signing — define what one "wake" is (the natural candidate
is one `turn.completed` event, i.e. reuse `usage_events` already computed in the same loop),
implement it in `audit()`, write the `agent_metrics.json`/`wake_boundary.json` writer tool, and
prove it against synthetic/free-handshake fixtures, all at $0. Flagged as a separate follow-up
task (not built here — out of scope for a stamping pass per gate-methodology's machinery-frozen
discipline; this report only diagnoses and rules).

## 5. Full test suite

```
UV_PROJECT_ENVIRONMENT=.venv-win-stamp UV_NATIVE_TLS=true uv run --frozen pytest -q
```
```
1369 passed, 16 skipped in 54.95s
```
Run on branch `docs/gate0-stamping` at `main`@`99c9fa7`, own worktree
(`git worktree add <scratchpad>/gate0-stamp -b docs/gate0-stamping origin/main`).

## 6. SIGNATURE PACKAGE FOR DAVID

Copy `eval/fixtures/gate0_signature.example.json`'s shape into `eval/fixtures/gate0_signature.json`
(not committed — gitignored by design, per `Confirm-PaidExecSignature`'s absence-refusal). Fields:

| Field | Value | Source |
|---|---|---|
| `schema_version` | `1` | fixed |
| `frozen_commit` | `git rev-parse HEAD` **at actual signature time** (this report's own checks were run against `99c9fa7970d967500cb7ba939d2a4feaab064844`; re-verify if signing later) | David runs `git rev-parse HEAD` in the checkout he launches from |
| `arm` | `red` or `miniwob` (one signature file per arm, or re-sign between launches) | David |
| `planned_model` | `gpt-5.6-sol` | pinned 2026-07-21, `eval/fixtures/gate0_expected_pins_{red,miniwob}.json` |
| `signed_by` | David's name | David |
| `signed_at` | ISO 8601 timestamp | David, at signature time |
| `expected_config_sha256` | **launch-time only** — read off the fresh `handshake-receipt.json`'s `config_sha256` produced by running `tools/run_gate0_codex.ps1 -Arm <arm> -Model gpt-5.6-sol -OutputDir <the real paid OutputDir>` once | David (§3b) |
| `expected_codex_mcp_list_sha256` | **launch-time only** — same receipt's `codex_mcp_list_sha256` | David (§3b) |
| `expected_launcher_sha256` | `859b4c5d0bb5e98c027418cef8187003f31c63fe97b4283bbe1ee2c803284a3e` (valid for commit `99c9fa7`; recompute if signing a later commit) | computed this pass, §3a |
| `expected_credit_breaker_sha256` | `eb77f32253a699bfb2dbd5b784679d85fe4e8f15e4ae4323fbf8b4377b82e8db` (same caveat) | computed this pass, §3a |
| `expected_credit_accountant_sha256` | `03ee8d9c91821ab000d6c8036d516e4ee822b32a69fd222f1ef8b44c0bb6b3a9` (same caveat) | computed this pass, §3a |
| `expected_credit_rate_sha256` | `a34cc006dc3c3d36084545ed7ece2e9f67e37ea4f425deac060c486bf49a649f` (same caveat) | computed this pass, §3a |
| `credit_rate_pin.model` | `gpt-5.6-sol` | same as `planned_model` |
| `credit_rate_pin.rate_source` | a citation, not a guess — e.g. "ChatGPT usage/billing page, screenshot/date, plan X" or an OpenAI pricing-page URL + date observed | **David must supply** |
| `credit_rate_pin.credits_per_usd` | David's real number | **David must supply — see formula below** |
| `credit_rate_pin.usd_per_input_token` | David's real number | **David must supply** |
| `credit_rate_pin.usd_per_cached_input_token` | David's real number | **David must supply** |
| `credit_rate_pin.usd_per_output_token` | David's real number | **David must supply** |
| `notes` | free text | optional |

**How David reads the credit-rate numbers off the ChatGPT/Codex usage page** (per
`tools/gate0_codex_credit_rate.py`'s docstring/plausibility band, PR #122 Finding 3):
- These are **normalized-credits-per-token** (or equivalently **$-per-token**) figures, not a flat
  monthly price. `credits_per_usd` = however many "normalized credits" your plan states 1 USD of
  usage equals (design doc's reference point is 25 credits = $1.00 — confirm your actual plan's
  number, don't assume this one). `usd_per_input_token` / `usd_per_cached_input_token` /
  `usd_per_output_token` = your plan's $-per-token price for each category (cached input is a
  cheaper subset of input tokens; `reasoning_output_tokens` is priced as a subset of output, so it
  has no separate field).
- **Plausibility band the loader enforces** (refuses outside these, PR #122 Finding 3):
  `usd_per_*_token` must be in `[1e-8, 1e-2]` ($0.01-$10,000 per million tokens) unless pinned
  exactly `0.0` (a genuine free tier); `credits_per_usd` must be in `[1, 1000]`.
- If your ChatGPT/Codex plan has no per-token metering visible (flat subscription, no observable
  per-call price) — `tools/gate0_codex_credit_rate.py::load_credit_rate_pin` still refuses an empty
  `rate_source`; you cannot invent a number. In that case, cite whatever the plan's own usage page
  *does* show (e.g. a monthly credit allotment + an observed credits-consumed-per-request figure)
  and derive `usd_per_output_token` from that, noting the derivation in `rate_source` — do not
  leave any field at the template's placeholder `0`.

## 7. Launch checklist

**Before signing anything:** close the wake-accounting gap (§4) — or explicitly accept, in
writing, the risk that the pre-registered attempt scores `INSUFFICIENT_DATA` regardless of task
performance. This is a decision only David can make; it is not this report's call.

Then, per the pre-reg's launch discipline (unchanged by this pass):
1. All preconditions rows in §1 read `MET` except #8 (inherently launch-time).
2. David authors `eval/fixtures/gate0_signature.json` per §6, immediately before that arm's launch
   (fields `expected_config_sha256`/`expected_codex_mcp_list_sha256` must come from a receipt
   produced at the exact `-OutputDir` about to be used).
3. **Precondition 8 — quota check, immediately before EACH arm's launch**: confirm remaining
   ChatGPT/Codex subscription quota covers that arm's hard ceiling (250 normalized credits). If
   insufficient, the arm **waits** for pool reset — this is a schedule slip, not a verdict event,
   per the 2026-07-18 pre-reg's "Pool reservation" note.
4. **Arm R (Red) launches first.** If Arm R alone reaches the combined ceiling, do not launch Arm
   W (pre-reg launch discipline, unchanged).
5. Bank whatever the frozen scorer prints — no informal rerun, no rounding up.

## Sources

`reports/2026-07-18-gate0-prereg.md`, `reports/2026-07-14-gate0-readiness.md`,
`reports/2026-07-21-gate0-fresh-handshakes.md`, `reports/2026-07-21-gate0-red-baseline-reconstruction.md`,
`reports/2026-07-21-gate0-wired-breaker-trip.md`, `reports/2026-07-18-gate0-image-rebuild.md`,
`tools/check_gate0_codex.py`, `tools/run_gate0_codex.ps1`, `eval/score_gate0.py`,
`eval/fixtures/gate0_signature.example.json`, `eval/fixtures/gate0_expected_pins_{red,miniwob}.json`,
`eval/fixtures/gate0_{readiness_dev,paid}_source_pins.json`, `tests/test_check_gate0_codex.py`,
`DAVID_BASELINES.md`, `runs/gate0_human_baseline/{red,miniwob}/human_metrics.json` (gitignored,
read read-only from the primary checkout `ai-pokemon-red-prereg`).
