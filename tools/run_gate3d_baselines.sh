#!/usr/bin/env bash
# tools/run_gate3d_baselines.sh -- WSL/Docker driver for the three FREE GATE-3D-A1 baselines
# (tools/gate3d_baselines.py): random policy, blind spinner, ATTACK-only. 200 episodes each against
# scenarios/dtc_gate.cfg, no LLM, no MCP seam -- pure Docker CPU (mirrors tools/run_smoke_sweep.sh's
# shape for the GB/NDS sweep).
#
# From Windows PowerShell:  wsl.exe -e bash /mnt/e/.../repo/tools/run_gate3d_baselines.sh
#
# Requires the vizdoom-world image (built from Dockerfile.vizdoom):
#   docker build -f Dockerfile.vizdoom -t vizdoom-world .
#
# Output: runs/gate3d_baselines/{random,spinner,attack_only}.jsonl + summary.json (gitignored, like the
# rest of runs/). The reviewed, committed record is eval/fixtures/gate3d_baselines.json -- written BY
# HAND from this run's summary.json, not by this script (see gate3d_baselines.py's module docstring).
set -u

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO" || exit 3
OUT="$REPO/runs/gate3d_baselines"
mkdir -p "$OUT"

echo "== GATE-3D-A1 free baselines (Docker vizdoom-world) ==" >&2
docker run --rm -v "$REPO:/work" -w /work --entrypoint python vizdoom-world \
  tools/gate3d_baselines.py --out-dir runs/gate3d_baselines "$@"
status=$?

if [ $status -ne 0 ]; then
  echo "WARN: gate3d_baselines container exited nonzero ($status)" >&2
fi

echo "== summary ==" >&2
cat "$OUT/summary.json" 2>/dev/null
exit $status
