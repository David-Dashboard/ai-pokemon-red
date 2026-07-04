---
name: run-brief-authoring
description: How to write the brief (the launcher-dir CLAUDE.md the paid brain auto-loads) and the kickoff -p prompt so a run isn't wasted on ambiguity, non-compliance, or scorer taint. Invoke before writing or editing ANY runs/<tag>/CLAUDE.md brief or kickoff prompt.
---

# Run-brief authoring

The brief (`runs/<tag>/CLAUDE.md`) IS the intervention — reviewers critique those exact words
(**gate-methodology** §3), and the brain only ever sees it plus the kickoff `-p` prompt. Prose is
the weakest enforcement rung: `.claude/PROTOCOL.md`'s preamble puts trained-in adherence at ~80%,
and gate-methodology §2 restates it ("the brief is the un-gate-able surface"). Treat the brief like
code: mandatory shapes, gates the brain cannot misread, and the last failure's autopsy at the top —
not persuasive writing. A brief-level fix that fails **twice** escalates to a mechanical guard
(pre-registered), never a third rewording — that's anti-thrash (`.claude/PROTOCOL.md` §6).

## 1. The shared skeleton (verified across 7 briefs)

Every brief in `runs/` follows the same shape, task briefs and gate briefs alike:

`# You are the brain for <world>` → only-through-MCP-tools framing → **"What this is"** (one
paragraph naming the experiment) → world-facts/perception notes → `## Tools (MCP server <name>)` →
`## ▶ YOUR TASK` (numbered protocol) → `## Budget` (decision cap) → a mandatory one-line closing
report (always "End with..."/"End by stating...").

Line counts (all read in full): `runs/brain_red_starter/CLAUDE.md` 68, `runs/brain_emerald/CLAUDE.md`
40, `runs/brain_kirby_nds/CLAUDE.md` 36, `runs/brain_kirby_v3/CLAUDE.md` 85,
`runs/brain_kirby_v3_1/CLAUDE.md` 93, `runs/brain_skill_ab_armA/CLAUDE.md` and
`.../armB/CLAUDE.md` 39 each, byte-identical (`diff` exit 0).

## 2. Brief types and what varies

| Type | Example | What's distinctive |
|---|---|---|
| Task brief | `brain_red_starter` | A concrete domain recipe (:48-53, the Oak's-table interaction), a success-evidence rule (:58 "Do not infer success — observe it"), a hard decision cap (:64). |
| Constancy probe | `brain_emerald`, `brain_kirby_nds` | Closing report is a 3-part gap survey, not a task-done check — emerald :38-40 asks "(a) did you reach free-roam ... (b) the 3 biggest perception gaps ... (c) one line on whether controls behaved as documented"; kirby_nds :17 adds a forbidden action ("NEVER blind-tap through save/erase-looking menus"). |
| Gate brief | `brain_kirby_v3`, `brain_kirby_v3_1` | Mandatory claim shapes, a numbered evidence cycle with ordering rules, explicit scorer-threat warnings ("at 20%+ excluded lines the run is unscorable"). |
| A/B arm brief | `brain_skill_ab_armA` / `armB` | The two briefs are **byte-identical**; arm isolation happens ONLY in `run.sh`/`.mcp.json` (env flag gating which tools the world exposes), never in the brief text. The brief carries one conditional section instead — ":17-24 "Your tool list MAY additionally include `define_skill`/`run_skill`... If those tools are not in your list, ignore this section"" — so the SAME words work for both arms and the brain never learns which arm it's in. |

## 3. Discipline devices that WORK (each with a receipt)

- **Mandatory claim shapes.** Fixed grammars the brain fills in, not prose it improvises:
  `ENT id=<k> region=(x0,y0,x1,y1) step=<n> claim=threat|benign` (v3 `CLAUDE.md:46`),
  `remember "NEAR id=<k> step=<n>"` (v3 `:59`), `DECLARE threat=<k>` / `DECLARE benign=<k>` /
  `REJECT id=<k> reason=<...>` (v3 `:75-77`).
- **The watermark device.** `brain_kirby_entity/CLAUDE.md:61-68`: "`step=<n>` must be the step
  number of the result you JUST received — the CURRENT step. NEVER a past step," followed by an
  explicit DO example (an honest current-step NEAR) and a DON'T example (backfilling a step number
  after seeing the outcome). `HANDOFF.md:250` records it worked: "retroactive-taint caught by the
  watermark (worked as designed)."
- **Failure-autopsy-on-top.** `brain_kirby_v3_1/CLAUDE.md:9-21`, titled "WHAT WENT WRONG LAST RUN —
  read this first, it wasted a whole paid run" — names the exact prior mistake (NEAR logged after
  the hit) before the brain reads anything else.
- **Hard gates phrased as preconditions**, not advice: `brain_kirby_v3_1/CLAUDE.md:63` "You may NOT
  call approach_suspect until this NEAR is logged at the current step."
- **Priority override to prevent discipline-vs-task deadlock.** `brain_kirby_v3_1/CLAUDE.md:84-85`:
  "Banking >=5 separate life-drop events is the priority — if the gap discipline is ever costing you
  drops, take the contact." Without this, a brain that can't simultaneously satisfy the gap rule and
  the drop-count target can stall entirely.
- **Closing-report mandate.** Present in all 7 briefs, always the last line — cheap insurance against
  a run ending with no legible summary.

## 4. Devices that FAILED (the humility section — read before trusting any device above)

- **v3: a mid-protocol instruction is not enforcement.** The mandatory pre-approach NEAR was stated
  once, inside cycle step (i) of `brain_kirby_v3/CLAUDE.md` — and the brain skipped it anyway. Per
  `reports/2026-07-03-entity-v3-verdict.md:97-106`, only 3 `NEAR id=1` claims existed against 5 drops,
  and each was logged AFTER its nearest drop (steps 7/38/64 vs drops at 6/35/61), starving `q_k` (the
  scorer's fraction of drops covered by a prior NEAR claim; bar 0.80 — see **gate-methodology** §1)
  to 0.400 — not a window-size (`W=15`) problem, a compliance problem. `:147-149` states it plainly: "The
  pre-approach-NEAR instruction already existed in this run's brief (cycle step (i)) and was skipped
  anyway." **Lesson: an instruction stated once mid-protocol is not enforcement — it needs a gate
  (precondition wording) + an autopsy block + a fixed shape, together.**
- **v3.1: the brain quoted the mandated shape inside bookkeeping, and the scorer's regex re-parsed
  it as a claim.** Fixes (a) (NEAR-before-approach) and (b) (>=3-press gap) both worked behaviorally
  (`reports/2026-07-04-entity-v3.1-verdict.md`: all 9 genuine NEARs logged before their approach, all
  5 drops covered; 6 of 7 run_skill calls cleared >=3 presses) — but the brain also wrote lesson notes
  like `DROP#1 at step=11 ... Covered by NEAR id=1 step=2,5`, and the scorer's `_NEAR_RE` (a `.search`
  over the whole lesson line) re-matched each of those 4 notes as a fresh NEAR claim, logged after
  the drop it referenced → RETROACTIVE. 4/13 = 30.8% >= the 20% retroactive cap → `VERDICT:
  INSUFFICIENT_DATA`, run unscorable, even though zero genuine NEARs were late. Same failure mode is
  pinned in **gate-methodology**'s "Known scorer/world gotchas" item 2. **Lesson: the brief must
  FORBID quoting mandated claim shapes inside any other note, and every claim-shape mandate must be
  checked against the scorer's regexes BEFORE launch** — dry-run the scorer on a synthetic transcript
  if in doubt; grep the regex source, don't guess from the docstring.

## 5. Kickoff `-p` prompt craft

The `-p` prompt is not a second brief — it restates only the 1-2 laws whose violation would waste
the entire run; everything else lives in `CLAUDE.md` (which the brain auto-loads from the launcher
dir per **paid-run-harness**).

- **Early pattern** (`brain_red_starter/run.sh:29`): a short task recap + explicit stop condition —
  "Begin YOUR TASK now, per CLAUDE.md: get your first Pokemon from Professor Oak. ... STOP when you
  have the Pokemon or after ~90 decisions, then give the one-line summary."
- **Current pattern adds a tools-check bail-out FIRST**, before any task text —
  `brain_skill_ab_armA/run.sh:30`: "FIRST: verify the mcp__arc tools (...) are available — if NOT,
  output exactly MCP_UNAVAILABLE and stop immediately." This turns an MCP-wiring failure into one
  grep-able token instead of 90 turns of confused retries.
- **Gate runs restate the hard rules verbatim, not just gesture at the brief.**
  `brain_kirby_v3_1/run.sh:32` opens with the MCP_UNAVAILABLE check, then: "TWO hard rules that decide
  whether this run is scoreable: (1) LOG THE NEAR BEFORE EVERY APPROACH ... (2) APPROACH ACROSS A
  >=3-PRESS GAP ..." — spelling out exactly the two v3 failure modes being fixed, in the same words
  as the brief's gates.
- **Rule of thumb:** if a rule's violation is fatal to scoring (unscorable, MCP_UNAVAILABLE), restate
  it in the `-p` prompt too, in the same wording as the brief. If a rule is important but not
  run-ending, it lives in the brief only — duplicating everything in the `-p` prompt just gives the
  brain two versions of the same instruction to reconcile (or ignore).

## 6. Pre-launch brief checklist

- [ ] If a prior attempt at this task/gate failed, the autopsy is the FIRST thing after the title —
  name the exact prior mistake, not a vague "be careful."
- [ ] Every mandated claim/log shape has been grep-checked against the scorer's actual regexes (not
  its docstring) — confirm it cannot re-match inside a different note (§4 v3.1 failure).
- [ ] A forbidden-quoting clause exists for any mandated shape ("do not write `NEAR id=...` inside a
  DROP/lesson note; use `covered_by_steps=` instead").
- [ ] Budget line + mandatory one-line closing report are present.
- [ ] No oracle/RAM facts leak into the brief — the brain gets screen/symbolic tools only (restates
  **safety-invariants** law 5, "Oracle/RAM/score never on the agent wire" — do not weaken it).
- [ ] If this is an A/B arm brief: the two arms' `CLAUDE.md` are word-for-word identical; any
  tool-availability difference is phrased conditionally ("MAY include... if not present, ignore") and
  arm identity is never named or inferable from the brief text.
- [ ] If this is a gate brief: the brief is being reviewed as an **appendix of the pre-registration**,
  not standalone — `reports/2026-07-04-entity-v3.1-prereg.md:269` ("Appendix — the pinned v3.1 run
  brief (the entire intervention)") is the pattern; get the adversarial review before spending
  (**gate-methodology** §3), don't ship a brief edit straight to `run.sh`.

## Cross-references

- **gate-methodology** — owns the brief for gate runs (the pre-reg's appendix); this skill is where
  the brief's craft/devices/failures live, gate-methodology owns the pre-reg/review/scoring process
  around it.
- **paid-run-harness** — launch mechanics (`.mcp.json`, `run.sh` shape, account-B/blank-agent laws,
  seam check); this skill only covers the two files inside the launcher dir that carry the brain's
  instructions (`CLAUDE.md`, the `-p` prompt string).
- **long-horizon-runs** — segment briefs + the closing-report ferry across multi-session runs; the
  closing-report mandate (§3) is what that skill's ferry design builds on.
- **diagnose-a-run** — the source discipline for autopsy blocks: when a run needs a §4-style
  "what went wrong" writeup, that skill is how you produce it from raw artifacts before it goes in
  the next brief.
- **world-lanes-frontier** + **new-world-port** — a brief for a NON-GB lane (ARC, 3D, NDS/MKDS,
  MiniWoB) must fold in that lane's banked gotchas and flags (e.g. `NDS_SKILLS=1` arm isolation,
  continuous-time perception breaks): read the lane's section in world-lanes-frontier BEFORE
  drafting, and its cited reports for the world-facts section of the brief.

## Sources

- `runs/brain_red_starter/CLAUDE.md`, `runs/brain_emerald/CLAUDE.md`, `runs/brain_kirby_nds/CLAUDE.md`,
  `runs/brain_kirby_v3/CLAUDE.md`, `runs/brain_kirby_v3_1/CLAUDE.md`, `runs/brain_kirby_entity/CLAUDE.md`,
  `runs/brain_skill_ab_armA/CLAUDE.md`, `runs/brain_skill_ab_armB/CLAUDE.md` (all read in full from
  the main checkout `/mnt/e/AI_Personas/10_pokemon_and_chess_and_office/ai-pokemon-red/runs/` —
  gitignored, read-only, a live run in progress there at time of writing)
- `runs/brain_red_starter/run.sh`, `runs/brain_skill_ab_armA/run.sh`, `runs/brain_kirby_v3_1/run.sh`
  (kickoff `-p` prompts)
- `reports/2026-07-03-entity-v3-verdict.md` (v3 NEAR-timing diagnosis, :97-106, :147-149)
- `reports/2026-07-04-entity-v3.1-verdict.md` and `reports/2026-07-04-entity-v3.1-prereg.md`
  (quoted-NEAR taint, 4/13 retroactive, brief-as-appendix pattern; PR #96, on `main` in this worktree)
- `HANDOFF.md:250` (watermark-worked-as-designed note)
- `.claude/skills/gate-methodology/SKILL.md` ("Known scorer/world gotchas" item 2)
- `.claude/skills/paid-run-harness/SKILL.md` (launcher-dir anatomy, run.sh shape)
- `.claude/skills/safety-invariants/SKILL.md` law 5 (oracle/RAM off the agent wire)
- `.claude/PROTOCOL.md` (~80% prose-adherence figure, §6 anti-thrash)
