# Live run #13 — battle auto-advance, validated (2026-06-20)

_Companion to the runs #6b–#12 battle arc (see `LEARNINGS.md`). Run #12 **won** the rival battle but
spent ~68 of 73 LLM wakes **inside** the fight — woken on every frame, even pure narration it can't act
on. That violated the project's **cheap-first** law. Run #13 validates the harness-only **battle
auto-advance** built this session._

**TL;DR — the cheap-first win lands, and the win behavior is unchanged.** With battle auto-advance, the
agent **won the rival battle with 18 battle wakes vs run #12's ~68 (~3.8× cheaper)**, picking the
damaging move every turn (SCRATCH ×12, GROWL ×0) with correct grounding (Charmander vs Squirtle, 0
confabulation). Verified per-step against the RAM oracle. Total **22 wakes / 400 steps (5.5%)**;
post-battle exploration cost only **4 wakes**. ~$0.15–0.2, 0 errors. The feature works exactly as
designed: **the expensive model is woken only at the two genuine decisions (the action menu and the
move list); the narration in between is advanced for free.**

---

## 1. What we were trying to do

Run #12 closed the battle-*capability* gap (the agent fights and wins) but exposed a battle-*cost* gap:
it was woken every step of the fight. The fix is the same move the project made for confabulation and
navigation — **decode the state finely enough that the cheap autopilot can handle the routine part** —
applied now to cost:

> In a battle, auto-advance the **narration** for free (press A) and wake the LLM **only** at the
> action menu (FIGHT/PKMN/ITEM/RUN) and the move list. Does the wake count drop sharply **without
> breaking the win**?

Constraints honored (the north star): screen-only perception (the sub-screen classifier is pixels-only;
RAM stays a non-leaking oracle), the same decoupled brain, cheap-by-default.

## 2. The mechanism (harness-only; 158 tests, $0 to validate)

- **`textbox.battle_subscreen(frame, table)`** (pixels only) splits a SETTLED battle frame into
  `battle_text` (advanceable narration) vs `battle_menu` (the action/move menu — a decision). It is
  **positive-ID-for-advance, default-to-wake**: returns `battle_text` only on a positive narration read
  (≥4 real glyphs, no reserved action word, and — checked **first** — `decode_move_menu` empty). The
  catastrophic case (mis-reading the move menu → auto-A picks GROWL, the run #6b/#11 failure) is
  structurally prevented: the move-menu detector runs before the narration check, and any ambiguity
  wakes.
- **The perceiver** emits the finer `context` (`battle_text` vs `battle`); only `perceive()` changes —
  `detect_mode` still returns `"battle"`, so `_settle_if_battle` keeps collapsing animations.
- **`HybridBrain`'s** existing dialog auto-advance branch is widened by one predicate to also advance
  `battle_text`. Plus a generic `_ADVANCE_FUSE=50` (no infinite free loop) and a **battle-aware
  watchdog in both drivers** (`play_loop.py` + `play_pokemon.py`): suppress `--stuck-steps` while
  `in_battle`, since a now-mostly-free fight would otherwise trip the halt mid-battle.

Validated free on the 8 real `runs/battle` captures (clean split: narration → `battle_text`; both menus
→ `battle_menu`) + 15 synthetic tests.

## 3. Method

**Clean start (mandatory, archived first):** `reset_aria_memory.py --yes` → archived prior memory to
`aria_memory_archives/iter-013_2026-06-20.zip`, wiped the run-generated experience (journal,
`earlier_today.json`, `usage.jsonl`), kept the seed + caches. aria-app/litellm up with
`ARIA_DATA_DIR=pokemon-red-data` (mount verified).

**The run (headless, recorded, guarded) — run #12's *winning* config + the auto-advance code:**
```
play_pokemon.py --brain hybrid --backend aria --perception --no-vision \
    --load-state rival_battle.state --steps 400 --max-llm-calls 60 --stuck-steps 80 \
    --out runs/run13 --record runs/run13.mp4 --save-state runs/run13_end.state
```
`--no-vision` (text-only) is the run #10–#12 cure for battle-sprite confabulation; the only *new* thing
vs run #12 is battle auto-advance. Started from the `rival_battle.state` fixture (agent parked at the
rival battle) to isolate the battle from flaky overworld nav.

## 4. Results (verified against the RAM oracle, not the model's narration)

| Metric | Run #12 | **Run #13** |
| --- | --- | --- |
| **Won the rival battle?** | yes | **YES** (`in_battle` 2→0 **sustained** at step 72) |
| **Battle wakes** (the headline) | ~68 | **18** (≈ **3.8× cheaper**) |
| Wakes per turn | every frame | **2** (action menu + move menu) |
| Battle narration auto-advanced (free) | 0 | **54** |
| Move choice | SCRATCH (won) | **SCRATCH ×12, GROWL ×0** |
| Grounding | correct (text-only) | correct — Charmander vs Squirtle, **0 confab** |
| Total wakes / steps | ~73 / ~230 | **22 / 400 (5.5%)** |
| Post-battle nav wakes | n/a (halted) | **4** over ~328 overworld steps |
| Maps reached (oracle) | 40→0→37→39 | **40→0→37,38,39** (left lab, explored Pallet) |
| Errors / 400s | 0 | **0** (aria credits held) |
| Cost | ~$0.5 | **~$0.15–0.2** |

**Battle wake pattern (oracle steps 0–71, `in_battle==2`):** `[0,1,2]` (enter + advance intro) then the
turn pairs `[9,10] [15,16] [21,22] [27,28] [35,36] [43,44] [49,50]` (action menu, then move menu) and
`[62]` (the faint/level-up text). Seven attacking turns, each costing exactly **2 wakes**, with ~6
narration frames auto-advanced free between them. At step 62: *"Battle ended; Charmander defeated
Squirtle and leveled up."* `in_battle` drops to 0 at step 72 and stays 0.

## 5. What worked, and why

- **Auto-advance is the cost win it was designed to be, with no behavioral regression.** The win
  behavior from run #12 is intact — every move-menu wake read *"SCRATCH is highlighted and deals damage
  → confirm"* and chose the damaging move; the type-disadvantage grind still resolved in the agent's
  favor. The only change is that the ~54 narration frames between decisions are now free.
- **The safety asymmetry held in the wild.** Across the whole fight, not one move menu was
  mis-advanced (GROWL ×0). The move-menu-first ordering + default-to-wake did its job on live pixels.
- **The bottleneck genuinely moved off the battle.** Post-battle, the free autopilot drove the agent
  **out of the lab and around Pallet** (maps 40→0,37,38,39) for just 4 wakes — the residual Phase-B
  lab-exit gap that bit run #12 didn't bite here.
- **The battle-aware watchdog was necessary and correct.** With battle steps now mostly free, the
  fight ran 72 steps with no oracle fingerprint progress; the `in_battle` suppression kept the watchdog
  from halting mid-battle (it would have, at step 80, without the fix).

## 6. What this confirms

1. **The cheap-first thesis, end-to-end:** decode the state finely enough and the expensive model is
   woken only at genuine decisions; the rest is free. Battle cost dropped ~3.8× with zero capability
   loss — the same decouple-and-cheapen pattern as GOTO (navigation) and dialog auto-advance.
2. **Battle is now the cleanest skill-compilation target in the game.** The fight was **7 nearly
   identical FIGHT→SCRATCH turns** — a System-2 deliberation that repeats. That is exactly what the
   **learned blind-execute battle policy** (System-2→System-1, INSIGHTS §6) should compile: deliberate
   once, distill the policy, run it blindly over the now-decoded state, re-wake only on novelty.

## 7. Next steps

- **Learned blind-execute battle policy** (the next rung): cache/compile the menu decisions over the
  decoded battle state, re-wake on novelty (a new foe, low HP, a status). Run #13's identical turns are
  the proof it's compressible.
- **Lab-exit / Pallet navigation** (the residual Phase-B gap): run #13 happened to clear it, but it's
  not yet robust — tighten it for a full Pallet→Route 1→Viridian run.
- Then the credit-gated **gating-probe** verdict and continued play past the rival.

---

_Artifacts: video `runs/run13.mp4`; oracle `runs/run13/oracle.jsonl`; final state
`runs/run13_end.state`; archived pre-wipe memory `aria_memory_archives/iter-013_2026-06-20.zip`. Spend
~$0.15–0.2 (22 wakes; 0 errors). Code on branch `feat/battle-auto-advance`._
