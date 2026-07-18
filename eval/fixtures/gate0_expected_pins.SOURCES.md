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
own tracked source, a value taken from the merged precondition-9 rebuild receipt
(`reports/2026-07-18-gate0-image-rebuild.md`, PR #117 -- a build receipt, not a run receipt) or
extracted live from the rebuilt images themselves, or an explicit `CONSTRAINT:` string for the two
fields that genuinely cannot be pre-pinned because they are functions of the launch invocation.

| Field | Source class | Where |
|---|---|---|
| `arm`, `readiness`, `paid_execution_enabled`, `auth_method`, `critical_config_transport`, `mcp_servers_observed`, `mcp_tools_observed`, `world_image_tag` | code-mandated constant | `tools/check_gate0_codex.py` + `tools/run_gate0_codex.ps1` agree byte-for-byte; cited line numbers in each field's `_source_*` |
| `planned_model` | design-level plan | `HANDOFF.md:53`; no `latest` alias per design doc:96-98 |
| `codex_version`, `codex_path`, `codex_executable_sha256` | fresh independent observation, 2026-07-19 | `codex --version` / `Get-Command codex -CommandType Application -All` / SHA-256 of the resolved `.exe`, run on the launch machine by this PR's author, not read from any receipt |
| `brain_config_sha256`, `task_sha256` | computed from the launcher's own deterministic logic | AST-extracted and evaluated from `tools/run_gate0_codex.ps1`'s `$BrainConfigText`/`$TaskSentence`/`$CommonTask` assignments with `Model='gpt-5.4'`, using the same `[System.Management.Automation.Language.Parser]::ParseFile` technique `tests/test_run_gate0_codex_launcher.py`'s harnesses already use -- not hand-transcribed (the here-string is CRLF-internal / LF-terminal; a hand-typed guess would risk a silently wrong hash) |
| `host_code_sha256`, `image_code_sha256` | computed directly from this repo; image side confirmed against the rebuilt images | `git cat-file blob HEAD:world_mcp.py` / `HEAD:core/miniwob_world.py` at commit `b45b47f3f77690f1678e5476d3ea7b95decd34e3`, matching `world_mcp.py::code_sha256()`'s canonical-git-blob contract. `image_code_sha256` was pinned equal to `host_code_sha256` as the parity target, then CONFIRMED 2026-07-19 by direct extraction against both rebuilt images (`docker run --rm --network none --entrypoint python <id> -c <the launcher's own $HashProgram> /app/world_mcp.py /app/core/miniwob_world.py` on `sha256:5bfabc7513ce...` and on `sha256:8bb3358e1421...` both returned exactly the pinned values), agreeing with `reports/2026-07-18-gate0-image-rebuild.md`'s 4/4 parity table |
| `world_image_id` | RESOLVED 2026-07-19 from the merged precondition-9 receipt | `reports/2026-07-18-gate0-image-rebuild.md` (PR #117, merged): `gb-mcp-world` = `sha256:5bfabc7513ce037ed077e955fd34445ef564a7b51037bd7fdddeef0cdb900d00`, `miniwob-world` = `sha256:8bb3358e1421dc97c72c07809fdef048f63d64bdfddb170c4d0188337fe6fd0f`, both rebuilt from a clean checkout of `main@154e8df`. Independently confirmed on the launch machine via `docker image inspect --format '{{.Id}}' <tag>` returning the same digests |
| `tool_schema_sha256` | RESOLVED 2026-07-19 by live extraction against the rebuilt images | Ran the launcher's exact `tools/list` handshake (`tools/run_gate0_codex.ps1:348-375`: same 3-line JSON-RPC, `docker run -i --rm --network none`, per-arm mount shape) against each frozen image ID, serialized with PowerShell 5.1 `ConvertTo-Json -Depth 20 -Compress` + trailing LF, UTF-8 no BOM (the launcher's exact `mcp-tools.json` recipe), then SHA-256: red = `e55bb8193f0c3ecb531519db2b93a3a597dbd97d9cb42468e63334c1ae7ffa71`, miniwob = `6c3d413199eae79f197ec219019bc6e8f82bb947d51f601f319a52bc5647e805`. Both observed inventories matched the frozen allowlists exactly. Corroboration only (not a source): byte-identical to the 2026-07-14 receipts' `mcp-tools.json` files -- expected, since the schemas are a pure function of the parity-identical `world_mcp.py` |
| `config_sha256`, `codex_mcp_list_sha256` | `CONSTRAINT:` (launch-invocation-dependent; recompute at signature) | No longer blocked on the image digest (frozen above) -- blocked on the launch invocation itself. `config.toml` embeds, verbatim, the docker mount source paths derived from the launch `-OutputDir` (`$WorldDir = OutputDir\world`) plus the launching checkout's absolute paths (`$Roms`/`$State`/`$Seeds`, `cwd=$RepoRoot`) (`tools/run_gate0_codex.ps1:244-256,292-302`); and `codex mcp list --json` was empirically shown 2026-07-19 (codex-cli 0.144.3, isolated `CODEX_HOME`, the exact `-c` override transport) to echo the full transport `args` array and `cwd` verbatim in its JSON output. Because one expected-pins file per arm serves BOTH scoring modes -- whose pinned `artifacts_dir` differ (`runs/gate0_readiness_dev/<arm>` vs `runs/gate0_paid/<arm>`) -- a single pre-pinned value would structurally fail one of the two modes. Each field's `_source_*` comment carries the deterministic recompute recipe for signature time, once the launch checkout + per-mode OutputDir are fixed. The `CONSTRAINT:` strings remain intentionally never-a-valid-hash, so they fail closed until then |

## Empirical corroboration (not a source -- a check)

Running `tools/check_gate0_codex.py` against the pre-existing, untouched 2026-07-14 free-handshake
receipts (`runs/gate0_readiness_2026-07-14/{red-v3,miniwob-v2}/` in the `ai-pokemon-red` checkout,
read-only, never used as a SOURCE for any pin value per the INDEPENDENCE LAW above), across the
three states of this file:

```
# before this PR (no expected-pins file existed at all):
constancy_failures: ["malformed_expected_pins", "expected_pins_malformed"]

# first freeze (pre-#117, six CONSTRAINT placeholders), both arms:
constancy_failures: ["pin_mismatch:config_sha256", "pin_mismatch:codex_mcp_list_sha256",
                      "pin_mismatch:tool_schema_sha256", "pin_mismatch:world_image_id",
                      "pin_mismatch:host_code_sha256", "pin_mismatch:image_code_sha256"]

# current (post-#117 resolution), both arms:
constancy_failures: ["pin_mismatch:config_sha256", "pin_mismatch:codex_mcp_list_sha256",
                      "pin_mismatch:world_image_id",
                      "pin_mismatch:host_code_sha256", "pin_mismatch:image_code_sha256"]
```

No `expected_missing:*` on either arm (all 20 fields present). `tool_schema_sha256` now MATCHES the
real receipts (15 of 20 fields matching a receipt none of these values were derived from). The five
remaining mismatches are all correct behavior, in two classes:

- **Genuine staleness of the 2026-07-14 receipts (3):** `world_image_id` -- those receipts pin the
  SUPERSEDED pre-rebuild images (`sha256:8701e664...` red, `sha256:7128be60...` miniwob), while the
  pin now holds PR #117's rebuilt digests; and `host_code_sha256`/`image_code_sha256` -- those
  receipts were produced pre-#114-canonical-fix with raw working-tree-byte hashing on a CRLF
  checkout (`6290b2b9...`/`09f5d28e...`), while the pins hold the canonical git-blob values the
  post-`d75e8be` launcher now produces (and which both rebuilt images were directly confirmed to
  contain). A FRESH free handshake against the rebuilt images would match all three; the stale
  receipts failing is the pin doing its job.
- **Run-time-only CONSTRAINT fields (2):** `config_sha256`/`codex_mcp_list_sha256`, launch-invocation
  dependent per the table above -- fail closed by design until frozen at signature.

## Freeze point

Both files are frozen against commit `b45b47f3f77690f1678e5476d3ea7b95decd34e3` (`origin/main` at the
time this PR branched); `world_image_id`/`tool_schema_sha256`/`image_code_sha256` confirmations were
performed 2026-07-19 against the PR #117 images (built from `main@154e8df`, whose `world_mcp.py` and
`core/miniwob_world.py` blobs are identical to `b45b47f`'s). If `world_mcp.py`,
`core/miniwob_world.py`, or `tools/run_gate0_codex.ps1` change before the actual Gate 0 launch,
`host_code_sha256`/`image_code_sha256`/`brain_config_sha256`/`task_sha256` must be re-derived the
same way (re-run the AST extraction / `git cat-file`), the images rebuilt, and
`world_image_id`/`tool_schema_sha256` re-extracted -- never hand-edited.
