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

## D5 — P1c's named satisfaction method is incomplete: a fresh capture alone does not satisfy it

**Landed by:** PR #195, `fix/gate0-red-capture-mode`.
**Touches:** `tools/capture_gate0_baseline_red.py`, its tests, and `DAVID_BASELINES.md`. No fixture,
no scorer, no `runs/` artifact, and **not** `reports/2026-07-25-gate0-v2-prereg.md`.

**Why D5 and not D2/D3/D4:** D1 is on `main`; #188 claims **D2**, #191 claims **D3**, #192 claims
**D4** — verified by reading this file on each branch head (`origin/fix/audit-verdict-not-gate-verdict`,
`origin/fix/red-glitch-row-signature`, `origin/fix/gate0-launcher-mode`) on 2026-07-28. #193 and #194
do not touch this file. D5 is the first uncontested slot; no collision. Append newest-last, so this
section belongs after D4.

### The rig change itself is NOT a deviation — the prereg pre-authorised it

Stated plainly so the log is not read as claiming more than it should. Prereg `:264-269` already
says:

> If the capture tool cannot yet emit Red under that mode, extending it to do so is in-scope
> plumbing for the P8/P9 batch

That plumbing was simply never done — the P8/P9 batch landed as **#180** without it, and
`tools/capture_gate0_baseline_red.py` still carried `MODE = "readiness_dev"  # the only mode this rig
supports` with no `--mode` flag at all. Adding the flag **satisfies** a precondition. It is recorded
here only for context; it is not the deviation.

### The deviation: this rig now REFUSES a capture the prereg says should just work

P1c does not leave its method open. It says (`:264-266`, emphasis original):

> **The satisfaction method is named here, not left open: P1c is satisfied by a FRESH CAPTURE under
> `--mode paid_gate0_v2`, producing a new artifact.**

**That is not sufficient, and this PR makes the rig say so out loud instead of letting the gap pass.**
All three source-pin fixtures pin `artifact_paths.red_human` at the SAME file —
`runs/gate0_human_baseline/red/human_metrics.json`, the banked `readiness_dev` artifact — and all
three freeze the same real digest `5144a5b3…` for it. Verified on `origin/main` (`322499f`) and
pinned mechanically by
`tests/test_capture_gate0_baseline_red.py::test_all_three_fixtures_currently_pin_the_same_banked_red_baseline`.

So a fresh v2 capture has exactly two possible destinations, and the prereg's text sanctions neither:

| destination | outcome |
|---|---|
| the pinned path (`runs/gate0_human_baseline/red/`) | **overwrites** an append-only banked artifact whose digest THREE fixtures freeze — breaking `readiness_dev` and `paid_gate0` source verification at the same time, and doing by `--out` exactly what `:266-269` forbids doing by hand-edit |
| anywhere else | the artifact is correct and **nothing reads it**; `_verify_sources` still loads the banked `readiness_dev` file, still fails `human_metric_identity:red`, still yields `INSUFFICIENT_DATA` |

**P1c therefore has a third step the prereg does not name: re-point `artifact_paths.red_human` (and
re-freeze `artifact_sha256.red_human`) in `eval/fixtures/gate0_paid_v2_source_pins.json`.** PR #194's
runbook reached the same conclusion independently ("a code change to the rig, a human replay by
David, and a re-point + re-freeze of `artifact_paths.red_human`").

This is the same shape of finding as **D4**: a `§0`/P-item that asserts its own completeness and is
not complete. It is recorded, not silently worked around.

### What changed, and the one deliberate behaviour difference

One required `--mode` (choices read from `eval.score_gate0.MODES` itself, function-local import), no
default — an unstated mode is a refusal, not a guess. It drives both mode-dependent values: the
`mode` field stamped into `human_metrics.json`, and the output directory, from a per-mode
`MODE_CONFIG` mirroring `tools/capture_gate0_baseline_miniwob.py`'s. Two guards, both on held-out
modes only:

1. **`--i-am-human`**, mirroring the MiniWoB rig. The rationale differs and the difference is
   deliberate: there it protects held-out SEEDS (and the rig also suppresses the task utterance);
   Red has no held-out seed family, its task text is public and printed in full in every mode, so
   there is nothing to suppress. What it protects here is the ARTIFACT — a paid-mode
   `human_metrics.json` is the denominator the `agent <= 2.0x human` bar is measured against.
2. **The fixture cross-check** — refuse unless the mode's own source-pins fixture already points
   `red_human` at the directory this capture writes to. **This is the deviation.** The prereg says a
   fresh capture satisfies P1c; the rig now refuses that capture until the fixture re-point exists.
   Refusing costs a `$0`, ~4-minute human replay. Not refusing costs the discovery at scoring, after
   the paid run. The refusal message names the exact fixture field to edit and explicitly forbids the
   two wrong workarounds (hand-editing the banked artifact; pointing `--out` at it).

   **Validate and refuse, never derive** (#192's F2 lesson, applied to a write path): deriving the
   output directory from the pin would send a v2 capture straight into the banked artifact — the
   worse of the two rows in the table above.

**`readiness_dev` is exempt from guard 2, and that scoping is load-bearing.** Its baseline is already
captured, banked, and pinned to exactly the file it writes; re-checking protects nothing and would add
a new way for a legitimate `--allow-retake` to fail. The exemption is what keeps that path untouched.

### `readiness_dev` identity — measured, not asserted

A throwaway differential harness (not committed) records what the tool **actually writes and where**:
the effective output directory, `REAL_OUT`, the `_under_real_path` answers over a path matrix, the
full `_build_metrics` payload, and — driving the real `run()` with `PyBoy` faked to raise, so no SDL2
window is ever created — the exit code, stdout, stderr and **every file written (path and content)**
across five scenarios: first attempt, `--test`, overwrite-refusal, `--allow-retake`, and stale-oracle
archival. Repo root, temp dirs, unix timestamps and ISO timestamps are normalised so two worktrees
are comparable; the harness was confirmed self-stable (two runs of the same tree hash equal).

`origin/main` (`322499f`, no flag) vs this branch (`--mode readiness_dev`):

```
IDENTICAL
b1a0c865931463d0adee8f19e43b998e4b8c1e11c909b46247128cb85131b3f3   (both sides)
```

The only recorded difference is the parsed argparse namespace, which gains `mode` and `i_am_human`
and moves `--out`'s default out of argparse into `run()`. The **effective** output directory is
byte-identical and is compared inside the hash above.

### What this does NOT do

It does not satisfy P1c. It supplies the first of three steps. It produces no capability evidence,
touches no `runs/` artifact, and re-freezes nothing. It also leaves a **declared duplication**:
`pinned_red_human_path()` re-implements #192's `pinned_artifact_path()` because #192 is unmerged (the
symbol does not exist on `origin/main`) and `tools/gate0_appserver_arm.py` was off-limits to this
change. Two resolutions of one pin is the drift class this workstream exists to remove — once both
land, lift one shared helper and delete both.
