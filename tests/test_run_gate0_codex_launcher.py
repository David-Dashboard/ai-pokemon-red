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
SIGNATURE_HARNESS = r"""
$ErrorActionPreference = 'Stop'
$tokens = $null
$errors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile(
    $env:GATE0_LAUNCHER_PATH, [ref]$tokens, [ref]$errors)
if ($errors.Count -ne 0) { throw 'Launcher did not parse.' }
foreach ($name in @('ConvertTo-NativeArgument', 'Invoke-GitBytes', 'Get-BytesSha256',
        'Get-CanonicalCodeSha256', 'Get-GitHeadCommit', 'Confirm-PaidExecSignature')) {
    $functions = @($ast.FindAll({
        param($node)
        $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and
            $node.Name -eq $name
    }, $true))
    if ($functions.Count -ne 1) { throw "Expected exactly one $name function definition." }
    Invoke-Expression $functions[0].Extent.Text
}
# $Gate0SafetyCriticalFiles (PR #122 Finding 1) is a script-scope assignment, not a function --
# extract its actual right-hand-side text from the real file (same technique HASH_HARNESS already
# uses for $HashProgram below) so this harness can never silently drift from the production list.
$assignments = @($ast.FindAll({
    param($node)
    $node -is [System.Management.Automation.Language.AssignmentStatementAst] -and
        $node.Left.Extent.Text -eq '$Gate0SafetyCriticalFiles'
}, $true))
if ($assignments.Count -ne 1) { throw 'Expected exactly one Gate0SafetyCriticalFiles assignment.' }
$Gate0SafetyCriticalFiles = Invoke-Expression $assignments[0].Right.Extent.Text
$signature = Confirm-PaidExecSignature -SignaturePath $env:GATE0_SIGNATURE_PATH `
    -RepoRoot $env:GATE0_REPO_ROOT -Arm $env:GATE0_ARM -Model $env:GATE0_MODEL `
    -ExpectedConfigSha256 $env:GATE0_EXPECTED_CONFIG_SHA256 `
    -ExpectedMcpListSha256 $env:GATE0_EXPECTED_MCP_LIST_SHA256
[Console]::Out.Write(($signature | ConvertTo-Json -Depth 8 -Compress))
"""
PAID_EXEC_ARGS_HARNESS = r"""
$ErrorActionPreference = 'Stop'
$tokens = $null
$errors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile(
    $env:GATE0_LAUNCHER_PATH, [ref]$tokens, [ref]$errors)
if ($errors.Count -ne 0) { throw 'Launcher did not parse.' }
$functions = @($ast.FindAll({
    param($node)
    $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and
        $node.Name -eq 'Get-PaidCodexExecArguments'
}, $true))
if ($functions.Count -ne 1) { throw 'Expected exactly one Get-PaidCodexExecArguments function definition.' }
Invoke-Expression $functions[0].Extent.Text
$overrides = @($env:GATE0_OVERRIDES | ConvertFrom-Json | ForEach-Object { $_ })
$result = Get-PaidCodexExecArguments -Overrides $overrides
[Console]::Out.Write(($result | ConvertTo-Json -Compress))
"""
BREAKER_SUPERVISED_EXEC_HARNESS = r"""
$ErrorActionPreference = 'Stop'
$tokens = $null
$errors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile(
    $env:GATE0_LAUNCHER_PATH, [ref]$tokens, [ref]$errors)
if ($errors.Count -ne 0) { throw 'Launcher did not parse.' }
foreach ($name in @('ConvertTo-NativeArgument', 'Get-Gate0KillOnCloseJob', 'Invoke-BreakerSupervisedExec')) {
    $functions = @($ast.FindAll({
        param($node)
        $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and
            $node.Name -eq $name
    }, $true))
    if ($functions.Count -ne 1) { throw "Expected exactly one $name function definition." }
    Invoke-Expression $functions[0].Extent.Text
}
$childArgs = @($env:GATE0_CHILD_ARGS | ConvertFrom-Json | ForEach-Object { $_ })
$accountantArgs = @($env:GATE0_ACCOUNTANT_ARGS | ConvertFrom-Json | ForEach-Object { $_ })
$result = Invoke-BreakerSupervisedExec -ChildExecutable $env:GATE0_CHILD_EXE -ChildArguments $childArgs `
    -AccountantExecutable $env:GATE0_ACCOUNTANT_EXE -AccountantArguments $accountantArgs `
    -WorkingDirectory $env:GATE0_WORKING_DIR -PollIntervalMs 50 -MaxWallClockS 30
[Console]::Out.Write(($result | ConvertTo-Json -Depth 6 -Compress))
"""
LEDGER_HARNESS = r"""
$ErrorActionPreference = 'Stop'
$tokens = $null
$errors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile(
    $env:GATE0_LAUNCHER_PATH, [ref]$tokens, [ref]$errors)
if ($errors.Count -ne 0) { throw 'Launcher did not parse.' }
foreach ($name in @('Write-Utf8NoBom', 'Get-Gate0CombinedCreditLedger',
        'Confirm-CombinedCreditBudgetAvailable', 'Add-Gate0CombinedCreditLedgerEntry')) {
    $functions = @($ast.FindAll({
        param($node)
        $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and
            $node.Name -eq $name
    }, $true))
    if ($functions.Count -ne 1) { throw "Expected exactly one $name function definition." }
    Invoke-Expression $functions[0].Extent.Text
}
# $Gate0CombinedCreditLimit is a script-scope assignment (PR #122 M4), not a function -- extract
# its real value the same way SIGNATURE_HARNESS extracts $Gate0SafetyCriticalFiles, so this harness
# can never silently drift from the production default.
$limitAssignments = @($ast.FindAll({
    param($node)
    $node -is [System.Management.Automation.Language.AssignmentStatementAst] -and
        $node.Left.Extent.Text -eq '$Gate0CombinedCreditLimit'
}, $true))
if ($limitAssignments.Count -ne 1) { throw 'Expected exactly one Gate0CombinedCreditLimit assignment.' }
$Gate0CombinedCreditLimit = Invoke-Expression $limitAssignments[0].Right.Extent.Text
$ledger = Get-Gate0CombinedCreditLedger -LedgerPath $env:GATE0_LEDGER_PATH
if ($env:GATE0_LEDGER_CONFIRM_BUDGET -eq 'true') {
    Confirm-CombinedCreditBudgetAvailable -Ledger $ledger -Limit ([int]$env:GATE0_LEDGER_LIMIT)
}
if ($env:GATE0_LEDGER_NEW_TOTAL) {
    $ledger = Add-Gate0CombinedCreditLedgerEntry -LedgerPath $env:GATE0_LEDGER_PATH -Ledger $ledger `
        -Arm $env:GATE0_LEDGER_ARM -NewTotal ([double]$env:GATE0_LEDGER_NEW_TOTAL) -Result $env:GATE0_LEDGER_RESULT
}
[Console]::Out.Write(($ledger | ConvertTo-Json -Depth 8 -Compress))
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


def _git_head(cwd):
    return subprocess.run(["git", "rev-parse", "HEAD"], cwd=cwd, check=True,
                           capture_output=True, text=True).stdout.strip()


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


# PR #122 review Finding 1: Confirm-PaidExecSignature now pins these four files too (the ones that
# ARE the paid-exec safety mechanism). Tests need a throwaway repo that actually contains them
# (unlike _init_lf_repo's single sample.py) so a real Get-CanonicalCodeSha256 hash can be computed
# and round-tripped through a signature.
SAFETY_CRITICAL_FIELD_BY_RELPATH = {
    "tools/run_gate0_codex.ps1": "expected_launcher_sha256",
    "tools/gate0_credit_breaker.py": "expected_credit_breaker_sha256",
    "tools/gate0_credit_accountant.py": "expected_credit_accountant_sha256",
    "tools/gate0_codex_credit_rate.py": "expected_credit_rate_sha256",
}


def _init_repo_with_safety_critical_files(path):
    """Commits placeholder content at the four safety-critical paths and returns
    {field_name: canonical_git_blob_sha256} ready to splice into a signature JSON."""
    path.mkdir(parents=True, exist_ok=True)
    _git("init", "--quiet", ".", cwd=path)
    _git("config", "user.email", "test@example.com", cwd=path)
    _git("config", "user.name", "test", cwd=path)
    _git("config", "core.autocrlf", "false", cwd=path)
    hashes = {}
    for relpath, field in SAFETY_CRITICAL_FIELD_BY_RELPATH.items():
        full = path / relpath
        full.parent.mkdir(parents=True, exist_ok=True)
        body = f"# placeholder content for {relpath}\n".encode("utf-8")
        full.write_bytes(body)
        hashes[field] = hashlib.sha256(body).hexdigest()
    _git("add", "tools", cwd=path)
    _git("commit", "--quiet", "-m", "init", cwd=path)
    return hashes


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


def run_confirm_paid_exec_signature(signature_path, repo_root, arm, model,
                                     expected_config_sha256, expected_mcp_list_sha256):
    env = os.environ.copy()
    env["GATE0_LAUNCHER_PATH"] = str(SCRIPT_PATH)
    env["GATE0_SIGNATURE_PATH"] = str(signature_path)
    env["GATE0_REPO_ROOT"] = str(repo_root)
    env["GATE0_ARM"] = arm
    env["GATE0_MODEL"] = model
    env["GATE0_EXPECTED_CONFIG_SHA256"] = expected_config_sha256
    env["GATE0_EXPECTED_MCP_LIST_SHA256"] = expected_mcp_list_sha256
    return subprocess.run(
        [POWERSHELL, "-NoProfile", "-NonInteractive", "-Command", SIGNATURE_HARNESS],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )


def run_get_paid_codex_exec_arguments(overrides):
    env = os.environ.copy()
    env["GATE0_LAUNCHER_PATH"] = str(SCRIPT_PATH)
    env["GATE0_OVERRIDES"] = json.dumps(overrides)
    return subprocess.run(
        [POWERSHELL, "-NoProfile", "-NonInteractive", "-Command", PAID_EXEC_ARGS_HARNESS],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )


def run_breaker_supervised_exec(child_exe, child_args, accountant_exe, accountant_args, working_dir):
    env = os.environ.copy()
    env["GATE0_LAUNCHER_PATH"] = str(SCRIPT_PATH)
    env["GATE0_CHILD_EXE"] = child_exe
    env["GATE0_CHILD_ARGS"] = json.dumps(child_args)
    env["GATE0_ACCOUNTANT_EXE"] = accountant_exe
    env["GATE0_ACCOUNTANT_ARGS"] = json.dumps(accountant_args)
    env["GATE0_WORKING_DIR"] = str(working_dir)
    return subprocess.run(
        [POWERSHELL, "-NoProfile", "-NonInteractive", "-Command", BREAKER_SUPERVISED_EXEC_HARNESS],
        capture_output=True,
        text=True,
        env=env,
        check=False,
        timeout=60,
    )


def run_combined_credit_ledger(ledger_path, confirm_budget=False, limit=250,
                                new_total=None, arm="red", result="TRIPPED"):
    env = os.environ.copy()
    env["GATE0_LAUNCHER_PATH"] = str(SCRIPT_PATH)
    env["GATE0_LEDGER_PATH"] = str(ledger_path)
    env["GATE0_LEDGER_CONFIRM_BUDGET"] = "true" if confirm_budget else "false"
    env["GATE0_LEDGER_LIMIT"] = str(limit)
    env["GATE0_LEDGER_ARM"] = arm
    env["GATE0_LEDGER_RESULT"] = result
    if new_total is not None:
        env["GATE0_LEDGER_NEW_TOTAL"] = str(new_total)
    else:
        env.pop("GATE0_LEDGER_NEW_TOTAL", None)
    return subprocess.run(
        [POWERSHELL, "-NoProfile", "-NonInteractive", "-Command", LEDGER_HARNESS],
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


# --------------------------------------------------------------------------------------------
# PR #118 checklist 4a-4d: the -PaidExec path. Every test in this section either (a) proves the
# flagless default is untouched via static text checks (mirroring the style above), or (b)
# extracts and runs the exact new production functions standalone, per this file's established
# AST-harness pattern -- never the full script (which needs real docker/ROMs/auth this suite must
# not depend on).
# --------------------------------------------------------------------------------------------

ROOT = Path(__file__).parents[1]


def test_paidexec_switch_is_optional_and_does_not_add_a_mandatory_param():
    # The free-handshake-only invariant's own test pins this at exactly 3 -- restated here so a
    # future edit that accidentally makes a paid-exec param Mandatory fails loudly in THIS file
    # too, next to the feature it would break.
    assert SCRIPT.count("[Parameter(Mandatory = $true)]") == 3
    assert "[switch]$PaidExec" in SCRIPT
    assert "[double]$StallTimeoutS = 300" in SCRIPT


def test_paidexec_block_is_gated_and_precedes_the_unchanged_tail():
    assert "if ($PaidExec) {" in SCRIPT
    gate_idx = SCRIPT.index("if ($PaidExec) {")
    tail_idx = SCRIPT.index("Write-Output 'readiness=NO_GO_INSUFFICIENT_WAKES'")
    assert gate_idx < tail_idx, "the paid-exec block must run and exit before the free-handshake tail"
    assert SCRIPT.rstrip().endswith("exit 1")


def test_paidexec_refuses_a_looser_stall_timeout_than_the_pinned_default():
    assert "StallTimeoutS -gt 300" in SCRIPT
    assert "never loosen it" in SCRIPT


def test_paidexec_signature_gate_checks_commit_arm_model_and_both_hashes():
    assert "Confirm-PaidExecSignature" in SCRIPT
    assert "$signature.frozen_commit -ne $headCommit" in SCRIPT
    assert "$signature.arm -ne $Arm" in SCRIPT
    assert "$signature.planned_model -ne $Model" in SCRIPT
    assert "$signature.expected_config_sha256 -ne $ExpectedConfigSha256" in SCRIPT
    assert "$signature.expected_codex_mcp_list_sha256 -ne $ExpectedMcpListSha256" in SCRIPT
    assert "credit_rate_pin" in SCRIPT


def test_paidexec_kill_contract_covers_both_breaker_exceptions_and_tree_kills():
    assert "taskkill.exe /PID" in SCRIPT and "/T /F" in SCRIPT
    assert "CopyToAsync" in SCRIPT  # live relay, never a materialized buffer
    assert "gate0_credit_accountant" in SCRIPT


@requires_powershell
def test_confirm_signature_refuses_when_file_is_absent(tmp_path):
    result = run_confirm_paid_exec_signature(
        tmp_path / "does-not-exist.json", tmp_path, "red", "gpt-5.6-sol", "a" * 64, "b" * 64)
    assert result.returncode != 0
    assert "no signature file at" in result.stderr


@requires_powershell
def test_confirm_signature_refuses_on_commit_mismatch(tmp_path):
    repo = tmp_path / "repo"
    _init_lf_repo(repo)
    signature = tmp_path / "sig.json"
    signature.write_text(json.dumps({
        "schema_version": 1, "frozen_commit": "0" * 40, "arm": "red", "planned_model": "gpt-5.6-sol",
        "expected_config_sha256": "a" * 64, "expected_codex_mcp_list_sha256": "b" * 64,
        "credit_rate_pin": {"model": "gpt-5.6-sol"},
    }), encoding="utf-8")
    result = run_confirm_paid_exec_signature(signature, repo, "red", "gpt-5.6-sol", "a" * 64, "b" * 64)
    assert result.returncode != 0
    assert "checkout is at" in result.stderr


@requires_powershell
def test_confirm_signature_refuses_without_credit_rate_pin(tmp_path):
    repo = tmp_path / "repo"
    _init_lf_repo(repo)
    head = _git_head(repo)
    signature = tmp_path / "sig.json"
    signature.write_text(json.dumps({
        "schema_version": 1, "frozen_commit": head, "arm": "red", "planned_model": "gpt-5.6-sol",
        "expected_config_sha256": "a" * 64, "expected_codex_mcp_list_sha256": "b" * 64,
    }), encoding="utf-8")
    result = run_confirm_paid_exec_signature(signature, repo, "red", "gpt-5.6-sol", "a" * 64, "b" * 64)
    assert result.returncode != 0
    assert "no credit_rate_pin" in result.stderr


@requires_powershell
def test_confirm_signature_refuses_when_a_safety_critical_hash_pin_is_missing(tmp_path):
    # PR #122 review Finding 1: a signature naming the right commit but not ALSO pinning the four
    # safety-critical files is refused -- naming a commit alone is not enough.
    repo = tmp_path / "repo"
    _init_repo_with_safety_critical_files(repo)
    head = _git_head(repo)
    rate_pin = {"model": "gpt-5.6-sol", "rate_source": "unit test fixture", "credits_per_usd": 25,
                "usd_per_input_token": 0.0, "usd_per_cached_input_token": 0.0,
                "usd_per_output_token": 0.001}
    signature = tmp_path / "sig.json"
    signature.write_text(json.dumps({
        "schema_version": 1, "frozen_commit": head, "arm": "red", "planned_model": "gpt-5.6-sol",
        "expected_config_sha256": "a" * 64, "expected_codex_mcp_list_sha256": "b" * 64,
        "credit_rate_pin": rate_pin,
    }), encoding="utf-8")
    result = run_confirm_paid_exec_signature(signature, repo, "red", "gpt-5.6-sol", "a" * 64, "b" * 64)
    assert result.returncode != 0
    assert "missing a valid expected_launcher_sha256 pin" in result.stderr


@requires_powershell
def test_confirm_signature_refuses_when_a_safety_critical_hash_mismatches(tmp_path):
    repo = tmp_path / "repo"
    hashes = _init_repo_with_safety_critical_files(repo)
    hashes["expected_credit_breaker_sha256"] = "0" * 64  # wrong on purpose
    head = _git_head(repo)
    rate_pin = {"model": "gpt-5.6-sol", "rate_source": "unit test fixture", "credits_per_usd": 25,
                "usd_per_input_token": 0.0, "usd_per_cached_input_token": 0.0,
                "usd_per_output_token": 0.001}
    signature = tmp_path / "sig.json"
    signature.write_text(json.dumps({
        "schema_version": 1, "frozen_commit": head, "arm": "red", "planned_model": "gpt-5.6-sol",
        "expected_config_sha256": "a" * 64, "expected_codex_mcp_list_sha256": "b" * 64,
        "credit_rate_pin": rate_pin, **hashes,
    }), encoding="utf-8")
    result = run_confirm_paid_exec_signature(signature, repo, "red", "gpt-5.6-sol", "a" * 64, "b" * 64)
    assert result.returncode != 0
    assert "canonical HEAD-blob hash" in result.stderr
    assert "does not match the signed expected_credit_breaker_sha256" in result.stderr


@requires_powershell
def test_confirm_signature_refuses_a_dirty_working_tree_at_the_signed_commit(tmp_path):
    # PR #122 review Finding 1's exact PoC: an UNCOMMITTED edit to a safety-critical file (e.g.
    # neutering tools/gate0_credit_breaker.py's credit ceiling) at the exact signed commit must
    # now be refused -- previously `git rev-parse HEAD` was blind to it.
    repo = tmp_path / "repo"
    hashes = _init_repo_with_safety_critical_files(repo)
    head = _git_head(repo)
    rate_pin = {"model": "gpt-5.6-sol", "rate_source": "unit test fixture", "credits_per_usd": 25,
                "usd_per_input_token": 0.0, "usd_per_cached_input_token": 0.0,
                "usd_per_output_token": 0.001}
    signature = tmp_path / "sig.json"
    signature.write_text(json.dumps({
        "schema_version": 1, "frozen_commit": head, "arm": "red", "planned_model": "gpt-5.6-sol",
        "expected_config_sha256": "a" * 64, "expected_codex_mcp_list_sha256": "b" * 64,
        "credit_rate_pin": rate_pin, **hashes,
    }), encoding="utf-8")

    # Signature is valid so far -- confirm it currently accepts, then tamper uncommitted.
    accepted = run_confirm_paid_exec_signature(signature, repo, "red", "gpt-5.6-sol", "a" * 64, "b" * 64)
    assert accepted.returncode == 0, accepted.stderr

    (repo / "tools" / "gate0_credit_breaker.py").write_text(
        "# uncommitted tamper: neuters the credit ceiling\nLIMIT_NORMALIZED_CREDITS = 250000\n",
        encoding="utf-8")
    tampered = run_confirm_paid_exec_signature(signature, repo, "red", "gpt-5.6-sol", "a" * 64, "b" * 64)
    assert tampered.returncode != 0
    assert "dirty working tree" in tampered.stderr


@requires_powershell
def test_confirm_signature_accepts_when_every_field_matches(tmp_path):
    repo = tmp_path / "repo"
    hashes = _init_repo_with_safety_critical_files(repo)
    head = _git_head(repo)
    rate_pin = {"model": "gpt-5.6-sol", "rate_source": "unit test fixture", "credits_per_usd": 25,
                "usd_per_input_token": 0.0, "usd_per_cached_input_token": 0.0,
                "usd_per_output_token": 0.001}
    signature = tmp_path / "sig.json"
    signature.write_text(json.dumps({
        "schema_version": 1, "frozen_commit": head, "arm": "red", "planned_model": "gpt-5.6-sol",
        "expected_config_sha256": "a" * 64, "expected_codex_mcp_list_sha256": "b" * 64,
        "credit_rate_pin": rate_pin, **hashes,
    }), encoding="utf-8")
    result = run_confirm_paid_exec_signature(signature, repo, "red", "gpt-5.6-sol", "a" * 64, "b" * 64)
    assert result.returncode == 0, result.stderr
    parsed = json.loads(result.stdout)
    assert parsed["frozen_commit"] == head
    assert parsed["credit_rate_pin"]["rate_source"] == "unit test fixture"


@requires_powershell
def test_get_paid_codex_exec_arguments_wraps_overrides_and_reads_the_prompt_from_stdin():
    result = run_get_paid_codex_exec_arguments(['model="gpt-5.6-sol"', 'approval_policy="never"'])
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == [
        "exec", "--json", "-c", 'model="gpt-5.6-sol"', "-c", 'approval_policy="never"', "-",
    ]


@requires_powershell
def test_breaker_supervised_exec_kills_the_child_mid_stream_on_a_synthetic_trip(tmp_path):
    # The precondition-4c shape, exercised fast: the stub emitter (zero spend, zero network) is
    # substituted for codex. The rate is pinned at the TOP of the plausibility band (PR #122 M3,
    # $10,000/million output tokens -- an extreme but not-refused price) with a correspondingly
    # large --output-tokens-per-event so the trip still lands partway through a longer stream,
    # proving the kill contract without waiting out a long real-time stream.
    rate_pin = tmp_path / "rate_pin.json"
    rate_pin.write_text(json.dumps({
        "model": "stub-model", "rate_source": "unit test fixture -- not a real price",
        "credits_per_usd": 25, "usd_per_input_token": 0.0, "usd_per_cached_input_token": 0.0,
        "usd_per_output_token": 1e-2,
    }), encoding="utf-8")
    progress = tmp_path / "progress.json"
    verdict = tmp_path / "verdict.json"
    emitter = ROOT / "tools" / "gate0_stub_codex_emitter.py"

    result = run_breaker_supervised_exec(
        child_exe=sys.executable,
        child_args=[str(emitter), "--total", "20", "--output-tokens-per-event", "100",
                    "--delay-s", "0.3", "--out-progress", str(progress)],
        accountant_exe=sys.executable,
        # -m (not a bare script path) matches exactly how tools/run_gate0_codex.ps1's -PaidExec
        # path invokes the real accountant, and needs WorkingDirectory=ROOT to resolve `tools.*`.
        accountant_args=["-m", "tools.gate0_credit_accountant", "--rate-pin", str(rate_pin),
                          "--model", "stub-model", "--verdict-out", str(verdict),
                          "--stall-timeout-s", "10"],
        working_dir=ROOT,
    )
    assert result.returncode == 0, result.stderr
    supervision = json.loads(result.stdout)
    assert supervision["ChildKilled"] is True
    assert supervision["ChildStillAliveAfterKill"] is False

    verdict_data = json.loads(verdict.read_text(encoding="utf-8"))
    assert verdict_data["result"] == "TRIPPED"

    progress_data = json.loads(progress.read_text(encoding="utf-8"))
    assert progress_data["emitted_count"] < progress_data["intended_total"], (
        "the emitter's own progress file must show an unsent tail -- proof the child was "
        "genuinely interrupted mid-stream, not merely observed after it finished on its own")


DETACHED_GRANDCHILD_POC = r'''
import subprocess
import sys
import os
import time

if len(sys.argv) > 2 and sys.argv[1] == "--grandchild":
    marker = sys.argv[2]
    with open(marker, "w") as f:
        f.write(str(os.getpid()))
        f.flush()
        os.fsync(f.fileno())
    for _ in range(200):
        time.sleep(0.1)
    sys.exit(0)

marker = sys.argv[1]
DETACHED_PROCESS = 0x00000008
CREATE_NEW_PROCESS_GROUP = 0x00000200
subprocess.Popen(
    [sys.executable, os.path.abspath(__file__), "--grandchild", marker],
    creationflags=DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP,
    close_fds=True,
)
# Give the grandchild time to start and write its PID marker before THIS process exits -- without
# this, the parent could exit (and the job could close) before the grandchild has even started,
# which would make the test's own instrumentation racy, not prove anything about the fix.
for _ in range(20):
    if os.path.exists(marker):
        break
    time.sleep(0.1)
print('{"type": "token_count", "info": {"last_token_usage": {"input_tokens": 0, "cached_input_tokens": 0, "output_tokens": 1, "reasoning_output_tokens": 0}}}')
sys.stdout.flush()
sys.exit(0)
'''


@requires_powershell
def test_breaker_supervised_exec_reaps_a_detached_grandchild_after_the_child_exits_cleanly(tmp_path):
    # PR #122 review Finding 2's exact PoC: a child that spawns a DETACHED_PROCESS/
    # CREATE_NEW_PROCESS_GROUP grandchild, emits one harmless (non-tripping) event, and exits 0.
    # Previously this left the grandchild running forever, untracked -- the kill was gated on
    # `-not $child.HasExited`, which a clean exit skips entirely. The Job Object fix must reap it
    # regardless of the child's own exit path.
    poc_script = tmp_path / "detached_grandchild_poc.py"
    poc_script.write_text(DETACHED_GRANDCHILD_POC, encoding="utf-8")
    marker = tmp_path / "grandchild_pid.txt"
    rate_pin = tmp_path / "rate_pin.json"
    rate_pin.write_text(json.dumps({
        "model": "stub-model", "rate_source": "unit test fixture -- not a real price",
        "credits_per_usd": 1, "usd_per_input_token": 0.0, "usd_per_cached_input_token": 0.0,
        "usd_per_output_token": 1e-4,  # one 1-token event is nowhere near tripping
    }), encoding="utf-8")
    verdict = tmp_path / "verdict.json"

    result = run_breaker_supervised_exec(
        child_exe=sys.executable,
        child_args=[str(poc_script), str(marker)],
        accountant_exe=sys.executable,
        accountant_args=["-m", "tools.gate0_credit_accountant", "--rate-pin", str(rate_pin),
                          "--model", "stub-model", "--verdict-out", str(verdict),
                          "--stall-timeout-s", "5"],
        working_dir=ROOT,
    )
    assert result.returncode == 0, result.stderr
    supervision = json.loads(result.stdout)
    # The IMMEDIATE child exits cleanly on its own -- the previous code's only kill signal.
    assert supervision["ChildKilled"] is False
    assert supervision["ChildExitCode"] == 0

    verdict_data = json.loads(verdict.read_text(encoding="utf-8"))
    assert verdict_data["result"] == "COMPLETED"
    assert verdict_data["trip"]["tripped"] is False

    # The decisive check: the DESCENDANT the (already-exited) child spawned must be gone too.
    assert marker.exists(), "grandchild never wrote its PID marker"
    grandchild_pid = int(marker.read_text().strip())
    result_check = subprocess.run(
        [POWERSHELL, "-NoProfile", "-NonInteractive", "-Command",
         f"[bool](Get-Process -Id {grandchild_pid} -ErrorAction SilentlyContinue)"],
        capture_output=True, text=True, check=False,
    )
    assert result_check.stdout.strip() == "False", (
        f"grandchild PID {grandchild_pid} is still alive after Invoke-BreakerSupervisedExec returned")


# --------------------------------------------------------------------------------------------
# PR #122 review Finding 4 / coordinator M4: the cross-arm combined <=250 ceiling ledger.
# --------------------------------------------------------------------------------------------

@requires_powershell
def test_combined_ledger_starts_at_zero_when_absent(tmp_path):
    result = run_combined_credit_ledger(tmp_path / "absent.json")
    assert result.returncode == 0, result.stderr
    ledger = json.loads(result.stdout)
    assert ledger["consumed_normalized_credits"] == 0
    assert ledger["limit_normalized_credits"] == 250
    assert ledger["entries"] == []


@requires_powershell
def test_combined_ledger_refuses_malformed_json(tmp_path):
    path = tmp_path / "ledger.json"
    path.write_text("not json", encoding="utf-8")
    result = run_combined_credit_ledger(path)
    assert result.returncode != 0
    assert "not valid JSON" in result.stderr


@requires_powershell
def test_confirm_combined_budget_available_refuses_when_already_exhausted(tmp_path):
    path = tmp_path / "ledger.json"
    path.write_text(json.dumps({
        "schema_version": 1, "kind": "gate0_combined_credit_ledger",
        "limit_normalized_credits": 250, "consumed_normalized_credits": 250, "entries": [],
    }), encoding="utf-8")
    result = run_combined_credit_ledger(path, confirm_budget=True, limit=250)
    assert result.returncode != 0
    assert "combined ceiling is exhausted" in result.stderr


@requires_powershell
def test_confirm_combined_budget_available_allows_when_under_limit(tmp_path):
    path = tmp_path / "ledger.json"
    path.write_text(json.dumps({
        "schema_version": 1, "kind": "gate0_combined_credit_ledger",
        "limit_normalized_credits": 250, "consumed_normalized_credits": 100, "entries": [],
    }), encoding="utf-8")
    result = run_combined_credit_ledger(path, confirm_budget=True, limit=250)
    assert result.returncode == 0, result.stderr


@requires_powershell
def test_add_ledger_entry_persists_across_a_simulated_second_arm(tmp_path):
    path = tmp_path / "ledger.json"
    # Arm R: writes the first entry from a fresh (absent) ledger.
    result_r = run_combined_credit_ledger(path, new_total=187.5, arm="red", result="TRIPPED")
    assert result_r.returncode == 0, result_r.stderr
    ledger_after_r = json.loads(path.read_text(encoding="utf-8"))
    assert ledger_after_r["consumed_normalized_credits"] == 187.5
    assert len(ledger_after_r["entries"]) == 1
    assert ledger_after_r["entries"][0]["arm"] == "red"
    assert ledger_after_r["entries"][0]["credits_before_this_arm"] == 0

    # Arm W: loads what Arm R left behind and refuses (already close to 250, plus its own spend
    # would cross it) is exercised separately above; here just confirm the carry-forward itself.
    result_w = run_combined_credit_ledger(path, new_total=240.0, arm="miniwob", result="TRIPPED")
    assert result_w.returncode == 0, result_w.stderr
    ledger_after_w = json.loads(path.read_text(encoding="utf-8"))
    assert ledger_after_w["consumed_normalized_credits"] == 240.0
    assert len(ledger_after_w["entries"]) == 2
    assert ledger_after_w["entries"][1]["arm"] == "miniwob"
    assert ledger_after_w["entries"][1]["credits_before_this_arm"] == 187.5


def test_paidexec_block_wires_the_combined_ledger():
    assert "-LedgerPath" in SCRIPT and "-ResetCombinedLedger" in SCRIPT
    assert "Confirm-CombinedCreditBudgetAvailable" in SCRIPT
    assert "'--starting-credits', $Ledger.consumed_normalized_credits" in SCRIPT
    assert "Add-Gate0CombinedCreditLedgerEntry" in SCRIPT
    assert "$Gate0CombinedCreditLimit = 250" in SCRIPT
