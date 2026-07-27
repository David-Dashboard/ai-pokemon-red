# Gate 0 v2 pre-registration — Arm R re-attempt under a corrected brief

**Written 2026-07-25. Rewritten end-to-end 2026-07-28** after an adversarial review found the
2026-07-25 draft NOT freezable (the recommended brief fought the predicate it targeted; the pin
list was incomplete; a source gate fired before capability; the best case was still FAIL; §0
misstated the banked v1 verdict). Every defect that review named is addressed below, and the
passages that would have let a failure be re-labelled a success are deleted, not softened.
A late challenge — that the harness is structurally incapable of ever emitting `PASS` — was raised
and withdrawn during the rewrite; §0.1 records the adjudication (true of
`tools/check_gate0_codex.py::audit()`'s own verdict field, false of the scorer this document names
as the pass bar) as a **non-blocking** note, since it is a recurring misreading the v1 pre-reg
already warned against.

**Status: DRAFT — FOR DAVID. $0, docs only.** This document proposes a change; it does not make
one. No fixture, scorer, predicate, or pinned file is edited by this document. No paid run is
launched by writing it. Paid runs are now authorized in general, which is exactly why this
document must be freezable before it is used: it is on the critical path, not hypothetical.

**Authorization boundary (safety-invariants law 1, gate-methodology §3):** the DECISION to spend
is David's. This pre-reg earns the right to be reviewed, not the right to run.

**Reading order:** §0 is a list of blocking preconditions. If any is unmet at launch time, the
run is void by construction and must not be launched. §2 states, before any number exists, what
counts as the agent FAILING.

---

## 0. BLOCKING PRECONDITIONS — all must be satisfied before launch

Each was verified on disk this session (2026-07-28), not assumed. A run launched with any of
these open produces an unscorable or void artifact and wastes the attempt.

| # | Precondition | State verified 2026-07-28 | Blocks |
|---|---|---|---|
| **P1** | `runs/gate0_paid_human_baseline/miniwob/human_metrics.json` exists | **MISSING.** The directory holds only `human_metrics.INCOMPLETE_1785175245.json`, a partial `oracle.jsonl`, `oracle.attempt1_1785174570.jsonl`, and frames `ep0_step0.png`…`ep1_step8.png` — an abandoned capture. | Any `score_manifest()` verdict, **both arms** |
| **P2** | `runs/gate0_live_breaker/live_breaker_dry_run_trip.json` exists and hashes to `27538b256bfdf276af91d4533b83247361ddbe470c5682b8addd58bda340e734` | **MISSING** — `runs/gate0_live_breaker/` does not exist in the primary checkout. v1 banked `source_unreadable:live_breaker` + `live_breaker_artifact` for exactly this. Regenerable byte-exactly from `tools/gate0_credit_breaker.py`. | Any `score_manifest()` verdict |
| **P3** | A fresh output directory, with `artifact_paths` / `audit_paths` re-pointed to it | **NOT DONE.** All twelve pinned paths in `eval/fixtures/gate0_paid_source_pins.json` point into `runs/gate0_paid/…`, which v1 already occupies. `runs/` is append-only raw data; v2 must not write there. | The whole attempt |
| **P4** | The four `task_sha256` pins and the four `expected_pins_sha256` cascade values re-frozen (§6) | **NOT DONE** (this document does not edit fixtures). | Launch audit + scoring |
| **P5** | A mechanical post-run hash-freeze step for the run-produced artifacts (§6, items 11–12) | **NOT PRE-REGISTERED ANYWHERE UNTIL NOW.** See §6. | Any `score_manifest()` verdict |
| **P6** | `sha256(eval/fixtures/gate0_miniwob_paid_seeds.json)` recomputed **from the tree that will score**, == `263aaed17ee653c8b32e608d88ed1b8d29d6a424d29ce2e123671b56df159e63` | Matches in a clean LF checkout (recomputed this session). v1 nonetheless banked `frozen_seed_hash`, so the scoring tree materialized CRLF. Check, do not assume. | Any `score_manifest()` verdict |
| **P7** | Adversarial review of **this** document, posted on the PR | Not done for this rewrite. | Launch decision |

### 0.1 Settled: the pass bar IS emittable — `audit()`'s ceiling is not the gate's

A review during this rewrite raised, then withdrew, the alarm that the harness is structurally
incapable of emitting `PASS` and that v2 could therefore disconfirm nothing. **It is recorded here
because it is a recurring misreading, not because it is a blocking risk. It is not a precondition.**

**What is true:** `tools/check_gate0_codex.py::audit()` is permanently fail-closed on wake
accounting. It always returns `"wakes": None` / `"wake_accounting": "INSUFFICIENT_WAKES"`
(`:297-298`), and its verdict chain (`:282-291`) ends in an unconditional
`else: overall = "NO_GO_INSUFFICIENT_WAKES"` — there is no `PASS` branch. Consequently
`check_gate0_codex.build_agent_metrics` (`:311-329`), which refuses anything but `overall ==
"PASS"`, is dead code by its own docstring's admission.

**What does not follow:** that this caps the gate. `eval/score_gate0.py::score()` consumes exactly
four fields off an audit dict — `leak_failures`, `constancy_failures`, `run_failures` (`:307-310`)
and `accounting_failures` (`:326`). It **never reads `audit()`'s `overall`**, and never gates on
`wake_accounting`, which is read once (`:287`) purely to populate the informational payload
reported at `:366-371` as `"status": "DEFERRED"`. **The v1 pre-registration already said so, and
this document simply restores that reading** — `reports/2026-07-18-gate0-prereg.md:81-83`:

> `tools/check_gate0_codex.py`'s own `overall`/`no_leak`/`wake_accounting` fields (e.g.
> `NO_GO_INSUFFICIENT_WAKES`) are an **intermediate per-arm audit input** consumed by
> `score_gate0.py`, not the gate's printed verdict — do not quote them as the Gate 0 result.

**Why wakes are non-gating, in one paragraph so it stops being re-litigated.** A wake is one model
decision. Nothing in the Codex JSONL stream emits one: PR #125 proposed `wakes = usage_events`, and
PR #126 falsified it — a single `turn.completed` bundles ≥2 real decisions and its usage is
cumulative for the whole turn, a ≥2x undercount, with no correct event to substitute
(`reports/2026-07-21-gate0-wake-grounding.md:52-62`). Following David's 2026-07-21 decision, wakes
are DEFERRED and non-gating, and Cheap rests on cost-per-task
(`eval/score_gate0.py:263-281`, `:331-336`, `"cheap_basis": "cost_per_task"`). Gate 0 was genuinely
unpassable for exactly one day — 2026-07-21 — and that is documented and closed. The production
launcher already routes around the dead gate: `tools/gate0_appserver_arm.py:858-863` says in as many
words that it deliberately does **not** call `check_gate0_codex.build_agent_metrics` ("permanently
unreachable dead wake gate") and builds the metrics record itself from `primitive_action_events`.

**Demonstrated, `$0`, this session.** `score()` fed an audit dict with the *exact* shape a real
`audit()` returns on a clean run — `overall: "NO_GO_INSUFFICIENT_WAKES"`, `wakes: None`,
`wake_accounting: "INSUFFICIENT_WAKES"`, all four failure lists empty — plus a synthetic Red oracle
satisfying all nine `_red_success` clauses, five clean MiniWoB terminals, and in-cap metrics:

```
scorer overall  : PASS
scorer readiness: GO
wake_accounting : DEFERRED
failures        : {"constancy": [], "leak": [], "infra": [], "capability": [], "cheap": [], "source": []}
```

Corroborated by two committed tests: `tests/test_score_gate0.py::test_pass_matrix` (`:180-181`) and
`::test_wake_cap_alone_no_longer_blocks_pass` (`:220-224`, asserting `overall == "PASS"` and
`wake_accounting["status"] == "DEFERRED"` in the same test).

**And the gate has already been observed discriminating on performance, not artifacts.** v1's two
arms failed on real capability — Arm R `red_no_sustained_battle_exit`, Arm W
`miniwob_episode_1_terminal_not_success` (seed 1001, reward 0.667)
(`reports/2026-07-24-gate0-paired-verdict.md`). Those are agent-behaviour outcomes; the harness
distinguished them from each other and from the pin failures.

**Non-blocking observations, recorded so the next reader does not re-derive them:**

- `audit()`'s `overall` must never be quoted as the gate verdict (D-7). The authority is
  `eval/score_gate0.py::score()["overall"]`.
- `tools/check_gate0_codex.py:380` is `return 0 if summary["overall"] == "PASS" else 1`, so that
  CLI **always exits non-zero**. Any script branching on that exit code is reading a constant. Not
  a precondition; worth knowing before someone wires an automation to it.
- The dead `PASS` branch and the unreachable `build_agent_metrics` are a standing trap that has now
  misled at least one reviewer into declaring the gate unwinnable. Worth a separate cleanup PR;
  **out of scope here, and not a v2 blocker.**
- Running the `$0` dry check above from the actual scoring tree before launch is cheap and sensible
  hygiene, particularly after the §6 fixture edits. It is **hygiene, not a gate** — nothing in this
  document is conditioned on it.

### P1 in detail — the source gate that fires before capability is evaluated

`eval/fixtures/gate0_paid_source_pins.json:11` points `miniwob_human` at
`runs/gate0_paid_human_baseline/miniwob/human_metrics.json`; `:20` pins its hash as
`PENDING_NOT_YET_CAPTURED_paid_seed_human_replay_tool_not_built`. With the file absent,
`_verify_sources` raises inside its `try` and appends `source_unreadable:miniwob_human`
(`eval/score_gate0.py:249-260`). `failures["source"]` is then non-empty, and `score()`'s
precedence chain returns at **`eval/score_gate0.py:353-354`**:

```python
elif failures["source"]:
    verdict, readiness = "INSUFFICIENT_DATA", "INSUFFICIENT_SOURCE"
```

— **before** the capability branch at `:355-356`. The verdict is a single combined value across
both arms, so this is not an Arm-W-only problem: it makes the *entire* Gate 0 unscorable on
capability no matter how well the agent plays either world. Any pre-registration whose "if both
arms PASS" branch does not carry this as a precondition is describing an unreachable state.

The artifact is produced by `tools/capture_gate0_baseline_miniwob.py --mode paid_gate0
--i-am-human` and by a real human only (`:202-205` refuses the mode without the flag; `:291-292`
suppresses the task utterance to protect the held-out seeds). **An unresolved rig contradiction is
currently blocking that capture** — the Submit control renders outside the clickable viewport band
on 6-checkbox layouts (`world_mcp.py:2199-2204` rejects any click below the viewport rather than
silently clamping), yet the banked Arm W run completed all five episodes. That contradiction must
be resolved before the capture is attempted, or the resulting denominator is not trustworthy.
Tracked separately; **not** in scope for this document.

Under §3's Arm-R-only scope, P1 stops blocking *this* attempt (which is not scored through
`score_manifest()` at all — see §3) but remains blocking for **any** Gate 0 verdict, ever.

---

## 1. The banked v1 result, stated correctly — and why it stays VOID

The 2026-07-25 draft claimed v1 banked `FAIL_CAPABILITY` on both arms. **That is wrong and is
corrected here.**

**The banked frozen-scorer verdict for v1 (2026-07-24) is `CONSTANCY_BREACH` / `NO_GO`**
(`reports/2026-07-24-gate0-paired-verdict.md` §1 and §4, which prints the full verdict JSON
verbatim). `score()`'s precedence chain (`eval/score_gate0.py:347-360`) short-circuits at
`constancy` before `source` and before `capability`, so no capability verdict was ever reached.

The predicate results *underneath* that verdict — diagnostic, not banked verdicts:

- **Arm R:** `_red_success` → `(False, ['red_no_sustained_battle_exit'])`. Party `0→1` at watch-row
  333; `in_battle == 2` for rows 391-433; only 4 trailing `in_battle == 0` rows where the predicate
  needs a 10-row window. Metrics `127.75 s` / 142 primitive actions vs human `233.288 s` / 271;
  `$0.41589` / `10.397275` credits.
- **Arm W:** `_miniwob_success` → `(False, ['miniwob_episode_1_terminal_not_success'])`. Five
  terminals, one per seed, `abandoned=false` throughout; seed 1001 at `reward = 0.6666666666666666`
  against a predicate that requires `reward == 1.0`. 97 actions / `295.594 s`; `$1.02958` /
  `25.7395` credits.
- **Cheap:** the `$1.4455` / `36.14` figure is a **hand computation against documented caps, not a
  scorer verdict** — `failures["source"]` was non-empty, so `score()`'s Cheap block
  (`eval/score_gate0.py:329-345`) never executed. `"cheap": []` in the banked JSON means NOT
  EVALUATED.

### The governance fact, encoded and not argued with

An audit has since **proven the v1 breach was a benign fixture-lifecycle artifact**
(`reports/2026-07-28-gate0-constancy-breach-addendum.md`, PR #175 — the authority on the mechanism;
its evidence is cross-referenced here, not restated).

Four of the six `constancy` entries (`config_sha256`, `codex_mcp_list_sha256`, both arms) were
comparisons of the run's **`handshake-receipt.json`** against the literal *placeholder* string
`"CONSTRAINT:launch-invocation-dependent-recompute-at-signature"` — a pin that was never a real
value. The launcher fix that resolves them at launch time
(`tools/gate0_appserver_arm.py::resolve_expected_pins()`, commit `3c3f704`, "fix(gate0-appserver):
resolve expected-pins gap causing a benign CONSTANCY_BREACH", 2026-07-24 23:56:06 +0200) postdates
**both** arms, but by very different margins, and the difference must not be blurred:

- **Arm W:** receipt at 23:39 local, ~295.594 s of run — the fix landed roughly **13 minutes**
  after that arm completed.
- **Arm R:** receipt written **16:00:11**, i.e. the fix postdates it by roughly **eight hours**.
  The "13 minutes" framing is **true of the MiniWoB arm only** and must not be stated of both.

The remaining two entries (`tool_schema_sha256`, both arms) were a serialization difference between
the PowerShell-era capture recipe and the app-server's Python `json.dumps` — specifically in
**separators, non-ASCII escaping, and (Arm R only) apostrophe escaping**. **Key ordering is
identical**; earlier documents that guessed "whitespace/key-order" are wrong and should not be
propagated. The values have since been independently re-derived and re-pinned on `main`
(commit `346b612`).

**The v1 result nonetheless remains VOID.** Two frozen laws say so, and neither has an exception
for "the breach turned out to be benign":

- `reports/2026-07-18-gate0-prereg.md:117-119` — *"`NO_LEAK` or `CONSTANCY_BREACH` void the attempt
  as evidence … constancy/no-leak checks run before task scoring, so neither is a capability
  outcome."*
- `reports/2026-07-13-minimum-north-star-gate-0-design.md:372-373` — *"Bank PASS/FAIL/
  INSUFFICIENT_DATA/CONSTANCY_BREACH as printed. Never rescue a marginal result with an informal
  rerun."*

The fact that we can now explain the breach is precisely the kind of after-the-fact knowledge a
pre-registration exists to make irrelevant. A pre-registration that can be reinterpreted once the
result is known is decorative. v1 is banked as `CONSTANCY_BREACH`, void as capability evidence, and
is not reinterpreted anywhere in this document. Its predicate outputs are used here only to choose
what to test next — never as evidence of capability or its absence.

**Cross-reference:** `reports/2026-07-28-gate0-constancy-breach-addendum.md` (PR #175) is the
authority on the breach mechanism. This section defers to it and deliberately does not duplicate
its evidence. Nothing in it can un-void v1.

---

## 2. DISCONFIRMATION — what counts as the agent FAILING

Stated before any v2 number exists, in terms a hostile reader can check mechanically from the
on-disk artifacts with the unedited `eval/score_gate0.py`.

**These conditions bite.** The verdict is a function of agent behaviour: `eval/score_gate0.py::
score()` emits `PASS`/`GO` on a clean input and `FAIL_CAPABILITY` on a failing predicate (§0.1,
demonstrated at `$0`), and v1's two arms already failed on real capability rather than harness
artifacts. A v2 run can genuinely disconfirm.

**v2 SUCCEEDS if and only if all five hold. Any single miss is a FAIL.**

| ID | Check | Mechanical test |
|---|---|---|
| **S-1** | Red predicate clean | `_red_success(_jsonl("<v2out>/red/world/oracle.jsonl"))` returns exactly `(True, [])` |
| **S-2** | Capability sub-bars | `wall_clock_s <= 466.576` (= `2 × 233.288`) **and** `primitive_actions <= 542` (= `2 × 271`) |
| **S-3** | No leak, no constancy failure | `audit()` returns empty `leak_failures` **and** empty `constancy_failures` for the arm |
| **S-4** | Cheap, frozen caps | `cost_usd <= 5.00` and `normalized_credits <= 125` |
| **S-5** | Attempt integrity | Exactly one launch; artifacts written to the §0-P3 fresh directory; no `runs/` file overwritten |

**Explicit FAIL conditions, spelled out because they are the ones this brief newly puts at risk:**

- **D-1.** `_red_success` returns any non-empty failure list. There is no partial credit: the
  function returns `not failures` over a list that must be **empty**. Satisfying eight of the nine
  clauses in §5.4 is a FAIL.
- **D-2.** `red_no_free_movement_after_exit` — the clause the 2026-07-25 draft's own recommended
  brief would have induced (§5). If v2 trades the sustained-exit clause for this one, that is a
  FAIL and a *worse* outcome than v1's predicate result, not a lateral move.
- **D-3.** `red_map_changed_during_battle_exit_span` — the clause the *new* brief puts at risk by
  instructing post-task movement. A FAIL here means the settle wording licensed too much roaming
  and must be tightened, not explained away.
- **D-4.** If David overrides §3 and runs Arm W: any `_miniwob_success` failure, **specifically
  including** `miniwob_episode_N_terminal_count` or `miniwob_episode_N_terminal_not_last_row`
  caused by the settle instruction itself (§5, Arm W analysis). That is the brief actively damaging
  an arm, and is a FAIL of the intervention, not an incidental.
- **D-5.** Any `leak_failures` or `constancy_failures` → the attempt is **VOID**: not a FAIL, not a
  PASS, no capability evidence in either direction, no rescue, regardless of how benign the cause
  later proves to be. Same law as §1.
- **D-6.** `_red_success` clean but S-2 or S-4 missed → FAIL (`FAIL_CAPABILITY` or `FAIL_CHEAP`
  respectively in the frozen vocabulary).
- **D-7.** Quoting `audit()`'s own `overall` (permanently `NO_GO_INSUFFICIENT_WAKES`) as the gate
  verdict, in either direction — forbidden by `reports/2026-07-18-gate0-prereg.md:81-83` and
  restated in §0.1. Not a run outcome; a verdict report that cites it as one is a reporting failure
  regardless of the underlying result.

**Forbidden interpretations.** These framings appeared in the 2026-07-25 draft and are banned from
any v2 verdict, in advance:

- "failed only on a … technicality it missed by N rows" — a predicate clause is not a technicality;
  missing it is a FAIL.
- "a clean, fully-scored, non-ambiguous result" said of a run whose banked verdict is
  `CONSTANCY_BREACH` — a void attempt is not a clean result.
- "bank the partial evidence" invoked to convert a combined FAIL into a partial success.
- "structurally inert for Arm W" — §5 shows this claim is false as stated.
- "a technicality the human baseline itself doesn't hit" — the human baseline satisfying a clause
  is evidence the bar is achievable, never a reason to discount an agent's miss of it.

---

## 3. Scope decision: v2 is **Arm R only**, and is **not** a Gate 0 verdict

The 2026-07-25 draft proposed re-running both arms while explicitly "doing nothing else about the
0.667 episode" and predicting it would recur. Since `score()` emits **one combined verdict** across
both arms and `_miniwob_success` requires `reward == 1.0` on **all five** seeds
(`eval/score_gate0.py:112-120`), that plan banks FAIL by construction: a perfect Arm R cannot
outvote a repeat of seed 1001. Paying for a foregone conclusion is not an experiment.

**Decision: Arm W is scoped OUT of v2.** Reasoning, in order of weight:

1. **A v2 Arm W on seeds 1000-1004 is not fresh held-out evidence** (§4). Even a 5/5 would not
   license the Generality claim Gate 0 exists to test.
2. **Arm W has no denominator.** P1's human baseline does not exist, so Arm W cannot produce a
   scorable capability number at all.
3. **The 0.667 may be a rig defect, not a capability miss.** The Submit-outside-the-clickable-band
   contradiction (§0-P1) is unresolved. Re-running the arm while its environment is under
   suspicion buys noise.
4. **Nothing in the v2 intervention targets Arm W.** The suffix edit addresses a premature-stop
   failure mode; seed 1001 terminated at the environment's own `done`. There is no mechanism by
   which v2 improves it — and §5 shows a real mechanism by which v2 could *damage* it.

**What v2 therefore buys, stated without inflation:** one fact — whether this brain, under a
corrected brief, satisfies the frozen `_red_success` predicate on the fixed Red start. That is one
arm of a two-arm gate. **It is not a Gate 0 PASS and must never be reported as one.** Gate 0's
Generality axis requires both arms; a single-arm result cannot satisfy it, whatever it prints.

**Mechanical consequence, pre-registered now rather than discovered later:** the frozen scorer has
**no single-arm mode**. `score_manifest()` always audits and scores both arms
(`eval/score_gate0.py:376-389`), and `_verify_sources` unconditionally requires all six named
artifacts including `miniwob_human`. A Red-only v2 therefore **cannot** be scored end-to-end by
`score_manifest()`. It will be scored by executing the unedited `_red_success` and `_arm_metrics`
directly against the produced oracle and metrics — exactly the procedure
`reports/2026-07-24-gate0-paired-verdict.md` §2 already used. **v2's output is a PREDICATE result,
not a frozen-scorer verdict, and must be labelled as such in its verdict report.** This is a
limitation, disclosed in advance, not a workaround.

**If David wants a full two-arm Gate 0 v2 instead**, that is a larger, separate pre-registration
requiring: a *new* held-out MiniWoB seed block (§4), the paid human baseline (P1), and a diagnosis
of the 0.667. Not this document.

---

## 4. Held-out freshness — seeds 1000-1004 are spent

MiniWoB seeds `1000..1004` were **consumed by the v1 agent attempt on 2026-07-24**. They are named
in merged, committed files (`eval/fixtures/gate0_miniwob_paid_seeds.json`,
`eval/fixtures/gate0_paid_source_pins.json:5`, both source-pin fixtures, and the banked verdict
reports), so merging this document burns nothing new.

**What follows, stated plainly:** a v2 Arm W result on those seeds is **no longer fresh held-out
evidence**. The design doc's held-out contract (`reports/2026-07-13-minimum-north-star-gate-0-
design.md:273-276`) is *"the agent sees held-out seeds `1000..1004` first; only after its artifacts
are banked does the human replay those exact seeds"* — a one-shot ordering. Once the agent has
played them and the artifacts are on disk and analysed, any subsequent agent run on the same seeds
is a re-attempt on known material, and its score cannot be reported as held-out generalization.

Three consequences, all binding:

1. Any future Arm W attempt intended as held-out evidence needs a **new seed block**, pre-registered
   and frozen before it is looked at.
2. The **human** replay of `1000..1004` (P1) is *not* affected — it is the denominator for the
   already-banked agent artifacts, and the ordering it must respect (human after agent) is
   satisfied. It stays required.
3. The v1 Arm W artifacts remain the only held-out MiniWoB evidence this project has, and they are
   attached to a **void** attempt (§1). The honest statement of the MiniWoB position is therefore:
   *no valid held-out MiniWoB capability evidence exists, and the seeds that would have produced it
   are spent.*

---

## 5. The intervention: one shared task-suffix sentence — with a clause-by-clause proof

Per **run-brief-authoring**, the brief IS the intervention; reviewers must critique these exact
words. The only line in scope is `COMMON_TASK_SUFFIX` in `tools/gate0_appserver_arm.py` (`:187-190`
on `main`), appended to both arms' task sentences by
`task_text_for(arm) = ARM_TASK_SENTENCES[arm] + "\n" + COMMON_TASK_SUFFIX + "\n"` and written
byte-identically to `launch/TASK.md`. There is no separate `CLAUDE.md` in the app-server harness —
this text *is* the brief. `ARM_TASK_SENTENCES`, `DEVELOPER_INSTRUCTION`, `render_brain_config_toml`,
the world images, the tool allowlists, the bars, and the caps are **unchanged**.

### 5.1 Why all three 2026-07-25 candidates were unusable

All three told the agent to stop moving. Candidate C, the recommended one, said: *"after your last
consequential action, continue observing the world for several more steps until the state has
visibly stopped changing, then stop."*

An agent obeying that literally earns the ten rows `red_no_sustained_battle_exit` needs and
**loses `red_no_free_movement_after_exit`** (`eval/score_gate0.py:85-88`), which requires at least
two distinct post-exit `(x, y)` tiles. The draft traded one predicate clause for another and called
it a fix. That defect is the reason this document was rewritten.

### 5.2 The mechanical facts the fix rests on (read from the code, not assumed)

- **One oracle watch row is written per `observe()` call**, at `core/perception_plugin.py:242`
  (`self._log_oracle(...)`, once per `observe`, after the patience auto-advance loop). Not a
  polling sampler; not per primitive action. "Ten rows" therefore means **ten further `observe`
  calls**.
- **`explore` and `goto` each emit many rows and move the player, in one tool call.** Both dispatch
  to `World._run_autopilot` (`world_mcp.py:1861-1899`), whose loop calls `self.plugin.observe(...)`
  once per step (`:1868`) and then executes a movement action (`:1885`), for up to `max_steps`
  (default 40 for `explore`, 60 for `goto`, hard-capped 200), followed by one more `observe` in the
  dispatch (`:1918-1919`, `:1927-1928`). A single post-battle `explore` call therefore produces
  ~41 rows across many distinct tiles.
- **`primitive_actions` counts MCP tool calls, not autopilot steps** —
  `tools/check_gate0_codex.py:251-258` increments `primitive_action_events` once per
  `mcp_tool_call` item. One `explore` = one primitive action, whatever it does internally. The
  settle behaviour is therefore nearly free against S-2.
- **In MiniWoB, `observe` / `read_region` / `whats_changed` write NO oracle row** — they return at
  `world_mcp.py:2164-2169`, above the logging block. Only `click` / `type_text` / `press_key` /
  `reset_episode` append a row (`:2229-2230`, `:2182-2183`). This asymmetry is what makes the Arm W
  analysis in 5.5 come out the way it does.

### 5.3 The proposed `COMMON_TASK_SUFFIX` (v2), verbatim

> "Use only the connected world MCP tools and screen-derived state. Do not use shell, files, web,
> tool search, or connectors. Begin by observing. Saying the task is done is not doing it: when you
> believe the stated task is complete, do not end your turn on that statement. Stay where you are
> and keep working the world for a further stretch — alternate observing with small local moves
> around your current position, without leaving the place you are in and without beginning any new
> objective — until several consecutive observations show nothing further changing. If the
> environment states that the episode, task, or input is over, or rejects further input, stop
> acting on it immediately and do not act on it again. Stop when the stated task is complete and
> has been confirmed this way."

Two clauses carry all the weight, and each is there for a named predicate clause:

- *"alternate observing with small local moves around your current position"* — feeds
  `red_no_sustained_battle_exit` (observes → rows) **and** `red_no_free_movement_after_exit`
  (moves → distinct tiles) with the same behaviour. This is the clause the old candidates lacked.
- *"without leaving the place you are in"* / *"if the environment states … is over … stop acting"*
  — the two guards, protecting `red_map_changed_during_battle_exit_span` and Arm W's terminal-row
  ordering respectively.

### 5.4 Clause-by-clause proof against `_red_success` (`eval/score_gate0.py:34-89`)

Every clause the function can emit, in the order it can emit it. "Unaffected" means the suffix
cannot change the behaviour that determines it, and v1's own trace already satisfied it.

| # | Clause | Code | How the v2 brief satisfies it |
|---|---|---|---|
| C1 | `red_not_fresh_party_zero` | `:37-38` | **Unaffected.** Requires `watches[0]["party"] == 0` — a property of the frozen fresh-bedroom savestate, not of the brief. The suffix adds nothing before "Begin by observing". v1 satisfied it. |
| C2 | `red_no_party_0_to_1` | `:39-43` | **Unaffected.** `ARM_TASK_SENTENCES["red"]` still says "obtain your first Pokemon from Professor Oak". v1 satisfied it (transition at row 333). |
| C3 | `red_first_party_transition_not_exactly_0_to_1` | `:44-46` | **Unaffected.** Same as C2 — the *first* party change must be `0→1`, which a fresh start plus one starter produces. The suffix does not encourage acquiring anything before the starter ("without beginning any new objective" cuts the other way). v1 satisfied it. |
| C4 | `red_no_trainer_battle_after_party_acquisition` | `:47-51` | **Unaffected.** The task sentence still requires winning the first rival battle. v1 satisfied it (`in_battle == 2`, rows 391-433). |
| C5 | `red_no_sustained_battle_exit` | `:52-56` | **THE v1 MISS. Satisfied by construction.** Needs some `i ∈ [battle_idx+1, len(watches)−10]` with `watches[i:i+10]` all `in_battle == 0`. One row per `observe` (5.2), so this needs ≥10 further `observe` calls after the battle ends. "keep working the world for a further stretch — alternate observing with small local moves … until several consecutive observations show nothing further changing" produces exactly that; a single `explore` call alone produces ~41. v1 produced 4. |
| C6 | `red_missing_player_hp_oracle` | `:70-78` | **Unaffected.** Requires `party_hp_hi`/`party_hp_lo` present as ints `0..255` on every non-corrupt row of `watches[battle_idx : exit_idx+10]`. Both are in the frozen watch spec (`world_mcp.py:176-178`, `0xD16C`/`0xD16D`). A brief cannot change which RAM addresses are sampled. |
| C7 | `red_map_changed_during_battle_exit_span` | `:80-82` | **Satisfied by the "without leaving the place you are in" guard.** `map` must equal `battle_map` on every row from `battle_idx` through `exit_idx+9`. This is the clause the settle instruction *newly* puts at risk: an unconstrained "wander around" would walk the autopilot through the lab door within the first ten post-exit observes and fail here. The brief forbids leaving the current place and forbids starting anything new. Note the constraint binds only through `exit_idx+9`; the brief deliberately does **not** say so — stating the boundary would leak the predicate's shape. |
| C8 | `red_player_hp_reached_zero` | `:83-84` | **Unaffected.** `min(hp) > 0` over the same span. The settle behaviour is local movement in the interior the battle ended in and explicitly starts no new objective, so it opens no new encounter. v1 satisfied it. |
| C9 | `red_no_free_movement_after_exit` | `:85-88` | **THE CLAUSE THE OLD DRAFT WOULD HAVE BROKEN. Satisfied.** `post = [(x,y) for w in watches[exit_idx:] …]` needs `len(set(post)) >= 2`. Pure observation leaves `(x,y)` constant and fails this. "small local moves around your current position" changes `(x,y)` while `in_battle` stays `0`; any autopilot step both observes and moves, so C5 and C9 are fed by the same action. |

**Are the clauses mutually satisfiable? Yes — this is not a scorer bug.** C5 constrains only
`in_battle`; C9 constrains only `(x, y)`; walking around out of battle sets `in_battle == 0` and
varies `(x, y)` on the same rows. The single genuine coupling is C7, which forbids that walk from
crossing a map boundary inside the first ten post-exit rows. "Walk around this room for a while,
observing as you go, without going through a door" satisfies C5, C7 and C9 simultaneously, with C6
and C8 untouched. No clause pair is in conflict.

### 5.5 Arm W: the change is **NOT** "structurally inert" — it is a live risk

The 2026-07-25 draft asserted the suffix edit was "structurally inert for Arm W". **That claim is
false**, and the correction matters more than the claim did:

`MiniWobSession.call` writes an oracle row for every `click` / `type_text` / `press_key`
(`world_mcp.py:2229-2230`), tagged with the *current* `self._episode_idx` and `self.mw.current_seed`
— which do not advance until `reset_episode`. So **any action taken after an episode's terminal and
before `reset_episode` appends a further row for that same `(episode, seed)`**. Feed that to
`_miniwob_success` (`eval/score_gate0.py:103-124`):

- if the extra row carries `done is True`, `len(terminal_idx) != 1` → `miniwob_episode_N_terminal_count`;
- if it carries `done is False`, the terminal is no longer the last row → `miniwob_episode_N_terminal_not_last_row`.

**Either way that episode hard-fails.** A settle instruction phrased as "keep acting after you think
you're done" is therefore not inert for Arm W — it is potentially fatal to it. Two things contain
the risk in the v2 wording, and one does not:

- **Contained (end of run):** after the fifth terminal, `_advance_pinned_seed` sets `_exhausted`
  (`world_mcp.py:2074-2077`), after which `call()` returns the refusal at `:2187-2189` **before**
  `_log_oracle` — post-exhaustion attempts cannot append a row.
- **Contained (wording):** *"If the environment states that the episode, task, or input is over …
  stop acting on it immediately"*. This is readable from a legal tool result: `observe`'s own status
  line says "Episode over — call reset_episode to start a fresh one." (`world_mcp.py:2099-2102`).
  That is environment-provided status already on the wire, not oracle leakage.
- **NOT contained:** an agent that applies the settle rule *per episode* rather than to the whole
  five-episode task, between episodes 0-3, can still poison an episode. This is a named,
  pre-registered risk of the v2 wording (D-4), not a discovery to be made afterwards.

This is the fourth independent reason Arm W is scoped out of v2 (§3).

### 5.6 Taint analysis

Checked against `safety-invariants` law 5 and the **run-brief-authoring** pre-launch checklist:

- **No oracle vocabulary.** No mention of `in_battle`, RAM, HP, party, `map`, `oracle.jsonl`,
  "rows", the scorer, or any predicate. The added words are "observing", "moves", "position",
  "place", "environment", "episode" — all already in the suffix's or the tool surface's own
  vocabulary.
- **No magic number, and no boundary.** The predicate's thresholds are 10 consecutive rows and 2
  distinct tiles; the constraint window ends at `exit_idx+9`. The brief says "a further stretch",
  "small local moves", "several consecutive observations" — never a count, never a window.
- **No tool named.** Naming `explore` would be Red-specific and would not parse in MiniWoB. The
  wording is behavioural, so each world's own tool surface implements it.
- **World-general by construction.** `COMMON_TASK_SUFFIX` is shared verbatim by both arms; there is
  no way to scope it to Red without forking the suffix per arm, which is a larger, unproposed
  change. The text would read identically in a browser task, a 3D-navigation task, or any other
  world in this project.
- **Does not change the success criterion.** "Stop when the stated task is complete" survives; the
  addition is a precondition on *when the agent may believe* that moment arrived — the same
  category as "verify before you claim done".
- **Does not touch any predicate.** `eval/score_gate0.py` and `tools/check_gate0_codex.py` are
  unedited. The fix acts entirely upstream, on agent behaviour.
- **Honest residual:** telling an agent to keep moving after it believes it is done is closer to the
  predicate's shape than telling it to keep observing. It is still behavioural and world-general,
  but a reviewer who thinks this crosses the line should say so — that is a legitimate reading, and
  this document is the place to settle it, not the verdict report.

---

## 6. Complete pin enumeration — everything that must be re-frozen

The 2026-07-25 draft named only the two `.appserver.json` fixtures. That list is incomplete, and an
incomplete list makes the run void by construction. **Verified by reading the fixtures this
session, and by recomputing the hashes**, the full set is:

### 6.1 Task-text pins (all four, not two)

Changing `COMMON_TASK_SUFFIX` changes `task_text_for()` for **both** arms, hence `task_sha256` for
both. `task_sha256` is reached through **two independent audit surfaces**:

| # | File | Field | v1 (frozen) | Reached by |
|---|---|---|---|---|
| 1 | `eval/fixtures/gate0_expected_pins_red.json` | `task_sha256` (`:29`) | `306751c34627f6d5c6a8c94ac2f714e358f0dcbc5867866c273e434de7f4b7c4` | `score_manifest` → `gate0_paid_source_pins.json:29` |
| 2 | `eval/fixtures/gate0_expected_pins_miniwob.json` | `task_sha256` (`:29`) | `845638c874df2f2de2adaebdd1d6c9318c689a46d0032fa76a9393e1e47512d1` | `score_manifest` → `gate0_paid_source_pins.json:37` |
| 3 | `eval/fixtures/gate0_expected_pins_red.appserver.json` | `task_sha256` | `306751c3…b7c4` (same value) | `gate0_appserver_arm.py::resolve_expected_pins()` at launch |
| 4 | `eval/fixtures/gate0_expected_pins_miniwob.appserver.json` | `task_sha256` | `845638c8…12d1` (same value) | same |

**The draft named only 3 and 4.** `eval/fixtures/gate0_paid_source_pins.json:29,37` points the
scorer at the **non**-`.appserver` files (1 and 2) — the same two files whose stale
`config_sha256` / `codex_mcp_list_sha256` / `tool_schema_sha256` produced v1's `CONSTANCY_BREACH`
(`reports/2026-07-24-gate0-paired-verdict.md` §4 names them explicitly). Missing 1 and 2 guarantees
a `pin_mismatch:task_sha256` on both arms and a repeat `CONSTANCY_BREACH`.

### 6.2 The `expected_pins_sha256` cascade (four more values, in two files)

Files 1 and 2 are **content-hash-pinned**, so editing them invalidates the pins that point at them
(`eval/score_gate0.py:204-215` refuses the arm on `expected_pins_hash_mismatch`):

| # | File | Field | Current value (recomputed and confirmed matching this session) |
|---|---|---|---|
| 5 | `eval/fixtures/gate0_paid_source_pins.json` | `expected_pins_sha256.red` (`:45`) | `ff00540b58704039d4da437ab677eb094f7a688d72f06a70148ee6fdfb850a82` |
| 6 | `eval/fixtures/gate0_paid_source_pins.json` | `expected_pins_sha256.miniwob` (`:46`) | `5d34c5ca56df78de3621001b6a8adb66eff51a72f5f51c9d14e1df8d65aa3870` |
| 7 | `eval/fixtures/gate0_readiness_dev_source_pins.json` | `expected_pins_sha256.red` | `ff00540b…50a82` (**identical** — same target file) |
| 8 | `eval/fixtures/gate0_readiness_dev_source_pins.json` | `expected_pins_sha256.miniwob` | `5d34c5ca…a3870` (**identical**) |

**7 and 8 are the trap.** `gate0_readiness_dev_source_pins.json` hash-pins the *same two files* as
the paid manifest. Editing 1 and 2 for a paid v2 silently breaks `readiness_dev` scoring unless 7
and 8 are recomputed in the same commit. Verified this session: the `.appserver.json` files
(hashing `35d33a25…` and `f4b4d7ab…`) are **not** pinned by either source-pins file at all — only
the non-appserver pair is.

### 6.3 Launcher identity

| # | File | Field | Why |
|---|---|---|---|
| 9 | `eval/fixtures/gate0_signature.appserver.json` | `expected_launcher_sha256`, `frozen_commit` | `COMMON_TASK_SUFFIX` lives inside `tools/gate0_appserver_arm.py`, so editing it changes the launcher's own hash. |

### 6.4 The non-task pins that made v1 void anyway

These have nothing to do with the task text and everything to do with whether a v2 run can be
scored at all. All four were live in v1's banked failure list.

| # | Item | Problem | Required action |
|---|---|---|---|
| 10 | `gate0_paid_source_pins.json` `artifact_paths` (6 strings) + `audit_paths` (12 strings) | All point into `runs/gate0_paid/…`, occupied by v1 and append-only. | Re-point every one to the §0-P3 fresh directory. `_verify_audit_paths` refuses any manifest path that is not literally the pinned string, so this is not optional. |
| 11 | `artifact_sha256.red_agent`, `.miniwob_agent`, `.wake_boundary` | Still `PENDING_NOT_YET_CAPTURED_…`. The fixture's own comment calls these "inert by construction" because the files do not exist — **that stops being true the moment the run produces them**, at which point the placeholder becomes an active mismatch. v1 banked `source_hash:red_agent`, `source_hash:miniwob_agent`, `source_hash:wake_boundary` for exactly this. | **Pre-registered mechanical post-run step (P5):** immediately after the run and *before* any scoring, compute the sha256 of each produced artifact, write it into the fixture, and record both the value and the timestamp in the verdict report. This is integrity binding, not interpretation — it is non-discretionary and its inputs are fixed by the run. Any deviation from "hash exactly what the run produced, change nothing else" is a protocol breach. |
| 12 | `artifact_sha256.miniwob_human` | `PENDING_NOT_YET_CAPTURED_paid_seed_human_replay_tool_not_built`. | Blocked on P1. Freeze from the produced artifact once it exists. |
| 13 | `artifact_paths.live_breaker` | Target file missing from the primary checkout (P2). | Regenerate, verify hash `27538b25…`. |
| 14 | `frozen_seed_sha256` | v1 banked `frozen_seed_hash` despite the pin matching in a clean LF checkout. | P6: recompute from the exact tree that will score. |

**No code change is required by any of the above.** `eval/score_gate0.py` and
`tools/check_gate0_codex.py` are not edited and must not be. Items 1-14 are fixture and artifact
lifecycle work, plus one pre-registered post-run hashing step.

---

## 7. The frozen scorer and bars (quoted, unchanged)

`eval/score_gate0.py`, read in full this session, unedited:

- **Capability, per arm** (`_arm_metrics`, `:128-150`): task predicate passes **and**
  `wall_clock_s <= 2 * human_wall_clock_s` **and** `primitive_actions <= 2 * human_primitive_actions`.
  For Red, the human denominator is `233.288 s` / `271` actions.
- **Cheap** (`score()`, `:337-345`): `limits = {"red": (5.0, 125), "miniwob": (2.0, 50)}` per arm;
  combined `sum(cost_usd) > 7.0 or sum(normalized_credits) > 175` → `FAIL_CHEAP`;
  `sum(normalized_credits) > 250` → `hard_breaker_exceeded`.
- **Verdict vocabulary** (`schema_version 1`): `readiness ∈ {GO, NO_GO, INSUFFICIENT_SOURCE}`;
  `overall ∈ {PASS, FAIL_CAPABILITY, FAIL_CHEAP, CONSTANCY_BREACH, NO_LEAK, INSUFFICIENT_DATA}`.
- **Check order** (`:347-360`, load-bearing for §0-P1 and §1):
  `leak → constancy → infra → source → capability → cheap`.
- **`task_sha256` is in `PIN_FIELDS` but not in `CONSTANCY_FIELDS`** (`tools/check_gate0_codex.py:
  21-31`) — so a task-text change cannot itself trigger a *between-arms* `CONSTANCY_BREACH`. It can
  and will trigger a *`handshake-receipt.json`-vs-frozen-pin* mismatch if §6 is not completed; those
  land in the same `failures["constancy"]` bucket. The two are different checks with an overloaded
  name.
- **Wakes do not gate anything** (`:263-281`, `:331-336`). `audit()`'s own `overall` is capped at
  `NO_GO_INSUFFICIENT_WAKES` and the scorer never reads it (§0.1). `"cheap_basis"` is
  `"cost_per_task"`; `"wake_accounting"` rides along as `"DEFERRED"`, informational only.

**No predicate, bar, or constant may be loosened.** The design doc's own law: *"the future
pre-registration may tighten [bars], never loosen them."* v2 loosens nothing. §8's H-d is a
**tighter** self-imposed prediction, which is permitted.

---

## 8. Budget, with numbers

Arm R only. v1's Arm R cost `$0.41589` / `10.397275` credits — 8.3% of both its caps.

- **Expected:** `~$0.50` / `~13` credits, allowing for the settle loop. The settle behaviour costs
  roughly one extra `explore` call plus a handful of `observe` calls; `primitive_actions` counts
  tool calls, not autopilot steps (5.2), so the action cost is single-digit.
- **H-d, as a number, not an order of magnitude:** **`cost_usd <= $1.00` and
  `normalized_credits <= 25` for Arm R.** Exceeding either is a recorded H-d falsification —
  reported as such in the verdict, meaning the settle instruction licensed an unbounded loop and
  the next iteration must bound it. (The 2026-07-25 draft said "the same order of magnitude as v1";
  10× of `$1.4455` is `$14.45`, above that document's own `$7.00` combined cap. That phrasing is
  deleted.)
- **Frozen caps, unchanged and authoritative:** `$5.00` / `125cr` Arm R; `$7.00` / `175cr` combined
  PASS bar; `250cr` hard breaker. H-d does not modify these — it is a prediction, and only the
  frozen caps decide `FAIL_CHEAP` (S-4).

---

## 9. Hypotheses (each independently observable in the scored output)

- **H-a:** Arm R's oracle contains, after the trainer-battle exit, ≥10 consecutive rows with
  `in_battle == 0` **and** ≥2 distinct `(x, y)` pairs among the post-exit rows — the two clauses
  (C5, C9) that must now hold *together*.
- **H-b:** `_red_success(rows)` returns exactly `(True, [])`. H-a can hold while C6/C7/C8 still
  fail; H-b is the only fact that banks.
- **H-c:** the settle instruction does not induce a map change inside the exit span — i.e. C7 does
  not appear in the failure list. If it does, the "without leaving the place you are in" guard is
  insufficient and the next iteration must strengthen it.
- **H-d:** Arm R stays within `$1.00` / `25` credits (§8).

---

## 10. One-attempt rule, void conditions, infra carve-out

- **One attempt.** No informal rerun of a completed v2 attempt. A v3 requires its own fresh,
  narrower pre-registration.
- **Void conditions.** Any `leak_failures` or `constancy_failures` voids the attempt as capability
  evidence entirely (D-5) — not a FAIL, not a PASS, no rescue, no reinterpretation once the cause is
  understood. Same law that keeps v1 void (§1).
- **Infra-death carve-out**, verbatim from `.claude/skills/paid-run-harness/SKILL.md` law 6:
  *"Relaunch only on infra death before ~10 decisions (MCP never connected, container crash, 429).
  Infra death AT or AFTER ~10 decisions = the attempt is spent: score whatever artifacts exist with
  the frozen scorer and bank that verdict (`INSUFFICIENT_DATA` is a legitimate outcome). No relaunch
  without David's explicit OK."*
- **Labelling.** v2's result is an Arm-R predicate result (§3), banked under that name. It is not a
  Gate 0 verdict and the verdict report must say so in its first line.

---

## 11. Escalation ladder for v3, written now

- **If v2 fails the SAME way** (`red_no_sustained_battle_exit` again) — a brief-level fix has failed
  twice on one failure mode. Per `.claude/PROTOCOL.md` §6 anti-thrash, v3 does **not** propose a
  third wording; it moves the discipline into the harness (forcing a fixed number of extra
  `observe`/`wait` round-trips after the model's `turn/completed`, in `run_gate0_arm_turn`). That is
  a scaffolding-side change to a safety-critical launcher — `expected_launcher_sha256` re-pin plus
  its own adversarial review — and needs its own write-up.
- **If v2 fails on `red_no_free_movement_after_exit` (D-2) or `red_map_changed_during_battle_exit_span`
  (D-3)** — the settle wording is mis-calibrated in a *known* direction (too static, or too roaming).
  One tightening iteration is permitted, stating in advance which direction and why.
- **If v2 fails a DIFFERENT way** — do not assume the brief is still the problem. Run
  **diagnose-a-run** against the raw artifacts first.
- **If v2 PASSES** — that is one arm. The next Gate 0 attempt needs a fresh MiniWoB held-out seed
  block (§4), the paid human baseline (P1), and a diagnosis of the 0.667 before it can claim
  Generality. There is no path from a v2 Arm R pass to a Gate 0 PASS that skips those.

---

## 12. Is this document freezable?

**The document is freezable. The run is not yet launchable.** Every metric, predicate, bar, and
disconfirmation condition above is fixed and mechanically checkable before any v2 number exists,
and none of them can be re-read favourably afterwards. The pass bar is one the scorer can actually
print — demonstrated at `$0` in §0.1, not assumed. What blocks launch is the P1-P7 precondition list —
fixture and artifact lifecycle work plus one review — not an open question of interpretation.

Freeze this document, complete P1-P7, then launch. Do not launch with any precondition open.

## Sources

- `eval/score_gate0.py` (frozen scorer; `_red_success` `:34-89`, `_miniwob_success` `:92-125`,
  `_arm_metrics` `:128-150`, `_verify_audit_paths` `:162-218`, `_verify_sources` `:221-299`,
  `score` `:302-373`, `score_manifest` `:376-389`)
- `tools/check_gate0_codex.py` (`TOOLS`, `PIN_FIELDS`, `CONSTANCY_FIELDS` `:15-31`;
  `primitive_action_events` `:251-258`; the permanently fail-closed wake ceiling `:267-298` and the
  unreachable `build_agent_metrics` `:311-329`)
- `tests/test_score_gate0.py::test_pass_matrix` (`:180-181`),
  `::test_wake_cap_alone_no_longer_blocks_pass` (`:220-224`) — committed proof that the scorer can
  emit `PASS` while wake accounting is `DEFERRED`
- `core/perception_plugin.py:189-242` (one oracle row per `observe`)
- `world_mcp.py:174-178` (Red watch spec), `:1861-1899` + `:1914-1928` (autopilot),
  `:2055-2065`, `:2162-2232` (MiniWoB oracle rows and the exhausted-refusal path)
- `tools/gate0_appserver_arm.py` (`COMMON_TASK_SUFFIX` `:187-190`, `ARM_TASK_SENTENCES`,
  `task_text_for`, `resolve_expected_pins`, `build_agent_metrics`)
- `eval/fixtures/gate0_paid_source_pins.json`, `gate0_readiness_dev_source_pins.json`,
  `gate0_expected_pins_{red,miniwob}.json`, `gate0_expected_pins_{red,miniwob}.appserver.json`,
  `gate0_signature.appserver.json`, `gate0_miniwob_paid_seeds.json`
- `tools/capture_gate0_baseline_miniwob.py` (`--mode paid_gate0 --i-am-human`)
- `reports/2026-07-24-gate0-paired-verdict.md` (**the banked v1 verdict: `CONSTANCY_BREACH`**),
  `reports/2026-07-24-gate0-armR-verdict.md`,
  `reports/2026-07-24-gate0-prereg-amendment-appserver.md`,
  `reports/2026-07-18-gate0-prereg.md` (`:117-119`, void law),
  `reports/2026-07-13-minimum-north-star-gate-0-design.md` (`:268-276` held-out ordering,
  `:372-373` bank-as-printed, `:380-397` escalation shelf)
- `reports/2026-07-28-gate0-constancy-breach-addendum.md` (PR #175 — authority on the v1 breach
  mechanism; cross-referenced in §1, not restated)
- `.claude/skills/{gate-methodology,run-brief-authoring,safety-invariants,paid-run-harness}/SKILL.md`,
  `.claude/PROTOCOL.md` §6
