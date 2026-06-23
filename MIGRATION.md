# MIGRATION — moving this project to another machine

"This project" = the **git repo** + a set of **local-only (gitignored)** artifacts + the **out-of-repo
Claude auto-memory**. Cloning is *not* enough — the lists below are what isn't in git. (Sizes: 2026-06-23.)

## 1. Clone (everything tracked)
```
git clone https://github.com/David-Dashboard/ai-pokemon-red.git
cd ai-pokemon-red
git checkout feat/cross-game-perception      # the active branch
uv sync                                       # recreates the main .venv from uv.lock
```

## 2. Copy manually — local-only, NOT in git (~1 GB)
| Path | Size | Why |
|---|---|---|
| `runs/` | 955 MB | recorded corpus + `.state` checkpoints (incl. `runs/kanto1/checkpoint_02.state`) + the ViZDoom run. Hard to re-derive. |
| `roms/` | 8.5 MB | copyrighted GB ROMs — NEVER published; local only. |
| `CLAUDE.md` | 6 KB | project instructions (gitignored). |
| `.claude/` (repo-local) | 24 KB | hooks (SessionStart / PreCompact / PreToolUse-commit-gate), settings, plans. |

Plus the **out-of-repo Claude auto-memory** (the cross-session brain) — copy the whole folder:
```
C:\Users\Succe\.claude\projects\C--Users-Succe-Documents-Github-ai-pokemon-red\memory\
```
(`MEMORY.md` + 14 topic memories.) Optionally the `*.jsonl` transcripts in that same folder = chat history.

> ⚠️ That `projects\…` folder name is **derived from the project's absolute path**. It auto-loads only if
> the project lives at the **same path** on the new machine (`C:\Users\Succe\Documents\Github\ai-pokemon-red`).
> Different user/location → Claude generates a *different* folder name → drop `memory\` under that new folder.

## 3. Recreate — do NOT copy (venvs ~2 GB, break across machines)
- **Main env:** `uv sync` (step 1).
- **Probe env** (`.venv-probe4` — CLIP MobileCLIP2-S0 + RapidOCR; used by `eval/probe_modality_appearance.py`
  and the other `eval/probe_*`/vision scripts):
  ```
  uv venv .venv-probe4 --python 3.12
  uv pip install --python .venv-probe4/Scripts/python.exe -r eval/requirements-probe.txt \
      --extra-index-url https://download.pytorch.org/whl/cpu
  ```
  (`torch==2.12.1+cpu` needs the CPU wheel index. Model weights — MobileCLIP2-S0, RapidOCR — auto-download
  to `~/.cache` on first use.) Smoke check: `.venv-probe4/Scripts/python.exe eval/probe_modality_appearance.py`.
- **Skip / regenerated:** `_vizdoom.ini`, `red_system_prompt.txt`, `__pycache__/`, `weights/`, `aria_memory_archives/`.

## 4. Environment + auth
- Install **uv** + **Python 3.12**. (Windowed recorder needs PySDL2 — handled by `uv sync`.)
- **Re-auth Claude Code**; **re-auth git** (push target `David-Dashboard/ai-pokemon-red`).
- **Only for PAID Pokémon runs** (the cross-game odometry work is free/offline): also bring the separate
  **`ai-aria`** repo + its data (constitution, `ARIA_DATA_DIR`, aria memory) and the **Anthropic API key/credits**.

## 5. Verify
```
uv run pytest -q                                                   # full suite (no ROM/PyBoy) — expect all green
.venv-probe4/Scripts/python.exe eval/probe_modality_appearance.py # CLIP/OCR probe runs
```
