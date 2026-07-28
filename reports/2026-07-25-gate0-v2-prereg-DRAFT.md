# Gate 0 v2 pre-registration — paired re-attempt under a corrected brief and a repaired interface

**Written 2026-07-25. Rewritten end-to-end 2026-07-28** after an adversarial review found the
2026-07-25 draft NOT freezable (the recommended brief fought the predicate it targeted; the pin
list was incomplete; a source gate fired before capability; the best case was still FAIL; §0
misstated the banked v1 verdict). Every defect that review named is addressed below, and the
passages that would have let a failure be re-labelled a success are deleted, not softened.

Two things were settled during the rewrite and are recorded so they are not re-litigated:

- **The harness *can* emit `PASS`.** A challenge that it cannot was raised and withdrawn; §0.1 holds
  the adjudication as a **non-blocking** note (true of `tools/check_gate0_codex.py::audit()`'s own
  verdict field, false of the scorer this document names as the pass bar), since it is a recurring
  misreading the v1 pre-reg already warned against.
- **Arm W stays in.** An earlier revision scoped it out, because a repeat of seed 1001's `0.667`
  banks FAIL whatever Arm R does. That is arithmetically right but rested on a false premise: the
  `0.667` is substantially a **defect in the world's own tool surface** — `press_key` documents a
  key NAME it cannot accept, and the click tool tells the agent an off-band control is "unreachable"
  without mentioning that the page scrolls (§3). Banking that as an agent failure would be
  dishonest, and dropping the arm would cost the Generality axis. v2 therefore repairs the interface
  first (**P8**) and runs **fresh seeds** (**P9**), keeping the paired structure — at the cost of a
  larger precondition list and an Arm W that is **not comparable to v1's** (§3.1).

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
| **P1a** | `runs/gate0_paid_human_baseline/miniwob/human_metrics.json` **captured** on the P9 seeds | **NOT DONE.** The directory holds only `human_metrics.INCOMPLETE_1785175245.json` and an abandoned capture's frames. The rig blocker is **resolved** (PR #174); this now waits only on David playing the episodes. | Any `score_manifest()` verdict, **both arms** |
| **P1b** | `artifact_sha256.miniwob_human` **frozen** to that file's real digest, in its own reviewed commit | **NOT DONE.** Still the literal `PENDING_NOT_YET_CAPTURED_…`, which `eval/score_gate0.py:255` compares against the real digest — capture alone does **not** clear the gate. | Any `score_manifest()` verdict, **both arms** |
| **P2** | `runs/gate0_live_breaker/live_breaker_dry_run_trip.json` exists and hashes to `27538b256bfdf276af91d4533b83247361ddbe470c5682b8addd58bda340e734` | **MISSING** — `runs/gate0_live_breaker/` does not exist in the primary checkout. v1 banked `source_unreadable:live_breaker` + `live_breaker_artifact` for exactly this. Regenerable byte-exactly from `tools/gate0_credit_breaker.py`. | Any `score_manifest()` verdict |
| **P3** | A fresh output directory — **`runs/gate0_paid_v2/<arm>/`** — with all 18 `artifact_paths` / `audit_paths` strings re-pointed to it | **NOT DONE.** All twelve pinned paths in `eval/fixtures/gate0_paid_source_pins.json` point into `runs/gate0_paid/…`, which v1 already occupies. `runs/` is append-only raw data; v2 must not write there. | The whole attempt |
| **P4** | The four `task_sha256` pins, the four `expected_pins_sha256` cascade values, **and `gate0_signature.appserver.json`'s `expected_launcher_sha256` + `frozen_commit`** re-frozen (§6, items **1-9**) | **NOT DONE** (this document does not edit fixtures). | Launch audit + scoring |
| **P5** | A mechanical post-run hash-freeze step for the run-produced artifacts (§6, item 11; item 12 is P1b) | **NOT PRE-REGISTERED ANYWHERE UNTIL NOW.** See §6. | Any `score_manifest()` verdict |
| **P6** | `sha256(eval/fixtures/gate0_miniwob_paid_seeds.json)` recomputed **from the tree that will score**, == `263aaed17ee653c8b32e608d88ed1b8d29d6a424d29ce2e123671b56df159e63` | Matches in a clean LF checkout (recomputed this session). v1 nonetheless banked `frozen_seed_hash`, so the scoring tree materialized CRLF. Check, do not assume. | Any `score_manifest()` verdict |
| **P7** | Adversarial review of **this** document, posted on the PR | Not done for this rewrite. | Launch decision |
| **P8** | **MiniWoB tool-surface interface repair, rebuilt into the world image and re-pinned** (§3, §0.2) | **NOT DONE.** `world_mcp.py:405-407` promises a key NAME the code cannot accept; `world_mcp.py:391-397` calls y>176 "unreachable" without mentioning that the page scrolls. | Arm W being a fair test at all |
| **P9** | **Fresh MiniWoB held-out seeds**, drawn and hash-committed before the run (§4.1) | **NOT DONE.** 1000-1004 are spent (§4). **Requires an additive edit to `eval/score_gate0.py::MODES` — see §0.2.** | Arm W as held-out evidence |

**Priority order:** P8 → P9 → P1a → P1b → P2 → P3/P4 → P5/P6 → P7. P8 comes first because P1a's human
baseline and P9's seed draw are both downstream of it: capturing a denominator against the broken
interface, or drawing seeds before the image is re-pinned, wastes the work.

### 0.2 The two preconditions that need code changes — flagged, not made here

This document edits nothing. Two preconditions cannot be satisfied by fixture work alone, and are
recorded as **required code changes needing their own plan, branch, and adversarial review**:

- **P8 — world-image interface repair.** Correct `_MINIWOB_KEY_TOOL`'s description (name → index,
  or make the field name-accepting by resolving against `allowed_keys` inside the world adapter) and
  amend `_MINIWOB_CLICK_TOOL`'s reachability text to state that the page scrolls and that keyboard
  focus can bring an off-band control into reach. This is **pin-cascading** (§6.5), so it lands in
  the already-planned batched PR alongside the EX02 oracle wiring and PR #138, followed by **one**
  world-image rebuild and re-pin. **Rebuild gotcha:** a naive `docker build .` from a Windows
  checkout bakes CRLF into the image and the resulting `image_code_sha256` self-refuses as stale —
  the rebuild must use an **LF-forced `git archive` context**.
- **P9 — fresh seeds require an additive scorer change.** `eval/score_gate0.py:13-16` hardcodes
  `MODES["paid_gate0"] = (…gate0_miniwob_paid_seeds.json, [1000, 1001, 1002, 1003, 1004])`, and
  `_verify_sources` (`:237-244`) fails `frozen_seed_contents` unless the seed file's contents equal
  that literal. **New seeds therefore cannot be adopted without editing the frozen scorer.** The
  minimal safe form is **additive**: a new `MODES` entry (e.g. `paid_gate0_v2`) with its own seed
  file and its own `SOURCE_PIN_FILES` entry, leaving `paid_gate0` byte-untouched so v1's banked
  artifacts stay scoreable exactly as printed. Adding a mode is not loosening a bar, but it **is** a
  change to the frozen scorer and needs its own review — it must not be smuggled in as part of a
  fixture regen.

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

**But be precise about what v1 demonstrated: the PREDICATES discriminated; the GATE did not.** v1's
two arms did produce real capability outcomes — Arm R `red_no_sustained_battle_exit`, Arm W
`miniwob_episode_1_terminal_not_success` (seed 1001, reward 0.667)
(`reports/2026-07-24-gate0-paired-verdict.md`). Those are genuine agent-behaviour facts, and they are
what §5's brief is designed against. **They are not gate verdicts.** `score()` never reached the
capability tier: 6 `pin_mismatch` entries short-circuited at `constancy`, and behind them sat **20
source failures** that would have short-circuited at `source` regardless
(`reports/2026-07-28-gate0-constancy-breach-addendum.md`; `HANDOFF.md:186-193`).

**The fact that makes P1 blocking, stated explicitly:** the addendum's Mode B reproduction shows
that with the pin chain cleaned, both arms' `audit()` failure lists go **empty** — and the run
*still* cannot reach a capability verdict, because the source tier is unsatisfied. A clean pin chain
plus a missing human baseline yields `INSUFFICIENT_DATA` / `INSUFFICIENT_SOURCE`, not a capability
result. Fixing pins is necessary and nowhere near sufficient; **P1 is what stands between this gate
and a scorable answer.**

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

**P1 is nothing but blocking. Nothing in this document de-blocks it, and nothing may.** v2 is a
paired attempt scored end-to-end by `score_manifest()` (§3), so the gate above fires on the whole
run.

**The rig contradiction that used to block the capture is RESOLVED and merged (PR #174, on `main`).**
The capture is now a matter of David playing five episodes:

- `press_key` takes an **index into `allowed_keys`**, and the human rig now resolves names to
  indices — the same defect that still stands on the agent-facing path (§3, P8).
- A 6-checkbox layout puts Submit at y=180, outside the 177px clickable band; **two `ArrowDown`
  presses scroll it to y=150**, where it clicks. The contradiction was a missing scroll step, not an
  unreachable control.
- An end-to-end dry run captured **5/5 episodes, `success: true`, in 178 s.**

The artifact is produced by `tools/capture_gate0_baseline_miniwob.py --mode paid_gate0
--i-am-human`, by a real human only (`:202-205` refuses the mode without the flag; `:291-292`
suppresses the task utterance to protect the held-out seeds). It must be captured on the **P9 seeds**,
**after** the agent's artifacts are banked, on the **repaired** interface (§4.1 step 4).

**P1 has TWO steps, and capturing the artifact alone does not satisfy the scorer.** The dry run
proved this. Even with the file present, `eval/score_gate0.py:255` compares
`artifact_sha256.miniwob_human` against the file's real digest — and that pin is still the literal
`PENDING_NOT_YET_CAPTURED_paid_seed_human_replay_tool_not_built`, which no real digest can equal. A
completed capture with an unchanged pin yields `source_hash:miniwob_human` instead of
`source_unreadable:miniwob_human` — the same `INSUFFICIENT_DATA` / `INSUFFICIENT_SOURCE` verdict,
one line further down. So:

- **P1a — capture.** Produce `runs/gate0_paid_human_baseline/miniwob/human_metrics.json`.
- **P1b — freeze the hash.** Set `artifact_sha256.miniwob_human` in the P9 mode's source-pins fixture
  to that file's real SHA-256, **in its own separate, reviewed commit**, and record the value in the
  verdict report. Mechanical and non-discretionary (hash exactly what was captured, change nothing
  else), but it is a distinct step and skipping it silently reproduces the failure it is meant to
  fix.

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

**Entry count — reconciling two correct readings.** Two audits reported different breach sizes
(two entries vs six). Both are right about different code paths, and a third dimension — time —
was missing from both. Measured this session by comparing each arm's banked
`handshake-receipt.json` (`reports/2026-07-24-gate0-{armR,paired}-verdict/`) field-by-field against
each fixture variant:

| Comparison | Producing function / fixture | Mismatched `PIN_FIELDS` |
|---|---|---|
| Launch-time audit, **today's** appserver fixtures | `audit()` vs `gate0_expected_pins_{arm}.appserver.json` @ `main` | **2 per arm** — `config_sha256`, `codex_mcp_list_sha256` |
| Launch-time audit, **run-time** appserver fixtures | `audit()` vs the same files as they stood on 2026-07-24 | **3 per arm** — the two above **+ `tool_schema_sha256`** |
| Scorer path (what actually banked) | `audit()` vs `gate0_expected_pins_{arm}.json` (**non**-appserver — the files `gate0_paid_source_pins.json:29,37` points at) | **3 per arm** |

`score()` aggregates both arms and arm-prefixes each entry (`:307-310`), so the **banked**
`failures["constancy"]` is `3 × 2 = 6`. The "two entries" reading is the per-arm `audit()` result
against **today's** appserver fixture, where `tool_schema_sha256` now matches because `main` re-pinned
it in `346b612` on 2026-07-25 — *after* the run. Both readings are correct; neither contradicts the
other; the banked verdict is six. See PR #175 for the mechanism.

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

**These conditions bite — but only once the source tier is satisfied.** `eval/score_gate0.py::
score()` emits `PASS`/`GO` on a clean input and `FAIL_CAPABILITY` on a failing predicate (§0.1,
demonstrated at `$0`), so the verdict *is* a function of agent behaviour. v1 never got that far: its
predicates discriminated, its gate did not (§0.1). Every condition below is reachable **only** with
P1a+P1b done; without them the run prints `INSUFFICIENT_DATA` no matter how the agent plays.

**v2 SUCCEEDS if and only if all six hold. Any single miss is a FAIL.**

| ID | Check | Mechanical test |
|---|---|---|
| **S-1** | Red predicate clean | `_red_success(_jsonl("runs/gate0_paid_v2/red/world/oracle.jsonl"))` returns exactly `(True, [])` |
| **S-2** | MiniWoB predicate clean | `_miniwob_success(_jsonl("runs/gate0_paid_v2/miniwob/world/oracle.jsonl"), <P9 seeds>)` returns exactly `(True, [])` — i.e. `reward == 1.0` on **all five** fresh seeds |
| **S-3** | Capability sub-bars, both arms | Red: `wall_clock_s <= 466.576` (= `2 × 233.288`) **and** `primitive_actions <= 542` (= `2 × 271`). MiniWoB: same `2×` rule against the P1 human baseline captured on the P9 seeds. |
| **S-4** | No leak, no constancy failure, both arms | `audit()` returns empty `leak_failures` **and** empty `constancy_failures` for each arm |
| **S-5** | Cheap, frozen caps | Red `<= $5.00`/`125cr`; MiniWoB `<= $2.00`/`50cr`; combined `<= $7.00`/`175cr`; `<= 250cr` hard breaker |
| **S-6** | Attempt integrity | Exactly one launch per arm; artifacts written to `runs/gate0_paid_v2/<arm>/` (P3); no `runs/` file overwritten |

The whole gate is one verdict: `score_manifest()` must print `overall: PASS` / `readiness: GO`.
Both arms must clear; there is no per-arm PASS.

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
- **D-4.** Any `_miniwob_success` failure — **specifically including**
  `miniwob_episode_N_terminal_count` or `miniwob_episode_N_terminal_not_last_row` caused by the
  settle instruction itself (§5.5). That is the brief actively damaging an arm, and is a FAIL of the
  intervention, not an incidental. A reward-`<1.0` terminal on the repaired interface (P8) is a
  genuine capability FAIL and banks as one — the interface repair removes the excuse, it does not
  create a new one.
- **D-5.** Any `leak_failures` or `constancy_failures` → the attempt is **VOID**: not a FAIL, not a
  PASS, no capability evidence in either direction, no rescue, regardless of how benign the cause
  later proves to be. Same law as §1.
- **D-6.** Both predicates clean but S-3 or S-5 missed → FAIL (`FAIL_CAPABILITY` or `FAIL_CHEAP`
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

## 3. Scope: v2 keeps **both arms** — because seed 1001's 0.667 is an interface defect

An earlier revision of this document scoped Arm W out, on the reasoning that `score()` emits **one
combined verdict** and `_miniwob_success` requires `reward == 1.0` on **all five** seeds
(`eval/score_gate0.py:112-120`), so a repeat of seed 1001's 0.667 banks FAIL whatever Arm R does.
That reasoning was sound but rested on a premise that has since been falsified: it treated the
0.667 as an unexplained capability miss that v2 had no mechanism to address.

**The 0.667 has an identified interface cause: a defect in the world's own tool surface that
actively misinformed the agent.** Verified by direct code reading this session:

1. **`press_key` promises a key NAME and cannot accept one.** `_MINIWOB_KEY_TOOL`
   (`world_mcp.py:405-407`) describes the argument as *"a single keyboard key (e.g. \"Enter\",
   \"Tab\", \"ArrowDown\")"* and types it `{"type": "string"}`. `world_mcp.py:2222` forwards it to
   `MiniWobWorld.press_key`, which at `core/miniwob_world.py:158-160` passes the string straight into
   miniwob++'s `create_action("PRESS_KEY", key=str(key))` — whose `key` field is an **index into
   `allowed_keys`**, not a name. `"Tab"` and `"Enter"` therefore raise
   `ValueError: invalid literal for int()`. *(Code path verified here; the live exception is
   evidenced in the breach/probe material, not re-run in this `$0` document.)*
2. **The click tool tells the agent the escape hatch does not exist.** `_MINIWOB_CLICK_TOOL`
   (`world_mcp.py:391-397`) states *"anything rendered below y=176 is unreachable"* — with **no
   mention that the page scrolls.** Submit's y is a deterministic function of checkbox count
   (2→104, 3→123, 4→142, 5→161, **6→180**); the clickable band is 177px against a 210px page, so on
   6-checkbox layouts Submit renders 3px outside reach and every click at y≥178 throws
   `MoveTargetOutOfBoundsException`. A real `Tab` keydown walks focus to Submit on the 7th press and
   scrolls it to y=141 — reachable. The agent could not do that, because of (1).

**Independent corroboration that this is real and known:** the in-flight branch
`fix/miniwob-key-name-press` (commits `91c1153`, `818c592`) fixes exactly this name→index
resolution — **in the human-baseline rig only** (`tools/capture_gate0_baseline_miniwob.py`), and
its own second commit is titled "Record the human-vs-agent interface asymmetry in the artifact".
The agent-facing path in `world_mcp.py` / `core/miniwob_world.py` is untouched. So the human
denominator is being repaired while the agent's interface stays broken — precisely the asymmetry
that would make banking the 0.667 as an agent failure dishonest.

**Decision: keep the paired Arm R + Arm W structure, and fix the interface first (P8).** Scoping
Arm W out would bank a documentation defect as a capability ceiling *and* cost the Generality axis,
reducing v2 to an Arm-R predicate result rather than a Gate 0 verdict. That is too high a price for
a bug we can fix. With P8 done, v2 is scored end-to-end by `score_manifest()` in the normal way and
**can** produce a real Gate 0 verdict.

### 3.1 What this costs, stated plainly

- **v2's Arm W tests a REPAIRED interface. It is not a like-for-like rerun of v1's Arm W and must
  never be compared to it as one.** v1's Arm W ran against a tool surface that denied it a working
  `press_key` and told it the page did not scroll. Any v1↔v2 Arm W delta is confounded by that
  repair and says nothing about the brain.
- **Three things change at once for Arm W:** the repaired interface (P8), the new task suffix (§5),
  and fresh seeds (P9). This is a capability gate, not an ablation — if Arm W passes, we will not
  know which change was load-bearing. Accepted deliberately; recorded here so no verdict report
  claims otherwise.
- **The fix is world-side, which is sanctioned.** Correcting a tool description that lies about its
  own argument type is world/perceiver work, not brain work — `core/contracts.py`, the brain, and
  the tool *contract shape* are untouched (**architecture-and-seam**). What changes is a description
  string and, if the argument is made name-accepting, a resolution step inside the world adapter.
- **The check against "fixing the world until the agent passes" is H-e plus §11, not an assurance.**
  P8 gets exactly one attempt to be the explanation: if Arm W fails any predicate clause after the
  repair, that banks as a genuine capability result and no further environment fix may be proposed
  for this arm (§11). The repair is bounded in advance; that boundary is the safeguard.

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
2. **The human denominator moves with the seeds.** P1a is captured on the **P9 seeds**, not on
   `1000..1004` — `_arm_metrics` compares the agent's wall-clock/actions against the human's on the
   *same* task instances, so a denominator drawn from spent seeds would not describe the run being
   scored. (A replay of `1000..1004` would still be a legitimate denominator for v1's banked
   artifacts, but v1 is void and is not being re-scored.)
3. The v1 Arm W artifacts remain the only held-out MiniWoB evidence this project has, and they are
   attached to a **void** attempt (§1). The honest statement of the MiniWoB position is therefore:
   *no valid held-out MiniWoB capability evidence exists, and the seeds that would have produced it
   are spent.*

**This argues for new seeds, not for dropping the arm** (§3). Spent seeds are a reason to draw
fresh ones; they are not a reason to abandon the Generality axis.

### 4.1 How the fresh seeds are drawn and committed (P9)

**What this procedure does and does not buy.** It prevents **post-hoc selection** — nobody can look
at how the agent did and then choose which seeds "count". It does **not** keep the seeds secret: the
formula below is published here, so anyone can compute the list. Secrecy is not the property being
bought, and the earlier claim that it was is withdrawn. The protection comes from the **formula being
fixed in a merged document before the run**, not from the hash.

1. **Draw — deterministic and fully published.**
   `candidate(i) = int.from_bytes(sha256(f"gate0-v2-armW:{i}".encode()).digest()[:4], "big") % 1_000_000`,
   walking `i = 0, 1, 2, …` and **accepting** a candidate only if it is not in `{0..4}` (dev), not in
   `{1000..1004}` (spent), and **not already accepted** (no duplicates — two identical seeds would
   collide in `_miniwob_success`'s per-episode `row.get("seed") == seed` filter and corrupt both
   episodes' row sets). A rejected candidate is skipped and the walk continues at `i+1`; **the
   replacement does not inherit the rejected candidate's position** — positions are assigned in
   acceptance order. Stop at five accepted seeds.
2. **6-checkbox requirement — binding, not optional.** The accepted set **must contain at least one
   seed that renders six checkboxes**, since that is the layout P8 repairs and the only layout on
   which H-e is testable. Determine each candidate's checkbox count by instantiating the task at that
   seed **without playing it** (`$0`, no model call, no reward observed), and if the first five
   accepted seeds contain none, continue the walk and **replace the last accepted seed** with the
   next accepted candidate that does. Record the walk in full — every `i`, every candidate, every
   accept/reject and why — in the verdict report, so the list is reproducible and the replacement is
   auditable. A rule applied by formula is not post-hoc selection; a rule invented afterwards would
   be.
3. **Commit the hash before the run.** Compute the SHA-256 of the seed file's LF-canonical bytes and
   **write that literal 64-hex value into this document and into the P9 source-pins fixture before
   launch.** Until that value is actually written here, this pre-registration commits to nothing on
   seeds — the placeholder below must be replaced, not left as prose.

   > `frozen_seed_sha256` (P9): `__________________________________________________________________`
   > — **UNSET. Filling this in is part of P9; the document is not frozen on seeds until it is.**

4. **Freeze at launch.** Write the seed file, check its hash against the committed value, and set
   `frozen_seed_sha256` in the new mode's source-pins fixture. A mismatch aborts the launch — no
   re-draw, no substitution.
5. **Human replay after (P1a).** The paid-seed human baseline is captured on these seeds **only
   after** the agent's artifacts are banked, per the design doc's ordering
   (`reports/2026-07-13-minimum-north-star-gate-0-design.md:273-276`), and using the **repaired**
   interface so that agent and human face the same world. Then its hash is frozen (P1b).
6. **One shot.** These seeds are spent the moment the agent plays them, exactly as 1000-1004 were.
   A v3 needs another block.

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
  settle behaviour is therefore nearly free against S-3.
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
> objective — until several consecutive observations show nothing further changing. **Confirming is
> looking, not doing: once the environment reports that an episode, task, or input is finished, take
> no further action on it — do not click, type, press a key, or otherwise act on a finished episode
> again. Looking at it is always safe; acting on it is not.** If the environment rejects further
> input, stop immediately. Stop when the stated task is complete and has been confirmed this way."

Three clauses carry all the weight, and each is there for a named predicate clause:

- *"alternate observing with small local moves around your current position"* — feeds
  `red_no_sustained_battle_exit` (observes → rows) **and** `red_no_free_movement_after_exit`
  (moves → distinct tiles) with the same behaviour. This is the clause the old candidates lacked.
- *"without leaving the place you are in"* — guards
  `red_map_changed_during_battle_exit_span` (C7), which the settle instruction newly puts at risk.
- *"Confirming is looking, not doing … do not click, type, press a key, or otherwise act on a
  finished episode again"* — guards **Arm W's terminal-row ordering** (5.5). This is a **hard
  prohibition naming the exact acts that corrupt an episode**, not a soft "stop acting" hint,
  because the failure it prevents is silent and unrecoverable: the agent gets no error, the episode
  simply fails at scoring time. It also states the safe alternative ("looking at it is always
  safe"), so the settle instruction and the prohibition cannot be read as contradicting each other.

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
| C6 | `red_missing_player_hp_oracle` | `:70-78` | **Newly exposed, low risk.** Requires `party_hp_hi`/`party_hp_lo` present as ints `0..255` on every non-corrupt row of `watches[battle_idx : exit_idx+10]`. Both are in the frozen watch spec (`world_mcp.py:176-178`, `0xD16C`/`0xD16D`), and a brief cannot change which RAM addresses are sampled — but the span only exists once `exit_idx` does, so **v1 never evaluated this clause** and it is unproven in practice, not proven safe. |
| C7 | `red_map_changed_during_battle_exit_span` | `:80-82` | **Satisfied by the "without leaving the place you are in" guard.** `map` must equal `battle_map` on every row from `battle_idx` through `exit_idx+9`. This is the clause the settle instruction *newly* puts at risk: an unconstrained "wander around" would walk the autopilot through the lab door within the first ten post-exit observes and fail here. The brief forbids leaving the current place and forbids starting anything new. Note the constraint binds only through `exit_idx+9`; the brief deliberately does **not** say so — stating the boundary would leak the predicate's shape. |
| C8 | `red_player_hp_reached_zero` | `:83-84` | **Newly exposed — a genuine new risk, NOT "unaffected".** `min(hp) > 0` over `watches[battle_idx : exit_idx+10]`. The settle behaviour starts no new encounter, so a real faint is unlikely — but the span is scanned from `battle_idx`, i.e. **through the whole battle**, and the corruption filter only drops rows where *every* watched field is 0. **Any mid-battle row with `party_hp_hi == party_hp_lo == 0` that is not the full all-zero signature fires this clause.** v1 returned at `:56` before `exit_idx` existed, so this clause was **never evaluated** — "v1 satisfied it" would be false. If C8 appears in v2's failure list, check the raw rows for a transient zero-HP sample before concluding the agent fainted. |
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
you're done" is therefore not inert for Arm W — it is potentially fatal to it. Exactly **one**
mechanical containment exists, and it only covers the end of the run:

- **Contained (end of run only):** after the fifth terminal, `_advance_pinned_seed` sets `_exhausted`
  (`world_mcp.py:2074-2077`), after which `call()` returns the refusal at `:2187-2189` **before**
  `_log_oracle` — post-exhaustion attempts cannot append a row.
- **NOT contained (episodes 0-3):** between episodes the environment does **not** refuse. The
  suffix's *"If the environment rejects further input, stop immediately"* clause therefore does
  nothing here — 5.5's own analysis is that the environment returns a normal
  `[click (x,y) -> ok]` and silently logs the damaging row. **Only the explicit prohibition in 5.3
  holds**, and it holds by instruction alone, with no mechanical backstop. An agent that applies the
  settle rule *per episode* rather than to the whole five-episode task can still poison episodes 0-3.
  This is a named, pre-registered risk of the v2 wording (D-4, H-f), not a discovery to be made
  afterwards.

**This is why the prohibition is in the brief text itself (5.3), not merely in this analysis.** An
agent cannot discover this rule from the environment: acting on a finished episode returns a normal
`[click (x,y) -> ok]` result, and the damage surfaces only at scoring time. The brief is the only
place the rule can live.

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
| 10 | `gate0_paid_source_pins.json` `artifact_paths` (6 strings) + `audit_paths` (12 strings) | All point into `runs/gate0_paid/…`, occupied by v1 and append-only. | Re-point every one to `runs/gate0_paid_v2/<arm>/` (P3). `_verify_audit_paths` refuses any manifest path that is not literally the pinned string, so this is not optional. |
| 11 | `artifact_sha256.red_agent`, `.miniwob_agent`, `.wake_boundary` | Still `PENDING_NOT_YET_CAPTURED_…`. The fixture's own comment calls these "inert by construction" because the files do not exist — **that stops being true the moment the run produces them**, at which point the placeholder becomes an active mismatch. v1 banked `source_hash:red_agent`, `source_hash:miniwob_agent`, `source_hash:wake_boundary` for exactly this. | **Pre-registered mechanical post-run step (P5):** immediately after the run and *before* any scoring, compute the sha256 of each produced artifact, write it into the fixture, and record both the value and the timestamp in the verdict report. This is integrity binding, not interpretation — it is non-discretionary and its inputs are fixed by the run. Any deviation from "hash exactly what the run produced, change nothing else" is a protocol breach. |
| 12 | `artifact_sha256.miniwob_human` | `PENDING_NOT_YET_CAPTURED_paid_seed_human_replay_tool_not_built`. `eval/score_gate0.py:255` compares it against the real digest, so **capturing the file is not enough** — an unfrozen pin turns `source_unreadable` into `source_hash`, same verdict. | **P1b:** freeze from the produced artifact, in its own separate reviewed commit. |
| 13 | `artifact_paths.live_breaker` | Target file missing from the primary checkout (P2). | Regenerate, verify hash `27538b25…`. |
| 14 | `frozen_seed_sha256` | v1 banked `frozen_seed_hash` despite the pin matching in a clean LF checkout. | P6: recompute from the exact tree that will score. |

### 6.5 The P8 world-image rebuild cascade (items 15-20)

The interface repair (§0.2) edits `world_mcp.py` and possibly `core/miniwob_world.py`. Both are
**baked into the world images and pinned**, so the cascade is larger than the task-text one and
**hits BOTH arms, not just MiniWoB**:

| # | Pin | Why it moves |
|---|---|---|
| 15 | `tool_schema_sha256` (miniwob, both fixture variants) | The `press_key` / `click` descriptions are part of the serialized tool list. |
| 16 | `world_image_id` + `world_image_tag` digest (**miniwob and red**) | Both images bake `world_mcp.py`. Editing it rebuilds both. |
| 17 | `image_code_sha256` (**both arms**) | Hashes `/app/world_mcp.py` and `/app/core/miniwob_world.py`. |
| 18 | `host_code_sha256` (**both arms**) | Same two paths, host side. |
| 19 | `expected_pins_sha256` × 4 (§6.2) | Recomputed **again**, after items 15-18 land — a second cascade pass. |
| 20 | `expected_launcher_sha256` / `frozen_commit` (`gate0_signature.appserver.json`) | New frozen commit. |

**Items 17 and 18 hit Red because of a known launcher quirk**, not because Red's world changed: the
code-hashing step hardcodes the same two world-module paths for **both** arms regardless of which
world runs (`tools/gate0_appserver_arm.py` ~`:374`, `:986-987`; flagged in
`reports/2026-07-24-gate0-paired-verdict.md` §3). Red's receipt therefore carries MiniWoB's
world-module hash. Do not treat a Red pin change here as evidence that Red's world moved.

**Sequencing that this implies, and it is not optional:** P8 must land, be rebuilt, and be re-pinned
**before** §6.1-6.4's task-text pins are frozen — otherwise the `expected_pins_sha256` cascade is
computed twice and the second pass silently invalidates the first. One batched PR, one rebuild, one
re-pin, then the task-text freeze. And the rebuild must use an **LF-forced `git archive` context**:
a naive `docker build .` from a Windows checkout bakes CRLF, and the resulting `image_code_sha256`
self-refuses as stale.

### 6.6 What needs a code change, and what does not

- **No code change** for items 1-20: they are fixture, image, and artifact lifecycle work plus the
  pre-registered post-run hashing step (item 11).
- **Code changes required, each needing its own plan/branch/review** (§0.2): **P8**'s
  `world_mcp.py` tool-description repair, and **P9**'s additive `eval/score_gate0.py::MODES` entry
  for the fresh seed block.
- **`eval/score_gate0.py`'s predicates, bars, caps, and verdict logic are not edited and must not
  be.** P9 adds a mode; it changes no threshold and no clause. `tools/check_gate0_codex.py` is not
  edited at all.

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

Both arms. v1 cost `$0.41589` / `10.397275` credits (Red) and `$1.02958` / `25.7395` credits
(MiniWoB) — 8.3% and 51.5% of their respective caps; combined `$1.4455` / `36.14`.

- **Expected:** `~$1.80` / `~45` credits combined — `~$0.50` Red (the settle loop costs roughly one
  extra `explore` call plus a handful of `observe` calls; `primitive_actions` counts tool calls, not
  autopilot steps, per 5.2) and `~$1.30` MiniWoB (a working `press_key` means more steps per
  episode than v1, which could not use one).
- **H-d, as numbers, not an order of magnitude:** **Red `<= $1.00` / `<= 25cr`; MiniWoB
  `<= $1.60` / `<= 40cr`; combined `<= $2.60` / `<= 65cr`.** Exceeding any of these is a recorded
  H-d falsification — reported as such, meaning either the settle instruction licensed an unbounded
  loop or the repaired interface costs materially more per episode than projected. (The 2026-07-25
  draft said "the same order of magnitude as v1"; 10× of `$1.4455` is `$14.45`, above that
  document's own `$7.00` cap. That phrasing is deleted.)
- **MiniWoB's headroom is the tight one.** v1 used 51.5% of the `$2.00`/`50cr` arm cap. The H-d
  ceiling of `$1.60`/`40cr` leaves real room before `FAIL_CHEAP`, but a run that needs many more
  steps per episode on the repaired interface could approach it — watch this arm, not Red.
- **Frozen caps, unchanged and authoritative:** `$5.00`/`125cr` Red; `$2.00`/`50cr` MiniWoB;
  `$7.00`/`175cr` combined PASS bar; `250cr` hard breaker. H-d does not modify these — it is a
  prediction, and only the frozen caps decide `FAIL_CHEAP` (S-5).

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
- **H-d:** costs stay within §8's numbers — Red `<= $1.00`/`25cr`, MiniWoB `<= $1.60`/`40cr`,
  combined `<= $2.60`/`65cr`.
- **H-e (Arm W, the P8 test):** with the repaired interface, the agent successfully reaches and
  clicks Submit on the **6-checkbox** layout — observable as `reward == 1.0` on the 6-checkbox seed
  that §4.1 step 2 **requires** the draw to contain, and, in the transcript, as at least one
  successful `press_key` call. **H-e is the falsifiable form of §3's claim that the 0.667 was an
  interface defect, and it is binding, not conditional** — the draw rule guarantees the test case
  exists, so H-e can never be vacuous.
- **H-f:** no episode fails on `miniwob_episode_N_terminal_count` or `_terminal_not_last_row` —
  i.e. the 5.3 prohibition held and the settle instruction did not corrupt an episode.

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
- **Labelling.** v2 is a paired, two-arm attempt scored end-to-end by `score_manifest()`, so it
  **can** bank a real Gate 0 verdict. The verdict report's first lines must nonetheless state that
  Arm W ran on a **repaired interface** and **fresh seeds**, and is therefore not comparable to
  v1's Arm W (§3.1).

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
- **If Arm W fails ANY predicate clause after P8** — not merely on the 6-checkbox seed — §3's
  interface diagnosis has had its one attempt and does not get a second appeal. Bank it as a genuine
  capability FAIL. **No further environment or tool-surface fix may be proposed for this arm**; the
  escalation is to the design doc's own shelf (*"MiniWoB cannot identify/check the named targets:
  the static-UI named layer is the critical path"*). Restricting the no-appeal rule to 6-checkbox
  failures would leave every other failure mode open to another round of world-fixing, which is the
  exact ratchet this rule exists to stop.
- **If Arm W fails on `terminal_count` / `terminal_not_last_row`** (H-f falsified) — the settle
  instruction damaged the arm. That is a brief defect, not a capability result: the wording must be
  narrowed before any further Arm W spend.
- **If one arm passes and the other fails** — per the design doc's escalation shelf, *"bank the
  partial evidence. Fix the failed seam, then wait for a new pre-registration; do not rerun the
  passing arm."* The combined verdict is still FAIL and is banked as printed; "one arm passed" is a
  diagnostic note, never a re-labelling of the verdict.
- **If both arms PASS** — per the design doc, *"add one held-out task/world at the next phase exit.
  Do not turn Gate 0 into the full ten-task graduation exam midstream."* Note honestly what the
  Generality claim rests on: two arms, one of which ran on an interface repaired between attempts.

---

## 12. Is this document freezable?

**The document is freezable. The run is not yet launchable.** Every metric, predicate, bar, and
disconfirmation condition above is fixed and mechanically checkable before any v2 number exists,
and none of them can be re-read favourably afterwards. The pass bar is one the scorer can actually
print — demonstrated at `$0` in §0.1, not assumed. What blocks launch is the P1-P9 precondition
list, not an open question of interpretation.

**The gap to launch is now larger than fixture work.** P8 and P9 each require a code change with
its own plan, branch, and adversarial review (§0.2), plus one world-image rebuild and a two-pass pin
re-freeze (§6.5). That is real engineering, not bookkeeping — but it is the honest price of Arm W
being a fair test rather than a banked interface defect.

Freeze this document, complete P1-P9 in the priority order given in §0, then launch. Do not launch
with any precondition open.

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
- `world_mcp.py:391-397` (`_MINIWOB_CLICK_TOOL`, the "unreachable" text), `:405-407`
  (`_MINIWOB_KEY_TOOL`, the key-NAME description), `core/miniwob_world.py:158-160`
  (`press_key` forwarding a string into miniwob++'s index-typed `PRESS_KEY` field) — the §3 defect
- branch `fix/miniwob-key-name-press` (`91c1153`, `818c592`) — the same name→index fix applied to
  the **human** rig only; corroborates the agent-side defect is still live
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
