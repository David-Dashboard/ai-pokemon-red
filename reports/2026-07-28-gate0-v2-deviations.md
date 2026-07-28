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

## D2 — the Red corruption predicate was widened after the freeze (all-zero-only → full wrong-WRAM-bank signature)

**Landed by:** PR on branch `fix/red-glitch-row-signature`.
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

Offline reproduction (`roms/PokemonRed.gb`, PyBoy 2.7.0, no paid run, no network):

| scan | frames | SVBK not in {0,1} | diverged from truth | distinct corrupt tuples |
|---|---|---|---|---|
| fresh boot, seed 7 | 200 000 | 1003 | 1003 | all-zero x599, `{x/y/map/badges=1, rest=0}` x403, `{...=3, rest=0}` x1 |
| `runs/run9_end.state` (mid trainer battle), seed 3 | 150 000 | 358 | **358 / 358** | all-zero x279, `{...=1, rest=0}` x79 |

**~1800 corrupt samples produced this signature and no other shape.** The alternate bank holds only
residue: `party`/`in_battle`/HP read 0, and the four `0xD3xx` fields all read one repeated residue
byte. All-zero is the *clean-bank* case — i.e. **the predicate that was already there was this same
signature with an untouched bank.** Widening it completes that predicate rather than inventing one.

Two of the 150 000-frame scan's divergent samples occurred while the true row read `in_battle == 2`,
i.e. **inside a live trainer battle** — the span C8 scans.

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
- It requires **`party == 0`**. Every call site consults it only *after* an exact `party` 0→1
  transition has been established (`party_idx` in `_red_success`; the identical corroboration in
  `_red_badge_success`). So every **genuine** row in scope has `party >= 1`, and a genuine faint, a
  genuine map change and a genuine badge are all **unreachable by this filter by construction** — a
  real Pokémon must exist to faint, and a badge cannot be held with an empty party.
- It requires `in_battle == 0`, so it can never drop a real in-battle row.
- Any non-`int` (or `bool`) field keeps the row — the widened form is strictly more fail-closed on
  malformed input than the `w.get(k) == 0` form it replaces, which accepted `False` as `0`.
- Both existing PR #121 regression tests (`test_red_corrupted_party_byte_does_not_mask_a_real_death`,
  `..._a_real_map_change`) pass unchanged, and a new test re-proves the property against the widened
  predicate specifically.

### Proof that no bar moved

Everything outside `_red_success` is byte-identical to `origin/main` (`322499f`), LF-canonical:

| region of `eval/score_gate0.py` | `origin/main` | PR head | |
|---|---|---|---|
| lines 1–43 (above `_red_success`) | `984a6d95a34edc519890494b047f3a52c931180755e17101a9451993e7d28c9e` | identical | ✅ |
| `_miniwob_success` → EOF | `cd8d19a6b5c791b420fa190e6f7a8ce498bfdd0933beea1c85a9f5139f69d493` | identical | ✅ |

Reproduce (LF-canonical, split at the `def _red_success` / `def _miniwob_success` lines):

```sh
git show origin/main:eval/score_gate0.py | tr -d '\r' | sed -n '1,43p'   | sha256sum
sed -n '1,43p' eval/score_gate0.py       | tr -d '\r' | sha256sum
git show origin/main:eval/score_gate0.py | tr -d '\r' | sed -n '102,$p'  | sha256sum
sed -n '126,$p' eval/score_gate0.py      | tr -d '\r' | sha256sum
```

So `MODES`, `SOURCE_PIN_FILES`, `MINIWOB_TASK`, `AUDIT_PATH_KEYS`, `_miniwob_success`,
`_arm_metrics`, `_verify_audit_paths`, `_verify_sources`, the arm caps, and the leak → constancy →
infra → source → capability precedence chain are all provably unmoved.

`score_manifest()` verdicts, same on-disk state scored before and after (sha256 of the sorted-JSON
verdict):

| mode | before | after | |
|---|---|---|---|
| `paid_gate0` (banked v1 artifacts) | `462b88479caf4d80d587b8032b8f9ba7727292716d907afcd8deae6a0833023b` | identical | ✅ |
| `readiness_dev` | `6458a29f53e16790a3b7e49d9cb106e92a6e56d192ceb22754f67c827a4cefd3` | identical | ✅ |
| `paid_gate0_v2` | `b4b40fc41185b62b537b7f99d5d475c531f64907d0801cbab472dadcdfeb4e68` | identical | ✅ |

Per-trace predicate outputs on **every** committed Red trace:

| trace | `_red_success` before → after | EX01 before → after |
|---|---|---|
| `gate0_red_human_attempt1_no_movement.jsonl` | `(False, ['red_no_free_movement_after_exit'])` → identical | `red_badge_never_earned` → identical |
| `gate0_red_human_attempt2_completion.jsonl` | `(True, [])` → identical | `red_badge_flip_not_after_battle` → **`red_badge_never_earned`** |
| `reports/2026-07-24-gate0-armR-verdict/oracle.jsonl` | `(False, ['red_no_sustained_battle_exit'])` → identical | `red_badge_flip_not_after_battle` → **`red_badge_never_earned`** |

**`_red_success` is unmoved on every banked trace.** The two EX01 changes are *failure-reason*
corrections; `overall` stays `FAIL_CAPABILITY` in both cases. **No verdict anywhere flips.** The
banked v1 `paid_gate0` `CONSTANCY_BREACH` stands, and this does not un-void it.

Root suite: **1676 passed / 18 skipped** before → **1680 passed / 18 skipped** after (+4 = the four
new tests, all built from the literal banked rows, none hand-invented).

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
