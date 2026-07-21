# Gate 0 wired-path live breaker -- TRIP receipt (PR #118 checklist 4a-4d) -- 2026-07-21

Closes the "WIRING PENDING" half of PR #118's precondition-4 ruling ("COMPONENT MET -- WIRING
PENDING (not launch-satisfying alone)"). This report documents the 4a-4d build: the token->credit
rate pin mechanism (4a), the paid-exec wiring behind `-PaidExec` (4b), a zero-spend wired-path TRIP
receipt against a stub emitter (4c), and the pre-registered stall backstop (4d).

**ABSOLUTE LAW respected throughout:** no real `codex exec` was ever run to produce this evidence.
Every TRIP demonstration below uses `tools/gate0_stub_codex_emitter.py`, which makes no network
call and invokes no model. Any real paid invocation stays gated on David's signature
(`eval/fixtures/gate0_signature.json`, absent on `main` by design) plus the pre-reg launch
checklist.

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
shape, corroborating the schema.

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
mismatch.

## 4b -- the paid launcher wraps `codex exec --json` through the breaker with a kill contract

`tools/run_gate0_codex.ps1` gains `-PaidExec` (switch, off by default), `-SignaturePath` (defaults
to `eval/fixtures/gate0_signature.json`), and `-StallTimeoutS` (defaults to the pre-registered
`300`, and the script refuses any *looser* override). Without `-PaidExec` the script is
byte-identical in behavior to before -- `tests/test_run_gate0_codex_launcher.py`'s existing
free-handshake-only assertions (including `SCRIPT.rstrip().endswith("exit 1")`) are unmodified and
still pass.

New functions (all individually extractable and testable via this file's existing AST-harness
pattern -- see `tests/test_run_gate0_codex_launcher.py`):

- **`Confirm-PaidExecSignature`** -- refuses `-PaidExec` unless a signature file exists that names
  the *exact* frozen commit (`git rev-parse HEAD`), arm, model, and the two launch-invocation-
  dependent hashes this run's own free-handshake logic just computed (`config_sha256`,
  `codex_mcp_list_sha256` -- PR #118's "CONSTRAINT... signature-time recompute recipe" pair), plus
  a `credit_rate_pin`.
- **`Get-PaidCodexExecArguments`** -- reuses the exact same explicit-override vocabulary the free
  `codex mcp list --json` handshake already proved Codex accepts; the task prompt is piped over
  stdin (`-`), never re-quoted as a CLI argument.
- **`Invoke-BreakerSupervisedExec`** -- THE KILL CONTRACT. Spawns the child (real Codex in
  production; the stub emitter for this proof) with its stdout relayed live, via .NET
  `Stream.CopyToAsync` (never buffered/materialized -- PR #118 breaker review MAJOR 1), into
  `tools/gate0_credit_accountant.py`, which feeds `run_breaker(raise_on_trip=True,
  stall_timeout_s=StallTimeoutS)` a lazy generator over that relayed stream. The accountant's own
  exit is the kill signal: the instant it exits for any reason other than the child having already
  finished on its own, the child's **whole process tree** is killed (`taskkill /PID <id> /T /F`,
  never a lone top-level `Stop-Process`, so a docker/MCP descendant cannot be stranded). Evidence
  (exit codes, `HasExited`, a post-kill liveness poll, the kill command's own output) is returned,
  not merely asserted.
- **`tools/gate0_credit_accountant.py`** -- the bridge subprocess. Reads stdin lazily
  (`for line in stdin`), converts each raw event via `gate0_codex_credit_rate`, and feeds
  `run_breaker`. Exit 0 = stream ended without tripping; exit 2 = a kill-worthy breaker exception
  fired -- **`BreakerTripped` or `MalformedCreditStream` are deliberately the same exit code**, so
  a caller cannot accidentally special-case away the fail-open `MalformedCreditStream` path (PR
  #118 breaker review MINOR 2); exit 3 = the rate pin itself was invalid, refused before a single
  stream byte was read.

## 4c -- wired-path TRIP receipt against a zero-spend stub emitter

`tools/gate0_stub_codex_emitter.py` makes no network call and invokes no model. It emits a
deterministic JSONL stream shaped exactly like the real `token_count` events found in 4a's
evidence (one pass-through `agent_message_delta` event interleaved, proving the zero-credit
pass-through path also runs on the real wired stream, not only in isolated unit tests), paced at
0.2s/event, with a synchronously-flushed-and-fsynced `--out-progress` file recording exactly how
many events it had emitted -- independent, write-side evidence of an unsent tail, separate from
the accountant's own read-side halt evidence.

`tools/gate0_wired_breaker_trip_proof.ps1` runs the proof: it extracts and invokes the exact same
production `Invoke-BreakerSupervisedExec`/`ConvertTo-NativeArgument` functions from
`tools/run_gate0_codex.ps1` (identical AST-extraction technique the test suite already uses),
substituting the stub emitter for `codex.exe` and a **clearly-labeled synthetic** credit-rate pin
(`rate_source` says outright it is a test fixture, not a real price) so the trip fires quickly.

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
    "rate_source": "SYNTHETIC TEST FIXTURE for PR #118 checklist 4c -- proves the wired kill path, NOT a real priced rate. See reports/2026-07-21-gate0-wired-breaker-trip.md.",
    "credits_per_usd": 1, "usd_per_input_token": 0, "usd_per_cached_input_token": 0, "usd_per_output_token": 1
  },
  "emitter": {
    "intended_total_events": 150, "emitted_count_at_kill": 47, "unsent_tail": 103,
    "output_tokens_per_event": 6, "delay_s_between_events": 0.2
  },
  "accountant_verdict": {
    "result": "TRIPPED", "credits_at_trip": 252.0, "event_index_at_trip": 42, "events_seen": 43
  },
  "child_process_termination_evidence": {
    "child_id": 34848, "child_killed": true, "child_has_exited": true, "child_exit_code": 1,
    "child_still_alive_after_kill": false,
    "kill_evidence": "SUCCESS: The process with PID 32120 (child process of PID 34848) has been terminated.\r\nSUCCESS: The process with PID 34848 (child process of PID 43072) has been terminated.\r\n"
  },
  "accountant_process": { "exit_code": 2, "stderr": "" },
  "started_at": "2026-07-21T03:25:51.5608690+02:00",
  "ended_at": "2026-07-21T03:26:01.6275162+02:00",
  "wall_clock_s": 10.067
}
```

`runs/gate0_live_breaker/wired_path_trip.json` SHA-256 (this specific run; regenerable but NOT
byte-deterministic like the 4c-adjacent dry-run artifact -- it carries real PIDs/timestamps from a
genuine process run, the same class of evidence as a handshake receipt, not a pure function of
committed code):
```
086e1438ff1d414f51d16a0e0fe1cd46df55bb34945465ac6c5a2ba2c9935d31
```

**Reading the evidence:**
- **Detector correctness (read side):** the accountant genuinely tripped mid-stream --
  `credits_at_trip: 252.0` at `event_index_at_trip: 42` (one `agent_message_delta` pass-through
  event shifted the raw-event index by one versus the pure-`token_count` 45x6 pattern in
  `tests/test_gate0_credit_breaker.py`; 43 raw events were consumed, never the whole stream).
- **Emission-side halt (write side), independent of the accountant:** the emitter's own
  fsync'd progress file shows `emitted_count_at_kill: 47` against `intended_total_events: 150` --
  **103 events it was told to emit were never written**, because the process was killed. This is
  the evidence class PR #118 explicitly required beyond "events unread": "events unread" alone
  proves only that the accountant stopped reading; this proves the *writer* itself was cut off.
- **Child-process termination (not merely "a signal was sent"):** `child_killed: true`,
  `child_has_exited: true`, and -- the decisive check -- `child_still_alive_after_kill: false`,
  confirmed by re-polling the OS process table for that PID after the kill, not merely inferred
  from the kill command's own exit status. `kill_evidence` is `taskkill /T /F`'s own SUCCESS output
  for both the target PID and one descendant it also caught, confirming the **process tree** kill
  (not a lone top-level `Stop-Process`) actually ran.

**A real, zero-spend engineering finding banked here for whoever wires the real stream next:**
Windows Python, when stdout is redirected to a pipe (not a console), prepended a UTF-8 byte-order
mark to the very first line of `tools/gate0_stub_codex_emitter.py`'s output -- caught because the
first proof attempt failed with `MALFORMED: malformed_json_line:0`. `codex.exe` is a Rust binary
and would not have this specific quirk, but `tools/gate0_credit_accountant.py`'s stream reader now
decodes as `utf-8-sig` regardless (strips a BOM if present, byte-identical to plain utf-8
otherwise) as cheap, general defense; the emitter was also fixed to stop emitting one.

## 4d -- wall-clock stall backstop

Wired default: `stall_timeout_s=StallTimeoutS` where `-StallTimeoutS` defaults to `300` (matching
`tools/gate0_credit_breaker.py::STALL_TIMEOUT_S`, pre-registered in PR #118's breaker review MINOR
3a). `run_gate0_codex.ps1` refuses any `-StallTimeoutS` greater than `300` -- overridable only to
tighten, never to loosen, the pre-registered value. The backstop's own detector correctness (a
stalled generator raises `MalformedCreditStream("stall_timeout:*")` rather than blocking forever)
is unit-tested in `tests/test_gate0_credit_breaker.py::test_stall_timeout_fails_closed`
(pre-existing) and exercised end-to-end through the accountant in
`tests/test_gate0_credit_accountant.py`.

## Status

**Precondition 4, all of 4a-4d, now built and proven zero-spend.** This does NOT authorize a real
paid launch: `eval/fixtures/gate0_signature.json` does not exist on `main` (only the schema
template `eval/fixtures/gate0_signature.example.json` does), so `-PaidExec` refuses closed until
David signs one naming the frozen commit, the two launch-invocation-dependent hashes, and a
**real** (not synthetic-test) `credit_rate_pin` with a genuine `rate_source` citation. The paid
launch may not proceed on this report's synthetic receipt alone, exactly as PR #118's ruling says
of the precondition-4 dry run before it.

## Commands (for reproduction)

```
powershell -File tools/gate0_wired_breaker_trip_proof.ps1
python -m tools.gate0_codex_credit_rate validate --rate-pin <path> --model <model>
UV_PROJECT_ENVIRONMENT=.venv-win-launch UV_NATIVE_TLS=true uv run --frozen pytest -q
```
