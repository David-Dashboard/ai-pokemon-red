[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet('red', 'miniwob')]
    [string]$Arm,

    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[A-Za-z0-9][A-Za-z0-9._-]{1,127}$')]
    [string]$Model,

    [Parameter(Mandatory = $true)]
    [string]$OutputDir
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

function Invoke-CodexLoginStatus([string]$ExecutablePath) {
    $result = Invoke-RedirectedProcess -ExecutablePath $ExecutablePath -Arguments @('login', 'status')
    if ($result.ExitCode -ne 0) {
        throw "Codex login status command exited with code $($result.ExitCode)."
    }
    [string]$text = (($result.StdOut + "`n" + $result.StdErr).Trim())
    return [pscustomobject]@{ Text = $text; ExitCode = $result.ExitCode }
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
# the exact host code before even the free tools/list handshake is allowed.
$HostCode = [ordered]@{
    '/app/world_mcp.py' = Get-FileSha256 (Join-Path $RepoRoot 'world_mcp.py')
    '/app/core/miniwob_world.py' = Get-FileSha256 (Join-Path $RepoRoot 'core\miniwob_world.py')
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

Write-Output 'readiness=NO_GO_INSUFFICIENT_WAKES'
Write-Output 'paid_execution_enabled=false'
Write-Output "receipt=$ReceiptPath"
exit 1
