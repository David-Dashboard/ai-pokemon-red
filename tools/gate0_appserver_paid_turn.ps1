#
# gate0_appserver_paid_turn.ps1 -- THE ONE BOUNDED PAID TURN. SPENDS REAL CHATGPT-SUBSCRIPTION
# QUOTA. NOT run by the Sonnet build session that wrote this file (CRITICAL BOUNDARY: "no billed
# turn / no real-codex execution by you"). This script is for THE ORCHESTRATOR to run, deliberately,
# once, after reading reports/2026-07-23-gate0-appserver-launch-runbook.md in full.
#
# WHAT THIS DOES: spawns REAL `codex app-server`, registers the STUB MCP server (one trivial
# `ping` tool -- PRIMARY path per the 2026-07-23 orchestrator update: Docker Desktop is down, so
# the Gate 0 `gb-mcp-world` container is unavailable; see -Mcp docker below for when it's back),
# runs `initialize` -> `thread/start` (approvalsReviewer="user") -> `turn/start` with a prompt that
# makes the brain call the `ping` tool exactly once, answers whatever approval/elicitation
# requests arrive (the #15824-regression "Approve app tool call?" prompt this whole build exists
# to answer), and scores whether that ONE MCP tool call COMPLETED (the confirmation) vs was
# CANCELLED (exec's failure mode reproducing under app-server too, which would mean the M1 unblock
# claim is wrong).
#
# THIS IS ONE PRE-REGISTERED ATTEMPT (safety-invariants law 5's "one-attempt rule" / blank-agent /
# oracle-off-the-wire laws apply in spirit -- there is no oracle/RAM truth on this wire at all, only
# a `ping`/`pong` tool call, so "oracle off the wire" is trivially satisfied here, but the
# one-attempt discipline is not: DO NOT re-run this to "fix" a cancelled/ambiguous result. A
# cancelled outcome IS the answer to the M1 question (the unblock claim would be FALSE) -- score it,
# don't rescue it.
#
# CREDIT CAP AND KILL CONDITIONS:
#   -CreditCap (normalized credits, default 10 -- far under the pinned 250 combined Gate-0 ceiling)
#   is WIRED THROUGH tools/gate0_appserver_launch.py's LiveCreditGuard, which IMPORTS (never edits)
#   tools/gate0_credit_breaker.run_breaker exactly as tools/run_gate0_codex.ps1's own paid path
#   does -- BUT (B1, stated plainly, not glossed over): -CreditCap IS CURRENTLY INERT ON THIS
#   TRANSPORT. `gate0_codex_credit_rate.codex_event_to_credit_event` only recognizes the
#   exec-shaped `{"type": "token_count", ...}` event; `codex app-server` sends JSON-RPC 2.0
#   notifications instead, and no committed schema/fixture for a usage/token-count notification
#   exists in this repo as of this build. LiveCreditGuard therefore never sees a priceable event
#   here, so the cap can never trip on real spend. TODO: once a real paid turn (or
#   `codex app-server generate-json-schema`) reveals the actual usage-notification shape, add an
#   ADDITIVE app-server usage shim feeding this same guard.
#   THE BOUND THAT IS ACTUALLY ENFORCED for this turn is -TurnTimeoutS (default 45s, may only be
#   tightened, passed straight through to --turn-timeout-s) -- codex is walked away from (client
#   closed, best-effort `taskkill /PID <pid> /T /F`) once that many seconds pass without a terminal
#   turn notification, regardless of what -CreditCap says.
#   KNOWN GAP vs the pinned launcher: this Python-side kill is NOT wrapped in a Windows kill-on-
#   close Job Object (tools/run_gate0_codex.ps1's Invoke-BreakerSupervisedExec has one; this script
#   does not reimplement it here to avoid duplicating that safety-critical mechanism unreviewed).
#   A `codex app-server` descendant that detaches before the timeout fires could in principle
#   survive the kill; the orchestrator should still watch the process list during the run and
#   manually `taskkill /T /F` the codex.exe PID printed to stdout if anything looks wrong.
#   -CreditRatePin: still REQUIRED (fail-closed, same contract as tools/gate0_codex_credit_rate.py,
#   and enforced again by tools/gate0_appserver_launch.py itself for any real turn) -- a
#   human-authored JSON naming `model`, `rate_source` (prose citing where the $/token numbers came
#   from), `credits_per_usd`, `usd_per_input_token`, `usd_per_cached_input_token`,
#   `usd_per_output_token`. This script REFUSES to run without one; there is no default rate. Given
#   the B1 gap above, the pin does not yet buy a live-enforced cap on this transport -- it is kept
#   mandatory anyway so a future usage shim (once added) has a rate ready, and so this script's
#   contract never silently degrades to "no rate needed."
#
# EXPECTED TOKEN COST: this is ONE turn whose ENTIRE task is "call one trivial no-argument MCP
# tool once, then stop" -- the smallest possible non-trivial turn. Expect on the order of a few
# hundred to a couple thousand tokens total (prompt + one tool call + the model's own turn-end
# reasoning/summary), i.e. a small fraction of the 10-credit -CreditCap default at any plausible
# 2026-era per-token price. This is an ASSUMPTION (no real turn has been run to confirm it) -- per
# B1 above, -TurnTimeoutS (not -CreditCap) is the actual enforced backstop today.
#
# BLANK-AGENT / ONE-ATTEMPT / ORACLE-OFF-THE-WIRE LAWS (safety-invariants skill, applies in spirit
# here too): this is a single Codex app-server turn, not a Pokemon-Red brain run, so there is no
# aria-memory to wipe and no RAM-truth oracle to keep off the wire -- but the ONE-ATTEMPT discipline
# is real: this script is meant to be run ONCE per confirmation attempt. If it fails to even reach
# a scored verdict (crash before `verdict.json` is written), that is an infra failure and MAY be
# retried once; a scored COMPLETED or CANCELLED verdict is banked, not rerun to "get a better
# answer."
#
# Usage (stub MCP -- PRIMARY, Docker daemon down as of 2026-07-23):
#   pwsh tools/gate0_appserver_paid_turn.ps1 -Model gpt-5.6-sol `
#       -OutputDir runs/gate0_appserver_paid_turn -CreditRatePin path\to\signed_rate_pin.json `
#       -IUnderstandThisSpendsMoney
#
# Usage (Docker world -- ONLY once the Docker daemon is back up; NOT this build's default):
#   pwsh tools/gate0_appserver_paid_turn.ps1 -Model gpt-5.6-sol `
#       -OutputDir runs/gate0_appserver_paid_turn_docker -CreditRatePin path\to\signed_rate_pin.json `
#       -Mcp docker -DockerImage gb-mcp-world `
#       -DockerMount "type=bind,source=$PWD\roms,target=/app/roms,readonly" `
#       -DockerMount "type=bind,source=$PWD\runs\red_start.state,target=/app/red_start.state,readonly" `
#       -DockerMount "type=bind,source=$PWD\runs\gate0_appserver_paid_turn_docker\world,target=/app/world" `
#       -DockerExtraArg '--game' -DockerExtraArg 'pokemon_red' -DockerExtraArg '--init-state' `
#       -DockerExtraArg '/app/red_start.state' -DockerExtraArg '--out' -DockerExtraArg '/app/world' `
#       -DockerTool observe -DockerTool explore -DockerTool goto -DockerTool remember `
#       -DockerTool press_button -DockerTool press_sequence -DockerTool wait `
#       -IUnderstandThisSpendsMoney
#
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[A-Za-z0-9][A-Za-z0-9._-]{1,127}$')]
    [string]$Model,

    [Parameter(Mandatory = $true)]
    [string]$OutputDir,

    [Parameter(Mandatory = $true)]
    [string]$CreditRatePin,

    # THE explicit, hard-to-fat-finger confirmation gate. This switch must be passed literally --
    # its presence is the "I read the header comment and intend to spend money" signal. There is
    # no default and no shorter alias on purpose.
    [Parameter(Mandatory = $true)]
    [switch]$IUnderstandThisSpendsMoney,

    [double]$CreditCap = 10.0,
    [double]$StallTimeoutS = 300,
    # B1: the bound actually enforced today (see header comment) -- default matches
    # tools/gate0_appserver_launch.py's own lowered default; may only be tightened, never loosened.
    [double]$TurnTimeoutS = 45,
    [string]$ToolName = 'ping',
    [ValidateSet('stub', 'docker')]
    [string]$Mcp = 'stub',
    [string]$DockerImage,
    [string[]]$DockerMount = @(),
    [string[]]$DockerExtraArg = @(),
    [string[]]$DockerTool = @(),
    # N3: isolated CODEX_HOME override / auth-seed source (default <OutputDir>\codex-home and
    # ~/.codex/auth.json respectively, both applied inside tools/gate0_appserver_launch.py).
    [string]$CodexHome = '',
    [string]$CodexAuthSource = '',
    [string]$PythonExe = 'python'
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

if ($Model -match '(?i)(^|[-_.])latest($|[-_.])') {
    throw 'Model must be an explicit model identifier, not a latest alias.'
}
if (-not (Test-Path -LiteralPath $CreditRatePin -PathType Leaf)) {
    throw "CreditRatePin file not found: $CreditRatePin -- this script refuses to guess a token->credit rate."
}
if ($StallTimeoutS -gt 300) {
    throw '-StallTimeoutS may only tighten the pre-registered 300s backstop, never loosen it.'
}
if ($TurnTimeoutS -gt 45) {
    throw '-TurnTimeoutS may only tighten the pre-registered 45s backstop, never loosen it (B1: this is the actually-enforced spend bound while -CreditCap is inert on the app-server transport).'
}
if ($env:OPENAI_API_KEY -or $env:CODEX_API_KEY) {
    throw 'OPENAI_API_KEY or CODEX_API_KEY is set; Gate 0 requires ChatGPT subscription authentication.'
}
if ($Mcp -eq 'docker' -and -not $DockerImage) {
    throw '-Mcp docker requires -DockerImage.'
}
# N1: a mandatory [switch] can still be passed explicitly as :$false -- assert its truth, don't
# just trust that Mandatory-ness alone forced an affirmative answer.
if (-not $IUnderstandThisSpendsMoney) {
    throw '-IUnderstandThisSpendsMoney must be true to run a real paid turn.'
}

Write-Output '=== Gate 0 app-server ONE BOUNDED PAID TURN ==='
Write-Output "Model: $Model"
Write-Output "MCP target: $Mcp $(if ($Mcp -eq 'docker') { "(image: $DockerImage)" } else { '(local stub, tools/gate0_stub_mcp_server.py)' })"
Write-Output "Credit cap: $CreditCap normalized credits (rate pin: $CreditRatePin) -- NOTE: inert on this transport, see header (B1)."
Write-Output "Stall timeout: $StallTimeoutS s"
Write-Output "Turn timeout: $TurnTimeoutS s (the actually-enforced spend bound today, see header (B1))"
Write-Output "Output dir: $OutputDir"
Write-Output ''

$pyArgs = @(
    '-m', 'tools.gate0_appserver_launch',
    '--mcp', $Mcp,
    '--model', $Model,
    '--out-dir', $OutputDir,
    '--tool-name', $ToolName,
    '--credit-cap', $CreditCap,
    '--credit-rate-pin', $CreditRatePin,
    '--stall-timeout-s', $StallTimeoutS,
    '--turn-timeout-s', $TurnTimeoutS
)
if ($CodexHome) { $pyArgs += @('--codex-home', $CodexHome) }
if ($CodexAuthSource) { $pyArgs += @('--codex-auth-source', $CodexAuthSource) }
if ($Mcp -eq 'docker') {
    $pyArgs += @('--docker-image', $DockerImage)
    foreach ($m in $DockerMount) { $pyArgs += @('--docker-mount', $m) }
    foreach ($a in $DockerExtraArg) { $pyArgs += @('--docker-extra-arg', $a) }
    foreach ($t in $DockerTool) { $pyArgs += @('--docker-tool', $t) }
}

& $PythonExe @pyArgs
$exitCode = $LASTEXITCODE

Write-Output ''
Write-Output "verdict.json / transcript.jsonl / audit.jsonl written under: $OutputDir"
if (Test-Path -LiteralPath (Join-Path $OutputDir 'verdict.json')) {
    Write-Output '--- verdict.json ---'
    Get-Content -LiteralPath (Join-Path $OutputDir 'verdict.json') -Raw | Write-Output
}
Write-Output "launcher exit code: $exitCode"
exit $exitCode
