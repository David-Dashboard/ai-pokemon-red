---
name: paid-run-harness
description: Launch a paid `claude -p` brain run against a Game Boy world over MCP (Windows host -> WSL claude -> Docker gb-mcp-world) without burning quota on infra mistakes. Invoke before ANY live brain run.
---

# Paid-run harness: `claude -p` brain over a Dockerized GB world

Topology: `wsl claude -p` (the brain, MCP client) ⇄ `docker run -i gb-mcp-world` (the world,
MCP stdio server, wraps `world_mcp.py` + PyBoy). `claude` lives ONLY in WSL at
`/home/nvidia/.local/bin/claude` — there is no Windows claude CLI.

## Hard laws (violating any one wastes a paid run)

1. **Account B ONLY.** Every run script starts with `export CLAUDE_CONFIG_DIR=/home/nvidia/.claude-b`.
   Never run on account A (`~/.claude`) or with an `ANTHROPIC_API_KEY` without David's explicit OK —
   those are his default account / per-token spend. Account-B subscription runs are pre-authorized
   (2026-07-02): just run and report, no per-run approval. A 429 on turn 0 = account-level 5-hour
   session cap — wait for reset, do NOT hammer.
2. **BLANK-AGENT law.** Wipe account-B cross-run auto-memory before EVERY launch (exact line from
   `runs/brain_kirby_v3_1/run.sh`):
   ```bash
   rm -rf /home/nvidia/.claude-b/projects/-mnt-e-AI-Personas-10-pokemon-and-chess-and-office-ai-pokemon-red/memory /home/nvidia/.claude-b/projects/-mnt-e-AI-Personas-10-pokemon-and-chess-and-office-ai-pokemon-red-runs-*/memory 2>/dev/null
   ```
3. **WSL invocation law.** NEVER pipe multi-line bash inline through `wsl.exe` from Git Bash — the
   boundary re-tokenizes newlines and MSYS mangles `2>`/`$vars`. Write a script FILE, run it via the
   **PowerShell** tool: `wsl -u nvidia -- bash -c "tr -d '\r' < /mnt/c/.../x.sh > /tmp/x.sh; bash /tmp/x.sh"`
   (`tr -d '\r'` strips CRLF from the Write tool). Simplest: keep `run.sh` in the launcher dir and run
   `wsl.exe -- bash -lc 'bash /mnt/e/AI_Personas/10_pokemon_and_chess_and_office/ai-pokemon-red/runs/<tag>/run.sh'`.
4. **Rebuild the Docker image after ANY change to `core/`, `games/`, or `world_mcp.py`** — the
   Dockerfile COPYs them; a stale image silently runs OLD code (stale perception looks like a brain bug):
   ```bash
   wsl.exe -- bash -lc 'cd /mnt/e/AI_Personas/10_pokemon_and_chess_and_office/ai-pokemon-red && docker build -t gb-mcp-world .'
   ```
5. **Oracle/RAM/score NEVER on the agent wire.** The brain gets symbolic/screen tools only
   (`--allowedTools mcp__<server>` confines it; no `--with-screenshot` pixels). `world/oracle.jsonl`
   (RAM truth) is scored OFFLINE after the run. Never expose it in the prompt or tools.
6. **One-attempt rule.** A completed run's verdict is BANKED — no reruns to get a better number.
   Relaunch only on infra death before ~10 decisions (MCP never connected, container crash, 429).
   Infra death AT or AFTER ~10 decisions = the attempt is spent: score whatever artifacts exist with
   the frozen scorer and bank that verdict (INSUFFICIENT_DATA is a legitimate outcome). No relaunch
   without David's explicit OK. For any run past ~100 turns, read **long-horizon-runs** first —
   session caps, context growth, and the no-mid-run-checkpoint reality change the calculus.

## Launcher dir anatomy (`runs/brain_<tag>/`)

Three files: `.mcp.json`, `CLAUDE.md` (the brief the brain auto-loads), `run.sh`.

`.mcp.json` (verified: `runs/brain_kirby_v3_1/.mcp.json`) — WSL paths are `/mnt/e/...`, never `E:/...`:
```json
{ "mcpServers": { "<server-name>": {
  "command": "docker",
  "args": ["run", "-i", "--rm",
    "-v", "/mnt/e/AI_Personas/10_pokemon_and_chess_and_office/ai-pokemon-red/roms:/app/roms:ro",
    "-v", "/mnt/e/AI_Personas/10_pokemon_and_chess_and_office/ai-pokemon-red/runs:/app/runs",
    "gb-mcp-world", "--game", "<game>",
    "--init-state", "runs/<state>.state",
    "--out", "runs/brain_<tag>/world", "--record", "--keep-frames"] } } }
```
(`-e KIRBY_SKILLS=1` style env flags go in `args` before the image name. `--record` = session.mp4;
`--keep-frames` = per-step PNGs, otherwise dropped.)

## FREE seam check BEFORE any spend

Never launch until a tools/list against the EXACT docker command from `.mcp.json` shows the expected
tools. Pattern (verified: `runs/brain_kirby_v3_1/seamcheck.sh`) — pipe JSON-RPC initialize +
tools/list into the container, count/inspect tool names, no claude session involved:
```bash
( printf '%s\n' \
  '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"seamcheck","version":"0"}}}' \
  '{"jsonrpc":"2.0","method":"notifications/initialized"}' \
  '{"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}}' ; sleep 8 ) | \
timeout 60 docker run -i --rm <exact -e/-v args from .mcp.json> \
  gb-mcp-world --game <game> --init-state runs/<state>.state --out runs/brain_<tag>/seamcheck_world \
  2>/tmp/seam.err | python3 -c '
import sys, json
for line in sys.stdin:
    try: m = json.loads(line)
    except Exception: continue
    if m.get("id") == 2:
        names = sorted(t["name"] for t in m["result"]["tools"]); print(names, "| total:", len(names))'
tail -1 /tmp/seam.err
```
Verify the tool COUNT and any flag-gated tools (e.g. `KIRBY_SKILLS=1` on vs off) before spending.

## run.sh shape (verified: `runs/brain_kirby_v3_1/run.sh`)

```bash
#!/bin/bash
export CLAUDE_CONFIG_DIR=/home/nvidia/.claude-b
rm -rf /home/nvidia/.claude-b/projects/-mnt-e-AI-Personas-10-pokemon-and-chess-and-office-ai-pokemon-red/memory /home/nvidia/.claude-b/projects/-mnt-e-AI-Personas-10-pokemon-and-chess-and-office-ai-pokemon-red-runs-*/memory 2>/dev/null
LAUNCH=/mnt/e/AI_Personas/10_pokemon_and_chess_and_office/ai-pokemon-red/runs/brain_<tag>

# Trust-dialog pre-acceptance: a fresh CLAUDE_CONFIG_DIR treats the workspace as UNTRUSTED and
# silently ignores .mcp.json. Fix both halves: this snippet + the --mcp-config flag below.
python3 - <<'PY' 2>/dev/null || true
import json, os
cfg = os.path.expanduser("~/.claude-b/.claude.json")
try:
    d = json.load(open(cfg))
except Exception:
    d = {}
base = "/mnt/e/AI_Personas/10_pokemon_and_chess_and_office"
paths = [base, base + "/ai-pokemon-red", base + "/ai-pokemon-red/runs/brain_<tag>"]
projects = d.setdefault("projects", {})
for p in paths:
    e = projects.setdefault(p, {})
    e["hasTrustDialogAccepted"] = True
    e["hasCompletedProjectOnboarding"] = True
json.dump(d, open(cfg, "w"), indent=2)
PY

cd "$LAUNCH" || exit 3
rm -rf world
timeout 3600 /home/nvidia/.local/bin/claude --max-turns 90 -p "<kickoff prompt: verify tools first, else output MCP_UNAVAILABLE and stop>" \
  --mcp-config .mcp.json --allowedTools mcp__<server-name> --output-format stream-json --verbose \
  < /dev/null > transcript.jsonl 2> run.err
echo "EXIT=$?" > run.exit
```
- **`--max-turns` is THE budget** (e.g. 90 turns ≈ $5-class run); `timeout 3600` is the wall-clock backstop.
- **`--output-format stream-json` REQUIRES `--verbose`** — without it claude exits 1 instantly.
- `< /dev/null` skips the "no stdin" warning. `--allowedTools mcp__<server-name>` = server key in `.mcp.json`.
- Launch via the **PowerShell** tool with `run_in_background` (per law 3), then monitor:
  `wsl.exe -- bash -lc 'bash /mnt/e/AI_Personas/10_pokemon_and_chess_and_office/ai-pokemon-red/runs/brain_<tag>/run.sh'`.
  Single-line `wsl.exe` invocations are safe from either shell; law 3 only forbids piping multi-line
  bash inline.

## Health mid-run / completion / reporting

Mid-run (all free, from Windows):
- `transcript.jsonl` growing (size/line count over a few minutes)?
- `run.err` empty or PyBoy noise only (a claude error lands here)?
- `runs/brain_<tag>/world/frame_*.png` count increasing (`--keep-frames`)?

Completed:
- `run.exit` contains `EXIT=0` (124 = wall-clock timeout).
- LAST line of `transcript.jsonl` is the `type=result` event: check `subtype` (`success` vs
  `error_max_turns`), `num_turns`, `is_error`, `total_cost_usd`.
- Score offline from `world/oracle.jsonl` with the repo venv, NOT bare `python3` (MS-Store alias trap
  on this host): `UV_PROJECT_ENVIRONMENT=.venv-win UV_NATIVE_TLS=true uv run --frozen python ...`.
- **Report `total_cost_usd` and `num_turns` to David** in the run summary, always (it is the
  estimated API cost; free on subscription but tracked).
- Before blaming the perceiver: replay `world/frame_*.png` + `oracle.jsonl` offline first — cheap,
  no paid session.

## Sources
- `runs/brain_kirby_v3_1/run.sh` (account-B export, blank-agent rm, trust snippet, launch line)
- `runs/brain_kirby_v3_1/.mcp.json` (docker server anatomy)
- `runs/brain_kirby_v3_1/seamcheck.sh` (free seam check)
- `reports/2026-06-26-mcp-claude-p-runbook.md` (env split, gotchas, outputs)
- `Dockerfile` (COPY core/ games/ world_mcp.py -> rebuild law)
- memory: `mcp-claude-p-harness.md`, `claude-p-run-authorization.md`, `wsl-command-quoting.md`
