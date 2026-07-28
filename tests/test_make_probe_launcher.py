"""Tests for tools/make_probe_launcher.py — CI-safe: only writes files given a fake ROM path (tmpdir),
no docker/emulator/network involved.
"""

import json
import os

from tools.make_probe_launcher import family_for, make_launcher, slug_for


def test_slug_for_strips_extension_and_sanitizes_spaces_punctuation():
    slug = slug_for("roms/gba/Kirby - Nightmare in Dreamland (U) [!].gba")
    assert slug and " " not in slug and not slug.lower().endswith(".gba")
    assert slug_for("roms/Cave Noire.gb") == "Cave_Noire"


def test_family_for_extensions():
    assert family_for("x.gb") == "gb"
    assert family_for("x.GBC") == "gb"
    assert family_for("x.gba") == "gba"
    assert family_for("x.nds") == "nds"


def test_family_for_rejects_unknown_extension():
    import pytest
    with pytest.raises(ValueError):
        family_for("x.zip")


def _write_fake_rom(tmp_path, name) -> str:
    roms = tmp_path / "roms"
    roms.mkdir(exist_ok=True)
    p = roms / name
    p.write_bytes(b"\x00" * 16)
    return str(p)


def test_make_launcher_gb_writes_expected_files(tmp_path):
    rom = _write_fake_rom(tmp_path, "MyGame.gb")
    out_dir = make_launcher(rom, repo_root=str(tmp_path))

    assert out_dir == str(tmp_path / "runs" / "probe_MyGame")
    for fname in (".mcp.json", "run.sh", "CLAUDE.md"):
        assert os.path.isfile(os.path.join(out_dir, fname)), fname
    assert not os.path.isfile(os.path.join(out_dir, "gba_server.sh"))

    mcp = json.load(open(os.path.join(out_dir, ".mcp.json"), encoding="utf-8"))
    server = mcp["mcpServers"]["world"]
    assert server["command"] == "docker"
    assert "gb_generic" in server["args"]
    assert "--rom" in server["args"]

    run_sh = open(os.path.join(out_dir, "run.sh"), encoding="utf-8").read()
    assert "CLAUDE_CONFIG_DIR=/home/nvidia/.claude-b" in run_sh
    assert "timeout 1200" in run_sh
    assert "> transcript.jsonl" in run_sh
    assert "--allowedTools mcp__world" in run_sh

    brief = open(os.path.join(out_dir, "CLAUDE.md"), encoding="utf-8").read()
    assert "MyGame" in brief
    assert "PROBE verdict=" in brief
    assert "~15 decision" in brief
    # brief must not hint at any game-specific mechanics
    assert "poke" not in brief.lower() and "kirby" not in brief.lower() and "cave" not in brief.lower()


def test_make_launcher_gba_writes_gba_server(tmp_path):
    rom = _write_fake_rom(tmp_path, "SomeGame.gba")
    out_dir = make_launcher(rom, repo_root=str(tmp_path))

    assert os.path.isfile(os.path.join(out_dir, "gba_server.sh"))
    mcp = json.load(open(os.path.join(out_dir, ".mcp.json"), encoding="utf-8"))
    server = mcp["mcpServers"]["world"]
    assert server["command"] == "bash"
    assert server["args"][0].endswith("gba_server.sh")

    gba_sh = open(os.path.join(out_dir, "gba_server.sh"), encoding="utf-8").read()
    # The carrier is the dedicated ROM-generic "gba_generic" key, NOT kirby_gba: routing arbitrary probe
    # ROMs through kirby_gba is what kept kirby_gba ROM-generic and therefore unable to ever hold a
    # Kirby-specific `watch` oracle. Asserted negatively too, so a revert cannot pass silently.
    assert "--game gba_generic" in gba_sh
    assert "kirby_gba" not in gba_sh
    assert "gba-spike" in gba_sh
    # repo-path interpolations must be quoted (a repo root with a space would otherwise break cd/PYTHONPATH)
    assert 'cd "' in gba_sh
    assert 'export PYTHONPATH="' in gba_sh


def test_make_launcher_nds_uses_docker_nds_game(tmp_path):
    rom = _write_fake_rom(tmp_path, "SomeDS.nds")
    out_dir = make_launcher(rom, repo_root=str(tmp_path))

    mcp = json.load(open(os.path.join(out_dir, ".mcp.json"), encoding="utf-8"))
    server = mcp["mcpServers"]["world"]
    assert server["command"] == "docker"
    assert "nds" in server["args"]
    assert not os.path.isfile(os.path.join(out_dir, "gba_server.sh"))


def test_make_launcher_custom_name_and_out(tmp_path):
    rom = _write_fake_rom(tmp_path, "x.gb")
    out_dir = str(tmp_path / "custom_out")
    make_launcher(rom, game_name="Displayed Name", out_root=out_dir, repo_root=str(tmp_path))
    brief = open(os.path.join(out_dir, "CLAUDE.md"), encoding="utf-8").read()
    assert "Displayed Name" in brief


def test_probe_brief_identical_across_games_except_name(tmp_path):
    """The probe brief template is fixed — only the game display name (and MCP server/slug name it's
    plumbed through) should differ between two different games' CLAUDE.md."""
    rom_a = _write_fake_rom(tmp_path, "GameA.gb")
    rom_b = _write_fake_rom(tmp_path, "GameB.gb")
    out_a = make_launcher(rom_a, repo_root=str(tmp_path))
    out_b = make_launcher(rom_b, repo_root=str(tmp_path))
    brief_a = open(os.path.join(out_a, "CLAUDE.md"), encoding="utf-8").read()
    brief_b = open(os.path.join(out_b, "CLAUDE.md"), encoding="utf-8").read()
    normalized_a = brief_a.replace("GameA", "X").replace("game_a", "x")
    normalized_b = brief_b.replace("GameB", "X").replace("game_b", "x")
    assert normalized_a == normalized_b


def test_slug_collision_gets_hash_suffix_not_overwrite(tmp_path):
    """Two ROMs whose sanitized names collide in the first 60 chars must NOT silently share a launcher
    dir (review finding on PR #65) — the second gets a short-hash-suffixed slug."""
    long_a = "X" * 70 + "A.gb"           # both truncate to the same 60-char slug
    long_b = "X" * 70 + "B.gb"
    rom_a = _write_fake_rom(tmp_path, long_a)
    rom_b = _write_fake_rom(tmp_path, long_b)
    assert slug_for(rom_a) == slug_for(rom_b)     # precondition: this IS a collision

    out_a = make_launcher(rom_a, repo_root=str(tmp_path))
    out_b = make_launcher(rom_b, repo_root=str(tmp_path))

    assert out_a != out_b
    assert os.path.isdir(out_a) and os.path.isdir(out_b)
    # the first launcher still points at ROM A (not clobbered by B's stamp)
    mcp_a = open(os.path.join(out_a, ".mcp.json"), encoding="utf-8").read()
    assert long_a in mcp_a and long_b not in mcp_a
    mcp_b = open(os.path.join(out_b, ".mcp.json"), encoding="utf-8").read()
    assert long_b in mcp_b
    # the suffixed slug still respects the 60-char bound
    assert len(os.path.basename(out_b)) <= len("probe_") + 60


def test_restamping_same_rom_reuses_same_dir(tmp_path):
    """Re-running the generator for the SAME ROM must update in place, not spawn a hash-suffixed twin."""
    rom = _write_fake_rom(tmp_path, "SameGame.gb")
    out_1 = make_launcher(rom, repo_root=str(tmp_path))
    out_2 = make_launcher(rom, repo_root=str(tmp_path))
    assert out_1 == out_2


def test_server_name_constant_and_allowed_tools_match(tmp_path):
    """Regression (live bug, 2026-07-03 first queue run): slug-derived MCP server names can contain
    "__" (e.g. slug "..._World__U" from "Super Mario World (U)"), and claude's --allowedTools matcher
    splits mcp__<server>__<tool> on "__" — so `--allowedTools mcp__<slug-with-__>` can NEVER match its
    own tools; all 6 probes burned ~$0.25 each on permission-denied. The server name must be a CONSTANT
    safe name with no "__" beyond the mcp__ prefix, and allowedTools must be exactly "mcp__" + server."""
    # The exact ROM naming style that triggered the live failure.
    rom = _write_fake_rom(tmp_path, "Super Mario Advance 2 - Super Mario World (U).gba")
    out_dir = make_launcher(rom, repo_root=str(tmp_path))

    mcp = json.load(open(os.path.join(out_dir, ".mcp.json"), encoding="utf-8"))
    (server_name,) = mcp["mcpServers"].keys()
    assert "__" not in server_name
    assert server_name == "world"

    run_sh = open(os.path.join(out_dir, "run.sh"), encoding="utf-8").read()
    allowed = [tok for line in run_sh.splitlines() if "--allowedTools" in line
               for tok in line.split() if tok.startswith("mcp__")]
    assert allowed == [f"mcp__{server_name}"]
    assert "__" not in allowed[0][len("mcp__"):]

    # the brief's server-name mention must reference the same constant name
    brief = open(os.path.join(out_dir, "CLAUDE.md"), encoding="utf-8").read()
    assert f"MCP server `{server_name}`" in brief
