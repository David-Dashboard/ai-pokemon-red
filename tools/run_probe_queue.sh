#!/usr/bin/env bash
# tools/run_probe_queue.sh — WSL queue-runner for account-B paid probes (tools/make_probe_launcher.py
# output). Reads a queue file (one slug per line), launches each probe_<slug>/run.sh in turn, appends a
# ledger row per attempt, and retries the SAME game after sleeping through a Claude Code session-limit
# hit. Idempotent: a slug with an existing runs/probe_ledger.jsonl row is skipped unless --redo.
#
# Usage: tools/run_probe_queue.sh <queue_file> [--redo]
#   queue_file: one probe slug per line (matches runs/probe_<slug>/), '#'-comments/blanks ignored.
#
# The skip/lock/session-limit/cost-parse decisions are pure Python (tools/probe_queue_lib.py, unit
# tested) — this script is just the orchestration: launch, wait, retry-on-limit, append ledger row.
set -u

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO" || exit 3

QUEUE="${1:-}"
REDO=0
for arg in "$@"; do
  [ "$arg" = "--redo" ] && REDO=1
done
if [ -z "$QUEUE" ] || [ ! -f "$QUEUE" ]; then
  echo "usage: $0 <queue_file> [--redo]" >&2
  exit 2
fi

LEDGER="$REPO/runs/probe_ledger.jsonl"
LOCK="$REPO/runs/.probe_queue.lock"
mkdir -p "$REPO/runs"

# A lock file prevents two queue-runners racing on the same ledger. mkdir is atomic on POSIX filesystems;
# `set -C` (noclobber) is not reliable enough over some WSL9p mounts, so use a lock DIRECTORY instead.
if ! mkdir "$LOCK" 2>/dev/null; then
  echo "another run_probe_queue.sh appears to be running (lock dir exists: $LOCK)" >&2
  echo "remove it manually if you're sure no other queue-runner is active." >&2
  exit 4
fi
trap 'rmdir "$LOCK" 2>/dev/null' EXIT

PY="${PROBE_QUEUE_PY:-python3}"

slugs="$("$PY" -c "
import sys
sys.path.insert(0, '$REPO')
from tools.probe_queue_lib import read_queue
for s in read_queue('$QUEUE'):
    print(s)
")"

if [ -z "$slugs" ]; then
  echo "no slugs in $QUEUE" >&2
  exit 0
fi

while IFS= read -r slug; do
  [ -z "$slug" ] && continue

  should_run="$("$PY" -c "
import sys
sys.path.insert(0, '$REPO')
from tools.probe_queue_lib import ledger_slugs, should_run
done = ledger_slugs('$LEDGER')
print('yes' if should_run('$slug', done, $([ "$REDO" -eq 1 ] && echo True || echo False)) else 'no')
")"
  if [ "$should_run" != "yes" ]; then
    echo "[$slug] already in ledger — skip (--redo to force)" >&2
    continue
  fi

  LAUNCH="$REPO/runs/probe_$slug"
  if [ ! -x "$LAUNCH/run.sh" ]; then
    echo "[$slug] no launcher at $LAUNCH/run.sh — skip (run tools/make_probe_launcher.py first)" >&2
    continue
  fi

  while :; do
    echo "== [$slug] launching ==" >&2
    t0="$(date +%s)"
    bash "$LAUNCH/run.sh"
    exit_code="$(grep -o '[0-9]*' "$LAUNCH/run.exit" 2>/dev/null | head -1)"
    exit_code="${exit_code:-1}"
    t1="$(date +%s)"
    duration="$((t1 - t0))"

    sleep_s="$("$PY" -c "
import sys
sys.path.insert(0, '$REPO')
from tools.probe_queue_lib import parse_session_limit
err = ''
try:
    err = open('$LAUNCH/run.err', encoding='utf-8', errors='replace').read()
except FileNotFoundError:
    pass
try:
    err += open('$LAUNCH/transcript.jsonl', encoding='utf-8', errors='replace').read()[-4000:]
except FileNotFoundError:
    pass
s = parse_session_limit(err)
print(s if s is not None else '')
")"

    if [ -n "$sleep_s" ]; then
      echo "[$slug] session-limit hit — sleeping ${sleep_s}s before retrying the SAME game" >&2
      sleep "$sleep_s"
      continue
    fi
    break
  done

  "$PY" -c "
import json, sys
sys.path.insert(0, '$REPO')
from tools.probe_queue_lib import ledger_row, parse_total_cost_usd
cost = parse_total_cost_usd('$LAUNCH/transcript.jsonl')
row = ledger_row('$slug', $exit_code, $duration, cost)
with open('$LEDGER', 'a', encoding='utf-8') as f:
    f.write(json.dumps(row) + '\n')
print(cost if cost is not None else 'null')
" > /tmp/probe_queue_cost.$$ 2>&1
  cost="$(cat /tmp/probe_queue_cost.$$)"
  rm -f /tmp/probe_queue_cost.$$
  echo "[$slug] exit=$exit_code duration=${duration}s cost=${cost} -> ledger" >&2

done <<< "$slugs"

echo "queue done." >&2
