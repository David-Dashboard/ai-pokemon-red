[CmdletBinding()]
param(
    [string]$OutPath = ''
)

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
if (-not $OutPath) { $OutPath = Join-Path $ScriptDir '..\runs\gate0_live_breaker\wired_path_trip.json' }

# PR #118 checklist 4c -- ZERO-SPEND wired-path TRIP receipt.
#
# This extracts and runs the EXACT SAME production functions tools/run_gate0_codex.ps1 uses for a
# real paid launch (Invoke-BreakerSupervisedExec, ConvertTo-NativeArgument -- via the identical
# AST-extraction technique tests/test_run_gate0_codex_launcher.py already uses for every other
# function in that script), with tools/gate0_stub_codex_emitter.py substituted for the real Codex
# executable. The stub makes no network call and calls no model -- see its own module docstring.
# The credit-rate pin below is a clearly-labeled SYNTHETIC TEST fixture, not a real priced rate
# (tools/gate0_codex_credit_rate.py's `rate_source` field says so explicitly) -- this proves the
# WIRING (4b) and the kill contract, not a real dollar figure (4a's real pin is a separate,
# still-open, David-signed artifact -- see eval/fixtures/gate0_signature.example.json).
$ErrorActionPreference = 'Stop'
$RepoRoot = [IO.Path]::GetFullPath((Join-Path $ScriptDir '..'))
$LauncherPath = Join-Path $RepoRoot 'tools\run_gate0_codex.ps1'

$tokens = $null
$errors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile($LauncherPath, [ref]$tokens, [ref]$errors)
if ($errors.Count -ne 0) { throw 'Launcher did not parse.' }
foreach ($name in @('ConvertTo-NativeArgument', 'Invoke-BreakerSupervisedExec')) {
    $functions = @($ast.FindAll({
        param($node)
        $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and
            $node.Name -eq $name
    }, $true))
    if ($functions.Count -ne 1) { throw "Expected exactly one $name function definition." }
    Invoke-Expression $functions[0].Extent.Text
}

$ProofDir = Join-Path $RepoRoot 'runs\gate0_live_breaker'
[void](New-Item -ItemType Directory -Path $ProofDir -Force)
$RatePinPath = Join-Path $ProofDir 'synthetic_rate_pin.json'
$ProgressPath = Join-Path $ProofDir 'wired_path_trip_emitter_progress.json'
$VerdictPath = Join-Path $ProofDir 'wired_path_trip_accountant_verdict.json'
$EmitterPath = Join-Path $RepoRoot 'tools\gate0_stub_codex_emitter.py'
$AccountantModel = 'stub-model'

$RatePin = [ordered]@{
    model = $AccountantModel
    rate_source = 'SYNTHETIC TEST FIXTURE for PR #118 checklist 4c -- proves the wired kill ' +
        'path, NOT a real priced rate. See reports/2026-07-21-gate0-wired-breaker-trip.md.'
    credits_per_usd = 1
    usd_per_input_token = 0.0
    usd_per_cached_input_token = 0.0
    usd_per_output_token = 1.0
}
# [Text.UTF8Encoding]::new($false): no BOM -- matches Write-Utf8NoBom in run_gate0_codex.ps1.
# Set-Content -Encoding utf8 on Windows PowerShell 5.1 writes a BOM, which broke
# tools.gate0_codex_credit_rate's plain `Path.read_text(encoding="utf-8")` + json.loads (BOM-
# prefixed JSON is not valid JSON) -- caught and confirmed while first producing this artifact.
[IO.File]::WriteAllText($RatePinPath, ($RatePin | ConvertTo-Json -Depth 4), [Text.UTF8Encoding]::new($false))

# A much longer intended stream than the trip point (which lands around event ~42-43, see
# tests/test_gate0_credit_breaker.py's 45x6 pattern this rate mirrors) so a large, unambiguous
# tail remains unsent when the kill lands -- proving a genuine mid-stream interruption rather than
# racing a stream that was already about to finish on its own.
$IntendedTotal = 150
$OutputTokensPerEvent = 6
$DelaySeconds = 0.2

$StartedAt = Get-Date
$Supervised = Invoke-BreakerSupervisedExec -ChildExecutable 'python' -ChildArguments @(
        $EmitterPath, '--total', $IntendedTotal, '--output-tokens-per-event', $OutputTokensPerEvent,
        '--delay-s', $DelaySeconds, '--out-progress', $ProgressPath
    ) -AccountantExecutable 'python' -WorkingDirectory $RepoRoot -AccountantArguments @(
        '-m', 'tools.gate0_credit_accountant', '--rate-pin', $RatePinPath, '--model', $AccountantModel,
        '--verdict-out', $VerdictPath, '--stall-timeout-s', 300
    )
$EndedAt = Get-Date

$Verdict = (Get-Content -LiteralPath $VerdictPath -Raw) | ConvertFrom-Json
$Progress = (Get-Content -LiteralPath $ProgressPath -Raw) | ConvertFrom-Json

$Receipt = [ordered]@{
    schema_version = 1
    kind = 'gate0_wired_breaker_trip_proof'
    checklist_item = 'PR #118 precondition-4 checklist 4c'
    status = if ($Verdict.result -eq 'TRIPPED' -and $Supervised.ChildKilled -eq $true `
        -and $Supervised.ChildStillAliveAfterKill -eq $false `
        -and $Progress.emitted_count -lt $Progress.intended_total) { 'PASS' } else { 'FAIL' }
    note = 'Zero-spend proof: tools/gate0_stub_codex_emitter.py (no network, no model call) ' +
        'substituted for codex.exe in the REAL production tools/run_gate0_codex.ps1::' +
        'Invoke-BreakerSupervisedExec, piped through the real tools/gate0_credit_accountant.py ' +
        '-> tools/gate0_credit_breaker.py::run_breaker(raise_on_trip=True). The credit-rate pin ' +
        'is a labeled synthetic test fixture, not a real priced rate (see rate_source above).'
    rate_pin = $RatePin
    emitter = [ordered]@{
        intended_total_events = $Progress.intended_total
        emitted_count_at_kill = $Progress.emitted_count
        unsent_tail = $Progress.intended_total - $Progress.emitted_count
        output_tokens_per_event = $OutputTokensPerEvent
        delay_s_between_events = $DelaySeconds
    }
    accountant_verdict = $Verdict
    child_process_termination_evidence = [ordered]@{
        child_id = $Supervised.ChildId
        child_killed = $Supervised.ChildKilled
        child_has_exited = $Supervised.ChildHasExited
        child_exit_code = $Supervised.ChildExitCode
        child_still_alive_after_kill = $Supervised.ChildStillAliveAfterKill
        kill_evidence = $Supervised.KillEvidence
    }
    accountant_process = [ordered]@{
        exit_code = $Supervised.AccountantExitCode
        stderr = $Supervised.AccountantStdErr
    }
    started_at = $StartedAt.ToString('o')
    ended_at = $EndedAt.ToString('o')
    wall_clock_s = [math]::Round(($EndedAt - $StartedAt).TotalSeconds, 3)
}

[void](New-Item -ItemType Directory -Path (Split-Path -Parent $OutPath) -Force)
[IO.File]::WriteAllText($OutPath, (($Receipt | ConvertTo-Json -Depth 10) + "`n"), [Text.UTF8Encoding]::new($false))
Write-Output "wrote $OutPath"
Write-Output ($Receipt | ConvertTo-Json -Depth 3 -Compress)
