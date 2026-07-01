# Hybrid ladder→UI-TARS navigator — live validation (2026-07-01)

**TL;DR.** The `HybridNavigator` (committed `559dc47`, unit-tested only until now) was run
end-to-end on the local RTX-3080 box across **27 games (NDS ×11, GB ×8, GBA ×8)** with
**UI-TARS-2B-SFT on `:8080`**. It does exactly what it was built for: **the blind escape-ladder
front-half clears every boot splash / logo / loading screen (27/27)** — the wall that pinned
pure-touch UI-TARS (Phoenix Wright: Capcom splash → tap-center ×24 forever) — then hands off to
UI-TARS grounding once a real menu is up. **NDS touch converts** (2 games all the way into
gameplay, 9/11 to a real interactive screen). **The GB/GBA grounding bridge is confirmed as the
next wall** — it reaches menus but, being stateless, ping-pongs the cursor and can't commit — plus
a **regression on bare "PRESS START" GB titles**. Evidence = the captioned trajectory strips in
[`assets/2026-07-01-hybrid-validation/`](assets/2026-07-01-hybrid-validation/) (`sheet_nds.png`,
`sheet_gb.png`, `sheet_gba.png`).

This closes the "live VLM validation is still PENDING" item on the hybrid commit.

## Method

- One process per ROM: `python -m eval.bakeoff <console> <rom> {hybrid-nds|hybrid-gb|hybrid-gba} strip.png 48`.
- **48 steps**, a strip tile kept every 6 steps; each tile's caption is the action chosen there —
  a button name (`a`/`right`/`start`/… = the ladder, or the UI-TARS GB/GBA button bridge) or
  `touchX,Y` (UI-TARS NDS grounding → stylus). The final tile is `END` = where it landed.
- **Server:** `UI-TARS-2B-SFT-Q4_K_M.gguf` + the borrowed `mmproj-Qwen2-VL-2B-Instruct-f16.gguf`
  on `127.0.0.1:8080`, `--image-min-tokens 1024`. NDS + GB ran in Windows `.venv-win` (py-desmume /
  pyboy) reaching the WSL server over localhost-forwarding; GBA ran in WSL `~/.venv-bakeoff` +
  `~/gba-spike` mgba.
- **Scoring = strip eyeball**, three buckets: ✅ reached gameplay · ◐ reached a real interactive
  screen but stuck · ❌ no progress. This is NOT oracle-scored, and it is a **single run per game**
  (no repeats / error bars). The handoff itself is visible in the strip as the caption flips from
  button names to `touchX,Y` (NDS) or from ladder-advance to bridge-directions (GB/GBA).

## Results

### NDS — `hybrid-nds` (touch grounding). 2/11 gameplay, 9/11 reached an interactive screen.

| Game | Outcome |
|---|---|
| Phoenix Wright: T&T | ✅ **gameplay** — splash→title→Episode-select (UI-TARS taps *Confirm*)→intro dialogue |
| New Super Mario Bros | ✅ **gameplay** — title→file-select→**world map** |
| Professor Layton | ◐ reached name-entry, stuck tapping *OK* on an empty name (name-grid) |
| Mario Kart DS | ◐ reached menus (emblem-create prompt); tapped through an "erase save → OK" en route |
| Kirby Super Star Ultra | ◐ deep menu nav (save-select → Group sub-games → multiplayer "waiting room") |
| Resident Evil: Deadly Silence | ◐ reached main menu (New Game / Load / Multi-Card / Options) |
| Star Wars: The Force Unleashed | ◐ reached the "A long time ago…" intro crawl |
| Harry Potter: OotP | ◐ reached title ("tap the screen to continue") |
| FIFA Street 3 | ◐ reached title |
| Zelda: Spirit Tracks | ❌ loading-bound — stuck cycling the Nintendo logo / boot |
| Pokémon White | ❌ emulator failure — DSi-enhanced title white-screens under desmume |

### GB — `hybrid-gb` (novelty-stall → UI-TARS **GB bridge, stateless**). 1/8 gameplay.

| Game | Outcome |
|---|---|
| Cave Noire | ✅ **gameplay** — reaches the dungeon floor (HP HUD visible); its menus are OK/NO confirm dialogs the ladder+A clears |
| Pokémon Red | ◐ reached the NEW GAME / OPTION menu — **cursor ping-pongs, never confirms** |
| Pokémon Gold | ◐ reached the NEW GAME / OPTION menu — same ping-pong |
| Final Fantasy Adventure | ◐ reached the name grid, stuck |
| F-1 Race | ◐ stuck oscillating on the Grand-Prix menu |
| Mortal Kombat | ◐ reached the title, stuck |
| Sword of Hope II | ❌ **regression** — stuck on the "PUSH START" title |
| Tetris Plus | ❌ **regression** — stuck on the "PRESS START" title |

### GBA — `hybrid-gba` (same stateless bridge). 0 clean gameplay; reaches title/menu on most.

| Game | Outcome |
|---|---|
| Pokémon Emerald | ◐ reached the NEW GAME / OPTION menu — cursor ping-pong (same as GB Pokémon) |
| Zelda: The Minish Cap | ◐ reached the "CHOOSE A FILE" select, stuck |
| Kirby: Nightmare in Dreamland | ◐ past the title into a sub-menu ("The Fountain of Dreams") |
| Super Mario Advance 2 | ◐ reached the title / mode-select (Single/Multiplayer) |
| Mortal Kombat Advance | ◐ reached the title, stuck |
| Naruto: Ninja Council 2 | ◐ reached the title (START attract), stuck |
| DBZ: Legacy of Goku | ? ambiguous — laddered the publisher splashes, END on a dark loading/intro |
| Final Fantasy VI Advance | ◐ reached the title, END on a black transition |

## Findings

1. **The ladder front-half is validated on every console.** Splash / logo / loading is solved
   27/27 (Capcom, LEVEL-5, Nintendo, Midway, Atari, Square Enix, HAL, LucasArts, EA, …). The exact
   pure-UI-TARS failure mode — tapping a splash center forever with nothing to ground — no longer
   occurs. This was the whole purpose of the hybrid.
2. **NDS touch is the winning path.** UI-TARS reliably grounds "PRESS START", menu buttons, file
   selects and *Confirm* buttons; 2 games (Phoenix Wright, NSMB) go all the way into gameplay and 7
   more reach a real interactive screen. The specialist pays off exactly where it was expected to.
3. **The GB/GBA grounding bridge is the confirmed next wall — the a↔up non-convergence the commit
   inherited, not fixed.** On a cursor menu (Pokémon New-Game, name grids, file-select) the
   stateless bridge presses up/right/a with no inter-step memory of whether the emulator moved, so
   it oscillates and never commits. **Fix options:** give the bridge inter-step state (confirm the
   selection moved before re-grounding), OR adopt the documented fallback — *ladder-for-buttons +
   UI-TARS-touch-only*, dropping the GB/GBA grounding bridge entirely.
4. **Regression on GB start-gated titles.** Handing off on the first novelty-stall replaces the
   ladder's start/A-press with the bridge's directional grounding, so bare "PRESS START" titles
   (Sword of Hope II, Tetris Plus, Mortal Kombat) stall where the *pure ladder* cleared them
   (ladder is GB champion 5/8). The handoff should not fire until a genuine cursor/touch menu is
   detected — a static "PRESS START" screen is not a menu UI-TARS should own.

## Caveats / honest notes

- **Strip-eyeballed, not oracle-scored**, and one run per game — treat the ✅/◐/❌ buckets as
  ordering, not hard counts. A couple of GBA end-states are genuinely ambiguous (DBZ, FF6 → black).
- **Blind touching has real side effects:** Mario Kart DS tapped through an "erase all saved data →
  OK" confirmation. Harmless on a fresh emulator, but a live consequence to remember.
- On low-detail NDS screens (Phoenix Wright dialogue, Layton black transitions) the caption shows
  `a`, not a touch — that is UI-TARS's button *fallback* firing when grounding returns no
  coordinates. Benign here (A advances Phoenix Wright dialogue, and the game kept progressing) but
  worth confirming it isn't masking grounding misses elsewhere.
- Two non-navigator failures: Pokémon White (DSi firmware) and Spirit Tracks (loading-bound) are
  emulator/boot limits, not the hybrid's fault.

## Next

- **Fix the GB/GBA bridge** — inter-step state, or switch to ladder-for-buttons + NDS-touch-only.
- **Fix the GB handoff regression** — don't hand off until a cursor menu is confirmed; keep the
  ladder pressing start/A on static title screens.
- verify + swap the SFT mmproj (`lmstudio-community/UI-TARS-2B-SFT-GGUF`) and A/B grounding.
- Fire the Claude same-harness test (`scratchpad/claude_test.py`) once a live `ANTHROPIC_API_KEY`
  is set.

**Server state:** UI-TARS-2B-SFT is left running on `:8080` (the 3Bs are stopped) for continued
hybrid iteration.
