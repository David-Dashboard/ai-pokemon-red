# North Star scorecard - 2026-07-14

This is the first rubric-backed baseline. It is not a claimed change from an earlier score.

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
- **Actual evidence / proof: 8/100.** Four North Star claims, 25 points each:
  - **Capability: 3/25.** Isolated banked successes exist, including MiniWoB click-button 5/5, but no
    controlled human-grade Red + MiniWoB Gate 0 verdict exists.
  - **Constancy: 1/25.** Historical isolated runs reused the brain pattern across worlds, but there is no
    frozen same-brain paired verdict that rules out configuration and bridge differences.
  - **Generality: 2/25.** GB/GBA/NDS/browser/ARC probes show breadth, but much of it is exploratory,
    bridged, or below human-grade completion.
  - **Cheap: 2/25.** Cost ledgers and one skill A/B batching result exist, but held-out skill compilation
    and a live spend breaker are not proven. For Gate 0 specifically, Cheap is grounded on cost-per-task
    ($-cost caps + the live credit breaker); wakes-per-task is DEFERRED — no per-model-decision
    observable exists in Codex's JSONL stream (`reports/2026-07-21-gate0-wake-grounding.md`) — and
    re-enters scope per the capability-map tripwire (`reports/2026-07-05-northstar-capability-map.md`
    §B3). This is a documented reduction of one of Cheap's two yardsticks for the first gate, not a
    loosening of the cost bar.
- **Overall: 19/100.** `ceil(0.15 * engineering + 0.85 * proof)` =
  `ceil(0.15 * 76 + 0.85 * 8)` = `ceil(18.20)` = `19`. The 85% proof weight prevents engineering
  activity from masquerading as North Star progress.

The free handshakes and R0/W0/C0 scorer add **zero proof points**. This slice buys readiness and
interpretability, not capability evidence.

## Milestone and critical path

- **Decisive milestone:** bank a controlled Gate 0 verdict with one fixed Codex brain on Red + MiniWoB.
- **Current blocker:** signature-time and launch-time items only — C0 lacks an independently frozen
  expected-pins JSON and a proven live-breaker dry-run TRIP receipt; R0/W0 lack human baselines and
  append-safe DEV artifacts. (Exact wake accounting is no longer on this list: it is DEFERRED, not a
  blocker — Gate 0's Cheap axis is grounded on cost-per-task instead, see the Cheap sub-score above.)
  Current-head image/free-handshake parity now passes. All remaining items are required before a
  frozen, reviewed pre-registration.
- **Critical path:** free handshake -> R0/W0/C0 -> frozen reviewed pre-registration -> one Red run + one
  MiniWoB run -> banked verdict.
- **Current Gate 0 spend:** `$0.00`; no model call.

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
