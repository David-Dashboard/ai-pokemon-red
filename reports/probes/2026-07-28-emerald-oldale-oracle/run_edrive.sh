#!/usr/bin/env bash
# Thin WSL launcher for edrive.py / etrace.py under the proven mgba env
# (reports/2026-06-29-gba-mgba-recipe.md). Called from Windows as:
#   wsl.exe -e bash -lc "/mnt/e/.../run_edrive.sh --rom ... --state-in ... --state-out ..."
# Point REPO_ROOT at whichever checkout/worktree holds core/gba_emulator.py.
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
SCRIPT="${EDRIVE_SCRIPT:-$(dirname "${BASH_SOURCE[0]}")/edrive.py}"
export LD_LIBRARY_PATH="$HOME/gba-spike"
export PYTHONPATH="$HOME/gba-spike/mgba-build/python/lib.linux-x86_64-3.8:$REPO_ROOT"
exec "$HOME/gba-spike/.venv/bin/python3" "$SCRIPT" "$@"
