---
name: new-world-port
description: Add a new game/console world (GB, GBA, NDS, other) to the harness and run a first constancy audit — registry entry, launcher, savestate, probes, scoring.
---

# Porting a new world into the harness

## The constancy law (non-negotiable)
The BRAIN is never edited per game. A new console/game changes only the world side of the
perception seam: one `Emulator` Protocol implementation, a registry entry, maybe a perceiver
recalibration. `core/contracts.py`, the gateway, the brain prompt/tools stay untouched
(see `reports/nds-emulation-plan.md` §0 and §6). The seam is the `Emulator` Protocol in
`core/gb_emulator.py`: `press(button, hold, settle) · tick(frames) · read(addr) ·
screen_ndarray() -> (H,W,C) uint8 · save_screen · save_state · load_state · frame · close`.
Adding a console = implement those ~9 methods (`core/gba_emulator.py`, `core/nds_emulator.py`
are the existing ports). Perception (`core/grid_perceiver.py`) consumes `screen_ndarray()` and
must not know which emulator produced the frame.

## Cheap-first ladder (spend nothing before it's earned)
1. **Binding spike (free, throwaway):** prove the emulator binding gives all four capabilities
   against a real ROM — framebuffer, RAM read, savestate roundtrip, input — before writing any
   port code (mandated by `reports/nds-emulation-plan.md` §1; both GBA and NDS did this).
2. **Zero-model smoke (free):** `uv run python play_generic.py --rom <rom> --steps 150`
   (headless; `--window` for SDL; works on GB/GBC/GBA per README).
3. **Free inline JSON-RPC probe of the MCP server** (no LLM): pipe
   `initialize` → `notifications/initialized` → `tools/call observe` JSON lines straight into
   the server process (`printf '%s\n' '{"jsonrpc":"2.0","id":1,"method":"initialize",...}' ... |
   docker run -i --rm ... gb-mcp-world --game <g> --init-state ...` — pattern in
   `reports/2026-06-26-mcp-claude-p-runbook.md`). Debug the world here, never in a paid run.
4. **Offline frame probes:** after any run, re-run perceiver code on `world/frame_*.png` +
   `world/oracle.jsonl` before hypothesizing perceiver bugs in a new paid run.
5. Only then: the paid `claude -p` constancy audit.

## Register the game
The registry is the `GAMES` dict in `world_mcp.py` (~line 118). Two patterns:
- **Lean world (start here, no new code):** shared plugin, generic perceiver, empty oracle —
  copy the `kirby_dreamland` / `gb_generic` / `emerald_gba` shape:
  `{"pkg": "core.perception_plugin", "plugin": "PerceptionPlugin",
    "perceiver_mod": "core.grid_perceiver", "perceiver": "FollowCameraPerceiver",
    "rom": "roms/<...>", "watch": {}}`
  GBA keys also need adding to `_GBA_WORLDS`; generic-GB keys to `_GB_GENERIC_WORLDS`; NDS
  worlds use the existing `"nds"` key with `--rom` override (no new entry needed).
- **Full plugin (later, only if earned):** a `games/<game>/` package with plugin + perceiver +
  sandbox, like `games/cave_noire/` or `games/pokemon_red/`.
`watch` = RAM addresses for the SCORING oracle, written to `world/oracle.jsonl`, never on the
wire to the brain. `watch: {}` is fine for a first port — score qualitatively (below).

## Per-console launcher patterns (all live under `runs/<name>/{.mcp.json,CLAUDE.md,run.sh}`)
Copy the nearest existing launcher; they are the verified templates:
- **GB/GBC — Docker.** `runs/brain_red_starter/`. `.mcp.json` runs
  `docker run -i --rm -v /mnt/e/.../roms:/app/roms:ro -v /mnt/e/.../runs:/app/runs
  gb-mcp-world --game <key> --init-state runs/<x>.state --out runs/<name>/world --record --keep-frames`.
  Build/rebuild: `docker build -t gb-mcp-world .` — REBUILD after ANY code change (the image
  COPYs `core/ games/ world_mcp.py`; a stale image silently runs old code).
- **GBA — NO Docker** (mgba is unbuildable in the container: no PyPI package exists, the source
  build needs a hand-patched EReader stub — `reports/2026-06-29-gba-mgba-recipe.md`).
  `runs/brain_emerald/` instead launches `gba_server.sh` from `.mcp.json`, which sets
  `LD_LIBRARY_PATH=/home/nvidia/gba-spike` and
  `PYTHONPATH=/home/nvidia/gba-spike/mgba-build/python/lib.linux-x86_64-3.8:<repo /mnt/e path>`
  then execs `/home/nvidia/gba-spike/py311/python/bin/python3.11 world_mcp.py --game emerald_gba
  --out runs/brain_emerald/world --keep-frames`. mgba logs BIOS/DMA noise to stdout at boot —
  normal; world_mcp redirects fd1 so the JSON-RPC channel stays clean.
- **NDS — Docker, py-desmume.** `runs/brain_kirby_nds/`: same `gb-mcp-world` image,
  `--game nds --rom "roms/nds/<game>.nds" --keep-frames`. The image already installs
  `py-desmume>=0.0.9` + `libglib2.0-0 libsdl2-2.0-0 libgl1` and sets `SDL_VIDEODRIVER=dummy`
  (DeSmuME dlopens these at emulator INIT, not import — the miss only surfaces on first observe).
  Gotcha: DSi-enhanced ROMs (e.g. Pokémon White) render BLANK — use a plain-DS ROM.
- **New console:** spike the binding (step 1 above), implement the Protocol mirroring
  `core/nds_emulator.py`, prefer the Docker container if the binding pip-installs on
  `python:3.11-slim`; fall back to a WSL env script (the GBA pattern) if it doesn't.
The `claude -p` side is identical across consoles (see `runs/brain_emerald/run.sh`):
`CLAUDE_CONFIG_DIR=/home/nvidia/.claude-b`, pre-trust the workspace in `~/.claude-b/.claude.json`,
`timeout 1500 claude -p "<task>" --mcp-config .mcp.json --allowedTools mcp__<server-key>
--output-format stream-json --verbose < /dev/null > transcript.jsonl`. `--verbose` is REQUIRED
with `stream-json`. Docker paths from WSL are `/mnt/e/...`, never `E:/...`.

## Savestate / init-state discipline
- Boot the agent at GAMEPLAY, never the title screen: `--init-state runs/<x>.state`.
- Making states: `play_<game>.py` and `human_play.py` only exist for already-ported GB games
  (`human_play.py` is hard-coded to PyBoy/`.gb`); the generic `play_generic.py`/`play_nds.py` have
  no `--save-state`/`--brain` flags. For a NEW world with no `play_<game>.py`, write a ~10-line
  throwaway script that constructs the family's `Emulator`, ticks/presses past the title, then calls
  `emulator.save_state(path)` (the Protocol method) — the way `runs/nds3d_probe/mkds_race_start.state`
  was made. (Pokémon Red only: `make_state.py`, NOT `new_game.py`, whose control-detection is fragile.)
- Verify the state before paying (e.g. Red: RAM `0xD163 == 0` party count at the bedroom start).
- Savestates are gitignored (copyrighted memory) — keep them local; ROMs mount read-only.

## Recording
- GB: `--record` (MP4) + `--keep-frames` (per-step PNGs) both work.
- GBA/NDS: `--record` FAILS LOUD by design (recording only threads through the default PyBoy
  path). Use `--keep-frames` only — the PNGs are your visual record.

## Oracle predicate gotchas (per console)
- Define success at a STABLE boundary: Red's party counter flips only after the received-dialog
  fully closes — a run stopped mid-textbox scores 0 even though it succeeded.
- GB HUD values are often BCD: Cave Noire hp is BCD at `0xC120` (an earlier probe's `0xD389`
  was wrong). Kirby's Dream Land hp at `0xD086` is a PLAIN int 0-5. When oracle-hunting, test
  both decodings against the HUD across a damage event before trusting an address.
- No RAM map yet? Ship `watch: {}` and score qualitatively.

## First run = constancy probe, not a completion run
Task the brain with something modest: "boot to free-roam and explore", ~35-40 decisions, then a
closing report (free-roam reached? perception gaps? tool behavior?) — exactly the
`runs/brain_emerald` and `runs/brain_kirby_nds` prompts. Do NOT ask for game completion.
Score it:
- `transcript.jsonl`: `tool_result` blocks = what the brain saw; final `result` event has
  `num_turns` / `total_cost_usd` / `is_error`.
- `world/oracle.jsonl` if `watch` has entries; otherwise judge qualitatively from the
  transcript + `world/frame_*.png` (did it reach free movement? did perception track motion?).
- Score offline with the repo venv: `UV_PROJECT_ENVIRONMENT=.venv-win UV_NATIVE_TLS=true
  uv run --frozen python ...` (Windows `python3` hits the MS-Store alias).
The question the run answers is: did the UNCHANGED brain make progress through the new world's
seam? Any fix goes on the world side. One git worktree per implementer agent if you parallelize.

## Sources
- `C:/Users/Succe/.claude/projects/E--AI-Personas-10-pokemon-and-chess-and-office/memory/cross-console-run-launchers.md`
- `C:/Users/Succe/.claude/projects/E--AI-Personas-10-pokemon-and-chess-and-office/memory/mcp-claude-p-harness.md`
- `world_mcp.py` (GAMES registry, flags, `--record` guards)
- `runs/brain_red_starter/`, `runs/brain_emerald/` (+ `gba_server.sh`), `runs/brain_kirby_nds/` (run.sh + .mcp.json)
- `Dockerfile` · `README.md` · `reports/2026-06-26-mcp-claude-p-runbook.md`
- `reports/2026-06-29-gba-mgba-recipe.md` · `reports/nds-emulation-plan.md`
- `reports/north-eye-perception-constitution.md` (cheap-first Realizer Ladder)
