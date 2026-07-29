# Scoping: EX02 single-item capability probe — Kirby's Dream Land, clear Stage 3

**Date:** 2026-07-29 · **Status:** scoping only, $0 spent, nothing launched · **Base:** `origin/main` `f3a26fd`

**This is NOT a Gate-0 attempt and NOT a graduation-exam attempt.** The exam's overall pass bar is unset
(`reports/2026-07-22-graduation-exam-v1-definition.md` §3, "**OPEN — pass bar not yet set**") and that
document's own rule forbids attempting the battery before David's explicit freeze. This is one
per-item capability probe against a bar that is already frozen *in code*.

---

## ⛔ RECOMMENDATION UP FRONT: do not run this probe as scoped

The bar requires the agent to reach stage index `3`. **No banked run has ever cleared even index `0`.**

`runs/brain_kirby_longhaul/` (2026-07-04) is the same world, a strictly *easier* brief ("clear stages,
beat the bosses, get as far as you can"), with the skill library enabled (`KIRBY_SKILLS=1`,
`define_skill`/`run_skill`), and it spent **$42.98 over 316 turns and 3,128 s** — and ended
**mid-Green-Greens after a GAME OVER at step 517**. Zero stages cleared. Index `0` never left.

This probe asks for three stage clears (Green Greens → Castle Lololo → Float Islands → *into* Bubbly
Clouds) on a budget framed as "$5". A FAIL is near-certain, would cost far more than $5 (§4), and
would re-measure exactly what longhaul already measured. See §5 for the one variant that is worth
running, which costs $0 to set up.

**→ §6 (added 2026-07-29, same day) IS that re-scope, approved by David: the Float-Islands capture
procedure (verified live) + launch-ready assets, one paid command away.**

---

## 1. Rig verification — executed today at $0

Docker daemon up (29.4.2); `gb-mcp-world:latest` built 2026-07-28 03:25:34. **Not stale**: no commit
between `609ab8a` (last `world_mcp.py` change) and `f3a26fd` touches `core/`, `games/`, or
`world_mcp.py`. All checks below mounted `runs/` **read-only** and wrote to a scratch dir, so the
append-only law was structurally enforced, not merely observed.

| # | Check | Result |
|---|---|---|
| 1 | Kirby world starts, MCP tools respond | ✅ 9 tools: `explore, goto, observe, press_button, press_sequence, read_region, remember, wait, whats_changed` |
| 2 | Fresh run emits `stage`/`hp`, not `c1..c5` | ✅ `{"hp": 6, "stage": 0}` on every row; `hp` fell 6→5 on a real contact hit |
| 3 | Banked human run still refused | ✅ `FAIL_CAPABILITY` / `kirby_stage3_missing_or_invalid_oracle_field` — its rows are still `c1..c5`/`band` |
| 4 | Scorer discriminates | ✅ 18 synthetic traces, every verdict as designed (below) |

**Scorer discrimination** — `eval/score_exam_kirby_stage3.py`, 18 traces, all correct:
PASS on clean progression, on overshoot to `4`, on clear-then-die-to-title (`3→0`), on a death sampled
inside the streak, on an isolated all-zero glitch row spliced out, and on a Float-Islands start.
FAIL/refuse on: reached `2` only, lone transient `3`, byte stuck at `3` with no progression, `>=3`
only while `hp=0`, never left Green Greens, a *multi-row* zero stretch correctly breaking the streak,
plus `bool` hp, `float` stage, out-of-range stage, `c1..c5` columns, and malformed JSON
(`INSUFFICIENT_DATA`).

**Also verified free, offline:** all 14 banked Kirby savestates boot at `stage=0` (Green Greens).
**There is no Float Islands savestate.** This is the fact that sets the price.

## 2. CGB hazard — CLEARED, verified from the ROM and the emulator

Kirby's Dream Land runs in **DMG mode**. The Red corruption mechanism cannot occur here.

| | Kirby's Dream Land | `roms/PokemonRed.gb` (the colorization romhack) |
|---|---|---|
| header `0x143` | `0x44` | `0xC0` |
| why | title `KIRBY DREAM LAND` is exactly 16 bytes filling `0x134-0x143`; `0x44` is the `'D'` of `LAND` — **title overflow, not a CGB flag** | genuine CGB-ONLY flag |
| `SVBK` (`0xFF70`) after 600 frames | `0x00` | `0x02` — actively bank-switched |
| `memory[bank, 0xD03B]` for banks 1-7 | **`PyBoyInvalidInputException`** — the banks do not exist | all 8 readable |

Since WRAM `0xD000-0xDFFF` is unbanked here, the flat read `self._pyboy.memory[addr]`
(`core/gb_emulator.py:126`) is unambiguous. `0xD03B`/`0xD086` cannot misread from a wrong bank.
**No Red-style corruption filter is needed, and the proposed `memory[1, addr]` fix would *raise* on
this world** — which is exactly the DMG guard behaviour that fix was specified to have.

---

## 3. PRE-REGISTRATION (the one page)

**Task ID:** EX02. **World:** `kirby_dreamland`. **One attempt. No retries.** A completed run's verdict
is banked whatever it says; INSUFFICIENT_DATA is a verdict. Relaunch only on infra death before ~10
decisions (MCP never connected, container crash, 429).

**Bar — frozen in code, cited not restated:** `eval/score_exam_kirby_stage3.py`,
`STAGE_INDEX_TARGET = 3`, `_MIN_CONSECUTIVE_ROWS = 2`, `_MAX_STAGE_INDEX = 4`, predicate
`_kirby_stage3_success`. Scored offline from `<out>/oracle.jsonl` only. No prose restatement of the
predicate appears in this document, deliberately — it would drift.

**Task brief — the agent is told exactly this, and nothing about the bar:**

> Clear Stage 3.

That is EX02's instruction verbatim from the exam definition (§EX02, line 71). The run brief
(`CLAUDE.md`) may carry world mechanics and tool usage — float, inhale, contact damage — but **must
not** mention `0xD03B`, the word "oracle", stage *indices*, a row count, or the target value `3`.
⚠ Whoever writes it must not copy `world_mcp.py:251` ("confirmed reading 4 at Stage 4" — it reads
`3`) or `:255` ("Only `>= 2` is meaningful") — **both comments are known-wrong** and `:255` is the
line that seeded an earlier wrong-bar near-miss. Note the naming trap: Stage 3 is *Float Islands*,
which is stage **index 2**; clearing it means the counter reaching **3**.

**Caps, and what happens at each:**

| Cap | Value | On hit |
|---|---|---|
| Model turns | `--max-turns N` | run ends, `subtype=error_max_turns`; score whatever `oracle.jsonl` holds |
| Wall clock | `timeout <s>` around `claude -p` | SIGTERM, exit 124; score whatever exists |
| Spend | **none — no live kill switch exists on this path** | see §4 |

⚠ `LiveCreditGuard(limit=250)` is constructed **only** in `tools/gate0_appserver_arm.py:1517` and
`tools/gate0_appserver_launch.py:670`. The `claude -p` harness this probe uses does not import it.
`--max-turns` is therefore the *only* real budget control, and it is a turn count, not a dollar cap.

**Artifacts:** `runs/probe_ex02_kirby_stage3_2026-07-29/` (launcher: `.mcp.json`, `CLAUDE.md`,
`run.sh`; outputs: `world/`, `transcript.jsonl`, `run.exit`). **Not** under `runs/gate0_*`. Nothing in
this probe touches the frozen Gate-0 pre-registration and it consumes **no deviation slot** — it is
not a Gate-0 deviation.

**What a PASS licenses:** that this agent cleared Float Islands from the given start state, once —
EX02's *item* bar, by the frozen scorer.
**What a PASS does NOT license:** (a) any statement about the graduation exam, whose overall pass bar
is unset; (b) discharge of the **still-open Stage-3 → Stage-4 bound**; (c) a general Kirby competence
claim from n=1.

**Three facts recorded before the run:**

1. **The human baseline FAILS this bar.** David's banked run `runs/2026-07-28_kirby_stage3_human/`
   reaches `c1` = **2** (Float Islands) and no further — verified today, `c1` takes only `{1,2}` across
   all 1,128 rows. It also *starts* at `1` (Castle Lololo), so it prices one stage, not three. There is
   no human demonstration of this bar in the repo.
2. **A PASS would be the first `2 → 3` increment ever observed in natural play.** Every `3` on record
   was produced by *writing* memory; the only game-made increment ever seen is `1 → 2`, once, in that
   human run. Such a run is worth inspecting on its own merits — and it is **NOT** a discharge of the
   Stage-3 → Stage-4 bound, which asks for that transition with no memory write anywhere in the run.
3. **Wiring hazard: `0` is overloaded.** `0` is Green Greens, *and* the uninitialised cold-boot value,
   *and* the post-game-over title screen — confirmed today: a cold-booted ROM reads `0xD03B`=0,
   `0xD086`=0. No predicate keyed on `== 0` is safe. The frozen scorer already avoids this.

---

## 4. Price

**Reference class** — `claude -p` on `kirby_dreamland` (the only apples-to-apples data):

| Run | Cost | Turns | $/turn | Outcome |
|---|---|---|---|---|
| `brain_kirby_v3` | $4.3176 | 87 | 0.0496 | entity gate, fixed early screen |
| `brain_kirby_v3_1` | $5.1931 | 74 | 0.0702 | entity gate, fixed early screen |
| `brain_kirby_entity/run3_walled` | $7.2489 | 112 | 0.0647 | entity gate |
| **`brain_kirby_longhaul`** | **$42.9838** | **316** | **0.1360** | **end-to-end play; 0 stages cleared** |

Turns ≈ tool calls (v3_1: 74 turns / 71 calls). $/turn **grows with context** — 0.05→0.07 at ~100
turns, 0.136 at 316.

⚠ The Red Gate-0 receipt offered as an anchor ($0.41589 / 142 actions / 127.75 s) is **not a
comparable**: `runs/gate0_paid/red/run-receipt.json` records `"model": "gpt-5.6-sol"` — it is a Codex
app-server run, not `claude -p`, and its own receipt says `"audit_overall": "CONSTANCY_BREACH"`. Do
not price a Claude Kirby run off it.

**Frame economics, measured today** (one oracle row per tool call in every case):
`press_button` = **24 frames**; `press_sequence` (max 16 buttons) = **384 frames**; `wait` (max 600) =
**600 frames** but buys no input.

**Game time required.** The human needed **9,888 frames (165 s) for Castle Lololo alone**. Three
stages ≈ **30,000 frames**, and that is *competent human* pace with no deaths.

**Turn estimate, from a cold start at Green Greens:**
- Floor, every press perfect, no deaths, all `press_button`: 30,000 / 24 ≈ **1,250 turns**.
- With deaths and retries (longhaul died out inside stage 0): **2,500–5,000 turns**.
- Heavy `press_sequence` batching could cut this ~10x on paper (30,000/384 ≈ 78 calls) but that is
  *blind* 16-press batching in a reactive platformer — longhaul had this tool and still failed.

**Cost:** at $0.14–0.20/turn (context growth past 300 turns), **$175 floor; $350–1,000 realistic.**
The exam document's own quota for EX02 — **"~$4, ~120 decisions"** — is low by roughly an order of
magnitude. 120 decisions buys 2,880 frames = 48 s of game time; Castle Lololo alone needs 165 s.

**Recommended cap — if David runs it anyway:** `--max-turns 150` and `timeout 2400`, expected
**$10–15**. Justification: it is the largest budget that stays a *probe*. It cannot plausibly reach the
bar, so do not sell it as an EX02 attempt — see §5. Do **not** authorise an open-ended `--max-turns
600`-class run at this bar; longhaul already bought that experiment and the answer was zero stages.

---

## 5. The single sharpest reason this probe would be uninterpretable

**A FAIL cannot distinguish "cannot clear Float Islands" from "ran out of budget three stages
earlier" — and every prior on this world says the second is what will happen.** The scorer returns
`kirby_stage3_never_cleared_stage_3` for both. That verdict string would be logged as a *capability*
result for a bar the run never got within two stages of testing, and EX02 would be marked attempted
and failed on evidence that says nothing about Float Islands.

A second, quieter version of the same problem: **a wiring break also returns `FAIL_CAPABILITY`.** The
banked human run scores `FAIL_CAPABILITY` / `missing_or_invalid_oracle_field` — the scorer refuses
correctly, but the *verdict label* says the agent failed when in fact the columns were wrong. If the
paid run's oracle shape breaks, the artifact reads as incapacity. Worth a follow-up: that refusal
class arguably belongs under `INSUFFICIENT_DATA`, not `FAIL_CAPABILITY`.

### The variant that is worth running, and it costs $0 to set up

**Start the run at Float Islands.** Then the probe measures the thing EX02 actually asks about, at
roughly one third the budget, **with no change to the frozen scorer** — verified today: a synthetic
trace booting at `stage=2` and reaching `3` returns **PASS**, because `2` already satisfies the
scorer's "an earlier row below the bar" clause.

What it needs: David plays Kirby to the start of Float Islands and saves a state — free, human,
offline, the same `record.py --mode human` rig that produced the banked capture. That savestate does
not exist today (all 14 banked states are `stage=0`).

This also buys the thing the project has actually been missing: if the agent clears Float Islands from
that state, the run contains a genuine **`2 → 3` increment with no memory write** — the exact evidence
the still-open Stage-3 → Stage-4 bound asks for.

**My recommendation:** capture the Float Islands savestate first ($0), then re-scope. Running the
cold-start version now buys a predictable FAIL at 20–200x the stated budget.

---

# §6 AMENDMENT (2026-07-29, later the same day): the float-start variant, launch-ready

David approved the float-start re-scope and the probe spend at the §4 cap (~$10–15). This section
adds (a) the verified capture procedure for the Float Islands savestate, and (b) the launch assets,
every command executed today up to — and only up to — the paid line. **$0 spent.** Assets live in
`reports/probes/2026-07-29-kirby-ex02-floatstart/launcher/` (`CLAUDE.md` brief, `mcp.json`
template, `run.sh`, `preflight.sh`). Nothing lands under `runs/` until launch step 1 in §6.4.

## 6.1 Capture procedure (David, ~20 min, desktop)

⚠ **Do not run `record.py` from this checkout as it sits.** The main checkout is currently on
branch `fix/miniwob-key-name-press`, whose `record.py` is 25 lines behind `origin/main` and still
has the pre-fix checkpoint path — **pressing C crashes it** (reproduced live today:
`FileNotFoundError: runs\capcheck\checkpoint_01.state`). The command in step 2 therefore runs the
#199 worktree's copy, byte-identical to `origin/main`. Once a checkout is back on current `main`,
plain `record.py` is fine.

1. On the desktop, open PowerShell:
   `cd E:\AI_Personas\10_pokemon_and_chess_and_office\ai-pokemon-red`
   `$env:UV_PROJECT_ENVIRONMENT=".venv-win"; $env:UV_NATIVE_TLS="true"`
2. Launch the recorder (one line):
   `uv run --frozen python E:\AI_Personas\10_pokemon_and_chess_and_office\wt-kirby-probe\record.py --rom "roms\Kirby's Dream Land (USA, Europe).gb" --name kirby_floatislands_human --mode human --watch "hp=0xD086,stage=0xD03B"`
   A PyBoy window opens at the Kirby title screen. Output dir (fresh dated dir = allowed append):
   `runs\<today>_kirby_floatislands_human\`. Add `--sound` for audio if you want it (untested here).
3. Controls: **WASD** = move, **J** = A (jump/float), **K** = B (inhale/spit), **Enter** = Start.
   Press Enter to start the game.
4. Play Green Greens; beat Whispy Woods. At the **start of Castle Lololo** press **C** once —
   insurance checkpoint; the console prints `[checkpoint -> ...checkpoint_01.state]`.
5. Play Castle Lololo; beat Lololo & Lalala.
6. The moment **Float Islands begins** — Kirby standing, under your control, vitality bar full —
   press **C**. Play a few seconds more and press **C** again at another clean spot (backup).
7. Press **ESC** to quit; the console prints `saved N steps`.
8. Verify each Float Islands candidate (swap the date and `NN`); want **`stage=2 hp=6`**
   (hp 5 acceptable; `stage≠2` or `hp=0` = wrong moment, try the other checkpoint):
   `uv run --frozen python -c "import sys; from pyboy import PyBoy; pb = PyBoy(sys.argv[1], window='null'); pb.load_state(open(sys.argv[2], 'rb')); pb.tick(2); print('stage=%d hp=%d' % (pb.memory[0xD03B], pb.memory[0xD086])); pb.stop(save=False)" "roms\Kirby's Dream Land (USA, Europe).gb" "runs\2026-XX-XX_kirby_floatislands_human\checkpoint_NN.state"`
9. If no candidate passes: relaunch the step-2 command with
   `--load-state runs\<dir>\checkpoint_01.state` appended — it appends to the same dir and the
   checkpoint numbering continues — and recapture from Castle Lololo.
10. Report the passing checkpoint's path plus its printed `stage=/hp=` line. That exact file
    becomes the probe's `--init-state`; do not rename or move it.

## 6.2 What was executed today to verify §6.1 (all $0, scratch dirs, nothing in `runs/`)

| Check | Receipt |
|---|---|
| `uv run --frozen python record.py --help` from the main checkout | clean, full flag list |
| Pre-fix `record.py` (main checkout's branch) with a **real C keypress** in a live window | **CRASHED** — `FileNotFoundError: runs\capcheck\checkpoint_01.state` — this is why step 2 pins the worktree copy |
| Fixed (`origin/main`) `record.py`, live window, real keypresses | C → `checkpoint_01.state` (143,103 B); C again → `checkpoint_02.state`; ESC → clean exit, `saved 210 steps` |
| `meta.json` watch persistence (the PR #180-era fix) | `"watch": {"hp": "0xD086", "stage": "0xD03B"}` + `watch_arg` present |
| `oracle.jsonl` rows | `{"step": 0, ..., "watch": {"hp": 0, "stage": 0}}` (title screen — correct cold-boot signature) |
| Step-8 verify one-liner, byte-for-byte | fresh checkpoint → `stage=0 hp=0`; banked in-play `runs/kirby_probe/kirby_stage1.state` → `stage=0 hp=6` |

The step-2 command's three ingredients were each verified from David's exact CWD (env resolution +
relative ROM path from the main checkout; worktree `record.py` + hotkeys + watch from a scratch
CWD); only their composition was not run as one line, because that would have written a throwaway
dir into `runs/`.

## 6.3 AMENDED PRE-REGISTRATION — EX02 float-start probe (supersedes §3's start state/caps/artifacts; all else carries over)

- **Start state:** David's human-captured Float Islands checkpoint (§6.1), verified `stage=2 hp>=5`
  twice — the §6.1 step-8 one-liner at capture, `preflight.sh` at launch (which also pins its
  sha256 into `preflight.ok`).
- **Bar — frozen in code, cited not restated:** `eval/score_exam_kirby_stage3.py::STAGE_INDEX_TARGET`
  (with `_MIN_CONSECUTIVE_ROWS`, `_MAX_STAGE_INDEX`, predicate `_kirby_stage3_success`). Scored
  offline from `runs/probe_ex02_kirby_stage3_floatstart/world/oracle.jsonl` only.
- **Tools:** exactly `explore, goto, observe, press_button, press_sequence, read_region, remember,
  wait, whats_changed` (9); `KIRBY_SKILLS`/`KIRBY_CLAIMS` unset. Account-B `claude -p`.
- **Brief:** Appendix A below, verbatim (= `launcher/CLAUDE.md`, the file the run copies in);
  kickoff `-p` prompt pinned inside `run.sh`. Neither mentions the oracle, RAM, addresses, stage
  indices, row counts, or the target value. The scorer reads `oracle.jsonl` only — never the
  transcript — and the brief mandates no claim shapes, so the v3.1 regex-taint class cannot occur.
- **Caps:** `--max-turns 150` (on hit: `subtype=error_max_turns`, score whatever exists);
  `timeout 2400` s (on hit: exit 124, score whatever exists). Expected **$10–15** (§4 economics).
  ⚠ **There is NO live spend kill switch on this path** — `LiveCreditGuard` is constructed only in
  `tools/gate0_appserver_arm.py:1517` and `tools/gate0_appserver_launch.py:670`; the `claude -p`
  harness never imports it. The two caps above are the ONLY bounds. Raising either = prereg
  amendment, in this file, before launch.
- **ONE attempt.** A completed run's verdict is banked whatever it says; INSUFFICIENT_DATA is a
  verdict. Relaunch only on infra death before ~10 decisions (MCP never connected, container crash,
  429) — §3's rule, unchanged. `run.sh` mechanically refuses a second launch (§6.5 F).
- **Artifacts:** `runs/probe_ex02_kirby_stage3_floatstart/` (launcher copies, `preflight.ok`,
  `world/`, `transcript.jsonl`, `run.err`, `run.exit`). Never under `runs/gate0_*`; no Gate-0
  deviation slot consumed.
- **Honesty clause 1 — what a PASS is:** the **first natural `2→3` increment ever observed**
  (every prior `3` on record was written into memory). Inspect the run — frames + oracle rows
  around the increment — before repeating the claim. It **bears on** the still-open
  Stage-3→Stage-4 bound; whether it discharges that bound is David's call on inspection, not
  automatic. It is **NOT a graduation-exam attempt**: the exam's overall pass bar is unset and its
  own rule forbids attempting the battery before David's freeze.
- **Honesty clause 2 — what a FAIL is:** from this start, `kirby_stage3_never_cleared_stage_3`
  genuinely means "could not clear Float Islands on 150 turns from its start at full vitality."
  The §5 objection (budget death two stages before the bar) does not apply. Bankable as the
  EX02-item capability read at this budget.
- **What a PASS does NOT license:** unchanged from §3 (no exam statement, no automatic bound
  discharge, no general Kirby-competence claim from n=1).

## 6.4 Launch runbook (each command below executed today except step 3's paid line)

1. **Stage the launch dir** (PowerShell; first and only write into `runs/`; swap the state path
   for David's verified checkpoint from §6.1 step 10):
   ```powershell
   $L = "E:\AI_Personas\10_pokemon_and_chess_and_office\ai-pokemon-red\runs\probe_ex02_kirby_stage3_floatstart"
   $T = "E:\AI_Personas\10_pokemon_and_chess_and_office\wt-kirby-probe\reports\probes\2026-07-29-kirby-ex02-floatstart\launcher"
   New-Item -ItemType Directory $L | Out-Null
   Copy-Item "$T\CLAUDE.md","$T\run.sh","$T\preflight.sh" $L
   (Get-Content "$T\mcp.json" -Raw).Replace("REPLACE_WITH_FLOAT_ISLANDS_STATE", "runs/2026-XX-XX_kirby_floatislands_human/checkpoint_NN.state") | Set-Content -NoNewline -Encoding ascii "$L\.mcp.json"
   ```
2. **Pre-flight, $0** (must print `PREFLIGHT: OK`; §6.5 lists what it checks):
   `wsl.exe -u nvidia -- bash -c "bash /mnt/e/AI_Personas/10_pokemon_and_chess_and_office/ai-pokemon-red/runs/probe_ex02_kirby_stage3_floatstart/preflight.sh"`
   Optional guard dry-run (also $0, must print `DRY_RUN OK`):
   `wsl.exe -u nvidia -- bash -c "EX02_DRY_RUN=1 bash /mnt/e/AI_Personas/10_pokemon_and_chess_and_office/ai-pokemon-red/runs/probe_ex02_kirby_stage3_floatstart/run.sh"`
3. **THE PAID LINE — the one command this doc exists for** (David's go; up to 40 min):
   `wsl.exe -u nvidia -- bash -c "bash /mnt/e/AI_Personas/10_pokemon_and_chess_and_office/ai-pokemon-red/runs/probe_ex02_kirby_stage3_floatstart/run.sh"`
4. Monitor, $0: `transcript.jsonl` growing; `run.err` PyBoy noise only; `world/frame_*.png` count
   rising.
5. On completion: `run.exit` (`EXIT=0`; `124` = wall timeout); last `transcript.jsonl` line is the
   `type=result` event — **report `num_turns` and `total_cost_usd` to David, always**.
6. Score offline (from a checkout carrying the frozen scorer — the #199 worktree today):
   ```powershell
   cd E:\AI_Personas\10_pokemon_and_chess_and_office\wt-kirby-probe
   $env:UV_PROJECT_ENVIRONMENT=".venv-win"; $env:UV_NATIVE_TLS="true"
   uv run --frozen python -m eval.score_exam_kirby_stage3 E:\AI_Personas\10_pokemon_and_chess_and_office\ai-pokemon-red\runs\probe_ex02_kirby_stage3_floatstart\world\oracle.jsonl
   ```

## 6.5 Pre-flight checklist — what `preflight.sh` gates, with today's rehearsal receipts

Checks, in order (all $0; the world boot mounts `runs/` **read-only** and writes to a per-invocation
`/tmp` scratch): launch dir populated (`.mcp.json` + `CLAUDE.md`) → placeholder resolved → the
EXACT `--init-state` in `.mcp.json` exists under `runs/` → WSL `claude` binary, account-B dir,
`gb-mcp-world:latest` present → world boots from that state, `tools/list` is exactly the 9 expected
tools, one `observe` succeeds → the resulting oracle row has exactly the `hp`+`stage` keys with
**`stage==2`** and `hp>=1` → the frozen scorer refuses a missing oracle (`INSUFFICIENT_DATA`) and
does **not** PASS the pre-run trace → writes `preflight.ok` (sha256 of the state) which `run.sh`
requires.

Rehearsed today (test overrides, no `preflight.ok` written): **placeholder** dir → `PREFLIGHT: FAIL
— placeholder` rc=1; **banked stage=0 state** → boots, `tools OK (9), observe OK`, then FAIL
`stage=0 (want 2)` rc=1 — the gate discriminates; **synthetic stage=2 fixture** (banked state with
the stage byte set to 2, scratch-only, never a run input) → `oracle row OK: {'hp': 6, 'stage': 2}`,
`PREFLIGHT: OK` rc=0. `run.sh` guard chain walked A–F on a scratch copy: missing dir / missing
`.mcp.json` / unresolved placeholder / missing `preflight.ok` → `REFUSING` rc=3; all green →
`DRY_RUN OK` rc=0; prior `transcript.jsonl` present → one-attempt `REFUSING` rc=4. Scorer refusals
also executed directly: missing file → `INSUFFICIENT_DATA`/`oracle_file_missing_or_malformed`;
single pre-bar row → `FAIL_CAPABILITY`/`kirby_stage3_never_cleared_stage_3`.

## Appendix A — the run brief, verbatim (= `reports/probes/2026-07-29-kirby-ex02-floatstart/launcher/CLAUDE.md`)

```markdown
# You are the brain playing Kirby's Dream Land (Game Boy)

You play ONLY through the MCP tools below (server `kirby`). There is no other channel — no memory
access, no source code, no files. What the tools return is everything you know about the world.
There is no time pressure: the game waits for your next tool call.

## What this is
A single fixed-budget play session. The game is loaded from a MID-GAME save: Kirby is at the start
of an island stage, alive, with full vitality. You play onward from exactly here — there is no
title screen to get through.

## HOW THIS WORLD READS (verified in prior sessions — trust these, they save runs)
- **SIDE-SCROLLER.** The position/pose/walls part of `observe` is UNRELIABLE — walls data mislabels
  ordinary step-ups as "walls", and pose drifts. **IGNORE pose/walls.** Trust instead: the entities
  line, `read_region`, and `whats_changed`. Use `whats_changed` after a move to confirm the screen
  actually scrolled / something changed.
- **Kirby can FLOAT.** Press `up` (or tap `a` repeatedly) to puff up and float over gaps, pits, and
  enemies — floating is your main tool for crossing hazards. Come back down when the hazard is
  cleared.
- **Inhale then act.** `b` inhales: suck in an enemy, then either spit it as a projectile (`b`
  again) or swallow it (`down`). Inhale-then-spit is your main weapon; some bosses have their own
  gimmick — observe a pattern before committing to it.
- **Contact damage is INSTANT.** Touching an enemy or hazard costs vitality the moment you touch
  it (brief invincibility after). Losing all vitality costs a life; running out of lives is game
  over. Grab any food (health pickup) you see.
- Step-ups: at a raised ledge, a short hop / float carries you up; if a `right` press does not
  scroll (check `whats_changed`), try `up`/`a` to rise, then `right` again.

## Tools (MCP server `kirby`)
`observe` / `read_region` / `whats_changed` / `press_button` / `press_sequence` / `wait` /
`remember` (also `explore` / `goto` generic helpers).
- `press_sequence` (up to 16 buttons) covers ground fast where you are confident; `press_button` +
  `whats_changed` is for reacting. `wait` lets a timed hazard or animation pass.
- Log milestones with `remember`: stage entered, mini-boss/boss beaten, life lost, stage cleared.

## ▶ YOUR TASK
1. `observe` first. Confirm you have control: one small press, then `whats_changed`.
2. **Clear the island stage you are in**: fight through it, defeat whatever blocks the way out,
   and advance OUT of the stage. This is the priority.
3. Whatever follows the clear — keep playing into it, as far as the budget allows.
4. Stuck at one spot for many decisions? Change maneuver (float over it, inhale it, approach from
   another side). Never repeat an input that has already failed twice unchanged.

## Budget
150 decisions for the whole session. Pace yourself — do not spend the budget proving one ledge.

End by stating in ONE line how far you got: what you cleared, where you stopped, lives left.
```
