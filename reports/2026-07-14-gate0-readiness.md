# Gate 0 R0/W0/C0 readiness verdict - 2026-07-14

## Verdict

| Gate | Verdict | Exact blocker |
|---|---|---|
| R0 - Pokemon Red | `INSUFFICIENT_SOURCE` | No same-start human baseline and no append-safe deterministic end-to-end Red readiness run. |
| W0 - MiniWoB DEV | `INSUFFICIENT_SOURCE` | No five-seed DEV run/human baseline for click-checkboxes. |
| C0 - constancy/accounting | `INSUFFICIENT_SOURCE` | No independently frozen expected pins, observable exact model-wake boundary, or mechanical live 250-credit breaker. |
| **Paid Gate 0** | **`NO_GO`** | R0, W0, and C0 must all be `GO`. |

This is a banked `$0` readiness verdict. It is not permission to run a model. No Codex execution,
paid-held-out seed, API key, or model was used.

## What this slice established

- `world_mcp.py` now logs Red's existing `ADDR_IS_IN_BATTLE` value in the offline `watch` oracle. It is
  joined by the first party member's current-HP bytes derived from existing `ADDR_PARTY_MON1 +
  OFF_CUR_HP`. These fields are not returned to the agent and change no tool or brain schema.
- `eval/score_gate0.py` is one fail-closed two-arm scorer. It calls
  `tools/check_gate0_codex.py::audit` for frozen receipt/artifact/constancy/no-leak checks before task
  scoring. It then scores:
  - Red: fresh party `0`, party `0 -> 1`, a later trainer battle, no zero player HP through battle exit,
    sustained exit on the same map, and movement after exit;
  - MiniWoB: reward `1.0` on every exact pinned episode/seed;
  - both arms: `<=2x` human wall-clock/actions, per-arm and combined wake/cost/credit caps, and the hard
    250-credit ceiling.
- Synthetic coverage proves `PASS`, arm capability failure, Cheap failure, infrastructure death,
  constancy breach, tool leak, and missing wake accounting. No synthetic result is capability evidence.
- Final canonical root-side verification passed: targeted readiness `64 passed`; full tracked plus scorer
  `1159 passed, 1 warning`; `git diff --check` passed. Both pytest runs used `uv run --frozen`.

## R0 - Red source status

`INSUFFICIENT_SOURCE`.

Positive source facts:

- `roms/PokemonRed.gb` and `runs/red_start.state` are present locally.
- The offline battle signal comes from `games/pokemon_red/memory_map.py::ADDR_IS_IN_BATTLE`, already used
  by the older Red run/scoring path.
- The scorer's synthetic clean trajectory proves the intended predicate is mechanically expressible
  once a new oracle exists. A regression fixture proves that same-map battle exit plus later movement
  still fails when player HP reaches zero. This is scorer validation, not an actual Red-run validation.

Unmet readiness facts:

- There is no human baseline from `runs/red_start.state` recording success, active/wall time, primitive
  button presses, and frames.
- No existing append-safe deterministic launcher completes fresh bedroom -> starter -> rival exit.
  `eval/capture_modes.py` and `eval/capture_battle.py` delete PNGs from fixed `runs/modes` and
  `runs/battle` directories before running; `eval/_archive/make_battle_state.py` builds a fixed battle
  fixture rather than the full readiness result. They were not run because raw artifacts are append-only.
- `runs/brain_red_starter/world/oracle.jsonl` proves party `0 -> 1` but predates the new `in_battle`
  watch field, so it cannot prove the full predicate and is not promoted.

## W0 - MiniWoB DEV source status

`INSUFFICIENT_SOURCE`.

Positive source facts:

- DEV seeds are frozen at `0..4` in `eval/fixtures/gate0_miniwob_dev_seeds.json` and are disjoint from
  paid-held-out `1000..1004`.
- Existing tests pin one-attempt seed advancement and oracle-only reward/seed/episode logging.
- The scorer requires exact seed order and reward `1.0` on 5/5 non-abandoned episodes.

Unmet readiness facts:

- There is no DEV `click-checkboxes` five-episode oracle artifact and no human baseline with wall time,
  clicks, region inspections, and corrections.
- `tools/preflight_gate0_miniwob.py` is deliberately hard-pinned to paid-held-out seeds `1000..1004`;
  running it would cross the held-out boundary and was not authorized or attempted.
- `runs/brain_miniwob/world/oracle.jsonl` is the older `click-button` task, lacks seed/episode fields,
  and is not evidence for click-checkboxes.

## C0 - constancy and accounting

`INSUFFICIENT_SOURCE`.

Final current-head free receipts:

- Red: `runs/gate0_readiness_2026-07-14/red-v3/handshake-receipt.json`, SHA-256
  `88a5a2d96f1a28218bc29e307b820706dfaef49820b6d6363ac4ad14601723e5`, immutable image
  `sha256:8701e664053f2984a4a3c5500ee8a997948def672372d569bf8fe8063ebe4318`.
- MiniWoB: `runs/gate0_readiness_2026-07-14/miniwob-v2/handshake-receipt.json`, SHA-256
  `0961c5c05d138ee917ee5632be0ee26971d46700c1f20801d473927bf496cc59`, immutable image
  `sha256:7128be603033f275eee7d13e4dd2c3a19349f0b354acd3203bc531528bb5f2cc`.

Root's property check passed common-brain equality, host/image code parity, and exact per-arm tool
inventories. Both receipts intentionally say `paid_execution_enabled=false` and
`NO_GO_INSUFFICIENT_WAKES`. This is current-head handshake evidence, not a full checker `GO`: there is no
independently frozen expected-pins JSON, so expected-vs-observed comparison remains unproved and no pins
were invented after observation.

The append-only MiniWoB compatibility attempt at
`runs/gate0_readiness_2026-07-14/miniwob-v1/` is preserved as an infrastructure failure. The first Red
watch implementation imported `games.pokemon_red.memory_map` at `world_mcp.py` module scope, but
`Dockerfile.miniwob` deliberately copies only `core/` plus `world_mcp.py`; MiniWoB therefore could not
import its server. The registry now keeps the Red-only addresses local as literals, matching the existing
watch style, while tests cross-check them against the memory-map constants. No Dockerfile or shared-world
abstraction was expanded. The final current-head handshakes supersede it; `miniwob-v1` is not reused.

Attempt ledger is append-only:

- `red-v1`: command resolution failed before an output directory or receipt existed.
- `red-v2`: valid pre-final-code receipt, superseded for current-head parity.
- `miniwob-v1`: cross-world import infrastructure failure; preserved and never reused.
- `red-v3` and `miniwob-v2`: final current-head free receipts above.

Negative claim receipt: no independently frozen expected-pins JSON exists. Searches of `tools/`, `eval/`,
`tests/`, and `reports/2026-07-13-minimum-north-star-gate-0-design.md` found no paid Codex launcher, documented exact
per-model-call wake boundary, or live normalized-credit breaker. `tools/run_gate0_codex.ps1` is handshake
only; `tools/check_gate0_codex.py` records aggregate token usage but returns `wakes=null` and
`wake_accounting=INSUFFICIENT_WAKES`. The only 250-credit references are the design bar and this scorer,
not an execution-time breaker. Turns, tool calls, and JSONL events are not substituted for wakes.

## North Star position and spend

- Overall: **19/100**.
- Engineering foundation: **76/100** (the offline two-arm scorer and Red battle oracle raise
  screen/control + scoring by one point; review is still pending).
- Actual evidence/proof: **8/100**. This work bought interpretability, not a brain result.
- Decisive milestone: one banked controlled Gate 0 verdict from the fixed Codex brain on Red + MiniWoB.
- Exact critical-path blocker: C0 independently frozen expected pins, exact wake accounting, and the live
  250-credit breaker. R0/W0 human baselines and safe DEV artifacts also remain required.
- Spend this slice: **`$0.00`**. Gate 0 cumulative spend remains **`$0.00`**.

## Next real experiment boundary

Do not perfect the harness beyond these blockers. Obtain the two human baselines and append-safe R0/W0
DEV artifacts; independently freeze expected pins; separately prove an observable wake boundary and live
250-credit breaker. When all three readiness gates are `GO`, freeze and adversarially review the
pre-registration, then ask David once for the paid/model Red + MiniWoB attempts.
