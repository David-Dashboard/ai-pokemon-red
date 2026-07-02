#!/usr/bin/env bash
# tools/run_smoke_sweep.sh — WSL driver for the free smoke sweep (tools/smoke_sweep.py).
#
# GB/GBC + NDS run inside the gb-mcp-world Docker image (pyboy + py-desmume live there; the
# repo is MOUNTED over /work so tools/ — not baked into the image — is available). GBA runs
# via the WSL ~/gba-spike env (mgba is not pip-installable and is NOT in Docker).
#
# From Windows PowerShell:  wsl.exe -e bash /mnt/e/.../repo/tools/run_smoke_sweep.sh
# ROMs are gitignored, so a worktree checkout has none: set ROMS_DIR to the main checkout's
# roms/ (defaults to <repo>/roms). Extra args are passed through to BOTH smoke_sweep.py
# invocations (e.g. --limit 1 for a quick probe).
#
# Output: runs/smoke_sweep/ (gitignored — never commit it): gb_nds.jsonl + gba.jsonl ->
# all.jsonl -> report.md.
set -u

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# WSL sessions can start in an EPHEMERAL docker-desktop bind-mount dir that a finished container
# tears down mid-script — a later os.getcwd() in the GBA phase then dies with FileNotFoundError
# (seen live 2026-07-03). Stand somewhere stable before anything else runs.
cd "$REPO" || exit 3
ROMS="${ROMS_DIR:-$REPO/roms}"
OUT="$REPO/runs/smoke_sweep"
mkdir -p "$OUT"
rm -f "$OUT/gb_nds.jsonl" "$OUT/gba.jsonl" "$OUT/all.jsonl"

echo "== GB/GBC + NDS sweep (Docker gb-mcp-world) ==" >&2
# smoke_sweep.py exits nonzero only when NO rom was swept; per-game crashes are isolated into the JSONL.
docker run --rm -v "$REPO:/work" -v "$ROMS:/work/roms:ro" -w /work \
  -e SDL_VIDEODRIVER=dummy --entrypoint python gb-mcp-world \
  tools/smoke_sweep.py --all-dir roms --consoles gb,nds \
  --out runs/smoke_sweep/gb_nds.jsonl "$@" \
  || echo "WARN: GB/NDS sweep container exited nonzero" >&2

echo "== GBA sweep (WSL gba-spike env) ==" >&2
GBA_PY="${GBA_PY:-/home/nvidia/gba-spike/py311/python/bin/python3.11}"
GBA_BINDING="${GBA_BINDING:-/home/nvidia/gba-spike/mgba-build/python/lib.linux-x86_64-3.8}"
if [ -x "$GBA_PY" ]; then
  LD_LIBRARY_PATH="${GBA_LIBS:-/home/nvidia/gba-spike}" \
  PYTHONPATH="$GBA_BINDING:$REPO" \
    "$GBA_PY" "$REPO/tools/smoke_sweep.py" --all-dir "$ROMS/gba" --consoles gba \
    --out "$OUT/gba.jsonl" "$@" \
    || echo "WARN: GBA sweep exited nonzero" >&2
else
  echo "WARN: gba-spike python not found at $GBA_PY — skipping the GBA sweep" >&2
fi

cat "$OUT"/gb_nds.jsonl "$OUT"/gba.jsonl 2>/dev/null > "$OUT/all.jsonl"

echo "== report ==" >&2
# The report is stdlib-only; render it in the same image so the driver needs no host python.
docker run --rm -v "$REPO:/work" -w /work --entrypoint python gb-mcp-world \
  tools/smoke_sweep_report.py runs/smoke_sweep/all.jsonl --out runs/smoke_sweep/report.md
cat "$OUT/report.md"
