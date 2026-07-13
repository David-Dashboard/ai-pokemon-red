# Entity v5 candidate shortlist - multi-scenario source-status (2026-07-13)

Status: **$0 docs/read-only shortlist**. No paid run, no v5
pre-registration, no scorer/code/tool-schema edit.

## Question

Which candidate worlds or scenarios deserve the next cheap source-status probe
before any entity-gate v5 spend?

This answers the one-scenario concern directly:

- One scenario is enough to **kill** a bad candidate cheaply.
- One scenario is not enough to **escalate** to a paid gate unless the
  pre-registration explicitly accepts a narrow, single-scenario claim.
- For v5, the safer rule is: screen several candidate scenarios first, then
  pre-register only after at least two source-status candidates pass the same
  bar, ideally from different dev games or at least different mechanics.

## Bar being screened

This shortlist uses the v5 design in
`reports/2026-07-13-entity-v5-bar-redesign.md` as the filter:

- Threat visibility: at least 4 of 5 scripted drops need a visible/near threat
  opportunity in the backward window `[d-6, d-1]`.
- Consequence supply: at least 5 drops, at least 30 scoreable steps, and no
  death spiral.
- Benign/rejection arm: one plausible comparator in the same segment/action
  regime, not distant scenery.
- Mechanism guard: one qualifying conditional predicate matched to the world.
- Oracle/tool readiness: enough offline truth to score drops and audit claims.
- Held-out hygiene: do not develop or tune on held-out games.

The held-out list in `eval/dataset_split.py` is Crystalis, Link's Awakening,
Super Mario Land, F-1 Race, and Doom. Those are excluded from v5 development.

## Shortlist

| Candidate | Status | Reason | Next receipt before spend |
|---|---|---|---|
| `kirby_dreamland` old `kirby_entity2.state` | **Dead as primary v5 candidate** | It has an HP oracle and the real v3.1 run banked 5 drops, but the v4 cascade showed hostile geometry: honest NEAR timing fights the camping ceiling, later clusters have only 0-1 press of lead, cadence is unresolved, and no plausible benign comparator was found. | None recommended. Do not spend here. |
| `kirby_dreamland` door/sub-room | **Dead as-is** | The door is real and `move_blocked` works, but the 2026-07-13 probe found no hp=6 near-door seed, only 3 non-death drops before death, poor retreat geometry, and no plausible benign comparator. | Only revive if a fresh hp=6 near-door state is manually captured and then passes consequence-supply plus decoy checks. Not the top path. |
| `cave_noire` controlled combat/corridor | **Top source-status candidate** | It is a dev game, already has an HP oracle at `0xC120`, fixed-screen geometry, region tools, and likely walls/props/items that can supply a real comparator. But v1 failed with only 2 drops and enemy-initiative damage, so this cannot be trusted without a fresh controlled source-status probe. | Run a $0 probe across at least two starts/routes. Prove 5+ drops, visible pre-drop threats in `[d-6,d-1]`, a plausible comparator, and a usable mechanism predicate. |
| `gauntlet` | **Defer** | It is a dev GB world with enemies/props, but `world_mcp.py` currently watches only x/y, not HP or another consequence signal. A v5 entity gate needs a consequence oracle before source-status is meaningful. | First do an oracle-readiness hunt: health/damage/score/terminal signal and whether repeated controlled drops exist. |
| `gb_generic` side-scroller candidates, e.g. Metroid-style worlds | **Defer** | They may offer slower or more legible enemies than Kirby, but the generic GB registry has no consequence watch. Side-scrollers may also repeat Kirby's contact-rusher failure mode. | First identify a dev-side-scroller ROM/state with a consequence oracle and slower visible threats. |
| `kirby_gba` / `emerald_gba` | **Defer** | GBA registry entries have no watch oracle, and comments note mGBA is not importable on Windows until lazy construction. Good future lane, bad first v5 candidate. | Separate GBA oracle-readiness pass; no entity v5 spend before that. |
| `nds` / MKDS | **Defer for entity v5** | NDS is valuable for real-time/continuous-action work, but the registry watch is empty and MKDS progress is not a threat/entity consequence. This lane buys A1/A5/A6 better than A2 entity grounding. | Keep for continuous-time gates unless a concrete damage/entity scenario is found. |
| MiniWoB tasks | **Not this gate** | Computer-use widgets can exercise naming and rejection, but they do not supply the threat/consequence structure v5 is trying to measure. | Save for named-layer/computer-use gates, not entity v5. |
| Doom/VizDoom | **Do not use for v5 development** | Doom is held-out by `eval/dataset_split.py`, and the current Doom work is a 3D/conditional-reflex lane, not this v5 entity bar. | None. Do not tune v5 here. |
| `pokemon_red` | **Not first** | The registry has map/party/badge watches, not battle HP. Overworld Red does not naturally provide repeated visible threat drops for this bar. | Better for named-place A2 work than v5 entity consequence attribution. |

## Recommended next probe

Run a **Cave Noire controlled-combat source-status probe** next, still $0 and
not a pre-registration.

Minimum shape:

1. Test at least two starts/routes, not one room.
2. Log HP/consequence drops from the existing `0xC120` oracle.
3. For each drop, save a screen receipt for whether a threat was visibly near
   in `[d-6, d-1]`.
4. Require at least 5 drops and 30 scoreable steps without death spiral.
5. Name one plausible benign comparator in the same segment/action regime.
6. Check one mechanism predicate, probably a blocked-movement or region-change
   predicate only if it survives idle/movement false-fire checks.
7. Paper-score honest and adversarial typed-claim schedules before any paid
   brief is drafted.

If Cave Noire passes only one start/route, keep it as a candidate but do not
escalate. If two Cave Noire routes pass, v5 still has only same-game evidence;
that may be enough for a narrow Cave-Noire-v5 gate, but not for a generality
claim. If David wants multi-game evidence first, the next work is an
oracle-readiness audit for Gauntlet / GB-generic side-scrollers / GBA worlds,
not a paid run.

## Decision

Do **not** pre-register entity v5 yet.

The next useful work is one cheap source-status probe on Cave Noire, explicitly
multi-route. Kirby is killed as the primary path for now; the other games are
not rejected as ideas, but they lack the consequence/oracle receipts needed to
be first in line.

## Sources read

- `reports/2026-07-13-entity-v5-bar-redesign.md`
- `reports/2026-07-13-kirby-door-probe.md`
- `reports/2026-07-11-entity-v4-verdict.md`
- `reports/2026-07-11-entity-v4-coverage-papercheck.md`
- `reports/2026-07-11-entity-v4-visibility-probe.md`
- `reports/2026-07-11-entity-v4-instrument-hunt.md`
- `reports/2026-07-05-entity-v4-d-probe.md`
- `reports/2026-07-03-entity-gate-v2-plan.md`
- `reports/2026-07-04-entity-v3.1-verdict.md`
- `reports/2026-07-05-northstar-capability-map.md`
- `eval/dataset_split.py`
- `world_mcp.py`
