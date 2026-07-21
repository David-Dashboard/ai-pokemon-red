import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

from tools.check_gate0_codex import SERVER, TOOLS
import world_mcp


SCRIPT = (Path(__file__).parents[1] / "tools" / "run_gate0_codex.ps1").read_text(encoding="utf-8")
SCRIPT_PATH = Path(__file__).parents[1] / "tools" / "run_gate0_codex.ps1"
POWERSHELL = shutil.which("powershell") or shutil.which("pwsh")
requires_powershell = pytest.mark.skipif(
    POWERSHELL is None,
    reason="PowerShell is required to exercise the production resolver AST",
)
RESOLVER_HARNESS = r"""
$ErrorActionPreference = 'Stop'
$tokens = $null
$errors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile(
    $env:GATE0_LAUNCHER_PATH, [ref]$tokens, [ref]$errors)
if ($errors.Count -ne 0) { throw 'Launcher did not parse.' }
$functions = @($ast.FindAll({
    param($node)
    $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and
        $node.Name -eq 'Resolve-CodexExecutable'
}, $true))
if ($functions.Count -ne 1) { throw 'Expected exactly one resolver function definition.' }
Invoke-Expression $functions[0].Extent.Text
$decoded = $env:GATE0_CODEX_CANDIDATES | ConvertFrom-Json
$candidates = @($decoded | ForEach-Object { $_ })
$resolved = Resolve-CodexExecutable -Candidates $candidates
[Console]::Out.Write([string]$resolved)
"""
LOGIN_HARNESS = r"""
$ErrorActionPreference = 'Stop'
$tokens = $null
$errors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile(
    $env:GATE0_LAUNCHER_PATH, [ref]$tokens, [ref]$errors)
if ($errors.Count -ne 0) { throw 'Launcher did not parse.' }
$functionNames = @('ConvertTo-NativeArgument', 'Invoke-RedirectedProcess', 'Invoke-CodexLoginStatus')
foreach ($name in $functionNames) {
    $functions = @($ast.FindAll({
        param($node)
        $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and
            $node.Name -eq $name
    }, $true))
    if ($functions.Count -ne 1) { throw "Expected exactly one $name function definition." }
    Invoke-Expression $functions[0].Extent.Text
}
$oldDirectory = [Environment]::CurrentDirectory
try {
    [Environment]::CurrentDirectory = $env:GATE0_SYNTHETIC_DIR
    $result = Invoke-CodexLoginStatus -ExecutablePath $env:GATE0_SYNTHETIC_EXECUTABLE
    [Console]::Out.Write(($result | ConvertTo-Json -Compress))
} finally {
    [Environment]::CurrentDirectory = $oldDirectory
}
"""
HASH_HARNESS = r"""
$ErrorActionPreference = 'Stop'
$tokens = $null
$errors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile(
    $env:GATE0_LAUNCHER_PATH, [ref]$tokens, [ref]$errors)
if ($errors.Count -ne 0) { throw 'Launcher did not parse.' }
$assignments = @($ast.FindAll({
    param($node)
    $node -is [System.Management.Automation.Language.AssignmentStatementAst] -and
        $node.Left.Extent.Text -eq '$HashProgram'
}, $true))
if ($assignments.Count -ne 1) { throw 'Expected exactly one hash-program assignment.' }
$program = Invoke-Expression $assignments[0].Right.Extent.Text
$output = & $env:GATE0_SYNTHETIC_EXECUTABLE -c $program $env:GATE0_HASH_FILE
if ($LASTEXITCODE -ne 0) { throw 'Hash program failed through PowerShell native invocation.' }
[Console]::Out.Write(($output | Out-String).Trim())
"""
CANONICAL_CODE_HASH_HARNESS = r"""
$ErrorActionPreference = 'Stop'
$tokens = $null
$errors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile(
    $env:GATE0_LAUNCHER_PATH, [ref]$tokens, [ref]$errors)
if ($errors.Count -ne 0) { throw 'Launcher did not parse.' }
foreach ($name in @('ConvertTo-NativeArgument', 'Get-BytesSha256', 'Invoke-GitBytes',
        'Get-CanonicalCodeSha256')) {
    $functions = @($ast.FindAll({
        param($node)
        $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and
            $node.Name -eq $name
    }, $true))
    if ($functions.Count -ne 1) { throw "Expected exactly one $name function definition." }
    Invoke-Expression $functions[0].Extent.Text
}
$result = Get-CanonicalCodeSha256 -RepoRoot $env:GATE0_REPO_ROOT -RelPath $env:GATE0_REL_PATH
[Console]::Out.Write([string]$result)
"""
NATIVE_ARGUMENT_HARNESS = r"""
$ErrorActionPreference = 'Stop'
$tokens = $null
$errors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile(
    $env:GATE0_LAUNCHER_PATH, [ref]$tokens, [ref]$errors)
if ($errors.Count -ne 0) { throw 'Launcher did not parse.' }
foreach ($name in @('ConvertTo-NativeArgument', 'Invoke-RedirectedProcess')) {
    $functions = @($ast.FindAll({
        param($node)
        $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and
            $node.Name -eq $name
    }, $true))
    if ($functions.Count -ne 1) { throw "Expected exactly one $name function definition." }
    Invoke-Expression $functions[0].Extent.Text
}
$arguments = @($env:GATE0_NATIVE_ARGUMENTS | ConvertFrom-Json | ForEach-Object { $_ })
$result = Invoke-RedirectedProcess -ExecutablePath $env:GATE0_SYNTHETIC_EXECUTABLE -Arguments $arguments
if ($result.ExitCode -ne 0) { throw "Synthetic native process exited $($result.ExitCode)." }
[Console]::Out.Write($result.StdOut)
"""


def run_production_resolver(*sources):
    env = os.environ.copy()
    env["GATE0_LAUNCHER_PATH"] = str(SCRIPT_PATH)
    env["GATE0_CODEX_CANDIDATES"] = json.dumps([{"Source": source} for source in sources])
    return subprocess.run(
        [POWERSHELL, "-NoProfile", "-NonInteractive", "-Command", RESOLVER_HARNESS],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )


def run_production_login_helper(directory):
    env = os.environ.copy()
    env["GATE0_LAUNCHER_PATH"] = str(SCRIPT_PATH)
    env["GATE0_SYNTHETIC_DIR"] = str(directory)
    env["GATE0_SYNTHETIC_EXECUTABLE"] = sys.executable
    return subprocess.run(
        [POWERSHELL, "-NoProfile", "-NonInteractive", "-Command", LOGIN_HARNESS],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )


def run_production_hash_program(path):
    env = os.environ.copy()
    env["GATE0_LAUNCHER_PATH"] = str(SCRIPT_PATH)
    env["GATE0_HASH_FILE"] = str(path)
    env["GATE0_SYNTHETIC_EXECUTABLE"] = sys.executable
    return subprocess.run(
        [POWERSHELL, "-NoProfile", "-NonInteractive", "-Command", HASH_HARNESS],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )


def run_production_canonical_code_hash(repo_root, rel_path):
    env = os.environ.copy()
    env["GATE0_LAUNCHER_PATH"] = str(SCRIPT_PATH)
    env["GATE0_REPO_ROOT"] = str(repo_root)
    env["GATE0_REL_PATH"] = rel_path
    return subprocess.run(
        [POWERSHELL, "-NoProfile", "-NonInteractive", "-Command", CANONICAL_CODE_HASH_HARNESS],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )


def _git(*args, cwd):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


CANONICAL_SAMPLE = b"a = 1\nb = 2\n"


def _init_lf_repo(path):
    path.mkdir(parents=True, exist_ok=True)
    _git("init", "--quiet", ".", cwd=path)
    _git("config", "user.email", "test@example.com", cwd=path)
    _git("config", "user.name", "test", cwd=path)
    _git("config", "core.autocrlf", "false", cwd=path)
    (path / "sample.py").write_bytes(CANONICAL_SAMPLE)
    _git("add", "sample.py", cwd=path)
    _git("commit", "--quiet", "-m", "init", cwd=path)


def run_redirected_process(*arguments):
    env = os.environ.copy()
    env["GATE0_LAUNCHER_PATH"] = str(SCRIPT_PATH)
    env["GATE0_NATIVE_ARGUMENTS"] = json.dumps(arguments)
    env["GATE0_SYNTHETIC_EXECUTABLE"] = sys.executable
    return subprocess.run(
        [POWERSHELL, "-NoProfile", "-NonInteractive", "-Command", NATIVE_ARGUMENT_HARNESS],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )


def test_launcher_is_free_handshake_only_and_fail_closed():
    assert "[ValidateSet('red', 'miniwob')]" in SCRIPT
    assert SCRIPT.count("[Parameter(Mandatory = $true)]") == 3
    assert "OutputDir must not exist or must be empty" in SCRIPT
    assert "$codex.Source exec" not in SCRIPT
    assert "paid_execution_enabled = $false" in SCRIPT
    assert "readiness = 'NO_GO_INSUFFICIENT_WAKES'" in SCRIPT
    assert SCRIPT.rstrip().endswith("exit 1")


def test_launcher_documents_the_live_breaker_wiring_point_without_adding_exec():
    # Pre-reg precondition 4 (reports/2026-07-18-gate0-prereg.md): the breaker is built and proven
    # in tools/gate0_credit_breaker.py, and this script names it as the future paid launcher's
    # integration point -- WITHOUT adding a live `codex exec` call here (that would break the
    # free-handshake-only invariant asserted above, which stays load-bearing until a separate paid
    # launcher exists).
    assert "tools/gate0_credit_breaker.py" in SCRIPT
    # Kill contract names BOTH breaker exceptions (review MINOR 2) and the pre-registered
    # stall backstop (review MINOR 3a) -- catching only BreakerTripped is fail-open.
    assert "BreakerTripped" in SCRIPT
    assert "MalformedCreditStream" in SCRIPT
    assert "stall" in SCRIPT.lower()
    assert "$codex.Source exec" not in SCRIPT
    assert SCRIPT.rstrip().endswith("exit 1")


def test_launcher_proves_chatgpt_auth_without_copying_it():
    assert "& $ResolvedCodexPath --version" in SCRIPT
    assert "Invoke-CodexLoginStatus -ExecutablePath $ResolvedCodexPath" in SCRIPT
    assert "$loginText = $loginStatus.Text" in SCRIPT
    assert "$env:OPENAI_API_KEY -or $env:CODEX_API_KEY" in SCRIPT
    assert "did not prove ChatGPT subscription authentication" in SCRIPT
    assert "latest alias" in SCRIPT
    assert "Copy-Item" not in SCRIPT and "auth.json" not in SCRIPT


@requires_powershell
def test_login_helper_captures_success_written_to_stderr(tmp_path):
    (tmp_path / "login").write_text(
        "import sys\nsys.stderr.write('Logged in using ChatGPT\\n')\nsys.exit(0)\n",
        encoding="utf-8",
    )
    result = run_production_login_helper(tmp_path)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {
        "Text": "Logged in using ChatGPT",
        "ExitCode": 0,
    }


@requires_powershell
def test_login_helper_rejects_nonzero_exit(tmp_path):
    (tmp_path / "login").write_text(
        "import sys\nsys.stderr.write('Logged in using ChatGPT\\n')\nsys.exit(7)\n",
        encoding="utf-8",
    )
    result = run_production_login_helper(tmp_path)
    assert result.returncode != 0
    assert "Codex login status command exited with code 7" in result.stderr


@requires_powershell
def test_image_hash_program_survives_powershell_native_argument_quoting(tmp_path):
    source = tmp_path / "source.bin"
    source.write_bytes(b"gate0-hash-probe")
    result = run_production_hash_program(source)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {
        str(source): hashlib.sha256(source.read_bytes()).hexdigest(),
    }


@requires_powershell
def test_redirected_process_preserves_toml_array_argument():
    toml_array = 'mcp_servers.gate0_world.args=["run","-i","C:\\world path"]'
    result = run_redirected_process("-c", "import json,sys; print(json.dumps(sys.argv[1:]))", toml_array)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == [toml_array]


@requires_powershell
def test_launcher_resolver_selects_one_exe_over_extensionless_candidate():
    result = run_production_resolver(r"C:\Tools\CoDeX.ExE", r"C:\Tools\codex")
    assert result.returncode == 0, result.stderr
    assert result.stdout == r"C:\Tools\CoDeX.ExE"


@requires_powershell
def test_launcher_resolver_fails_without_exe_candidate():
    result = run_production_resolver(r"C:\Tools\codex")
    assert result.returncode != 0
    assert "Expected exactly one Codex .exe application candidate; found 0" in result.stderr


@requires_powershell
def test_launcher_resolver_fails_with_multiple_exe_candidates():
    result = run_production_resolver(r"C:\One\codex.exe", r"C:\Two\CODEX.EXE")
    assert result.returncode != 0
    assert "Expected exactly one Codex .exe application candidate; found 2" in result.stderr


def test_launcher_uses_only_the_scalar_resolved_codex_path():
    assert "Resolve-CodexExecutable -Candidates @(" in SCRIPT
    assert "Get-Command codex -CommandType Application -All" in SCRIPT
    assert SCRIPT.count("& $ResolvedCodexPath") == 1
    assert "codex_path = $ResolvedCodexPath" in SCRIPT
    assert "Get-FileSha256 $ResolvedCodexPath" in SCRIPT
    assert "$codex.Source" not in SCRIPT


def test_effective_config_uses_explicit_overrides_in_isolated_home():
    assert "critical_config_transport = 'explicit_cli_overrides'" in SCRIPT
    assert "foreach ($override in $Overrides)" in SCRIPT
    assert "$McpListArgs += @('mcp', 'list', '--json')" in SCRIPT
    assert "$env:CODEX_HOME = $IsolatedHome" in SCRIPT
    assert "Invoke-RedirectedProcess -ExecutablePath $ResolvedCodexPath -Arguments $McpListArgs" in SCRIPT
    for setting in ("approval_policy", "sandbox_mode", "web_search",
                    "features.shell_tool", "apps._default.enabled"):
        assert setting in SCRIPT


def test_launcher_pins_image_and_compares_host_to_image_code():
    assert "docker image inspect --format '{{.Id}}'" in SCRIPT
    assert "$ImageId -notmatch '^sha256:[0-9a-f]{64}$'" in SCRIPT
    assert "$ImageId, '--game'" in SCRIPT
    assert "'/app/world_mcp.py'" in SCRIPT
    assert "'/app/core/miniwob_world.py'" in SCRIPT
    assert "open(p,chr(114)+chr(98))" in SCRIPT
    assert "World image is stale" in SCRIPT


def test_host_code_hash_is_canonical_git_blob_not_worktree_bytes():
    # PR #114 readiness-audit MAJOR: raw working-tree-byte hashing made host_code_sha256
    # non-reproducible across machines with different core.autocrlf settings. The launcher must
    # use the canonical git-blob hash (contract: world_mcp.py::code_sha256) for the two code
    # files and refuse a dirty working tree rather than silently pinning unreviewed bytes.
    assert "Get-CanonicalCodeSha256 -RepoRoot $RepoRoot -RelPath 'world_mcp.py'" in SCRIPT
    assert "Get-CanonicalCodeSha256 -RepoRoot $RepoRoot -RelPath 'core/miniwob_world.py'" in SCRIPT
    assert "world_mcp.py::code_sha256" in SCRIPT
    assert "'UNHASHABLE'" in SCRIPT
    assert "refusing to hash a dirty working tree" in SCRIPT
    assert "Get-FileSha256 (Join-Path $RepoRoot 'world_mcp.py')" not in SCRIPT
    assert "Get-FileSha256 (Join-Path $RepoRoot 'core\\miniwob_world.py')" not in SCRIPT


@requires_powershell
def test_canonical_code_hash_identical_across_lf_and_crlf_checkouts(tmp_path):
    lf_repo = tmp_path / "lf"
    _init_lf_repo(lf_repo)
    lf_result = run_production_canonical_code_hash(lf_repo, "sample.py")
    assert lf_result.returncode == 0, lf_result.stderr
    assert lf_result.stdout == hashlib.sha256(CANONICAL_SAMPLE).hexdigest()

    # A clone of the SAME commit checked out with core.autocrlf=true materializes CRLF bytes on
    # disk -- raw-byte hashing would diverge here; the canonical git-blob hash must not.
    crlf_repo = tmp_path / "crlf"
    subprocess.run(["git", "clone", "--quiet", "-c", "core.autocrlf=true",
                    str(lf_repo), str(crlf_repo)], check=True, capture_output=True)
    crlf_bytes = (crlf_repo / "sample.py").read_bytes()
    assert b"\r\n" in crlf_bytes
    assert hashlib.sha256(crlf_bytes).hexdigest() != lf_result.stdout
    crlf_result = run_production_canonical_code_hash(crlf_repo, "sample.py")
    assert crlf_result.returncode == 0, crlf_result.stderr
    assert crlf_result.stdout == lf_result.stdout


@requires_powershell
def test_canonical_code_hash_refuses_dirty_worktree(tmp_path):
    repo = tmp_path / "repo"
    _init_lf_repo(repo)
    (repo / "sample.py").write_bytes(CANONICAL_SAMPLE + b"c = 3\n")
    result = run_production_canonical_code_hash(repo, "sample.py")
    assert result.returncode == 0, result.stderr
    assert result.stdout == "UNHASHABLE"


@requires_powershell
def test_canonical_code_hash_agrees_with_world_mcp_primitive(tmp_path):
    # world_mcp.code_sha256() is the contract; the launcher's PowerShell reimplementation must
    # produce the identical value on the identical repo, and the identical refusal when dirty.
    repo = tmp_path / "repo"
    _init_lf_repo(repo)
    ps_hash = run_production_canonical_code_hash(repo, "sample.py")
    assert ps_hash.returncode == 0, ps_hash.stderr
    assert ps_hash.stdout == world_mcp.code_sha256(repo / "sample.py", repo_root=repo)

    (repo / "sample.py").write_bytes(CANONICAL_SAMPLE + b"c = 3\n")
    ps_dirty = run_production_canonical_code_hash(repo, "sample.py")
    assert ps_dirty.returncode == 0, ps_dirty.stderr
    assert ps_dirty.stdout == "UNHASHABLE"
    assert world_mcp.code_sha256(repo / "sample.py", repo_root=repo) == "UNHASHABLE"


def test_live_tools_list_must_exactly_match_frozen_inventory():
    assert "$Server = 'gate0_world'" in SCRIPT and SERVER == "gate0_world"
    assert '"method":"tools/list"' in SCRIPT
    assert "ObservedNames" in SCRIPT
    assert "live world MCP tool inventory differs from the frozen allowlist" in SCRIPT
    for tool in TOOLS["red"] + TOOLS["miniwob"]:
        assert f"'{tool}'" in SCRIPT


def test_worlds_tasks_and_network_are_pinned():
    assert "gb-mcp-world" in SCRIPT and "runs\\red_start.state" in SCRIPT
    assert "miniwob-world" in SCRIPT and "gate0_miniwob_paid_seeds.json" in SCRIPT
    assert "--network', 'none'" in SCRIPT
    assert "From the fresh bedroom start" in SCRIPT
    assert "Complete five fresh episodes" in SCRIPT


def test_receipt_contains_observed_security_evidence():
    for field in ("codex_executable_sha256", "mcp_servers_observed", "mcp_tools_observed",
                  "codex_mcp_list_sha256", "tool_schema_sha256", "world_image_id",
                  "host_code_sha256", "image_code_sha256"):
        assert f"{field} =" in SCRIPT
