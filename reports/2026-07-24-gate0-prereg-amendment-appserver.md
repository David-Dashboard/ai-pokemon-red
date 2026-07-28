# Gate 0 pre-registration amendment — launch surface: `codex exec` -> `codex app-server` (2026-07-24)

**Status: build complete, $0-tested only. No paid run was launched by this build.** This amends
`reports/2026-07-18-gate0-prereg.md` (the DRAFT pre-registration) and
`reports/2026-07-13-minimum-north-star-gate-0-design.md` (the design doc) to reflect the M1 unblock
(`reports/2026-07-23-gate0-appserver-m1-confirmation.md`): `codex exec` cannot get past the
upstream MCP-tool-call-approval bug (`openai/codex#15824`/`#16685`) headlessly, but `codex
app-server`'s answerable JSON-RPC approval flow does, confirmed against a real paid turn.

## Authorization

David's standing paid-run grant, 2026-07-24, authorizes running the real Gate 0 Arm R and Arm W
attempts over this new app-server launch surface, once built and reviewed. **This build itself
performed no paid run** — build + $0-test only, per this task's own scope; the orchestrator runs
the paid attempts.

## Adversarial review of PR #157 — one BLOCKING fix, one SHOULD-fix (2026-07-24)

Both fixed on this branch before merge; suite re-verified green (counts below).

**BLOCKING — the adapter false-`NO_LEAK`'d every real run.** Proven empirically, not by
inspection: running the original adapter (which renamed only `mcpToolCall`, leaving
`userMessage`/`agentMessage`/`reasoning` unmapped) over the real, committed M1 transcript and
feeding the result through the frozen `audit()` produced `overall=NO_LEAK`,
`leak_failures=['forbidden_item:...:userMessage', 'forbidden_item:...:agentMessage']`. Root cause:
`audit()`'s skip-list (`tools/check_gate0_codex.py:249`) accepts only
`{reasoning, agent_message, mcp_tool_call}`, and the real app-server capture
(`reports/2026-07-23-gate0-appserver-m1-confirmation/transcript.jsonl` lines 16-30) emits FOUR item
types — `userMessage`, `reasoning`, `mcpToolCall`, `agentMessage` — not just the one this build had
originally confirmed. **Fix**, grounded against a second piece of real evidence
(`reports/2026-07-22-gate0-paid-exec-noop-diagnosis.md`, a REAL `codex exec --json` capture whose
item types are exactly `agent_message`/`mcp_tool_call` and — critically — **no user-message item at
all**): added the confirmed rename `agentMessage -> agent_message`; `userMessage` is now DROPPED
entirely (no `item.*` line emitted for it — it is the prompt echo, and the exec-shaped target
vocabulary has no counterpart for it at all, so translating it under any name is a guaranteed
false-positive leak); `reasoning` needed no change (already spelled identically to the skip-list).
The genuinely-unknown-type fail-closed default is unchanged and still correct.
**The decisive proof** is `test_adapter_over_the_real_m1_transcript_produces_zero_leak_failures` —
replays the real, committed transcript (not a hand-built fixture) through
`ObservingGate0Client`/the adapter/the frozen `audit()` and asserts `leak_failures == []`; before
the fix this assertion failed with exactly the two `forbidden_item` entries quoted above.

**SHOULD — one-attempt guard hole.** `refuse_if_already_completed` keyed solely on
`agent_metrics.json`, which is written only at the very END of a successful run. A run that
**spends real credits then crashes mid-turn** leaves no marker at all, so a second launch into the
same `--out-dir` would silently re-spend. Fixed: the guard now ALSO refuses if
`transcript.raw_appserver.jsonl` exists — that file is written from the very FIRST message
`ObservingGate0Client` observes, long before any real turn/tool-call spend begins, so it catches a
crashed-after-spending attempt `agent_metrics.json` alone would miss. Both markers are checked (not
one replacing the other). New test:
`test_one_attempt_guard_catches_a_crashed_after_spending_run_with_no_agent_metrics` — builds an
out-dir containing only `transcript.raw_appserver.jsonl` (explicitly asserts `agent_metrics.json`
does NOT exist, reproducing the exact hole) and confirms a second launch is still refused.

**Not changed, per the coordinator's explicit call:** wake-scorability (confirmed
`eval/score_gate0.py` never reads `audit()`'s `overall` field, so the adapter's leak-vocabulary fix
has no bearing on wake accounting either way); the signature-gate deviation (accepted for this
attempt — manual discipline, bounded by David's standing authorization + the 250-credit breaker).

## What changes

1. **Launch surface: `codex exec --json` (piped stdin, `tools/run_gate0_codex.ps1`) ->
   `codex app-server --listen stdio://` (bidirectional JSON-RPC, `tools/gate0_appserver_arm.py`,
   built on the proven M1 stack `tools/gate0_appserver_client.py` +
   `tools/gate0_appserver_launch.py`).** `tools/run_gate0_codex.ps1` is UNEDITED and remains the
   frozen exec-based reference recipe; it is not run by, or a dependency of, the new launcher.
2. **New runner identity.** The safety-critical file whose hash a launch signature must pin is now
   `tools/gate0_appserver_arm.py` (plus the reused, unmodified `tools/gate0_appserver_launch.py`),
   not `tools/run_gate0_codex.ps1`. See `eval/fixtures/gate0_signature.appserver.json` (a NEW,
   separately named template — never overwrites `eval/fixtures/gate0_signature.example.json`).
3. **Approval mechanism.** `codex exec`'s only path past an MCP tool-call approval prompt is a
   closed stdin that EOF-declines it (`#16685`) — a structural dead end, not a config fix. `codex
   app-server` instead delivers the identical prompt as an answerable JSON-RPC request
   (`mcpServer/elicitation/request` / `item/tool/requestUserInput`); `tools/gate0_appserver_client.py`
   answers `accept`, confirmed end-to-end against a real paid turn
   (`reports/2026-07-23-gate0-appserver-m1-confirmation.md`). No
   `--dangerously-bypass-approvals-and-sandbox` flag is used anywhere.
4. **Recompute-at-launch hashes.** `config_sha256` and `codex_mcp_list_sha256` remain
   launch-invocation-dependent (they always were, even under the exec-based recipe — both embed
   absolute, checkout/OutputDir-specific mount paths) — marked `PENDING`/the same
   `CONSTRAINT:launch-invocation-dependent-recompute-at-signature` sentinel the frozen exec-based
   pins already use, in the two new `eval/fixtures/gate0_expected_pins_<arm>.appserver.json` files.
   The recompute RECIPE is now `tools/gate0_appserver_arm.py`'s own
   `render_full_config_toml()`/`codex_mcp_list_json()`, not the `.ps1`'s here-strings.
5. **A known, flagged gap: no code-enforced signature gate.** `tools/run_gate0_codex.ps1` refuses
   `-PaidExec` unless `Confirm-PaidExecSignature` validates a signed
   `eval/fixtures/gate0_signature.json` against the checkout's live hashes.
   `tools/gate0_appserver_arm.py` does **not** reimplement this mechanical gate — its sole
   fail-closed containment for "refuse to spend un-priced" is `--credit-rate-pin` (identical
   contract to `tools/gate0_appserver_launch.py`'s own B2 guard). `eval/fixtures/
   gate0_signature.appserver.json` is prepared as the same kind of human-authored authorization
   record, but its consumption today is a **manual orchestrator discipline**, not code-enforced.
   Flagged loudly here per this build's own instruction; closing this gap (an equivalent
   `Confirm-PaidExecSignature` check inside the Python launcher) is a candidate follow-up, not done
   in this build.
6. **App-server-necessary config addition (not a loosening): generous MCP timeouts.** The exec path
   never needed this, but `codex app-server` enforces its own per-tool-call/startup timeout
   (`null`/unmeasured server default unless set), and `gate0_world` is lazy-boot: the first real
   tool call inside the paid turn boots PyBoy+ROM (~30-40s) before it can respond. `PR #159` adds
   `tool_timeout_sec = 90` / `startup_timeout_sec = 90` to `render_world_config_toml`'s
   `[mcp_servers.gate0_world]` block — confirmed-real config keys (codex-cli 0.144.3, empirically
   checked via `codex mcp get --json` against a scratch `CODEX_HOME`, not guessed), covering the
   boot with margin without touching any other pinned field.

## What is IDENTICAL (verified, not assumed)

- **Task text, verbatim, both arms.** `tools/gate0_appserver_arm.py::task_text_for()` was hash-
  compared against the frozen `task_sha256` pins during this build:
  red `306751c34627f6d5c6a8c94ac2f714e358f0dcbc5867866c273e434de7f4b7c4` and miniwob
  `845638c874df2f2de2adaebdd1d6c9318c689a46d0032fa76a9393e1e47512d1` — **exact match**, both arms.
- **Common brain config, verbatim.** `render_brain_config_toml("gpt-5.6-sol", <the same
  developer_instructions string>)` was hash-compared against the frozen, model-pinned
  `brain_config_sha256` (`ab7e54c1785f5d8be4352bbe0f85edb37cda68cf56df2128d61df025c1041fc3`,
  identical for both arms per its CONSTANCY_FIELDS status) — **exact match**. (The subtle,
  easy-to-miss detail that made this match on the first correct attempt: `tools/run_gate0_codex.ps1`
  is itself CRLF-line-ended on disk, and PowerShell here-strings preserve the source file's literal
  newline bytes — so the reconstruction had to join lines with `\r\n` internally and a single bare
  `\n` only at the very end, not all-`\n`. Confirmed by direct byte inspection of the `.ps1` file,
  not assumed.)
- **World images, by immutable ID, unchanged.** `sha256:5bfabc7513ce037ed077e955fd34445ef564a7b51037bd7fdddeef0cdb900d00`
  (red, `gb-mcp-world`) and `sha256:8bb3358e1421dc97c72c07809fdef048f63d64bdfddb170c4d0188337fe6fd0f`
  (miniwob, `miniwob-world`) — same tags, same pinned digests, `docker image inspect` only (never
  a container run of the real image in this build).
- **`enabled_tools` allowlists, unchanged, reused from `tools.check_gate0_codex.TOOLS`** (not
  re-declared) — red: `observe, explore, goto, remember, press_button, press_sequence, wait`;
  miniwob: `observe, read_region, whats_changed, click, type_text, press_key, reset_episode`.
- **The scorer.** `eval/score_gate0.py` and `tools/check_gate0_codex.py` are UNEDITED and read
  verbatim (see "the transcript adapter" below for how the new launcher satisfies their fixed
  vocabulary).
- **Bars, baselines, one-attempt law, blank-state, oracle-off-wire — all unchanged.** Cheap bar
  (`<=$5.00`/`<=125` credits Red, `<=$2.00`/`<=50` credits MiniWoB, `<=$7.00`/`<=175` combined
  PASS, `<=250` combined hard breaker); Capability bar (task predicate + `<=2.0x` human wall-clock
  + `<=2.0x` human primitive actions); one attempt per arm, banked as printed; `history.persistence
  = "none"` + `features.memories = false` (blank-agent wipe, verified present in
  `render_brain_config_toml`'s output); the oracle (RAM watch / DOM / reward) stays off the agent
  wire, written only to `world/oracle.jsonl` by the frozen world image, never returned by any tool.
- **The design doc's own tightening law, quoted verbatim**
  (`reports/2026-07-13-minimum-north-star-gate-0-design.md`, C0 section): *"Confirm the human
  baselines and scripted physics fit the bars pinned below; the future pre-registration may
  tighten them but never loosen them."* This amendment tightens nothing and loosens nothing — the
  numeric bars above are byte-identical to the DRAFT pre-registration's table. The one place this
  amendment's OWN containment is at least as strict as the original: `--stall-timeout-s` and
  `--wall-clock-s` on `tools/gate0_appserver_arm.py` both enforce "may only tighten, never loosen"
  against the same pinned defaults (`STALL_TIMEOUT_S=300`, `3600`s) the original `.ps1` uses.

## The transcript adapter decision (flagged per this build's own "honesty > green" instruction)

`tools/check_gate0_codex.py::audit()` (frozen) expects an EXEC-shaped JSONL vocabulary
(`item.completed` / `type: mcp_tool_call` / `turn.completed.usage` with four snake_case token
fields). `codex app-server` speaks JSON-RPC notifications in a different, camelCase shape
(`item/completed` / `type: mcpToolCall` / `thread/tokenUsage/updated`). **This build wrote a real
adapter, not a raw-dump fallback** — `tools.gate0_appserver_arm.
adapt_app_server_notifications_to_exec_shape()` — because a faithful, non-guessed mapping is
possible for the two things this build has concrete captured evidence for (both quoted verbatim in
`reports/2026-07-23-gate0-appserver-m1-confirmation.md`):

- `item/completed` with `item.type == "mcpToolCall"` -> `item.completed` with `type` renamed to
  `mcp_tool_call` (the `server`/`tool` field NAMES already match what `audit()` reads — no
  renaming needed there).
- `thread/tokenUsage/updated` -> tracked, folded into ONE `turn.completed.usage` line at
  `turn/completed`, carrying the four TOKEN_FIELDS from the LATEST cumulative `total`.
- `item/started` is deliberately DROPPED (not translated) — `audit()` has no started-vs-completed
  distinction, so forwarding both would double-count `primitive_action_events` for the same real
  tool call.

**The one loudly-flagged, unresolved gap:** for any OTHER item type — most importantly the model's
own reasoning traces and its final message, both certain to occur in a real many-decision
Red/MiniWoB turn — this repo has **no committed app-server Item/ThreadItem schema dump**
(`tests/fixtures/gate0_appserver/` holds only the four approval/elicitation/permission schemas +
`JSONRPCRequest`/`Response` + `Initialize`/`ThreadStart` — confirmed by listing that directory
during this build). The only confirmed item-type spelling this build has evidence for is
`"mcpToolCall"`. Guessing that reasoning/message items are spelled `"reasoning"`/`"agentMessage"`
and silently mapping them into `audit()`'s exact skip-list strings would be exactly the fabricated
mapping this build was told never to do. The adapter therefore passes any non-`mcpToolCall` item's
`type` field through **verbatim, unmapped** — `audit()`'s own frozen logic will then either skip it
(only if the wire string happens to literally match `"reasoning"`/`"agent_message"`) or flag it
`forbidden_item` (a `NO_LEAK` failure) otherwise. **Practical consequence:** a real, fully-compliant
Red/MiniWoB attempt may score `NO_LEAK` purely because its legitimate reasoning/message items don't
happen to match `audit()`'s hardcoded snake_case strings — not because anything was actually
leaked. **Recommended resolution before the first paid arm launch:** one additional $0-or-cheap
observation of a real turn's item-type vocabulary (e.g. a `--handshake-only` or single-cheap-turn
capture against the stub MCP server with a prompt that forces a visible reasoning/message item)
to either confirm or correct the camelCase-convention guess — not done in this build (the existing
`gate0_stub_mcp_server.py`'s trivial `ping`-only turn does not exercise this path, and this build's
own $0 boundary excludes any live codex invocation).

Both streams are written, nothing lost: `transcript.jsonl` (the pinned scorer path) carries the
ADAPTED stream; `transcript.raw_appserver.jsonl` (a new, non-scorer-pinned sibling file) carries
the complete, untranslated wire tee.

## The MiniWoB human-baseline caveat (Arm W)

The paid-seed (`1000..1004`) human baseline for MiniWoB is **PENDING** —
`eval/fixtures/gate0_paid_source_pins.json`'s own `artifact_sha256.miniwob_human` already reads
`"PENDING_NOT_YET_CAPTURED_paid_seed_human_replay_tool_not_built"`, and per the design doc
("DEV-seed human runs are readiness estimates, never the final denominator"), that replay is
captured **by David, AFTER** the agent's Arm W attempt is banked, on the exact held-out seeds — not
before. Until that replay exists, `eval/score_gate0.py`'s Arm W verdict reads `INSUFFICIENT_SOURCE`
(a source-completeness gap, correctly distinguished from `FAIL_CAPABILITY`/`FAIL_CHEAP`) —
**this is the expected, pre-registered outcome for Arm W's first scoring pass, not a build defect.**
`tools/gate0_appserver_arm.py::build_agent_metrics()` handles the missing human file honestly:
`human_wall_clock_s`/`human_primitive_actions` are written as `null` with an explicit
`human_source_note`, never a fabricated number (verified by
`test_build_agent_metrics_reports_missing_human_file_honestly_not_a_crash`).

## Fold-in fix (orchestrator-requested, after PR #156 merged to `main`)

Mid-build, the orchestrator reported PR #156 (the credit-cap branch this build started from) had
merged to `main`, and asked two review nits from that PR be folded into this one:

1. **Fail loud on regressed cumulative totals.** `AppServerUsageTracker.delta_for()` previously
   clamped a strictly-regressed field (one going DOWN versus the last-seen baseline) to a zero
   delta and continued — silently pricing a stream fault at zero rather than refusing to trust it.
   Fixed to raise `ValueError` instead (still returns an honest zero delta for an exact-duplicate
   notification, which is a real, harmless idempotency case, not a fault). `LiveCreditGuard`
   already wraps this into `MalformedCreditStream` — a kill signal — via its existing
   `except ValueError` handling, so no other wiring changed.
2. **Fixture provenance.** The credit-tracker ground-truth test fixture's comment claimed one
   event's per-field breakdown was "not on record"; it IS on record, verbatim, at
   `reports/2026-07-23-gate0-appserver-m1-confirmation/transcript.jsonl` lines 27 and 31. Both
   `_GT_EVENT_1`/`_GT_EVENT_2` fixtures (and every dependent assertion/comment) were corrected to
   the real captured numbers.

## What was built ($0 only — receipts, not claims)

- `tools/gate0_appserver_arm.py` — the arm runner (`--arm red|miniwob`, `--dry-run`,
  `--seam-check`, `--with-tools-list`, real mode gated on `--model` + `--credit-rate-pin`).
- Two new fixtures: `eval/fixtures/gate0_expected_pins_red.appserver.json`,
  `eval/fixtures/gate0_expected_pins_miniwob.appserver.json` — verified during this build to have
  **zero field diffs** against the frozen originals across all 20 `PIN_FIELDS` (script-checked,
  see commits) — only `config_sha256`/`codex_mcp_list_sha256` stay the same
  launch-invocation-dependent placeholder either fixture already used.
- `eval/fixtures/gate0_signature.appserver.json` — a prepared (unsigned) template, pointing
  `expected_launcher_sha256` at the new runner and adding one field the original template didn't
  need: `expected_appserver_launch_sha256` (the reused M1 client-wiring module).
- `tests/test_gate0_appserver_arm.py` — 49 mock-only, CI-safe tests (dry-run artifact-set shape,
  transcript-adapter fidelity — including the decisive real-transcript regression test, see
  "Adversarial review" above — per-arm soft-cap warnings + the hard 250 ceiling wired together
  exactly as `_run_real` combines them, one-attempt guard including the crashed-after-spending
  hole, TOML-rendering byte-exact regression pins, CLI validation, seam-check with a
  monkeypatched docker probe never a real container).
- Two small fixes to `tools/gate0_appserver_launch.py`/its tests, folded in per orchestrator
  request after PR #156 merged to `main` (see "Fold-in fix" below) — `AppServerUsageTracker` now
  fails loud (raises) on a strictly regressed cumulative token total instead of silently clamping
  it to a zero delta, and the credit-tracker ground-truth test fixture now cites the real captured
  transcript line numbers instead of self-consistent filler.
- Full suite: **1564 passed, 16 skipped** (1515 pre-existing + 49 new; zero regressions).

## Orchestrator commands (none of these were run by this build)

**(a) $0 seam-check per arm** (docker image-inspect only; add `--with-tools-list` once the Docker
daemon is back up to also run the live `tools/list` handshake against the real image):
```
python -m tools.gate0_appserver_arm --arm red --out-dir runs/gate0_seam_check/red --seam-check
python -m tools.gate0_appserver_arm --arm miniwob --out-dir runs/gate0_seam_check/miniwob --seam-check
```

**(b) $0 dry-run per arm** (in-process stub peer, no codex/docker spawned):
```
python -m tools.gate0_appserver_arm --arm red --out-dir runs/gate0_dry_run/red --dry-run --call-count 5
python -m tools.gate0_appserver_arm --arm miniwob --out-dir runs/gate0_dry_run/miniwob --dry-run --call-count 5
```

**(c) The paid Arm R and Arm W runs** (requires David's signed `credit_rate_pin` extracted from a
completed `eval/fixtures/gate0_signature.appserver.json`; `--out-dir` matches
`eval/fixtures/gate0_paid_source_pins.json`'s pinned `audit_paths` exactly, so the frozen scorer
can read the result without any path renaming — **Arm R launches first**, per the design doc's
launch discipline):
```
python -m tools.gate0_appserver_arm --arm red --model gpt-5.6-sol \
    --out-dir runs/gate0_paid/red --credit-rate-pin <path-to-signed-rate-pin.json>
python -m tools.gate0_appserver_arm --arm miniwob --model gpt-5.6-sol \
    --out-dir runs/gate0_paid/miniwob --credit-rate-pin <path-to-signed-rate-pin.json>
```

## Assumption vs. verified fact

**Verified this build (receipts, hash-compared, not asserted on faith):**
- `brain_config_sha256` and `task_sha256` (both arms) reconstructed byte-exact and hash-matched
  against the frozen pins.
- The 20 `PIN_FIELDS` in the two new `*.appserver.json` fixtures are byte-identical to the frozen
  originals (script-diffed, zero mismatches).
- `AppServerUsageTracker`'s duplicate-vs-regression fix and its ground-truth fixture correction
  (real transcript line 27/31 values) — hand-recomputed and test-verified.
- The reentrancy bug in `MultiCallStubAppServerPeer` (Gate0AppServerClient answers synchronously
  and reentrantly, so a naive "pending queue empty" check fires the turn-ending events once per
  call instead of once per turn) — found by direct transcript inspection during this build's own
  smoke test, then fixed and covered by a dedicated regression test.
- The subprocess-hang risk against an unreachable Docker daemon (this host's own current state,
  matching `tools/gate0_appserver_launch.py`'s already-documented "Docker Desktop is down") — found
  by direct observation (an orphaned `docker.exe` process after a 120s tool-timeout), then fixed
  with an explicit `_SUBPROCESS_TIMEOUT_S` backstop on every docker/codex probe call.

**Assumed / not independently verified this build (flagged, not silently trusted):**
- The app-server item-type spelling for anything OTHER than the four now-confirmed types
  (`mcpToolCall`, `agentMessage`, `reasoning`, `userMessage` — see "Adversarial review" above,
  which closed the guaranteed-to-fire version of this gap). A genuinely novel item type (e.g. a
  real shell/web/file leak, or some other content item this build has never observed) is still
  passed through unmapped and left to `audit()`'s fail-closed judgment — narrower than before, but
  still the remaining open flag in this build.
- `config_sha256`/`codex_mcp_list_sha256` recompute parity between this launcher's Python renderer
  and the original `.ps1`'s here-strings for the WORLD config block specifically (the BRAIN config
  block's byte-parity IS verified, above; the world config block's CRLF/quoting convention is
  structurally identical by construction, but was not independently hash-compared against a real
  `.ps1`-produced `config.toml`, since no such file exists in this checkout — `runs/` is
  gitignored and no prior app-server-based Gate 0 launch has occurred).
- Real codex `app-server` behavior on a many-tool-call, many-minute turn (the M1 confirmation was a
  single trivial `ping` call) — the multi-call code path is exercised only via the in-process
  `MultiCallStubAppServerPeer`, never against real `codex.exe`.
