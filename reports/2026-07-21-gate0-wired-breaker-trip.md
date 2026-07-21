# Gate 0 wired-path live breaker -- TRIP receipt (PR #118 checklist 4a-4d) -- 2026-07-21

*(Revised same-day after PR #122's adversarial review: 4 MAJOR findings, all reproduced with
runnable PoCs, plus 1 minor. All four are fixed below; see "Review-fix round." The wired-path TRIP
receipt was regenerated after the fixes -- new hash, same trip arithmetic. Precondition 4 remains
**WIRING PENDING, not MET**, pending re-review of this revision.)*

Closes the "WIRING PENDING" half of PR #118's precondition-4 ruling ("COMPONENT MET -- WIRING
PENDING (not launch-satisfying alone)"). This report documents the 4a-4d build: the token->credit
rate pin mechanism (4a), the paid-exec wiring behind `-PaidExec` (4b), a zero-spend wired-path TRIP
receipt against a stub emitter (4c), and the pre-registered stall backstop (4d).

**ABSOLUTE LAW respected throughout, including the revision round:** no real `codex exec` was ever
run to produce this evidence. Every TRIP demonstration below uses `tools/gate0_stub_codex_emitter.py`
or other zero-spend PoC scripts that make no network call and invoke no model. Any real paid
invocation stays gated on David's signature (`eval/fixtures/gate0_signature.json`, absent on `main`
by design) plus the pre-reg launch checklist.

## 4a -- token->normalized-credit conversion, pinned at signature time

**What Codex CLI actually emits (verified zero-spend, 2026-07-21, on the launch machine):**
`codex exec --help` documents `--json` as "Print events to stdout as JSONL". Rather than guess the
event shape, this was checked directly against `codex doctor` (codex-cli 0.144.3, confirms the
Gate 0 pin `model gpt-5.6-sol . openai`, `stored auth mode chatgpt`) and against this machine's own
pre-existing (already-paid) local Codex session rollouts (`~/.codex/sessions/**/*.jsonl`) -- reading
history already on disk spends nothing new. Every rollout's `event_msg` entries with
`payload.type == "token_count"` carry:

- `info.total_token_usage` -- cumulative for the whole session
- `info.last_token_usage` -- this turn's delta (confirmed empirically: `total_tokens ==
  input_tokens + output_tokens`; `cached_input_tokens` is a priced-differently SUBSET of
  `input_tokens`, `reasoning_output_tokens` a subset of `output_tokens`, never additional tokens)
- `rate_limits.credits` -- an object `{has_credits, unlimited, balance}`, observed on this
  ChatGPT-subscription account (`plan_type: "plus"`, `auth: "chatgpt"`) as
  `{"has_credits": false, "unlimited": false, "balance": "0"}`

**Conclusion:** the CLI does not hand back a usable normalized-credit number for the Gate 0
ChatGPT-subscription auth mode -- only raw token counts are observable. Per this task's own
instruction, the rate therefore cannot be invented. `tools/gate0_codex_credit_rate.py` implements
exactly the required fallback: `load_credit_rate_pin()` refuses to run (`CreditRateNotPinned`)
unless a rate-pin JSON exists with a non-empty `rate_source` citation and a matching `model`, and
`token_usage_delta_to_credits()` prices `last_token_usage` deltas (never the cumulative total) via
that pin. No dollar figure is hardcoded anywhere in this codebase. `TOKEN_FIELDS` in
`tools/check_gate0_codex.py` (pre-existing, independent of this work) matches this exact 4-field
shape, corroborating the schema. **Review-fix round addition: a plausibility band on the rate
itself -- see Finding 3 below.**

The `--json` stdout envelope for a genuinely live `codex exec --json` run was **not**
independently re-verified (that would require a real paid exec, forbidden here). The extractor
(`codex_event_to_credit_event`) is defensive: it accepts either a bare `{"type": "token_count",
...}` line or one wrapped as `{"msg": {"type": "token_count", ...}}` (the shape codex-rs's own
rollout persistence uses for the same struct); a line matching neither shape is a zero-credit
pass-through, never a fabricated credit delta.

**Signature-time pin field:** `eval/fixtures/gate0_signature.json` (absent on `main`; template at
`eval/fixtures/gate0_signature.example.json`) embeds `credit_rate_pin` with required fields
`model`, `rate_source`, `credits_per_usd`, `usd_per_input_token`, `usd_per_cached_input_token`,
`usd_per_output_token`. `-PaidExec` runs a preflight (`python tools/gate0_codex_credit_rate.py
validate`) before spawning any process, and refuses closed on any missing/invalid field or a model
mismatch. **Review-fix round addition: the same signature now also pins canonical hashes of the
four safety-critical source files -- see Finding 1.**

## 4b -- the paid launcher wraps `codex exec --json` through the breaker with a kill contract

`tools/run_gate0_codex.ps1` gains `-PaidExec` (switch, off by default), `-SignaturePath` (defaults
to `eval/fixtures/gate0_signature.json`), `-StallTimeoutS` (defaults to the pre-registered `300`,
refuses any *looser* override), and, after the review-fix round, `-LedgerPath`/
`-ResetCombinedLedger` (Finding 4). Without `-PaidExec` the script is byte-identical in behavior to
before -- `tests/test_run_gate0_codex_launcher.py`'s existing free-handshake-only assertions
(including `SCRIPT.rstrip().endswith("exit 1")`) are unmodified and still pass.

New functions (all individually extractable and testable via this file's existing AST-harness
pattern -- see `tests/test_run_gate0_codex_launcher.py`):

- **`Confirm-PaidExecSignature`** -- refuses `-PaidExec` unless a signature file exists that names
  the *exact* frozen commit (`git rev-parse HEAD`), arm, model, the two launch-invocation-dependent
  hashes this run's own free-handshake logic just computed (`config_sha256`,
  `codex_mcp_list_sha256`), a `credit_rate_pin`, **and (review-fix round, Finding 1) canonical
  git-blob hashes of the four safety-critical source files themselves.**
- **`Get-PaidCodexExecArguments`** -- reuses the exact same explicit-override vocabulary the free
  `codex mcp list --json` handshake already proved Codex accepts; the task prompt is piped over
  stdin (`-`), never re-quoted as a CLI argument.
- **`Invoke-BreakerSupervisedExec`** -- THE KILL CONTRACT. Spawns the child (real Codex in
  production; the stub emitter for this proof) with its stdout relayed live, via .NET
  `Stream.CopyToAsync` (never buffered/materialized -- PR #118 breaker review MAJOR 1), into
  `tools/gate0_credit_accountant.py`, which feeds `run_breaker(raise_on_trip=True,
  stall_timeout_s=StallTimeoutS)` a lazy generator over that relayed stream. The accountant's own
  exit is the kill signal. **Review-fix round (Finding 2): the child's whole process tree is now
  torn down by TWO independent mechanisms on every exit path -- a Windows Job Object assigned at
  spawn time, closed in `finally`, plus an unconditional `taskkill /PID <id> /T /F`** (previously
  gated on the child still being alive, which a clean exit skipped).
- **`tools/gate0_credit_accountant.py`** -- the bridge subprocess. Reads stdin lazily
  (`for line in stdin`), converts each raw event via `gate0_codex_credit_rate`, and feeds
  `run_breaker`. Exit 0 = stream ended without tripping; exit 2 = a kill-worthy breaker exception
  fired -- **`BreakerTripped` or `MalformedCreditStream` are deliberately the same exit code**, so
  a caller cannot accidentally special-case away the fail-open `MalformedCreditStream` path; exit 3
  = the rate pin itself was invalid, refused before a single stream byte was read.
- **`Get-Gate0CombinedCreditLedger` / `Confirm-CombinedCreditBudgetAvailable` /
  `Add-Gate0CombinedCreditLedgerEntry`** -- review-fix round, Finding 4: the cross-arm `<=250
  combined` ledger.

## Review-fix round (2026-07-21, PR #122 adversarial review, all reproduced with runnable PoCs)

**Finding 1 (MAJOR) -- the signature did not pin the code that enforces it.** `git rev-parse HEAD`
says which commit HEAD points at, not whether the working tree matches that commit's blobs. The
reviewer proved this live: an *uncommitted* edit to `tools/gate0_credit_breaker.py` (e.g. changing
`LIMIT_NORMALIZED_CREDITS = 250` to `250000`, neutering the ceiling) at the exact signed commit was
accepted, because nothing hashed the launcher/breaker/accountant/rate-converter files themselves --
only `world_mcp.py`/`core/miniwob_world.py` got that treatment via `Get-CanonicalCodeSha256`.
**Fix:** `Confirm-PaidExecSignature` now runs that identical function (same canonical-git-blob-at-
HEAD contract, same `UNHASHABLE` dirty-tree refusal) against `tools/run_gate0_codex.ps1`,
`tools/gate0_credit_breaker.py`, `tools/gate0_credit_accountant.py`, and
`tools/gate0_codex_credit_rate.py`, comparing each to a new required signature field
(`expected_launcher_sha256`, `expected_credit_breaker_sha256`, `expected_credit_accountant_sha256`,
`expected_credit_rate_sha256` -- added to `eval/fixtures/gate0_signature.example.json`). **PoC now
refuses:** `tests/test_run_gate0_codex_launcher.py::test_confirm_signature_refuses_a_dirty_working_tree_at_the_signed_commit`
reproduces the reviewer's exact scenario (sign, then edit `gate0_credit_breaker.py` uncommitted) and
asserts refusal with `"dirty working tree"` in the error.

**Finding 2 (MAJOR) -- the kill only fired if the immediate child was still alive.** A child that
spawns a `DETACHED_PROCESS`/`CREATE_NEW_PROCESS_GROUP` grandchild, emits one harmless event, and
exits normally left that grandchild running forever -- `Invoke-BreakerSupervisedExec`'s only kill
path was gated on `-not $child.HasExited`. The real production child (`codex.exe`) itself spawns
`docker run` as its MCP-server subprocess, so an unclean codex exit racing a still-finishing docker
process hits this exact gap. **Fix, both applied (coordinator asked for either; this PR does
both):** (a) the child is assigned to a Windows Job Object created with
`JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE` and no breakaway flag the instant it is spawned -- closing that
job (in `finally`, on every exit path: trip, clean exit, stall, or an exception in the function
itself) kills every process still in it, including a descendant whose immediate parent already
exited; (b) `taskkill /PID <id> /T /F` is now issued unconditionally (previously conditional),
never a lone `Stop-Process`. **PoC now refuses (i.e. the grandchild no longer survives):**
`tests/test_run_gate0_codex_launcher.py::test_breaker_supervised_exec_reaps_a_detached_grandchild_after_the_child_exits_cleanly`
reproduces the reviewer's exact PoC end to end and confirms, via a fresh `Get-Process` poll, that
the grandchild is gone after `Invoke-BreakerSupervisedExec` returns even though the immediate child
exited cleanly (`ChildKilled: false`, `ChildExitCode: 0`). A real bug surfaced while proving this
fix: `tools/gate0_credit_breaker.py`'s stall-backstop daemon thread can still be mid-read on the
accountant's stdin when the main thread tries to exit, and a normal Python interpreter shutdown
races that thread against the buffered-I/O lock -- observed as a `STATUS_ACCESS_VIOLATION` crash
that delayed PowerShell's supervisor from noticing the accountant had exited by several seconds
(long enough for a short-lived child to finish on its own before the kill landed). Fixed in
`tools/gate0_credit_accountant.py` with `os._exit()` instead of `sys.exit()`/`SystemExit` after the
verdict file is already written and closed -- terminates immediately via the OS syscall without
racing the daemon thread. (`tools/gate0_credit_breaker.py` itself, the pinned PR #118 file, was not
touched for this.)

**Finding 3 (MAJOR) -- no magnitude sanity check on the rate pin.** `load_credit_rate_pin` refused
`credits_per_usd<=0` and negative fields, but accepted any positive value. The reviewer's PoC:
`1e-12 $/token` (a plausible units mistake, e.g. quoting a per-1M-token price as per-token) is
accepted, and needs **~2.5 billion turns** to reach 250 credits -- the ceiling is effectively
disabled. The opposite direction (a rate 10x+ too high) is safe but wastes the one pre-registered
attempt on an instant false trip. **Fix:** `MIN_USD_PER_TOKEN = 1e-8` / `MAX_USD_PER_TOKEN = 1e-2`
($0.01-$10,000 per million tokens -- six orders of magnitude around real 2026-era frontier pricing,
so a genuine future price change is never blocked while a >=100x units error is refused) and
`MIN_CREDITS_PER_USD = 1` / `MAX_CREDITS_PER_USD = 1000` (bracketing the design doc's pinned "25
credits = $1.00" with the same generosity). A field pinned exactly to `0.0` is exempt (a genuine
free tier is a real price, not a units bug). `Invoke-BreakerSupervisedExec`'s `MaxWallClockS`
(3600s default) remains a documented, separate, independent backstop for a rate implausible-but-
still-inside this band -- this check narrows the gap, it does not replace that backstop. **PoC now
refuses:** `tests/test_gate0_codex_credit_rate.py::test_load_credit_rate_pin_refuses_the_reviewers_implausibly_low_poc`
(`1e-12`) and `..._implausibly_high_poc` (`1.0`) both raise `CreditRateNotPinned` with
`rate_pin_implausible_field:usd_per_output_token`.

**Finding 4 (MAJOR, scope caveat resolved by David/coordinator: in scope) -- the pre-registered
"hard breaker <=250 (combined)" was not mechanically enforced across arms.**
`LIMIT_NORMALIZED_CREDITS=250` was a per-invocation limit; each `-PaidExec` launch got a fresh
accountant whose `run_breaker` total started at `0.0`, so Arm R could spend up to ~250 and Arm W
could independently spend another ~250 -- an actual code-enforced worst case of ~2x the
pre-registered combined hard-stop the design doc's launch discipline describes in prose only.
**Fix:** a small gitignored ledger (`runs/gate0_live_breaker/combined_credit_ledger.json`, default
path, overridable via `-LedgerPath`) records the running combined total across launches of the same
pre-registered attempt. `Confirm-CombinedCreditBudgetAvailable` refuses `-PaidExec` outright, before
spawning anything, once the ledger shows the combined budget exhausted. `tools/gate0_credit_breaker.py::run_breaker`
gained an additive `starting_credits: float = 0.0` parameter (default preserves every existing
single-invocation caller's behavior exactly; a carried-over total already at/over the limit trips
immediately, before pulling a single event) and `gate0_credit_accountant.py` gained
`--starting-credits`, wired from the ledger's current total. On COMPLETED/TRIPPED the ledger records
the breaker's own exact final total (which already includes the carry-over); on any other outcome
(MALFORMED/RATE_NOT_PINNED/no verdict) the true spend at failure is not precisely known, so the
ledger conservatively records the ledger as FULLY EXHAUSTED rather than risk under-counting real
spend and letting a subsequent arm launch on a false "budget available" read. `-ResetCombinedLedger`
starts a fresh pre-registered attempt's accounting at zero -- an explicit, deliberate flag, never
implicit. **Tested:** `tests/test_gate0_credit_breaker.py` (starting-credits seeding, immediate trip
when already over budget, fail-closed on an invalid value), `tests/test_gate0_credit_accountant.py::test_starting_credits_carries_over_and_can_trip_on_the_first_event`,
and `tests/test_run_gate0_codex_launcher.py` (ledger absent-starts-at-zero, malformed-JSON refusal,
budget-exhausted refusal, and a simulated two-arm carry-forward through
`Add-Gate0CombinedCreditLedgerEntry`).

**Minor -- rate-pin reader `utf-8` to `utf-8-sig`.** Not exploitable today (the launcher always
writes this file itself via `Write-Utf8NoBom`, confirmed BOM-free), but `load_credit_rate_pin` now
decodes `utf-8-sig` for the same hard-won reason `gate0_credit_accountant.py`'s stream reader
already does (a leading BOM is byte-identical to plain utf-8 otherwise, so this never masks a
genuinely malformed file).

## 4c -- wired-path TRIP receipt against a zero-spend stub emitter

`tools/gate0_stub_codex_emitter.py` makes no network call and invokes no model. It emits a
deterministic JSONL stream shaped exactly like the real `token_count` events found in 4a's
evidence (one pass-through `agent_message_delta` event interleaved, proving the zero-credit
pass-through path also runs on the real wired stream, not only in isolated unit tests), paced at
0.2s/event, with a synchronously-flushed-and-fsynced `--out-progress` file recording exactly how
many events it had emitted -- independent, write-side evidence of an unsent tail, separate from
the accountant's own read-side halt evidence.

`tools/gate0_wired_breaker_trip_proof.ps1` runs the proof: it extracts and invokes the exact same
production `Invoke-BreakerSupervisedExec`/`Get-Gate0KillOnCloseJob`/`ConvertTo-NativeArgument`
functions from `tools/run_gate0_codex.ps1` (identical AST-extraction technique the test suite
already uses), substituting the stub emitter for `codex.exe` and a **clearly-labeled synthetic**
credit-rate pin (`rate_source` says outright it is a test fixture, not a real price) so the trip
fires quickly. **Regenerated after the review-fix round:** the rate pin now sits at the real
design-doc `credits_per_usd=25` and the top of Finding 3's plausibility band
(`usd_per_output_token=0.01`) rather than the pre-fix fixture's implausible `1.0` -- which the
fixed `load_credit_rate_pin` would now itself refuse -- with a correspondingly larger
`--output-tokens-per-event 24` preserving the exact same "6 credits/event" arithmetic as before.

Command:
```
powershell -File tools/gate0_wired_breaker_trip_proof.ps1
```

Result -- `runs/gate0_live_breaker/wired_path_trip.json` (gitignored, `runs/` per `.gitignore:27`;
this report is the committed evidence, same convention as
`reports/2026-07-19-gate0-live-breaker-dry-run.md`):

```json
{
  "schema_version": 1,
  "kind": "gate0_wired_breaker_trip_proof",
  "checklist_item": "PR #118 precondition-4 checklist 4c",
  "status": "PASS",
  "rate_pin": {
    "model": "stub-model",
    "rate_source": "SYNTHETIC TEST FIXTURE for PR #122 checklist 4c -- proves the wired kill path at a real credits_per_usd and the top of the plausible per-token band, NOT a real priced rate. See reports/2026-07-21-gate0-wired-breaker-trip.md.",
    "credits_per_usd": 25, "usd_per_input_token": 0, "usd_per_cached_input_token": 0, "usd_per_output_token": 0.01
  },
  "emitter": {
    "intended_total_events": 150, "emitted_count_at_kill": 46, "unsent_tail": 104,
    "output_tokens_per_event": 24, "delay_s_between_events": 0.2
  },
  "accountant_verdict": {
    "result": "TRIPPED", "credits_at_trip": 252.0, "event_index_at_trip": 42, "events_seen": 43
  },
  "child_process_termination_evidence": {
    "child_id": 40140, "child_killed": true, "child_has_exited": true, "child_exit_code": 1,
    "child_still_alive_after_kill": false,
    "kill_evidence": "SUCCESS: The process with PID 46716 (child process of PID 40140) has been terminated.\r\nSUCCESS: The process with PID 40140 (child process of PID 35052) has been terminated.\r\n"
  },
  "accountant_process": { "exit_code": 2, "stderr": "" },
  "started_at": "2026-07-21T06:25:34.5611385+02:00",
  "ended_at": "2026-07-21T06:25:44.7041597+02:00",
  "wall_clock_s": 10.143
}
```

`runs/gate0_live_breaker/wired_path_trip.json` SHA-256 (this specific run; regenerable but NOT
byte-deterministic like the 4c-adjacent dry-run artifact -- it carries real PIDs/timestamps from a
genuine process run, the same class of evidence as a handshake receipt, not a pure function of
committed code; **supersedes the pre-review-round hash `086e1438...`**):
```
fb67cdd49e1521b43f902aacf2ffeddbfe89320a8829a810de70936a87488542
```

**Reading the evidence:**
- **Detector correctness (read side):** the accountant genuinely tripped mid-stream --
  `credits_at_trip: 252.0` at `event_index_at_trip: 42` (identical trip point to the pre-fix run:
  the plausibility-band rate change preserved the exact "6 credits/event" arithmetic on purpose).
- **Emission-side halt (write side), independent of the accountant:** the emitter's own fsync'd
  progress file shows `emitted_count_at_kill: 46` against `intended_total_events: 150` -- **104
  events it was told to emit were never written**, because the process was killed.
- **Child-process termination (not merely "a signal was sent"), now via TWO independent mechanisms
  (Finding 2 fix):** `child_killed: true`, `child_has_exited: true`, and -- the decisive check --
  `child_still_alive_after_kill: false`, confirmed by re-polling the OS process table for that PID
  after the kill. `kill_evidence` is `taskkill /T /F`'s own SUCCESS output for both the target PID
  and a descendant it also caught; the Job Object close ran alongside it in the same supervised
  call (see `test_breaker_supervised_exec_reaps_a_detached_grandchild_after_the_child_exits_cleanly`
  for the case where taskkill's PPID scan is NOT what saves the day -- the job close is).

**A real, zero-spend engineering finding banked here for whoever wires the real stream next:**
Windows Python, when stdout is redirected to a pipe (not a console), prepended a UTF-8 byte-order
mark to the very first line of `tools/gate0_stub_codex_emitter.py`'s output -- caught because the
first proof attempt failed with `MALFORMED: malformed_json_line:0`. `codex.exe` is a Rust binary
and would not have this specific quirk, but `tools/gate0_credit_accountant.py`'s stream reader
decodes as `utf-8-sig` regardless (strips a BOM if present, byte-identical to plain utf-8
otherwise) as cheap, general defense; the emitter was also fixed to stop emitting one. A SECOND
finding surfaced during the review-fix round is documented under Finding 2 above (the daemon-thread
interpreter-shutdown race fixed with `os._exit()`).

## 4d -- wall-clock stall backstop

Wired default: `stall_timeout_s=StallTimeoutS` where `-StallTimeoutS` defaults to `300` (matching
`tools/gate0_credit_breaker.py::STALL_TIMEOUT_S`, pre-registered in PR #118's breaker review MINOR
3a). `run_gate0_codex.ps1` refuses any `-StallTimeoutS` greater than `300` -- overridable only to
tighten, never to loosen, the pre-registered value. The backstop's own detector correctness (a
stalled generator raises `MalformedCreditStream("stall_timeout:*")` rather than blocking forever)
is unit-tested in `tests/test_gate0_credit_breaker.py::test_stall_timeout_fails_closed`
(pre-existing) and exercised end-to-end through the accountant in
`tests/test_gate0_credit_accountant.py`. Per Finding 3, `MaxWallClockS` (3600s,
`Invoke-BreakerSupervisedExec`'s supervisory poll-loop ceiling) is a separate, documented backstop
for an implausible-but-in-band rate, not a replacement for the plausibility check itself.

## Status

**Precondition 4's 4a-4d build is complete and the review-fix round closes all four reproduced
MAJOR findings plus the minor**, each with its own regression test and (Findings 1-3) a test that
reproduces the reviewer's exact PoC and confirms it now refuses. Precondition 4 stays **WIRING
PENDING, not MET**, pending a re-review of this revision -- this report's synthetic receipt does
not authorize a real paid launch on its own, exactly as PR #118's ruling said of the precondition-4
dry run before it. `eval/fixtures/gate0_signature.json` does not exist on `main` (only the schema
template `eval/fixtures/gate0_signature.example.json` does, now carrying the four safety-critical
hash fields too), so `-PaidExec` refuses closed until David signs one naming the frozen commit, all
six hash pins, and a **real** (not synthetic-test) `credit_rate_pin` with a genuine `rate_source`
citation inside the new plausibility band.

## Commands (for reproduction)

```
powershell -File tools/gate0_wired_breaker_trip_proof.ps1
python -m tools.gate0_codex_credit_rate validate --rate-pin <path> --model <model>
UV_PROJECT_ENVIRONMENT=.venv-win-launch UV_NATIVE_TLS=true uv run --frozen pytest -q
```
