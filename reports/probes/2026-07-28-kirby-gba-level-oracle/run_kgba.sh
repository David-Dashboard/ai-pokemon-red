#!/usr/bin/env bash
# Thin launcher for kgba_drive.py under the proven WSL mgba env (reports/2026-06-29-gba-mgba-recipe.md).
# Invoked from Windows as: wsl.exe -e bash <this-script> --plan /mnt/c/.../plan.json
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
export LD_LIBRARY_PATH="$HOME/gba-spike"
export PYTHONPATH="$HOME/gba-spike/mgba-build/python/lib.linux-x86_64-3.8:$REPO_ROOT"
exec "$HOME/gba-spike/.venv/bin/python3" \
  "$REPO_ROOT/reports/probes/2026-07-28-kirby-gba-level-oracle/kgba_drive.py" "$@"
