[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet('red', 'miniwob')]
    [string]$Arm,

    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[A-Za-z0-9][A-Za-z0-9._-]{1,127}$')]
    [string]$Model,

    [Parameter(Mandatory = $true)]
    [string]$OutputDir,

    # Everything below is OFF by default so a bare invocation stays the byte-identical
    # free-handshake-only script this launcher has always been
    # (tests/test_run_gate0_codex_launcher.py::test_launcher_is_free_handshake_only_and_fail_closed).
    # -PaidExec is the ONLY way to reach a live `codex exec` call (PR #118 checklist 4b); it is
    # refused unless a David-signed eval/fixtures/gate0_signature.json (or an explicit
    # -SignaturePath override) authorizes the exact frozen commit this checkout is on.
    [switch]$PaidExec,
    [string]$SignaturePath = (Join-Path $PSScriptRoot '..\eval\fixtures\gate0_signature.json'),
    # Pre-registered wired-path stall backstop (PR #118 breaker review MINOR 3a,
    # tools/gate0_credit_breaker.py::STALL_TIMEOUT_S = 300). Overridable only to a STRICTER
    # (smaller) value at signature time -- the paid path refuses a looser override.
    [double]$StallTimeoutS = 300
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

function Quote-Toml([string]$Value) {
    return '"' + $Value.Replace('\', '\\').Replace('"', '\"') + '"'
}

function Write-Utf8NoBom([string]$Path, [string]$Text) {
    [IO.File]::WriteAllText($Path, $Text, [Text.UTF8Encoding]::new($false))
}

function Get-BytesSha256([byte[]]$Bytes) {
    $sha = [Security.Cryptography.SHA256]::Create()
    try { return ([BitConverter]::ToString($sha.ComputeHash($Bytes))).Replace('-', '').ToLowerInvariant() }
    finally { $sha.Dispose() }
}

function Get-FileSha256([string]$Path) {
    return Get-BytesSha256 ([IO.File]::ReadAllBytes($Path))
}

function Resolve-CodexExecutable([object[]]$Candidates) {
    $exeCandidates = @($Candidates | Where-Object {
        ([string]$_.Source).EndsWith('.exe', [StringComparison]::OrdinalIgnoreCase)
    })
    if ($exeCandidates.Count -ne 1) {
        throw "Expected exactly one Codex .exe application candidate; found $($exeCandidates.Count)."
    }
    return [string]$exeCandidates[0].Source
}

function ConvertTo-NativeArgument([string]$Value) {
    if ($Value.Length -gt 0 -and $Value -notmatch '[\s"]') { return $Value }
    $result = [Text.StringBuilder]::new()
    [void]$result.Append('"')
    $backslashes = 0
    foreach ($char in $Value.ToCharArray()) {
        if ($char -eq '\') {
            $backslashes += 1
            continue
        }
        if ($char -eq '"') {
            [void]$result.Append(('\' * (2 * $backslashes + 1)))
            [void]$result.Append('"')
        } else {
            if ($backslashes -gt 0) { [void]$result.Append(('\' * $backslashes)) }
            [void]$result.Append($char)
        }
        $backslashes = 0
    }
    if ($backslashes -gt 0) { [void]$result.Append(('\' * (2 * $backslashes))) }
    [void]$result.Append('"')
    return $result.ToString()
}

function Invoke-RedirectedProcess([string]$ExecutablePath, [string[]]$Arguments) {
    $startInfo = [Diagnostics.ProcessStartInfo]::new()
    $startInfo.FileName = $ExecutablePath
    $startInfo.Arguments = (($Arguments | ForEach-Object { ConvertTo-NativeArgument $_ }) -join ' ')
    $startInfo.UseShellExecute = $false
    $startInfo.RedirectStandardOutput = $true
    $startInfo.RedirectStandardError = $true
    $startInfo.CreateNoWindow = $true
    $process = [Diagnostics.Process]::new()
    $process.StartInfo = $startInfo
    try {
        [void]$process.Start()
        $stdoutTask = $process.StandardOutput.ReadToEndAsync()
        $stderrTask = $process.StandardError.ReadToEndAsync()
        $process.WaitForExit()
        return [pscustomobject]@{
            StdOut = [string]$stdoutTask.GetAwaiter().GetResult()
            StdErr = [string]$stderrTask.GetAwaiter().GetResult()
            ExitCode = [int]$process.ExitCode
        }
    } finally {
        $process.Dispose()
    }
}

function Invoke-GitBytes([string]$RepoRoot, [string[]]$GitArguments) {
    $startInfo = [Diagnostics.ProcessStartInfo]::new()
    $startInfo.FileName = 'git'
    $startInfo.Arguments = ((@('-C', $RepoRoot) + $GitArguments |
        ForEach-Object { ConvertTo-NativeArgument $_ }) -join ' ')
    $startInfo.UseShellExecute = $false
    $startInfo.RedirectStandardOutput = $true
    $startInfo.RedirectStandardError = $true
    $startInfo.CreateNoWindow = $true
    $process = [Diagnostics.Process]::new()
    $process.StartInfo = $startInfo
    try {
        [void]$process.Start()
        $stderrTask = $process.StandardError.ReadToEndAsync()
        $memory = [IO.MemoryStream]::new()
        $process.StandardOutput.BaseStream.CopyTo($memory)
        $process.WaitForExit()
        [void]$stderrTask.GetAwaiter().GetResult()
        return [pscustomobject]@{ ExitCode = [int]$process.ExitCode; Bytes = $memory.ToArray() }
    } finally {
        $process.Dispose()
    }
}

# Canonical-content code hash. The CONTRACT here is world_mcp.py::code_sha256() -- keep the two in
# lockstep (tests/test_run_gate0_codex_launcher.py pins their agreement on identical repos): SHA-256
# over the exact git blob bytes at HEAD (git cat-file blob HEAD:<path>), NEVER over raw working-tree
# bytes, which vary with core.autocrlf/line-ending config across machines and OSes even when the
# tracked content is byte-identical -- raw-byte hashing made host_code_sha256 non-reproducible from
# a clean clone (PR #114 readiness-audit MAJOR). When the working tree differs from HEAD (or git is
# unusable), return the distinct refusal sentinel 'UNHASHABLE' -- never silently fall back to
# hashing dirty bytes. Byte-stream capture (Invoke-GitBytes) is deliberate: piping git output
# through PowerShell strings would re-mangle line endings and corrupt the hash.
function Get-CanonicalCodeSha256([string]$RepoRoot, [string]$RelPath) {
    $clean = Invoke-GitBytes -RepoRoot $RepoRoot -GitArguments @('diff', '--quiet', 'HEAD', '--', $RelPath)
    if ($clean.ExitCode -ne 0) { return 'UNHASHABLE' }
    $blob = Invoke-GitBytes -RepoRoot $RepoRoot -GitArguments @('cat-file', 'blob', "HEAD:$RelPath")
    if ($blob.ExitCode -ne 0) { return 'UNHASHABLE' }
    return Get-BytesSha256 $blob.Bytes
}

function Invoke-CodexLoginStatus([string]$ExecutablePath) {
    $result = Invoke-RedirectedProcess -ExecutablePath $ExecutablePath -Arguments @('login', 'status')
    if ($result.ExitCode -ne 0) {
        throw "Codex login status command exited with code $($result.ExitCode)."
    }
    [string]$text = (($result.StdOut + "`n" + $result.StdErr).Trim())
    return [pscustomobject]@{ Text = $text; ExitCode = $result.ExitCode }
}

# ---------------------------------------------------------------------------------------------
# Paid-exec wiring (PR #118 checklist 4a-4d). Every function below is inert unless -PaidExec is
# passed AND every gate here passes; none of it changes the free-handshake-only default path.
# ---------------------------------------------------------------------------------------------

function Get-GitHeadCommit([string]$RepoRoot) {
    $result = Invoke-GitBytes -RepoRoot $RepoRoot -GitArguments @('rev-parse', 'HEAD')
    if ($result.ExitCode -ne 0) { throw 'Could not resolve the current commit for signature verification.' }
    return ([Text.Encoding]::UTF8.GetString($result.Bytes)).Trim()
}

# 4b signature gate. Refuses -PaidExec unless a David-authored artifact names the EXACT frozen
# commit this checkout is on plus the two launch-invocation-dependent hashes (config_sha256,
# codex_mcp_list_sha256 -- PR #118 body's "CONSTRAINT... signature-time recompute recipe" pair)
# already computed by this run's own free-handshake logic above. It also carries the 4a credit-
# rate pin (see tools/gate0_codex_credit_rate.py) so one signed artifact authorizes both "this is
# the reviewed commit/config" and "this is the priced rate for this model" at once. No value here
# is invented by this script -- everything is compared against either the receipt this run just
# produced or fields the signer supplied.
function Confirm-PaidExecSignature {
    param(
        [string]$SignaturePath, [string]$RepoRoot, [string]$Arm, [string]$Model,
        [string]$ExpectedConfigSha256, [string]$ExpectedMcpListSha256
    )
    if (-not (Test-Path -LiteralPath $SignaturePath -PathType Leaf)) {
        throw "PaidExec refused: no signature file at $SignaturePath. David must author one before any paid launch."
    }
    try { $signature = (Get-Content -LiteralPath $SignaturePath -Raw) | ConvertFrom-Json }
    catch { throw "PaidExec refused: signature file at $SignaturePath is not valid JSON." }
    if ($signature.schema_version -ne 1) { throw 'PaidExec refused: signature schema_version must be 1.' }
    $headCommit = Get-GitHeadCommit -RepoRoot $RepoRoot
    if ([string]$signature.frozen_commit -ne $headCommit) {
        throw "PaidExec refused: signature pins commit $($signature.frozen_commit), checkout is at $headCommit."
    }
    if ([string]$signature.arm -ne $Arm) {
        throw "PaidExec refused: signature pins arm $($signature.arm), this launch is arm $Arm."
    }
    if ([string]$signature.planned_model -ne $Model) {
        throw "PaidExec refused: signature pins model $($signature.planned_model), this launch is model $Model."
    }
    if ([string]$signature.expected_config_sha256 -ne $ExpectedConfigSha256) {
        throw 'PaidExec refused: signature expected_config_sha256 does not match this run''s freshly computed config_sha256.'
    }
    if ([string]$signature.expected_codex_mcp_list_sha256 -ne $ExpectedMcpListSha256) {
        throw 'PaidExec refused: signature expected_codex_mcp_list_sha256 does not match this run''s freshly computed codex_mcp_list_sha256.'
    }
    if ($null -eq $signature.credit_rate_pin) {
        throw 'PaidExec refused: signature carries no credit_rate_pin (4a).'
    }
    return $signature
}

# Reuses the exact same explicit-override vocabulary the free-handshake `codex mcp list --json`
# probe already proved Codex accepts (`$Overrides`, built once, above) -- `codex exec --json` gets
# the identical model/sandbox/mcp wiring, never a second hand-typed config. The prompt is piped
# over stdin (never a CLI argument) for the same reason TASK.md is a file: arbitrary task text
# must never be re-quoted through a shell.
function Get-PaidCodexExecArguments([string[]]$Overrides) {
    $arguments = @('exec', '--json')
    foreach ($override in $Overrides) { $arguments += @('-c', $override) }
    $arguments += '-'
    return $arguments
}

# THE KILL CONTRACT (tools/gate0_credit_breaker.py module docstring, PR #118 breaker review MINOR
# 2/3a): spawns $ChildExecutable (real Codex in production; a zero-spend stub emitter for the 4c
# proof -- this function does not know or care which) with its stdout relayed, as a live byte
# stream via .NET CopyToAsync (never buffered/materialized -- MAJOR 1), into $AccountantExecutable
# (tools/gate0_credit_accountant.py), which feeds run_breaker(raise_on_trip=True,
# stall_timeout_s=...) an ITERATOR over that relayed stream. The accountant process's own exit is
# the kill signal: EITHER breaker exception (BreakerTripped from a real trip, or
# MalformedCreditStream from a malformed event OR a stall -- catching only the former is
# fail-open) makes it exit non-zero, and the instant it exits for any reason other than the child
# having already finished on its own, the child's WHOLE process tree is killed via `taskkill /T
# /F` (never a lone top-level Stop-Process, which would strand any docker/MCP descendants).
# Evidence of the kill (exit/alive state, not merely "a signal was sent") is returned so callers
# can bank a receipt precondition 4c can stand behind.
function Invoke-BreakerSupervisedExec {
    param(
        [string]$ChildExecutable, [string[]]$ChildArguments, [string]$ChildStdinText,
        [string]$AccountantExecutable, [string[]]$AccountantArguments,
        [string]$WorkingDirectory = '',
        [int]$PollIntervalMs = 100, [int]$MaxWallClockS = 3600
    )
    $childInfo = [Diagnostics.ProcessStartInfo]::new()
    $childInfo.FileName = $ChildExecutable
    $childInfo.Arguments = (($ChildArguments | ForEach-Object { ConvertTo-NativeArgument $_ }) -join ' ')
    $childInfo.UseShellExecute = $false
    $childInfo.RedirectStandardInput = $true
    $childInfo.RedirectStandardOutput = $true
    $childInfo.RedirectStandardError = $true
    $childInfo.CreateNoWindow = $true
    if ($WorkingDirectory) { $childInfo.WorkingDirectory = $WorkingDirectory }
    $child = [Diagnostics.Process]::new()
    $child.StartInfo = $childInfo

    $acctInfo = [Diagnostics.ProcessStartInfo]::new()
    $acctInfo.FileName = $AccountantExecutable
    $acctInfo.Arguments = (($AccountantArguments | ForEach-Object { ConvertTo-NativeArgument $_ }) -join ' ')
    $acctInfo.UseShellExecute = $false
    $acctInfo.RedirectStandardInput = $true
    $acctInfo.RedirectStandardOutput = $true
    $acctInfo.RedirectStandardError = $true
    $acctInfo.CreateNoWindow = $true
    if ($WorkingDirectory) { $acctInfo.WorkingDirectory = $WorkingDirectory }
    $accountant = [Diagnostics.Process]::new()
    $accountant.StartInfo = $acctInfo

    $startedAt = Get-Date
    try {
        [void]$accountant.Start()
        [void]$child.Start()
        $childId = $child.Id

        if ($ChildStdinText) { $child.StandardInput.Write($ChildStdinText) }
        $child.StandardInput.Close()

        $childErrTask = $child.StandardError.ReadToEndAsync()
        $acctErrTask = $accountant.StandardError.ReadToEndAsync()
        $acctOutTask = $accountant.StandardOutput.ReadToEndAsync()
        # The live relay: bytes flow from the child's stdout straight into the accountant's stdin
        # as they arrive. Nothing here reads the child's output into a PowerShell variable first.
        $relayTask = $child.StandardOutput.BaseStream.CopyToAsync($accountant.StandardInput.BaseStream)

        while ($true) {
            if ($accountant.HasExited) { break }
            if ($child.HasExited -and $relayTask.IsCompleted) { break }
            if (((Get-Date) - $startedAt).TotalSeconds -gt $MaxWallClockS) { break }
            Start-Sleep -Milliseconds $PollIntervalMs
        }

        $killed = $false
        $killEvidence = $null
        if (-not $child.HasExited) {
            $killed = $true
            $killEvidence = (& taskkill.exe /PID $childId /T /F 2>&1 | Out-String)
        }
        try { $accountant.StandardInput.Close() } catch {}
        # [void]: a bare, unassigned `.GetAwaiter().GetResult()` statement on this non-generic
        # Task otherwise leaks onto this function's own output pipeline (empirically confirmed --
        # it is not just "no-op discarded"), silently turning the single-object return below into
        # a two-element array. Observing/swallowing the relay's own exception (e.g. a broken pipe
        # because the accountant already exited on a trip) must never do that.
        try { [void]$relayTask.GetAwaiter().GetResult() } catch {}
        [void]$child.WaitForExit(10000)
        [void]$accountant.WaitForExit(10000)

        # Confirm the kill: the child PID must be truly gone, not merely signaled.
        Start-Sleep -Milliseconds 200
        $stillAlive = $null -ne (Get-Process -Id $childId -ErrorAction SilentlyContinue)

        [pscustomobject]@{
            ChildId = $childId
            ChildExitCode = if ($child.HasExited) { $child.ExitCode } else { $null }
            ChildHasExited = $child.HasExited
            ChildStillAliveAfterKill = $stillAlive
            ChildKilled = $killed
            KillEvidence = $killEvidence
            ChildStdErr = $childErrTask.GetAwaiter().GetResult()
            AccountantExitCode = if ($accountant.HasExited) { $accountant.ExitCode } else { $null }
            AccountantStdOut = $acctOutTask.GetAwaiter().GetResult()
            AccountantStdErr = $acctErrTask.GetAwaiter().GetResult()
            StartedAt = $startedAt.ToString('o')
            EndedAt = (Get-Date).ToString('o')
        }
    } finally {
        foreach ($p in @($child, $accountant)) {
            try { if (-not $p.HasExited) { $p.Kill() } } catch {}
        }
        $child.Dispose()
        $accountant.Dispose()
    }
}

if ($Model -match '(?i)(^|[-_.])latest($|[-_.])') {
    throw 'Model must be an explicit model identifier, not a latest alias.'
}
if (Test-Path -LiteralPath $OutputDir) {
    if (-not (Test-Path -LiteralPath $OutputDir -PathType Container)) {
        throw 'OutputDir exists and is not a directory.'
    }
    if (Get-ChildItem -LiteralPath $OutputDir -Force | Select-Object -First 1) {
        throw 'OutputDir must not exist or must be empty.'
    }
}

# Authentication is observed through the user's normal CODEX_HOME. It is never copied into the
# isolated config home used below for the free MCP inventory command.
[string]$ResolvedCodexPath = Resolve-CodexExecutable -Candidates @(
    Get-Command codex -CommandType Application -All -ErrorAction Stop
)
$versionText = (& $ResolvedCodexPath --version 2>$null | Out-String).Trim()
if ($LASTEXITCODE -ne 0 -or $versionText -notmatch '^codex(?:-cli)?\s+[0-9][0-9A-Za-z.+-]*$') {
    throw 'Codex version is unavailable or not safely parseable.'
}
if ($env:OPENAI_API_KEY -or $env:CODEX_API_KEY) {
    throw 'OPENAI_API_KEY or CODEX_API_KEY is set; Gate 0 requires ChatGPT authentication.'
}
$loginStatus = Invoke-CodexLoginStatus -ExecutablePath $ResolvedCodexPath
$loginText = $loginStatus.Text
if ($loginText -notmatch '(?i)\bchatgpt\b' -or
    $loginText -match '(?i)\bapi(?:[ -]?key)?\b') {
    throw 'Codex login status did not prove ChatGPT subscription authentication.'
}

$RepoRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$OutputDir = [IO.Path]::GetFullPath($OutputDir)
[void](New-Item -ItemType Directory -Path $OutputDir -Force)
$LaunchDir = Join-Path $OutputDir 'launch'
$WorldDir = Join-Path $OutputDir 'world'
$IsolatedHome = Join-Path $OutputDir 'codex-home'
[void](New-Item -ItemType Directory -Path $LaunchDir)
[void](New-Item -ItemType Directory -Path $WorldDir)
[void](New-Item -ItemType Directory -Path $IsolatedHome)
& git init --quiet $LaunchDir
if ($LASTEXITCODE -ne 0) { throw 'Could not initialize the fresh launch git repository.' }

$Server = 'gate0_world'
if ($Arm -eq 'red') {
    $Tools = @('observe', 'explore', 'goto', 'remember', 'press_button', 'press_sequence', 'wait')
    $TaskSentence = 'From the fresh bedroom start, obtain your first Pokemon from Professor Oak and win the first rival battle.'
    $ImageTag = 'gb-mcp-world'
    $State = Join-Path $RepoRoot 'runs\red_start.state'
    $Roms = Join-Path $RepoRoot 'roms'
    if (-not (Test-Path -LiteralPath $State -PathType Leaf) -or
        -not (Test-Path -LiteralPath $Roms -PathType Container)) {
        throw 'The pinned Red state or ROM directory is unavailable.'
    }
} else {
    $Tools = @('observe', 'read_region', 'whats_changed', 'click', 'type_text',
        'press_key', 'reset_episode')
    $TaskSentence = 'Complete five fresh episodes of the browser click-checkboxes task from their on-screen instructions using screen pixels and ordinary mouse and keyboard controls.'
    $ImageTag = 'miniwob-world'
    $Seeds = Join-Path $RepoRoot 'eval\fixtures\gate0_miniwob_paid_seeds.json'
    if (-not (Test-Path -LiteralPath $Seeds -PathType Leaf)) {
        throw 'The pinned MiniWoB seed manifest is unavailable.'
    }
}

$ImageId = (& docker image inspect --format '{{.Id}}' $ImageTag 2>$null | Out-String).Trim()
if ($LASTEXITCODE -ne 0 -or $ImageId -notmatch '^sha256:[0-9a-f]{64}$') {
    throw "Docker image $ImageTag is unavailable or has no immutable image ID."
}

# Both Dockerfiles copy these files. A mutable tag is never enough: the exact image must contain
# the exact host code before even the free tools/list handshake is allowed. Host-side hashes are
# canonical git-blob hashes at HEAD (Get-CanonicalCodeSha256; contract = world_mcp.py::code_sha256),
# so the receipt reproduces from any clean clone of the same commit regardless of local line-ending
# config. The image-side hashes below stay raw in-image bytes (the image is content-addressed, so
# they are already machine-independent) -- parity therefore also proves the image holds the exact
# canonical LF content, and an image built from a CRLF checkout correctly refuses as stale.
$HostCode = [ordered]@{
    '/app/world_mcp.py' = Get-CanonicalCodeSha256 -RepoRoot $RepoRoot -RelPath 'world_mcp.py'
    '/app/core/miniwob_world.py' = Get-CanonicalCodeSha256 -RepoRoot $RepoRoot -RelPath 'core/miniwob_world.py'
}
foreach ($path in $HostCode.Keys) {
    if ($HostCode[$path] -eq 'UNHASHABLE') {
        throw "Host code for $path differs from HEAD or git is unavailable; refusing to hash a dirty working tree."
    }
}
$HashProgram = 'import hashlib,json,sys; print(json.dumps({p:hashlib.sha256(open(p,chr(114)+chr(98)).read()).hexdigest() for p in sys.argv[1:]},sort_keys=True))'
$ImageCodeText = (& docker run --rm --network none --entrypoint python $ImageId -c $HashProgram `
    '/app/world_mcp.py' '/app/core/miniwob_world.py' 2>$null | Out-String).Trim()
if ($LASTEXITCODE -ne 0) { throw 'Could not inspect code inside the pinned world image.' }
try { $ImageCodeJson = $ImageCodeText | ConvertFrom-Json }
catch { throw 'World image code-hash receipt was malformed.' }
foreach ($path in $HostCode.Keys) {
    $property = $ImageCodeJson.PSObject.Properties[$path]
    if ($null -eq $property -or $property.Value -ne $HostCode[$path]) {
        throw "World image is stale: $path does not match the host source. Rebuild after merge."
    }
}

if ($Arm -eq 'red') {
    $McpArgs = @('run', '-i', '--rm', '--network', 'none',
        '--mount', "type=bind,source=$Roms,target=/app/roms,readonly",
        '--mount', "type=bind,source=$State,target=/app/red_start.state,readonly",
        '--mount', "type=bind,source=$WorldDir,target=/app/world",
        $ImageId, '--game', 'pokemon_red', '--init-state', '/app/red_start.state',
        '--out', '/app/world', '--keep-frames')
} else {
    $McpArgs = @('run', '-i', '--rm', '--network', 'none',
        '--mount', "type=bind,source=$Seeds,target=/app/seeds.json,readonly",
        '--mount', "type=bind,source=$WorldDir,target=/app/world",
        $ImageId, '--game', 'miniwob_click_checkboxes', '--seeds-file',
        '/app/seeds.json', '--out', '/app/world')
}

$CommonTask = 'Use only the connected world MCP tools and screen-derived state. Do not use shell, files, web, tool search, or connectors. Begin by observing. Stop when the stated task is complete.'
$Task = $TaskSentence + "`n" + $CommonTask + "`n"
$TaskPath = Join-Path $LaunchDir 'TASK.md'
Write-Utf8NoBom $TaskPath $Task
$CodexDir = Join-Path $LaunchDir '.codex'
[void](New-Item -ItemType Directory -Path $CodexDir)
$ConfigPath = Join-Path $CodexDir 'config.toml'
$TomlArgs = ($McpArgs | ForEach-Object { Quote-Toml $_ }) -join ', '
$TomlTools = ($Tools | ForEach-Object { Quote-Toml $_ }) -join ', '
$DeveloperInstruction = 'Use only gate0_world MCP tools. Never use shell, files, web, tool search, connectors, or other MCP servers.'
$BrainConfigText = (@"
model = $(Quote-Toml $Model)
forced_login_method = "chatgpt"
approval_policy = "never"
sandbox_mode = "read-only"
web_search = "disabled"
developer_instructions = $(Quote-Toml $DeveloperInstruction)

[history]
persistence = "none"

[features]
shell_tool = false
skill_mcp_dependency_install = false
apps = false
goals = false
hooks = false
memories = false
multi_agent = false

[apps._default]
enabled = false
"@).Trim() + "`n"
$WorldConfigText = (@"
[mcp_servers.$Server]
command = "docker"
args = [$TomlArgs]
cwd = $(Quote-Toml $RepoRoot)
required = true
enabled = true
enabled_tools = [$TomlTools]
default_tools_approval_mode = "auto"
"@).Trim() + "`n"
$ConfigText = $BrainConfigText + "`n" + $WorldConfigText
Write-Utf8NoBom $ConfigPath $ConfigText
$BrainConfigPath = Join-Path $OutputDir 'brain-config.toml'
Write-Utf8NoBom $BrainConfigPath $BrainConfigText

# These explicit overrides are the effective config. They do not depend on fresh-project trust.
$Overrides = @(
    "model=$(Quote-Toml $Model)", 'forced_login_method="chatgpt"', 'approval_policy="never"',
    'sandbox_mode="read-only"', 'web_search="disabled"',
    "developer_instructions=$(Quote-Toml $DeveloperInstruction)", 'history.persistence="none"',
    'features.shell_tool=false', 'features.skill_mcp_dependency_install=false', 'features.apps=false',
    'features.goals=false', 'features.hooks=false', 'features.memories=false',
    'features.multi_agent=false', 'apps._default.enabled=false',
    ("mcp_servers.$Server.command=" + (Quote-Toml 'docker')), "mcp_servers.$Server.args=[$TomlArgs]",
    "mcp_servers.$Server.cwd=$(Quote-Toml $RepoRoot)", "mcp_servers.$Server.required=true",
    "mcp_servers.$Server.enabled=true", "mcp_servers.$Server.enabled_tools=[$TomlTools]",
    ("mcp_servers.$Server.default_tools_approval_mode=" + (Quote-Toml 'auto'))
)

# Observe the config Codex itself accepts, from an empty CODEX_HOME. This command does not call a model
# and needs no authentication; the user's auth cache remains untouched in its original home.
$McpListPath = Join-Path $OutputDir 'codex-mcp-list.json'
$McpListErrPath = Join-Path $OutputDir 'codex-mcp-list.stderr.log'
$McpListArgs = @()
foreach ($override in $Overrides) { $McpListArgs += @('-c', $override) }
$McpListArgs += @('mcp', 'list', '--json')
$OldCodexHome = $env:CODEX_HOME
try {
    $env:CODEX_HOME = $IsolatedHome
    $McpListResult = Invoke-RedirectedProcess -ExecutablePath $ResolvedCodexPath -Arguments $McpListArgs
    Write-Utf8NoBom $McpListErrPath $McpListResult.StdErr
    if ($McpListResult.ExitCode -ne 0) { throw 'Codex rejected the isolated explicit MCP configuration.' }
    $McpListText = $McpListResult.StdOut.Trim()
} finally {
    if ($null -eq $OldCodexHome) { Remove-Item Env:CODEX_HOME -ErrorAction SilentlyContinue }
    else { $env:CODEX_HOME = $OldCodexHome }
}
Write-Utf8NoBom $McpListPath ($McpListText + "`n")
try { $McpList = @($McpListText | ConvertFrom-Json) }
catch { throw 'Codex MCP inventory was malformed.' }
if ($McpList.Count -ne 1 -or $McpList[0].name -ne $Server) {
    throw 'Codex did not observe exactly the gate0_world MCP server.'
}

# Observe the exact live MCP tool schemas directly from the immutable image. tools/list is lazy and
# does not boot the emulator/browser or inspect a held-out task instance.
$Rpc = @(
    '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"gate0-readiness","version":"1"}}}',
    '{"jsonrpc":"2.0","method":"notifications/initialized","params":{}}',
    '{"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}}'
) -join "`n"
$McpErrPath = Join-Path $OutputDir 'mcp-handshake.stderr.log'
$McpInput = $Rpc + "`n"
$McpOutput = ($McpInput | & docker @McpArgs 2>> $McpErrPath | Out-String).Trim()
if ($LASTEXITCODE -ne 0) { throw 'The immutable world MCP failed its direct tools/list handshake.' }
$Responses = @()
foreach ($line in ($McpOutput -split "`r?`n")) {
    if ($line.Trim()) {
        try { $Responses += ,($line | ConvertFrom-Json) }
        catch { throw 'The world MCP emitted malformed JSON during the handshake.' }
    }
}
$ToolsResponse = @($Responses | Where-Object { $_.id -eq 2 })
if ($ToolsResponse.Count -ne 1 -or $null -eq $ToolsResponse[0].result.tools) {
    throw 'The world MCP did not return exactly one tools/list result.'
}
$ObservedTools = @($ToolsResponse[0].result.tools)
$ObservedNames = @($ObservedTools | ForEach-Object { $_.name })
if (($ObservedNames | ConvertTo-Json -Compress) -ne ($Tools | ConvertTo-Json -Compress)) {
    throw 'The live world MCP tool inventory differs from the frozen allowlist.'
}
$ToolsPath = Join-Path $OutputDir 'mcp-tools.json'
$ToolsJson = $ObservedTools | ConvertTo-Json -Depth 20 -Compress
Write-Utf8NoBom $ToolsPath ($ToolsJson + "`n")

$Receipt = [ordered]@{
    schema_version = 2
    arm = $Arm
    readiness = 'NO_GO_INSUFFICIENT_WAKES'
    paid_execution_enabled = $false
    auth_method = 'chatgpt'
    planned_model = $Model
    codex_version = $versionText
    codex_path = $ResolvedCodexPath
    codex_executable_sha256 = Get-FileSha256 $ResolvedCodexPath
    critical_config_transport = 'explicit_cli_overrides'
    mcp_servers_observed = @($Server)
    mcp_tools_observed = $ObservedNames
    brain_config_sha256 = Get-FileSha256 $BrainConfigPath
    task_sha256 = Get-FileSha256 $TaskPath
    config_sha256 = Get-FileSha256 $ConfigPath
    codex_mcp_list_sha256 = Get-FileSha256 $McpListPath
    tool_schema_sha256 = Get-FileSha256 $ToolsPath
    world_image_tag = $ImageTag
    world_image_id = $ImageId
    host_code_sha256 = $HostCode
    image_code_sha256 = $ImageCodeJson
}
$ReceiptPath = Join-Path $OutputDir 'handshake-receipt.json'
Write-Utf8NoBom $ReceiptPath (($Receipt | ConvertTo-Json -Depth 8) + "`n")

# Live-breaker wiring point (pre-reg precondition 4, reports/2026-07-18-gate0-prereg.md;
# tools/gate0_credit_breaker.py). Without -PaidExec this script remains exactly what it always
# was -- free-handshake-only, no exec call, no spend, ending in the NO_GO receipt below. The
# `codex exec --json` path now exists ONLY behind -PaidExec (PR #118 checklist 4a-4d) and is
# refused unless a signed eval/fixtures/gate0_signature.json authorizes this exact commit
# (Confirm-PaidExecSignature, above). When it does run, Invoke-BreakerSupervisedExec feeds
# run_breaker(raise_on_trip=True, stall_timeout_s=StallTimeoutS) an ITERATOR pulled lazily from
# the live relayed stream (never a buffered/materialized source -- PR #118 breaker review MAJOR 1)
# and kills the codex child's WHOLE process tree the instant the accountant subprocess signals
# either breaker exception: BreakerTripped OR MalformedCreditStream (catching only the former is
# fail-open -- a malformed/stalled stream crashes the accountant while the child keeps spending).
# The 300 s stall backstop is pre-registered (STALL_TIMEOUT_S); the detector's halting correctness
# is proven against a synthetic stream in tests/test_gate0_credit_breaker.py and
# reports/2026-07-19-gate0-live-breaker-dry-run.md, and the wired path's own zero-spend stub-emitter
# TRIP receipt is banked at reports/2026-07-21-gate0-wired-breaker-trip.md (PR #118 checklist 4c).

if ($PaidExec) {
    $Signature = Confirm-PaidExecSignature -SignaturePath $SignaturePath -RepoRoot $RepoRoot `
        -Arm $Arm -Model $Model -ExpectedConfigSha256 $Receipt.config_sha256 `
        -ExpectedMcpListSha256 $Receipt.codex_mcp_list_sha256
    if ($StallTimeoutS -gt 300) {
        throw 'PaidExec refused: -StallTimeoutS may only tighten the pre-registered 300 s backstop, never loosen it.'
    }

    $PaidDir = Join-Path $OutputDir 'paid'
    [void](New-Item -ItemType Directory -Path $PaidDir -Force)
    $RatePinPath = Join-Path $PaidDir 'credit_rate_pin.json'
    Write-Utf8NoBom $RatePinPath (($Signature.credit_rate_pin | ConvertTo-Json -Depth 8) + "`n")

    # 4a preflight: the SAME Python validation the accountant subprocess uses, run once up front so
    # an invalid/absent/model-mismatched rate pin refuses BEFORE any process is spawned. Invoked by
    # absolute path (this module has no internal tools.* imports of its own -- see its docstring --
    # so unlike the accountant it never needs -m/cwd resolution).
    $RateCheckerPath = Join-Path $RepoRoot 'tools\gate0_codex_credit_rate.py'
    $PreflightResult = Invoke-RedirectedProcess -ExecutablePath 'python' -Arguments @(
        $RateCheckerPath, 'validate', '--rate-pin', $RatePinPath, '--model', $Model)
    if ($PreflightResult.ExitCode -ne 0) {
        throw "PaidExec refused: credit-rate pin failed preflight validation: $($PreflightResult.StdErr.Trim())"
    }

    $VerdictPath = Join-Path $PaidDir 'accountant-verdict.json'
    $ExecArgs = Get-PaidCodexExecArguments -Overrides $Overrides
    $Supervised = Invoke-BreakerSupervisedExec -ChildExecutable $ResolvedCodexPath -ChildArguments $ExecArgs `
        -ChildStdinText $Task -AccountantExecutable 'python' -WorkingDirectory $RepoRoot -AccountantArguments @(
            '-m', 'tools.gate0_credit_accountant', '--rate-pin', $RatePinPath, '--model', $Model,
            '--verdict-out', $VerdictPath, '--stall-timeout-s', $StallTimeoutS)

    $Verdict = if (Test-Path -LiteralPath $VerdictPath) {
        (Get-Content -LiteralPath $VerdictPath -Raw) | ConvertFrom-Json
    } else {
        [pscustomobject]@{ result = 'NO_VERDICT_WRITTEN' }
    }
    $PaidResult = [ordered]@{
        schema_version = 1
        kind = 'gate0_paid_exec_result'
        arm = $Arm
        signed_commit = $Signature.frozen_commit
        verdict = $Verdict
        supervision = $Supervised
    }
    $PaidResultPath = Join-Path $PaidDir 'paid-exec-result.json'
    Write-Utf8NoBom $PaidResultPath (($PaidResult | ConvertTo-Json -Depth 12) + "`n")
    Write-Output "paid_exec_result=$PaidResultPath"
    if ($Verdict.result -eq 'COMPLETED' -and -not $Supervised.ChildKilled) { exit 0 }
    exit 2
}

Write-Output 'readiness=NO_GO_INSUFFICIENT_WAKES'
Write-Output 'paid_execution_enabled=false'
Write-Output "receipt=$ReceiptPath"
exit 1
