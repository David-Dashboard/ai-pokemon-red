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

## D3 — the Red corruption predicate was widened after the freeze (all-zero-only → full wrong-WRAM-bank signature)

**Numbering:** this entry was drafted as `D2`. PR #188 (`fix/audit-verdict-not-gate-verdict`, commit
`7d6b2ee`) was written first, is further along, and also lands a `D2` in this file. Renumbered to
`D3` here to avoid a collision on merge; nothing else about the entry changed with the renumber.

**Landed by:** PR #191 on branch `fix/red-glitch-row-signature`.
**Touches:** `eval/score_gate0.py::_red_success::_is_corrupt_glitch_row` and its mirror in
`eval/score_exam_red_badge.py` (EX01), plus four tests. No fixture, no pin, no other predicate.

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

`roms/PokemonRed.gb` carries CGB flag **`0xC0`** at header offset `0x143`, so PyBoy runs it in **CGB
mode**, where `0xD000-0xDFFF` is WRAM-bank-switched by **SVBK (`0xFF70`)**. Pokémon Red is DMG code
and never manages SVBK, but transiently stomps it (values 2–7 observed live). **Every** watched
address — `0xD057`, `0xD163`, `0xD16C`, `0xD16D`, `0xD356`, `0xD35E`, `0xD361`, `0xD362`
(`world_mcp.py` `GAMES["pokemon_red"]["watch"]`) — lies inside that banked window, and
`core/perception_plugin.py::_log_oracle` builds the whole watch dict in one comprehension against
one emulator state. So a stomped tick reads **all eight fields out of the wrong WRAM bank at once**,
and the next sample is back on bank 1 — exactly the "sandwiched between identical, consistent
neighbor rows" shape the original PR #121 comment described.

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
ticks, because an idle game never stomps SVBK. The two rows above are what actually reproduces. Both
were measured twice: the cold-boot row matches the PR #191 reviewer's independent scan **exactly**
(785 / 410 / same SVBK histogram / same single tuple), and the reviewer's read of *why* it is 52% not
100% is right — a cold-boot prefix exists where the alternate bank happens to equal truth.

**What the predicate actually needs is the second column, not the first:** not "every stomped tick
diverges" but **"every *diverging* tick produces this signature"** — 410/410 and 247/247, i.e. 657/657
across both scans, with **two** distinct shapes total and both of them matched. The alternate bank
holds only residue: `party`/`in_battle`/HP read 0, and the four `0xD3xx` fields all read one repeated
residue byte. All-zero is the *clean-bank* case — i.e. **the predicate that was already there was this
same signature with an untouched bank.** Widening it completes that predicate rather than inventing
one. The old predicate matched **5 / 657**.

Two of the mid-battle scan's divergent samples occurred while the true row read `in_battle == 2`,
i.e. **inside a live trainer battle** — the span C8 scans. (That figure reproduces from the first
draft unchanged.)

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

> **CORRECTION (PR #191 review Major 2).** The first draft of this entry argued something different
> and **false**: that "every call site consults it only *after* an exact `party` 0→1 transition has
> been established (`party_idx` in `_red_success`; the identical corroboration in
> `_red_badge_success`)", so every genuine row in scope has `party >= 1`.
>
> That is true in `_red_success` — both call sites are downstream of `exit_idx`, which is downstream
> of `party_idx` — and **false in `_red_badge_success`**, where the load-bearing half of the claim
> was. `eval/score_exam_red_badge.py:76` filters the **entire** watch list; `party_idx` is not
> computed until `:97`, and it is computed **from the already-filtered list**. Worse, `:89`
> positively **requires** `parties[0] == 0`, so the entire pre-starter prefix of every genuine trace
> has `party == 0` by construction — the opposite of what the argument asserted. The claim was not
> merely unproven at that site, it was inverted.
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
`red_badge_bit_reverted_after_set` (`eval/score_exam_red_badge.py:121-122`). A delta row whose
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
implicit: `:120` documents that clause as catching "a savestate reload, a substituted row", i.e. not
only RAM corruption, so a reader is entitled to know the corruption filter now sits in front of it.
Both the PR's boot scan and the reviewer's observed only **odd** residue bytes (`1`, `3`), so a
bit-0-clear residue is untested rather than impossible — if one is ever observed live, this is the
clause to re-examine first.

### `post` was fail-OPEN — the type guard, corrected (PR #191 review Major 1)

The first draft claimed the widened form is "strictly more fail-closed on malformed input than the
`w.get(k) == 0` form it replaces, which accepted `False` as `0`". **That was false**, and it was
false in the direction that matters. `_is_corrupt_glitch_row` *keeps* a row carrying any bool/non-int
field. That is fail-closed at `score_gate0.py`'s safety span (the kept row hits the `hi`/`lo`
`isinstance` checks and raises `red_missing_player_hp_oracle`) and at `score_exam_red_badge.py:76`
(a kept malformed row makes `_badges_bit0` return `None` → hard refusal). It was fail-**OPEN** at
`_red_success`'s `post` clause, which had **no type validation at all** — it gated only on
`is not None`. `origin/main` filtered those rows incidentally (`0.0 == 0`, `False == 0`); the
equality-free predicate does not, so a kept malformed row donated its `(x, y)` and manufactured the
second distinct position that satisfies `red_no_free_movement_after_exit`.

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

**Honest scoping.** This needs a malformed watch value, and `core/perception_plugin.py::_log_oracle`
emits PyBoy ints, so it is not reachable from a well-formed run today. It matters because this
scorer's stated premise is tamper/corruption resistance, `post` was the only Red capability clause
with zero type validation, and the first draft of this entry asserted the opposite property.

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
sed -n '167,$ p' eval/score_gate0.py     | tr -d '\r' | sha256sum
```

(`102` and `167` are the `def _miniwob_success` lines on `origin/main` and on this head; `44` is
`def _red_success` on both. The un-hashed middle is `_red_success` plus its two blank separator lines
and nothing else, so the two digests cover the whole file between them.)

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

Root suite: **1676 passed / 18 skipped** on `origin/main` → **1684 passed / 18 skipped** here (+8 =
four tests built from the literal banked rows, none hand-invented, plus four added for the PR #191
review Minor 4 gap — the `post` clause and the type guard had zero coverage).

### What this does NOT fix

The **root cause is the emulator configuration, not the scorer.** `core/gb_emulator.py` constructs
`PyBoy(rom_path, ...)` with no `cgb` argument, so the CGB-flagged header selects CGB mode and the
banked-WRAM window exists at all. Constructing with `cgb=False` (DMG mode) makes `0xD000-0xDFFF`
unbanked and SVBK inert, eliminating the artifact at source — no scorer filter needed. That was
**not** done here: it is a world change (image rebuild + re-pin), and it **invalidates every
existing savestate** — verified, `PyBoy.load_state` raises
`Loading state which *is* CGB-mode, but PyBoy *is not* in CGB mode!` on `runs/*.state`. It needs its
own plan and its own PR.

Until then the scorer-side signature remains a **residue-shape filter, not a law**: it caught
~1800/1800 reproduced samples, but the corrupt values are whatever the alternate bank happens to
hold, and a bank dirtied differently could in principle produce a shape this predicate does not
match. It is strictly better than the all-zero-only form and strictly safer than no filter — it is
not a proof that the artifact can never leak through. **C8's advice to check the raw rows behind any
Red failure therefore remains good practice and is not retired by this change.**
