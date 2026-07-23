#
# gate0_appserver_handshake_smoke.ps1 -- $0 REAL `codex app-server` HANDSHAKE SMOKE.
#
# WHAT THIS DOES: spawns the REAL `codex app-server` binary, drives `initialize` (declaring the
# experimentalApi/mcpServerOpenaiFormElicitation capabilities -- see tools/gate0_appserver_client.py)
# and `thread/start` (approvalsReviewer="user"), registers the STUB MCP server ONLY (one trivial
# `ping` tool, tools/gate0_stub_mcp_server.py -- PRIMARY path per the 2026-07-23 orchestrator
# update: Docker Desktop is down, so the Gate 0 `gb-mcp-world` container is unavailable), prints
# exactly what the real binary returns, then EXITS. It never calls `--handshake-only`'s sibling
# turn/start -- NO model turn is run, NO tokens are spent, NO ChatGPT-subscription quota is used
# beyond whatever `codex app-server`/`initialize` itself costs (nothing, per codex's own docs: the
# handshake is local process bring-up, not a model call).
#
# NOT run by the Sonnet build session that wrote this file (CRITICAL BOUNDARY in that session's
# task: "no real-codex handshake ... run by you"). This script is for THE ORCHESTRATOR to run.
#
# Preconditions this script checks before spawning anything (mirrors the spirit, not the code, of
# tools/run_gate0_codex.ps1's own safety checks -- that pinned file is never invoked or edited by
# this script):
#   - `codex` resolves on PATH and reports a parseable version.
#   - Neither OPENAI_API_KEY nor CODEX_API_KEY is set (Gate 0 requires ChatGPT subscription auth,
#     never an API key -- a key in the environment is refused, matching the pinned launcher's own
#     `throw` for this exact condition).
#   - `codex login status` proves ChatGPT auth (not an API key).
#   - Uses an ISOLATED `CODEX_HOME` (this script's own `-OutputDir\codex-home`, or `-CodexHome` if
#     given), NEVER the user's real `~/.codex` -- tools/gate0_appserver_launch.py sets/restores the
#     `CODEX_HOME` env var around the child process; nothing here or there mutates
#     `~/.codex/config.toml`. The user's real `~/.codex/auth.json` credential is still what
#     authenticates (Codex auth is observed through whichever CODEX_HOME points at it -- an
#     isolated CODEX_HOME with no `auth.json` of its own will FAIL to authenticate). N3 fix: the
#     launcher itself now COPIES `-CodexAuthSource` (default `~/.codex/auth.json`) into the
#     isolated home when it lacks one -- never pastes a token in cleartext, never mutates the
#     source file or `~/.codex/config.toml`.
#
# Usage:
#   pwsh tools/gate0_appserver_handshake_smoke.ps1 -Model gpt-5.6-sol -OutputDir runs/gate0_appserver_smoke
#
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[A-Za-z0-9][A-Za-z0-9._-]{1,127}$')]
    [string]$Model,

    [Parameter(Mandatory = $true)]
    [string]$OutputDir,

    # N3: isolated CODEX_HOME override (default <OutputDir>\codex-home, set by the launcher).
    [string]$CodexHome = '',

    # N3: where to copy auth.json FROM when the isolated CodexHome lacks one (default
    # ~/.codex/auth.json inside tools/gate0_appserver_launch.py). Never the destination.
    [string]$CodexAuthSource = '',

    [string]$PythonExe = 'python'
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

if ($Model -match '(?i)(^|[-_.])latest($|[-_.])') {
    throw 'Model must be an explicit model identifier, not a latest alias.'
}

$ResolvedCodex = (Get-Command codex -CommandType Application -All -ErrorAction Stop |
    Where-Object { ([string]$_.Source).EndsWith('.exe', [StringComparison]::OrdinalIgnoreCase) })
if (@($ResolvedCodex).Count -ne 1) {
    throw "Expected exactly one Codex .exe application candidate; found $(@($ResolvedCodex).Count)."
}
$versionText = (& $ResolvedCodex[0].Source --version 2>$null | Out-String).Trim()
if ($LASTEXITCODE -ne 0 -or $versionText -notmatch '^codex(?:-cli)?\s+[0-9][0-9A-Za-z.+-]*$') {
    throw 'Codex version is unavailable or not safely parseable.'
}
Write-Output "codex version: $versionText"

if ($env:OPENAI_API_KEY -or $env:CODEX_API_KEY) {
    throw 'OPENAI_API_KEY or CODEX_API_KEY is set; Gate 0 requires ChatGPT subscription authentication, not an API key.'
}
# PS-5.1 fix: `& codex login status 2>&1` under Windows PowerShell 5.1 with
# $ErrorActionPreference='Stop' promotes ANY stderr line from a native command to a terminating
# NativeCommandError, even on exit code 0 -- this threw before the login-status text was ever
# inspected. .NET Process redirection (same pattern tools/run_gate0_codex.ps1's own
# Invoke-RedirectedProcess uses) sidesteps PowerShell's native-command stderr handling entirely, so
# it behaves identically under powershell.exe 5.1 and pwsh 7.
$loginStartInfo = [Diagnostics.ProcessStartInfo]::new()
$loginStartInfo.FileName = $ResolvedCodex[0].Source
$loginStartInfo.Arguments = 'login status'
$loginStartInfo.UseShellExecute = $false
$loginStartInfo.RedirectStandardOutput = $true
$loginStartInfo.RedirectStandardError = $true
$loginStartInfo.CreateNoWindow = $true
$loginProcess = [Diagnostics.Process]::new()
$loginProcess.StartInfo = $loginStartInfo
[void]$loginProcess.Start()
$loginStdOutTask = $loginProcess.StandardOutput.ReadToEndAsync()
$loginStdErrTask = $loginProcess.StandardError.ReadToEndAsync()
$loginProcess.WaitForExit()
$loginText = (([string]$loginStdOutTask.GetAwaiter().GetResult() + "`n" +
    [string]$loginStdErrTask.GetAwaiter().GetResult())).Trim()
$loginProcess.Dispose()
if ($loginText -notmatch '(?i)\bchatgpt\b' -or $loginText -match '(?i)\bapi(?:[ -]?key)?\b') {
    throw 'Codex login status did not prove ChatGPT subscription authentication.'
}
Write-Output 'codex login status: ChatGPT subscription auth confirmed.'

Write-Output ''
Write-Output '=== Spawning REAL codex app-server for a HANDSHAKE-ONLY smoke (no turn, no spend) ==='
$pyArgs = @(
    '-m', 'tools.gate0_appserver_launch',
    '--handshake-only',
    '--mcp', 'stub',
    '--model', $Model,
    '--out-dir', $OutputDir
)
if ($CodexHome) { $pyArgs += @('--codex-home', $CodexHome) }
if ($CodexAuthSource) { $pyArgs += @('--codex-auth-source', $CodexAuthSource) }
& $PythonExe @pyArgs
$exitCode = $LASTEXITCODE
Write-Output ''
Write-Output "verdict.json / transcript.jsonl / audit.jsonl written under: $OutputDir"
Write-Output "launcher exit code: $exitCode"
exit $exitCode
