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

**Those are the same tool.** `World._run_autopilot` serves both `explore` and `goto` and is
frontier-seeking — its job is to leave the room. §5.3's actual wording takes the C7-safe path
(*"small local moves … without leaving the place you are in"*) and thereby **discards the margin C5's
defence was computed on**. What is left is the primitive path, and the primitive path's arithmetic
was never written down:

| act | rows written | read at |
|---|---|---|
| `observe` | **1** | `core/perception_plugin.PerceptionPlugin.observe` — one `_log_oracle` per call, after the patience loop |
| `press_button` (and every other direct action) | **1** | `world_mcp.World.call`'s direct-action branch: `body = [head, *self._content(self.plugin.observe(_AGENT))]` — one trailing `observe`, therefore one row, whatever the action did |

So *"alternate observing with small local moves"* × N alternations ⇒ **2N rows**, against
`_red_success`'s `watches[i:i+10]` window — **ten**. **N = 5 hits the bar exactly; N = 4 gives 8 and
fails.** The entire margin was the word *"several"*, conventionally 3-5.

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

**No phrase in the brief points at ten.** The floor rules out a handful (below the bar); the
doubling carries the total well past it. The threshold is reached by *composition*, never named —
which is a stronger taint position than §5.3's, where "several" sat directly on the bar.

#### W3 — `task,` deleted from the prohibition's trigger list

§5.3 read *"once the environment reports that an episode, **task**, or input is finished, take no
further action on it — do not click, type, **press a key**…"*. In Arm R the task-complete and
episode-complete conditions fire **at the same instant** (winning the rival battle is the stated
task), and `press_button` is the only way to make a small local move there. The brief therefore told
the agent to move and not to move simultaneously, and §5.3's stated reason they cannot conflict —
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
2. W4's carve-out **blesses `reset_episode`, which DOES write a row**. So the prohibited set is no
   longer the writing set and the blessed set is no longer the non-writing set. The correspondence
   is broken in both directions rather than merely obscured.

`observe` remains the one tool name the brief effectively names, and that is deliberate and
pre-registered: §5.6's own permitted-vocabulary list contains *"observing"*, and it is the act that
writes nothing in Arm W.

### Worst-case row-yield analysis (the deliverable the amendment is judged on)

Under the **most literal, least generous** reading a competent agent could take. One round = one
small local move + one observation = **2 rows** (both established above, by symbol).

| step | reading | rounds | rows |
|---|---|---|---|
| *"a handful of rounds is not enough"* | a handful is five, so the smallest obedient count is six | ≥ 6 | ≥ 12 |
| *"stopping the first time nothing new appears is not enough either"* | cannot terminate early on quiet | — | — |
| *"treat that judgement as the halfway point … carry on … for as many rounds again"* | doubles whatever the agent settled on | ≥ 12 | **≥ 24** |

**24 rows against a threshold of 10 — 14 rows of slack, 2.4×.** Every one of them carries
`in_battle == 0` (no new objective, so no fresh encounter) and an unchanged map (*"without leaving
the place you are in"*), which is what C7 needs over the first ten of them; and the moves vary
`(x, y)`, which is what C9 needs. `exit_idx` lands on the first post-battle row with ≥ 24 rows
behind it, so `range(battle_idx + 1, len(watches) - 9)` contains it.

**Degenerate floor.** If the agent disobeys *"Observe again after every move"* and counts a round as
the move alone, the yield is 12 rounds × 1 row = **12 rows — still over the bar, by 2.** The
analysis only collapses if the agent ignores *two* explicit imperatives (the observe-after-move and
the doubling), at which point it is not obeying the brief at all.

**For comparison, the same arithmetic on §5.3:** N alternations ⇒ 2N rows, with N = "several" = 3-5
⇒ **6 to 10 rows**, i.e. a fail at N ≤ 4 and an exact tie at N = 5 — and the terminating tail
observation-only, so the moves that feed C9 come only from the short prefix.

**Costs, checked:** ~24 extra MCP tool calls. `primitive_action_events` counts tool calls, not
autopilot steps, so v1 Red's 142 actions against the 542 cap and 127.75 s against 466.576 s both
absorb it with room to spare (S-3 is not at risk).

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
