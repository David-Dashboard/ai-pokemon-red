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

## 6. HELD-OUT verification games — AUTONOMOUS ONLY (never human, never tuned on)
The `dataset_split` held-out set (Crystalis / Zelda LA / SML / F-1 Race) is recorded **HANDS-OFF** — human input
would defeat the zero-shot test and risk leakage. Same `--explore` policy as dev, no `--load-state`:
```
.venv-win/Scripts/python.exe record.py --rom "roms/Crystalis (USA).gbc"                              --name crystalis_explore --mode auto --explore --hold 16 --settle 4 --ram --steps 4000
.venv-win/Scripts/python.exe record.py --rom "roms/Super Mario Land (World) (Rev 1).gb"             --name sml_explore       --mode auto --explore --hold 16 --settle 4 --ram --steps 4000
.venv-win/Scripts/python.exe record.py --rom "roms/Legend of Zelda, The - Link's Awakening (U) (V1.2) [!].gb" --name zelda_explore --mode auto --explore --hold 16 --settle 4 --ram --steps 4000
.venv-win/Scripts/python.exe record.py --rom "roms/F-1 Race (World).gb"                              --name f1race_explore    --mode auto --explore --hold 16 --settle 4 --ram --steps 4000
```
Then score zero-shot: `.venv-win/Scripts/python.exe -m eval.verify_heldout`
NOTE: `--explore` only drives top-down games (Crystalis). Side-scrollers (SML), intro-gated (Zelda), and racers
(F-1, needs sustained accelerate) come out **LOW-MOTION → inconclusive** — that's the autonomous-control gap, not
a perception failure. Do NOT hand-play them to "fix" it; that gap is the agent's job.

## 7. RAM-GROUNDING (`--watch`) — true position oracle for the ego-motion estimator
To validate ego-motion against TRUTH on non-Pokémon games, log known WRAM position bytes per step with
`--watch name=HEXADDR,...` (world-agnostic: just reads `pb.memory[addr]`; the address is looked up per game on
Data Crystal RAM maps). Validated end-to-end on Red (`x=0xD362,y=0xD361` tracked live position). Looked-up
camera/position addresses:
- **Metroid II:** `x_px=0xD027,x_scr=0xD028,y_px=0xD029,y_scr=0xD02A` (X/Y within area = world position).
- **Kirby's Dream Land:** `scroll_x=0xD051` (the camera scroll register — exactly what `best_shift` estimates).
- **Super Mario Land** (HELD-OUT — verification oracle only): `0xC202` is Mario *on-screen* X, NOT the level
  scroll; find the scroll/level-X before relying on it.
```
# pair clean locomotion WITH the oracle (human play, since auto can't drive these):
.venv-win/Scripts/python.exe record.py --rom "roms/Metroid II - Return of Samus (World).gb" --name metroid_play_ram --mode human --ram --watch x_px=0xD027,x_scr=0xD028,y_px=0xD029,y_scr=0xD02A
.venv-win/Scripts/python.exe record.py --rom "roms/Kirby's Dream Land (USA, Europe).gb"     --name kirby_play_ram   --mode human --ram --watch scroll_x=0xD051
```
GBC games (Crystalis, Gold) have BANKED WRAM (0xD000–0xDFFF switches) — a single fixed address may be unreliable;
prefer DMG titles or verify the bank.

**Undocumented games (no Data Crystal map) — auto-discover the address:** `eval/find_ram_addr.py` correlates each
WRAM byte's per-step delta with the pressed direction (uses the recorded `ram.bin` + `buttons.jsonl`; no game
knowledge). It needs a run where the avatar moved under clean presses (e.g. a `--explore` run with `--ram`).
```
uv run python -m eval.find_ram_addr runs/<run-with-ram.bin>     # ranked X/Y candidate addresses (consistency, n, range)
```
Pick the HIGH-consistency, HIGH-n, HIGH-range candidate, then confirm with `--watch`. Worked example (Gauntlet II,
fully undocumented): finder → X `0xC286`, Y `0xC2C6` (100%, n>700); `--watch x=0xC286,y=0xC2C6` confirmed they
track live movement (changed 146/299 steps).

