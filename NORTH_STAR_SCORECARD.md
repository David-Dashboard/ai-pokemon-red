# North Star scorecard - 2026-07-14

This is the first rubric-backed baseline. It is not a claimed change from an earlier score.

## Scores

- **Engineering foundation: 75/100.** Four components, 25 points each:
  - **Architecture / seam: 20/25.** The fixed-brain/swappable-perceiver boundary is implemented,
    documented, and guarded; a controlled cross-world Gate 0 verdict has not yet audited it end to end.
  - **Screen/control + offline scoring: 20/25.** Screen-derived control paths and oracle-off-wire scorers
    exist across several worlds; R0/W0/C0 are still incomplete.
  - **Hermetic auth/tool/image/reproducibility: 20/25.** Both free handshakes now prove ChatGPT auth,
    exact CLI/image/code hashes, one MCP server, and exact per-arm tools; paid execution is not frozen.
  - **Cost/safety/eval operations: 15/25.** Pre-registration, one-attempt, held-out, append-only, and
    fail-closed practices exist; exact wake accounting and a live 250-credit breaker are missing.
- **Actual evidence / proof: 8/100.** Four North Star claims, 25 points each:
  - **Capability: 3/25.** Isolated banked successes exist, including MiniWoB click-button 5/5, but no
    controlled human-grade Red + MiniWoB Gate 0 verdict exists.
  - **Constancy: 1/25.** Historical isolated runs reused the brain pattern across worlds, but there is no
    frozen same-brain paired verdict that rules out configuration and bridge differences.
  - **Generality: 2/25.** GB/GBA/NDS/browser/ARC probes show breadth, but much of it is exploratory,
    bridged, or below human-grade completion.
  - **Cheap: 2/25.** Cost ledgers and one skill A/B batching result exist, but held-out skill compilation,
    exact wakes/task, and a live spend breaker are not proven.
- **Overall: 19/100.** `ceil(0.15 * engineering + 0.85 * proof)` =
  `ceil(0.15 * 75 + 0.85 * 8)` = `ceil(18.05)` = `19`. The 85% proof weight prevents engineering
  activity from masquerading as North Star progress.

The free handshakes add **zero proof points**. This slice buys readiness and interpretability, not
capability evidence.

## Milestone and critical path

- **Decisive milestone:** bank a controlled Gate 0 verdict with one fixed Codex brain on Red + MiniWoB.
- **Current blocker:** R0/W0/C0 are incomplete; exact wake accounting and a live 250-credit breaker must
  be proven before a frozen, reviewed paid pre-registration.
- **Critical path:** free handshake -> R0/W0/C0 -> frozen reviewed pre-registration -> one Red run + one
  MiniWoB run -> banked verdict.
- **Current Gate 0 spend:** `$0.00`; no model call.

## Historical usage manifest

These are disjoint API-reported or API-equivalent groups. They total exactly `$220.035810`.

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

Older summaries only support ranges or rounded reconstruction:

| Additional disjoint group | Amount | Tracked source / locator |
|---|---:|---|
| Early API runs | `$16.69-$17.34` | [HANDOFF](HANDOFF.md), early paid-run ledgers before the cross-console audit (~880-915) |
| Other Iteration 1 runs | `$9.740000` | [HANDOFF](HANDOFF.md), Iteration 1 run ledger excluding close + patience (~898-963) |
| Other entity-v2 runs | `$76.943528` | [HANDOFF](HANDOFF.md), entity-v2 history (`about $80` / seven-run `~$57` ledgers, ~685-721), excluding exact run 11 |
| Gate3D run 2 | `~$5.000000` | [HANDOFF](HANDOFF.md), Gate3D run ledger (~630-632); explicitly estimated and excluded above |
| Other day-2 probes | `~$5.120000` | [HANDOFF](HANDOFF.md), day-2 `~$66` ledger (~710-721), excluding separately listed disjoint groups |
| **Estimated additional subtotal** | **`$113.493528-$114.143528`** | Sum of rows above |

**Reconstructed API-equivalent total:** `$333.529338-$334.179338`.

This is **not exact cash spend**. Most runs after 2026-06-26 used subscription quota; the legacy `~$190`
ledger conflicts by about `$73`; exact all-time cash spend is unrecoverable from tracked summaries.
