---
name: gate-methodology
description: How this project designs, pre-registers, runs, scores, and banks capability gates. Invoke before planning, running, scoring, or writing the verdict for ANY paid gate attempt (entity gate, skill gate, HUD gate, ports).
---

# Gate methodology

A "gate" is one pre-registered, paid (~$4-6) agent run scored by a frozen script. The method is
pre-registration → adversarial review → ONE attempt → verbatim scoring → banked verdict → diagnosis.
Reference examples (read these to see the shape): `reports/2026-07-03-kirby-skill-port-entity-v3.md`
(pre-reg), `reports/2026-07-03-entity-v3-verdict.md` (verdict). The v3.1 pair
(`reports/2026-07-04-entity-v3.1-prereg.md`, `reports/2026-07-04-entity-v3.1-verdict.md`, PR #96,
merged to `main`) is the most recent worked example.
**v3.1 HAS ALREADY RUN** (2026-07-04, `runs/brain_kirby_v3_1/`, `run.exit`=EXIT=0, verdict
INSUFFICIENT_DATA via claim-regex taint): it is a spent attempt — do NOT relaunch `run.sh` or
re-register v3.1. HANDOFF's older `⇒ NEXT` "v3.1 pre-registration" line predates this run.

## 1. Pre-register BEFORE spending

Write `reports/<date>-<gate>-prereg.md` BEFORE the paid run. It must pin, in writing:

- [ ] **What changed vs frozen.** Exactly which surfaces this attempt varies (e.g. "brief-only;
      machinery frozen") and which are inherited verbatim. List frozen items explicitly: scorer file,
      predicate enums, constants (`WINDOW`, `MIN_NEAR`, caps...), turn cap, budget.
- [ ] **Hypotheses.** Each independently observable in the scored output (v3.1's H-a: "q_k >= 0.80";
      H-b: ">=1 qualifying-conditional run_skill call").
- [ ] **The exact scorer + bar.** Name the file (`eval/score_entity_gate_v3.py`), quote the bar with
      numbers (`q_k >= 0.80`, `q_k - b_k >= 0.15`, `b_k <= 0.70`, `MIN_NEAR = 3`), and the PASS
      definition (e.g. ">=1 GROUNDED threat AND >=1 correctly-rejected benign AND skill guard clears").
- [ ] **The run brief, verbatim, as an appendix.** The brief IS the intervention; reviewers critique
      those exact words. Deltas from the prior brief marked (v3.1 uses `[v3.1]` tags). Write it per
      the **run-brief-authoring** skill (devices, failed-device autopsies, the pre-launch checklist
      that catches shape/regex collisions like gotcha 2 below).
- [ ] **Escalation ladder, pre-registered NOW.** "IF this fails the same way, vNext does X" —
      written before the run, not improvised after (v3.1 §3 / §4 pin the v3.2-(a) watermark-look guard
      and v3.2-(b) `min_iters=3` floor as shelf items).
- [ ] **One-attempt rule + verdict vocabulary** restated: PASS / FAIL / INSUFFICIENT_DATA /
      INSUFFICIENT_DROPS / NO_DECLARE (or the gate's own set). Infra-death carve-out if any
      (v3.1: relaunch once only if it dies before 10 decisions; a completed run is final).

## 2. Machinery-frozen discipline

- The scorer is reused **byte-for-byte**. Changes to scoring machinery are allowed only if
  **stricter-only** (a new precondition, a lower cap — never loosening a pinned constant).
- Free pre-check gates (dry executor, seam isolation, press physics, etc.) test machinery; if no
  machinery changed, they carry over as already-passed — nothing to re-run (v3.1 §5).
- The brief is the un-gate-able surface: prose is the weakest enforcement rung (~80% adherence per
  `.claude/PROTOCOL.md`). If a brief-level fix fails twice, the pre-registered escalation moves the
  discipline into code as an invariant.

## 3. Adversarial review BEFORE the run

Send the pre-reg through at least one adversarial (Sonnet) reviewer before launch; fix majors; record
a "Review triage" section in the pre-reg itself. This catches real design bugs pre-spend: v3.1's
review found the NEAR-coverage vs distance-invocation contradiction and the `k >= 3` binding-floor
miscalibration — both fixed before the $5 was spent. Account-B launch mechanics are pre-authorized (paid-run-harness
law 1); what needs David is the DECISION to spend on a new gate attempt or a pre-registered
escalation — list candidates, let him pick.

## 4. One paid attempt — verdict BANKED as-is

One attempt per pre-registration. Whatever the frozen scorer prints is the verdict. **Never
informally re-run** a completed attempt — a second attempt requires a fresh, narrower
pre-registration (v3 §8 required this; v3.1 was that document).

## 5. Scoring: run the frozen scorer, quote VERBATIM

```
# Linux/WSL:
uv run --frozen python eval/score_entity_gate_v3.py runs/<dir>
# Windows PowerShell:
$env:UV_PROJECT_ENVIRONMENT=".venv-win"; $env:UV_NATIVE_TLS="true"; uv run --frozen python eval/score_entity_gate_v3.py runs/<dir>
# (module form also documented in the scorer docstring: uv run python -m eval.score_entity_gate_v3 runs/<dir>)
```

It reads `<dir>/transcript.jsonl`, `<dir>/world/oracle.jsonl`, `<dir>/world/skills.jsonl`. Paste the
scorer's output into the verdict **verbatim, in a code block** — never paraphrase the verdict line.

## 6. INSUFFICIENT_DATA is a real verdict — diagnose from artifacts

Do not treat it as "try again". Diagnose line-by-line from the raw run artifacts
(`transcript.jsonl`, `world/oracle.jsonl`, `world/skills.jsonl`, frames) before proposing vNext.
Standard: every number in the verdict is re-verified against the raw files, not the scorer summary
(v3 verdict: recomputed every run_skill span; v3.1 verdict: identified exactly which 4 lines were
retroactive and why). Separate INDEPENDENT failure modes explicitly — fixing one does not fix the
other. Also record what VALIDATED despite the verdict (v3: b_k repair 0.812→0.585, benign arm PASS).

Escalations go on the pre-registered shelf; picking one (or spending again) is **David's decision** —
list candidates in the verdict, do not decide.

## 7. Write the verdict + update HANDOFF

`reports/<date>-<gate>-verdict.md` containing: run facts (turns, $, `subtype: success`,
`is_error`, launch details), the verbatim scorer output, the banked verdict, what validated, the
mechanical diagnosis, honest bounds, and vNext candidates (marked "NOT decided — David's call").
Then append the HANDOFF.md top block (the v3.1 verdict commit did both in one change). Note:
`runs/<dir>` is gitignored — cite it as on-disk evidence, the report is what's tracked.

## Known scorer/world gotchas (each cost a real run — check BEFORE designing)

1. **HP oracles can be BCD.** Cave Noire current HP is **BCD at 0xC120** (`0x10` = HP 10); the
   Phase-A claim of `0xD389` was **WRONG** (a coincidental 2-anchor match; `eval/_archive/find_hp_addr.py`
   tested raw-decimal only). When oracle-hunting any GB HUD value, test the BCD decode
   `(b>>4)*10 + (b&0xF)` and verify against MANY displayed frames, not 2 anchors. (The v3 scorer's
   `_bcd()` is identity for bytes 0-9, so it works for both Cave Noire 0xC120 and Kirby's plain-int
   0xD086.)

2. **Claim-regex taint (killed v3.1).** Entity-gate scorers match claims with `.search` over whole
   remember lines (`_NEAR_RE = NEAR\s+id=(-?\d+)\s+step=(-?\d+)`). Quoting a claim shape inside ANY
   other note re-parses as a claim: v3.1's brain wrote bookkeeping like
   `DROP#1 at step=11 ... Covered by NEAR id=1 step=2,5` — each re-matched as a NEAR, logged
   post-drop, hence RETROACTIVE; 4/13 = 30.8% >= the 20% cap → unscorable, run dead, zero genuine
   NEARs were late. **Briefs must FORBID quoting the claim shape** (mandate e.g.
   `DROP#n covered_by_steps=2,5` instead) — this is v3.2 candidate (c).

3. **`region_changed` is degenerate against enemies that move toward you** — the target enters the
   watched box almost immediately, so the predicate fires at press 1 (a one-shot dressed as a loop).
   And **`steps_elapsed(n)` loops do NOT count as conditional evidence** by design (a pure step-count
   loop never branches on world state — pinned in the v3 scorer §5.4 wording). v3.1's brain hit both:
   `region_changed` fired at press 1, it adaptively switched to `steps_elapsed(4)`, and the guard
   scored 0 qualifying-conditional. Against converging enemies, consider `move_blocked`, a box ahead
   of the avatar, or conditionally approaching a STATIONARY target (v3.2 candidate (d), plus the
   unlettered stationary-target variant — undecided, David's call).

## Sources

- `reports/2026-07-03-kirby-skill-port-entity-v3.md` (v3 pre-registration, incl. Amendment A1)
- `reports/2026-07-03-entity-v3-verdict.md`
- `reports/2026-07-04-entity-v3.1-prereg.md` and `reports/2026-07-04-entity-v3.1-verdict.md`
  (PR #96, merged)
- `eval/score_entity_gate_v3.py` (module docstring + pinned constants/regexes)
- `eval/README.md`
- `.claude/PROTOCOL.md` (anti-thrash, autonomy boundary)
- Memory: `entity-v3-verdict.md`, `cave-noire-hp-oracle.md`, `adr002-gate-passed.md`
  (C:/Users/Succe/.claude/projects/E--AI-Personas-10-pokemon-and-chess-and-office/memory/)
