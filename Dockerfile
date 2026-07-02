# A Game Boy world as an MCP (stdio) server — containerized so a real MCP client (Claude Code, ai-aria)
# spawns a clean `docker run -i` instead of a host python.exe (sidesteps the Windows node-spawn quirk and
# any venv trampoline; reproducible across Win/Linux/Pi — the project's "containerize" preference).
# GAME-AGNOSTIC: the world is chosen at runtime with `--game` (registry in world_mcp.py), not baked in.
#
# ROMs are copyrighted and NOT in the image — mount roms/ read-only at runtime:
#   docker build -t gb-mcp-world .
#   docker run -i --rm -v "$PWD/roms:/app/roms:ro" -v "$PWD/runs:/app/runs" gb-mcp-world \
#          --game cave_noire --init-state runs/cn_open.state --out runs/mcp_world --record
FROM python:3.11-slim

WORKDIR /app
# Runtime for world_mcp.py: PyBoy (headless "null" window — no SDL/display) + numpy + pillow, and
# imageio(+ffmpeg) for the optional --record MP4. ffmpeg is bundled by imageio-ffmpeg (no apt install).
# py-desmume enables --game nds in the container (manylinux wheels available). mgba/--game kirby_gba
# /emerald_gba are NOT installed here (known-blocked in Docker) — GBA runs come from the WSL spike env.
# libglib2.0-0 + libsdl2: DeSmuME's native core dlopens them at emulator INIT (the pip wheel imports fine
# without them — the miss only surfaces on the first observe; confirmed live 2026-07-03).
RUN apt-get update && apt-get install -y --no-install-recommends libglib2.0-0 libsdl2-2.0-0 libgl1 \
    && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir "pyboy>=2.0" "numpy>=1.21" "pillow>=9.0" \
                               "imageio>=2.37.3" "imageio-ffmpeg>=0.6.0" "py-desmume>=0.0.9"

# All worlds' code (core/ + games/) so --game can serve any of them. roms/ and runs/ are mounted, not copied.
COPY core/ ./core/
COPY games/ ./games/
COPY world_mcp.py ./

# Headless container: no X/display — SDL must use the dummy video driver or DeSmuME's init fails.
ENV SDL_VIDEODRIVER=dummy

# world_mcp speaks JSON-RPC on stdout (it redirects fd1->stderr internally to keep the channel clean).
# Args after the image name go to world_mcp.py (--game/--init-state/--out/--record/...).
ENTRYPOINT ["python", "world_mcp.py"]
