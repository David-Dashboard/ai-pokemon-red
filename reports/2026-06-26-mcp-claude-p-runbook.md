# RUNBOOK — live System-2 (`claude -p`) over MCP test

How to drive a **real Claude reasoning brain** through `world_mcp.py` to play a game live, score it, and
record it. This is the harness behind `reports/2026-06-25-model-comparison-mcp.md`. Written so a memory-wiped
agent can set up a run **without trial-and-error**. Everything here was validated 2026-06-26.

## Why it's wired this way (the env split)
- The **brain** is a headless `claude -p` instance — it runs in **WSL** (`/home/nvidia/.local/bin/claude`,
  Ubuntu-20.04), on David's **subscription** (free, not API tokens). It is NOT on the Windows PATH.
- The **world** is `world_mcp.py` (an MCP stdio server) which needs the **Windows** PyBoy env (`.venv-win`).
- WSL-claude can't spawn a Windows python path → the bridge is **Docker** (`gb-mcp-world`), which runs the
  same on both sides. The brain (MCP client) ⇄ docker container (MCP server) over stdio JSON-RPC.

```
wsl claude -p  ──MCP/stdio──▶  docker gb-mcp-world (world_mcp.py)  ──▶  PyBoy game
   (System 2)                   (System 1: perceiver + free autopilot)        │
   sees only the symbolic view (observe/explore/goto/press)        RAM ─▶ oracle.jsonl (scoring only)
```

## One-time setup
```bash
# Rebuild the image AFTER ANY change to core/, games/, or world_mcp.py (the Dockerfile COPYs them in):
cd /e/AI_Personas/10_pokemon_and_chess_and_office/ai-pokemon-red
docker build -t gb-mcp-world .
```
The image already bundles `imageio`+`imageio-ffmpeg` (for `--record` MP4) and PyBoy/numpy/pillow.

## Run an experiment (the recipe)
Each experiment is a **launcher dir** (e.g. `runs/brain_<tag>/`) holding three files, then one WSL command.

**1. `runs/brain_<tag>/.mcp.json`** — the dockerized MCP server (mounts use `/mnt/e/...` because it runs
from WSL; add `--record` for the MP4):
```json
{ "mcpServers": { "<server-name>": {
  "command": "docker",
  "args": ["run","-i","--rm",
    "-v","/mnt/e/AI_Personas/10_pokemon_and_chess_and_office/ai-pokemon-red/roms:/app/roms:ro",
    "-v","/mnt/e/AI_Personas/10_pokemon_and_chess_and_office/ai-pokemon-red/runs:/app/runs",
    "gb-mcp-world","--game","<game>","--init-state","runs/<state>.state",
    "--out","runs/brain_<tag>/world","--record","--keep-frames"] } } }
```
**2. `runs/brain_<tag>/.claude/settings.local.json`** — enable the server:
```json
{ "enabledMcpjsonServers": ["<server-name>"] }
```
**3. `runs/brain_<tag>/CLAUDE.md`** — the brief (auto-loaded). Use the fixed comparison task (observe →
explore/goto/press → STOP at decisions=20 → report cells/decision). Copy from `runs/brain_cn/CLAUDE.md`.

**4. Launch (background; ~5 min, free):**
```bash
wsl.exe -e bash -lc 'cd /mnt/e/AI_Personas/10_pokemon_and_chess_and_office/ai-pokemon-red/runs/brain_<tag> \
  && rm -rf world \
  && timeout 600 claude -p "Begin the COMPARISON TASK now per CLAUDE.md. Call observe first, then \
       explore/goto/press to cover NEW ground, and STOP at decisions = 20." \
     --allowedTools mcp__<server-name> --output-format stream-json --verbose \
     > transcript.jsonl 2> run.err; echo "EXIT=$?" > run.exit'
```

## GOTCHAS (the trial-and-error, encoded)
- **`--output-format stream-json` REQUIRES `--verbose`** — without it claude exits 1 instantly, no run.
- **`claude` is WSL-only** — call it via `wsl.exe -e bash -lc '...'`. `which claude` on Windows finds nothing.
- **Docker mounts from WSL use `/mnt/e/...`**, not `E:/...`. (From *Windows* Git Bash, prefix the docker
  command with `MSYS_NO_PATHCONV=1` or it mangles the `:/app/...` paths.)
- **`--allowedTools mcp__<server-name>`** confines the brain to the 7 game tools (no Bash/Write). The
  `<server-name>` is the key in `.mcp.json`. The first brain turn may call `ToolSearch` to load the MCP tools.
- **Rebuild the image after any code change** — the container has a *copy*; stale image = stale perceiver.
- **Save-state required** — boot at gameplay, not the title. `cn_open.state` (Cave Noire). Make others with
  `play_<game>.py --brain scripted --steps 250 --save-state runs/<x>.state`.
- Quick non-brain smoke (verify the server serves a game) — pipe JSON-RPC straight into the container:
  `printf '%s\n' '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{...}}' '{...tools/call observe...}' | docker run -i --rm -v ... gb-mcp-world --game <g> --init-state ...`

## Outputs & scoring (per run, in `runs/brain_<tag>/`)
- **`transcript.jsonl`** — full brain trajectory (stream-json): `tool_use` blocks (its decisions),
  `tool_result` blocks (the symbolic views it saw incl. the `Cost so far: N decision(s) … X per decision`
  tally), and the final `result` event (`num_turns`, `total_cost_usd` = *estimated* API cost; free on sub).
- **`world/oracle.jsonl`** — RAM truth per step (`watch` x/y/…), **scoring only, never on the wire**.
  Distinct `(x,y)` = ground-truth tiles covered. (Cave Noire dead-reckon baseline ≈ 7 before livelock.)
- **`world/session.mp4`** — recorded emulator video **with audio** (`--record`; `aac` muxed on close).
  `world_mcp` finalizes the mux on SIGTERM/SIGINT too (claude terminates the container rather than closing
  stdin), so the MP4 is no longer lost on teardown.
- **`world/frame_NNNNNN.png`** — per-step stills (`--keep-frames`; default DROPS them as debris). Each pairs
  with its `oracle.jsonl` step (RAM) and the symbolic view the brain saw — the aligned per-decision record.
- **`run.err`** — stderr (PyBoy/docker noise + any claude error). **`run.exit`** — exit code.

Note: the brain never gets pixels (`--with-screenshot` is OFF by design — symbolic-only is the perception
seam). The MP4 is **our** visual log, not the brain's input.

## Registry & states (current)
`world_mcp.py` `GAMES`: `cave_noire` (localizer), `cave_noire_baseline` (A/B dead-reckon control),
`gauntlet` (follow-cam), `pokemon_red` (overworld; It1's "get your first Pokémon" task — see
`runs/brain_red_starter/`). States: `cn_open.state`, `gauntlet_play.state`, `red_start.state`
(`python new_game.py --rom roms/PokemonRed.gb --out runs/red_start.state`). Watch addrs live in the
GAMES entry.

## Pokemon notes
`pokemon_red` is now a lean `PerceptionPlugin` world like the others (the heavy pre-seam `GamePlugin`
was archived to `games/pokemon_red/_archive/`). One difference from cave_noire/gauntlet: it's the only
game with its own `emulator.py` (a fade-detecting PyBoy wrapper) — but `world_mcp.World` builds the
plugin via `rom_path=` only, so it gets the GENERIC `core.gb_emulator.PyBoyEmulator`, not Red's own. The
perceiver's own scene-cut detection still catches warps (incl. non-fading stairs) without the fade flag;
a fading door-warp right after a mis-classified menu frame is the one edge case that loses its extra
robustness aid under the seam (known, accepted for It1 — see the perceiver's `_AREA_THRESHOLD` notes).
