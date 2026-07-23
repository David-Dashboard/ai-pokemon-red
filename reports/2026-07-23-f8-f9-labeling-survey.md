# 2026-07-23 — F8/F9 dataset-gap survey + honest $0 backfill

Scope: capability-map Track F8 ("label the frontier data" — GBA/NDS ground truth) and F9 ("fill
the OCR ground-truth hole" — text/health read-strings). $0 session, worktree
`data/f8-f9-labeling-2026-07-23`, no paid runs, held-out law respected throughout (Crystalis/
Zelda-LA/SML/F-1/Doom untouched; no title on any current exam-reserve list — F10 "name the exam
reserve" has not happened yet, so no such list exists to check against).

## Verdict up front

- **F9: partial backfill landed.** 34 read-values added to `2026-06-23_cavenoire_explore` (the
  only game with both a validated RAM oracle address AND enough existing hand-typed examples to
  pin the on-screen format). Corpus-wide OCR coverage: **48/661 (7%) → 82/661 (12%)**. Every other
  F9 candidate was evaluated and rejected/deferred with a concrete reason below — not silently
  skipped.
- **F8: genuine gap, correctly not fake-filled.** GBA/NDS frames exist and *are* structurally
  compatible with `label_frames.py` (contrary to what "GB-only manifest" might suggest — the tool
  itself is game-agnostic). The missing piece is a **human** at a display running the interactive
  tool. An agent cannot do this hand-labeling itself without violating the provenance law (there is
  no RAM oracle for any GBA/NDS world in `world_mcp.py` — every entry's `"watch"` is `{}` — so a
  model "reading the pixels" to place/caption boxes would be exactly the forbidden
  model-generated-not-oracle-checked case, indistinguishable after the fact from a real hand label).
  No frames were labeled for F8 this session. Exact minimal path below.

## F9 — OCR read-value backfill

### Method (oracle-derive, not eyeballing)

`record.py --ram` writes one 8KB WRAM snapshot per recorded step to `ram.bin`, indexed by the same
step counter used for the `frame_NNNNNN.png` filename and the label JSON's `"frame"` field — so a
label frame index maps 1:1 onto a `ram.bin` chunk. `eval/score_hud_grounding.py` /
`eval/score_entity_gate*.py` already validate Cave Noire's HP oracle as **BCD @ 0xC120** (battle-
tested across 4+ scorer files, not re-derived here). That's the only pre-existing, validated,
non-Pokemon-Red RAM-HP address in the codebase.

Script (scratch, not committed — a data backfill, not a new tool):
1. Decode BCD HP at `0xC120` for the 5 frames `2026-06-23_cavenoire_explore` already has hand-typed
   (`HP10/10`, `HP 3/10`, etc.) — **all 5 matched exactly**, confirming frame-index ↔ ram.bin chunk
   alignment and the `"HP{v:>2}/10"` format convention.
2. Backfilled the remaining **34 blank, `mode:"gameplay"` `health`-category boxes** with the same
   decode.
3. Spot-checked frame 1599 (`HP 5/10`) against its actual PNG — matches on screen.

`runs/2026-06-23_cavenoire_explore/frame_labels.json` (the live corpus) was edited directly, then
`uv run python -m eval.snapshot_labels --version v3` regenerated `datasets/labels/v3/` from ALL
`runs/*/frame_labels.json` (all 13 games — the other 12 are byte-for-byte unchanged from v2; only
`2026-06-23_cavenoire_explore.json` differs).

### What was deliberately NOT backfilled, and why

| game | health/text boxes blank | why not touched |
|---|---|---|
| `cavenoire_explore` (3 boxes) | 3 `mode:"menu"` health boxes | Menu-mode HP renders differently (`"HP. 4/10"`, seen once in a `text` box at frame 159 — note the period) than gameplay's `"HP10/10"`. One example is not enough to pin the exact format (is "10" `"HP.10/10"` or `"HP. 10/10"`?). Left blank rather than guess. |
| `kirby_ramplay` (19 health boxes, 1 pre-filled) | 18 blank | **Visually confirmed not OCR-able**: viewed `frame_000053.png` and `frame_000418.png` — the right-hand "health" box is a row of heart *icons* (graphical vitality bar), not digit text; there is no on-screen numeral for HP at all. The one existing value (`"KIRBY"`, frame 418) is a static name-plate, not an HP reading. `world_mcp.py`'s `kirby_dreamland` watch (`hp @ 0xD086`) is real RAM but has no corresponding on-screen text to transcribe — inserting a number would fabricate a read-string for something that isn't rendered as text. |
| `gauntlet_ramplay`, `metroid_ramplay`, `tetris_auto` | 0 health boxes exist | Nothing to backfill (manifest already shows `health:0` for all three). |
| `gold_explore`, `ffa_explore`, `spaceinv_auto`, `red_resume` | 8/11/8/8 blank (resp.) | **No validated RAM oracle address exists in this codebase** for these games' HP/status text. `world_mcp.py`'s `GAMES` dict has no entry for Gold/FFA/Space Invaders/Tetris at all, and Pokémon Red's party struct (`games/pokemon_red/memory_map.py`, cur/max HP at party-mon offsets `0x01`/`0x22`) IS validated — but `red_resume`'s 8 blank health boxes are all in scrolling menu/summary screens with wildly varying box geometry and **zero existing hand-typed examples** to pin which party slot/format each box shows. Guessing either the address-to-game mapping (Gold/FFA/etc.) or the format (Red) would be exactly the "model-generated, not oracle-checked" case the provenance law forbids. Flagged as a good **next** F9 target (the party-HP decode already exists; someone just needs to hand-verify the format once per box position, the same way the 5 existing Cave Noire examples bootstrapped this session's backfill). |

Net: 82/661 boxes now carry a read-value (12%), up from 48/661 (7%). Still concentrated in early/
dev games, still "not yet cross-world" — this was a backfill of the existing hole, not a claim that
the hole is closed.

## F8 — GBA/NDS ground truth

### What's actually on disk

`label_frames.py`'s glob (`frame_*.png`) is not GB-specific — it matches whatever's there. Survey
of every GBA/NDS directory under `runs/`:

| directory | frames | `frame_*.png`-compatible? |
|---|---|---|
| `runs/nds3d_probe/{mario-kart-ds*,nsmb*,spirit-tracks,re-deadly-silence*}` | 8-18 each | **No** — ad-hoc probe scripts named frames `boot_0060.png`, `00_title_replay.png`, `s000_boot.png`, `accel_f000.png`, etc. This is the directory F8's own capability-map entry named (`runs/nds3d_probe`) — it is NOT directly label-tool-compatible as named. |
| `runs/nds_play/kirby` | 63 | **Yes** |
| `runs/nds_play/nsmb` | 61 | **Yes** |
| `runs/nds_play/game` | 63 | **Yes** |
| `runs/nds_play/nsmb-smoke` | 61 | **Yes** |
| `runs/nds_bench/nsmb` | present | **Yes** |
| `runs/probe_0247_-_Mortal_Kombat_Advance...world/` | 14 | **Yes** (GBA) |
| `runs/probe_2288_-_...Dragon_Ball_Z.../world/` | 41 | **Yes** (GBA) |
| `runs/probe_2689_-_...Final_Fantasy_VI.../world/` | 28 | **Yes** (GBA) |
| `runs/probe_Legend_of_Zelda...Minish_Cap.../world/` | 35 | **Yes** (GBA; NOT the held-out title — Zelda-LA is GB, Minish Cap is a different GBA game) |
| `runs/probe_Naruto.../world/` | 22 | **Yes** (GBA) |
| `runs/probe_Super_Mario_Advance_2.../world/` | 37 | **Yes** (GBA) |

So there IS a labelable, glob-compatible corpus: ~250 GBA frames across 6 games + ~250 NDS frames
across 2-3 games (`kirby`/`nsmb`/`game` in `nds_play` look like separate ROMs by directory name but
none carry a `meta.json` to confirm which; `INDEX.md` marks the whole `nds_play` batch "NO oracle").
None of it has been hand-labeled — `datasets/labels/v2` (now v3) is 100% GB (160×144).

The `runs/nds3d_probe` directory F8's capability-map entry specifically names is the **wrong**
corpus to point `label_frames.py` at without a rename/copy pass first (wrong filenames, and mostly
tiny 8-18-frame boot sequences rather than sustained gameplay).

### Why this session did not hand-label any of it

1. `label_frames.py` is interactive: tkinter window, mouse-drag boxes, a `simpledialog` text prompt
   per text/health box. It requires a **human** watching the frame and typing what it says.
2. This is an autonomous agent session. Driving that GUI myself (even via computer-use style pixel
   control) would mean *I* decide box placement and transcribe on-screen text by looking at it — no
   different in substance from an LLM hand-labeling, and there is no RAM oracle to check it against
   for ANY GBA/NDS world (`world_mcp.py`: `kirby_gba`, `emerald_gba`, and every NDS entry all have
   `"watch": {}`). That is precisely the case the task's provenance law forbids ("model-generated
   labels not oracle-checked"), and the resulting JSON would be indistinguishable from a genuine
   hand label after the fact — worse than an honest gap.
3. Unlike F9's Cave Noire case, there is no shortcut: no validated RAM address exists for any
   GBA/NDS world's on-screen text/entities in this codebase, so there is no oracle-derive path
   either.

### Minimal path (for a human, or a future session with a human at the keyboard)

Already-recorded, ready today:
```
python -m eval.label_frames runs/nds_play/kirby --n 30
python -m eval.label_frames runs/nds_play/nsmb --n 30
python -m eval.label_frames "runs/probe_2288_-_2_in_1_-_Dragon_Ball_Z_-_The_Legacy_of_Goku_I___II__U/world" --n 20
# ...repeat per game, then:
uv run python -m eval.snapshot_labels --version v4
```
~20-30 min/game hand-labeling, same as the existing GB corpus was built.

Needs a recording pass first (no frames exist yet): the capability-map's F8 also names one
touch-driven NDS game "nearly pure reading/touch." Both candidates are on the shelf —
`roms/nds/Phoenix Wright - Ace Attorney - Trials and Tribulations (USA).nds` and
`roms/nds/Professor Layton and the Curious Village (USA, Australia).nds` — but neither has been
recorded (no `runs/` directory for either). That's `play_nds.py`/an NDS recorder pass, THEN
`label_frames.py`, i.e. two missing steps, not one.

## Files touched this session

- `runs/2026-06-23_cavenoire_explore/frame_labels.json` (gitignored corpus, not committed) — 34
  read-values backfilled.
- `datasets/labels/v3/*.json` + `datasets/labels/v3/manifest.md` (new, committed) — full re-snapshot
  of all 13 games; only `2026-06-23_cavenoire_explore.json` differs from v2.
- This report.

No code changed, no new eval/ tool added, no held-out or exam-reserve title touched.
