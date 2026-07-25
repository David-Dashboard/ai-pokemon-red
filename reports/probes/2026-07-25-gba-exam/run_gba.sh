#!/usr/bin/env bash
# Thin launcher for gba_drive.py under the proven WSL mgba env (reports/2026-06-29-gba-mgba-recipe.md).
# Single-line invocation from Windows: wsl.exe -e bash -lc "/mnt/.../run_gba.sh --rom ... ..."
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
export LD_LIBRARY_PATH="$HOME/gba-spike"
export PYTHONPATH="$HOME/gba-spike/mgba-build/python/lib.linux-x86_64-3.8:$REPO_ROOT"
exec "$HOME/gba-spike/.venv/bin/python3" "$REPO_ROOT/reports/probes/2026-07-25-gba-exam/gba_drive.py" "$@"
