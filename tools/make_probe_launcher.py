#!/usr/bin/env python
"""tools/make_probe_launcher.py — stamp out a paid-probe launcher dir (runs/probe_<slug>/) for one ROM.

Emits the account-B `claude -p` launcher trio for a single ROM, in the same shape as the hand-built
runs/brain_*/ launchers on disk (gitignored): .mcp.json (world server wiring), run.sh (account-B pattern:
CLAUDE_CONFIG_DIR=/home/nvidia/.claude-b, pre-trust python block, timeout, stream-json transcript), and
CLAUDE.md (the FIXED probe brief — identical across games except the game name/tool prefix).

Family dispatch by ROM extension (mirrors world_mcp.py's own --rom/--game validation):
  .gb/.gbc -> Docker gb-mcp-world, --game gb_generic --rom <rom>
  .gba     -> WSL gba-spike env via a generated gba_server.sh (mirrors runs/brain_emerald/gba_server.sh),
              --game kirby_gba --rom <rom> (any registered GBA world key works as a generic carrier via
              --rom override -- its plugin/perceiver are already game-agnostic; see _GBA_CARRIER_GAME)
  .nds     -> Docker gb-mcp-world (same image serves NDS), --game nds --rom <rom>

The probe brief is NEVER game-specific: no hints about controls, mechanics, or what to expect on screen
(the point is to see what the brain figures out cold). Only the game display name changes.

CI-safe: this module only writes files (no ROM/docker/network needed to test it).
"""
from __future__ import annotations

import argparse
import hashlib
import os
import stat

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

CLAUDE_CONFIG_DIR = "/home/nvidia/.claude-b"
TIMEOUT_SECONDS = 1200

# The MCP server name in every generated .mcp.json — a CONSTANT, deliberately NOT the slug. claude's
# --allowedTools matcher splits mcp__<server>__<tool> on "__", so a server name containing "__" (easy to
# produce from sanitized ROM names like "..._World__U") can NEVER match its own tools: the whole first
# paid queue run burned ~$0.25/probe on permission-denied because of this. One server per launcher dir
# means uniqueness buys nothing; a fixed safe name buys correctness.
SERVER_NAME = "world"

# The FIXED probe brief template. {game_name} is the only substitution — everything else (task wording,
# decision cap, closing verdict format) is identical across every game so results are comparable.
PROBE_BRIEF_TEMPLATE = """\
# You are the brain for {game_name}

You play this game **only through the MCP tools below**. There is no time pressure: the game waits.

**What this is:** a cold probe — you have no prior knowledge of this game, its controls beyond what's
listed below, or what to expect on screen. That's intended.

## Tools (MCP server `{server_name}`)
- **`observe`** — look now: a symbolic view of what's on screen. Call it first, and after every action.
- **`press_button {{button}}`** — press one button (see the tool's allowed values).
- **`press_sequence {{buttons}}`** — several presses in order.
- **`wait {{frames}}`** — let an animation or transition finish without acting.
- **`goto {{x, y}}`** / **`explore {{max_steps?}}`** — free System-1 autopilot (pathfind / auto-explore),
  where available.
- **`remember {{lesson}}`** — record a short lesson; it is shown back to you every turn.

## YOUR TASK

Reach free/interactive play from boot and explore; describe what you can see and do; note anything the
perception seam fails to show you.

**Cap yourself at ~15 decisions (tool calls) total.** Spend them getting past any boot/title/menu screens
into actual interactive play, then explore a little.

End with a structured self-report line in this EXACT format:
```
PROBE verdict=<free_movement|stuck_title|stuck_dialog|other> gaps=<comma-list>
```
- `verdict`: `free_movement` if you reached real interactive control; `stuck_title` if you never got past
  a title/boot screen; `stuck_dialog` if you got stuck in a menu/dialog loop; `other` for anything else
  (describe it in `gaps`).
- `gaps`: a comma-separated list of concrete perception gaps you hit (what you needed to know and
  couldn't see) — empty (`gaps=none`) if there were none.
"""


def slug_for(rom_path: str) -> str:
    """Filesystem-safe slug from a ROM's basename (no extension)."""
    name = os.path.splitext(os.path.basename(rom_path))[0]
    return "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in name).strip("_")[:60] or "rom"


def family_for(rom_path: str) -> str:
    """Console family for a ROM path: gb (.gb/.gbc), gba (.gba), or nds (.nds)."""
    ext = os.path.splitext(rom_path)[1].lower()
    if ext in (".gb", ".gbc"):
        return "gb"
    if ext == ".gba":
        return "gba"
    if ext == ".nds":
        return "nds"
    raise ValueError(f"unrecognized ROM extension for {rom_path!r} (need .gb/.gbc/.gba/.nds)")


def _wsl_path(host_repo_root: str) -> str:
    """Best-effort /mnt/<drive>/... form of an absolute Windows repo root, for embedding in WSL scripts.
    A repo root already given in /mnt/... form (i.e. running this from WSL) passes through unchanged."""
    p = host_repo_root.replace("\\", "/")
    if p.lower().startswith("/mnt/"):
        return p
    if len(p) >= 2 and p[1] == ":":
        drive = p[0].lower()
        return f"/mnt/{drive}{p[2:]}"
    return p


def _mcp_config(slug: str, family: str, rom_path: str, repo_wsl: str, repo_root: str) -> dict:
    launch_wsl = f"{repo_wsl}/runs/probe_{slug}"
    if family == "gba":
        return {"mcpServers": {SERVER_NAME: {"command": "bash", "args": [f"{launch_wsl}/gba_server.sh"]}}}
    game = "nds" if family == "nds" else "gb_generic"
    roms_root = os.path.join(repo_root, "roms")
    try:
        rel_rom = os.path.relpath(rom_path, roms_root).replace(os.sep, "/")
    except ValueError:                      # Windows: different drive letters can't be made relative
        rel_rom = ".."
    if rel_rom.startswith(".."):
        raise ValueError(f"ROM {rom_path!r} must live under {roms_root!r} — the Docker world server "
                         "only mounts <repo>/roms into the container (see every existing runs/brain_*/"
                         ".mcp.json launcher); copy/symlink the ROM there first.")
    return {"mcpServers": {SERVER_NAME: {
        "command": "docker",
        "args": ["run", "-i", "--rm",
                 "-v", f"{repo_wsl}/roms:/app/roms:ro",
                 "-v", f"{repo_wsl}/runs:/app/runs",
                 "gb-mcp-world", "--game", game,
                 "--rom", f"roms/{rel_rom}",
                 "--out", f"runs/probe_{slug}/world", "--keep-frames"],
    }}}


# Any already-registered GBA world key works as a generic-GBA carrier via --rom override: kirby_gba's
# pkg/plugin/perceiver (core.perception_plugin.PerceptionPlugin + core.grid_perceiver.FollowCameraPerceiver)
# is already game-agnostic — the registry entry only pins a default ROM, which --rom replaces. No new
# "gba_generic" registry key is needed (gb_generic is GB-family only; a GBA ROM must use a GBA-family key
# so world_mcp.py's --rom/--game family check, ext == fam, agrees).
_GBA_CARRIER_GAME = "kirby_gba"


def _gba_server_sh(slug: str, rom_path: str, repo_wsl: str, repo_root: str) -> str:
    try:
        rel_rom = os.path.relpath(rom_path, repo_root).replace(os.sep, "/")
    except ValueError:                      # Windows: different drive letters can't be made relative
        rel_rom = ".."
    if rel_rom.startswith(".."):
        raise ValueError(f"ROM {rom_path!r} must live under the repo ({repo_root!r}) so the WSL "
                         "gba-spike script can find it via a repo-relative path.")
    return f"""#!/bin/bash
# MCP world server for {slug} (GBA) — runs world_mcp.py directly in WSL using the ~/gba-spike mgba build
# (mgba is not pip-installable; the Docker image is GB/NDS-only). Mirrors runs/brain_emerald/gba_server.sh.
export LD_LIBRARY_PATH=/home/nvidia/gba-spike
export PYTHONPATH="/home/nvidia/gba-spike/mgba-build/python/lib.linux-x86_64-3.8:{repo_wsl}"
cd "{repo_wsl}" || exit 3
exec /home/nvidia/gba-spike/py311/python/bin/python3.11 world_mcp.py --game {_GBA_CARRIER_GAME} --rom "{rel_rom}" \\
  --out runs/probe_{slug}/world --keep-frames
"""


def _run_sh(slug: str, repo_wsl: str) -> str:
    launch_wsl = f"{repo_wsl}/runs/probe_{slug}"
    server = f"mcp__{SERVER_NAME}"
    return f"""#!/bin/bash
# Paid probe run on account B (separate CLAUDE_CONFIG_DIR); drive claude -p through the {slug} MCP seam.
# Generated by tools/make_probe_launcher.py — edit the generator, not this file, to change the pattern.
export CLAUDE_CONFIG_DIR={CLAUDE_CONFIG_DIR}
LAUNCH={launch_wsl}

# Fresh config B treats the workspace as untrusted -> project settings get ignored. Pre-trust it
# (non-fatal: --mcp-config below loads the world server explicitly regardless).
python3 - <<'PY' 2>/dev/null || true
import json, os
cfg = os.path.expanduser("~/.claude-b/.claude.json")
try:
    d = json.load(open(cfg))
except Exception:
    d = {{}}
base = "{os.path.dirname(repo_wsl)}"
paths = [base, "{repo_wsl}", "{launch_wsl}"]
projects = d.setdefault("projects", {{}})
for p in paths:
    e = projects.setdefault(p, {{}})
    e["hasTrustDialogAccepted"] = True
    e["hasCompletedProjectOnboarding"] = True
json.dump(d, open(cfg, "w"), indent=2)
PY

cd "$LAUNCH" || exit 3
rm -rf world
timeout {TIMEOUT_SECONDS} /home/nvidia/.local/bin/claude -p "Begin YOUR TASK now, per CLAUDE.md." \\
  --mcp-config .mcp.json --allowedTools {server} --output-format stream-json --verbose \\
  < /dev/null > transcript.jsonl 2> run.err
echo "EXIT=$?" > run.exit
"""


def make_launcher(rom_path: str, game_name: str | None = None, out_root: str | None = None,
                   repo_root: str | None = None) -> str:
    """Write runs/probe_<slug>/{.mcp.json, run.sh, CLAUDE.md[, gba_server.sh]} for `rom_path`. Returns the
    launcher dir. `repo_root` (defaults to this file's repo) lets tests point at a tmpdir fixture repo."""
    repo_root = repo_root or _REPO
    rom_path = os.path.abspath(rom_path)
    family = family_for(rom_path)
    slug = slug_for(rom_path)
    game_name = game_name or os.path.splitext(os.path.basename(rom_path))[0]
    if out_root is None:
        # Slug-collision guard (review finding on PR #65): two ROMs whose sanitized names collide in the
        # first 60 chars (e.g. near-duplicate regional dumps) must not silently overwrite each other's
        # launcher. A .rom marker in the dir records which ROM it was stamped for; a DIFFERENT rom path
        # on an existing dir gets a short-hash-suffixed slug instead. Re-stamping the SAME rom is fine.
        candidate = os.path.join(repo_root, "runs", f"probe_{slug}")
        marker = os.path.join(candidate, ".rom")
        if os.path.isdir(candidate) and os.path.isfile(marker):
            with open(marker, encoding="utf-8") as f:
                if f.read().strip() != rom_path:
                    slug = f"{slug[:51]}_{hashlib.md5(rom_path.encode('utf-8')).hexdigest()[:8]}"
        out_root = os.path.join(repo_root, "runs", f"probe_{slug}")
    os.makedirs(out_root, exist_ok=True)
    with open(os.path.join(out_root, ".rom"), "w", encoding="utf-8", newline="\n") as f:
        f.write(rom_path + "\n")

    repo_wsl = _wsl_path(repo_root)

    import json
    with open(os.path.join(out_root, ".mcp.json"), "w", encoding="utf-8", newline="\n") as f:
        json.dump(_mcp_config(slug, family, rom_path, repo_wsl, repo_root), f, indent=2)
        f.write("\n")

    if family == "gba":
        gba_path = os.path.join(out_root, "gba_server.sh")
        with open(gba_path, "w", encoding="utf-8", newline="\n") as f:
            f.write(_gba_server_sh(slug, rom_path, repo_wsl, repo_root))
        os.chmod(gba_path, os.stat(gba_path).st_mode | stat.S_IEXEC)

    run_path = os.path.join(out_root, "run.sh")
    with open(run_path, "w", encoding="utf-8", newline="\n") as f:
        f.write(_run_sh(slug, repo_wsl))
    os.chmod(run_path, os.stat(run_path).st_mode | stat.S_IEXEC)

    with open(os.path.join(out_root, "CLAUDE.md"), "w", encoding="utf-8", newline="\n") as f:
        f.write(PROBE_BRIEF_TEMPLATE.format(game_name=game_name, server_name=SERVER_NAME))

    return out_root


def main() -> int:
    ap = argparse.ArgumentParser(description="Stamp out a paid-probe launcher dir for one ROM.")
    ap.add_argument("--rom", required=True, help="ROM path (.gb/.gbc/.gba/.nds)")
    ap.add_argument("--name", default=None, help="display name for CLAUDE.md (default: ROM basename)")
    ap.add_argument("--out", default=None, help="launcher dir (default: runs/probe_<slug>)")
    args = ap.parse_args()
    out_dir = make_launcher(args.rom, game_name=args.name, out_root=args.out)
    print(f"wrote {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
