# Gate 0 pre-registration (for David's signature) — 2026-07-18

**Gate:** Minimum North Star Gate 0 — one fixed Codex brain, two worlds (Pokémon Red + MiniWoB),
one attempt each. **Status: DRAFT, not signed, not launch-ready.** R0/W0/C0 readiness are not all
`GO` (below). No spend is authorized by this document.

## What this buys

Per the capability-map B-track rule — "every gate pre-registration names which capability(ies) it
buys evidence about; a gate that buys none is not run" (`reports/2026-07-05-northstar-capability-map.md:187-189`)
— Gate 0 buys **the first controlled joint lower bound on Capability + Constancy + Generality + Cheap**,
the four North Star claims defined in `HANDOFF.md:852-866` (§1). It is explicitly **not** the
graduation exam (`reports/2026-07-13-minimum-north-star-gate-0-design.md:41-43`, hereafter "design doc").

**One-attempt-per-arm law:** "one attempt per world, with artifacts and verdict banked as-is"
(design doc:110); restated at signature/launch as step 3, "Run one ChatGPT-subscription Codex
attempt per world... The task and whole arm config retain their separate hashes" (design doc:363-365).

**Banked-as-is law:** "Bank PASS/FAIL/INSUFFICIENT_DATA/CONSTANCY_BREACH as printed. Never rescue
a marginal result with an informal rerun." (design doc:372-373).

## Arms

| | Arm R — Pokémon Red | Arm W — MiniWoB click-checkboxes |
|---|---|---|
| Task (verbatim, no hints) | "From the fresh bedroom start, obtain your first Pokemon from Professor Oak and win the first rival battle." (design doc:126-127) | Task instruction comes from the environment exactly as shown to a human; brief says only to complete five fresh episodes via screen pixels + mouse/keyboard (design doc:144-148) |
| Forbidden brief content | lab route, ball location, facing rule, button sequence, starter choice, nickname answer, battle move, or anything distinguishing the correct object from alternatives (design doc:129-131) | — |
| Oracle end-state | party `0→1` AND rival battle entered+exited without blackout, free movement after (design doc:133-138) — code form: fresh party 0, first transition exactly 0→1, later trainer battle (`in_battle==2`), 10-row sustained exit with unchanged map and HP never 0, ≥2 distinct post-exit positions (PR #114 `eval/score_gate0.py:28-69`, not yet on `main`) | reward `1.0` on exactly 5/5 non-abandoned pinned episodes, seeds `1000..1004` (design doc:150-152, 176; `eval/score_gate0.py:72-87`) |
| **Verbatim run brief** | **NOT YET DRAFTED.** Gate-methodology requires the brief as a pre-reg appendix (`.claude/skills/gate-methodology/SKILL.md` §1). This is an open precondition, not covered by this DRAFT — see Preconditions. | same |

**Fixed Codex brain, pool = ChatGPT/Codex subscription only.** No `ANTHROPIC`/`OPENAI_API_KEY` /
`CODEX_API_KEY` fallback — the launcher throws if either is set (`tools/run_gate0_codex.ps1:125-128`);
auto-top-up OFF, no API key (design doc:367). Fields to be frozen **at signature** from a fresh
receipt (not hardcoded now — C0 is not `GO` and images may be rebuilt): `codex_path`,
`codex_executable_sha256`, `codex_version` (no `latest` alias — design doc:96-98, enforced at
`tools/run_gate0_codex.ps1:104-106`), `planned_model`, `brain_config_sha256`,
`critical_config_transport`, `auth_method` — the full pinned-field set is
`tools/check_gate0_codex.py:17-23` (`PIN_FIELDS`), and the subset that must match byte-identically
between arms is `tools/check_gate0_codex.py:24-27` (`CONSTANCY_FIELDS`). Last-observed **free**
(non-paid) values, NOT the frozen pin: `codex_version=0.144.3`, `planned_model=gpt-5.4`
(`HANDOFF.md:20-24`) — these must be re-observed and hashed fresh at signature, not copy-pasted.

## Bars (quoted verbatim; scoring by `eval/score_gate0.py` verdict vocabulary as-printed)

**Capability bar**, for each world (design doc:262-271):
1. the task-specific success predicate above passes; and
2. agent wall-clock time is `<= 2.0x` the one-human baseline; and
3. agent primitive control actions are `<= 2.0x` the human baseline.
"R0/W0 must return `NO_GO` without spend if a free latency/physics ceiling already proves the 2.0x
bar impossible." (design doc:269-270)

**Cheap bar** (design doc:282-286, 288-295):

| Arm | Wakes | Cost | Normalized Codex credits |
|---|---:|---:|---:|
| Red starter+rival | `<=90` | `<=$5.00` | `<=125` |
| MiniWoB 5 episodes | `<=50` | `<=$2.00` | `<=50` |
| **Combined PASS** | `<=140` | `<=$7.00` | `<=175` |
| **Hard breaker** | — | — | `<=250` (combined) |

"A successful run costing `$7.01..$10.00` is `FAIL_CHEAP`" (design doc:306-307) — note the $10
figure is prose-only; the scorer's mechanical hard-breaker check tests **credits only**
(`sum(credits) > 250` → `hard_breaker_exceeded`, `eval/score_gate0.py:220-221`), folded into the
same `FAIL_CHEAP` verdict as a missed combined cap — the scorer does not emit a distinct verdict
class for "breach vs fail," it prints `FAIL_CHEAP` either way. The **live** 250-credit halt is a
separate runtime control, not this offline check (see Preconditions).

**Constancy / Generality / no-leak bars** (design doc:316-323): exact model ID, executable version,
`brain_config_sha256`, memory-wipe receipt, and init-inventory policy match across arms; no
brain/contract/tool-schema change between arms; only task text, perceiver/world config, and human
control vocabulary differ; both world tasks must pass (one-world success is not Generality PASS);
every assistant tool call belongs to the pinned world-MCP allowlist.

**Verdict vocabulary, exactly as printed by `eval/score_gate0.py` (schema_version 1)** — two
fields, `readiness` and `overall`:
- `readiness` ∈ `GO | NO_GO | INSUFFICIENT_SOURCE` (design doc:252-253)
- `overall` ∈ `PASS | FAIL_CAPABILITY | FAIL_CHEAP | CONSTANCY_BREACH | NO_LEAK | INSUFFICIENT_DATA`
  (design doc:325-327, matches `eval/score_gate0.py:223-236` exactly)
- Constancy/no-leak checks run before task scoring (design doc:327; scorer checks `leak` then
  `constancy` before `capability`/`cheap`, `eval/score_gate0.py:223-234).
- `tools/check_gate0_codex.py`'s own `overall`/`no_leak`/`wake_accounting` fields (e.g.
  `NO_GO_INSUFFICIENT_WAKES`) are an **intermediate per-arm audit input** consumed by
  `score_gate0.py`, not the gate's printed verdict — do not quote them as the Gate 0 result.

**No re-scoring, no bar edits post-signature.** R0/W0/C0 "may tighten them but never loosen them"
(design doc:250, 258).

## Preconditions — ALL must be GO before launch

| # | Precondition | Evidence pointer | Status |
|---|---|---|---|
| 1 | R0/W0/C0 readiness all `GO` | PR #114 "Gate 0: bank R0/W0/C0 readiness verdict" (`codex/gate0-r0-w0-c0-readiness-2026-07-14`, OPEN, not merged) — banked verdict table: R0 `INSUFFICIENT_SOURCE`, W0 `INSUFFICIENT_SOURCE`, C0 `INSUFFICIENT_SOURCE`, Paid Gate 0 `NO_GO` (readiness report on that branch, `reports/2026-07-14-gate0-readiness.md:5-10`) | **NOT MET** |
| 2 | `eval/score_gate0.py` itself lands on `main` | currently exists ONLY on PR #114's branch — confirmed absent from `main`@`a8997cd` (`git show main:eval/score_gate0.py` fails) | **NOT MET** — merging #114 (or landing the scorer) is a precondition, independent of R0/W0/C0 |
| 3 | Frozen expected-pins JSON, independent of the observed receipt | must supply all 19 `PIN_FIELDS` (`tools/check_gate0_codex.py:17-23`) written BEFORE the run, never derived from it; readiness report: "no independently frozen expected-pins JSON exists" (PR#114 `reports/2026-07-14-gate0-readiness.md:121-122`) | **NOT MET** |
| 4 | Live breaker dry-run TRIP receipt | design doc requires "a live breaker that halts at 250 normalized credits without relying on end-of-run arithmetic" (design doc:244-246); scorer requires a `live_breaker` artifact with `kind=live_credit_breaker`, `status=PASS`, `limit=250` (`eval/score_gate0.py:174-179) — **tighten, not loosen:** that artifact must record an actual dry-run TRIP (breaker fired at/above 250 and halted execution), not merely a self-declared PASS status; readiness report: no live breaker exists (PR#114 `reports/2026-07-14-gate0-readiness.md:124-126`) | **NOT MET** |
| 5 | Blank-agent wipe line (Codex form) | each launch uses a fresh, empty `OutputDir` (`tools/run_gate0_codex.ps1:107-114`) and a newly created isolated `codex-home` per run (`tools/run_gate0_codex.ps1:140,143`), with `history.persistence="none"` and `features.memories=false` forced in the config overrides (`tools/run_gate0_codex.ps1:260,262`) — mechanism exists; not yet exercised in a paid context | **MECHANISM EXISTS, unexercised** |
| 6 | Human baselines recorded (who/when) | R0: "no human baseline from `runs/red_start.state`..." ; W0: "no DEV click-checkboxes five-episode oracle artifact and no human baseline" (PR#114 `reports/2026-07-14-gate0-readiness.md:58-59,80-81`) | **NOT MET — who/when: ___ (David to fill)** |
| 7 | Codex CLI executability + auth receipt | contrary to the task's assumption that the WindowsApps-alias issue is still open: it is **RESOLVED** on current `main` — `Resolve-CodexExecutable` fails closed to exactly one real `.exe` (PR #112, merged) and both arms now have free ChatGPT-auth receipts: Red `handshake-receipt.json` sha256 `88a5a2d9…3e5`, MiniWoB sha256 `0961c5c0…c59` (`HANDOFF.md:15-18`) | **MET** (free handshake only — NOT a paid-execution receipt) |
| 8 | **[David, 2026-07-18] Codex-pool quota check** | Immediately before EACH arm's launch, confirm remaining ChatGPT/Codex subscription quota is sufficient for that arm's hard ceiling (250 normalized credits). If insufficient: the arm **WAITS** for the pool reset. Switching the gate to a different brain/pool is **FORBIDDEN** — the fixed-Codex-brain pin is constitutive of Gate 0; a brain switch is a new gate requiring fresh pre-registration | pool status is finite and may run out per David; no receipt yet | **NOT MET** |
| 9 | **World images rebuilt from a clean checkout AFTER #114 merges** | PR #114's fix `d75e8be` makes code-parity hashing canonical-git-blob (CRLF-portable) with an `UNHASHABLE` refusal on dirty trees — any image built from a pre-fix/CRLF context now correctly REFUSES parity. Rebuild `gb-mcp-world` (and any Gate-0-pinned image) from a clean post-merge checkout; receipt = image digest + a passing C0 parity check against it | fixer note, PR #114 comment (2026-07-18) | **NOT MET** (blocked on #114 merge) |

## Launch discipline

Order (design doc:358-373, step numbers as-printed): (1) all-`GO` R0+W0+C0 → (2) this pre-reg
frozen + adversarially reviewed → (3) one Codex attempt per world, blank memory before each, same
exact executable/model/brain-config → (4) auto-top-up OFF, no API key → (5) hard-stop at combined
`<=$10`/`250` credits (containment, not a success target; PASS still needs `<=$7`/`175`) → (6) "If
Arm R alone reaches the combined ceiling, do not launch Arm W" (design doc:371) — **Arm R launches
first** → (7) bank the printed verdict, never an informal rerun.

**[David, 2026-07-18] Pool reservation:** the Codex/ChatGPT pool is reserved **exclusively for
Gate 0** during this campaign — the graduation exam and all mechanism pilots run on the Claude
account-B brain per the campaign plan. Gate 0 therefore has first claim on that pool; a
pool-exhaustion wait (precondition 8) is a **schedule slip, not a verdict event** — it does not
count against the one-attempt law and does not itself produce `INSUFFICIENT_DATA`.

**What aborts vs banks:** `NO_LEAK` or `CONSTANCY_BREACH` void the attempt as evidence — "the
result is a constancy breach, not a capability verdict" (design doc:117-118); constancy/no-leak
checks run before task scoring, so neither is a capability outcome. A completed run's
capability/cheap failure (`FAIL_CAPABILITY`, `FAIL_CHEAP`) still **banks** — it is real evidence,
scored and reported as printed.

**No-retry rule + the ONE harness-death carve-out.** The design doc requires the future pre-reg to
state an "infra carve-out" (design doc:359-361) but **does not itself specify one** — its
escalation shelf (design doc §"Interpretation and escalation shelf", :380-397) covers how to
interpret Red/MiniWoB *task* failures, not infra death. This carve-out is therefore inherited
verbatim from the project's standing general law, not quoted from Gate 0's own escalation shelf:
"Relaunch only on infra death before ~10 decisions (MCP never connected, container crash, 429).
Infra death AT or AFTER ~10 decisions = the attempt is spent: score whatever artifacts exist with
the frozen scorer and bank that verdict (`INSUFFICIENT_DATA` is a legitimate outcome). No relaunch
without David's explicit OK." (`.claude/skills/paid-run-harness/SKILL.md` law 6, restated
`.claude/skills/safety-invariants/SKILL.md` law 5). David should confirm this ~10-decision/wake
threshold applies unchanged to the Codex harness, or set a Gate-0-specific number, at signature.

## Signature block

Pre-registered by: ______________________ / Date: ______________________
Frozen commit: ______________________ (the commit whose `eval/score_gate0.py`,
`tools/check_gate0_codex.py`, and both arm briefs this signature binds to)

**David's pending items (pulled from the readiness report and this review):**
1. Merge or otherwise land PR #114 (`eval/score_gate0.py` + readiness report) onto `main`.
2. Record both human baselines (Red from `runs/red_start.state`; MiniWoB DEV `0..4`) — who/when.
3. Author + adversarially review the two verbatim hint-free run briefs (currently undrafted).
4. Independently freeze the expected-pins JSON before any receipt exists.
5. Produce the live-breaker dry-run TRIP receipt and the exact-wake-boundary receipt.
6. Confirm the ~10-decision/wake harness-death carve-out number for the Codex harness (Launch
   discipline, above).
7. Sign off on the Codex-pool reservation and quota-check precondition (#8 above).

## Falsifiability — what each verdict means for the four North Star claims

- **`PASS`** (both arms `GO`+`PASS`): first controlled evidence FOR Capability, Constancy,
  Generality, and Cheap jointly — a lower bound only, not graduation (design doc:41-43).
- **`FAIL_CAPABILITY`**: the fixed brain cannot complete a human-grade task from the screen alone
  in that world at this bar — falsifies Capability for this task; per-failure interpretation is
  design doc's escalation shelf (:382-397) — e.g. Red failing before the ball implicates the
  named/static-object referential layer (:382-384), not the brain.
- **`FAIL_CHEAP`**: Capability may still hold, but Cheap is falsified at current bars — "inspect
  repeated decisions... no automatic or cross-run promotion" (design doc:391-393).
- **`CONSTANCY_BREACH`**: the brain/config differed between arms — falsifies the premise that any
  capability/cheap result in this run is attributable to one fixed brain; voids Constancy AND
  taints whatever Capability/Cheap numbers were printed (not usable as evidence for either).
- **`NO_LEAK`**: an oracle/RAM/DOM/tool-allowlist leak occurred — falsifies the screen-only
  precondition for Capability; the run is not evidence for any claim.
- **`INSUFFICIENT_DATA`**: infra/accounting failure — no claim is falsified or supported; per
  gate-methodology, diagnose from raw artifacts before proposing a vNext, never "try again"
  informally.
- **One-arm PASS / one-arm FAIL**: bank the partial evidence; Generality is NOT established (single
  world success is explicitly excluded, design doc:322); "fix the failed seam, then wait for a new
  pre-registration; do not rerun the passing arm" (design doc:394-395).

## AMENDMENT (2026-07-21, David's decision) — Cheap axis grounded on cost-per-task; wakes deferred

**Does not retro-edit anything above — this DRAFT's bars, arms, and preconditions are left as
originally written.** PR #126 (`reports/2026-07-21-gate0-wake-grounding.md`) proved, against a real
`codex exec --json` transcript, that Codex's JSONL stream has no documented per-model-decision
boundary event (one `turn.completed` bundled `>=2` real decisions, cumulative usage) — so
`tools/check_gate0_codex.py::audit()` correctly reverted to a fail-closed `wakes=None`/
`wake_accounting="INSUFFICIENT_WAKES"` hardcode. Pre-amendment, that made `eval/score_gate0.py`'s
verdict permanently unable to reach `PASS`, on any run however clean, purely because the scorer
required `wake_accounting == "PASS"` — an axis nobody can currently measure, not a capability, cost,
or constancy failure.

**Gate 0's Cheap axis is grounded on COST-PER-TASK** ($-cost caps + the live credit breaker) exactly
as pinned in this document's "Cheap bar" table above (`<=$5.00`/`<=$2.00`/`<=$7.00` per-arm/combined,
`<=125`/`<=50`/`<=175` normalized credits, `<=250` hard breaker) — **unchanged, still fully gating.**
**Wakes-per-task is DEFERRED** — no documented per-model-decision observable exists in the Codex
JSONL stream (evidence: `reports/2026-07-21-gate0-wake-grounding.md`); it re-enters scope when Codex
ships a per-decision boundary event or a world-seam counter is built+gated. This is a documented
reduction of one of Cheap's two yardsticks for the FIRST gate, not a loosening of the cost bar.

Wakes/`wake_accounting` stay COMPUTED and REPORTED in the scorer's verdict (`wake_accounting.status
== "DEFERRED"`, plus a new `cheap_basis == "cost_per_task"` field) for the record, but never gate
`overall`. Scorer change lands on `feat/gate0-wake-accounting` (`eval/score_gate0.py`); its tests pin
the four synthetic verdicts: clean run within cost caps + wakes insufficient -> `PASS`/`GO`; same but
over a cost cap -> `FAIL_CHEAP` (cost bar unchanged, still bites); leak/constancy breach -> still
`NO_LEAK`/`CONSTANCY_BREACH`; capability `>2x` human -> still `FAIL_CAPABILITY`.

**Residual divergence, named (per adversarial review):** cost-per-task and decision-count can
diverge — a run with many cheap decisions passes on cost though it would exceed the old wake cap;
this is accepted because Gate 0's Cheap bar IS cost, and no working wake defense existed to weaken
(audit was already hardcoded fail-closed).

## Sources

Design doc `reports/2026-07-13-minimum-north-star-gate-0-design.md` (all cited lines above);
readiness report + scorer, PR #114 `codex/gate0-r0-w0-c0-readiness-2026-07-14` (OPEN, unmerged —
`reports/2026-07-14-gate0-readiness.md`, `eval/score_gate0.py`); `tools/check_gate0_codex.py`
(merged, on `main`); `tools/run_gate0_codex.ps1` (merged, on `main`); `HANDOFF.md` §1 (:842-866)
and current top block (:12-28); `reports/2026-07-05-northstar-capability-map.md` (:187-189);
`.claude/skills/gate-methodology/SKILL.md`, `.claude/skills/run-brief-authoring/SKILL.md`,
`.claude/skills/paid-run-harness/SKILL.md`, `.claude/skills/safety-invariants/SKILL.md`.
