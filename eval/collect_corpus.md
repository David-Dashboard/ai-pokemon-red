# Camera-model / odometry corpus — collection runbook (2026-06-23)

The recorded corpus lives under `runs/` which is **gitignored** (raw data, kept locally / on the big disk —
here junctioned to `D:\ai_pokemon_runs`). This file is the **recipe** to regenerate it. Run from the repo root
with the main env (`UV_PROJECT_ENVIRONMENT=.venv-win`); recorder + probe are numpy+PIL only (no probe venv).

Interpreter used below: `.venv-win/Scripts/python.exe` (Windows). On Linux use `uv run python`.

## Why a recipe and not stored data
The jittery `--smart-auto` policy gets the avatar INTO gameplay but wiggles it in place — the camera never
pans, so the camera-model features are starved. Locomotion needs either a direction-PERSISTENT policy
(`--explore`, top-down games) or a human (side-scrollers need run+jump). So the corpus is regenerated, not
shipped.

## 1. Fixed arcade games — cold-boot auto (no camera scroll, policy irrelevant)
```
.venv-win/Scripts/python.exe record.py --rom "roms/Space Invaders (USA) (SGB Enhanced).gb"      --name spaceinv_auto --mode auto --smart-auto --ram --steps 8000
.venv-win/Scripts/python.exe record.py --rom "roms/Tetris Plus (USA, Europe) (SGB Enhanced).gb" --name tetris_auto   --mode auto --smart-auto --ram --steps 8000
```

## 2. Top-down follow-scroller that auto can drive — `--explore` from a gameplay checkpoint
First make a checkpoint past the intro (human, press `C` once in the overworld, then ESC), then resume-record:
```
.venv-win/Scripts/python.exe record.py --rom "roms/Pokemon - Gold Version (USA, Europe) (SGB Enhanced) (GB Compatible).gbc" --name gold_human --mode human
.venv-win/Scripts/python.exe record.py --rom "roms/Pokemon - Gold Version (USA, Europe) (SGB Enhanced) (GB Compatible).gbc" --name gold_explore --mode auto --explore --hold 16 --settle 4 --ram --steps 6000 --load-state runs/<dated>_gold_human/checkpoint_01.state
```

## 3. Games auto CAN'T drive — human play (the locomotion-rich ground truth)
Side-scrollers (run+jump) and any game `--explore` gets stuck on. Play ~2–3 min of real travel (sustained
directions so the camera pans), then ESC. Controls: WASD move, J=A, K=B, Enter=Start, Backspace=Select, C=checkpoint.
```
.venv-win/Scripts/python.exe record.py --rom "roms/Gauntlet II (USA, Europe).gb"            --name gauntlet_play  --mode human
.venv-win/Scripts/python.exe record.py --rom "roms/Kirby's Dream Land (USA, Europe).gb"     --name kirby_play     --mode human
.venv-win/Scripts/python.exe record.py --rom "roms/Metroid II - Return of Samus (World).gb" --name metroid_play   --mode human
.venv-win/Scripts/python.exe record.py --rom "roms/Cave Noire (Japan) [T-En by Aeon Genesis v1.00].gb" --name cavenoire_play --mode human
```

## 4. HELD-OUT 3D (Doom / ViZDoom) — separate env, never used for dev tuning
```
UV_NATIVE_TLS=true uv run --no-project --with vizdoom --with numpy --with pillow python -m eval.vizdoom_smoke
```
Writes `runs/vizdoom_mywayhome/` (frames + buttons + ground-truth pos/angle). `dataset_split` flags it held-out
by dir name.

## 5. Gate + score
`record.py` auto-prefixes run dirs with today's date (`YYYY-MM-DD_`); update the names in
`eval/probe_camera_model.py` (`RUNS` / `UNIT`) to match, then:
```
.venv-win/Scripts/python.exe -m eval.corpus_activity runs/<run> ...   # sustained-gameplay gate (READY/THIN)
.venv-win/Scripts/python.exe -m eval.probe_camera_model               # signatures + sib-mean + held-out Doom test
```
