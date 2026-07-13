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

# Keep Codex's normal auth cache in place. A separate CODEX_HOME would lose the cached ChatGPT
# subscription session, and copying auth material would create a credential leak. Isolation instead
# comes from --ignore-user-config/--ignore-rules and the fresh launch repository below.
$codex = Get-Command codex -CommandType Application -ErrorAction Stop
$versionText = (& $codex.Source --version 2>$null | Out-String).Trim()
if ($LASTEXITCODE -ne 0 -or $versionText -notmatch '^codex(?:-cli)?\s+[0-9][0-9A-Za-z.+-]*$') {
    throw 'Codex version is unavailable or not safely parseable.'
}
if ($env:OPENAI_API_KEY -or $env:CODEX_API_KEY) {
    throw 'OPENAI_API_KEY or CODEX_API_KEY is set; Gate 0 requires unambiguous ChatGPT subscription authentication.'
}
$loginText = (& $codex.Source login status 2>&1 | Out-String).Trim()
if ($LASTEXITCODE -ne 0 -or $loginText -notmatch '(?i)\bchatgpt\b' -or
    $loginText -match '(?i)\bapi(?:[ -]?key)?\b') {
    throw 'Codex login status did not prove ChatGPT subscription authentication.'
}

$RepoRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$OutputDir = [IO.Path]::GetFullPath($OutputDir)
if (-not (Test-Path -LiteralPath $OutputDir)) {
    [void](New-Item -ItemType Directory -Path $OutputDir)
}
$LaunchDir = Join-Path $OutputDir 'launch'
$WorldDir = Join-Path $OutputDir 'world'
[void](New-Item -ItemType Directory -Path $LaunchDir)
[void](New-Item -ItemType Directory -Path $WorldDir)
& git init --quiet $LaunchDir
if ($LASTEXITCODE -ne 0) { throw 'Could not initialize the fresh launch git repository.' }

$Server = 'gate0_world'
if ($Arm -eq 'red') {
    $Tools = @('observe', 'explore', 'goto', 'remember', 'press_button', 'press_sequence', 'wait')
    $TaskSentence = 'From the fresh bedroom start, obtain your first Pokemon from Professor Oak and win the first rival battle.'
    $State = Join-Path $RepoRoot 'runs\red_start.state'
    $Roms = Join-Path $RepoRoot 'roms'
    if (-not (Test-Path -LiteralPath $State -PathType Leaf) -or
        -not (Test-Path -LiteralPath $Roms -PathType Container)) {
        throw 'The pinned Red state or ROM directory is unavailable.'
    }
    $McpArgs = @('run', '-i', '--rm', '--network', 'none',
        '--mount', "type=bind,source=$Roms,target=/app/roms,readonly",
        '--mount', "type=bind,source=$State,target=/app/red_start.state,readonly",
        '--mount', "type=bind,source=$WorldDir,target=/app/world",
        'gb-mcp-world', '--game', 'pokemon_red', '--init-state', '/app/red_start.state',
        '--out', '/app/world', '--keep-frames')
} else {
    $Tools = @('observe', 'read_region', 'whats_changed', 'click', 'type_text',
        'press_key', 'reset_episode')
    $TaskSentence = 'Complete five fresh episodes of the browser click-checkboxes task from their on-screen instructions using screen pixels and ordinary mouse and keyboard controls.'
    $Seeds = Join-Path $RepoRoot 'eval\fixtures\gate0_miniwob_paid_seeds.json'
    if (-not (Test-Path -LiteralPath $Seeds -PathType Leaf)) {
        throw 'The pinned MiniWoB seed manifest is unavailable.'
    }
    $McpArgs = @('run', '-i', '--rm', '--network', 'none',
        '--mount', "type=bind,source=$Seeds,target=/app/seeds.json,readonly",
        '--mount', "type=bind,source=$WorldDir,target=/app/world",
        'miniwob-world', '--game', 'miniwob_click_checkboxes', '--seeds-file',
        '/app/seeds.json', '--out', '/app/world')
}

$CommonTask = @'
Use only the connected world MCP tools and screen-derived state. Do not use shell, files, web, tool search, or connectors. Begin by observing. Stop when the stated task is complete.
'@
$Task = $TaskSentence + "`n" + $CommonTask.Trim() + "`n"
$TaskPath = Join-Path $LaunchDir 'TASK.md'
Write-Utf8NoBom $TaskPath $Task
$CodexDir = Join-Path $LaunchDir '.codex'
[void](New-Item -ItemType Directory -Path $CodexDir)
$ConfigPath = Join-Path $CodexDir 'config.toml'
$TomlArgs = ($McpArgs | ForEach-Object { Quote-Toml $_ }) -join ', '
$TomlTools = ($Tools | ForEach-Object { Quote-Toml $_ }) -join ', '
$BrainConfig = @"
model = $(Quote-Toml $Model)
forced_login_method = "chatgpt"
approval_policy = "never"
sandbox_mode = "read-only"
web_search = "disabled"
developer_instructions = "Use only gate0_world MCP tools. Never use shell, files, web, tool search, connectors, or other MCP servers."

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

"@
$WorldConfig = @"
[mcp_servers.$Server]
command = "docker"
args = [$TomlArgs]
cwd = $(Quote-Toml $RepoRoot)
required = true
enabled = true
enabled_tools = [$TomlTools]
default_tools_approval_mode = "auto"
"@
$BrainConfigText = $BrainConfig.Trim() + "`n"
$ConfigText = $BrainConfigText + "`n" + $WorldConfig.Trim() + "`n"
Write-Utf8NoBom $ConfigPath $ConfigText

$SchemaObject = [ordered]@{ server = $Server; tools = $Tools }
$SchemaJson = $SchemaObject | ConvertTo-Json -Compress
$Receipt = [ordered]@{
    schema_version = 1
    arm = $Arm
    auth_method = 'chatgpt'
    model = $Model
    codex_version = $versionText
    codex_path = $codex.Source
    codex_executable_sha256 = Get-FileSha256 $codex.Source
    mcp_servers = @($Server)
    mcp_tools = $Tools
    brain_config_sha256 = Get-BytesSha256 ([Text.Encoding]::UTF8.GetBytes($BrainConfigText))
    task_sha256 = Get-FileSha256 $TaskPath
    config_sha256 = Get-FileSha256 $ConfigPath
    tool_schema_sha256 = Get-BytesSha256 ([Text.Encoding]::UTF8.GetBytes($SchemaJson))
}
$ReceiptPath = Join-Path $OutputDir 'receipt.json'
Write-Utf8NoBom $ReceiptPath (($Receipt | ConvertTo-Json -Depth 4 -Compress) + "`n")

$TranscriptPath = Join-Path $OutputDir 'transcript.jsonl'
$StderrPath = Join-Path $OutputDir 'codex.stderr.log'
[void](New-Item -ItemType File -Path $TranscriptPath)
[void](New-Item -ItemType File -Path $StderrPath)
$Prompt = [IO.File]::ReadAllText($TaskPath)
Push-Location $LaunchDir
try {
    & $codex.Source exec --json --ephemeral --ignore-user-config --ignore-rules --sandbox read-only `
        --model $Model $Prompt 1>> $TranscriptPath 2>> $StderrPath
    $exitCode = $LASTEXITCODE
} finally {
    Pop-Location
}
exit $exitCode
