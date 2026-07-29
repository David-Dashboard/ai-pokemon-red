#!/bin/bash
# $0 PRE-FLIGHT for the EX02 float-start probe. Run from WSL AFTER David's Float Islands savestate
# exists and the launcher template has been copied into the launch dir. Spends nothing: no claude
# session, runs/ is mounted READ-ONLY for the world boot, all output goes to /tmp/ex02_preflight.
# On success writes <launch>/preflight.ok (run.sh refuses to launch without it).
#
# Checks: launch dir populated; placeholder resolved; the EXACT --init-state named in .mcp.json
# exists, boots, and its first oracle row reads stage=2 / hp>=1 with exactly the hp+stage keys;
# tools/list is exactly the 9 expected tools; the frozen scorer refuses a missing oracle and does
# not PASS the pre-run trace; WSL claude binary, account-B dir and world image all present.
#
# Test-only overrides (used by the $0 rehearsal recorded in the scoping doc §6 — NEVER for a real
# launch; when either is set, preflight.ok is NOT written):
#   PREFLIGHT_LAUNCH_DIR — check a different launch dir
#   PREFLIGHT_STATE_DIR  — host dir holding the state file named in .mcp.json
set -u
REPO_RUNS=/mnt/e/AI_Personas/10_pokemon_and_chess_and_office/ai-pokemon-red/runs
ROMS=/mnt/e/AI_Personas/10_pokemon_and_chess_and_office/ai-pokemon-red/roms
SRC="$(cd "$(dirname "$0")/../../../.." && pwd)"   # the checkout this script lives in -> its eval/ scorer
LAUNCH="${PREFLIGHT_LAUNCH_DIR:-$REPO_RUNS/probe_ex02_kirby_stage3_floatstart}"
# Per-invocation scratch: the container writes into the mount as root, so a fixed dir would not be
# removable by this (non-root) script on the next run. Leftovers die with /tmp on reboot.
SCRATCH=$(mktemp -d /tmp/ex02_preflight.XXXXXX)
fail() { echo "PREFLIGHT: FAIL — $1"; exit 1; }

[ -f "$LAUNCH/.mcp.json" ] || fail "no .mcp.json in $LAUNCH (copy launcher/mcp.json to .mcp.json)"
[ -f "$LAUNCH/CLAUDE.md" ] || fail "no CLAUDE.md brief in $LAUNCH"
if grep -q REPLACE_WITH_FLOAT_ISLANDS_STATE "$LAUNCH/.mcp.json"; then
  fail ".mcp.json still carries the --init-state placeholder"
fi

STATE=$(python3 - "$LAUNCH/.mcp.json" <<'PY'
import json, sys
args = json.load(open(sys.argv[1]))["mcpServers"]["kirby"]["args"]
print(args[args.index("--init-state") + 1])
PY
) || fail "cannot parse --init-state out of .mcp.json"

if [ -n "${PREFLIGHT_STATE_DIR:-}" ]; then
  echo "NOTE: PREFLIGHT_STATE_DIR override active — NOT a launch-valid preflight"
  HOST_STATE="$PREFLIGHT_STATE_DIR/$(basename "$STATE")"
  MOUNT=(-v "$PREFLIGHT_STATE_DIR:/app/pfstate:ro")
  CSTATE="pfstate/$(basename "$STATE")"
else
  case "$STATE" in runs/*) ;; *) fail "--init-state must live under runs/ (got: $STATE)";; esac
  HOST_STATE="$REPO_RUNS/${STATE#runs/}"
  MOUNT=()
  CSTATE="$STATE"
fi
[ -f "$HOST_STATE" ] || fail "state file not found on host: $HOST_STATE"

/home/nvidia/.local/bin/claude --version >/dev/null 2>&1 || fail "WSL claude binary missing"
[ -d /home/nvidia/.claude-b ] || fail "account-B config dir /home/nvidia/.claude-b missing"
docker image inspect gb-mcp-world:latest >/dev/null 2>&1 || fail "gb-mcp-world:latest image missing"

# World boots from the pinned state; 9 tools; one observe -> one oracle row. runs/ READ-ONLY.
( printf '%s\n' \
  '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"preflight","version":"0"}}}' \
  '{"jsonrpc":"2.0","method":"notifications/initialized"}' \
  '{"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}}' ; sleep 6 ; printf '%s\n' \
  '{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"observe","arguments":{}}}' ; sleep 8 ) | \
timeout 120 docker run -i --rm \
  -v "$ROMS:/app/roms:ro" -v "$REPO_RUNS:/app/runs:ro" -v "$SCRATCH:/app/pfout" "${MOUNT[@]}" \
  gb-mcp-world --game kirby_dreamland --init-state "$CSTATE" --out pfout/world \
  > "$SCRATCH/rpc.out" 2> "$SCRATCH/rpc.err"

python3 - "$SCRATCH/rpc.out" <<'PY' || fail "tools/list or observe failed (see $SCRATCH/rpc.*)"
import json, sys
tools, observed = None, False
for line in open(sys.argv[1]):
    try:
        m = json.loads(line)
    except Exception:
        continue
    if m.get("id") == 2:
        tools = sorted(t["name"] for t in m["result"]["tools"])
    if m.get("id") == 3 and not m.get("error"):
        observed = True
expect = ["explore", "goto", "observe", "press_button", "press_sequence",
          "read_region", "remember", "wait", "whats_changed"]
assert tools == expect, f"tool list mismatch: {tools}"
assert observed, "observe call failed"
print("tools OK (9), observe OK")
PY

python3 - "$SCRATCH/world/oracle.jsonl" <<'PY' || fail "oracle row check failed (want stage=2, hp>=1)"
import json, sys
rows = [json.loads(l) for l in open(sys.argv[1]) if l.strip()]
assert rows, "no oracle rows"
w = rows[-1]["watch"]
assert set(w) == {"hp", "stage"}, f"watch keys wrong: {sorted(w)}"
assert w["stage"] == 2, f"stage={w['stage']} (want 2 = the Float Islands start)"
assert w["hp"] >= 1, f"hp={w['hp']} (boot/dead signature)"
print(f"oracle row OK: {w}")
PY

# Frozen scorer is fail-closed on this exact tree: refuses a missing file, cannot PASS pre-run.
cd "$SRC" || fail "cannot cd to $SRC"
python3 -m eval.score_exam_kirby_stage3 "$SCRATCH/nope/oracle.jsonl" | grep -q INSUFFICIENT_DATA \
  || fail "scorer did not refuse a missing oracle file"
if python3 -m eval.score_exam_kirby_stage3 "$SCRATCH/world/oracle.jsonl" | grep -q '"overall": "PASS"'; then
  fail "scorer PASSed a pre-run trace — must be impossible, do not launch"
fi

if [ -n "${PREFLIGHT_STATE_DIR:-}${PREFLIGHT_LAUNCH_DIR:-}" ]; then
  echo "PREFLIGHT: OK (TEST MODE — no preflight.ok written)"
else
  sha256sum "$HOST_STATE" > "$LAUNCH/preflight.ok"
  echo "PREFLIGHT: OK — $STATE verified (sha256 recorded in preflight.ok)"
fi
