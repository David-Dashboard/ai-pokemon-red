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

## D2 — the checker was edited after the freeze (`audit()`'s `overall` → `audit_overall`)

**Landed by:** PR #188, `fix/audit-verdict-not-gate-verdict`.
**Touches:** `tools/check_gate0_codex.py`, `tools/gate0_appserver_arm.py`,
`tools/gate0_wake_boundary.py`, their tests, and one probe script under `reports/probes/`.
`eval/score_gate0.py` is byte-untouched.

### What the prereg says

§6.6 ("What needs a code change, and what does not"), `:869-870`:

> **`eval/score_gate0.py`'s predicates, bars, caps, and verdict logic are not edited and must not
> be.** P9 adds a mode; it changes no threshold and no clause. `tools/check_gate0_codex.py` is not
> edited at all.

As of PR #188 the final sentence is false: `tools/check_gate0_codex.py` **is** edited. That is the
deviation being reported.

### Why this is a deviation to report, not a violation to escalate

- **The clause is descriptive, not prescriptive.** Note the asymmetry inside that one bullet: the
  scorer is "not edited **and must not be**"; the checker is only "not edited at all". §6.6's job is
  to say which files §6's twenty pin items touch — it is scoping the re-freeze work, not issuing a
  prohibition. The prohibition in that bullet attaches to `eval/score_gate0.py`, which PR #188 does
  not touch.
- **§0.1 asks for exactly this change.** The same frozen document records the 2026-07-28 false
  escalation — a reviewer read `audit()`'s `overall: NO_GO_INSUFFICIENT_WAKES` as the gate's ceiling
  and concluded Gate 0 v2 was structurally unwinnable — and names the dead `build_agent_metrics`
  (`:311-329`) as evidence of the trap. `:180-182` calls that trap "worth a separate cleanup PR;
  **out of scope here, and not a v2 blocker**". PR #188 is that cleanup PR.
- **Line-number drift is pre-authorised.** §"Line-number citations are anchored to a commit"
  anchors every `tools/check_gate0_codex.py:N` citation to `208d211` and states that where a
  citation and the quoted code disagree, the quoted code and the named identifier win.

### The property the prereg warns about is deliberately preserved

`:176-179` records:

> `tools/check_gate0_codex.py:380` is `return 0 if summary["overall"] == "PASS" else 1`, so that
> CLI **always exits non-zero**. Any script branching on that exit code is reading a constant. Not
> a precondition; worth knowing before someone wires an automation to it.

An earlier revision of PR #188 changed `main()` to exit 0 when the four failure lists are clean,
which would have falsified that paragraph outright. **That change was dropped before merge** and
`main()` still returns `0 if summary[<verdict key>] == "PASS" else 1` — now keyed on
`audit_overall`, and still always 1, because that chain has no `PASS` branch. Only the quoted key
name in that citation is stale; the behaviour it documents is intact. Reasoning: `audit()` is an
intermediate diagnostic, the verdict authority is `eval/score_gate0.py::score()`, and a CLI that
exits 0 on a clean audit is the audit-verdict/gate-verdict conflation in executable form — one
`... && echo PASS` away from a fabricated Gate 0 pass. No consumer of that exit code exists (no
launcher, no CI, no `.ps1`/`.sh`), so there was no benefit to weigh against that risk.

### What did NOT change — measured, not asserted

`eval/score_gate0.py` is byte-untouched (`git diff --name-only origin/main..HEAD` lists no file
under `eval/`). Two `$0` differentials were run:

**`audit()`, `origin/main` vs PR #188, five transcript shapes across both arms:**

```
clean             all other fields identical + verdict VALUE identical: True  (NO_GO_INSUFFICIENT_WAKES)
leak              all other fields identical + verdict VALUE identical: True  (NO_LEAK)
run_failed        all other fields identical + verdict VALUE identical: True  (NO_GO_RUN_FAILED)
empty_transcript  all other fields identical + verdict VALUE identical: True  (NO_LEAK)
red_arm_clean     all other fields identical + verdict VALUE identical: True  (NO_GO_INSUFFICIENT_WAKES)
-> field-level mismatches: 0
```

Only two things differ at all: the key `overall` → `audit_overall`, and the emitted dict's
`schema_version` 2 → 3. Every verdict VALUE is unchanged, and every field the scorer reads is
unchanged.

**`score()` fed both audit-dict shapes, across all five failure tiers:**

```
all clean    verdict identical: True  -> INSUFFICIENT_DATA/INSUFFICIENT_SOURCE
leak         verdict identical: True  -> NO_LEAK/NO_GO
constancy    verdict identical: True  -> CONSTANCY_BREACH/NO_GO
run failure  verdict identical: True  -> INSUFFICIENT_DATA/INSUFFICIENT_SOURCE
accounting   verdict identical: True  -> INSUFFICIENT_DATA/INSUFFICIENT_SOURCE
-> verdict differences across shapes: 0
```

No predicate, bar, cap, threshold, seed, mode, fixture, or pinned constant is touched. The RUN
RECEIPT's `schema_version` deliberately stays `2` (`_receipt_shape_failures`); only `audit()`'s own
emitted dict moves to `3`.

### The cost this deviation does carry: four §0.1 citations no longer resolve against HEAD

PR #188 deletes `check_gate0_codex.build_agent_metrics`, and the frozen prereg cites that function
in **four** places as evidence for §0.1's own reasoning — `:115` and `:138` and `:180` inside §0.1
itself, plus `:1034` in `## Sources` ("the unreachable `build_agent_metrics` `:311-329`"). A hostile
reader re-deriving §0.1 against HEAD will find the cited function absent and cannot verify the
citations from the working tree; they now resolve only against the anchor commit `208d211`.

This is a real cost and it is not being papered over. It is judged minor and accepted because: the
argument those citations support is that the function was **dead** — deleting it does not weaken
that argument, it completes it; §0.1's conclusion (that `audit()`'s ceiling does not cap the gate)
rests on `eval/score_gate0.py`, which is untouched and still verifiable line-for-line; and `git show
208d211:tools/check_gate0_codex.py` reproduces every cited line on demand. The prereg is frozen and
is **not** edited to repair the citations. (A fifth mention, `:1047`, lists a `build_agent_metrics`
belonging to `tools/gate0_appserver_arm.py` — a different function, still present, unaffected.)

### Precondition impact (P1a–P9)

**No effect: P1a, P1b, P1c, P2, P3, P5, P6, P7, P8, P9.**

**P4 — partial, item 9 only.** PR #188 edits `tools/gate0_appserver_arm.py`, so that file's blob
hash moves, and §6.3 pins it as `expected_launcher_sha256`. Nothing is invalidated today:
`eval/fixtures/gate0_signature.appserver.json` still carries
`REPLACE_WITH_canonical_HEAD_blob_sha256_of_tools/gate0_appserver_arm.py` and
`REPLACE_WITH_git_rev-parse_HEAD_AT_SIGNATURE_TIME`. P4's re-freeze must be computed **after**
#188 merges, as it must be after any launcher edit. `COMMON_TASK_SUFFIX` is untouched, so the four
`task_sha256` pins do not move.

### One artifact under `reports/` was repaired

`reports/probes/2026-07-28-gate0-breach-addendum/reproduce_breach.py` is tracked executable code
that imports the live `audit()`; the rename would have made it raise `KeyError`. Its three key
tuples were repointed and its docstring updated. No finding, verdict, or number of that probe
changes — the `reports/` freeze protects claims, and a claim's reproduction script that no longer
runs protects nothing.

**Correction (added after an independent review of this report).** An earlier revision claimed the
repaired probe "still print[s] `CONSTANCY_BREACH` with `['pin_mismatch:config_sha256',
'pin_mismatch:codex_mcp_list_sha256']`, matching
`reports/2026-07-28-gate0-constancy-breach-addendum.md:73-74`." **The verdict reproduces; that
specific failure list does not.** It was copied from the addendum's table rather than read off the
run, which is exactly the "never claim a result you did not just observe" rule this repo runs on.
What the probe actually prints today, both arms `CONSTANCY_BREACH`:

```
miniwob  Mode A: pin_mismatch: config_sha256, codex_mcp_list_sha256, tool_schema_sha256,
                 world_image_id, host_code_sha256, image_code_sha256      (6)
         Mode B: pin_mismatch: tool_schema_sha256, world_image_id,
                 host_code_sha256, image_code_sha256                      (4)
red      Mode A: pin_mismatch: config_sha256, codex_mcp_list_sha256, world_image_id,
                 host_code_sha256, image_code_sha256                      (5)
         Mode B: pin_mismatch: world_image_id, host_code_sha256, image_code_sha256   (3)
```

**This is not caused by PR #188** — the differential above shows `origin/main`'s `audit()` and this
branch's produce byte-identical failure lists. The extra entries are post-addendum fixture re-pins
landing between the addendum and now: the #180 world-image rebuild moves `world_image_id` /
`host_code_sha256` / `image_code_sha256`, and the P8 MiniWoB tool-surface repair moves
`tool_schema_sha256` on that arm only. The addendum's own numbers were true against the tree it was
written on; reproducing it byte-for-byte requires that tree, not this one.

### Sources

- `reports/2026-07-25-gate0-v2-prereg.md` §0.1, §6.3, §6.6, `:176-179` (frozen; read, not edited)
- `reports/2026-07-28-gate0-constancy-breach-addendum.md:73-74`
- PR #188, and its posted adversarial reviews
