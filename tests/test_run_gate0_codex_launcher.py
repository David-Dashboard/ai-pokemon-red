from pathlib import Path

from tools.check_gate0_codex import SERVER, TOOLS


SCRIPT = (Path(__file__).parents[1] / "tools" / "run_gate0_codex.ps1").read_text(encoding="utf-8")


def test_launcher_has_required_inputs_and_empty_output_guard():
    assert "[ValidateSet('red', 'miniwob')]" in SCRIPT
    assert SCRIPT.count("[Parameter(Mandatory = $true)]") == 3
    assert "[string]$Model" in SCRIPT and "[string]$OutputDir" in SCRIPT
    assert "Get-ChildItem -LiteralPath $OutputDir -Force" in SCRIPT
    assert "OutputDir must not exist or must be empty" in SCRIPT


def test_launcher_proves_version_and_chatgpt_before_exec():
    version = SCRIPT.index("$codex.Source --version")
    login = SCRIPT.index("$codex.Source login status")
    execute = SCRIPT.index("$codex.Source exec")
    assert version < login < execute
    assert "$env:OPENAI_API_KEY -or $env:CODEX_API_KEY" in SCRIPT
    assert "OPENAI_API_KEY or CODEX_API_KEY is set" in SCRIPT
    assert "did not prove ChatGPT subscription authentication" in SCRIPT
    assert "latest alias" in SCRIPT


def test_launcher_uses_hermetic_codex_exec_flags_and_no_auth_copy():
    for flag in ("--json", "--ephemeral", "--ignore-user-config", "--ignore-rules",
                 "--sandbox read-only", "--model $Model"):
        assert flag in SCRIPT
    assert "CODEX_HOME" in SCRIPT  # explanatory comment only
    for forbidden in ("Copy-Item", "auth.json", "OPENAI_API_KEY |", "--with-api-key"):
        assert forbidden not in SCRIPT
    assert "1>> $TranscriptPath" in SCRIPT
    assert "2>> $StderrPath" in SCRIPT
    assert "codex.stderr.log" in SCRIPT


def test_generated_config_has_one_mcp_and_disables_nonworld_surfaces():
    assert SCRIPT.count("[mcp_servers.$Server]") == 1
    assert "$Server = 'gate0_world'" in SCRIPT
    assert 'web_search = "disabled"' in SCRIPT
    assert "shell_tool = false" in SCRIPT
    assert "skill_mcp_dependency_install = false" in SCRIPT
    for feature in ("apps", "goals", "hooks", "memories", "multi_agent"):
        assert f"{feature} = false" in SCRIPT
    assert "[apps._default]" in SCRIPT and "enabled = false" in SCRIPT
    assert 'sandbox_mode = "read-only"' in SCRIPT
    assert "--network', 'none'" in SCRIPT


def test_arm_tool_inventories_match_checker_and_worlds_are_pinned():
    assert SERVER == "gate0_world"
    for tool in TOOLS["red"] + TOOLS["miniwob"]:
        assert f"'{tool}'" in SCRIPT
    assert "gb-mcp-world" in SCRIPT and "runs\\red_start.state" in SCRIPT
    assert "miniwob-world" in SCRIPT
    assert "miniwob-mcp-world" not in SCRIPT
    assert "gate0_miniwob_paid_seeds.json" in SCRIPT
    assert "--seeds-file" in SCRIPT


def test_task_briefs_are_unbridged_and_launch_dir_is_fresh_git_repo():
    assert "From the fresh bedroom start, obtain your first Pokemon from Professor Oak and win the first rival battle." in SCRIPT
    assert "Complete five fresh episodes of the browser click-checkboxes task" in SCRIPT
    for forbidden_hint in ("balls are east", "right + a", "hardcoded submit", "click at ("):
        assert forbidden_hint not in SCRIPT.casefold()
    assert "git init --quiet $LaunchDir" in SCRIPT
    assert "Join-Path $LaunchDir 'TASK.md'" in SCRIPT
    assert "Join-Path $LaunchDir '.codex'" in SCRIPT
    assert SCRIPT.count("$CommonTask = @'") == 1
    assert '$Task = $TaskSentence + "`n" + $CommonTask.Trim() + "`n"' in SCRIPT


def test_constancy_hashes_common_brain_separately_from_arm_config():
    assert '$BrainConfigText = $BrainConfig.Trim() + "`n"' in SCRIPT
    assert '$ConfigText = $BrainConfigText + "`n" + $WorldConfig.Trim() + "`n"' in SCRIPT
    assert "brain_config_sha256 = Get-BytesSha256" in SCRIPT
    assert "task_sha256 = Get-FileSha256 $TaskPath" in SCRIPT
    assert "config_sha256 = Get-FileSha256 $ConfigPath" in SCRIPT


def test_sanitized_receipt_matches_checker_schema():
    for field in ("schema_version", "arm", "auth_method", "model", "codex_version",
                  "codex_path", "codex_executable_sha256", "mcp_servers", "mcp_tools",
                  "brain_config_sha256", "task_sha256", "config_sha256",
                  "tool_schema_sha256"):
        assert f"{field} =" in SCRIPT
    assert "auth_method = 'chatgpt'" in SCRIPT
    assert "codex_path = $codex.Source" in SCRIPT
    assert "codex_executable_sha256 = Get-FileSha256 $codex.Source" in SCRIPT
