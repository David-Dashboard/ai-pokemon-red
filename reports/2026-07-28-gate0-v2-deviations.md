# Gate 0 v2 — deviations from the frozen pre-registration (2026-07-28)

Deviation log for `reports/2026-07-25-gate0-v2-prereg.md`, which is **frozen on merge**. Its
closing law, verbatim (`:1019`):

> After merge, this is a frozen pre-registration: cite it, satisfy it, or report a deviation from
> it — but do not revise it to fit a result.

**This file exists because that law needs a place to land and no such place existed.** No deviation
log, launch report, or amendment file for the v2 prereg is present in `reports/` as of this date
(the v1-era `reports/2026-07-24-gate0-prereg-amendment-appserver.md` amends the *2026-07-18* prereg,
a different frozen document, and PR #180 satisfied precondition P8 without recording a deviation
anywhere). Rather than edit the frozen document — which the law forbids — new entries go here.
Append one section per deviation, newest last. **Nothing in this file relaxes any bar, and nothing
here may be cited to reinterpret a banked result.**

---

## D1 — the scorer was edited after the freeze (missing/undecodable oracle → verdict, not crash)

**Landed by:** PR #187, `fix/scorer-missing-oracle-verdict`.
**Touches:** `eval/score_gate0.py::score_manifest()` only.

### What the prereg says

- §0.2 sets the standard for any post-freeze scorer change: *"Adding a mode is not loosening a bar,
  but it IS a change to the frozen scorer and needs its own review — it must not be smuggled in as
  part of a fixture regen."*
- §2 stakes the document on a hostile reader re-checking every predicate **"with the unedited
  `eval/score_gate0.py`"**.

That §2 phrase is **now false**, and that is the deviation being reported. §0.2's standard is met —
this change had its own plan, its own branch, its own PR and its own adversarial review, and rode in
with no fixture regen — but meeting the standard does not excuse leaving the record silent.

### What changed

`score_manifest()` read each arm's pinned `oracle.jsonl` unguarded, so a run that died before
writing its oracle raised `FileNotFoundError` straight out of the public entry point — a stack
trace where a verdict belongs. The read is now guarded and fails closed through the **existing**
source-failure machinery, uniformly across all three modes:

| condition | exception caught | failure string emitted |
|---|---|---|
| oracle path cannot be opened/read at all | `OSError` | `source_unreadable:oracle:<arm>` |
| oracle is present but its **bytes** do not decode as JSONL | `JSONDecodeError`, `UnicodeDecodeError` | `source_malformed:oracle:<arm>` |

Both land in `failures["source"]`, which the untouched precedence chain resolves to
`INSUFFICIENT_DATA` / `INSUFFICIENT_SOURCE` — the same treatment `_verify_sources` already gives its
six pinned artifacts via `source_unreadable:{key}`.

**Explicitly still crashes, by design:** an oracle whose lines decode as valid JSON but are the
wrong *shape* (e.g. `5\n7\n`) raises `AttributeError: 'int' object has no attribute 'get'` inside
`_red_success`. Verified, not assumed. Shape is a claim about content, and content is what the
predicates exist to judge; converting it to "no oracle" would let a structurally-wrong trace
masquerade as an absent one.

### Why this is additive and fail-closed

- It **cannot turn a failure into a pass.** The only reachable new outcomes are two additional
  `failures["source"]` entries. A non-empty `failures["source"]` can never produce `PASS`/`GO`.
- It **cannot turn a pass into a failure.** Neither catch fires unless the oracle read already
  raised — which previously terminated the process with no verdict at all.
- It is **not mode-specific**: no branch on `mode`, no special case for `paid_gate0_v2`.

### Proof that no bar moved

Against the frozen scorer commit `208d211` (*"feat(eval): additive paid_gate0_v2 scoring mode on
fresh MiniWoB seeds"*), LF-canonical bytes (per this repo's CRLF-pinning doctrine):

| region | frozen `208d211` | PR #187 head | |
|---|---|---|---|
| lines 1–386 (everything above `score_manifest`) | `f408dfac5aaf718e5f71be73b8b8f4d36395d01cd9a67b8746b2984e6c5d2d49` | identical | ✅ |
| `score()`, lines 312–383 | `fe0059c6cc75d466b1c8aab44f79f9f51dcd4291a8000267e4fb1c1ad0c36245` | identical | ✅ |

Reproduce:

```sh
git show 208d211:eval/score_gate0.py | head -386 | tr -d '\r' | sha256sum
head -386 eval/score_gate0.py       | tr -d '\r' | sha256sum
```

Because lines 1–386 are byte-identical, **every** predicate, threshold, cap and constant the prereg
depends on is provably unmoved: `MODES`, `SOURCE_PIN_FILES`, `MINIWOB_TASK`, `AUDIT_PATH_KEYS`,
`_red_success`, `_miniwob_success`, `_arm_metrics`, `_verify_audit_paths`, `_verify_sources`, the
`{"red": (5.0, 125), "miniwob": (2.0, 50)}` arm caps, the `7.0`/`175`/`250` combined and breaker
caps, and the leak → constancy → infra → source → capability precedence chain. The entire diff is
below line 386.

Behavioural non-regression, same on-disk state scored before and after (sha256 of the
sorted-JSON verdict):

| mode | oracle state | before | after |
|---|---|---|---|
| `paid_gate0` (banked v1 artifacts) | present | `965807f0a2bdf064af8a4522a47a39180fd282343c6d6501674ea3e20938fdd1` | identical |
| `readiness_dev` | present | `a1363a3633e4e7b42d9b7d6990be6cc3918700913c8aad66f70f97020ddfde4b` | identical |
| `readiness_dev` | absent (real state) | `FileNotFoundError`, no verdict | verdict with `source_unreadable:oracle:{red,miniwob}` |

The banked v1 `paid_gate0` result is byte-identical. **This does not un-void it** — the
`CONSTANCY_BREACH` stands per `reports/2026-07-28-gate0-constancy-breach-addendum.md` §1.

### Known cosmetic artefact (pre-existing, not introduced)

When the oracle read fails, `oracles[name]` stays unset, so `score()` runs the predicates against
`[]` and emits capability failures (`red:red_not_fresh_party_zero`, `miniwob:miniwob_episode_N_
terminal_count`, …) that are artefacts of the missing source rather than real findings. The verdict
is unaffected — source precedes capability — but an operator reading the raw failure list during
triage could be misled. This is the identical shape the pre-existing unpinned-arm `continue` path
in `score_manifest()` already produced, so it is inherited, not created here. Left alone
deliberately: fixing it would mean touching `score()`, which this deviation exists to prove was not
touched.
---

## D6 — the PRE-REGISTERED INTERVENTION ITSELF was revised before the run (§5.3's task brief, four amendments)

**Landed by:** PR #193, `feat/gate0-v2-task-brief`.
**Touches:** `COMMON_TASK_SUFFIX` in `tools/gate0_appserver_arm.py` and its tests
(`V2_LOAD_BEARING_CLAUSES` and the two `task_sha256` literals). No fixture, no scorer, no checker,
no `runs/` artifact, and — above all — **not** `reports/2026-07-25-gate0-v2-prereg.md`, which stays
byte-identical to `main`.
**Authorised by:** David, explicitly, on 2026-07-28, having read PR #193's adversarial review
(`https://github.com/David-Dashboard/ai-pokemon-red/pull/193#issuecomment-5107207373`). That
authorisation is the only reason this is an amendment rather than a refusal.

**Why D6 and not D2-D5:** D1 is on `main`; #188 claims **D2**, #191 **D3**, #192 **D4**, #195
**D5** — verified by reading this file on each branch head (`origin/fix/audit-verdict-not-gate-verdict`,
`origin/fix/red-glitch-row-signature`, `origin/fix/gate0-launcher-mode`,
`origin/fix/gate0-red-capture-mode`) on 2026-07-28. D6 is the first free slot. Append newest-last, so
this section belongs after D5; this branch carries only D1, so landing it after the others will need
the same trivial append-order conflict resolution D5 already flagged.

**Citation convention (D3's, kept):** every code citation below names the **symbol**. Line numbers
are given only where the symbol alone is ambiguous, and each was re-read at the commit named beside
it. `tools/gate0_appserver_arm.py` is under concurrent edit by #188 and #192, so it is cited by
symbol with no line number at all.

### This is the heaviest entry in this log, and it is not being dressed down

Every earlier entry reports a change to *apparatus*: a scorer's error path (D1), a checker's field
name (D2), a corruption predicate (D3), a launcher's v1 hardcodes (D4), a capture rig's mode (D5).

**This one revises the intervention.** §5 says of the brief: *"Per **run-brief-authoring**, the brief
IS the intervention; reviewers must critique these exact words."* Those exact words have been
changed. The prereg's closing law is *"cite it, satisfy it, or report a deviation from it — but do
not revise it to fit a result."* PR #193 originally applied §5.3 **verbatim** and argued — correctly
at the time — that verbatim application was *satisfaction*, not deviation, so no entry was owed.
That argument does not survive this commit. **§5.3 is no longer what the paid brain will read**, and
`eval/fixtures/`-bound reviewers, the runbook (#194), and anyone reconstructing this attempt later
must be able to find that fact without diffing a launcher against a frozen report.

### The timing argument, which is the whole of the defence

**This is done before any Gate 0 v2 run exists.** Not a launched one, not an aborted one, not a
partial transcript, not a single artifact under any `paid_gate0_v2` path. P1a, P1b, P1c and P2 are
all still open; §6.1 items 1-4 have not landed, so `refuse_if_expected_pins_stale` (added at
`ec881e4` on this same branch) would refuse a launch attempted today. **There is no v2 result of any
kind to fit a rule to.** That is the same timing argument that legitimised D1 and D3 — D3 states it
in those words — and it is the only thing separating this from the exact act the closing law
forbids.

It is also, deliberately, the last moment at which it is available. Once a v2 run exists this
amendment becomes unmakeable, and the escalation ladder in §11 takes over instead.

### What forced it: §5.4's own proof is internally inconsistent

Not a reviewer's preference — a contradiction inside the frozen document's own argument.

- §5.4's **C5** defence (`red_no_sustained_battle_exit`) reassures with: *"a single `explore` call
  alone produces ~41"* rows.
- §5.4's **C7** defence (`red_map_changed_during_battle_exit_span`) reassures with: *"an
  unconstrained 'wander around' would walk the autopilot through the lab door … and fail here."*

**C5's margin sits on `explore`, which C7's guard makes unusable.** `World._run_autopilot` serves
both `explore` and `goto`, but only `explore` (`target=None`) is frontier-seeking — its job is to
leave the room. `_run_autopilot(target=…)`, i.e. `goto`, navigates to an explicit cell and returns
*"arrived at the target cell"*, so **a `goto` to a tile inside the current room is fully
C7-compliant** and feeds C5 and C9 together. §5.4 never costed `goto` either. The honest statement
is not "the C5 defence routes through a tool the C7 defence rules out" — it is that §5.4 quantified
its C5 reassurance on the one autopilot mode C7 forbids, and left the compliant paths, primitive
and `goto` alike, unquantified.

§5.4's *"~41"* is also wrong for the tool it names. `_run_autopilot`'s loop is
`for _ in range(max(1, min(int(max_steps), 200)))` and observes at the **top** of every iteration,
so a call yields (iterations + 1) rows. The default `max_steps=40` gives 41 — but `max_steps` is
agent-supplied and the hard cap is 200. **v1's own first `explore` hit that cap: 200 autopilot
steps, 201 rows, from one tool call.** §5.4 quoted the default as if it were the yield.

That correction cuts both ways, and the second direction is the one that matters. §5.4's *"~41"*
made the C5 margin look like an order of magnitude. It is not — see the measured table below.

Worse, the stop condition — *"until several consecutive observations show nothing further
changing"* — **can only be satisfied by ceasing to move**, because moving changes what is observed.
A literal-minded agent must therefore move a little, stop moving, and then observe until stable: the
terminating tail is observation-only and its length is "several".

**That is v1's exact failure mode, reproduced inside the intervention written to fix it.** v1
produced 4 rows.

### The four amendments

Each is scoped to the smallest edit that removes the defect, and each was checked against the taint
rule before the wording was fixed.

#### W1 + W2 — the settle stretch is bounded by EFFORT, not by the world going quiet

The stability stop condition is gone. In its place: an explicit **round** unit, a floor stated as a
negative bound, a refusal to stop at first quiet, and a doubling rule.

> Observe again after every move; one move and the observation that follows it are one round. Do
> this many times over: a handful of rounds is not enough, and stopping the first time nothing new
> appears is not enough either. When you first judge that you have done enough of these rounds,
> treat that judgement as the halfway point rather than the end — carry on the same way for as many
> rounds again, and only then stop settling.

*"alternate observing with small local moves around your current position"* and *"without leaving
the place you are in"* are **kept verbatim**; the second is C7's entire defence and was never in
scope to touch.

**No phrase in the brief points at ten**, and no digit is named. **But the floor this buys is 8
rows, not the 24 first claimed here** — see the measured table below, which supersedes the
arithmetic this amendment was written on. W1/W2 raise the floor from §5.3's 6 and remove the
ceasing-to-move tail, both real improvements, and **still leave the worst compliant reading under
the bar.** They are recorded as landed because they are strictly better than §5.3 and because W3/W4
(which are load-bearing for Arm W) travel with them — **not** because they close C5.

#### W3 — `task,` deleted from the prohibition's trigger list

§5.3 read *"once the environment reports that an episode, **task**, or input is finished, take no
further action on it — do not click, type, **press a key**…"*. In Arm R the task-complete and
episode-complete conditions fire **at the same instant** (winning the rival battle is the stated
task), and `press_button` is the only way to make a small local move there.

**Stated at the right strength (correction).** An earlier version of this entry said §5.3 *"forbade
Arm R's only means of movement at exactly the moment the settle instruction demanded it"*. That is
stronger than §5.3's own text supports: its trigger was conditioned on *"once **the environment
reports** that an episode, task, or input is finished"*, and Red's environment reports nothing of
the sort — `PerceptionPlugin`'s render carries no finished/complete/episode-over state line. On a
**strict** reading the clause never fired in Red at all. What §5.3 actually risked was a **loose**
reading — the agent's own "I have finished the task" collapsing into "do not … press a key" — which
is a real hazard and worth removing, but it is a hazard of misreading, not a contradiction on the
face of the text. The fix is right; the reason previously given was stronger than the evidence.

On the loose reading the brief told the agent to move and not to move simultaneously, and §5.3's
stated reason they cannot conflict —
*"It also states the safe alternative … so [they] cannot be read as contradicting each other"* — is
a non-sequitur: stating a safe alternative **resolves** a contradiction rather than dissolving it,
and it resolves it toward **not moving**, which is precisely what §5.1 rejected all three
2026-07-25 candidates for.

The trigger is now *"once the environment reports that an episode or an input is finished"*.
Scoping verified in both directions:

- **Arm W protection intact.** `MiniWobSession._observe_content`'s status line is literally
  `"Episode over — call reset_episode to start a fresh one."`, so the episode trigger still fires
  exactly where §5.5 needs it — before `reset_episode`, when a further action would append a second
  row to the same `(episode, seed)` and hard-fail it.
- **Arm R released.** Red reports no finished "episode" and no finished "input", so the prohibition
  no longer fires there at all.

#### W4 — a `reset_episode` carve-out

§5.3 exempted nothing from *"take no further action on it"*, and §5.5 never mentions `reset_episode`
— yet Arm W's five episodes cannot advance without it, and `observe` is at that moment instructing
the agent to call it. An agent obeying the brief would have been obeying it **against the
environment's explicit instruction**, at a cost of four hard-failed episodes.

Added: *"Starting the next episode is not acting on the finished one."*

Mechanically safe, read at `ec881e4`: in `MiniWobSession.call`, `reset_episode` is handled **above**
the `_exhausted` guard, and its `_log_oracle(done=False)` fires **after** `_advance_pinned_seed` has
already bumped `_episode_idx`, so the row lands on the **new** episode. Scoped to a **finished**
episode on purpose: `_advance_pinned_seed` logs `done=True, abandoned=True` against the current
episode when `not self._episode_over`, so a carve-out that licensed an *early* reset would hard-fail
the episode it was meant to protect. After the fifth terminal `_exhausted` refuses, and the brief's
unchanged *"If the environment rejects further input, stop immediately"* covers that.

#### W5 — the write-side leak

§5.6 claims *"No tool named."* **That is false of §5.3.** `click` is verbatim an entry of
`check_gate0_codex.TOOLS["miniwob"]`, and "type"/"press a key" are one paraphrase step from
`type_text`/`press_key`. Worse than the naming: `click` / `type_text` / `press_key` is **exactly the
row-writing subset** of that tool surface (`MiniWobSession.call`'s shared
`self._log_oracle(done=ep_over)` tail), while the blessed *"looking"* acts — `observe`,
`read_region`, `whats_changed` — write **none**. The brief prohibited precisely the writing set and
blessed precisely the non-writing set, at precisely the moment a row is fatal. No digit and no
threshold leaked; **the predicate's write-side shape did.**

Two changes, neither of which weakens the prohibition §5.5 calls the only containment for a silent,
unrecoverable failure:

1. The enumeration is replaced by the tool-agnostic *"take no further action on it — send it no
   further input of any kind"*. **Strictly wider** than three named verbs, so it cannot be weaker;
   it simply stops mirroring the tool surface. *"Looking at it is always safe; acting on it is not"*
   survives verbatim.
2. W4's carve-out **blesses `reset_episode`, which DOES write a row**, so the blessed set is
   genuinely no longer the non-writing set.

**Correction — "broken in both directions" was half true.** Only the blessed side actually breaks.
Extensionally the *prohibited* set is **unchanged**: everything except
`observe`/`read_region`/`whats_changed`/`reset_episode` is still exactly
`click`/`type_text`/`press_key`, still exactly the row-writing acts other than `reset_episode`. What
changed on that side is that the brief no longer *says so*. The correct statement is **broken on the
blessed side and no longer disclosed on the other** — which is still worth having, because
disclosure was the leak, but it is one direction, not two.

`observe` remains the one tool name the brief effectively names, and that is deliberate and
pre-registered: §5.6's own permitted-vocabulary list contains *"observing"*, and it is the act that
writes nothing in Arm W.

### The measured row-yield table — Arm R's whole tool surface

This table is the thing whose absence caused two failed attempts at this amendment. Every earlier
version of this section computed against a *model* of the harness. This one is derived by symbol and
then reconciled, exactly, against the only paid run that exists.

**One row is written at exactly one site:** `PerceptionPlugin._log_oracle`, whose only call site in
that file is inside `PerceptionPlugin.observe`. So **rows = invocations of `plugin.observe()`**, and
nothing else. The patience auto-advance loop inside `observe` re-perceives many times but calls
`_log_oracle` once, so it never changes the count.

Per tool call, over `check_gate0_codex.TOOLS["red"]`:

| tool | moves performed | **oracle rows** | why |
|---|---|---|---|
| `observe` | 0 | **1** | `World.call`'s `observe` branch: `body = self._content(self.plugin.observe(_AGENT))` |
| `press_button` | 1 | **1** | direct-action branch: `gw.execute(...)` (which never observes) then one trailing `plugin.observe` |
| `press_sequence`, 1 button | 1 | **1** | same branch |
| **`press_sequence`, 16 buttons** | **16** | **1** | `PerceptionPlugin._do_buttons` loops `emu.press` over every button and returns via `_post_action` — **it never observes**. `ToolSpec` caps `buttons` at `maxItems: 16` |
| `wait` | 0 (ticks only) | **1** | same branch |
| `remember` | 0 | **1** | `remember` branch also ends in a trailing `plugin.observe` |
| `goto` | k autopilot steps | **k + 1**, min **2**, max **201** | `_run_autopilot` observes at the top of each loop iteration, plus the branch's trailing observe |
| `explore` | k autopilot steps | **k + 1**, min **2**, max **201** | same; `for _ in range(max(1, min(int(max_steps), 200)))` |

**The ratio between what an agent counts and what the scorer counts spans 16 : 1 to 1 : 201.**

**Reconciliation against `runs/gate0_paid/red/` — exact, not approximate.** From
`transcript.jsonl`'s 142 `mcp_tool_call` items and the autopilot step counts each `explore`/`goto`
result reports back:

| tool | calls | reported steps | predicted rows |
|---|---|---|---|
| `press_button` | 131 | — | 131 |
| `press_sequence` | 4 | 8, 12, 6, 8 buttons | 4 |
| `wait` | 2 | — | 2 |
| `observe` | 1 | — | 1 |
| `explore` | 3 | 200 (hit the cap), 88, 5 | 201 + 90 + 7 = 298 |
| `goto` | 1 | 0 (*"blocked / no path to the target"*) | 2 |
| | **142** | | **438** |

`runs/gate0_paid/red/world/oracle.jsonl` contains **438** rows. The model above is confirmed to the
row. Note `press_sequence` moved **34** buttons across four calls and wrote **4** rows.

### What that does to this amendment's floor — the correction

The previous version of this section asserted *"One round = one small local move + one observation =
**2 rows**"* and concluded **24 rows, 2.4× slack**. **That is wrong, and it is wrong by 2×.**

The two symbols establish that a move writes a row and an observe writes a row. They do **not**
establish that the agent performs two acts. `World.call`'s direct-action branch returns
`[head, *self._content(self.plugin.observe(_AGENT))]` and its `observe` branch returns
`self._content(self.plugin.observe(_AGENT))` — **byte-identical apart from the header**. Every
action in this world hands back a complete fresh observation. *"Observe again after every move"* is
therefore satisfied **by the move itself**; a second `observe` call returns the same content and
writes the only extra row.

**The v1 agent worked this out.** It called `observe` **once in 142 tool calls** — the opening
*"Begin by observing"* — and never again. Corrected table:

| reading | rounds | rows | vs the ten-row window |
|---|---|---|---|
| a separate `observe` after each move (what this section previously assumed) | 12 | 24 | +14 |
| **observation taken from the action result**, handful = 5 | 12 | **12** | **+2** |
| handful = 4 | 10 | **10** | **tie, zero slack** |
| **handful = 3** (ordinary English) | 8 | **8** | **FAIL** |

**The claimed 2.4× does not exist. The true design margin is 2 rows, and two compliant readings land
at or under the bar.** *"A handful"* is 3-5 in ordinary English; the brief says only that a handful
is *not enough*, so settling at four rounds is obedient, and the doubling gives eight.

**Retraction — the "degenerate floor" framing was wrong.** This section previously wrote *"if the
agent **disobeys** 'Observe again after every move'"* and called the resulting 12 rows a degenerate
case. Taking the observation from the action result is **not disobedience and not degenerate**; on
the only evidence that exists about how this model behaves on this harness, it is **the expected
case**, at 141 of 142 calls. The floor is the expected reading, not the pathological one.

**A second, weaker mismatch, recorded because it is the same defect in a different direction.** The
brief denominates its unit in *moves*; the scorer counts *rows*, which come from row-writing tool
calls. `press_sequence` carries up to sixteen moves in one call and writes one row. An agent that
counts buttons as moves can report twelve rounds while writing three. This needs one inconsistency
(a batched sequence does not observe after *every* move), where the reading above needs none — so it
is not strictly compliant, and it is not what makes the floor fail. It is recorded because the brief
defines its unit in a currency the harness converts at up to 16 : 1.

**Costs, unchanged and not the constraint:** `primitive_action_events` counts tool calls, not
autopilot steps, so v1's 142 actions against the 542 cap and 127.75 s against 466.576 s absorb any
of these floors with room to spare. S-3 was never at risk and is not the reason this is hard.

### The recommendation: stop amending the brief and escalate. C5 is not fixable in a wording.

Two moves are available: **(A)** a third revision of the text, with the floor denominated in a unit
that maps 1 : 1 onto rows; **(B)** §11's harness-side v3. Both were assessed. **(B) is recommended,
and no third text is proposed in this PR.**

#### Why not (A) — with the strongest (A) I can construct, and its arithmetic

The unit that maps 1 : 1 onto rows without depending on a redundant `observe` is **a single move**:
every direct action writes exactly one row by itself. So the honest (A) is denominated in moves, and
tool-agnostically forbids batching (which the 16 : 1 `press_sequence` ratio otherwise permits):

> "Make each small move on its own rather than several at once. A handful of moves is not enough,
> and stopping the first time nothing new appears is not enough either. When you first judge that
> you have made enough of them, treat that judgement as the halfway point rather than the end —
> carry on the same way for as many moves again, and only then stop settling."

**Worst compliant reading: handful = 3 → smallest obedient count 4 → doubled → 8 rows.** The same
miss, one revision later. The doubling has to become a tripling or a second doubling to clear ten,
and *"carry on for as many again, and then once more for as many again after that"* collapses into a
single emphatic doubling under an ordinary reading — back to 8. Every variant I could build fails
one of three ways:

| variant | worst-case rows | why rejected |
|---|---|---|
| move-denominated floor + one doubling (above) | **8** | under the bar — v1's failure mode, third time |
| + a second doubling | 16 if read as two steps, **8** if collapsed | the margin rests on the reader not collapsing it |
| raise the base: *"a handful is not enough, nor is twice that"* | 14 | *"twice a handful"* evaluates to **exactly the bar** at handful = 5 — the same on-the-bar coincidence *"several"* had |
| a bigger quantifier word (*"dozens"*) | ≥ 24 | hands the agent a number in words; *"a dozen"* sits 2 above the bar |
| keep the round unit, force *"a separate look"* | 16 | the margin rests on the agent performing an act the world makes redundant — **the exact behaviour already observed to fail**, 141 times in 142 |

Every (A) either lands its worst case at 8-14, or introduces a number-phrase that evaluates on or
near the bar, or rests its margin on a redundant act this model has already been seen to skip.
**A margin of 2-4 rows on a one-shot, unrepeatable run against a spent seed block — computed by the
third consecutive person to compute a margin here — is not a design margin.** The first two
computations were 14 and 2.4×; both were wrong, in the same direction, for the same reason.

**And the count matters.** (A) would be draft **three**, each written after a reviewer computed a
miss, none of them after a run. The risk section below already concedes *"there is no principled
stopping rule in this document that would tell us when to stop amending and launch."* This is where
that rule gets written, and the number is **two**.

#### Why (B) — and an honest note on the trigger

§11 pre-commits: *"a brief-level fix has failed twice on one failure mode … v3 does **not** propose a
third wording; it moves the discipline into the harness."* That is exactly the situation, with one
deviation stated plainly: **§11's trigger is a v2 run that failed, and no v2 run exists.** This is a
*pre-run* escalation invoked on arithmetic rather than on a result. It is the cheaper direction of
error — escalating early costs engineering, escalating late costs the held-out seed block under §10's
one-attempt rule, which no later fix returns.

#### §11's named mechanism does not work. Two independent defects, both measured.

> *"forcing a fixed number of extra `observe`/`wait` round-trips after the model's `turn/completed`,
> in `run_gate0_arm_turn`"*

1. **A pure `observe`/`wait` drain converts a C5 failure into a C9 failure.** Neither tool changes
   `(x, y)`. `_red_success` computes `post = [(x, y) …] for watches[exit_idx:]` — **all** rows to
   end of file — and needs ≥ 2 distinct tiles. Measured on the only run that exists: v1's entire
   post-battle tail is **4 rows, every one at `(5, 6)` on map 40 — one distinct tile**. Append any
   number of forced observes to that trace and `exit_idx` becomes 434, C5 passes, and
   `red_no_free_movement_after_exit` **fails**. That is §5.1's defect verbatim — *"The draft traded
   one predicate clause for another and called it a fix"* — repeated at the harness level. **A v3
   drain must move, not merely look**, which means the launcher performs game actions, which is a
   materially heavier change than §11 budgeted for.
2. **The launcher has no channel to the world.** `build_docker_mcp_args` returns
   `docker run -i --rm …`: the world is a **stdio child of `codex`**, whose pipes `codex` owns.
   `run_gate0_arm_turn` speaks JSON-RPC to `codex app-server` and never to `gate0_world`; there is no
   `plugin.observe` for it to call. §11's mechanism is not merely insufficient — **it is not
   implementable at the site §11 names.**

#### The v3 that *is* implementable, named so the escalation is not a dead end

`build_turn_start_request(thread_id, input_items)` is already parameterised on `thread_id`, so the
launcher can start a **second turn on the same thread** after `turn/completed`. The world container
is still alive and the MCP session unchanged, so the agent's own tools do the moving — and the
second turn's text lives in code, where an integer is permitted and cannot be re-read as *"a
handful"*. Its costs are real and all of them are David's call:

- one extra short turn's tokens (cached prefix; S-3 has ~400 tool calls of headroom);
- **a taint decision**: whether an explicit count inside a post-hoc evidence-collection turn leaks
  the predicate. It is worth arguing rather than assuming, and the argument is this — **C5, C7 and
  C9 are evidence-quality clauses, not capability clauses.** The claim under test is C2/C3/C4:
  obtain the starter, win the rival battle. Those are decided, and unfakeable, before the second
  turn begins. C5 exists to confirm the RAM reading is a sustained real state rather than a one-tick
  artifact; C9 to confirm the player is alive and free rather than frozen. **Asking the subject to
  generate the evidence that its own result is trustworthy is the category error underneath both
  failed drafts**, and it is the thing a harness is for.
- an `expected_launcher_sha256` re-pin, its own plan/branch/adversarial review per §0.2 and §11.

#### Does #193 still merge? Yes — and merging it cannot cause a launch

W3/W4/W5 are correct, W4 is load-bearing for Arm W, and W1/W2 are strictly better than §5.3 even
though they do not close C5. Landing them is right. Launching on them is not, and the harness
already enforces that: `refuse_if_expected_pins_stale` refuses on all four stale fixtures today.
**§6.1's pin re-freeze is the last gate between here and a paid run, and it must not land until the
C5 escalation is settled.**

#### Two risks the amendment amplifies, named here rather than discovered later

- **`BLOCKED` may read as rejection.** `PerceptionPlugin`'s render carries
  `Last move '<b>' -> BLOCKED: you did NOT move; that direction is a wall.`, and the brief's
  unchanged *"If the environment rejects further input, stop immediately"* meets it. The amendment
  demands *more* small local moves inside a confined room, so wall collisions multiply; an agent
  reading BLOCKED as rejection stops settling at its first wall. The clause is pre-registered and
  unchanged, so this is not a new defect — but the amendment amplifies it, and it is one more reason
  the floor cannot be entrusted to a wording.
- **Arm W exposure rose and was not analysed.** Everything above is Arm-R-only. §5.5 pre-registered
  the risk that an agent applies the settle rule *per episode*; this amendment raises the settle
  floor, so if that ever happens the damage is proportionally longer. The guards (the prohibition
  plus W4's carve-out) are intact and improved, so this is not blocking — but per §11 an Arm W
  `terminal_count` / `terminal_not_last_row` failure is *"a brief defect, not a capability result"*:
  it burns the run without buying evidence.

### The honest risk, on the record because David asked for it, not because it is comfortable

**Tuning a brief until reviewers stop predicting failure is its own form of p-hacking.**

That sentence is the cost of this entry and it is not hedged. What has happened here is that a
pre-registered intervention was rewritten in response to a prediction that it would fail, by the
same programme that will score whether it failed. The timing argument above is a real defence and it
is the standard one — but it is a defence of *legitimacy*, not of *neutrality*. Nothing in it stops
the next reviewer predicting a different failure, or the one after that, and there is no principled
stopping rule in this document that would tell us when to stop amending and launch. If v2 passes C5,
a hostile reader is entitled to ask how many drafts it took, and the honest answer will be **two, on
the day of the run, the second written after a reviewer computed that the first would miss.** That
answer must be given, not buried.

Three things narrow it, and none of them dissolve it:

1. **No bar, predicate, threshold, fixture or seed moved.** `eval/score_gate0.py` is byte-untouched
   by this PR. The thing being tuned is the *instruction to the agent*, not the *test*. Tuning the
   test would be fatal; tuning the brief is the intervention doing its job — §5's own framing is
   that the brief IS the intervention.
2. **The defect was arithmetic, not taste.** §5.4's C5 and C7 defences rest on using and not using
   the same tool. That is a demonstrable inconsistency inside the frozen proof, reproducible by
   anyone, not a reviewer's hunch about how a model will behave.
3. **It is one amendment, authorised once, before any run.** If a *further* wording change is
   proposed after this, it needs its own entry and its own authorisation, and the count in that
   entry will be three.

**This entry does not relax any bar and may not be cited to reinterpret any result.** If v2 comes
back with `red_no_sustained_battle_exit` a second time, §11's escalation ladder applies unchanged
and the correct conclusion is the harness-side v3, not a third brief.

### What §5.4/§5.6 now say that is no longer true of the applied text

Recorded here because the frozen document cannot be corrected:

- **§5.4 C5** quotes *"until several consecutive observations show nothing further changing"* as the
  mechanism that satisfies the clause. That sentence no longer exists in the brief; the mechanism is
  now the round/floor/doubling construction above.
- **§5.6** cites *"several consecutive observations"* as evidence that no count is named. Still no
  count is named, but the evidence has moved to *"a handful of rounds is not enough"* — a negative
  bound below the bar, not a positive one on it.
- **§5.6's "No tool named" is false as written** (see W5) and was false of §5.3 too. It is true of
  the amended text for every tool except `observe`, which §5.6's own vocabulary list already
  permits.
- **§5.3's three-clause table** is now a five-clause set. All three original entries survive; the
  prohibition's act enumeration is replaced and two settle clauses plus the reset carve-out are
  added. All of them are pinned by name in
  `tests/test_gate0_appserver_arm.py::V2_LOAD_BEARING_CLAUSES`, alongside a
  `test_the_prohibition_trigger_names_an_episode_and_not_a_task` two-sided assertion and a
  mechanical re-run of §5.6's taint rule.

### The pins moved again — printed, not written

Recomputed by the launcher's **own** `task_text_for()`, never hand-typed, and deliberately **not**
written into any fixture (that is §6.1, a separate reviewed step):

| arm | v1 (in all four fixtures today) | §5.3 verbatim (superseded) | **D6-amended (current)** |
|---|---|---|---|
| `red` | `306751c34627f6d5c6a8c94ac2f714e358f0dcbc5867866c273e434de7f4b7c4` | `9adb98f89f1d3f2c68c55fb5ea6c646ba79c2c38e5aadaf80cc187b4dd4968a7` | **`aa8f1a7a4e409d03c42843e622df896fdc61c7ff8a74d51905defdcbfcb06d88`** |
| `miniwob` | `845638c874df2f2de2adaebdd1d6c9318c689a46d0032fa76a9393e1e47512d1` | `ba1549d4814e0fc9265643c794376b119721bf993846695446988c5f2ceb5b74` | **`24e4d9b27aa8277c8e2d35639c3b1d0bc53d7343a3b00efa46c34ba79daae440`** |

**§6.1's re-freeze must copy the third column.** The middle column is dead and exists in this table
only so that a reader who finds it in an old PR body knows which one it is.

`refuse_if_expected_pins_stale` (`ec881e4`, this branch) still refuses a launch on all four stale
fixtures, and the `xfail(strict=True)` fixture→code tripwire still xfails for the same reason it did
before — this amendment moves the digest, it does not close the gap.

### Taint re-check, run mechanically over the amended text

No digits at all. No occurrence of `in_battle`, `RAM`, `HP`, `party`, `oracle`, `row`, `score`,
`tile`, `battle`, `map`, `watch`, `exit`, `jsonl`, `predicate` or `threshold`. Exactly one non-ASCII
codepoint, `U+2014`, ×3, as before. No threshold, span or `exit_idx+9` boundary is named.
**Vocabulary removed:** `click`, `type`, `press`, `key`, `several`, `consecutive`, `changing`,
`show`, `until`, `observations`, `otherwise`, `act`. **Vocabulary added:** `long`, `observe`,
`observation`, `again`, `after`, `every`, `move`, `one`, `round(s)`, `many`, `times`, `over`,
`handful`, `enough`, `stopping`, `first`, `time`, `appears`, `either`, `judge`, `judgement`,
`treat`, `halfway`, `point`, `rather`, `than`, `carry`, `same`, `way`, `then`, `these`, `of`,
`settling`, `send`, `kind`, `starting`, `next`, `as`, `follows`, `have`. The net movement is **away**
from the tool surface and toward ordinary effort language.

**Net taint position: a wash, not an improvement — stated at the right strength.** Mechanically the
amended text is clean, and replacing §5.3's *"several"* (which evaluated to exactly the bar at
5 alternations × 2 rows) with a negative bound plus a multiplier does remove a real on-the-bar
coincidence. But the round construction **discloses something §5.3 did not: it hands the agent a
countable unit and tells it to count.** The scorer's currency is one row per row-writing tool call;
the brief's new currency is one round per move-plus-look. Defining a unit that maps near-1 : 1 onto
the scorer's own counting basis is structurally *closer* to the predicate than *"several consecutive
observations"* was, even with no count named. Improvement on the coincidence, regression on the
counting basis. This entry does **not** claim a stronger taint position than §5.3's.
