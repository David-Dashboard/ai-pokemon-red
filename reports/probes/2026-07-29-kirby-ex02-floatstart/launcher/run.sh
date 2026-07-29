#!/bin/bash
# PAID launch: EX02 float-start probe — ONE attempt. Prereg: reports/2026-07-29-kirby-ex02-probe-scoping.md §6.
# Run from WSL: wsl.exe -- bash -lc 'bash /mnt/e/AI_Personas/10_pokemon_and_chess_and_office/ai-pokemon-red/runs/probe_ex02_kirby_stage3_floatstart/run.sh'
#
# ⚠ NO live spend kill switch exists on this path (LiveCreditGuard is constructed only in the
# Gate-0 appserver tools; the claude -p harness never imports it). The ONLY bounds are
# --max-turns 150 and the timeout 2400 below. Do not raise either without a prereg amendment.
#
# EX02_DRY_RUN=1 exercises every guard below and exits BEFORE the account-B wipe and the paid line.
LAUNCH=/mnt/e/AI_Personas/10_pokemon_and_chess_and_office/ai-pokemon-red/runs/probe_ex02_kirby_stage3_floatstart

cd "$LAUNCH" || { echo "REFUSING: launch dir missing ($LAUNCH) — copy the launcher template in first"; exit 3; }
[ -f .mcp.json ] || { echo "REFUSING: no .mcp.json in $LAUNCH (copy launcher/mcp.json to .mcp.json)"; exit 3; }
[ -f CLAUDE.md ] || { echo "REFUSING: no CLAUDE.md brief in $LAUNCH"; exit 3; }
if grep -q REPLACE_WITH_FLOAT_ISLANDS_STATE .mcp.json; then
  echo "REFUSING: .mcp.json still carries the --init-state placeholder"; exit 3
fi
[ -f preflight.ok ] || { echo "REFUSING: no preflight.ok — run preflight.sh first (it is \$0)"; exit 3; }
if [ -e world ] || [ -e transcript.jsonl ]; then
  echo "REFUSING: prior attempt artifacts exist — ONE-ATTEMPT rule; no relaunch without David's explicit OK"; exit 4
fi
if [ -n "${EX02_DRY_RUN:-}" ]; then
  echo "DRY_RUN OK: all guards passed; would wipe account-B auto-memory, pre-accept trust, then run claude -p (--max-turns 150, timeout 2400s)"
  exit 0
fi

# Account-B ONLY (paid-run-harness law 1) + BLANK-AGENT law (law 2)
export CLAUDE_CONFIG_DIR=/home/nvidia/.claude-b
rm -rf /home/nvidia/.claude-b/projects/-mnt-e-AI-Personas-10-pokemon-and-chess-and-office-ai-pokemon-red/memory /home/nvidia/.claude-b/projects/-mnt-e-AI-Personas-10-pokemon-and-chess-and-office-ai-pokemon-red-runs-*/memory 2>/dev/null

# Trust-dialog pre-acceptance: a fresh CLAUDE_CONFIG_DIR otherwise silently ignores .mcp.json
python3 - <<'PY' 2>/dev/null || true
import json, os
cfg = os.path.expanduser("~/.claude-b/.claude.json")
try:
    d = json.load(open(cfg))
except Exception:
    d = {}
base = "/mnt/e/AI_Personas/10_pokemon_and_chess_and_office"
paths = [base, base + "/ai-pokemon-red", base + "/ai-pokemon-red/runs/probe_ex02_kirby_stage3_floatstart"]
projects = d.setdefault("projects", {})
for p in paths:
    e = projects.setdefault(p, {})
    e["hasTrustDialogAccepted"] = True
    e["hasCompletedProjectOnboarding"] = True
json.dump(d, open(cfg, "w"), indent=2)
PY

timeout 2400 /home/nvidia/.local/bin/claude --max-turns 150 -p "FIRST: verify the mcp__kirby tools (observe, whats_changed, read_region, explore, goto, press_button, press_sequence, wait, remember) are available — if NOT, output exactly MCP_UNAVAILABLE and stop immediately. Then play per CLAUDE.md: the game is loaded MID-GAME at the start of an island stage with Kirby at full vitality. observe first, confirm control with one small press + whats_changed, then CLEAR the stage you are in — fight through it, defeat whatever blocks the way out, advance out of the stage — and keep playing into whatever follows, as far as the budget allows. Budget: 150 decisions total; if stuck at one spot for many decisions, change maneuver (float over, inhale, approach from another side) — never repeat an input that has already failed twice unchanged. When you cannot continue or the budget is nearly spent, end with the ONE-line summary per CLAUDE.md." \
  --mcp-config .mcp.json --allowedTools mcp__kirby --output-format stream-json --verbose \
  < /dev/null > transcript.jsonl 2> run.err
echo "EXIT=$?" > run.exit
