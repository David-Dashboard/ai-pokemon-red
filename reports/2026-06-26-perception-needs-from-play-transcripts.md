# Perception primitives a playing agent needs — mined from 4 PLAY transcripts (2026-06-26)

Method: 4 subagents drove PyBoy directly to play GB games (Pokémon Red battle, Metroid II, Kirby, Pokémon
Gold) with **zero symbolic perception** — they reconstructed every perceptual fact from raw PNGs / pixel
crops / brightness math, and dropped to RAM peeks when pixels failed. **Every RAM peek marks a missing
perception primitive.** Source transcripts: `runs/agent_transcripts/agent-*.jsonl`.

## Ranked needs (most-reached-for first)

1. **Self-localization + walkability** — "where am I, what's walkable, is that a wall, where's the exit/warp?"
   *Biggest cost by a landslide; it BROKE the Gold run (~250 of ~420 turns hunting a staircase/door it
   couldn't perceive).* Red & Metroid hit the same wall (rock fences, staircases). Workarounds: RAM coords,
   brute-force collision sweeps, brightness-flash warp detection, BFS floods, (wrong) genre knowledge.
   → ADR-002: **blob-segment + ego-motion + track + recognition-hash** (door/stair/grass vs wall).

2. **Action→effect feedback** — "did my last action do anything / did I move / am I stuck?"
   Reached for constantly (agents acted in blind batches, diagnosed after). Workarounds: RAM-coord equality,
   per-frame pixel-diff, side-by-side PNGs, "if stuck, jump/random." → **change/`whats_changed` + consequence + ego-motion**.

3. **Mode / context detection** — "overworld / battle / menu / dialogue / fade — is input pending?"
   *Highest-frequency micro-cost* (Red: ~25/60 battle turns were press-A→Read-PNG→classify). Also broke Gold
   (couldn't tell "Elm still talking" from "free to move"). Workarounds: repeated PNG classification by eye,
   RAM battle-flag `0xD057`, "coord frozen?" as a dialogue proxy. → **modality/context-detect + recognition-hash + read_text**.

4. **HUD scalar reading** — "my HP / energy / vitality, did it drop?" The nominal task; never clean at 160×144.
   Kirby got the vitality-circle crop wrong 3× before counting "●●●●●● → ●●●● = dropped 2." Red/Metroid read
   the digits by eye (which is how the wrong RAM oracles were caught). → **glyph-read/`read_text`** (digits) + **blob-segment** (bars/pips).

5. **Entity detection** — "where's the enemy / item / NPC?" (needed to *cause* damage + navigate). Inferred
   from raw pixel clusters + genre priors. → **blob-segment + track + recognition-hash**.

6. **Text reading** — OCR dialogue/menus; a hard blocker in Gold (scrolling-vs-done). → **read_text + modality**.

## Impact
- **Self-localization (#1) cost the most** — consumed the majority of the Gold run and caused the only failed
  run (never reached a battle).
- **Mode/context (#3) was the highest-frequency** micro-cost across both Pokémon sequences.
- **HUD reading (#4)** was cheap-but-fiddly (Kirby's 3 failed crops).

## Bottom line — reorder the roadmap
The agents were blindest on **walkability/self-localization** and **mode/context detection** — NOT the
"read my HP" task we'd been focused on. Prioritize **blob-segment + walkability/traversability**,
**modality/context-detect** (overworld/menu/dialogue/battle/fade + "input pending"), and
**change/consequence** (did my action move me / advance the screen) *before* the scalar readers
(`read_text` OCR for HUD/dialogue; bar/pip segmentation for health).

**What we already have (partial):** `core/localize.py` AvatarLocalizer (#1, fixed-camera), `core/modality.py`
detect_modality (#3), `core/egomotion.py` best_shift (#1/#2), `grid_max_change` (#2), RapidOCR read_text (#4/#6).
**Genuinely missing:** blob-segment, persistence/track, walkability-from-pixels, the general consequence detector.

## Dev-tooling (NOT an in-game primitive, but recurs in every transcript)
The RAM-oracle hunt — find the byte mirroring an on-screen scalar — burned dozens of turns each run, with
real bugs caught: Metroid's stated `0xDA13` was wrong (energy is BCD `0xD051`); Red's `0xD16C` roster-HP
lags/glitches (true in-battle HP `0xD015`); Gold's HP unreadable via `pb.memory[]` (GBC bank-switched WRAM).
Worth a small helper: feed it frames + the visually-read scalar trajectory; it scans WRAM columns across
u8 / u16-BE / u16-LE / BCD and returns matching address + encoding. Belongs in the dev/validation harness.
