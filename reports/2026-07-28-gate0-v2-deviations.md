# Gate 0 v2 — deviations from the frozen pre-registration (2026-07-28)

Deviation log for `reports/2026-07-25-gate0-v2-prereg.md`, which is **frozen on merge**. Its
closing law, verbatim (`:1018-1019` — the sentence starts on `:1018`; the earlier `:1019` was off by
one):

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
- **§0.1 asks for the deletion — not the rename, and not the exit-code change.** An earlier
  revision of this entry said "§0.1 asks for exactly this change." It does not, and this is the
  permanent record, so the distinction is drawn here in full rather than left to a reader's
  goodwill.

  **What §0.1 does ask for.** The same frozen document records the 2026-07-28 false escalation — a
  reviewer read `audit()`'s `overall: NO_GO_INSUFFICIENT_WAKES` as the gate's ceiling and concluded
  Gate 0 v2 was structurally unwinnable — and names the dead `build_agent_metrics` (`:311-329`) as
  evidence of the trap. `:180-182`, in full:

  > The dead `PASS` branch and the unreachable `build_agent_metrics` are a standing trap that has
  > now misled at least one reviewer into declaring the gate unwinnable. Worth a separate cleanup
  > PR; **out of scope here, and not a v2 blocker.**

  That names a **deletion** — the dead `PASS` branch and the unreachable function — and it names it
  as a recommendation, not a precondition (§0.1 is flagged non-blocking in its own heading and
  again at `:109`). PR #188 performs that deletion.

  **What §0.1 does not ask for.** The **rename** `overall` → `audit_overall` is this PR's own
  proposal. `:175-176` states a reading discipline and nothing more — "`audit()`'s `overall` must
  never be quoted as the gate verdict (D-7). The authority is
  `eval/score_gate0.py::score()["overall"]`" — and requests no code change to enforce it. (That
  `D-7` is the prereg's own failure-mode list at `:419`, not an entry in this file.) The same
  discipline was already written down at `reports/2026-07-18-gate0-prereg.md:81-83` and did not
  hold; moving it into the identifier is **this PR's judgement** about how to make it hold, and it
  should be reviewed as a proposal on its merits, not as a frozen instruction being carried out.

  **The exit-code change cut against §0.1 rather than being asked for by it.** It, too, was this
  PR's own proposal, and `:177-179` records the always-non-zero exit as a *fact about the CLI*, not
  a defect to repair — so shipping it would have falsified the frozen text. It was dropped before
  merge; see the next section.
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


## D3 — the Red corruption predicate was widened after the freeze (all-zero-only → full wrong-WRAM-bank signature)

**Numbering:** this entry was drafted as `D2`. PR #188 (`fix/audit-verdict-not-gate-verdict`, commit
`7d6b2ee`) was written first, is further along, and also lands a `D2` in this file. Renumbered to
`D3` here to avoid a collision on merge; nothing else about the entry changed with the renumber.

**Landed by:** PR #191 on branch `fix/red-glitch-row-signature`.
**Touches:** `eval/score_gate0.py::_red_success` (the `_is_corrupt_glitch_row` predicate, plus the
type guards its widening made necessary at `post` and in the safety span) and the counterpart in
`eval/score_exam_red_badge.py` (EX01), plus twelve tests. No fixture, no pin, no other predicate.

**Line-number convention (read this before trusting a number in this entry).** Every
`eval/score_exam_red_badge.py` line number below is against this PR's **final head** and was
re-derived by locating the **symbol**, not copied from a review. Each citation names the symbol as
well as the number, so a reader who finds the two disagreeing should trust the symbol and re-locate.
This is not decorative. Each of the fix rounds on this PR grew these functions and moved every
number in this entry: `:76`/`:97`/`:89`, `:121-122` and `:120` all shipped **stale** in the round-2
head, and the `_miniwob_success` split line in the reproduce recipe below has moved **three times
within this PR** — `126` (`eff5746`) → `167` (`24e27f2`) → `209` (`794ee37`) → `225` (`5e37385`,
unchanged at `bef7797`) — four times counting `origin/main`'s `102`. The same defect recurred across
four PRs on 2026-07-28.

> **The chain itself shipped incomplete, and the round-4 review's correction of it was also wrong.**
> Earlier drafts wrote the chain as `167` → `209` → `225`, silently dropping the first PR head's
> `126`. Review round 4 read that three-value chain and concluded the count should be *"two moves —
> three only if you count `origin/main`'s `102` → `167`, which isn't in the chain"*. There is no
> `102` → `167` move: `origin/main` is `102`, the PR's first commit `eff5746` is `126`, and `126` →
> `167` is a separate move. So *"three times"* was right for the wrong reason and the **chain** was
> what was defective. Re-derived by running `git show <rev>:eval/score_gate0.py | grep -n '^def
> _miniwob_success'` over **every** commit in `origin/main..bef7797`, which is the only way to get
> this right. It is the first line-number defect in this entry introduced by a *reviewer* rather than
> by the author — the same lesson as everything below, now in both directions: **do not reason about
> a number, re-derive it.**

`tools/capture_gate0_baseline_red.py` is cited by **symbol with no line number at all**, because it
is under concurrent edit. The single exception to all of this is the `:56` inside the §5.4 C8 block
quote below: that is **verbatim frozen-prereg text** (`reports/2026-07-25-gate0-v2-prereg.md:689`)
describing the *v1-era* scorer, and is reproduced unaltered on purpose — correcting a quotation would
falsify it.

**Timing, on the record:** this change is made **before any Gate 0 v2 run exists** — P1a/P1b/P1c/P2
are all still open, no v2 agent attempt has been launched, and there is no v2 result of any kind to
fit a rule to. That timing is what makes it legitimate rather than post-hoc, and it is the reason
this is recorded now instead of after the run.

### What the prereg says

§5.4 **C8** (`red_player_hp_reached_zero`) did not miss this. It named it, verbatim:

> **Newly exposed — a genuine new risk, NOT "unaffected".** … the span is scanned from `battle_idx`,
> i.e. **through the whole battle**, and the corruption filter only drops rows where *every* watched
> field is 0. **Any mid-battle row with `party_hp_hi == party_hp_lo == 0` that is not the full
> all-zero signature fires this clause.** v1 returned at `:56` before `exit_idx` existed, so this
> clause was **never evaluated** … If C8 appears in v2's failure list, check the raw rows for a
> transient zero-HP sample before concluding the agent fainted.

§5.4 **C6** (`red_missing_player_hp_oracle`) carries the same "unproven in practice, not proven safe"
caveat over the same span. §0.2 sets the standard for any post-freeze scorer change: it *"needs its
own review — it must not be smuggled in as part of a fixture regen."*

**This deviation therefore supersedes a pre-registered handling, not merely a bug.** C8 chose a
*manual raw-row inspection at interpretation time*. That handling is replaced here by an automated
predicate. Two reasons it was not sufficient to leave in place:

1. **C8's handling is FAIL-direction only.** It tells a reader who sees `red_player_hp_reached_zero`
   to go check the rows. It cannot help anyone when the artifact produces a **PASS**, and it says
   nothing at all about `eval/score_exam_red_badge.py` (EX01), which is outside the Gate 0 path and
   where this same artifact **can return a false PASS** (see below).
2. **It relies on whoever reads the failure list actually doing it.** An automated full-row
   signature does not.

### The mechanism, established — not inferred

> **CORRECTED (PR #191 re-review §4).** The first draft of this section said *"Pokémon Red is DMG
> code and never manages SVBK, but transiently stomps it."* **That is false.** `roms/PokemonRed.gb`
> is **byte-identical** to `Pokemon Red Version (Colorization).gb` inside
> `roms/Pokemon Red Version (Colorization).zip` in the same directory — both sha256
> `0602291f922443faf9d6b3a31948e37607a5f487ed8927892f926f86f4105700`, 1 048 576 bytes; confirmed
> independently three times, most recently by hashing both here. The held-out Red world is therefore
> running a **CGB colorization romhack, not stock Red**, and its SVBK writes are **deliberate CGB
> code**, not a DMG program stomping a register it does not know about. The header byte says so
> without any measurement: `0x143` is `0xC0` = **CGB-ONLY** (not `0x80` = CGB-compatible).
>
> The mechanism that actually matters is unchanged and is on the *reader's* side: the oracle reads a
> bank-switched window with an unbanked `memory[addr]`, so whichever bank the ROM has selected at
> sample time is what comes back. Everything below follows from that, not from who wrote to SVBK.
>
> That the world runs a romhack rather than stock Red is **out of scope for this PR and has
> implications past this scorer** — it needs its own issue.

`roms/PokemonRed.gb` carries CGB flag **`0xC0`** at header offset `0x143`, so PyBoy runs it in **CGB
mode**, where `0xD000-0xDFFF` is WRAM-bank-switched by **SVBK (`0xFF70`)**, and the ROM — being CGB
code — drives SVBK deliberately (values 2–7 observed live). **Every** watched
address — `0xD057`, `0xD163`, `0xD16C`, `0xD16D`, `0xD356`, `0xD35E`, `0xD361`, `0xD362`
(`world_mcp.py` `GAMES["pokemon_red"]["watch"]`) — lies inside that banked window, and **every**
producer builds the whole watch dict in **one comprehension against one emulator state**:
`core/perception_plugin.py::_log_oracle`, `tools/capture_gate0_baseline_red.py::run.read_watch` and
`record.py::main.record` alike. So a stomped tick reads **all eight fields out of the wrong WRAM bank
at once**, and the next sample is back on bank 1 — exactly the "sandwiched between identical,
consistent neighbor rows" shape the original PR #121 comment described.

Naming all three matters here and not only under NEW-1: the banked rows this entry rests on
(`attempt1` row 624, `attempt2` rows 363 and 494) are in the **human** traces, so they were written
by `capture_gate0_baseline_red.py`, not by `_log_oracle`. An argument scoped to the agent path would
not have covered its own evidence.

Offline reproduction (`roms/PokemonRed.gb`, PyBoy 2.7.0 headless, no paid run, no network).

**Method, stated in full so the numbers below are re-derivable** (the first draft of this entry
quoted `1003 | 1003` and `358 / 358` without stating the input policy; PR #191 review Nit 6 could not
reproduce them, correctly — see "Corrected figures" below):

1. `PyBoy(rom, window="null", sound_emulated=False, sound_volume=0)` — constructed exactly as
   `core/gb_emulator.py` does, i.e. **no `cgb=` argument**, so the `0xC0` header flag selects CGB
   mode. Optionally `load_state()` a savestate (read-only).
2. Advance **one frame at a time**. After each frame read SVBK (`0xFF70`); a value not in `{0, 1}`
   is a "stomped" tick.
3. On a stomped tick: read the eight `world_mcp.py` watch addresses **as sampled**, then write
   `SVBK = 1`, re-read the same eight as **truth**, then restore SVBK. `diverged` = as-sampled ≠ truth.
4. Classify each diverged tuple against the OLD (all-zero-only) and NEW (eight-field) predicates.

| scan | frames | input | SVBK ∉ {0,1} | diverged | distinct corrupt tuples | old pred. | new pred. |
|---|---|---|---|---|---|---|---|
| cold boot | 60 000 | none | 785 (`{2:779, 3:1, 4:1, 5:1, 6:1, 7:2}`) | **410 / 785** (52%) | `(3,3,3,0,3,0,0,0)` ×410 — one shape | 0/410 | **410/410** |
| `runs/run9_end.state` (mid trainer battle) | 150 000 | `random.Random(3)`, one button every 24 frames, `delay=8` | 247 (all `2`) | **247 / 247** (100%) | `{x/y/map/badges=1, rest=0}` ×242, all-zero ×5 | 5/247 | **247/247** |

**Corrected figures (PR #191 review Nit 6).** The original entry's `1003 | 1003` / `358 / 358` are
withdrawn: they were quoted without the input policy, and the mid-battle scan **cannot** be
reproduced without one — 150 000 frames from `run9_end.state` with **zero** input yields **0** stomped
ticks, because an idle game never stomps SVBK. The two rows above are what actually reproduces.

**Both rows have now been measured three times, and every figure in the table matches on all three.**
The cold-boot row matches the PR #191 round-1 reviewer's independent scan exactly (785 / same SVBK
histogram / 410 / same single tuple / 0-of-410 old / 410-of-410 new); the PR #191 **re-review** fix
round re-ran **both** rows from scratch and reproduced every cell, including the mid-battle row's
`247` / `247` / `{x/y/map/badges=1}×242` + `all-zero×5` / `5-of-247` / `247-of-247` and the
`in_battle == 2` count of **2** below. The reviewer's read of *why* the cold-boot row is 52% and not
100% is right — a cold-boot prefix exists where the alternate bank happens to equal truth.

**Every count in this entry is now stated with its input policy attached**, and that is a standing
rule for this document, not a one-off correction: the withdrawn `358 / 358` was explained entirely by
an unstated input policy, and the `cgb=False` PC-count under "What this does NOT fix" has since been
measured twice as **73** and as **31** — a ~2.4x disagreement on the same quantity — for exactly the
same reason. A bare count in this file is a defect.

**What the predicate actually needs is the second column, not the first:** not "every stomped tick
diverges" but **"every *diverging* tick produces this signature"** — 410/410 and 247/247, i.e. 657/657
across both scans, with **two** distinct shapes total and both of them matched. The alternate bank
holds only residue: `party`/`in_battle`/HP read 0, and the four `0xD3xx` fields all read one repeated
residue byte. All-zero is the *clean-bank* case — i.e. **the predicate that was already there was this
same signature with an untouched bank.** Widening it completes that predicate rather than inventing
one. The old predicate matched **5 / 657**.

Two of the mid-battle scan's divergent samples occurred while the true row read `in_battle == 2`,
i.e. **inside a live trainer battle** — the span C8 scans. (That figure reproduces unchanged from the
first draft, and again in the re-review fix round.)

### The artifact is in banked data, and C8's hazard is realised there

| trace | rows | all-zero (already filtered) | non-zero variant (**was not filtered**) |
|---|---|---|---|
| `eval/fixtures/gate0_red_human_attempt1_no_movement.jsonl` | 900 | **624** — `in_battle == 2` on both neighbours | — |
| `eval/fixtures/gate0_red_human_attempt2_completion.jsonl` | 900 | **494** — `in_battle == 2` on both neighbours | **363** |
| `reports/2026-07-24-gate0-armR-verdict/oracle.jsonl` (banked paid Red arm) | 438 | — | **335, 347** |

All three non-zero rows are byte-identical:
`{"x": 1, "y": 1, "map": 1, "party": 0, "badges": 1, "in_battle": 0, "party_hp_hi": 0, "party_hp_lo": 0}`,
each sandwiched between consistent neighbours (`{"x": 5, "y": 3, "map": 40, "party": 1, "badges": 0,
...}` for rows 335/347). Rows 624 and 494 prove the artifact lands **inside** the safety span on real
human data; only the luck of a clean bank let the old filter catch those two.

**EX01's false PASS is the sharper half.** The non-zero variant reads `badges == 1` — Boulder Badge
bit **set**. In `_red_badge_success`, a corrupt row after the qualifying battle satisfies the
badge-flip check, and if nothing after it clears the bit (e.g. it is the last row)
`red_badge_bit_reverted_after_set` never fires: **a trace in which no badge was ever earned scores
PASS.** On a graduation-exam scorer that is strictly worse than the false-FAIL direction. Not
speculative — on **both** committed traces carrying the variant, EX01 already returned the wrong
reason, `red_badge_flip_not_after_battle` (manufactured entirely by the corrupt row flipping the bit
ahead of `battle_idx`) instead of the true `red_badge_never_earned`.

### Why this cannot mask a real failure (the PR #121 argument, re-proved)

PR #121 review Major 1 rejected a `party`-keyed filter because it would drop a row carrying a
genuinely-corrupted `party` byte **and** a real HP=0 or real map change, silently erasing a real
failure. That argument is preserved and strengthened:

- The predicate still fires only on the **full eight-field signature**, never on a stray field.
- **The delta requires `badges != 0` while `party == 0`.** Work out `New \ Old` exactly — the set of
  rows the widened form drops that the all-zero-only form kept. Every such row has all eight values
  plain ints, `party == in_battle == party_hp_hi == party_hp_lo == 0`, and
  `x == y == map == badges == k`. If `k == 0` the row is all-zero and the *old* form already dropped
  it, so the entire delta needs `k != 0` — a **held Gym Badge alongside an empty party**, which is
  not a reachable Pokémon Red state. A genuine faint, a genuine map change and a genuine badge are
  therefore all outside the delta: they cannot be newly masked, whatever else is on the row.
  Confirmed empirically — across all three committed Red traces the delta is exactly `{363}` in
  `attempt2`, `{335, 347}` in the armR oracle, and `{}` in `attempt1`; every one a known corrupt row.
- It requires `in_battle == 0`, so it can never drop a real in-battle row.
- Both existing PR #121 regression tests (`test_red_corrupted_party_byte_does_not_mask_a_real_death`,
  `..._a_real_map_change`) pass unchanged, and a new test re-proves the property against the widened
  predicate specifically.

> **CORRECTION #1 (PR #191 review Major 2).** The first draft of this entry argued something different
> and **false**: that "every call site consults it only *after* an exact `party` 0→1 transition has
> been established (`party_idx` in `_red_success`; the identical corroboration in
> `_red_badge_success`)", so every genuine row in scope has `party >= 1`.
>
> That is true in `_red_success` — both call sites are downstream of `exit_idx`, which is downstream
> of `party_idx` — and **false in `_red_badge_success`**, where the load-bearing half of the claim
> was. `_red_badge_success`'s `kept = [...]` filter (`eval/score_exam_red_badge.py:123`) filters the
> **entire** watch list; `party_idx` is not computed until its `party_idx = next(...)` line (`:150`),
> and it is computed **from the already-filtered list**. Worse, the fresh-start guard
> `parties[0] != 0` (`:142`) positively **requires** `parties[0] == 0`, so the entire pre-starter
> prefix of every genuine trace has `party == 0` by construction — the opposite of what the argument
> asserted. The claim was not merely unproven at that site, it was inverted.
>
> The conclusion survives, via the `badges != 0 ∧ party == 0` route above, which holds at **both**
> call sites and does not depend on any call-site ordering. The wrong argument has been replaced in
> all three places it appeared: here, `eval/score_gate0.py`'s `_is_corrupt_glitch_row` comment, and
> the `_red_badge_success` mirror docstring at `eval/score_exam_red_badge.py`. A fourth, weaker
> instance in `tests/test_score_gate0.py::test_red_wrong_bank_shape_with_a_real_party_still_fails_a_
> real_death`'s comment — where the ordering claim is *true*, because it is scoped to `_red_success`
> — was also rewritten to the stronger form, so the false version does not survive anywhere to be
> copied.

### The fourth protected clause: `red_badge_bit_reverted_after_set` (PR #191 review Minor 3)

The list above is about what the filter cannot *mask*. It is not the whole story for EX01, and the
first draft's enumeration (genuine faint / genuine map change / genuine badge) was incomplete. There
is a fourth EX01 clause the widening does newly suppress:
`red_badge_bit_reverted_after_set` — the `any(b is False for b in bits[transition_idx:])` clause
(`eval/score_exam_red_badge.py:174-175`). A delta row whose
residue byte is **even** reads `badges` bit-0 **clear**, which is exactly the revert signal, so
dropping the row drops the revert. Constructed trace (reviewer's, reproduced):

```
fresh → starter → in_battle==2 → badges=1 (bit set) → {x=y=map=badges=2, party/in_battle/hp=0} → badges=1
origin/main : (False, ['red_badge_bit_reverted_after_set'])
this head   : (True, [])
```

**Deliberate, not an oversight — the behaviour is kept.** A row with a held badge and `party == 0` is
corrupt by exactly the argument above, and reading a corrupt row as evidence of a *real* badge revert
is the same category error the filter exists to prevent. Suppressing it is the same call as
suppressing the false `red_player_hp_reached_zero`. The reason it is called out rather than left
implicit: that clause's own comment (`:173`) documents it as catching "a savestate reload, a
substituted row", i.e. not only RAM corruption, so a reader is entitled to know the corruption
filter now sits in front of it.
Both the PR's boot scan and the reviewer's observed only **odd** residue bytes (`1`, `3`), so a
bit-0-clear residue is untested rather than impossible — if one is ever observed live, this is the
clause to re-examine first.

**Second reason to re-examine that clause: it was also the only net on a FAKE badge (PR #191
re-review NEW-2).** The justification above — "a `party == 0` row alongside a *held badge* is
corrupt, so declining to read it as a revert is defensible" — quietly assumes the badge is genuine.
It need not be. The re-review built an EX01 trace in which **no badge is ever earned**, where the
badge bit is supplied entirely by a residue-shaped row with **one field mistyped** (so
`_is_corrupt_glitch_row` declines to drop it), while the even-residue revert-catcher **is** dropped:

```
base: fresh → starter → in_battle==2 → sustained exit, badges NEVER leaves 0
  + {"x":7,"y":"7","map":7,"badges":7,"party":0,...}   ← ONE field a str: not dropped, donates badge bit 0
  + {"x":6,"y":6,"map":6,"badges":6,"party":0,...}     ← even residue, bit 0 clear: the revert signal, dropped
```

Reproduced exactly:

| trace | `origin/main` | `24e27f2` | fixed |
|---|---|---|---|
| clean base (no badge anywhere) | `red_badge_never_earned` | `red_badge_never_earned` | `red_badge_never_earned` |
| + spurious row only | **PASS** (shared pre-existing hole) | **PASS** | `red_badge_missing_or_invalid_oracle_field` |
| + spurious row + even residue | `red_badge_bit_reverted_after_set` | **PASS — false PASS** | `red_badge_missing_or_invalid_oracle_field` |
| control: same row with `y: 7` (int) | `red_badge_bit_reverted_after_set` | `red_badge_never_earned` | `red_badge_never_earned` |

**Closed, not argued away**, because a false PASS on a graduation-exam scorer is the worst direction
this file has. `origin/main`'s catch was accidental — one corruption catching another — and row 2
shows the spurious-badge hole is **shared by both branches**; the widening only removed the accident.
The fix refuses the untypeable row outright (`_malformed_row` in `eval/score_exam_red_badge.py`),
which closes both rows at once, including the pre-existing one `origin/main` also had.
**Refuse, not drop:** every clause in `_red_badge_success` only ever *adds* a failure, so dropping an
untypeable row could suppress a real revert; refusing cannot.
`red_badge_missing_or_invalid_oracle_field` is this scorer's existing refusal token for exactly this
case — no new failure name. The **first** reason above (a live even-residue byte) is unaffected and
still stands on its own.

#### The two refusals are NOT mirrors — the scopes differ, deliberately

Earlier drafts of this entry (and of the `_malformed_row` docstrings) described EX01's refusal as
"mirroring `score_gate0.py`". **The helper is shared; the scope is not**, and saying "mirror"
obscures the one difference a reviewer most needs to check:

| | what it scans | refuses when |
|---|---|---|
| `_red_success` (Gate 0) | `watches[battle_idx : exit_idx+10]` — the **safety span only** | a malformed field appears on a row **inside the span** |
| `_red_badge_success` (EX01) | `kept` — the **entire** post-filter watch list | a malformed field appears on **any row of the whole trace** |

**The asymmetry is right, and it follows from the same structural difference that broke the Major 2
argument above.** EX01 filters and validates the whole watch list up front, *before* `party_idx`
exists, and every subsequent clause (`bits`, `parties`, `in_battles`, `party_idx`, `battle_idx`,
`transition_idx`, the revert scan) reads from that one whole-trace list. There is no narrower scope
available to refuse in — the whole list *is* the scope, so a whole-list refusal is the only
fail-closed choice.

`_red_success` is built the opposite way: its spans are computed *later*, and the span is the only
place it **dereferences** a watched value into a substantive claim (`map` compared against
`battle_map`; `hi`/`lo` shifted into `hp_values`). The span guard catches any non-int that reaches
one of those dereferences, and at `post` the same `_malformed_row` helper is used to **drop**,
because there removing a row can only ever *cause* `red_no_free_movement_after_exit`. Gate 0's
refusal is **not** widened to the whole trace, and the reason is **scope, not safety**: post-freeze,
on input no Gate 0 Red producer can emit, pre-existing identically on `origin/main`, and outside what
this PR is for. The pre-span clauses are **not** type-safe, and the paragraph that used to claim they
were is corrected immediately below.

> **CORRECTION #3, on the correction on the correction (PR #191 review round 4, Major).** (The three
> corrections are numbered by the order they were *written*, not the order they appear: #1 is under
> "Why this cannot mask a real failure" above, #2 is under "`post` was fail-OPEN" below. The table at
> the end of this block lays all three out together — that table, not this correction, is the point.)
> The paragraph above previously read: *"Everywhere else it only tests equality against fixed ints
> (`party != 0`, `in_battle == 2`, `in_battle == 0`), where **a non-int simply fails to match and
> pushes toward a refusal token — already the fail-closed direction** … **Widening Gate 0's refusal
> to the whole trace would therefore not buy safety**; it would convert benign non-matches into hard
> refusals on rows the predicate never reads."* **That was false, and measurably so.** In Python
> `False == 0` and `0.0 == 0`, so a `bool` or a `float` does not fail to match — it matches, and it
> matches on the **passing** side.
>
> Measured on the standard success fixture (`tests/test_score_gate0.py::_red()`), mutating **row 0
> only** — index 0, outside the safety span, which on that fixture starts at `battle_idx == 2`:
>
> | row 0 `party` | head `bef7797` | `origin/main` (`322499f`) |
> |---|---|---|
> | `1` (a genuine non-fresh start) | `(False, ['red_not_fresh_party_zero'])` | same |
> | `False` | **`(True, [])`** | same |
> | `0.0` | **`(True, [])`** | same |
> | `"0"` (str — control) | `(False, ['red_not_fresh_party_zero'])` | same |
> | `None` (control) | `(False, ['red_not_fresh_party_zero'])` | same |
>
> A non-int outside the span turns a refusal into a **clean PASS**. That is fail-**OPEN**, and it
> happens at `_red_success`'s very first clause — `if not watches or watches[0].get("party") != 0`,
> `eval/score_gate0.py:47` at `bef7797` — which is the *exact* clause the deleted sentence named.
> The claim is true only for `str` and `None` (rows 4-5); it is exactly backwards for the two types
> `==` treats as equal to `0`. And a whole-trace refusal — EX01's scope, the widening the sentence
> argued against — **does** catch both: the real helper,
> `eval/score_exam_red_badge.py::_malformed_row`, returns `True` on that row for `False`, `0.0` and
> `"0"` alike. So *"widening would not buy safety"* is contradicted by the code as it now stands.
>
> The `in_battle == 0` half has the same shape. Mutating **every** `in_battle == 0` → `False` on the
> same fixture: `origin/main` returns **`(True, [])`**, a clean PASS, and this head returns
> `(False, ['red_missing_player_hp_oracle', 'red_no_free_movement_after_exit'])`. The head does fail —
> but via the **span refusal this PR adds**, not because a comparison "failed to match". The stated
> mechanism was doing none of the work at either site.
>
> **Scope, stated plainly so this is not over-read.** Pre-existing on `origin/main` (column 3 is
> identical throughout), unreachable from any real capture (every Gate 0 Red `watch` producer
> `int()`-casts — see the table under NEW-1), and **this PR changes none of it**. It is **not a
> regression, not a blocker, and not grounds to move the predicate post-freeze.** What changes is only
> the *justification*: the reason not to widen is **out of scope, unreachable, pre-existing on both
> branches** — all three true — and **not** a fail-closed property the code does not have.

> **THE PATTERN, which is the finding worth more than the correction.** This is the **third** false
> safety argument in this PR. Commit attribution below was re-derived with `git grep` over every
> commit in `origin/main..bef7797`, not recalled:
>
> | # | the false safety claim | first written in | corrected in | why it was false |
> |---|---|---|---|---|
> | 1 | the widened filter is safe because the call site sits *after* `party_idx` proved a `0→1` transition, so every genuine row has `party >= 1` | `eff5746` — the original widening | `24e27f2` (review Major 2) | true at Gate 0's call site, **false** at EX01's, which filters the whole list *before* `party_idx` exists — and whose `parties[0] != 0` guard *requires* the opposite |
> | 2 | a kept malformed row is already fail-closed in the safety span, because it *"hits the `hi`/`lo` `isinstance` checks and raises `red_missing_player_hp_oracle`"* | `24e27f2` — **the very commit that corrected #1** | `794ee37` (re-review NEW-1) | true for 2 of the 8 watched fields; for the other six the span instead emitted two *substantive* claims from a row it had explicitly declined to type |
> | 3 | outside the span *"a non-int simply fails to match and pushes toward a refusal token"*, so widening *"would not buy safety"* | `5e37385` — **the same fix round that corrected #2** | here (round 4 Major) | `False == 0` and `0.0 == 0`; it is fail-**OPEN** at `_red_success`'s first clause, and widening *would* close it |
>
> So #2 and #3 were each authored *inside the round that fixed the one before*; only #1 shipped with
> the original change. **Two of the three survived multiple adversarial reviews** before anyone
> executed them — #1 through a full round, #2 *inherited* from the previous round's text rather than
> invented fresh, and wrong both times. That is the part that matters: review-by-reading did not catch
> any of the three, and review-by-reading is what this project mostly does.
>
> The shape is identical in all three, and it is not carelessness. Each was **derived from the code's
> structure by reading it**, each was locally plausible, and each was **stated as a universal over a
> domain the author had only checked one point of**. #1 generalised from one call site to two. #2
> generalised from two watched fields to eight. #3 generalised from `str`/`None`, where it is true, to
> `bool`/`float`, where the language says otherwise. In every case the *true* version was narrower and
> would have been enough.
>
> **The rule this buys, for whoever writes the next safety argument in this file.** A sentence of the
> form *"X is safe because Y"* is not finished until Y has been **executed over the whole domain it
> quantifies over** — every call site, every watched field, every type that can inhabit the slot,
> *including the ones `==` treats as equal to the value being tested for*. Until then, write the weaker
> sentence. In all three cases here the weaker sentence was available, true, and sufficient: **out of
> scope, unreachable, pre-existing on both branches.** A weaker true claim costs this document
> nothing. An argument-shaped false one costs it the next session, which cites the paragraph instead
> of re-measuring — which is precisely how #2 got inherited across rounds. And note the failure mode
> this PR has now demonstrated **twice in a row**: **the text written to fix a false safety argument
> is where the next one appears.** Treat a correction block as the highest-risk paragraph in the
> file, not the safest.

So: one helper, three call sites, **three different dispositions** (EX01 whole-list refuse, Gate 0
span refuse, Gate 0 `post` drop), each chosen by which direction is fail-closed at that site. That is
the property to check when reading these two scorers side by side — not a symmetry that isn't there.

### `post` was fail-OPEN — the type guard, corrected (PR #191 review Major 1)

The first draft claimed the widened form is "strictly more fail-closed on malformed input than the
`w.get(k) == 0` form it replaces, which accepted `False` as `0`". **That was false**, and it was
false in the direction that matters. `_is_corrupt_glitch_row` *keeps* a row carrying any bool/non-int
field. It was fail-**OPEN** at
`_red_success`'s `post` clause, which had **no type validation at all** — it gated only on
`is not None`. `origin/main` filtered those rows incidentally (`0.0 == 0`, `False == 0`); the
equality-free predicate does not, so a kept malformed row donated its `(x, y)` and manufactured the
second distinct position that satisfies `red_no_free_movement_after_exit`.

> **CORRECTION #2, on the correction (PR #191 re-review NEW-1).** The fix round's replacement text
> here, and the matching comment in `eval/score_gate0.py`, added that the same kept row is
> *"fail-closed at `score_gate0.py`'s safety span (the kept row hits the `hi`/`lo` `isinstance`
> checks and raises `red_missing_player_hp_oracle`)"*. **That was true for 2 of the 8 watched
> fields.** For the other six the mistyped field is not `hi`/`lo`, the row's plain-int
> `party_hp_hi == party_hp_lo == 0` sailed past those checks, and `map` was compared with **no type
> check at all** — so the span emitted the substantive claims **`red_player_hp_reached_zero` AND
> `red_map_changed_during_battle_exit_span`** from a row whose type the predicate had *explicitly
> declined to establish*. That is not "fail-closed", it is a different failure mode wearing a
> reassuring name — **the same defect class as Major 2 (a safety sentence true at one site and false
> at the others), sitting inside the block written to fix Major 2.** The re-review notes it seeded
> this claim in round 1 and that it was wrong then too; it was inherited rather than invented here,
> and that does not make it less load-bearing.
>
> Reproduced — all-zero row with ONE field mistyped, inserted **inside** the safety span of the
> standard success fixture (`battle_idx=2`, `exit_idx=3`, span `2..12`), 24 cases:
>
> | mistyped field | value | `origin/main` | `24e27f2` | fixed |
> |---|---|---|---|---|
> | `x`,`y`,`map`,`party`,`badges`,`in_battle` | `0.0` / `False` | **PASS** | `['red_map_changed_during_battle_exit_span', 'red_player_hp_reached_zero']` | `['red_missing_player_hp_oracle']` |
> | `party_hp_hi`, `party_hp_lo` | `0.0` / `False` | **PASS** | `['red_missing_player_hp_oracle']` | `['red_missing_player_hp_oracle']` |
> | `x`,`y`,`map`,`party`,`badges` | `"0"` | `['red_map_changed…', 'red_player_hp_reached_zero']` | same | `['red_missing_player_hp_oracle']` |
>
> **Fixed by refusing, NOT by dropping, and not by rewording.** Fail-closed points the *opposite* way
> at the two sites, which is precisely what the wrong sentence obscured:
>
> - At **`post`**, the clause fails for having too *few* distinct positions, so removing a row can
>   only ever *cause* `red_no_free_movement_after_exit`. **Dropping is fail-closed.**
> - At the **safety span**, all three clauses only ever *add* a failure, so removing a row can only
>   ever *suppress* one — dropping an untypeable row would silently erase a real HP=0 or a real map
>   change riding on it, which is exactly the PR #121 Major 1 hazard. **Dropping is fail-OPEN;
>   refusing is fail-closed.**
>
> The token is **`red_missing_player_hp_oracle`** — the span's existing *refusal* clause (prereg §5.4
> **C6**), meaning "this span's oracle row is not a readable RAM sample". It is deliberately not a new
> name: the frozen prereg's clause list must not grow, and C6 already carries exactly this "refuse
> rather than guess" semantics for this span. A refusal is honest about what the scorer knows; a
> death claim is not.
>
> Direction and reach, stated plainly: on these inputs `origin/main` **PASSes** (it drops the row
> incidentally under `== 0`) and this head now **refuses**, so this is a **false-FAIL-direction**
> difference, on input **no Gate 0 Red `watch` producer can emit**. It is inert on everything
> reachable — see the differential-fuzz row below.
>
> **Scoping widened (third review).** This claim was previously written as "on input
> `core/perception_plugin.py::_log_oracle` cannot emit" — which scopes it to the **agent** path only.
> That is the wrong path to scope it to. The question a refusal has to answer is *"can it reject a
> genuine success?"*, and the genuine successes are written by the **human baseline**:
> `tools/capture_gate0_baseline_red.py` produced the one genuine PASS trace
> (`gate0_red_human_attempt2_completion.jsonl`, `_red_success` → `(True, [])`) and is what David
> re-runs to capture the v2 baseline. The claim is in fact **stronger** than it was written, and now
> covers every producer **that can write a Pokémon Red Gate 0 oracle row** — verified by reading all
> three:
>
> | producer | role | cast |
> |---|---|---|
> | `core/perception_plugin.py::_log_oracle` | agent | `int(self.emu.read(ad))` |
> | `tools/capture_gate0_baseline_red.py::run.read_watch` | **human baseline** | `int(rd(addr))` |
> | `record.py::main.record` | offline recorder | `int(pb.memory[ad])` |
>
> **The property that holds across all three: every watched value is produced by `int()`, and `int()`
> returns exactly `int` — never `bool`, `float` or `str`.** So no producer *on this path* can emit a
> value `_malformed_row` rejects, and neither refusal (Gate 0's or EX01's) can fire on a genuinely
> captured Red trace, agent or human. `capture_gate0_baseline_red.py` is cited by **symbol only,
> deliberately**: it is under concurrent edit (a `--mode` flag is being added) and any line number
> here would be stale on arrival.
>
> > **SCOPED ON PURPOSE (review round 4, Nit 3) — the unscoped version is false repo-wide.** "All
> > three writers of a `watch` row" is **not** a true statement about this repository. At least three
> > further writers exist and **none** of them casts:
> > `reports/probes/2026-07-25-gba-exam/gba_drive.py`,
> > `reports/probes/2026-07-28-emerald-oldale-oracle/edrive.py` and
> > `reports/probes/2026-07-28-kirby-gba-level-oracle/kgba_drive.py` all build `rec["watch"]` from an
> > uncast `read_width(emu, addr, width)`, whose `u8` branch is a bare `emu.read(addr)`. A seventh,
> > `record.py`'s `meta.json` writer, emits a `watch` map of **address strings** (`f"0x{ad:04X}"`) —
> > not an oracle row at all. The three probe drivers are **GBA-only** and cannot produce a Game Boy
> > Pokémon Red trace, so none of them can reach `_red_success` or `_red_badge_success`, and the
> > claim holds at the scope the safety argument actually needs. It is scoped explicitly rather than
> > deleted, because **an unscoped universal that happens to be false is the exact defect class the
> > three corrections in this entry are about** — and stating it unscoped would have made it a
> > fourth.

Reproduced on the standard success fixture with the last row's `x`/`y` left unmoved (so the run
genuinely never moves) and **one** row appended past `exit_idx + 10`, i.e. never touching the safety
span:

| appended row | `origin/main` | first draft | fixed |
|---|---|---|---|
| *(none)* | FAIL | FAIL | FAIL |
| all-zero **ints** | FAIL | FAIL | FAIL |
| all-zero **floats** | FAIL | **PASS** | FAIL |
| one bool (`"party": false`) | FAIL | **PASS** | FAIL |
| all-`false` | FAIL | **PASS** | FAIL |
| all `"0"` strings | **PASS** (pre-existing hole) | **PASS** | FAIL |

`post` is now type-guarded by a `_malformed_row` helper: a row is dropped if **any** watched field is
present but is not a plain int. An `x`/`y`-only type check is **not** sufficient — the
`{"party": false, rest 0}` row has plain-int `x`/`y` and still passes one. Dropping (rather than
appending a new failure token) is the fail-closed direction here: `post` only ever fails for having
too *few* distinct positions, so removing rows can cause `red_no_free_movement_after_exit` but never
suppress it, and no failure name not already in the frozen prereg's clause list is introduced. This
also closes the pre-existing string-`"0"` hole that both branches had.

**Also fixed, and previously unclaimed: `post` could CRASH the scorer on `origin/main`.** The third
review surfaced this and the PR had not claimed it. `origin/main` builds `post` as a list of
`(w.get("x"), w.get("y"))` tuples with no type validation and then calls `len(set(post))` — so an
`x` or `y` that is *unhashable* (a list, a dict) does not produce a wrong verdict, it raises out of
the public entry point:

| input: one post-`exit_idx` row with `"x": [1, 2], "y": [3, 4]` | result |
|---|---|
| `origin/main` | **`TypeError: unhashable type: 'list'`** |
| this head | `(False, ['red_no_free_movement_after_exit'])` |

Measured directly against both revisions of `_red_success`, same trace. The `_plain_int` guard filters
the row before the tuple ever reaches `set()`, so the head returns a verdict where `origin/main`
returned a stack trace. This is the **same defect class D1 fixed** at `score_manifest`'s oracle read —
handing the operator a traceback where a verdict belongs, which is precisely the misdiagnosis
`.claude/skills/diagnose-a-run` exists to prevent — and it is closed here as a side effect of the type
guard rather than by a new `except`.

**Honest scoping.** All of this needs a malformed watch value, and **no producer that can write a
Pokémon Red Gate 0 oracle row** emits one: all three cast with `int()`
(`core/perception_plugin.py::_log_oracle`, `tools/capture_gate0_baseline_red.py::run.read_watch`,
`record.py::main.record` — see the widened scoping note in the NEW-1 block above, including why that
sentence is scoped to the Red path and false without the scope). So none of it is reachable from a
well-formed run today. It matters
because this scorer's stated premise is tamper/corruption resistance, `post` was the only Red
capability clause with zero type validation, and the first draft of this entry asserted the opposite
property.

### Proof that no bar moved

Everything outside `_red_success` is byte-identical to `origin/main` (`322499f`), LF-canonical:

| region of `eval/score_gate0.py` | `origin/main` | PR head | |
|---|---|---|---|
| lines 1–43 (above `_red_success`) | `984a6d95a34edc519890494b047f3a52c931180755e17101a9451993e7d28c9e` | identical | ✅ |
| `_miniwob_success` → EOF | `cd8d19a6b5c791b420fa190e6f7a8ce498bfdd0933beea1c85a9f5139f69d493` | identical | ✅ |

Reproduce (LF-canonical, split at the `def _red_success` / `def _miniwob_success` lines):

```sh
git show origin/main:eval/score_gate0.py | tr -d '\r' | sed -n '1,43p'    | sha256sum
sed -n '1,43p'  eval/score_gate0.py      | tr -d '\r' | sha256sum
git show origin/main:eval/score_gate0.py | tr -d '\r' | sed -n '102,$ p'  | sha256sum
sed -n '225,$ p' eval/score_gate0.py     | tr -d '\r' | sha256sum
```

(`102` and `225` are the `def _miniwob_success` lines on `origin/main` and on this head; `44` is
`def _red_success` on both. The un-hashed middle is `_red_success` plus its two blank separator lines
and nothing else, so the two digests cover the whole file between them. Both digests re-derived
unchanged after each PR #191 fix round; every round only grew `_red_success`, so the head split line
has moved `126` → `167` → `209` → `225` while both digests stayed put. **Re-derive this split line by
locating `def _miniwob_success`, never by reusing the number** — it has moved three times within this
PR, four counting `origin/main`'s `102`; see the line-number convention note above.)

So `MODES`, `SOURCE_PIN_FILES`, `MINIWOB_TASK`, `AUDIT_PATH_KEYS`, `_miniwob_success`,
`_arm_metrics`, `_verify_audit_paths`, `_verify_sources`, the arm caps, and the leak → constancy →
infra → source → capability precedence chain are all provably unmoved.

`score_manifest()` verdicts, same on-disk state scored before and after (sha256 of the sorted-JSON
verdict), re-derived 2026-07-28 after the PR #191 review fixes:

| mode | `origin/main` | this head | `readiness` | |
|---|---|---|---|---|
| `paid_gate0` (banked v1 artifacts) | `ca1768bca23617563f8d30f06a97162f487dd60edad54a07243de965bbda7424` | identical | `NO_GO` | ✅ |
| `readiness_dev` | `2286dde5c4ccf332e9980dc3580a3e23f8aa4aabebcdafdb27a00f88f4007cdd` | identical | `NO_GO` | ✅ |
| `paid_gate0_v2` | `20d35b8ca46d4aafd88edfce435dbd61401ddceea6c17fd7287bca238fbaf86e` | identical | `INSUFFICIENT_SOURCE` | ✅ |

**Re-verified after the re-review fix round**, this time three-way — `origin/main` vs `24e27f2` vs
this head — on one machine, same on-disk state: **all three modes identical across all three
revisions.** The absolute digests from that re-run differ from the table above and are NOT
substituted in, because it was run with `ROOT` repointed at a checkout whose `runs/**` tree is not in
the same state; that is the environment-dependence the next paragraph is about, and it is why the
equality column is the load-bearing one. The claim that does not depend on any of this is the
per-trace table below, `_red_success` and EX01 run **directly** on the banked oracle rows.

**How to reproduce, and what is *not* reproducible from the repo alone (PR #191 review Nit 7).** The
first draft quoted three digests with no recipe at all; these replace them. The manifest is built
entirely from the frozen pin file's own `audit_paths` — nothing invented, and the only construction
`_verify_audit_paths` accepts:

```python
pins = json.load(open(f"eval/fixtures/{PINFILE[mode]}.json"))
keys = ("transcript", "receipt", "expected_pins", "artifacts_dir", "peer_receipt")
manifest = {"mode": mode, "arms": {arm: {"codex_audit": {k: pins["audit_paths"][arm][k] for k in keys},
                                         "oracle": pins["audit_paths"][arm]["oracle"]}
                                   for arm in ("red", "miniwob")}}
# write to any path; score_manifest() resolves the pinned relative paths against eval/score_gate0.py's ROOT
digest = sha256(json.dumps(score_manifest(path), sort_keys=True).encode()).hexdigest()
```

The absolute digests are **environment-dependent and not reviewer-reproducible**, and this is not
fixable by committing a fixture: `paid_gate0`'s pinned inputs live under `runs/gate0_paid/**`, which
is gitignored, so only a machine holding the banked artifacts can produce that row. What *is*
reproducible anywhere, and what the claim actually needs, is the **`origin/main` == head** column —
the recipe above run against both branches on one machine, which is how the table was produced. The
`paid_gate0` row does genuinely reach the changed code: its red capability failure is
`red:red_no_sustained_battle_exit`, i.e. `_red_success` ran on the banked 438-row oracle. The other
two modes have no run artifacts on disk at all (`runs/gate0_readiness_dev/` and `runs/gate0_paid_v2/`
do not exist), so their rows only pin that nothing *else* moved.

**Confirmed by the third review, and worth naming precisely: `readiness_dev` and `paid_gate0_v2`
reproduced exactly from a clean worktree; `paid_gate0` did not.** That is the expected result, and
the reason is now pinned down rather than left as "environment-dependent":

> **Running the root suite inside a git worktree CREATES `runs/gate0_paid/wake_boundary.json` in that
> worktree, and that alone changes the `paid_gate0` digest.**

`tools/gate0_appserver_arm.py::_finalize_real_run` writes
`REPO_ROOT / "runs" / "gate0_paid" / "wake_boundary.json"` (`ensure_wake_boundary_artifact`), and
`REPO_ROOT` is `Path(__file__).resolve().parent.parent` — i.e. **the worktree root**, not the primary
checkout. The two tests that exercise it
(`tests/test_gate0_appserver_arm.py::test_finalize_real_run_writes_metrics_and_receipt_even_on_signature_mismatch`
and `::test_finalize_real_run_success_path_still_resolves_pins_and_scores`) pass a `tmp_path`
`out_dir`, but *this one path is REPO_ROOT-relative and escapes the tmp_path sandbox*. Observed
directly: a worktree that never received any banked data ends up with `runs/gate0_paid/` containing
exactly one file, `wake_boundary.json`, byte-identical to the primary checkout's
(`9cddf29c4d8c778a71ee9517fe7d9393e7cf2d62a638f78c369a257c4b37b094`).

The digest moves because the file's mere presence flips which token `_verify_sources` emits — the
`paid_gate0` pin for this artifact is the literal placeholder
`PENDING_NOT_YET_CAPTURED_wake_accounting_not_built`, so a present file can only ever mismatch it:

| `runs/gate0_paid/wake_boundary.json` | token in `failures.source` |
|---|---|
| absent (clean worktree) | `source_unreadable:wake_boundary` |
| present (after a root-suite run) | `source_hash:wake_boundary` |

Measured, not inferred — and **re-measured for review round 4, because two figures in the previous
draft were wrong.** The conditions matter more than the numbers here, so they are stated first: a
**clean git worktree at this head (`bef7797`)**, one that has never received banked data, so `runs/`
is absent entirely; `paid_gate0` mode via the recipe above; scored **before** and **after** a single
`uv run --frozen pytest -q` on the root suite. That suite run is the *only* difference between the
two columns. It creates `runs/gate0_paid/wake_boundary.json`
(sha256 `9cddf29c4d8c778a71ee9517fe7d9393e7cf2d62a638f78c369a257c4b37b094`, byte-identical to the
primary checkout's) and writes nothing else anywhere under `runs/`.

| `paid_gate0`, clean worktree at `bef7797` | before the suite run | after the suite run |
|---|---|---|
| `runs/gate0_paid/wake_boundary.json` | absent | present |
| token in `failures["source"]` | `source_unreadable:wake_boundary` | `source_hash:wake_boundary` |
| `readiness` | **`NO_GO`** | **`NO_GO`** |
| `overall` | `NO_LEAK` | `NO_LEAK` |
| `failures` | constancy 2, leak 4, infra 0, **capability 8**, cheap 0, source 23 — **37 total** | *identical, all six buckets* |
| verdict sha256 | `2286dde5c4ccf332e9980dc3580a3e23f8aa4aabebcdafdb27a00f88f4007cdd` | `9c7f1d8a26273abbedfa7ef1067ffa2a4b001368a179bac7efc3a6eae89ba5c7` |

**Readiness, `overall`, and the entire failure vector are identical across the flip; only that one
source token — and therefore the hex — moves.** The previous draft supported the same conclusion with
two wrong numbers: it said *"`readiness` is `INSUFFICIENT_SOURCE` in both cases and the failure count
is 8 in both"*. `INSUFFICIENT_SOURCE` is **`paid_gate0_v2`'s** readiness in this very measurement, not
`paid_gate0`'s (which is `NO_GO`, matching its row in the digest table above); and `8` is the
**capability** bucket, not any total — the total is 37. The conclusion is untouched, which is exactly
why the `origin/main` == head **equality** column is the load-bearing one and the absolute hex is not.

Two datapoints from the same measurement, both bounding what a reviewer can check from the repo alone:

- In that clean worktree, `paid_gate0` and `readiness_dev` produce the **identical** verdict digest
  `2286dde5c4ccf332e9980dc3580a3e23f8aa4aabebcdafdb27a00f88f4007cdd` — with no banked artifacts on
  disk, `paid_gate0` degenerates exactly onto the `readiness_dev` row of the table above. That is the
  precise reason the `paid_gate0` row is not reviewer-reproducible while the other two are.
- Scored against the **real banked artifacts** (`ROOT` repointed at the primary checkout's `runs/`,
  this head's frozen `eval/fixtures/` otherwise unchanged), `paid_gate0` is a different verdict
  altogether — `readiness NO_GO`, `overall CONSTANCY_BREACH`, constancy 12 / leak 0 / infra 0 /
  capability 4 / cheap 0 / source 19 — and `wake_boundary.json`'s presence flips the same single
  token there too, with readiness, `overall` and the whole failure vector again unmoved. So the "no
  bar moves" conclusion holds in **both** environments; only the figures quoted for it are
  environment-specific, and the ones tabulated above are the clean-worktree ones.

*Operational consequence:* run the root suite in a worktree, not in the primary checkout, and do not
compare a `paid_gate0` absolute digest across machines or across a suite run. `runs/` is read-only
banked data; this stray write is a test-created artifact, not evidence.

Per-trace predicate outputs on **every** committed Red trace:

| trace | `_red_success` before → after | EX01 before → after |
|---|---|---|
| `gate0_red_human_attempt1_no_movement.jsonl` (900 rows) | `(False, ['red_no_free_movement_after_exit'])` → identical | `red_badge_never_earned` → identical |
| `gate0_red_human_attempt2_completion.jsonl` (900 rows) | `(True, [])` → identical | `red_badge_flip_not_after_battle` → **`red_badge_never_earned`** |
| `reports/2026-07-24-gate0-armR-verdict/oracle.jsonl` (438 rows) | `(False, ['red_no_sustained_battle_exit'])` → identical | `red_badge_flip_not_after_battle` → **`red_badge_never_earned`** |
| `runs/gate0_paid/red/world/oracle.jsonl` (banked paid Arm R, 438 rows, read-only) | `(False, ['red_no_sustained_battle_exit'])` → identical | `red_badge_flip_not_after_battle` → **`red_badge_never_earned`** |

EX01 `overall` is `FAIL_CAPABILITY` on all four traces on **both** branches — the two changes are
*failure-reason* corrections only.

**`_red_success` is unmoved on every banked trace.** The two EX01 changes are *failure-reason*
corrections; `overall` stays `FAIL_CAPABILITY` in both cases. **No verdict anywhere flips.** The
banked v1 `paid_gate0` `CONSTANCY_BREACH` stands, and this does not un-void it.

Root suite, from the repo root, both measured here: **1676 passed / 18 skipped** on `origin/main` →
**1688 passed / 18 skipped** here (+12 = four tests built from the literal banked rows, none
hand-invented; four for the PR #191 review Minor 4 gap — the `post` clause and the type guard had
zero coverage; and four for the re-review, two per finding, covering NEW-1's safety-span refusal and
NEW-2's mistyped residue row, each paired with an over-fire test in the opposite direction).

### Differential fuzz — the re-review fix round is inert on reachable input

The re-review measured this PR against a ground-truth oracle (ground truth = the verdict on the base
trace with the injected artifact rows removed). The NEW-1/NEW-2 fixes were re-measured the same way,
three-way, so the question "did fixing the findings cost anything?" has a number rather than an
argument.

**Input policy**, since that is the standing rule here: base traces are structurally valid Red runs
(fresh → starter → `in_battle == 2` → sustained exit → optional movement / faint / map change /
badge). Arm A is 20 000 clean traces, no artifact rows. Arm B is 60 000 traces poisoned with 1–3
well-formed artifact rows at random positions — the residue shape
`{x == y == map == badges == k, party == in_battle == hp_hi == hp_lo == 0}` for `k` in 0..7 (`k == 0`
is the all-zero row), i.e. everything any `watch` producer can emit under a wrong-bank sample. **Every value
is a plain int; no malformed value appears anywhere**, which is exactly why the fixes cannot show up
here.

| | new false PASS | new false FAIL | fixes a `main` false PASS | fixes a `main` false FAIL |
|---|---|---|---|---|
| `_red_success` | **0** | **0** | 1 369 | 21 666 |
| `_red_badge_success` | **0** | **0** | 865 | 14 218 |

- Arm A: `origin/main`, `24e27f2` and this head agree **20 000 / 20 000** on both predicates.
- Arm B: **`24e27f2` and this head disagree 0 times in 120 000 poisoned scorer-evaluations.** The
  NEW-1 and NEW-2 fixes are *exactly* inert on the reachable input domain — they are unreachable by
  construction, since both trigger only on a value that is not a plain int.
- The absolute counts differ from the re-review's (which reported 1 873 / 20 390 fixed) because the
  trace generators differ; the columns that carry the claim are the two zeros and the 0 disagreements.

### What this does NOT fix

> **CORRECTED (PR #191 re-review §4).** This section previously named `cgb=False` as the root fix:
> *"Constructing with `cgb=False` (DMG mode) makes `0xD000-0xDFFF` unbanked and SVBK inert,
> eliminating the artifact at source — no scorer filter needed."* **`cgb=False` is not a fix, because
> it does not run this ROM at all.** The decisive evidence is the header byte, not a measurement:
> `0x143` is `0xC0` = **CGB-ONLY**, and a non-CGB machine refuses such a cartridge by specification.
> The ROM's own nature was the missing premise — see the correction in "The mechanism, established"
> above: this is a CGB colorization romhack, so "make it a DMG machine" was never available.
>
> The corroborating measurement, **with its input policy attached**: cold boot from ROM reset (no
> savestate), **zero input**, 20 000 frames advanced one at a time, `window="null"`, PC sampled
> **once per frame at the frame boundary** via `pyboy.register_file.PC` and collected into a set —
> **73 distinct PCs under `cgb=False` vs 559 with no `cgb=` argument.** 73 distinct PCs over 20 000
> frames is a spin loop, i.e. a hard lock. Measured here; reproduces the PR #191 re-reviewer's scan
> exactly on both numbers.
>
> ⚠ **Do not quote a bare PC count.** A *separate* investigation measured the same `cgb=False`
> quantity as **31** — ~2.4x off the 73 above. The figures are not comparable and neither is wrong:
> a once-per-frame PC sample is a function of **sampling cadence and input policy**, not of how much
> code executed (20 000 samples against billions of instructions), and a zero-input CGB-mode figure
> is an attract-loop-only number that would be far higher with input. Every run shows the same hard
> lock and the conclusion is unaffected. **The `0xC0` header byte is the claim that depends on none
> of this, and it is the one to rely on.** This is the second figure in this document to need its
> input policy supplied after the fact; see the standing rule under "Corrected figures".

The **root cause is on the read side, not in the scorer.** `core/perception_plugin.py::_log_oracle`
reads the eight watch addresses with an **unbanked** `memory[addr]`, while `0xD000-0xDFFF` is
bank-switched in CGB mode — so whichever bank the ROM has selected at sample time is what comes back.

**The actual root fix is a bank-correct read: `memory[1, addr]` for `0xD000-0xDFFF`, guarded on CGB
mode.** Measured against truth on the cold-boot scan (60 000 frames, zero input, no `cgb=` argument):
it equalled truth on **785/785** stomped ticks, including all **410** diverging ones. That is a total
fix at source, and it needs its own plan and its own PR — it touches the world (`world_mcp.py` /
`core/perception_plugin.py`), which means an image rebuild and a re-pin.

**The disposition of this filter has therefore changed.** It is no longer a stopgap awaiting a
one-line emulator flag — that flag does not exist. **Until a bank-correct oracle read lands, this
filter is the only mitigation for the artifact**, on both `_red_success` and EX01. That is why the
re-review's NEW-1 was worth fixing *before* merge rather than after.

Even so, the scorer-side signature remains a **residue-shape filter, not a law**: it matched
**657/657** diverging ticks across the two reproduction scans above (each with its input policy
stated there), but the corrupt values are whatever the alternate bank happens to hold, and a bank
dirtied differently could in principle produce a shape this predicate does not match. It is strictly
better than the all-zero-only form (which matched **5/657**) and strictly safer than no filter — it
is not a proof that the artifact can never leak through. **C8's advice to check the raw rows behind
any Red failure therefore remains good practice and is not retired by this change.**


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

