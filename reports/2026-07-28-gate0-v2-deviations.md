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

## D4 — the LAUNCHER's own v1 hardcodes were not pre-registered, and had to be fixed to launch at all

**Landed by:** PR #192, `fix/gate0-launcher-mode`.
**Touches:** `tools/gate0_appserver_arm.py` + its tests only. No fixture, no scorer, no `runs/`
artifact, and **not** `reports/2026-07-25-gate0-v2-prereg.md`.

**Why D4 and not D2/D3:** D1 is on `main`; #188 (`fix/audit-verdict-not-gate-verdict`, head
`7d6b2ee`) claims **D2**; #191 (`fix/red-glitch-row-signature`, head `24e27f2`) claims **D3** —
verified by reading this file on both branch heads. D4 is therefore the first uncontested slot and
there is no collision. (An earlier revision of this section said #191 also claimed D2; that was true
when written and #191 has since renumbered to D3. Corrected here rather than left standing, because
this log is a permanent record that will be read as history.) The three PRs should land in numeric
order **#188 → #191 → #192**: this log appends newest-last, so landing #192 first would leave it
ordered D1, D4, D2. Numeric order keeps it monotonic with zero renumbering. If any of those PRs is
closed unmerged the numbering will have a cosmetic gap; a gap is preferable to a collision, and
nothing in this log depends on the numbers being dense.

### What the prereg says

§0.2's "required code changes needing their own plan, branch, and adversarial review" names exactly
one seed hardcode, and it is the **scorer's**:

> **P9 — fresh seeds require an additive scorer change.** `eval/score_gate0.py:13-16` hardcodes
> `MODES["paid_gate0"] = (…gate0_miniwob_paid_seeds.json, [1000, 1001, 1002, 1003, 1004])` …

P9 was satisfied (PR #179 + the additive `MODES` entry, `208d211`). But **the launcher has four
mode-blind v1 paths of its own, and none of P1–P9 mentions any of them.** The prereg's §0 table asserts that
"each was verified on disk this session" and that "a run launched with any of these open produces
an unscorable or void artifact and wastes the attempt" — the list was not complete. `P3` even
records that v2 "writes to `runs/gate0_paid_v2/<arm>/`" as **DONE**, on the strength of the fixture
carrying the right paths; the launcher that would have produced those artifacts could not honour
them.

### What was wrong, verified on `origin/main` (`322499f`)

| # | `tools/gate0_appserver_arm.py` | Effect on a v2 launch |
|---|---|---|
| 1 | `build_docker_mcp_args` `:313` mounted `eval/fixtures/gate0_miniwob_paid_seeds.json` | Arm W plays the **SPENT** `[1000..1004]` block. `_miniwob_success` then fails `miniwob_extra_episode_or_seed_conflict` against v2's expected seeds — and even a clean run could not be reported as held-out, since v1's Arm W transcript with the answers is committed. |
| 2 | `_finalize_real_run` `:1192` stamped `mode="paid_gate0"` | `_verify_sources` (`:276-279`) requires the stamp to equal the scoring mode → `agent_metric_identity:<arm>` → `INSUFFICIENT_SOURCE`. |
| 3 | `_finalize_real_run` `:1196` wrote `REPO_ROOT/runs/gate0_paid/wake_boundary.json` **regardless of `--out-dir`** | v2's `wake_boundary` pin points at `runs/gate0_paid_v2/wake_boundary.json` → `source_unreadable:wake_boundary`. And any run through this launcher reached into v1's banked, append-only tree uninvited — demonstrated: on `322499f`, running `pytest tests/test_gate0_appserver_arm.py` in a fresh worktree with no `runs/` directory **creates `runs/gate0_paid/wake_boundary.json`**. |
| 4 | `_default_human_metrics_path` `:1063` took `arm` and **not** `mode`, returning v1's `runs/gate0_paid_human_baseline/miniwob/` for every mode | v2 pins `runs/gate0_paid_v2_human_baseline/miniwob/` (P1a), and `tools/capture_gate0_baseline_miniwob.py`'s `MODE_CONFIG` already routes the CAPTURE side there — the launcher was the sole peer of that pair that was not mode-aware. Not verdict-gating (the scorer reads human numbers from the pinned human FILE, not from `agent_metrics.json`), but a v2 `agent_metrics.json` would have banked **v1's denominator** in its own `human_source_note` — a provenance defect in an append-only artifact. Found by the adversarial review of this PR (F1), not by the original pass, which had named `tools/check_gate0_codex.py:14` as the fourth instance; that one is genuinely unrelated to the v2 flow and #188 deletes it. |

All four are silent. Each is detected only at scoring — or, for #4, never, which is worse.

### What changed

One required `--mode` argument, choices taken from `eval.score_gate0.MODES` itself, and all four
values derived from it (plus `--out-dir` for the wake boundary). No default — an unstated mode is a
refusal, not a guess. Three guards, all reading the SAME frozen declarations the scorer reads, so
launcher/scorer disagreement is impossible rather than merely absent today:

1. the selected seed manifest is re-read at launch and refused if its decoded contents differ from
   `MODES[mode][1]` **or** if its bytes differ from that mode's `frozen_seed_sha256` pin (the
   contents check alone is type-blind: `[417545.0, …]` and `[false, true, 2, 3, 4]` both compared
   equal and launched — F3);
2. on the **real-run** path only, `--out-dir` must equal the directory the mode pre-registers
   (`artifact_paths.<arm>_agent`'s parent). `wake_boundary.json` is the one artifact written
   *outside* `out_dir` (at `out_dir.parent`, because both arms of an attempt share it), so an
   out-of-shape `--out-dir` was the only input that could make a write escape the attempt tree —
   `--out-dir runs/gate0_paid_v2` dropped one at the top of `runs/`, a bare relative path in the
   repo root (F2). Binding `out_dir` itself, rather than deriving the wake path from the pin, was
   deliberate: deriving would reinstate the very defect fixed above, a launch pointed at a scratch
   directory reaching into `runs/gate0_paid_v2/` uninvited. **Bound, not sealed** (approval round,
   G1): that comparison is symlink-resolved on both sides — it has to be, or a checkout sitting
   under a junction would refuse every legitimate launch — so a junction planted at the *leaf* arm
   directory resolves both sides to the same target and is accepted, moving the wake boundary out
   of the attempt tree. Recorded rather than fixed: creating it needs local write access to the
   repo (with which one could write the file anywhere directly), and it fails **closed** at
   scoring as `source_unreadable:wake_boundary`. Reproduced with `mklink /J`, no admin;
3. the human-baseline path is read from the mode's own `artifact_paths.<arm>_human` (F1).

`paid_gate0` behaviour is **unchanged**, proven by differential rather than asserted, and re-proven
after each review round. Run against `322499f` and against this branch with `--mode paid_gate0`, the
docker argv of both arms, the resolved human-baseline path of both arms, the seed manifest, the
`agent_metrics` mode stamp, the wake-boundary path, and every file `_finalize_real_run` writes (path
**and** content) are identical. (The capture harness prints a digest of its own normalized record.
That digest is **internal to the harness and not re-derivable by a third party** — it hashes a
private normalization. The reproducible claim is the *equality* of the two sides, which any reader
can re-obtain from the two checkouts; the number is not evidence and is not reproduced here.)

**Two deliberate behaviour changes, both outside `--mode paid_gate0`:**

1. **Guard 2, on the real-run path of every mode.** At both pre-registered v1 out-dirs
   (`runs/gate0_paid/red`, `runs/gate0_paid/miniwob`) the launcher accepts exactly as before; it now
   refuses only real-run invocations aimed off that shape, which are precisely the ones `main`
   allowed to write outside the attempt tree.
2. **`readiness_dev`'s MiniWoB human baseline moves.** Guard 3 is mode-aware, so
   `--mode readiness_dev --arm miniwob` now reads `runs/gate0_human_baseline/miniwob/` (that mode's
   own pin) instead of v1's `runs/gate0_paid_human_baseline/miniwob/`. In David's primary checkout
   the v1-paid file is **absent** and the dev file **exists**, so a `readiness_dev` MiniWoB run's
   `agent_metrics.json` changes from `human_wall_clock_s: null` + `human_source_note: "human
   baseline file not found"` to the dev baseline's real numbers + `"copied from
   .../gate0_human_baseline/miniwob/human_metrics.json"`. This is the correct value — it is the
   file `eval/score_gate0.py::_verify_sources` reads for that mode, so before this change the
   launcher's own record disagreed with the scorer — and `readiness_dev` is the **$0 dev mode**, so
   no paid artifact is affected. It was not disclosed in the first two rounds and is recorded here
   because a governance record that omits a behaviour change is the defect, not the change.

`paid_gate0` and `paid_gate0_v2` human baselines are untouched by (2). v1's banked artifacts stay
scoreable exactly as printed, which is what §0.2 requires.

### What this does NOT do

It does not make a v2 launch ready. P1a/P1b/P1c/P2/P4/P5/P6/P7 all remain open, and this change
**invalidates** `gate0_signature.appserver.json`'s `expected_launcher_sha256` — P4 item 9 — which
must be re-frozen after whichever launcher edit lands last. It also does not touch
`tools/run_gate0_codex.ps1:632`, which carries the same v1 seed hardcode on the **superseded exec**
launch surface; see the PR body for why that was left, and treat it as a live trap for anyone who
reaches for that script. Sharper than the PR body originally put it: that script's paid path is
gated by `Confirm-PaidExecSignature` against `eval/fixtures/gate0_signature.json`, which is
**untracked and absent from git but present and fully populated (no `REPLACE_WITH_…` placeholders)
in David's primary checkout** — so on the machine a v2 attempt would actually be launched from, that
file is a real, populated signature rather than the template the repo implies.

**Corrected (approval round, G4): populated is not the same as passable, and the earlier wording
blurred them.** That signature pins `frozen_commit
53a8ded5c90ef5362233f9daaead7581e7d5989e` (signed 2026-07-22, for Arm R) and `arm: red`.
`Confirm-PaidExecSignature` compares `frozen_commit` against the checkout's live HEAD and `arm`
against the launch's arm, so **as of today it refuses every launch from that script** — HEAD is
`322499f`, not `53a8ded`. What the populated file demonstrates is the file's *shape* — that David
has authored a real signature before and the machinery is exercised, not placeholder-only — **not**
that the gate is currently open. The trap is therefore narrower than stated: reaching for
`run_gate0_codex.ps1` for a v2 attempt fails at the signature check first, and only becomes a spent-
seed hazard if someone re-signs it for a v2 HEAD without noticing `:632`'s v1 seed hardcode. The
honest minimum follow-up is unchanged: make that script *refuse* a non-v1 attempt outright rather
than teach it modes.
