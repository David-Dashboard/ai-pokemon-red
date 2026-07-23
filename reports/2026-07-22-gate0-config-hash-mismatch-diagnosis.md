# Gate 0 `-PaidExec` config_sha256 mismatch — diagnosis (2026-07-22)

**$0 diagnosis only.** No `codex exec` or live `codex` call ran this session (a direct `codex
login status` probe was blocked by the harness classifier and was not routed around). Findings come
from reading `tools/run_gate0_codex.ps1`, existing on-disk artifacts, and a pure string/hash
reconstruction script (zero codex/docker-exec calls). The real launcher (signature-hash-checked)
was never modified; instrumentation lived only in scratch copies under the session scratchpad.

## Repro (as reported)

Free handshake `-Arm red -Model gpt-5.6-sol -OutputDir runs\gate0_paid\red` (no `-PaidExec`)
reproducibly wrote `config_sha256 = f304512389d792ba1e93cebc132885cd603b5c66527d6e23e77b63ca6f47aa1f`
— matching `eval/fixtures/gate0_signature.json`'s `expected_config_sha256` (its `notes` field says
it was captured "from the free handshake at runs/gate0_paid/red, 2026-07-22"). A later `-PaidExec`
attempt at the same `-OutputDir` text computed a different value, tripping
`Confirm-PaidExecSignature` at `tools/run_gate0_codex.ps1:220-221`.

## Root cause

`config_sha256` is **not** a fixed function of (commit, arm, model) — it embeds the docker
`--mount` bind source for `/app/world` verbatim (`$WorldDir = Join-Path $OutputDir 'world'`, line
608, baked into `config.toml`'s `[mcp_servers.gate0_world]` `args`, line 723/743).
`$OutputDir = [IO.Path]::GetFullPath($OutputDir)` (line 605) resolves a **relative** `-OutputDir`
against the shell's **current directory**, while `$RepoRoot` (line 604) anchors to `$PSScriptRoot`
instead — two anchors for one launch. `-PaidExec` is never read before line 847 (full-file grep) —
not the cause, only where the hash gets checked: run it from a cwd even slightly different from the
free-mode probe that seeded the signature, and `config_sha256` (plus `codex_mcp_list_sha256`, same
transport) silently changes; `Confirm-PaidExecSignature` reports only a bare mismatch, no cwd hint.

Corroborated by prior work already in-repo: `eval/fixtures/gate0_expected_pins_red.json:31-32`
marks both fields `CONSTRAINT:launch-invocation-dependent-recompute-at-signature` ("config.toml
embeds... mount source paths derived from the launch `-OutputDir`... a single value would
structurally fail one of the two modes"); `reports/2026-07-21-gate0-fresh-handshakes.md` hit the
identical `pin_mismatch:config_sha256`/`codex_mcp_list_sha256` on a receipt from a different
`OutputDir` (no test covers cwd-anchor sensitivity).

## Byte-exact proof (reconstruction, no codex/docker exec)

A scratch `Build-ConfigText` script (Quote-Toml/here-string templates copied verbatim from lines
693-733, `$RepoRoot`/`$Arm`/`$Model`/`$ImageId` fixed at real, live-confirmed values) reconstructs
`config.toml` from pure string ops — validated **byte-for-byte** against the real captured
`runs/gate0_paid/red_probe/launch/.codex/config.toml`
(`beb1226367d8f51d43e3bef67e745740097cf72cef3008c68ff74b2409cc537d`, exact match). Applied to
`-OutputDir runs\gate0_paid\red`:

| Invocation cwd | Resolved OutputDir | config_sha256 |
|---|---|---|
| repo root | `...\ai-pokemon-red\runs\gate0_paid\red` | `f304512389...c47aa1f` (matches signed pin) |
| repo root`\tools` | `...\ai-pokemon-red\tools\runs\gate0_paid\red` | `2acd0bdef7...aa6e7949c` |

Everything else (model, features, `cwd=$RepoRoot`, `enabled_tools`, image id, other two mounts) is
byte-identical; only the `/app/world` mount's `source=` path differs — enough to explain the bug.

## Recommended fix — process, not code (b)

Config generation (693-733) is correct and deterministic *given* a fixed absolute `OutputDir` — no
code change needed there. The gap is procedural: sign from a value guaranteed launch-exact, not a
separate free-mode probe under a possibly different cwd. `Confirm-PaidExecSignature` (847-850)
fails closed before any spawn (`codex exec` only at line 882), so a `-PaidExec` attempt with a
stale/absent signature is guaranteed zero-spend and already writes its own `handshake-receipt.json`
(line 828) with this run's real hashes before throwing. Recommended: (1) always pass `-OutputDir`
as a fully-qualified absolute path; (2) sign `eval/fixtures/gate0_signature.json` from that exact
receipt (or the pure recompute above), never a separate earlier free-mode run; (3) re-run
`-PaidExec` immediately after, same shell, no `cd` in between. Future PR (not applied here):
`Confirm-PaidExecSignature` should name the resolved `$OutputDir` on mismatch, not a bare hex string.

## Zero-spend confirmation

No `codex exec`, no real-launcher `-PaidExec`, no direct `codex` CLI call this session (`docker
image inspect`, read-only, confirmed `gb-mcp-world`'s image id stable since the 2026-07-18 rebuild).
