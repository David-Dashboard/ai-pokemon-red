# Gate 0 expected-pins source citations (pre-reg precondition 3)

`eval/fixtures/gate0_expected_pins_red.json` and `gate0_expected_pins_miniwob.json` each carry a
`_source_<field>` comment key next to every one of `tools.check_gate0_codex.PIN_FIELDS`'s 20 fields
(the pre-reg text says 19; the live tuple has 20 -- not something this PR corrects, just noting the
drift). This file is the short index; read the JSON's own `_source_*` keys for the full citation
text per field.

**INDEPENDENCE LAW.** No value in either file was copied from
`runs/gate0_readiness_2026-07-14/red-v3/handshake-receipt.json`,
`runs/gate0_readiness_2026-07-14/miniwob-v2/handshake-receipt.json`, or any other observed run
receipt. Every field below is either a code-mandated constant, a value freshly and independently
observed on 2026-07-19 (not read from a receipt file), a value computed directly from this repo's
own tracked source, or an explicit `CONSTRAINT:` string for a field that genuinely cannot be known
before precondition 9 (world image rebuild) lands.

| Field | Source class | Where |
|---|---|---|
| `arm`, `readiness`, `paid_execution_enabled`, `auth_method`, `critical_config_transport`, `mcp_servers_observed`, `mcp_tools_observed`, `world_image_tag` | code-mandated constant | `tools/check_gate0_codex.py` + `tools/run_gate0_codex.ps1` agree byte-for-byte; cited line numbers in each field's `_source_*` |
| `planned_model` | design-level plan | `HANDOFF.md:53`; no `latest` alias per design doc:96-98 |
| `codex_version`, `codex_path`, `codex_executable_sha256` | fresh independent observation, 2026-07-19 | `codex --version` / `Get-Command codex -CommandType Application -All` / SHA-256 of the resolved `.exe`, run on the launch machine by this PR's author, not read from any receipt |
| `brain_config_sha256`, `task_sha256` | computed from the launcher's own deterministic logic | AST-extracted and evaluated from `tools/run_gate0_codex.ps1`'s `$BrainConfigText`/`$TaskSentence`/`$CommonTask` assignments with `Model='gpt-5.4'`, using the same `[System.Management.Automation.Language.Parser]::ParseFile` technique `tests/test_run_gate0_codex_launcher.py`'s harnesses already use -- not hand-transcribed (the here-string is CRLF-internal / LF-terminal; a hand-typed guess would risk a silently wrong hash) |
| `host_code_sha256`, `image_code_sha256` | computed directly from this repo | `git cat-file blob HEAD:world_mcp.py` / `HEAD:core/miniwob_world.py` at commit `b45b47f3f77690f1678e5476d3ea7b95decd34e3`, matching `world_mcp.py::code_sha256()`'s canonical-git-blob contract; `image_code_sha256` is pinned equal to `host_code_sha256` because that equality IS the parity requirement precondition 9's rebuild must hit |
| `config_sha256`, `codex_mcp_list_sha256`, `tool_schema_sha256`, `world_image_id` | `CONSTRAINT:` (cannot be known pre-run) | These transitively embed the Docker image digest (`config.toml`'s `mcp_servers.gate0_world.args` contains the resolved `$ImageId`, and `codex mcp list --json` is invoked with the same image-ID-bearing overrides) or ARE the image digest itself. Image digests are build-process-dependent, not a pure function of tracked source, and precondition 9 (image rebuild) has not landed. Each `CONSTRAINT:` string is intentionally never a valid hash/digest, so it can never accidentally satisfy an equality check -- these four fields fail closed until precondition 9's rebuild report supplies the real values (see `reports/2026-07-18-gate0-image-rebuild.md`, a parallel PR -- referenced, not invented) |

## Empirical corroboration (not a source -- a check)

Running `tools/check_gate0_codex.py` against the pre-existing, untouched 2026-07-14 free-handshake
receipts (`runs/gate0_readiness_2026-07-14/{red-v3,miniwob-v2}/` in the `ai-pokemon-red` checkout,
read-only, never used as a SOURCE for any pin value per the INDEPENDENCE LAW above) shows every
independently-frozen field matching that real prior receipt on both arms, with mismatches confined
to exactly the six image-coupled fields this file marks `CONSTRAINT:`:

```
# before this PR (no expected-pins file existed at all):
constancy_failures: ["malformed_expected_pins", "expected_pins_malformed"]

# after (this PR's eval/fixtures/gate0_expected_pins_{red,miniwob}.json), both arms:
constancy_failures: ["pin_mismatch:config_sha256", "pin_mismatch:codex_mcp_list_sha256",
                      "pin_mismatch:tool_schema_sha256", "pin_mismatch:world_image_id",
                      "pin_mismatch:host_code_sha256", "pin_mismatch:image_code_sha256"]
```

No `expected_missing:*` on either arm (all 20 fields present), and 14 of 20 fields -- including
`planned_model`, `codex_version`, `codex_path`, `codex_executable_sha256`, `brain_config_sha256`,
`task_sha256` -- matched a real receipt this file's values were never derived from. The remaining six
are exactly the ones this document already says are blocked on precondition 9 (image rebuild); they
are expected to mismatch until that lands, not a bug.

## Freeze point

Both files are frozen against commit `b45b47f3f77690f1678e5476d3ea7b95decd34e3` (`origin/main` at the
time this PR branched). If `world_mcp.py`, `core/miniwob_world.py`, or `tools/run_gate0_codex.ps1`
change before the actual Gate 0 launch, `host_code_sha256`/`image_code_sha256`/`brain_config_sha256`/
`task_sha256` must be re-derived the same way (re-run the AST extraction / `git cat-file`), not
hand-edited.
