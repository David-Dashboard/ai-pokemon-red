# North Star scorecard - 2026-07-25

This reflects the 2026-07-24 re-score (proof 8/100 -> 18/100) as first proposed, further corrected
on 2026-07-25 after an adversarial fact-check found the Constancy and Cheap bumps overstated (see
the paired verdict report, `reports/2026-07-24-gate0-paired-verdict.md` §3/§4, revised). The doc now
IS a claimed change from an earlier score, not a first baseline.

## Scores

- **Engineering foundation: 76/100.** Four components, 25 points each:
  - **Architecture / seam: 20/25.** The fixed-brain/swappable-perceiver boundary is implemented,
    documented, and guarded; a controlled cross-world Gate 0 verdict has not yet audited it end to end.
  - **Screen/control + offline scoring: 21/25.** The single fail-closed Gate 0 scorer and Red battle
    oracle now exist; live R0/W0 sources and human baselines are still incomplete.
  - **Hermetic auth/tool/image/reproducibility: 20/25.** Both free handshakes now prove ChatGPT auth,
    exact CLI/image/code hashes, one MCP server, and exact per-arm tools; paid execution is not frozen.
  - **Cost/safety/eval operations: 15/25.** Pre-registration, one-attempt, held-out, append-only, and
    fail-closed practices exist; independently frozen expected pins and a proven live-breaker
    dry-run TRIP receipt are still missing at signature/launch time. Exact per-decision wake
    accounting is no longer a tracked gap here — it is DEFERRED (David's decision, 2026-07-21):
    Codex's JSONL stream has no per-model-decision observable
    (`reports/2026-07-21-gate0-wake-grounding.md`), so Gate 0's scorer now grounds Cheap on
    cost-per-task instead and reports wakes informationally, never gating.
- **Actual evidence / proof: 14/100** (was 8/100 — re-scored 2026-07-24, corrected 2026-07-25, see
  note below). Four North Star claims, 25 points each:
  - **Capability: 5/25** (was 3/25). **2026-07-24 update:** the FIRST completed, frozen-predicate-
    scored, two-arm paid Gate 0 attempt now exists (`reports/2026-07-24-gate0-paired-verdict.md`,
    `reports/2026-07-24-gate0-armR-verdict.md`, PR #161) — both `_red_success`/`_miniwob_success`
    re-verified `FAIL`. This moves the axis off "no controlled run has ever completed" (the prior
    3/25 basis) without claiming capability is proven: Red beat the human baseline on wall-clock and
    actions but missed the anti-false-victory tail (a measurement-shaped miss, task likely actually
    done); MiniWoB solved 4/5 held-out seeds at reward 1.0 with one genuine partial (0.667). Isolated
    banked successes (MiniWoB click-button 5/5) still stand as separate, smaller evidence.
  - **Constancy: 4/25** (was 1/25). **2026-07-24 update, corrected 2026-07-25:**
    `tools/check_gate0_codex.py::compare_constancy` ran, for the first time ever, against real Red +
    MiniWoB peer receipts from the same banked attempt — clean, zero mismatches across all 9
    `CONSTANCY_FIELDS`. An adversarial fact-check on 2026-07-25 found the initial +6 bump (to 7/25)
    overclaimed what this establishes — full diagnosis in the paired verdict report §3 (revised). 4
    of the 9 matching fields are hardcoded string literals that cannot differ between any two
    receipts this launcher emits; `brain_config_sha256` cannot differ given the same launcher build
    + `--model`; `codex_path` matching is guaranteed by same-machine execution. That leaves roughly
    three genuinely independent facts (`codex_version`, `codex_executable_sha256`, and
    `planned_model` — itself the operator-supplied `--model` argument, not an observed model
    identity), not nine, and the two arms ran ~7h40m apart with no observability into that gap. This
    is a **launch-configuration consistency check, substantially tautological by construction**, not
    a measurement of brain sameness — worth a modest bump (a check this tautological cannot
    reasonably be worth more than ~5/25), landing at 4/25 (+3, not +6). It still rules out Codex-CLI
    auto-update drift and a model-flag change across that gap, and does not speak to
    behavioral/performance equivalence — both arms still FAILed their predicates, by different
    mechanisms.
  - **Generality: 2/25 — unchanged.** GB/GBA/NDS/browser/ARC probes show breadth, but much of it is
    exploratory, bridged, or below human-grade completion. **2026-07-24 evidence note (no score
    change):** the same paired attempt drove two of the most different world classes in the probe
    set (GB emulator vs. browser DOM) through one harness end to end, but both arms scored below the
    frozen bar, so per this report's own instruction not to inflate, the number stays put — only the
    evidence base is larger.
  - **Cheap: 3/25** (was 2/25). **2026-07-24 update, corrected 2026-07-25:** a real two-arm paid
    attempt landed combined `$1.4455`/`36.14` credits, ~5x under the `$7.00`/`175`-credit PASS bar,
    nowhere near the 250-credit hard breaker (`reports/2026-07-24-gate0-paired-verdict.md` §2c) —
    this particular run was cheap. An adversarial fact-check on 2026-07-25 found the original +2
    bump (to 4/25) overclaimed what this shows: it is **not** "genuine evidence the cost mechanism
    holds under a real spend" — the breaker never fired, and its proof artifact
    (`live_breaker_dry_run_trip.json`) is absent; the only file at that path is a 2026-07-22 dry-run
    ledger reading `consumed_normalized_credits: 0` that doesn't describe this attempt. Cut to a
    smaller +1 instead, because: (1) **the frozen scorer never evaluated Cheap** —
    `score_gate0.py`'s Cheap block is gated on `source` failures being empty, and `source` was
    non-empty this attempt, so the number is a hand computation, not a scorer verdict (paired verdict
    §2c/§4); (2) the figures come from `agent_metrics.json`, whose integrity pins are still
    `PENDING_NOT_YET_CAPTURED_paid_attempt_not_run` — unpinned, launcher-self-reported, never
    hash-verified; (3) this run's cheapness is partly *caused by* its failure mode — Red declared
    victory and stopped acting, so `$0.4159` partly reflects a prematurely-terminated run, not
    efficient task completion. Held-out skill compilation remains unproven, unchanged.
- **Overall: 24/100** (was 19/100). `ceil(0.15 * engineering + 0.85 * proof)` =
  `ceil(0.15 * 76 + 0.85 * 14)` = `ceil(23.3)` = `24`. The 85% proof weight prevents engineering
  activity from masquerading as North Star progress.

  **Re-score provenance (2026-07-24, corrected 2026-07-25):** these deltas were proposed by the
  session that banked the first paired Gate 0 verdict (`reports/2026-07-24-gate0-paired-verdict.md`),
  per that task's own instruction to re-score honestly rather than leave stale "no controlled run has
  ever completed" language in place, while explicitly not inflating Capability/Generality past FAIL.
  An adversarial fact-check on 2026-07-25 found the Constancy and Cheap bumps overclaimed (see those
  entries above, and the paired verdict report §3/§4, revised) and corrected them: Constancy +6 -> +3
  (7/25 -> 4/25), Cheap +2 -> +1 (4/25 -> 3/25). Capability and Generality deltas were unaffected. The
  rubric is inherently judgment-based — **David should sanity-check these specific point deltas**
  (current: Capability +2, Constancy +3, Generality +0, Cheap +1) against his own read of the
  evidence; nothing here should be treated as a mechanically-derived or final number.

The free handshakes and R0/W0/C0 scorer add **zero proof points**. This slice buys readiness and
interpretability, not capability evidence.

## Milestone and critical path

- **Decisive milestone: DONE, verdict FAIL.** A controlled, banked, paired Gate 0 verdict with one
  fixed Codex brain on Red + MiniWoB now exists (2026-07-24,
  `reports/2026-07-24-gate0-paired-verdict.md`, PR #161) — both frozen predicates FAILed (§1/§2
  there), Cheap PASSed, and the between-arms Constancy check ran clean for the first time. This
  milestone is spent, banked as-is; it is not "not yet reached," it is "reached and did not clear
  the capability bar."
- **Current blocker (next milestone):** the paid-seed MiniWoB human baseline is still PENDING
  (`gate0_paid_source_pins.json`'s `artifact_sha256.miniwob_human` placeholder) — required before
  Arm W's `≤2×human` bars and the full frozen `score_manifest()` verdict are computable
  (`reports/2026-07-24-gate0-paired-verdict.md` §9). Separately, `red_agent`/`miniwob_agent`/
  `wake_boundary` artifact-hash pins need re-freezing against the now-real files, and the
  `live_breaker` proof-artifact path is missing for this attempt — both fixture/pin maintenance,
  same report §4/§9. A vNext capability attempt (fresh pre-registration required, task text is
  hash-pinned) is undecided — David's call, candidates listed in the paired verdict §10.
- **Critical path (next lap):** freeze the MiniWoB paid-seed human baseline -> re-freeze the
  agent/wake-boundary/live-breaker pins -> full `score_manifest()` verdict computable -> David
  decides on a vNext capability attempt (or bank as the proof-floor baseline).
- **Current Gate 0 spend:** `$1.4455` combined (`$0.41589` Red + `$1.02958` MiniWoB), the first real
  model spend against Gate 0 (2026-07-24) — see the paired verdict §2c. (Prior `$0.00`/"no model
  call" line described the pre-paid-attempt state; that state is now superseded.)

## Historical usage manifest

These are disjoint reported/API-equivalent groups. They total exactly `$220.035810`; that is an
accounting subtotal, **not historical cash spend**.

| Disjoint group | Amount | Tracked source / locator |
|---|---:|---|
| Iteration 1 close + patience | `$5.210000` | [HANDOFF](HANDOFF.md), Red It1 close and patience blocks (~898, ~947-963: `$3.66 + $1.55`) |
| Emerald + Kirby | `$2.560000` | [HANDOFF](HANDOFF.md), cross-console audit run ledger (~924, ~928) |
| ADR-002 invalid + valid | `$7.040000` | [HANDOFF](HANDOFF.md), ADR-002 gate blocks (~738, ~753-765) |
| Entity v1 | `$4.020000` | [HANDOFF](HANDOFF.md), entity-grounding v1 block (~713-751) |
| Entity v2 run 11 | `$3.056472` | [entity-v3 design](reports/2026-07-03-kirby-skill-port-entity-v3.md), `--max-turns` receipt (~384-386) |
| GBA sweep | `$3.880000` | [HANDOFF](HANDOFF.md), paid GBA probe sweep (~710) |
| MiniWoB click-button | `$1.3557615` | [Gate 0 design](reports/2026-07-13-minimum-north-star-gate-0-design.md), banked result (~65-69) |
| Gate3D runs 1 + 3 | `$85.870000` | [HANDOFF](HANDOFF.md), Gate3D ledger (~626-632: `$3.01 + $82.86`); estimated run 2 excluded |
| ARC first three | `$36.400000` | [HANDOFF](HANDOFF.md), ARC wall / paid ledger (~556-561) |
| Skill A/B | `$16.607135` | [skill rung-1 verdict](reports/2026-07-03-skill-rung1-ab-verdict.md), cost ledger (~43) |
| Entity v3 | `$4.317600` | [entity-v3 verdict](reports/2026-07-03-entity-v3-verdict.md), run facts (~38-40) |
| Entity v3.1 | `$5.190000` | [entity-v3.1 verdict](reports/2026-07-04-entity-v3.1-verdict.md), ledger (~68-70) |
| Kirby longhaul | `$42.980000` | [HANDOFF](HANDOFF.md), long-horizon banked run (~323-340) |
| MKDS A/B | `$1.5488415` | [MKDS verdict](reports/2026-07-13-mkds-ab-verdict.md), total cost (~30-37) |
| **Exact/API-equivalent subtotal** | **`$220.035810`** | Sum of rows above |

### Early API-era audit and dedupe

The tracked early-run records support these constituents:

- **Runs #1-12: `~$6.85`.** [HANDOFF](HANDOFF.md), early live-run accounting (~2128-2178) lists
  `~$3 + $0.23 + $0.33 + $0.11 + $0.83 + $0 + $0.25 + $0.30 + $0.40 + $0.30 + $0.30 + $0.30 + $0.50`.
  [LEARNINGS](reports/LEARNINGS.md), the battle-run chronology, corroborates the run identities/outcomes.
- **Pre-run work before the numbered ledger: `~$0.66`.** The same [HANDOFF](HANDOFF.md) accounting
  (~2172-2179) reports this separately; it is not assigned to or duplicated in runs #1-12.
- **Runs #13-17: `~$2.05-$2.70`.** The five run-ID-disjoint archived reports give:
  [#13](reports/_archive/2026-06-20-live-run-13-battle-auto-advance.md) `~$0.15-$0.20`,
  [#14](reports/_archive/2026-06-20-live-run-14.md) `~$0.10`,
  [#15](reports/_archive/2026-06-20-live-run-15.md) `~$0.60-$0.80`,
  [#16](reports/_archive/2026-06-20-live-run-16-interior-nav-drift-fix-end-to-end-re-run.md)
  `~$0.60-$0.80`, and
  [#17](reports/_archive/2026-06-20-live-run-17-affordance-layer-probe-saliency-got-the-starter.md)
  `~$0.60-$0.80`.
- **Auditable early through-#17 band: `~$9.56-$10.21`.** This is pre-run `$0.66` + numbered runs #1-17.
  Those records do not overlap the 2026-07-02 Iteration-1 close/patience row in the exact manifest.

The prior `$16.69-$17.34` "early API" bucket and `$9.74` "other Iteration 1" bucket are removed: tracked
summaries do not expose their constituents or prove that they exclude runs #1-17, each other, and the
exact close/patience row. They are not added to any precise subtotal.

### Rounded additional estimates

- Other entity-v2 attempts: **about `$77`** ([HANDOFF](HANDOFF.md), entity-v2 `about $80` history and
  seven-run `~$57` ledger, ~685-721), excluding the exact `$3.056472` run-11 row.
- Gate3D run 2: **about `$5`** ([HANDOFF](HANDOFF.md), Gate3D ledger ~630-632); excluded from the exact
  Gate3D row.
- Other day-2 probes: **about `$5`** ([HANDOFF](HANDOFF.md), rounded day-2 `~$66` ledger ~710-721), after
  the separately listed entity/GBA/MiniWoB groups.

Combining the exact `$220.04` subtotal with only the auditable early band and these rounded additions
supports a **rough API-equivalent lower reconstruction of about `$317`**. Allowing for unresolved legacy
summary buckets yields only a **broad rough range of about `$317-$334`**, not a six-decimal total.

This is **reported/API-equivalent usage, not exact cash spend**. Most runs after 2026-06-26 used
subscription quota; the legacy `~$190` ledger conflicts materially with the reconstruction; exact all-time
cash spend is unrecoverable from tracked summaries.
