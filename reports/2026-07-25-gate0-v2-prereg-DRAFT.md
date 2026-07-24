# Gate 0 v2 pre-registration — brief fix for the Red premature-stop — 2026-07-25

**Status: DRAFT — FOR DAVID, NOT AUTHORIZED. $0, docs only.** This document proposes a change; it
does not make one. No fixture, scorer, predicate, or pinned file is edited by this DRAFT. No
paid run is launched by writing this. Per **gate-methodology** §1, this is the pre-registered
escalation written BEFORE any further spend, responding to the v1 attempt that banked
`FAIL_CAPABILITY` (Arm R) / `FAIL_CAPABILITY` (Arm W) on 2026-07-24. It mirrors the structure of
`reports/2026-07-18-gate0-prereg.md` (the v1 pre-reg) and inherits everything from
`reports/2026-07-24-gate0-prereg-amendment-appserver.md` (the app-server launch-surface amendment)
except where explicitly marked `[v2]` below.

**Authorization boundary, restated up front per safety-invariants law 1 and gate-methodology §3:**
the DECISION to spend on this escalation is David's, not this document's. This pre-reg only earns
the right to be reviewed; it does not earn the right to run. See §8.

## 0. The banked v1 result (what this responds to)

Re-verified this session directly against the raw on-disk artifacts (not the summary docs) —
`runs/gate0_paid/red/agent_metrics.json`, `runs/gate0_paid/miniwob/agent_metrics.json`,
`runs/gate0_paid/red/world/oracle.jsonl`, `runs/gate0_paid/red/transcript.jsonl` — per
gate-methodology §6 ("every number in the verdict is re-verified against the raw files"):

- **Arm R:** `_red_success = (False, ['red_no_sustained_battle_exit'])`. The oracle log
  (438 rows) shows the fresh party `0→1` transition, then a trainer battle (`in_battle==2`) that
  is entered and exited alive, then **exactly 4** trailing rows at `in_battle==0` — the predicate
  requires 10 consecutive. The transcript's final `agent_message` (`phase: "final_answer"`) reads
  *"Obtained [starter] from Professor Oak and defeated [rival] in the first rival battle."* — the
  turn ends immediately after this message; no further tool calls follow it. Metrics: `127.75s` /
  142 actions vs human `233.288s` / 271 actions (the agent beat the human baseline on both
  Capability sub-bars); `$0.41589`, `10.397` normalized credits (8.3% of the 125-credit Red soft
  cap).
- **Arm W:** `_miniwob_success = (False, ['miniwob_episode_1_terminal_not_success'])`. All 5
  held-out seeds (1000-1004) played, exactly one terminal each, `abandoned=false`; 4/5 at reward
  `1.0`; seed 1001 terminal at reward `0.6667` — a genuine partial completion, not a premature
  stop (the episode ran to its own terminal state; nothing was cut short). `97` actions /
  `295.594s`; `$1.02958`, `25.7395` normalized credits (51.5% of the 50-credit MiniWoB soft cap).
  Human baseline for the paid seeds remains `PENDING` (unchanged from the amendment; Arm W's
  formal verdict layer is `INSUFFICIENT_SOURCE` on that axis independent of the capability miss).
- **Cheap PASSED decisively**, both arms: combined `$1.4455` / `36.14` credits vs the `$7.00` /
  `175`-credit PASS bar and the `250`-credit hard breaker. `NO_LEAK` clean on both arms
  (`tools/check_gate0_codex.py::audit()` returned no `leak_failures` for either — the transcript
  adapter fix from PR #157's review held). Breaker never tripped.
- **Key epistemics fact, load-bearing for this whole document:** the human baseline run itself
  *satisfies* `_red_success` (a human playing the same fresh-start task produces the sustained
  post-battle telemetry the predicate requires). The predicate is achievable, not broken — Red's
  FAIL is a real capability/compliance gap in the agent's *stopping behavior*, not an unfair or
  miscalibrated bar. **v2 must not, and does not, touch the predicate.**

## 1. What changes vs v1, and what stays frozen byte-for-byte

**The ONLY intended change is the task text** — specifically `COMMON_TASK_SUFFIX` in
`tools/gate0_appserver_arm.py` (the world-agnostic suffix appended to both arms' task sentences
via `task_text_for(arm) = ARM_TASK_SENTENCES[arm] + "\n" + COMMON_TASK_SUFFIX + "\n"`, written
byte-identically to `launch/TASK.md` and sent verbatim as the `turn/start` message text — this
*is* the brief; there is no separate `CLAUDE.md` in the app-server harness). Nothing else is
proposed to change.

**Everything else stays frozen, verified this session by direct inspection, not assumed:**

- `ARM_TASK_SENTENCES` (the actual task sentences, per arm) — **unchanged**. v2 does not touch
  what the agent is asked to do, only how it is told to confirm it's done.
- `DEVELOPER_INSTRUCTION` and `render_brain_config_toml()` — **unchanged**; `COMMON_TASK_SUFFIX`
  is not part of the brain-config block, so `brain_config_sha256` (`ab7e54c1785f5d8be4352bbe0f85
  edb37cda68cf56df2128d61df025c1041fc3`) is **byte-identical** across v1 and v2 for both arms.
  Confirmed by direct reading of `render_brain_config_toml()` — it takes `developer_instructions`
  (the `DEVELOPER_INSTRUCTION` constant), never `COMMON_TASK_SUFFIX`.
- `eval/score_gate0.py` and `tools/check_gate0_codex.py` — **unedited, read verbatim**, including
  `_red_success`, `_miniwob_success`, `_arm_metrics`, all cost/credit caps, and `PIN_FIELDS`/
  `CONSTANCY_FIELDS`. **Confirmed: `task_sha256` is in `PIN_FIELDS` but explicitly NOT in
  `CONSTANCY_FIELDS`** (`tools/check_gate0_codex.py:21-31`) — the scorer's own design already
  treats task text as legitimately per-arm/per-version, so a task-text change cannot itself
  trigger `CONSTANCY_BREACH`. This is a design fact, not a loophole v2 is exploiting.
- World images by immutable ID (`sha256:5bfabc75...` red, `sha256:8bb3358e...` miniwob),
  `enabled_tools` allowlists (red: `observe, explore, goto, remember, press_button,
  press_sequence, wait`; miniwob: `observe, read_region, whats_changed, click, type_text,
  press_key, reset_episode`), bars, human baselines, credit caps (`$5.00`/`125cr` Red, `$2.00`/
  `50cr` MiniWoB, `$7.00`/`175cr` combined PASS, `250cr` hard breaker), the one-attempt rule, and
  the blank-agent wipe (`history.persistence="none"`, `features.memories=false`) — **all
  unchanged**, inherited verbatim from the amendment.

**CRITICAL mechanical consequence — `task_sha256` is a byte-frozen pin and MUST be re-frozen:**
Changing `COMMON_TASK_SUFFIX` changes `task_text_for()`'s output for **both** arms (the suffix is
shared), which changes `launch/TASK.md`'s bytes, which changes `task_sha256` for **both** arms.
This is not optional bookkeeping — `tools/check_gate0_codex.py::audit()` hard-compares the
observed receipt's `task_sha256` against the frozen `expected_pins` file
(`_receipt_shape_failures`/pin-mismatch check over `PIN_FIELDS`) and fails the audit on any
mismatch. Concretely, the exact fields that must be regenerated before any v2 launch:

| File | Field | v1 (frozen) value | v2 (proposed, computed this session — see §2) |
|---|---|---|---|
| `eval/fixtures/gate0_expected_pins_red.appserver.json` | `task_sha256` | `306751c34627f6d5c6a8c94ac2f714e358f0dcbc5867866c273e434de7f4b7c4` | recommended-candidate value in §2 |
| `eval/fixtures/gate0_expected_pins_miniwob.appserver.json` | `task_sha256` | `845638c874df2f2de2adaebdd1d6c9318c689a46d0032fa76a9393e1e47512d1` | recommended-candidate value in §2 |

I independently re-derived the hashing recipe this session (not assumed from the docstring):
`sha256((ARM_TASK_SENTENCES[arm] + "\n" + COMMON_TASK_SUFFIX + "\n").encode("utf-8"))` — no CRLF
subtlety (`TASK.md` is written with `newline="\n"`, unlike the `.ps1`-derived brain-config block).
Recomputing this exact function against the current frozen suffix reproduced both pinned values
above byte-for-byte, confirming the recipe before proposing new numbers. **Every other field in
both `*.appserver.json` fixtures (all 20 `PIN_FIELDS`) stays exactly as pinned** —
`brain_config_sha256`, `world_image_id`, `mcp_tools_observed`, `codex_path`/`codex_version`/
`codex_executable_sha256`, `auth_method`, `critical_config_transport`, `host_code_sha256`/
`image_code_sha256`, etc. `config_sha256`/`codex_mcp_list_sha256` remain the same
launch-invocation-dependent `CONSTRAINT:...` placeholder they already are (unaffected by task
text; recomputed at actual launch time regardless of v1/v2). `eval/fixtures/
gate0_signature.appserver.json` needs no field-level change — it does not itself pin
`task_sha256` (only `frozen_commit` + launcher/safety-file hashes + the credit-rate pin), but a
fresh signature naturally implies `frozen_commit` points at whatever commit lands the v2 suffix
edit.

**Nothing else may be touched.** No edit to `eval/score_gate0.py`, `tools/check_gate0_codex.py`,
`ARM_TASK_SENTENCES`, `enabled_tools`, world images, bars, or caps is in scope for v2. If any of
those needs to change, that is a different, larger proposal than this one.

## 2. The brief fix, drafted verbatim (the appendix — the entire intervention)

Per **run-brief-authoring**, the brief IS the intervention; reviewers must critique these exact
words. The only line in scope is `COMMON_TASK_SUFFIX`
(`tools/gate0_appserver_arm.py:159-162`), currently:

> "Use only the connected world MCP tools and screen-derived state. Do not use shell, files, web,
> tool search, or connectors. Begin by observing. Stop when the stated task is complete."

### Candidate phrasings

**Candidate A — explicit "settling" framing:**
> "Use only the connected world MCP tools and screen-derived state. Do not use shell, files, web,
> tool search, or connectors. Begin by observing. `[v2]` Before treating the task as complete,
> continue observing for a few more steps to confirm the world state has settled — a transition,
> animation, or other change still in progress does not count as complete. Stop when the stated
> task is complete."

`task_sha256` if adopted: red `bf89e95b08b64b03fead22547ba44689db570a6b5c68f763e481f1c35c0c3aac`,
miniwob `8c59a369b49cd2f3dce834abca00284d5719c00e0b76f654f7de88ec0c4ad79b`.

**Candidate B — minimal, one-clause insertion:**
> "Use only the connected world MCP tools and screen-derived state. Do not use shell, files, web,
> tool search, or connectors. Begin by observing. `[v2]` Continue observing and acting until the
> world state has visibly settled before concluding the task is complete. Stop when the stated
> task is complete."

`task_sha256` if adopted: red `4b90455b79fda1ac87556d5d2677b1dd909b483c89bdb106ec70515bc89ffcbf`,
miniwob `32f23d193ebfa0dee8fbde9f983c80b4c6931ae94628857699edac4cf7a53d0f`.

**Candidate C — targets the observed failure shape directly (narration vs. confirmation):**
> "Use only the connected world MCP tools and screen-derived state. Do not use shell, files, web,
> tool search, or connectors. Begin by observing. `[v2]` A narrated summary of what happened is
> not confirmation that the task is complete — after your last consequential action, continue
> observing the world for several more steps until the state has visibly stopped changing, then
> stop."

`task_sha256` if adopted: red `61dc6d831903c2c57d826873138e84610fdd339acf474b358d38bd89d0385fe8`,
miniwob `96354dd5979e4fccc112695aaf9aa2b0801850a845700815b2b7952882709c28`.

(All three hashes were computed this session against the real `ARM_TASK_SENTENCES` and the exact
`task_text_for` concatenation rule — read-only, illustrative; none is written to any fixture by
this DRAFT.)

### Recommendation: Candidate C

v1's transcript shows the agent produced a `phase: "final_answer"` **prose** message declaring
victory and then simply stopped calling tools — the failure is specifically that a narrated
conclusion substituted for continued grounding in the world. Candidate C names that exact
shape ("a narrated summary... is not confirmation") without describing the game, the battle, or
any oracle fact — it would read identically if pasted into a browser-form task, a 3D-navigation
task, or any other world in this project. Candidates A and B are also viable and not taint (same
reasoning below applies to all three); C is preferred because it is the most direct antidote to
the specific mechanism observed, not just a generic "wait a bit" nudge.

### Taint analysis — why this is not oracle-on-the-wire or scorer taint

Checked against `safety-invariants` law 5 ("oracle/RAM/score never on the agent wire") and the
run-brief-authoring pre-launch checklist:

- **No oracle vocabulary anywhere.** None of the three candidates mentions `in_battle`, RAM, HP,
  party, `oracle.jsonl`, "rows", the scorer, or a predicate. They use only vocabulary the suffix
  already contains ("observing", "world state") — no new domain-specific concept is introduced.
- **No magic number.** The predicate's threshold is exactly 10 consecutive rows. All three
  candidates deliberately say "a few more steps" / "several more steps" — never a number — so the
  agent cannot back out the exact oracle boundary from the brief. Stating "10" (or any number)
  would be a direct leak of the predicate's shape and is explicitly avoided.
- **World-general, not Red-specific.** `COMMON_TASK_SUFFIX` is, by construction, shared verbatim
  by both arms (`task_text_for` appends the same suffix regardless of `arm`). Any edit here
  necessarily applies identically to Arm W too — there is no way to scope this fix to Red only
  without forking the suffix per arm, which is a larger, unproposed change. This is a feature, not
  a side effect: it forces the fix to be phrased in genuinely world-agnostic terms (the same
  discipline **run-brief-authoring** §2 applies to A/B arm briefs — shared wording, no
  arm-identifying content).
- **Does not change the success criterion.** All three candidates keep "Stop when the stated task
  is complete" as the terminal instruction; they only add a precondition on *when the agent may
  believe* that moment has arrived. This is the same category of instruction as "verify before you
  claim done" — general task hygiene applicable to any agent in any environment, not a hint about
  what "done" specifically looks like in Pokemon Red.
- **Does not touch `_red_success` or any predicate.** Per §1, the scorer is unedited. The fix acts
  entirely upstream, on agent behavior, never on how success is measured.

### Effect on Arm W — deliberately does nothing about the 0.667 episode

Arm W's miss (seed 1001, reward `0.6667`) was a **genuine partial** — the episode ran to its own
environment-issued terminal (`done=True`), not a premature agent stop. The suffix edit is
targeted at Red's specific failure mode (agent narrates success and stops calling tools before
its own turn's natural end); MiniWoB episodes terminate via the environment's own `done`/`reward`
signal, not via the agent narrating completion, so this change is **structurally inert for Arm
W** — it may cause a few extra `observe` calls before the agent accepts an already-terminal
episode as terminal, but it cannot change which checkboxes got clicked or what reward the
environment returned. **v2 proposes doing nothing else about the 0.667 episode.** Attempting a
MiniWoB-specific fix via the brief risks teaching the task (e.g., anything that nudges the agent
toward "check every box before submitting" edges toward stating the solution) and is explicitly
out of scope here — per the design doc's escalation shelf, a genuine partial on an otherwise
5-seed-clean arm is banked evidence, not an immediate-fix target.

## 3. Hypotheses (each independently observable in the scored output)

- **H-a:** Arm R's oracle (`world/oracle.jsonl`) contains, after the trainer-battle exit,
  ≥10 consecutive rows with `in_battle == 0` AND ≥2 distinct `(x, y)` pairs among the post-exit
  rows — i.e., the exact two conditions `_red_success`'s `exit_idx`/`red_no_free_movement_after_
  exit` checks require, satisfied where v1 fell short (4 rows, well under 10).
- **H-b:** `_red_success(oracle_rows)` returns `(True, [])` — the scorer's actual verdict, not an
  inference from H-a alone (H-a could hold while some other `_red_success` branch still fails,
  e.g. an HP dip or a map change during the exit span; H-b is the only fact that actually banks).
- **H-c:** Arm W's 5 terminal rows are unchanged in *kind* from v1 — same count of terminals (one
  per episode, 5 total), `abandoned=false` throughout, and the same qualitative split (4 clean
  `1.0` successes + 1 partial) — i.e., the brief edit measurably did not alter MiniWoB's task
  behavior, only (at most) its action count via a few extra `observe` calls. A material change in
  Arm W's terminal shape would falsify the "structurally inert for Arm W" claim in §2 and needs
  its own diagnosis, not a shrug.
- **H-d (cost control):** combined `cost_usd` and `normalized_credits` stay within the same order
  of magnitude as v1 (i.e., nowhere near the `$7.00`/`175`-credit combined PASS bar) — confirms
  the fix didn't turn into an unbounded "keep observing forever" loop. See §6 budget headroom.

## 4. The exact scorer + bars (quoted verbatim, unchanged from v1)

`eval/score_gate0.py`, read this session, unedited:

- **Capability bar, per arm** (`_arm_metrics`, unchanged): task predicate passes AND
  `wall_clock_s <= 2 * human_wall_clock_s` AND `primitive_actions <= 2 * human_primitive_actions`.
- **Cheap bar** (`score()`, unchanged): `limits = {"red": (5.0, 125), "miniwob": (2.0, 50)}` per
  arm (cost_usd cap, normalized_credits cap); combined `sum(cost_usd) > 7.0 or
  sum(normalized_credits) > 175` → `FAIL_CHEAP`; `sum(normalized_credits) > 250` →
  `hard_breaker_exceeded` (folded into `FAIL_CHEAP`).
- **Verdict vocabulary, exactly as printed** (`schema_version 1`): `readiness ∈ {GO, NO_GO,
  INSUFFICIENT_SOURCE}`; `overall ∈ {PASS, FAIL_CAPABILITY, FAIL_CHEAP, CONSTANCY_BREACH,
  NO_LEAK, INSUFFICIENT_DATA}`. Order of checks, unchanged: leak → constancy → infra → source →
  capability → cheap (`score()`'s `if/elif` chain, `eval/score_gate0.py:347-360`).
- **`_red_success` and `_miniwob_success`, quoted structurally (not reproduced line-for-line to
  avoid this document itself becoming a second copy of scorer logic that could drift): both
  functions are read in full in `eval/score_gate0.py:34-125` (this session) and are
  **byte-identical to v1** — no edit proposed or made.

**No predicate, bar, or constant may be loosened.** Post-hoc predicate edits to convert v1's
FAILs into PASSes are FORBIDDEN, restated verbatim from the design doc's own tightening law:
*"the future pre-registration may tighten [bars], never loosen them."* v2 tightens nothing and
loosens nothing — it is a pure prose-brief change upstream of the frozen scorer.

## 5. One-attempt rule, verdict vocabulary, infra-death carve-out (restated)

Same as v1, unchanged:

- **One attempt per arm; banked as printed.** No informal rerun of a completed v2 attempt. A
  further attempt (v3) requires its own fresh, narrower pre-registration (§7).
- **Verdict vocabulary** as quoted in §4. Constancy/leak checks run before task scoring — a
  `NO_LEAK` or `CONSTANCY_BREACH` voids the attempt as capability evidence entirely (does not
  bank as a capability result either way).
- **Infra-death carve-out, verbatim from `.claude/skills/paid-run-harness/SKILL.md` law 6 /
  `safety-invariants` law 5:** "Relaunch only on infra death before ~10 decisions (MCP never
  connected, container crash, 429). Infra death AT or AFTER ~10 decisions = the attempt is spent:
  score whatever artifacts exist with the frozen scorer and bank that verdict
  (`INSUFFICIENT_DATA` is a legitimate outcome). No relaunch without David's explicit OK." This
  already happened three times at `$0` during v1's own build-out (per the amendment doc's M1
  section) — the carve-out is proven to work as written on this exact harness.
- **`CONSTANCY_FIELDS` exclusion re-confirmed (§1):** because `task_sha256` is not a constancy
  field, v2's task-text change cannot itself cause `CONSTANCY_BREACH` between the two arms of the
  *same* v2 attempt. It is not evaluated against v1's task_sha256 at all — v1 and v2 are separate
  pre-registrations, not two arms of one constancy check.

## 6. Budget

Expected combined spend: **~$1.50**, based on v1's actual banked cost (`$0.41589 + $1.02958 =
$1.4455`) plus a small margin for whatever additional `observe` calls the new suffix sentence
elicits. Hard bounds are **unchanged**: `$5.00`/`125cr` Red arm cap, `$2.00`/`50cr` MiniWoB arm
cap, `$7.00`/`175cr` combined PASS bar, `250cr` hard breaker (live, wired, TRIP-tested per the
v1 pre-reg's precondition 4).

**Headroom check (why "a few extra observe calls" is not a real cost risk):** v1's Red arm used
`10.397` of its `125`-credit soft cap (8.3%) and `$0.416` of its `$5.00` cap (8.3%); MiniWoB used
`25.74` of `50` (51.5%) and `$1.03` of `$2.00` (51.5%). Even a generous 10-20 extra `observe`
calls per arm (each a small tool-call-plus-short-reasoning turn, not a new full decision cycle)
would not remotely threaten either arm's cap, let alone the combined `$7.00`/`175cr` PASS bar or
the `250cr` hard breaker — H-d (§3) is the check that confirms this held in practice, not just in
projection.

## 7. Pre-registered escalation ladder for v3 (written now, before v2 runs)

- **If v2 Arm R fails the SAME way** (still `red_no_sustained_battle_exit`, still <10 post-exit
  rows) — a brief-level fix has now failed **twice** on the identical failure mode. Per
  **run-brief-authoring** §4's own stated lesson ("an instruction stated once ... is not
  enforcement" / "a brief-level fix that fails twice escalates to a mechanical guard, never a
  third rewording" — `.claude/PROTOCOL.md` §6 anti-thrash), v3 does **not** propose a third
  wording. v3's candidate instead moves the discipline into the harness: have
  `tools/gate0_appserver_arm.py`'s turn-driving code (`run_gate0_arm_turn`) itself force a small,
  fixed number of additional `observe`/`wait`-tool round-trips after the model's `turn/completed`
  before accepting the turn as finished — a **scaffolding-side** change (world/launcher code, not
  the brain, not `core/contracts.py`, not the tool schema), consistent with safety-invariants law
  7. Flag explicitly: this is a larger, code-level change to the safety-critical launcher itself
  (would need `expected_launcher_sha256` re-pinned and its own adversarial review, not just a
  fixture regen) — bigger than this pre-reg's scope, and would need its own write-up.
- **If v2 Arm R fails a DIFFERENT way** (e.g., predicate fails on `red_missing_player_hp_oracle`,
  `red_map_changed_during_battle_exit_span`, or never reaches the battle at all) — do **not**
  assume the brief is still the problem. Run **diagnose-a-run** against the raw v2 artifacts
  first; a new failure mode needs its own diagnosis before any vNext is proposed.
- **If v2 Arm R PASSES but Arm W's seed-1001 partial is unchanged** (H-c holds) — bank the
  partial evidence exactly as the design doc's escalation shelf directs: *"One task passes: bank
  the partial evidence. Fix the failed seam, then wait for a new pre-registration; do not rerun
  the passing arm."* A MiniWoB-specific v3 (if David wants one) is a separate, later
  pre-registration — not folded into this ladder.
- **If v2 Arm R PASSES but costs regress toward the caps** (H-d fails, i.e. the extra observing
  loop ran long) — that is `FAIL_CHEAP`, not `FAIL_CAPABILITY`; the v3 candidate is a cap on how
  many extra observe/wait steps the "settle" instruction can license (a stricter, more explicit
  brief wording — tightening, not loosening), before jumping to a scaffolding change.
- **If both arms PASS** — per the design doc: *"add one held-out task/world at the next phase
  exit. Do not turn Gate 0 into the full ten-task graduation exam midstream."* Gate 0 v2's own
  scope ends there; no further Gate-0-labeled attempt follows automatically.

## 8. Open question for David — run v2, or bank v1 as the honest baseline?

Two live options; this document does not decide between them:

- **(a) Bank v1 as-is.** v1 is a clean, fully-scored, non-ambiguous result: `NO_LEAK` clear on
  both arms, Cheap passed decisively, one arm (`Red`) that *beat the human baseline on both
  Capability sub-bars* and failed only on a 10-row sustained-exit technicality it missed by 6
  rows, and one arm (`MiniWoB`) with a genuine, non-premature partial. This is real, decisive,
  reportable evidence as-is — the design doc explicitly treats a banked `FAIL_CAPABILITY` as
  legitimate, informative evidence, not a wasted attempt.
- **(b) Run v2.** The identified failure mode is narrow, mechanically diagnosed (not a mystery),
  and the proposed fix is a single sentence that does not touch the predicate, the scorer, the
  task definition, or the frozen brain/contract. Marginal cost is small: ~$1.50 expected, against
  a $7.00/175-credit PASS bar and a $10/250-credit hard-breaker economics the campaign has
  already accepted for Gate 0 generally.

**My recommendation: (b), run v2.** The cost is trivial relative to the gate's own budget, the
fix is the narrowest possible lever (prose only, one shared sentence, no code/predicate/fixture
edit beyond the two `task_sha256` regenerations it mechanically requires), and per gate-methodology
§3 this exact situation — a clean FAIL with a well-understood, narrowly-fixable cause — is what
"pre-registered escalation" exists for, as opposed to either re-running blind or declaring the
axis closed on a technicality the human baseline itself doesn't hit. That said, this is explicitly
David's call, not mine to make: this pre-reg still needs an adversarial review pass before any
launch decision (**gate-methodology** §3, not yet done for this DRAFT), and the DECISION to spend
the ~$1.50 is his per safety-invariants law 1, regardless of which way the recommendation leans.

## Sources

- `reports/2026-07-18-gate0-prereg.md` (v1 pre-reg, structure mirrored)
- `reports/2026-07-24-gate0-prereg-amendment-appserver.md` (app-server launch-surface amendment,
  inherited verbatim except §1/§2 above)
- `reports/2026-07-13-minimum-north-star-gate-0-design.md` (design doc: bars, escalation shelf,
  tightening-not-loosening law)
- `eval/score_gate0.py` (frozen scorer, read in full this session — `_red_success`,
  `_miniwob_success`, `_arm_metrics`, `score`)
- `tools/check_gate0_codex.py` (`PIN_FIELDS`, `CONSTANCY_FIELDS`, `audit()`)
- `tools/gate0_appserver_arm.py` (`ARM_TASK_SENTENCES`, `COMMON_TASK_SUFFIX`, `task_text_for`,
  `render_brain_config_toml`, `run_gate0_arm_turn`)
- `eval/fixtures/gate0_expected_pins_red.appserver.json`,
  `eval/fixtures/gate0_expected_pins_miniwob.appserver.json`,
  `eval/fixtures/gate0_signature.appserver.json`
- `runs/gate0_paid/red/{agent_metrics.json,world/oracle.jsonl,transcript.jsonl}`,
  `runs/gate0_paid/miniwob/agent_metrics.json` (banked v1 artifacts, gitignored, read-only,
  re-verified this session — cited as on-disk evidence per gate-methodology §7)
- `.claude/skills/gate-methodology/SKILL.md`, `.claude/skills/run-brief-authoring/SKILL.md`,
  `.claude/skills/safety-invariants/SKILL.md`
