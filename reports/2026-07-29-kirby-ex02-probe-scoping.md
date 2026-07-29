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
