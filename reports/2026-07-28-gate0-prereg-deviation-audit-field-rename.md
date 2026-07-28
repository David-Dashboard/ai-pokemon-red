# Gate-0 v2 pre-registration — DEVIATION REPORT: `tools/check_gate0_codex.py` was edited (2026-07-28)

**The frozen pre-registration is NOT edited by this document.** `reports/2026-07-25-gate0-v2-prereg.md`
froze on merge (#162) and stays byte-untouched. Its own rules require a deviation to be *reported*
rather than papered over, and this file is that report.

## 1. The deviation

`reports/2026-07-25-gate0-v2-prereg.md:869-870` (§6.6, "What needs a code change, and what does
not") states:

> **`eval/score_gate0.py`'s predicates, bars, caps, and verdict logic are not edited and must not
> be.** P9 adds a mode; it changes no threshold and no clause. `tools/check_gate0_codex.py` is not
> edited at all.

As of PR #188 the final sentence is false: `tools/check_gate0_codex.py` **is** edited.

## 2. Why this is a deviation to report, not a violation to escalate

- **The clause is descriptive, not prescriptive.** Note the asymmetry inside that one bullet: the
  scorer is "not edited **and must not be**"; the checker is only "not edited at all". §6.6's job is
  to say which files §6's twenty pin items touch — it is scoping the re-freeze work, not issuing a
  prohibition. The prohibition in that bullet attaches to `eval/score_gate0.py`, which PR #188 does
  not touch.
- **§0.1 asks for exactly this change.** The same frozen document records the 2026-07-28 false
  escalation — a reviewer read `audit()`'s `overall: NO_GO_INSUFFICIENT_WAKES` as the gate's ceiling
  and concluded Gate 0 v2 was structurally unwinnable — and names the dead `build_agent_metrics`
  (`:311-329`) as evidence of the trap. PR #188 removes the trap.
- **Line-number drift is pre-authorised.** §"Line-number citations are anchored to a commit"
  anchors every `tools/check_gate0_codex.py:N` citation to `208d211` and states that where a
  citation and the quoted code disagree, the quoted code and the named identifier win.

Two citations in the frozen document are now stale and, per the freeze, are left standing:
`:176-177` quotes `main()`'s old `return 0 if summary["overall"] == "PASS" else 1`, and §0.1 cites
`build_agent_metrics` at `:311-329` — a function PR #188 deletes.

## 3. What did NOT change — measured, not asserted

`eval/score_gate0.py` is byte-untouched (`git diff --name-only origin/main..HEAD` lists no file
under `eval/`). Two `$0` differentials were run this session:

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

## 4. Precondition impact (P1a–P9)

**No effect: P1a, P1b, P1c, P2, P3, P5, P6, P7, P8, P9.**

**P4 — partial, item 9 only.** PR #188 edits `tools/gate0_appserver_arm.py`, so that file's blob
hash moves, and §6.3 pins it as `expected_launcher_sha256`. Nothing is invalidated today:
`eval/fixtures/gate0_signature.appserver.json` still carries
`REPLACE_WITH_canonical_HEAD_blob_sha256_of_tools/gate0_appserver_arm.py` and
`REPLACE_WITH_git_rev-parse_HEAD_AT_SIGNATURE_TIME`. P4's re-freeze must be computed **after**
#188 merges, as it must be after any launcher edit. `COMMON_TASK_SUFFIX` is untouched, so the four
`task_sha256` pins do not move.

## 5. One artifact under `reports/` was repaired

`reports/probes/2026-07-28-gate0-breach-addendum/reproduce_breach.py` is tracked executable code
that imports the live `audit()`; the rename would have made it raise `KeyError`. Its three key
tuples were repointed and its docstring updated. Verified read-only against the banked
`runs/gate0_paid` arms: both still print `CONSTANCY_BREACH` with
`['pin_mismatch:config_sha256', 'pin_mismatch:codex_mcp_list_sha256']`, matching
`reports/2026-07-28-gate0-constancy-breach-addendum.md:73-74`. No finding, verdict, or number of
that probe changes — the `reports/` freeze protects claims, and a claim's reproduction script that
no longer runs protects nothing.

## 6. Sources

- `reports/2026-07-25-gate0-v2-prereg.md` §0.1, §6.3, §6.6 (frozen; read, not edited)
- `reports/2026-07-28-gate0-constancy-breach-addendum.md:73-74`
- PR #188, and its two posted adversarial reviews
