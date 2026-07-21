# Gate 0 fresh free-handshake receipts (pinned model gpt-5.6-sol) - 2026-07-21

This is a `$0` addendum. No Codex execution, paid-held-out seed, API key, or model call was used --
both receipts below come from `tools/run_gate0_codex.ps1`'s free `codex mcp list --json` +
direct-image `tools/list` handshake path only, which every receipt still self-declares
(`readiness=NO_GO_INSUFFICIENT_WAKES`, `paid_execution_enabled=false`).

## Why

PR #118 (merged to `main` at `0dff594`) pinned the Gate 0 brain to `planned_model=gpt-5.6-sol` and
froze independent expected-pins JSON (`eval/fixtures/gate0_expected_pins_{red,miniwob}.json`)
against the rebuilt world images. Both fixtures' `_source_*` notes flag the 2026-07-14 receipts
(`red-v3`, `miniwob-v2`) as correctly stale on exactly 5 of the 20 `PIN_FIELDS`:
`planned_model`, `brain_config_sha256`, `world_image_id`, `host_code_sha256`, `image_code_sha256`.
This addendum re-runs the free handshake for both arms with the now-pinned model against the
rebuilt images to produce receipts that clear those 5 fields, then re-runs the readiness checker.

## Preconditions verified before launch

- `git branch --show-current` -> `main`; `git log --oneline -1` -> `0dff594 Merge pull request #118
  ...`; tree clean (`git status --porcelain=v1 -uno` empty) after `git pull --ff-only`.
- `docker image inspect --format '{{.Id}}' gb-mcp-world` -> `sha256:5bfabc7513ce037ed077e955fd34445ef564a7b51037bd7fdddeef0cdb900d00`
  (matches the frozen `gate0_expected_pins_red.json:world_image_id`).
- `docker image inspect --format '{{.Id}}' miniwob-world` -> `sha256:8bb3358e1421dc97c72c07809fdef048f63d64bdfddb170c4d0188337fe6fd0f`
  (matches `gate0_expected_pins_miniwob.json:world_image_id`; a `miniwob-mcp-world` tag alias
  resolves to the same image ID).
- `codex --version` -> `codex-cli 0.144.3`; `codex login status` -> `Logged in using ChatGPT`;
  `OPENAI_API_KEY` / `CODEX_API_KEY` both unset.

## Receipts (fresh, this addendum)

Command (identical shape for both arms, only `-Arm`/`-OutputDir` differ):

```
tools/run_gate0_codex.ps1 -Arm <red|miniwob> -Model gpt-5.6-sol -OutputDir runs/gate0_readiness_2026-07-14/<red-v4|miniwob-v3>
```

Both runs exited `1` with `readiness=NO_GO_INSUFFICIENT_WAKES` / `paid_execution_enabled=false` --
the launcher's fail-closed success path (see `tools/run_gate0_codex.ps1:416-419`).

| Arm | Receipt path | Receipt SHA-256 | World image ID |
|---|---|---|---|
| red | `runs/gate0_readiness_2026-07-14/red-v4/handshake-receipt.json` | `6051fcb759509cdf7adcd3ad90e93737d3e4081ef9ad0b7c36fc8149bc64cb5a` | `sha256:5bfabc7513ce037ed077e955fd34445ef564a7b51037bd7fdddeef0cdb900d00` |
| miniwob | `runs/gate0_readiness_2026-07-14/miniwob-v3/handshake-receipt.json` | `b80af26a3986748a96c78c13cf95e85f74d60ae9b87c9d270fdcaa7ca96b9325` | `sha256:8bb3358e1421dc97c72c07809fdef048f63d64bdfddb170c4d0188337fe6fd0f` |

Both new receipts (`schema_version=2`) observe `planned_model=gpt-5.6-sol`,
`brain_config_sha256=ab7e54c1785f5d8be4352bbe0f85edb37cda68cf56df2128d61df025c1041fc3`, and
`host_code_sha256 == image_code_sha256 == {"/app/world_mcp.py":
"967866ab5ddcfcef17747aab1d83070a95a32c2cb05bc0b6252defce7b519fc9", "/app/core/miniwob_world.py":
"f98b0dc9846bff0fceb96c8f77eee8b4261b9db894abd793a8d7b1145a23ce54"}` -- all five previously-stale
fields now match the frozen expected pins verbatim (confirmed mechanically below, not just by eye).
`runs/` is gitignored; these receipts are local-only, append-only additions (`red-v1`..`red-v4`,
`miniwob-v1`..`miniwob-v3` all still present, nothing overwritten).

## Readiness re-run (`tools/check_gate0_codex.py`, this addendum)

No real transcript exists for either receipt (the launcher never calls `codex exec`; a free
handshake produces no Codex-run JSONL). Invoked with an empty placeholder transcript file so the
constancy/artifact/peer checks -- the fields this addendum actually changed -- run and are reported
in full; the resulting `leak_failures:["transcript_empty"]` / `accounting_failures` /
`overall:"NO_LEAK"` are an artifact of that placeholder and of no paid run having happened, not a
new finding (a full paid-run audit is out of scope for a `$0` handshake and remains gated on
precondition 4's wiring, below).

```
uv run --frozen python tools/check_gate0_codex.py <empty.jsonl> \
  runs/gate0_readiness_2026-07-14/red-v4/handshake-receipt.json \
  eval/fixtures/gate0_expected_pins_red.json \
  runs/gate0_readiness_2026-07-14/red-v4 \
  --arm red --peer-receipt runs/gate0_readiness_2026-07-14/miniwob-v3/handshake-receipt.json
```

Red result (verbatim):

```json
{"accounting_failures": ["no_observable_token_usage"], "arm": "red", "constancy_failures": ["pin_mismatch:config_sha256", "pin_mismatch:codex_mcp_list_sha256"], "leak_failures": ["transcript_empty"], "no_leak": "NO_LEAK", "overall": "NO_LEAK", "peer_constancy": "PASS", "run_failures": [], "schema_version": 2, "token_usage": {"cached_input_tokens": 0, "input_tokens": 0, "output_tokens": 0, "reasoning_output_tokens": 0}, "token_usage_events": 0, "wake_accounting": "INSUFFICIENT_WAKES", "wakes": null}
```

MiniWoB result (verbatim, same command shape with `--arm miniwob`, the miniwob pins/artifacts dir,
and `--peer-receipt` pointing at the red-v4 receipt):

```json
{"accounting_failures": ["no_observable_token_usage"], "arm": "miniwob", "constancy_failures": ["pin_mismatch:config_sha256", "pin_mismatch:codex_mcp_list_sha256"], "leak_failures": ["transcript_empty"], "no_leak": "NO_LEAK", "overall": "NO_LEAK", "peer_constancy": "PASS", "run_failures": [], "schema_version": 2, "token_usage": {"cached_input_tokens": 0, "input_tokens": 0, "output_tokens": 0, "reasoning_output_tokens": 0}, "token_usage_events": 0, "wake_accounting": "INSUFFICIENT_WAKES", "wakes": null}
```

## Before / after

| Field | 2026-07-14 (`red-v3`/`miniwob-v2`) | 2026-07-21 (`red-v4`/`miniwob-v3`) |
|---|---|---|
| `planned_model` | `gpt-5.4` (mismatch) | `gpt-5.6-sol` (matches pin) |
| `brain_config_sha256` | `eb264d8b...` (mismatch) | `ab7e54c1...` (matches pin) |
| `world_image_id` (red) | `sha256:8701e664...` (superseded pre-rebuild image) | `sha256:5bfabc75...` (matches pin) |
| `world_image_id` (miniwob) | `sha256:7128be60...` (superseded pre-rebuild image) | `sha256:8bb3358e...` (matches pin) |
| `host_code_sha256` / `image_code_sha256` | `6290b2b9.../09f5d28e...` (mismatch, pre-rebuild code) | `967866ab.../f98b0dc9...` (matches pin, both fields equal each other and the pin) |
| `constancy_failures` (checker output) | not run against a frozen pins file at that time (none existed yet) | exactly `["pin_mismatch:config_sha256", "pin_mismatch:codex_mcp_list_sha256"]` for both arms |

All 5 previously-flagged stale fields are cleared. `constancy_failures` reduces to exactly the 2
fields the pin files themselves mark `CONSTRAINT:launch-invocation-dependent-recompute-at-signature`
(`config_sha256`, `codex_mcp_list_sha256` -- both embed the launch `OutputDir`'s absolute mount
paths, so no single pre-frozen value can ever match them; see each expected-pins file's
`_source_config_sha256`/`_source_codex_mcp_list_sha256`). `peer_constancy: "PASS"` for both arms --
every `CONSTANCY_FIELDS` value (`readiness`, `paid_execution_enabled`, `auth_method`,
`planned_model`, `codex_version`, `codex_path`, `codex_executable_sha256`,
`critical_config_transport`, `brain_config_sha256`) is identical between the red and miniwob
receipts, as required.

## What remains before launch (no rounding up to GO)

Not a `GO`. Remaining, in full, no items omitted:

1. **By-design CONSTRAINT fields (signature-time, not a defect):** `config_sha256` and
   `codex_mcp_list_sha256` structurally cannot be pre-frozen (they embed the launch invocation's
   absolute `OutputDir`/mount paths) -- both pin files document the deterministic recompute recipe
   to apply "once the launch checkout + per-mode `OutputDir` are fixed" at actual signature time.
2. **Human baselines (readiness preconditions R0/W0, prereg precondition 6):** `runs/gate0_human_baseline/`
   does not exist on this machine. `DAVID_BASELINES.md` documents the two capture scripts
   (`tools/capture_gate0_baseline_red.py`, `tools/capture_gate0_baseline_miniwob.py`); neither has
   been run yet. Still **NOT MET**.
3. **Wake accounting / live-credit-breaker wiring (prereg precondition 4):** PR #118 shipped the
   breaker component (`tools/gate0_credit_breaker.py`) and a synthetic-stream dry-run TRIP proof
   (`reports/2026-07-19-gate0-live-breaker-dry-run.md`), but status is explicitly **COMPONENT MET --
   WIRING PENDING**: the paid launcher itself (streaming `codex exec --json` through an iterator-fed
   `run_breaker(raise_on_trip=True)` that kills the child on any breaker exception) does not exist
   yet. The PR #118 body's 4a-4d checklist (token->credit rate pinned for `gpt-5.6-sol`; iterator-fed
   wiring with child-termination; a wired-path TRIP receipt against a zero-spend stub emitter; the
   300s stall backstop) must all clear first. `tools/run_gate0_codex.ps1:403-414` carries this same
   status note verbatim.
4. This addendum's own readiness re-run used a placeholder empty transcript (no paid run occurred),
   so `wake_accounting=INSUFFICIENT_WAKES`, `wakes=null`, and `accounting_failures` /
   `leak_failures` are expected artifacts of that, not new findings -- a real accounting/no-leak
   audit only becomes meaningful once an actual paid transcript exists, which is gated on item 3.

Net: C0's constancy sub-check (the 20 `PIN_FIELDS` minus the 2 by-design CONSTRAINT fields) is now
clean for both arms with the pinned model and rebuilt images. R0/W0 human baselines and the live
breaker's launcher-side wiring remain the open, launch-blocking gaps -- unchanged in kind from the
2026-07-18 pre-reg's precondition table, just no longer confounded by a stale model/image pin.
