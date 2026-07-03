# 2026-07-04 — ViZDoom 3D sensorimotor floor: minimal tier + pre-registered gate

Design + gate plan only — **no primitives are built by this pass**. Scope discipline: ADR-002 §11
("build ONLY the 2-3 primitives the gate needs"), the North Eye constitution (7-slot contract, Realizer
Ladder R0-first), and the house pre-registration style of `reports/2026-07-03-adr002-gate-plan.md` /
`reports/2026-07-03-entity-gate-v2-plan.md`. Evidence base: `runs/vizdoom_probe/PROBE_REPORT.md` +
`analysis_results.json` (2026-07-02 offline probe, `vizdoom==1.3.0` in Docker) plus one new free
analysis run for this doc (§1.3 below; script output `runs/vizdoom_probe/stationary_mover_check_full.json`,
gitignored like the rest of `runs/`).

## 0. What the probe established (the re-tier ADR-002 §10 predicted)

| 2D primitive | 3D verdict | Consequence for this design |
|---|---|---|
| Blob-segment (`core/blob.py` RollingBg) | **DEAD** — 40-245 phantom blobs/frame from texture parallax; rolling-median background never converges under a moving camera | Do NOT port. Movers must come from a different mechanism (§1.3). |
| `best_shift` ego-motion | **DEAD and silently wrong** — reported "none" on 190/200 tics of continuous real rotation. Also: its dx range hit the `max_shift=18` cap exactly (`[-2, 18]`), i.e. the true per-action yaw shift *exceeds the search window* — a second silent failure mode on top of the projective-warp mismatch | Replace for 3D with a 1D horizontal-band estimator with a wide search and an explicit `None` (§1.1). "Silently wrong" is the cardinal sin (North Eye rule 5); the new primitive's contract centres on failing loudly. |
| Frame-diff | **DEGRADED globally, alive when gated** — `basic` mean 13.4 every tick (no idle baseline); but see §1.3: on genuinely ego-stationary pairs the baseline collapses to ~0.8 | Usable ONLY behind an ego-stationary gate. |
| Perceptual hash | survives weakly | Keep as-is (already in core/); no work needed for this gate. |

Integration facts carried forward (probe §"Integration facts"): multi-hot button vectors;
`make_action(action, tics)` frame-skip; **default cfgs do not expose KILLCOUNT** (a custom `.cfg` or
`set_available_game_variables` is required for the oracle); `get_state()` returns `None` after
episode end — every read must guard it; pin `ScreenFormat.RGB24` + `RES_320X240` explicitly.

---

## 1. The minimal 3D floor tier

Verdict up front: **build exactly two primitives** — P1 `YawBandFlow` and P2 `StationaryMovers`.
The forward-motion cue (c below) and the center-column depth proxy (d) are evaluated and **deferred
post-gate**: the gate scenario (§2) requires facing + shooting, not approaching, so building them now
is the §11 "over-build the sensorium before the gate" tripwire by definition.

### 1.1 P1 — `YawBandFlow` (ego-rotation: am I turning, which way, how fast) — BUILD

7-slot contract (North Eye):

1. **Computational.** Answers "what changed — how did I move?" restricted to yaw: direction + rate of
   my own rotation. Serves the decision "turn until the target azimuth is centered" and gates P2.
   Minimal and task-relative — NOT scene reconstruction, not full 6-DoF pose.
2. **Grounding (action↔sensor, self-calibrating).** In ViZDoom, `TURN_LEFT` rotates the view left, so
   the world image streams **rightward** (+dx). The binding is checked live: issue a known turn, the
   sign of the measured band shift must match; the px-per-turn-tic scale constant is regressed
   within-run from commanded turns vs measured shifts (never hand-set — the `fg_grid=58` sin).
   Disagreement drops confidence toward `None` rather than emitting a value. Within-run only; the
   calibration is wiped at session end (learning-boundary law).
3. **Algorithmic.** Collapse a mid-screen horizontal band (rows ≈ 0.35H–0.65H — excludes the weapon
   sprite at bottom and ceiling at top) to a 1D column-mean intensity profile; 1D cross-correlation of
   consecutive profiles over shifts ±64px (1D is cheap, so the window can be wide — directly fixes the
   probe's clipped `max_shift=18`). Value = argmax shift; confidence = normalized peak prominence
   (margin of best over second-best non-adjacent peak); `None` when prominence is below a floor
   **pinned by the offline fixture probe** (PR-2, §4), not hand-chosen.
4. **Implementational.** R0: numpy only. Explicitly swappable to R1 (Farnebäck / Lucas–Kanade
   horizontal component) if the R0 rung fails the fixture bar — measure-first, climb-on-evidence.
5. **Output contract.** `{dx_px: int | None, direction: "left"|"right"|"none" | None, deg_per_step:
   float | None, confidence: float}`. Three-valued honesty: `"none"` = *confidently stationary*;
   `None` = *cannot tell* (ambiguous correlation, e.g. a blank wall filling the band). `best_shift`'s
   probe failure was exactly conflating these two — a naive consumer read "sensor can't express this
   warp" as "not moving". Fabricating a value when the peak is flat is forbidden.
6. **Layer & composition.** L1 signal (numbers, not nouns). Consumes L0 frames; produced signal is
   consumed by P2's gate, the seam payload (§3), and any future odometry.
7. **Selection.** The world activates it by grounding payoff: in a 2D scroll world commanded turns
   don't exist / don't correlate, so it self-reports low payoff and is ignored. No hand-label
   ("this is a 3D game") anywhere — the `MoveSignal` sin.

Expected-to-work evidence: rotation in `defend_the_center` produced consistent, *large* horizontal
translation (the 2D search saturated its cap at +18 rather than finding nothing), and the fixture
frames exist to verify before any live wiring.

### 1.2 P2 — `StationaryMovers` (mover segmentation gated on ego-stationary) — BUILD

1. **Computational.** Answers "what is here (that moves and isn't me)?" — the azimuth (px offset from
   screen center, degrees once P1's scale is calibrated) of salient movers. Serves the decision "face
   that, then attack". Explicitly NOT "detect monsters" — it reports moving/animating blobs; the brain
   hypothesizes what they mean (L3 stays upstairs, per ADR-002).
2. **Grounding.** Two loops: (i) **gate honesty** — it only fires on ego-stationary frame pairs
   (no motion action issued between the frames AND P1 reports `"none"` with adequate confidence);
   (ii) **azimuth honesty** — turning toward a reported mover by its azimuth must drive that
   azimuth toward 0 (action↔sensor, self-checking, no oracle). The brain performs (ii) live; the
   scorer never needs it.
3. **Algorithmic.** Consecutive-frame abs-diff on gated pairs → threshold → 4-connected components
   (reuse the labeling pattern of `core/blob.py::_label_bfs`; do NOT reuse `RollingBg`, which is
   structurally dead in 3D) → drop fragments below `min_area` → merge near-overlapping boxes → top-K
   (K=5) by area, each with `{azimuth_px, azimuth_deg|None, area, bbox, confidence}`.
4. **Implementational.** R0 numpy. Thresholds (`pix_t`, `min_area`) pinned from the fixture data
   (§1.3 gives the starting point: `pix_t≈25/255`, `min_area≈30` at 320×240), verified by the offline
   probe in PR-2, and documented as fixture-derived — not free parameters to twiddle later.
5. **Output contract.** When the gate is CLOSED (ego-motion in progress or P1 uncertain): returns
   `None` with reason `"not ego-stationary"` — **never a fabricated mover list**. When open: possibly
   an empty list (confidently "nothing moving") — again distinct from `None`.
6. **Layer.** L1/L2 boundary (a tracked blob with an azimuth, still meaning-free). Consumes L0 frames
   + P1 + the action echo.
7. **Selection.** Pays off only where movers predict consequences; in a static-screen world it returns
   empty forever and costs nothing. Self-gating, no hand-label.

### 1.3 Quantified: do movers pop out of the noise when ego-stationary? (new free analysis)

The probe's headline "frame-diff mean 13.4 even standing still" is a *global* number over a scripted
run that was turning most of the time. Re-analysis over **all 199 consecutive pairs** of the same 200
`defend_the_center` frames (threshold `pix_t=25/255`, `min_area=30`, 4-connectivity; split by global
mean diff < 3.0 = ego-stationary — the scripted round-robin left 34 such pairs). The medians below are
computed over the FULL split and match `runs/vizdoom_probe/stationary_mover_check_full.json` exactly
(a first draft of this table quoted medians from a 12+6-pair sample against the full-split pair counts
— caught in review, regenerated over all pairs; the old `stationary_mover_check.json` is superseded):

| Regime | pairs | global diff mean | frac pixels changed (median) | components ≥ 30px (median) |
|---|---|---|---|---|
| Ego-stationary | 34 | **0.76** | **0.0109** | **4.5** |
| Turning | 165 | 9.50 | 0.0758 | 19 |

On stationary pairs the residual diff concentrates into a handful of compact blobs (top areas ~80-150px
— consistent with the approaching zombiemen + weapon idle), i.e. **≈7× separation in changed-pixel
fraction and ≈4× in component count**. This is a directional signal from ONE scripted run, not a
threshold-calibration dataset — PR-B's fixture probe re-derives `pix_t`/`min_area` on its own committed
fixtures rather than inheriting these constants as settled. The mechanism is viable *when gated*;
ungated it is exactly the probe's 40-105 phantom-blob failure.

**Honest caveat → pre-check PC-1 (§2.4):** `defend_the_center`'s monsters *walk toward you*;
`basic`'s monster mostly stands still and only its idle/animation frames produce diff. Whether that
animation clears `min_area=30` on stationary pairs in the *gate* scenario is checked FREE from
captured frames before anything is built on it.

### 1.4 Evaluated and DEFERRED (post-gate)

- **(c) Forward-motion cue** (`ForwardStreamCue`): radial expansion / floor-texture streaming; R0
  sketch = best zoom factor z∈[1.00, 1.06] matching the previous center crop to the current frame
  (looming), value+confidence+`None`, grounded by "issue MOVE_FORWARD → z > 1". Contract slots fill
  cleanly, but the gate scenario needs no approach (hitscan weapon, single room), so building it now
  is over-building. First candidate for the tier's second gate (a navigate-to scenario).
- **(d) Center-column depth proxy**: height of the floor/wall boundary in the center column as a
  monotone range proxy. R0-cheap but serves no decision the gate asks; same deferral.

---

## 2. THE GATE — pre-registered before any build

**Riskiest claim:** a region-neutral brain over the MCP seam, given ONLY this minimal symbolic 3D
floor (no screenshot, no game variables on the wire), can complete `basic` (find + shoot the monster)
at a better-than-random rate, cheaply. If that fails, the 3D floor tier dies cheap here — before any
sensorium build-out, exactly as ADR-002 §9 died-or-passed for HUD grounding.

### 2.1 Scenario (pinned)

- **`scenarios/basic_gate.cfg`** (new, committed): `basic.wad`, but —
  - `available_buttons = { TURN_LEFT, TURN_RIGHT, ATTACK }` (turns replace the default strafes so P1
    is actually load-bearing; MOVE_FORWARD deliberately excluded — no forward cue exists in the tier).
  - `available_game_variables = { HEALTH, AMMO2, KILLCOUNT }` — the probe established defaults do NOT
    expose KILLCOUNT; the custom cfg is the fix. These are the **oracle, logged server-side to
    `oracle.jsonl` only, never on the wire** (no-leak law, unchanged).
  - `episode_timeout = 300` tics, screen pinned `RGB24` / `RES_320X240`, `set_window_visible(False)`,
    frame-skip via `tics` per action (default 4).
- Runtime: Docker `python:3.11-slim` + `vizdoom==1.3.0` (the probe's proven recipe; WSL py3.8 is a
  known dead end).

### 2.2 The pinned gate statement (verbatim; constants final; stricter-only thereafter)

> **GATE-3D (pre-registered 2026-07-04).** A region-neutral brain over the MCP seam, receiving only
> the symbolic 3D-floor payload (P1 yaw + P2 movers + episode status; no screenshot, no game
> variables), plays `basic_gate.cfg` for **N = 30 episodes** on **30 distinct pinned seeds**, at most
> **40 brain decisions per episode** (System-1 tool calls execute between decisions). **Action grain
> is pinned equal across arms and baselines: every action executes with `tics = 4` fixed** — the gate
> world's tools take no `tics` parameter — so brain and scripted policies share the identical
> 300-tic / ~75-action-step episode budget, and R is measured under that same budget.
>
> **ARM (a) — task.** `kill_rate` = (episodes with oracle `KILLCOUNT ≥ 1` before the 300-tic
> timeout) / 30. PASS requires `kill_rate ≥ max(0.60, R + 0.30)`, where **R** = the random-policy
> kill rate over **200 free scripted episodes** (uniform over the 3 actions, `tics=4`, the same
> 300-tic / ~75-step episode budget, same cfg and seed procedure), measured and written into the
> scorer BEFORE the paid run.
>
> **ARM (b) — grounding honesty.** Scored from the run's own logs (commanded actions are the truth;
> no oracle involved): over all commanded discrete turns with a P1 reading, sign agreement between
> commanded turn direction and P1's reported direction ≥ **0.90**, with ≥ **20** scored turn steps,
> and P1 `None`-rate on turn steps ≤ **0.50**. A primitive that is silently wrong (the probe's
> `best_shift` failure) fails this arm even if the brain lucks into kills.
>
> **Degenerate guards (any fires → no PASS is recordable):**
> - **Perception-free-decoy guard:** each pre-registered scripted decoy — **blind spinner**
>   ("TURN_LEFT + ATTACK every step", multi-hot) and **ATTACK-only** ("ATTACK every step, never
>   turn" — catches a centered-enough spawn making aiming unnecessary) — is run for 200 free
>   episodes and must NOT clear ARM (a)'s bar. Measured BEFORE the paid run; if either clears, the
>   scenario is re-pinned harder (shorter timeout / ammo cap) before any paid run, and this document
>   is amended stricter-only.
> - **Variation guard:** the 30 seeds are distinct and pinned in the launcher; kill episodes must show
>   ≥ 3 distinct time-to-kill tic values, else DEGENERATE (a constant kill signature indicates a
>   scripted artifact, the HUD-gate lesson).
> - **Alignment:** all log↔oracle alignment is by episode index + tic/step count. Wall-clock is never
>   used for alignment (the sev-1 lesson from PR #55).
> - **Episode-boundary guard:** any observation after `is_episode_finished()` must return an explicit
>   `episode_finished` marker (never a stale frame) — `get_state()` is `None` after finish.
> - **One attempt per seed:** the harness enforces exactly one attempt per pinned seed — a
>   `new_episode` issued before the current episode finishes counts that seed's episode as FAILED
>   (no kill) and advances to the next seed. No re-rolling a bad start.
> - **Completion floor:** < 25/30 episodes completed → `INSUFFICIENT_DATA` (harness fault, not FAIL).
>
> **Both arms required.** Verdict vocabulary: `PASS / FAIL / DEGENERATE / INSUFFICIENT_DATA`.
> Cost cap for the paid run: one session, ≤ 40 decisions × 30 episodes, target ≤ $10.

### 2.3 Why this shape

- **The random baseline is measured, not assumed, and free** — 200 scripted episodes cost only Docker
  CPU. `basic`'s room is small and the pistol is hitscan, so random may be nontrivial; the relative
  bar (`R + 0.30`) protects against that, and the absolute floor (0.60) protects against a
  pathologically bad R making a mediocre brain look good.
- **The perception-free decoys (blind spinner, ATTACK-only) are the decoy arm's analogue** for a
  motor task: they are the cheapest strategies that ignore perception entirely (ATTACK-only also
  probes whether the spawn is centered enough that no aiming is ever needed). The gate is only
  meaningful if perception-free play does not pass — hence both are measured first and the scenario
  hardened pre-registration-style if needed. Note ATTACK-only also cannot vacuously pass ARM (b): a
  run with < 20 scored turn steps fails ARM (b)'s minimum-count requirement rather than passing empty.
- **ARM (b) exists because of the probe's headline surprise:** `best_shift` failed *quietly*. A 3D
  floor whose ego-rotation channel confabulates would corrupt everything above it; the gate makes
  "fails loudly when uncertain" a scored requirement, not an aspiration.

### 2.4 Free pre-checks (before PR-3 wires anything live)

- **PC-1 (mover pop-out in the gate scenario):** capture 200 scripted frames of `basic_gate.cfg`
  (free, Docker); on ego-stationary pairs where the monster is on-screen (hand-check ~20 frames), a
  diff component ≥ `min_area` overlapping the monster must appear in ≥ 80% of them. If the standing
  monster's idle animation does NOT clear the floor, P2's azimuth channel for THIS scenario is
  re-based on P1-only search behaviour (turn-and-watch-for-any-mover), and that finding is recorded
  here before the paid run.
- **PC-2 (yaw fixture bar):** on the existing `defend_the_center` captures (known scripted action
  sequence), P1 sign agreement ≥ 0.90 with `None`-rate ≤ 0.30 on turn pairs. This is PR-2's offline
  test and the R0-vs-R1 climb decision point.

---

## 3. Seam mapping (world_mcp for a 3D world)

Follows the existing `GAMES` registry pattern (`world_mcp.py`): a new entry + a plugin/perceiver pair;
static tool specs mirror live tools exactly (`assert_action_tools_fresh` discipline).

### 3.1 `observe` payload (symbolic ONLY — no screenshot to the brain, unchanged law)

```
ego:      { turning: "left"|"right"|"none"|None, dx_px, deg_per_step|None, confidence }   # P1
movers:   None | [ { azimuth_px, azimuth_deg|None, area, bbox, confidence } ... ≤5 ]       # P2
          # None => "can't tell (not ego-stationary)"; [] => "confidently nothing moving"
episode:  { finished: bool, tic: int, episode_index: int }
last_action: echo of the last tool call + tics
```

No pose, no map, no entity names — the brain hypothesizes meaning ("the recurring mover at stable
azimuth is probably the target") and grounds it by behaviour (turn toward it → azimuth → 0 → attack →
episode ends).

**Payload honesty — what this gate does and does not test.** In `basic_gate.cfg` (one monster, one
room) the `movers` list will typically contain **≤ 1 entry**, so "the only mover's azimuth" is de
facto target-lock even though the primitive attaches no label and genuinely does not know it is a
monster. Said out loud: **GATE-3D primarily tests turn-to-azimuth control + P1's grounding honesty,
NOT entity discrimination.** Discriminating among multiple movers (which one is the threat, which is
benign) is deliberately deferred to a later multi-monster gate (`defend_the_center`-class scenario,
where the single-mover shortcut breaks by construction) — that future gate tightens from this
explicitly recorded baseline, stricter-only.

Screenshot stays behind `--with-screenshot` (debug only). The foveated
`read_region`/`whats_changed` tools are NOT extended to this world pre-gate (`_REGION_TOOL_WORLDS`
stays as-is): no proven need yet — adding them unasked is sensorium creep.

### 3.2 Action tools

- `turn_left {}`, `turn_right {}`, `attack {}` — **no `tics` parameter in the gate world; every call
  executes with `tics = 4` fixed** (the gate's action-grain equivalence pin, §2.2 — brain and scripted
  baselines act on the identical step cadence). A variable-`tics` schema is a post-gate extension, not
  a flag to add quietly. Each tool builds the multi-hot vector over `get_available_buttons()` by
  *name lookup*, never positional index (the probe: the variable/button arrays are order-sensitive;
  zip by name once at init).
- `new_episode {}` — explicit reset; `observe` after finish returns `episode.finished=true` and every
  frame-reading path guards `get_state() is None` (probe integration fact #4). Auto-advancing to the
  next episode implicitly is forbidden — the brain must see the boundary.
- Sandbox: an `Allowlist({"turn_left", "turn_right", "attack", "new_episode"})`, mirroring
  `_gba_sandbox()`.

### 3.3 Oracle wiring

`state.game_variables` zipped by name → appended per-step to `runs/<run>/oracle.jsonl`
(`{episode, tic, health, ammo2, killcount}`). Scoring only. It is never serialized into any tool
result. The scorer (`eval/score_doom_gate.py`) joins transcript ↔ oracle on (episode_index, tic).

## 4. Build plan — smallest PR sequence

| PR | Contents | Gate on it |
|---|---|---|
| **PR-A (this)** | `reports/2026-07-04-vizdoom-3d-floor-design.md` — docs only | review = does the gate pre-registration hold water |
| **PR-B** | `core/flow3d.py` (P1) + `core/movers.py` (P2), both to the 7-slot contract; `eval/fixtures/vizdoom_flow/` (a ~30-frame committed subset of the probe's `defend_the_center` captures + an `actions.jsonl` reconstructed from the probe's scripted round-robin — regenerate the capture WITH an action log if ambiguous, free) + `eval/fixtures/vizdoom_stationary/` (~12 stationary pairs); offline tests pin PC-2's bar and the §1.3 stationary/turning separation. **No live ViZDoom dependency in tests** — pure PNG fixtures. | PC-2 passes at R0, else the R1 climb decision is made HERE, cheaply |
| **PR-C** | `games/vizdoom/` adapter (plugin + perceiver emitting §3.1; lazy import so `world_mcp.py` stays importable without vizdoom — the mgba pattern); `scenarios/basic_gate.cfg`; `GAMES["doom_basic"]` entry; oracle→jsonl wiring; Docker run recipe note | `assert_action_tools_fresh` + a scripted smoke episode end-to-end |
| **PR-D** | `eval/score_doom_gate.py` with §2.2's constants verbatim + unit tests on synthetic transcripts (PASS/FAIL/DEGENERATE/INSUFFICIENT_DATA each pinned, the score_gate_run.py pattern); the three free baseline runs (random R, blind spinner, ATTACK-only) executed and their numbers written into the scorer + this doc's addendum; harness enforcement of one-attempt-per-seed | baselines measured; perception-free-decoy guard evaluated BEFORE any paid run |
| **paid run** | one live Claude-over-MCP session (account B, per standing authorization), 30 episodes, scored | GATE-3D verdict; results PR appends the verdict — never edits §2.2 |

Every PR through the standard loop: plan → branch → Sonnet implements → <5 adversarial reviewers →
triage → David merges.

## 5. Anti-drift table (ADR-002 §11 style — drift → guard)

| Drift | Guard |
|---|---|
| **Hand-code a Doom monster detector** (sprite template, color key, "cacodemon classifier") | P2 reports meaning-free movers; the brain hypothesizes "target" and grounds it by behaviour. Any file matching sprite art or naming a monster = the bespoke-perceiver drift ADR-002 exists to kill. |
| **Over-build the 3D sensorium pre-gate** (full optical-flow field, depth map, SLAM, ForwardStreamCue "while we're at it") | Build ONLY P1 + P2. §1.4's deferrals are pinned; a third primitive appears only with a new pre-registered gate that needs it. |
| **A yaw estimator that is silently wrong** (the `best_shift` re-run) | `None` is a first-class output; ARM (b) scores sign-agreement + None-rate from the run's own action log; PR-B's fixture tests pin `None` on ambiguous input (blank-wall frames). |
| **Tune thresholds on the paid run** | `pix_t`/`min_area`/prominence floor are pinned from fixtures in PR-B; gate constants are pinned HERE. Stricter-only amendments, per the entity-gate-v2 clause. |
| **A gate that can't fail** ("it moved toward the monster, looks right") | §2.2's numeric bars + measured random, blind-spinner AND attack-only baselines; the decoys are the perception-free policies that must not pass. |
| **Wall-clock alignment** | Episode index + tic count only (PR #55 sev-1 lesson). |
| **Oracle on the wire** (HEALTH/AMMO2/KILLCOUNT in a tool result) | game_variables → `oracle.jsonl` only; scorer-side join; reviewer checklist item on PR-C. |
| **Screenshot to the brain** ("3D is too hard for symbols, just send the frame") | §4-confabulation law unchanged; `--with-screenshot` debug-only. If the symbolic payload proves too lossy, that is an ADR-level finding to report, not a flag to flip. |
| **Persist P1's calibration or the brain's target hypothesis across runs** | Learning-boundary HARD LAW: within-run only, blank every run. |
| **Quietly widen the action set** (add MOVE_FORWARD because the brain "seems stuck") | The button set is pinned in `basic_gate.cfg` §2.1; changing it = re-pinning the gate, stricter-only, before any paid run. |

## 6. Decided vs open

- **DECIDED (this doc):** the two-primitive tier (P1 `YawBandFlow`, P2 `StationaryMovers`); defer (c)+(d);
  the GATE-3D statement §2.2 verbatim; the seam payload shape §3.1; the PR sequence §4.
- **OPEN (measured before the paid run, free):** R (random kill-rate), the blind-spinner rate, PC-1
  (does `basic`'s standing monster pop out on stationary pairs), PC-2 (does R0 suffice for P1 or does
  it climb to R1).
- **OPEN (the gate answers):** can a region-neutral brain over this floor beat random at basic.cfg —
  the tier's right to exist.

---

# AMENDMENT A1 (2026-07-04) — scenario re-pin after PC-1 FAIL: `basic_gate` → `dtc_gate`

Appended per the house stricter-only discipline: the original text above is LAW as written and is not
edited; this amendment supersedes it only where explicitly stated. Trigger: the §2.4 free pre-checks
ran (`runs/vizdoom_precheck/PRECHECK_REPORT.md` + raw JSONs, 2026-07-03) — **PC-1 FAILED
unambiguously, PC-2 PASSED**. The §2.4 fallback clause and the §2.2 re-pin clause both fire; this is
the recorded re-pin, made BEFORE any primitive build, live wiring, baseline run, or paid run.

## A1.1 PC-1 evidence (the justification)

From `pc1_results.json` / `pc1_wake_results.json` (`basic.cfg` with the pinned button set, 213
frames / 3 seeds, monster bbox from the server-side labels buffer — oracle-side only):

- **33/36 ego-stationary monster-visible pairs are pixel-IDENTICAL (gmean exactly 0.0).** The
  standing Cacodemon's idle state is a single sprite frame; monster-overlap component rate = **0.0%
  vs the pre-registered ≥ 80% bar**. The only 3 nonzero pairs are first-pair weapon-settle artifacts
  (no monster overlap).
- **Missed shots do not wake it**: 49 post-fire stationary pairs, all zero diff (`basic_wake`,
  seed 666). It animates only when hit — which ends or nearly ends the episode (1-2 shots kill).
- Pipeline sanity holds (turn pairs: gmean 16.3, 25.1% pixels changed) — the scene is genuinely
  static, not a detector bug.

Consequence: in `basic_gate.cfg` the payload would carry `movers: []` on every ego-stationary
observation — the symbolic seam cannot distinguish facing-the-monster from facing-a-wall, the brain's
achievable policy collapses toward the blind-spinner decoy, and the §2.2 perception-free-decoy guard
would (correctly) kill the run in PR-D. The §1.3 mover evidence came from monsters that **walk**
(`defend_the_center`: 0.0109 frac / 4.5 comps median on stationary pairs); the gate scenario moves to
where that evidence actually holds. P2's design is unchanged — the primitive was honest (it reported
"nothing moving" because nothing moved); the SCENARIO was wrong for it.

## A1.2 PC-2 record (the R0 decision — no climb)

R0 `YawBandFlow` (§1.1 sketch implemented verbatim, throwaway) on fresh action-logged captures,
floor sweep (`pc2_floor_sweep.json`, `pc2_dtc_fresh.json`): at fixture-derivable floors
(ncc 0.2 / prom 0.02) **pooled sign-agreement 0.964, None-rate 0.201** over ≥ 95 scored turn pairs —
clears ARM (b)'s 0.90 / 0.50 bars and §2.4's stricter 0.30 None bar. Sign convention verified
empirically (TURN_LEFT → +dx, median +39..53px; zero wrong-sign readings on fresh dtc at any floor);
idle false-motion rate **0.000** across 177 idle pairs (three-valued honesty holds); deg-per-px is
**regime-dependent** (Doom slow vs fast turns: ~7.03° vs ~14.06° per 4-tic action), confirming §1.1's
within-run self-calibration at the commanded action grain — a hand-set constant would be wrong.
**Verdict: R0 sufficient; no R1 climb.** PR-B pins its floors near ncc 0.2–0.3 / prom 0.02 from its
own committed fixtures and re-verifies the ARM (b) margin there.

## A1.3 The re-pinned scenario: `scenarios/dtc_gate.cfg`

`defend_the_center.wad` (player fixed at the center of a circular arena; melee monsters spawn at the
perimeter and **walk toward you** — the regime where §1.3's mover numbers were actually measured),
with cfg deltas pinned:

- `available_buttons = { TURN_LEFT, TURN_RIGHT, ATTACK }` (dtc's native set — no strafes, no
  translation, so "ego-stationary" for P2 = simply "not turning", the cleanest possible gate).
- `available_game_variables = { HEALTH, AMMO2, KILLCOUNT }` — KILLCOUNT explicitly added (probe
  fact: dtc's default exposes only AMMO2 + HEALTH). Oracle-side only, never on the wire.
- `episode_timeout = 1000` tics (= 250 action-steps at the pinned grain); episode also ends on
  player death (melee overwhelm / ammo exhaustion — dtc ships 26 pistol rounds). Screen pinned
  `RGB24` / `RES_320X240`, headless.
- **Action grain unchanged from the first pin:** every action executes with `tics = 4` fixed; the
  gate world's tools take no `tics` parameter. Tools gain a System-1 `repeat: 1..10` parameter (the
  same single action executed repeat times at tics=4 each) so the brain's decision budget is not
  consumed by mechanical repetition — the per-step grain stays identical to the scripted baselines.

## A1.4 The re-pinned gate statement (verbatim; supersedes §2.2's scenario + ARM (a); stricter-only thereafter)

> **GATE-3D-A1 (re-pinned 2026-07-04, before any build).** A region-neutral brain over the MCP seam,
> receiving only the symbolic 3D-floor payload (P1 yaw + P2 movers + episode status; no screenshot,
> no game variables), plays `dtc_gate.cfg` for **N = 30 episodes** on **30 distinct pinned seeds**,
> at most **40 brain decisions per episode** (a decision = one tool call; `repeat ≤ 10` System-1
> steps per call). **Action grain is pinned equal across arms and baselines: every action-step
> executes with `tics = 4` fixed**, and every baseline runs under the identical 1000-tic /
> 250-step / death-terminated episode budget.
>
> **ARM (a) — task.** `K` = mean final oracle `KILLCOUNT` over the 30 episodes. PASS requires
> `K ≥ max(R + 2.0, 1.5 × R)`, where **R** = mean final KILLCOUNT of the random policy (uniform
> over the 3 single-button actions each step) over **200 free scripted episodes**, same cfg, same
> grain, same budget, measured and written into the scorer BEFORE the paid run.
>
> **ARM (b) — grounding honesty (unchanged from §2.2).** From the run's own logs: P1 sign-agreement
> with commanded turn direction ≥ **0.90** over ≥ **20** scored commanded-turn steps, P1 `None`-rate
> on turn steps ≤ **0.50**. Fewer than 20 scored turn steps = ARM (b) not passed (no vacuous pass).
>
> **Degenerate guards (all carried over, re-measured on THIS scenario; any fires → no PASS):**
> - **Perception-free-decoy guard:** **blind spinner** (TURN_LEFT + ATTACK multi-hot every step) and
>   **ATTACK-only** (never turn — dtc's converging monsters make this a serious decoy: they walk into
>   the line of fire), each 200 free episodes on `dtc_gate.cfg`, must each score
>   `< max(R + 2.0, 1.5 × R)` on mean KILLCOUNT. If either clears, the scenario is re-pinned harder
>   (stricter-only amendment A2) before any paid run.
> - **Variation guard:** 30 distinct pinned seeds; the brain's 30 final KILLCOUNTs must span ≥ 3
>   distinct values AND episode lengths (tics) must not all be identical, else DEGENERATE.
> - **One attempt per seed:** `new_episode` before the current episode ends counts that seed's
>   episode with its KILLCOUNT at abandonment (no re-rolling).
> - **Alignment:** episode index + tic/step count only; wall-clock never used for alignment.
> - **Episode-boundary guard:** post-finish observations return an explicit `episode_finished`
>   marker; every frame read guards `get_state() is None`.
> - **Completion floor:** < 25/30 episodes completed → `INSUFFICIENT_DATA`.
> - **Oracle law:** HEALTH/AMMO2/KILLCOUNT go to `oracle.jsonl` only, never into any tool result.
>
> **Both arms required.** Verdicts: `PASS / FAIL / DEGENERATE / INSUFFICIENT_DATA`. Cost cap: one
> session, ≤ 40 decisions × 30 episodes, target ≤ $10.

**Payload-honesty note, restated for dtc:** multiple movers may now appear simultaneously, but all of
them are hostile — aiming at *any* mover suffices, so GATE-3D-A1 tests turn-to-azimuth control +
P1/P2 grounding honesty under real ego-motion and moving targets. It still does **NOT** test entity
discrimination (threat-vs-benign among movers); that stays deferred to a later gate with mixed-role
movers, tightening from this recorded baseline.

## A1.5 Fixture note (binding on PR-B)

The 2026-07-02 probe capture of `defend_the_center` has an intermittent **one-frame action↔frame
misalignment** (PC-2 finding: naive scoring on it gives sign-agreement 0.02–0.19 — an artifact, not a
primitive failure). It is NOT a valid fixture source. PR-B regenerates its committed fixtures from
`runs/vizdoom_precheck/basic_mixed/` + `runs/vizdoom_precheck/dtc_mixed/`, which carry per-step
`actions.jsonl` under the pinned convention **frame_i = state BEFORE action_i** (the capture scripts
alongside in that directory are the template).

## A1.6 Build-plan deltas (§4 updated for the re-pin)

- **PR-B:** unchanged scope (P1 + P2 + offline fixture tests) with two bindings: fixtures from the
  §A1.5 sources only; P1 floors pinned near ncc 0.2–0.3 / prom 0.02 and re-verified against ARM (b)'s
  margin on the committed fixtures.
- **PR-C:** ships `scenarios/dtc_gate.cfg` + `GAMES["doom_dtc"]` (the `basic_gate.cfg` /
  `GAMES["doom_basic"]` deliverables are DROPPED — dead scenario); tools per §A1.3 (no `tics` param,
  `repeat: 1..10`); oracle→jsonl wiring incl. KILLCOUNT.
- **PR-D:** scorer implements GATE-3D-A1 verbatim (incl. one-attempt-per-seed enforcement and the
  `< max(R + 2.0, 1.5 × R)` decoy comparison); **three** free baselines (random R, blind spinner,
  ATTACK-only) run on `dtc_gate.cfg`, 200 episodes each, numbers written into the scorer + an A2
  addendum here BEFORE the paid run.
- **Paid run:** unchanged shape; scored under GATE-3D-A1.

## A1.7 Decided vs open (supersedes §6 where in conflict)

- **DECIDED by this amendment:** the scenario (`dtc_gate.cfg`, §A1.3); GATE-3D-A1 (§A1.4) as the
  operative gate statement; R0 for P1 (no climb, §A1.2); fixture sources (§A1.5).
- **OPEN (free, before the paid run):** R and both decoy means on `dtc_gate.cfg` — with the explicit
  pre-registered risk that ATTACK-only clears the bar and forces amendment A2.
- **OPEN (the gate answers):** unchanged — can a region-neutral brain over this floor beat
  perception-free play, now in a scenario where the floor's evidence actually holds.
