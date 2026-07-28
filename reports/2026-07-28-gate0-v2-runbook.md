# Gate 0 v2 — executable runbook, from today's state to a scored verdict

**Written 2026-07-28 against `origin/main` = `322499f`. $0, docs only. This document launches
nothing, merges nothing, and spends nothing.**

This is the operational companion to the **frozen** pre-registration
`reports/2026-07-25-gate0-v2-prereg.md`. It **adds no bar, removes no bar, and reinterprets
nothing**. Where it disagrees with the prereg on a matter of *fact about the tree*, it says so
explicitly and cites both sides; where it disagrees on a matter of *bar or protocol*, the prereg
wins and this document is wrong.

It exists because the prereg's §0 precondition table is a **dependency graph**, not a schedule, and
because four of its "NOT DONE" rows describe a tree that has moved since it was frozen. What follows
is the schedule.

---

## 0. How to read this

**Verification legend.** Every claim below carries one of:

| Tag | Meaning |
|---|---|
| **[V]** | Verified on this machine on 2026-07-28 by running the cited command or reading the cited `file:line`. The command and its output are reproduced. |
| **[UNVERIFIED]** | Not checked here, and why. Treat as a claim to be tested, not a fact. Every one is also listed in §7. |

**Actor legend.** Every step carries one of:

| Tag | Who |
|---|---|
| **[D]** | David only. Cannot be delegated to an agent — either because it is a spend/merge decision, because it is a human-in-the-loop capture, or because the safety law reserves it. |
| **[A]** | Delegable to an implementer agent under the normal `dev-workflow` (plan → own worktree → PR → adversarial review → David merges). |
| **[auto]** | A tool does it; a human only reads the output. |

**Proof legend.** Every step ends with **PROOF:** — a command whose output can be checked, or a file
that must exist and hash to a stated value. A step with no checkable proof is not a step.

**Where commands run.** Unless a step says otherwise, commands run from the **repo root of the tree
that will score**, on the Windows host, in Git Bash or PowerShell. `eval/score_gate0.py` resolves
every pinned relative path against `ROOT = Path(__file__).resolve().parents[1]`
(`eval/score_gate0.py:12`) — the repo root of *the checkout running the scorer*, **not** the
manifest's directory. Scoring from a worktree without `runs/` therefore reports
`source_unreadable:*` for artifacts that exist perfectly well in the primary checkout. **[V]** —
observed exactly this, §4 Phase 2.

**`runs/` is append-only source of truth.** Two steps in this runbook write into it. Both are
flagged **⚠ WRITES TO `runs/`** and both require David's explicit OK at the moment of execution.

---

## 1. Verified starting state — 2026-07-28

Each row was checked here. Do not trust the prereg's §0 table for these; it was frozen earlier the
same day and four of its rows have been overtaken.

### 1.1 Repository

| Fact | Value | How verified |
|---|---|---|
| `origin/main` | `322499f35238fa9a51682ba8edae8217dfd292b6` | **[V]** `git rev-parse origin/main` |
| Full test suite at `322499f` | **1676 passed, 18 skipped** in 68.89 s | **[V]** `uv run --frozen python -m pytest -q` |
| **⚠ The primary checkout is NOT on `main`** | branch `fix/miniwob-key-name-press`, HEAD `818c592` | **[V]** `git -C E:/.../ai-pokemon-red rev-parse --abbrev-ref HEAD` |

That last row is load-bearing and is the cheapest abort in this whole document — see §5.4.

### 1.2 The five open PRs — none merged

| PR | Branch | Review verdict | Touches Gate-0 v2? |
|---|---|---|---|
| **#181** | `feat/gate0-v2-pin-freeze` | **APPROVED — HELD.** "Do not merge until prereg items 1-2 are re-frozen." | Yes — freezes §6.2 items **8a/8b** |
| **#188** | `fix/audit-verdict-not-gate-verdict` | **MERGE WITH FIXES** (edits applied, `7d6b2ee`) | Yes — edits `tools/gate0_appserver_arm.py`, moves the launcher blob hash |
| **#190** | `fix/ex09-arc-game-id` | **APPROVE** | **No.** ARC/EX09 only; its `.gitattributes` addition scopes to `eval/fixtures/arcagi3_wa30_banked/*.jsonl` |
| **#191** | `fix/red-glitch-row-signature` | **MERGE-WITH-EDITS** (round-2 fixes, `794ee37`) | Yes — widens `_red_success`'s corruption filter |
| **#192** | `fix/gate0-launcher-mode` | **MERGE-WITH-EDITS** (all six findings addressed, `e664074`) | **Yes — without it a v2 launch is impossible.** See §2.5 |

**[V]** review verdicts read from the PR comment threads via `gh pr view <n> --json comments`. Note
that GitHub's own `reviews` array is **empty for all five** — these are comment-thread reviews by
subagents, not GitHub review objects. **[UNVERIFIED]** whether any further review has been posted
since this document was written.

**Landing order — `#188 → #191 → #192`, then `#190` (anywhere), then `#181` last.** **[V]** and
non-negotiable for a mechanical reason: each of #188/#191/#192 appends a section to
`reports/2026-07-28-gate0-v2-deviations.md`, and each already claims its number —
`## D2` (#188), `## D3` (#191), `## D4` (#192). Any other order forces a renumber-and-rebase. #181
is last because #188 and #192 both move `tools/gate0_appserver_arm.py`, and #181's whole content is
a hash freeze. (**[V]** `gh pr diff <n> | grep '^+## D[0-9]'`.)

### 1.3 The prereg's P-table, re-checked against the tree

| P | Prereg says (`:55-72`) | Actual state 2026-07-28 | Verified by |
|---|---|---|---|
| **P1a** | NOT DONE; "the directory holds only `human_metrics.INCOMPLETE_1785175245.json`" | **NOT DONE — and the quoted detail is wrong.** `runs/gate0_paid_v2_human_baseline/` **does not exist at all**. The `INCOMPLETE_1785175245` file is in the **v1** dir `runs/gate0_paid_human_baseline/miniwob/`. Conclusion unchanged. | **[V]** `find runs -name 'human_metrics*'` |
| **P1b** | NOT DONE | **NOT DONE.** `artifact_sha256.miniwob_human` = `PENDING_NOT_YET_CAPTURED_v2_seed_human_replay_not_run` | **[V]** read `eval/fixtures/gate0_paid_v2_source_pins.json` |
| **P1c** | NOT DONE | **NOT DONE — and materially harder than the prereg implies.** See §6.1. | **[V]** `tools/capture_gate0_baseline_red.py:59` |
| **P2** | "MISSING — `runs/gate0_live_breaker/` does not exist" | **Partly stale.** The **directory exists** (holds `combined_credit_ledger.json`); the **file** `live_breaker_dry_run_trip.json` is absent. Conclusion unchanged. | **[V]** `ls -la runs/gate0_live_breaker` |
| **P3** | DONE (PR #179) | **DONE.** All 18 v2 paths present in the fixture. | **[V]** dumped the fixture |
| **P4** | NOT DONE | **NOT DONE**, and split: items 5-8 are **already frozen on `main`** post-#180; items **8a/8b** are what #181 freezes; items **1-4** and **9** are still open. See §3. | **[V]** |
| **P5** | not pre-registered until the prereg | Mechanical post-run step. Not startable before the run exists. | — |
| **P6** | "Check, do not assume" | **CHECKS CLEAN in a fresh worktree.** `eval/fixtures/gate0_miniwob_paid_v2_seeds.json` hashes to `4ede74d3110a067c2e5e625b65c1992b4c7d25ad8788f80b8c1ec053e1392172`, equal to the git blob. `.gitattributes:8` pins `eval/fixtures/gate0_*.json text eol=lf`, which is why. **Must be re-checked in the actual scoring tree.** | **[V]** `sha256sum` + `git show HEAD:… \| sha256sum` |
| **P7** | Not done | **Not done.** No code change satisfies it. See §6.3. | **[V]** |
| **P8** | "NOT DONE" | **DONE.** PR #180 (merge `b890d8c`, source `609ab8a`) rebuilt both world images. **The frozen doc's own line is stale, and that is correct behaviour, not a bug** — a frozen document records the state at freeze time. | **[V]** §1.4 below |
| **P9** | DRAWN, NOT CLOSED | **CLOSED.** Both #179 and #162 are merged; `MODES["paid_gate0_v2"]` is live at `eval/score_gate0.py:21-23` with the block `[417545, 662948, 660918, 981149, 558952]`. | **[V]** |

### 1.4 P8 is done, and the images on this machine are parity-clean — **[V]**

```
$ docker image inspect --format '{{.Id}}' gb-mcp-world
sha256:c889c344bd6442292ab8c8b63c4cbdadfc37b988a969f7629c71a268d6325d3e
$ docker image inspect --format '{{.Id}}' miniwob-world
sha256:ee12a2f0e54a798458568fea4730f770ede062956dd205afd7bf8290fa091ae4
```

Both equal `tools/gate0_appserver_arm.py:201-204`'s `ARM_IMAGE_IDS` exactly, which is what
`:1239-1242` hard-checks before spending.

Host↔image code parity, the CRLF tripwire, also holds — **[V]**, using the launcher's own hash
program (`tools/gate0_appserver_arm.py:395-403`, mirrored from `tools/run_gate0_codex.ps1:659`):

```
$ MSYS_NO_PATHCONV=1 docker run --rm --network none --entrypoint python miniwob-world \
    -c 'import hashlib,json,sys; print(json.dumps({p:hashlib.sha256(open(p,chr(114)+chr(98)).read()).hexdigest() for p in sys.argv[1:]},sort_keys=True))' \
    /app/world_mcp.py /app/core/miniwob_world.py
{"/app/core/miniwob_world.py": "f98b0dc9846bff0fceb96c8f77eee8b4261b9db894abd793a8d7b1145a23ce54",
 "/app/world_mcp.py": "b4ae7cf3d292cf56fa8cd3e8ddb56cd8e1339a6821e8c9a7f06f578ba8d05bfc"}
```

Identical for `gb-mcp-world`. And the host side at `origin/main`:

```
$ git cat-file blob HEAD:world_mcp.py | sha256sum
b4ae7cf3d292cf56fa8cd3e8ddb56cd8e1339a6821e8c9a7f06f578ba8d05bfc
$ git cat-file blob HEAD:core/miniwob_world.py | sha256sum
f98b0dc9846bff0fceb96c8f77eee8b4261b9db894abd793a8d7b1145a23ce54
```

**Consequence, and it removes a whole phase from this runbook: no world-image rebuild is needed for
v2.** The v2 intervention edits `tools/gate0_appserver_arm.py`, and **`tools/` is not copied into
either image** — `Dockerfile:25-27` copies `core/`, `games/`, `world_mcp.py`; `Dockerfile.miniwob:40-41`
copies `core/`, `world_mcp.py`. **[V]** The prereg's §6.5 items 15-20 cascade is therefore already
spent by #180 and **does not fire again** for the task-text change.

**But the parity check is against the *launch* tree, not against `origin/main`.** The primary
checkout's HEAD (`818c592`) carries `world_mcp.py` = `967866ab5ddcfcef17747aab1d83070a95a32c2cb05bc0b6252defce7b519fc9`
— **[V]**, and that is **not** `b4ae7cf3…`. Launching from the primary checkout as it stands today
aborts at `tools/gate0_appserver_arm.py:1251` (`"world image is stale: host/image code parity check
failed."`) for **$0**. See §5.4.

### 1.5 The ROM question — **[V]**, and it is David's decision, not a footnote

```
$ sha256sum roms/PokemonRed.gb
0602291f922443faf9d6b3a31948e37607a5f487ed8927892f926f86f4105700
$ xxd -s 0x143 -l 1 -p roms/PokemonRed.gb
c0
```

And from `roms/Pokemon Red Version (Colorization).zip`, the single member
`Pokemon Red Version (Colorization).gb`, 1 048 576 bytes:
sha256 `0602291f922443faf9d6b3a31948e37607a5f487ed8927892f926f86f4105700`, header `0x143` = `0xC0`.

**`roms/PokemonRed.gb` is byte-identical to a colorization romhack, and its CGB flag `0xC0` means
CGB-only** — this is not a stock 1 MB Pokémon Red, which is 1 MB with `0x143 = 0x80` at most and is
normally distributed as `Pokemon Red Version (USA, Europe) (SGB Enhanced).gb`. **[UNVERIFIED]** what
the stock ROM's digest is; I did not obtain one, and I am not asserting the hack's provenance beyond
the filename inside the zip.

**All banked Red evidence rests on this ROM.** `runs/gate0_human_baseline/red/human_metrics.json`
records `"rom_sha256": "0602291f922443faf9d6b3a31948e37607a5f487ed8927892f926f86f4105700"` — **[V]**.
The 233.288 s / 271-action human denominator that S-3 divides against was played on the romhack.

**This is an open decision for David, and it gates Arm R.** See §4 Phase 1, step **1.0**.

### 1.6 Cost receipts — **[V]**, all four figures reproduce

From `runs/gate0_paid/{red,miniwob}/agent_metrics.json`:

| Arm | `cost_usd` | `normalized_credits` | `primitive_actions` | `wall_clock_s` |
|---|---|---|---|---|
| red | `0.41589099999999996` | `10.397274999999999` | 142 | 127.75 |
| miniwob | `1.02958` | `25.739499999999996` | 97 | 295.594 |
| **combined** | **`$1.44547`** | **`36.13677`** | 239 | — |

Rounded: **Red $0.4159 / 142 actions; MiniWoB $1.0296 / 97 actions; $1.4455 total.** Matches.
Caps `$7.00` / `175` credits combined are at `eval/score_gate0.py:347-355`; the `250`-credit hard
breaker at `:354-355` and `tools/gate0_appserver_arm.py:209`. All **[V]**.

---

## 2. The four contested readings, adjudicated

Each was re-derived here from primary sources, not taken on trust.

### 2.1 P1a is captured AFTER the agent run — **SURVIVES. Verified twice, independently.**

**Source 1 — the design doc.** `reports/2026-07-13-minimum-north-star-gate-0-design.md:273-276`,
verbatim (**[V]**, read at that line range):

> "For MiniWoB, the agent sees held-out seeds `1000..1004` first; only after its artifacts are banked
> does the human replay those exact seeds for the formal time/action denominator."

**Source 2 — the prereg's own §4.1 step 5** (`:597-600`): *"The paid-seed human baseline is captured
on these seeds **only after** the agent's artifacts are banked, per the design doc's ordering
(`…design.md:273-276`), and using the **repaired** interface."* Restated at `:220-223`.

**And the priority order at `:69` cannot be chronological, by its own contents.** It reads
`P8 → P9 → P1a → P1b → P1c → P2 → P3/P4 → P5/P6 → P7`. If that were a schedule, the pin freeze (P4)
and the adversarial review of the prereg (P7) would both happen *after* the human baseline capture —
i.e. after the paid run. That is absurd. It is a **dependency order**: P1a blocks the **verdict**,
not the **launch**.

**This has been gotten wrong twice. The runbook states it as a rule:** the only things that block
*launch* are the ones the launcher or the run itself consumes — P4 items 1-4 and 9, P6, P2, P8, P9,
the intervention, and P7's decision. P1a/P1b/P1c/P5 block *scoring*, and three of them cannot even
start until the run has happened.

### 2.2 The intervention is NOT implemented — **SURVIVES.**

`tools/gate0_appserver_arm.py:187-190` at `origin/main` (**[V]**, read verbatim):

```python
COMMON_TASK_SUFFIX = (
    "Use only the connected world MCP tools and screen-derived state. Do not use shell, files, "
    "web, tool search, or connectors. Begin by observing. Stop when the stated task is complete."
)
```

That is the **v1** string. The prereg's §5.3 v2 text (`:648-659`) — the settle instruction, the
"without leaving the place you are in" guard, and the "Confirming is looking, not doing" prohibition
— is **absent**.

**No open PR applies it. [V]** — `gh pr diff <n> | grep COMMON_TASK_SUFFIX` over all five returns
only *prose mentions*: #181's fixture note (which says in as many words *"prereg §5's
`COMMON_TASK_SUFFIX` intervention has NOT landed"*) and #188's deviation text (*"`COMMON_TASK_SUFFIX`
is untouched"*). Zero code changes.

**Without it, a v2 run re-tests the exact brief that produced v1's `red_no_sustained_battle_exit`
miss** (prereg §1, `:293-296`). It would be a paid re-run of a known-failing condition.

**It moves `task_sha256` for BOTH arms** (prereg §6.1, `:771`), because
`task_text_for(arm) = ARM_TASK_SENTENCES[arm] + "\n" + COMMON_TASK_SUFFIX + "\n"`
(`tools/gate0_appserver_arm.py:219-220`, **[V]**). Verified mechanically — the current suffix
reproduces both frozen v1 pins exactly:

```
$ python -c "import hashlib; from tools.gate0_appserver_arm import task_text_for; \
    [print(a, hashlib.sha256(task_text_for(a).encode('utf-8')).hexdigest()) for a in ('red','miniwob')]"
red     306751c34627f6d5c6a8c94ac2f714e358f0dcbc5867866c273e434de7f4b7c4
miniwob 845638c874df2f2de2adaebdd1d6c9318c689a46d0032fa76a9393e1e47512d1
```

Those are exactly the pins at `eval/fixtures/gate0_expected_pins_{red,miniwob}.json` `task_sha256`
(prereg §6.1 items 1-2). **So P4 items 1-2 (and 3-4, and the whole `expected_pins_sha256` cascade,
and item 9) must be re-frozen AFTER the suffix change, never before.** #181 freezes 8a/8b against
**today's** targets; the moment the suffix lands, #181's two digests are stale.

There is no CRLF subtlety here: `launch/TASK.md` is written `newline="\n"`
(`tools/gate0_appserver_arm.py:1263`, **[V]**), so the in-process recompute equals
`_sha256_file(out_dir/"launch"/"TASK.md")` at `:1286`.

### 2.3 P2 writes into `runs/` — **SURVIVES, and it is byte-exactly regenerable. [V]**

The target is `runs/gate0_live_breaker/live_breaker_dry_run_trip.json`, pinned to
`27538b256bfdf276af91d4533b83247361ddbe470c5682b8addd58bda340e734`
(`eval/fixtures/gate0_paid_v2_source_pins.json` `artifact_sha256.live_breaker`). Regenerated into a
scratch path here and the digest matched on the first try:

```
$ python -m tools.gate0_credit_breaker dry-run-synthetic --out <scratch>/breaker_test.json
{"out": "...", "status": "PASS", "trip": {"credits_at_trip": 252.0, "limit_normalized_credits": 250,
 "tripped": true, "halted_before_exhausting_stream": true, ...}}
$ sha256sum <scratch>/breaker_test.json
27538b256bfdf276af91d4533b83247361ddbe470c5682b8addd58bda340e734
```

`--limit` must be left at its default (`LIMIT_NORMALIZED_CREDITS` = 250,
`tools/gate0_credit_breaker.py:300`); the artifact is written `newline="\n"` deliberately so the
digest is platform-independent (`:313-315`, comment quoted there).

**⚠ This step writes a new file into `runs/`, which is append-only source of truth. It creates
nothing that overwrites anything — `runs/gate0_live_breaker/` currently holds only
`combined_credit_ledger.json` — but it is still a write into the raw-data tree and needs David's
explicit OK at the moment it is run.** It is presented in §4 as a gated step, not routine.

### 2.4 P7 is an adversarial review of the prereg document itself — **SURVIVES.**

Prereg `:65`: *"Adversarial review of **this** document, posted on the PR | Not done for this
rewrite. | **Launch decision**."* It is the only precondition whose "Blocks" column reads *Launch
decision* rather than a scorer state. **No code change satisfies it, and no amount of fixture work
discharges it.** The PR is **#162**; the review must be posted there.

Note the awkwardness honestly: #162 is **merged** (that merge is what froze the document). A review
posted on a merged PR cannot gate that merge — it gates the *launch*. §4 Phase 2 places it
accordingly, as the last gate before spend.

### 2.5 A fifth thing, which David's brief did not list and which outranks all four

**Without #192 the v2 launcher cannot launch v2, and the failure is silent and expensive.** **[V]**
by reading `origin/main`'s `build_arg_parser()` (`:944-971`) — there is **no `--mode` flag at all**.
Four v1 values are hardcoded:

| # | Hardcode at `origin/main` | What a v2 launch would do |
|---|---|---|
| 1 | `build_docker_mcp_args:313` mounts `eval/fixtures/gate0_miniwob_paid_seeds.json` | Arm W plays the **SPENT** `[1000..1004]` — full price, un-reportable as held-out |
| 2 | `_finalize_real_run:1192` stamps `mode="paid_gate0"` | `agent_metric_identity:<arm>` → `INSUFFICIENT_SOURCE` (`eval/score_gate0.py:286-287`) |
| 3 | `_finalize_real_run:1196` writes `REPO_ROOT/runs/gate0_paid/wake_boundary.json` regardless of `--out-dir` | v2 pins `runs/gate0_paid_v2/wake_boundary.json` → `source_unreadable:wake_boundary`; **and it reaches into v1's banked append-only tree uninvited** |
| 4 | `_default_human_metrics_path:1001-1004` returns v1's miniwob baseline | a v2 `agent_metrics.json` banks v1's denominator in its `human_source_note` |

Defect 3 is live right now and is not hypothetical: **running `pytest` in a fresh worktree with no
`runs/` directory creates `runs/gate0_paid/wake_boundary.json`** — **[V]**, it happened in my own
worktree during the §1.1 baseline run.

#192 replaces all four with derivations from one required `--mode`, whose choices are taken from
`eval.score_gate0.MODES` itself, with **no default**. **#192 is a launch blocker, not a nicety.**

---

## 3. The true re-pin set

I re-derived this rather than copying either earlier list. Two independent cascades exist; conflating
them is what produced the wrong lists.

### 3.1 Cascade A — the world-image rebuild cascade. **ALREADY SPENT. Does not fire for v2.**

Triggered by editing `world_mcp.py` or `core/`. **[V]** both are baked into both images
(`Dockerfile:25-27`, `Dockerfile.miniwob:40-41`), so **both images move together** — David's claim
confirmed. `host_code_sha256`/`image_code_sha256` pin exactly two paths, `/app/world_mcp.py` and
`/app/core/miniwob_world.py` (`tools/gate0_appserver_arm.py:402`, `:1244`) — also confirmed.

PR #180 already executed this cascade. **[V]** §1.4: local images match `ARM_IMAGE_IDS` and parity
holds. **The v2 intervention lives in `tools/`, which neither image copies, so Cascade A does not
fire again.** If it ever does, the file set is:

1. `eval/fixtures/gate0_expected_pins_red.json`
2. `eval/fixtures/gate0_expected_pins_miniwob.json`
3. `eval/fixtures/gate0_expected_pins_red.appserver.json`
4. `eval/fixtures/gate0_expected_pins_miniwob.appserver.json`
5. `eval/fixtures/gate0_paid_source_pins.json` — `expected_pins_sha256` ×2
6. `eval/fixtures/gate0_readiness_dev_source_pins.json` — `expected_pins_sha256` ×2
7. `eval/fixtures/gate0_paid_v2_source_pins.json` — `expected_pins_sha256` ×2 (**8a/8b**)
8. `tools/gate0_appserver_arm.py` — `ARM_IMAGE_IDS` (`:201-204`), a fifth hardcoded image-ID site
9. `eval/fixtures/gate0_signature.appserver.json` — `expected_launcher_sha256` + `frozen_commit`, because (8) moved the launcher blob
10. `eval/fixtures/gate0_expected_pins.SOURCES.md` — provenance record

**Ten files. "At least nine" is right; the tenth is the SOURCES doc.** Item 7 is the one both earlier
lists dropped, and the prereg §6.2 is explicit about why it matters: *"six values across three files,
not four across two"* (`:801`). Nothing cross-checks (8) against (1)-(4) — `HANDOFF.md:252-253`.

### 3.2 Cascade B — the task-text cascade. **THIS is the one v2 fires.**

Triggered by editing `COMMON_TASK_SUFFIX` (or anything else in `tools/gate0_appserver_arm.py`).

| File | Field(s) | Why |
|---|---|---|
| `eval/fixtures/gate0_expected_pins_red.json` | `task_sha256` | `task_text_for("red")` changed |
| `eval/fixtures/gate0_expected_pins_miniwob.json` | `task_sha256` | `task_text_for("miniwob")` changed |
| `eval/fixtures/gate0_expected_pins_red.appserver.json` | `task_sha256` | resolved at launch by `resolve_expected_pins()` |
| `eval/fixtures/gate0_expected_pins_miniwob.appserver.json` | `task_sha256` | same |
| `eval/fixtures/gate0_paid_source_pins.json` | `expected_pins_sha256.{red,miniwob}` | content-hash-pins the two non-appserver files |
| `eval/fixtures/gate0_readiness_dev_source_pins.json` | `expected_pins_sha256.{red,miniwob}` | **the trap** — pins the *same two files* |
| `eval/fixtures/gate0_paid_v2_source_pins.json` | `expected_pins_sha256.{red,miniwob}` | **8a/8b — the pins that actually gate v2** |
| `eval/fixtures/gate0_signature.appserver.json` | `expected_launcher_sha256`, `frozen_commit` | the suffix lives inside the launcher |

**Eight files, six of them shared with Cascade A.** Note the `.appserver` pair is **not** itself
hash-pinned by any source-pins file — **[V]**, only the non-appserver pair is — so editing it
costs no further cascade.

**Current cascade state on `main` — [V]:**

```
$ sha256sum eval/fixtures/gate0_expected_pins_{red,miniwob}.json
67b95a29966443a792f93a61149c5630924a602a12e6515bc9ac1acda3522b92  ...red.json
8c19185309773ee565796e290460baa79838cae4553ba91e2aac98a01f180a02  ...miniwob.json
```

and `gate0_paid_source_pins.json` and `gate0_readiness_dev_source_pins.json` **already carry those
two values**. So Cascade B rows 5 and 6 are *currently* consistent; #181 makes row 7 consistent too.
**The prereg §6.2's quoted `ff00540b…` / `5d34c5ca…` are the pre-#180 values and are superseded** —
the fixture's own `_source_expected_pins_sha256` note says so in as many words.

**Sequencing that follows, and it is not optional.** All eight rows above must be recomputed **in one
commit, after the suffix lands**. Doing #181 first and the suffix second means #181's digests are
wrong; doing them in one commit means #181 is redundant. This is the "recompute #181's 8a/8b
digests" job — §4 Phase 1 step 1.4.

### 3.3 Also: `gate0_signature.appserver.json` is a blank template, not a fixture

**[V]** — every value in it is a `REPLACE_WITH_…` placeholder, and its own `_comment` says
*"TEMPLATE ONLY -- not a real signature"* and that `tools/gate0_appserver_arm.py` **does not**
implement a mechanical gate that reads it. Filling it is **manual orchestrator discipline**, and it
needs more than the two fields the prereg's item 9 names:

`frozen_commit`, `arm` (**one signature per arm**), `signed_by`, `signed_at`,
`expected_launcher_sha256` (`tools/gate0_appserver_arm.py`),
`expected_credit_breaker_sha256` (`tools/gate0_credit_breaker.py`),
`expected_credit_accountant_sha256` (`tools/gate0_credit_accountant.py`),
`expected_credit_rate_sha256` (`tools/gate0_codex_credit_rate.py`),
`expected_appserver_launch_sha256` (`tools/gate0_appserver_launch.py`), and the five-field
`credit_rate_pin` block.

The canonical hash recipe is given in the file's own `_comment_launcher_hash`:
`git diff --quiet HEAD -- <path> && git cat-file blob HEAD:<path> | sha256sum`.

---

## 4. The ordered sequence

Tick these in order. Anything unticked at Phase 3 is a launch abort.

---

### Phase 0 — Land what is already reviewed  *(no spend, no `runs/` writes)*

- [ ] **0.1 [D]** Merge **#188** (`fix/audit-verdict-not-gate-verdict`). Reviewed MERGE-WITH-FIXES.
      **PROOF:** `git -C <repo> fetch origin && git log --oneline -1 origin/main` names #188;
      `grep -c '^## D2' reports/2026-07-28-gate0-v2-deviations.md` → `1`.
- [ ] **0.2 [D]** Merge **#191** (`fix/red-glitch-row-signature`). **PROOF:** as above for `## D3`.
- [ ] **0.3 [D]** Merge **#192** (`fix/gate0-launcher-mode`). **PROOF:** as above for `## D4`, **and**
      `python -c "import tools.gate0_appserver_arm as m; p=m.build_arg_parser(); a=next(x for x in p._actions if x.dest=='mode'); print(a.required, sorted(a.choices))"`
      → `True ['paid_gate0', 'paid_gate0_v2', 'readiness_dev']`.
- [ ] **0.4 [D]** Merge **#190** if you want it — Gate-0-neutral, order-free. **PROOF:** suite green.
- [ ] **0.5 [auto]** Full suite on the merged tree. **PROOF:**
      `UV_PROJECT_ENVIRONMENT=.venv-win uv run --frozen python -m pytest -q` → `0` failures.
      Baseline at `322499f` was **1676 passed, 18 skipped**; the count will rise, not fall.

> **Do NOT merge #181 here.** It is APPROVED-but-HELD for a correct reason and its digests are about
> to go stale. It is superseded by step 1.4.

---

### Phase 1 — The intervention and the pin freeze  *(no spend, no `runs/` writes)*

- [ ] **1.0 [D] — GATE: ratify the ROM, or stop.**
      `roms/PokemonRed.gb` is a **CGB-only colorization romhack** (§1.5, **[V]**). Arm R's savestate,
      its 271-action human denominator, and every banked Red oracle row derive from it.
      **Decide, in writing, one of:**
      (a) **Ratify** — the romhack IS Arm R's pre-registered subject; record the digest
          `0602291f9224…5700` and the CGB flag in the launch record and in the verdict report's
          first lines; or
      (b) **Do not ratify** — then Arm R must be re-based on a stock ROM, which invalidates the
          human baseline, the savestate, and P1c's target, and this runbook does not cover it.
      **There is no (c).** A v2 verdict that does not state which was chosen is not reportable.
      **PROOF:** a line in `reports/2026-07-28-gate0-v2-deviations.md` (as `## D5`) or in the launch
      record, naming the digest and the decision, signed and dated.

- [ ] **1.1 [A] — Apply the §5.3 intervention.** One PR. Scope: `tools/gate0_appserver_arm.py:187-190`
      **only**. Replace `COMMON_TASK_SUFFIX` with the prereg §5.3 text **verbatim**
      (`reports/2026-07-25-gate0-v2-prereg.md:650-659`, the block quote). **Three things in that
      block are typography, not string content, and all three must be stripped:** the leading `> `
      markers, the `**…**` emphasis around the "Confirming is looking" clause, and **the enclosing
      `"` quote marks** on the first and last lines. The em-dashes (`—`) and the line wrapping *are*
      content — the existing v1 constant is a parenthesised implicit concatenation with single
      trailing spaces, and the new one must be too, or the digest is not what §5.3 describes.
      Do not touch `ARM_TASK_SENTENCES`, `DEVELOPER_INSTRUCTION`, or `render_brain_config_toml`.
      **PROOF:**
      `python -c "from tools.gate0_appserver_arm import COMMON_TASK_SUFFIX as s; print(repr(s))"`
      matches the prereg text character-for-character, checked by a human against `:650-659`.

- [ ] **1.2 [A] — Recompute the four `task_sha256` pins.** In the **same PR** as 1.1.
      **PROOF:**
      ```
      python -c "import hashlib; from tools.gate0_appserver_arm import task_text_for; \
        [print(a, hashlib.sha256(task_text_for(a).encode('utf-8')).hexdigest()) for a in ('red','miniwob')]"
      ```
      Both new digests must appear, unchanged, as `task_sha256` in all four
      `eval/fixtures/gate0_expected_pins_{red,miniwob}{,.appserver}.json`. Neither may still be
      `306751c3…` / `845638c8…`.

- [ ] **1.3 [A] — Recompute the six `expected_pins_sha256` values across three files.**
      Same PR as 1.1/1.2 — §3.2's rows 5, 6, 7. **This supersedes #181.**
      **PROOF:**
      ```
      sha256sum eval/fixtures/gate0_expected_pins_red.json eval/fixtures/gate0_expected_pins_miniwob.json
      python -c "import json; [print(f, json.load(open('eval/fixtures/'+f))['expected_pins_sha256']) \
        for f in ('gate0_paid_source_pins.json','gate0_readiness_dev_source_pins.json','gate0_paid_v2_source_pins.json')]"
      ```
      All three files must print the same pair, and that pair must equal the two `sha256sum` outputs.
      No value may remain `PENDING_NOT_YET_FROZEN_…`, `67b95a29…`, or `8c191853…`.
      **PROOF (regression):** `tests/test_gate0_source_pins.py` passes.

- [ ] **1.4 [D] — Close #181.** Either close it as superseded by 1.3, or rebase it onto 1.1-1.3 and
      let it carry the recomputed digests. **Do not merge it as it stands** — its `67b95a29…` /
      `8c191853…` are the pre-intervention values.
      **PROOF:** `gh pr view 181 --json state` → `CLOSED` or `MERGED` with the new digests present.

- [ ] **1.5 [A] — Append the deviation entries.** In `reports/2026-07-28-gate0-v2-deviations.md`,
      newest last, matching the existing `## D<n> — <clause> (<mechanism>)` + `**Landed by:**` /
      `**Touches:**` + five `###` subsections format. At minimum the ROM ratification (1.0) if it was
      recorded there, and — if 1.1-1.3 land as one PR — nothing else, because applying the
      pre-registered §5.3 text is **satisfying** the prereg, not deviating from it.
      **PROOF:** `grep '^## D' reports/2026-07-28-gate0-v2-deviations.md` is monotonic with no gaps.

- [ ] **1.6 [D]** Merge the 1.1-1.3 PR after adversarial review. **PROOF:** suite green on `main`.

- [ ] **1.7 [A] — Fill and sign `gate0_signature.appserver.json`.** One record **per arm** (§3.3).
      All hashes computed **after** 1.6, from the launch commit.
      **PROOF:** for each of the five pinned tools,
      `git diff --quiet HEAD -- <path> && git cat-file blob HEAD:<path> | sha256sum` equals the value
      written; `frozen_commit` equals `git rev-parse HEAD`; no `REPLACE_WITH_` string survives.
      *(Note: nothing in code reads this file — `eval/fixtures/gate0_signature.appserver.json`'s own
      `_comment`. It is a discipline artifact. Its absence will not stop a launch, which is exactly
      why it must be ticked by hand.)*

---

### Phase 2 — Pre-flight  *(no spend; ⚠ one `runs/` write)*

- [ ] **2.1 [D] — Move the primary checkout to the launch commit.** It is currently on
      `fix/miniwob-key-name-press` @ `818c592` (**[V]**), whose `world_mcp.py` blob is `967866ab…`,
      **not** `main`'s `b4ae7cf3…`. **Only David may do this** — it is his checkout, and the
      shared-checkout hazard is a standing project law.
      **PROOF:** `git rev-parse --abbrev-ref HEAD` → `main`; `git rev-parse HEAD` == the 1.6 merge
      commit; `git status --porcelain -- world_mcp.py core/ tools/ eval/` is **empty**.
      *(A dirty tree makes `git_blob_sha256` return `"UNHASHABLE"` and the launcher refuses at
      `tools/gate0_appserver_arm.py:1246-1248`.)*

- [ ] **2.2 [auto] — P6: seed hash, from the tree that will score.**
      **PROOF:** `sha256sum eval/fixtures/gate0_miniwob_paid_v2_seeds.json` →
      `4ede74d3110a067c2e5e625b65c1992b4c7d25ad8788f80b8c1ec053e1392172`.
      **If it prints `0e1861d3…` the checkout materialized CRLF — STOP.** Fix with
      `git rm --cached -r . && git reset --hard` under a correct `.gitattributes`, then re-check.
      (In a fresh worktree here it came out clean, because `.gitattributes:8` pins
      `eval/fixtures/gate0_*.json text eol=lf`. **[V]**)

- [ ] **2.3 [auto] — Image identity and parity.**
      **PROOF:** `docker image inspect --format '{{.Id}}' gb-mcp-world` → `sha256:c889c344…5d3e`;
      `… miniwob-world` → `sha256:ee12a2f0…1ae4`; both equal `tools/gate0_appserver_arm.py:201-204`.
      Then the parity program from §1.4 against both images → `/app/world_mcp.py` = `b4ae7cf3…` and
      `/app/core/miniwob_world.py` = `f98b0dc9…`, equal to
      `git cat-file blob HEAD:<path> | sha256sum`. **[V]** all four values today.
      *(On Git Bash, prefix with `MSYS_NO_PATHCONV=1` or the container-side `/app/...` paths get
      mangled into Windows paths.)*

- [ ] **2.4 [D] ⚠ WRITES TO `runs/` — P2: the live-breaker artifact.**
      **Ask David before running this. It creates a new file in the append-only raw-data tree.**
      ```
      python -m tools.gate0_credit_breaker dry-run-synthetic \
        --out runs/gate0_live_breaker/live_breaker_dry_run_trip.json
      ```
      Leave `--limit` at its default. **PROOF:** `sha256sum` of the written file →
      `27538b256bfdf276af91d4533b83247361ddbe470c5682b8addd58bda340e734`. **[V]** reproduced
      byte-exactly here into a scratch path. **If the digest differs, do not overwrite anything —
      stop and report.**

- [ ] **2.5 [auto] — The `$0` dry score. This is the single highest-value pre-flight step.**
      Write the v2 manifest (below) to a **scratchpad path, never inside the repo**, and run:
      ```
      python -m eval.score_gate0 <scratch>/v2_manifest.json
      ```
      The manifest's twelve path strings must be copied **verbatim** from
      `eval/fixtures/gate0_paid_v2_source_pins.json`'s own `audit_paths` — `_verify_audit_paths`
      refuses anything else (`eval/score_gate0.py:210-212`):
      ```json
      {"mode": "paid_gate0_v2",
       "arms": {
         "red": {"codex_audit": {"transcript": "runs/gate0_paid_v2/red/transcript.jsonl",
                                  "receipt": "runs/gate0_paid_v2/red/handshake-receipt.json",
                                  "expected_pins": "eval/fixtures/gate0_expected_pins_red.json",
                                  "artifacts_dir": "runs/gate0_paid_v2/red",
                                  "peer_receipt": "runs/gate0_paid_v2/miniwob/handshake-receipt.json"},
                 "oracle": "runs/gate0_paid_v2/red/world/oracle.jsonl"},
         "miniwob": {"codex_audit": {"transcript": "runs/gate0_paid_v2/miniwob/transcript.jsonl",
                                      "receipt": "runs/gate0_paid_v2/miniwob/handshake-receipt.json",
                                      "expected_pins": "eval/fixtures/gate0_expected_pins_miniwob.json",
                                      "artifacts_dir": "runs/gate0_paid_v2/miniwob",
                                      "peer_receipt": "runs/gate0_paid_v2/red/handshake-receipt.json"},
                     "oracle": "runs/gate0_paid_v2/miniwob/world/oracle.jsonl"}}}
      ```
      **PROOF — the expected pre-run output, [V] here** (measured with P2 done and the Red human
      baseline present; exit code 1, which is correct and expected):
      `overall: INSUFFICIENT_DATA`, `readiness: INSUFFICIENT_SOURCE`,
      **`failures["constancy"] == []`**, and `failures["source"]` containing **exactly**:
      `source_unreadable:{red_agent, miniwob_agent, miniwob_human, wake_boundary}`,
      `wake_boundary_artifact`, `expected_pins_hash_pin_missing:{red,miniwob}` (which step 1.3
      clears), and the twelve `missing_or_invalid_metric` entries downstream of the absent agent
      artifacts.
      **Anything else in that list — in particular any `constancy` entry, any `frozen_seed_*`, any
      `source_hash:live_breaker`, any `source_hash:red_human`, or any `audit_path_mismatch` — is a
      launch abort at $0.**
      *(Absent `red_agent` masks `human_metric_identity:red` — it hits `continue` at
      `eval/score_gate0.py:265-267`. This dry check therefore **cannot** clear P1c. See §6.1.)*

- [ ] **2.6 [auto] — `$0` seam checks, both arms.**
      ```
      python -m tools.gate0_appserver_arm --arm red     --mode paid_gate0_v2 --out-dir runs/gate0_seam_check_v2/red     --seam-check
      python -m tools.gate0_appserver_arm --arm miniwob --mode paid_gate0_v2 --out-dir runs/gate0_seam_check_v2/miniwob --seam-check
      ```
      **PROOF:** `seam_check.json` in each dir with `"ok": true`; exit 0.
      **[UNVERIFIED]** the exact `--mode`/`--out-dir` interaction on the seam-check path post-#192 —
      #192's `_validate_args` binds `--out-dir` to the mode's pre-registered directory **on the
      real-run path only**, so a seam-check out-dir outside the attempt tree should be accepted, but
      I did not run it. If it refuses, use `runs/gate0_paid_v2/<arm>` — but see the one-attempt
      guard warning in 3.1. ⚠ Note the seam check inspects by pinned **ID**, not by tag, so
      `image_id_matches_pin` is near-tautological; **2.3's tag→id comparison is the meaningful one.**

- [ ] **2.7 [D] — P7: post the adversarial review of the pre-registration on PR #162.**
      A launch-decision blocker that no code change satisfies (§2.4). The reviewer must attack §2's
      six disconfirmation conditions, §5's brief text, and §6's pin enumeration — and must be told
      that §0's P-table rows for P8/P9 are **stale-by-design** and that §6.2's `ff00540b…`/`5d34c5ca…`
      are superseded, so the review does not spend itself re-finding those.
      **PROOF:** a review comment on PR #162 with an explicit verdict.

- [ ] **2.8 [D] — The spend decision.** Prereg `:33-34`: *"the DECISION to spend is David's. This
      pre-reg earns the right to be reviewed, not the right to run."* Nothing above authorizes it.
      **PROOF:** David says go, in writing, after reading 2.5's output.

---

### Phase 3 — The paid attempt  *(⚠ SPENDS MONEY. ⚠ WRITES TO `runs/`. ONE SHOT.)*

> **One shot, twice over.** `tools/gate0_appserver_arm.py:920-937` refuses a second launch into an
> out-dir that already holds `transcript.raw_appserver.jsonl` **or** `agent_metrics.json`. And prereg
> §4.1 item 6: *"These seeds are spent the moment the agent plays them… A v3 needs another block."*
> Arm W's five seeds are consumed by the attempt, pass or fail.

- [ ] **3.1 [D] — Arm R first.** Launch discipline per the amendment
      (`reports/2026-07-24-gate0-prereg-amendment-appserver.md:264-274`).
      ```
      python -m tools.gate0_appserver_arm --arm red --mode paid_gate0_v2 \
          --model gpt-5.6-sol --out-dir runs/gate0_paid_v2/red \
          --credit-rate-pin <path-to-signed-rate-pin.json>
      ```
      `--model` and `--credit-rate-pin` are **required for a real run**
      (`tools/gate0_appserver_arm.py:977-978`, `:989-991`). A `latest` alias is refused (`:979-980`).
      **PROOF:** exit 0; `runs/gate0_paid_v2/red/` contains `agent_metrics.json`, `run-receipt.json`,
      `handshake-receipt.json`, `transcript.jsonl`, `transcript.raw_appserver.jsonl`, `audit.jsonl`,
      `mcp-tools.json`, `codex-mcp-list.json`, `brain-config.toml`, `launch/TASK.md`,
      `launch/.codex/config.toml`, `expected-pins.resolved.json`, `world/oracle.jsonl`; and
      `runs/gate0_paid_v2/wake_boundary.json` exists (post-#192, `wake_boundary_path_for(out_dir)`
      = `out_dir.parent / "wake_boundary.json"`).
      **⚠ [UNVERIFIED]** the exact rate-pin file path. The only rate-pin JSON on disk is
      `runs/gate0_paid/red_exec_noop_2026-07-22/paid/credit_rate_pin.json`
      (`credits_per_usd: 25`, `model: gpt-5.6-sol`); v1's receipts do not record which path was
      passed. **David must supply and verify this file himself** — an unpriced or mis-priced launch
      is the one thing the launcher's only hard money-gate protects against.

- [ ] **3.2 [D] — Arm W second.**
      ```
      python -m tools.gate0_appserver_arm --arm miniwob --mode paid_gate0_v2 \
          --model gpt-5.6-sol --out-dir runs/gate0_paid_v2/miniwob \
          --credit-rate-pin <path-to-signed-rate-pin.json>
      ```
      **PROOF:** as 3.1, for `runs/gate0_paid_v2/miniwob/`.

- [ ] **3.3 [auto] — Infra-death triage, if it happens.** Verbatim law, prereg `:957-961`:
      *"Relaunch only on infra death before ~10 decisions… Infra death AT or AFTER ~10 decisions =
      the attempt is spent: score whatever artifacts exist with the frozen scorer and bank that
      verdict (`INSUFFICIENT_DATA` is a legitimate outcome). No relaunch without David's explicit OK."*

---

### Phase 4 — Denominators and the post-run freeze  *(⚠ WRITES TO `runs/`; ⚠ P1c may be impassable — read §6.1 first)*

Everything here happens **after** Phase 3's artifacts are banked (§2.1's ordering).

- [ ] **4.1 [D] ⚠ HUMAN-ONLY ⚠ WRITES TO `runs/` — P1a: the MiniWoB human baseline.**
      David plays five episodes on the P9 seeds, on the repaired interface, through the screenshot
      relay. **A scripted stand-in cannot satisfy `--i-am-human`** and must not try.
      Build check first (`DAVID_BASELINES.md:100-105`): `docker image inspect --format '{{.Id}}'
      miniwob-world` must equal `world_image_id` in `eval/fixtures/gate0_expected_pins_miniwob.json`.
      Then, from the repo root (`DAVID_BASELINES.md:121-126`, with `--mode`/`--i-am-human` appended):
      ```
      MSYS_NO_PATHCONV=1 docker run -it --rm \
        -v "$PWD/tools:/app/tools" -v "$PWD/eval:/app/eval" -v "$PWD/runs:/app/runs" \
        --entrypoint python miniwob-world -m tools.capture_gate0_baseline_miniwob \
        --mode paid_gate0_v2 --i-am-human
      ```
      **These are the tool's real flags — [V]**, read from
      `tools/capture_gate0_baseline_miniwob.py:454-477`. The full set is
      `--mode {paid_gate0,paid_gate0_v2,readiness_dev}` (default `readiness_dev`), `--out`,
      `--seeds-file`, `--player` (default `David`), `--i-am-human`, `--allow-retake REASON`,
      `--test`. **Only `--mode paid_gate0_v2` and `--i-am-human` are needed**; `--out` and
      `--seeds-file` default correctly per mode (`MODE_CONFIG`, docstring `:58-63`). Do **not** pass
      `--allow-retake` on a first attempt. Do **not** pass `--mode paid_gate0` — it would refuse the
      P9 seeds and capture on the spent `1000..1004` into the wrong directory (prereg `:225-230`).
      **PROOF:** `runs/gate0_paid_v2_human_baseline/miniwob/human_metrics.json` exists (**not**
      `human_metrics.INCOMPLETE_*.json` — that name means the capture aborted) and carries
      `schema_version: 1, arm: "miniwob", role: "human", mode: "paid_gate0_v2"`; the script prints
      `PASS` and exits 0.
      **⚠ One cold attempt per task.** A botched capture needs `--allow-retake "<reason>"` and the
      reason is recorded in the artifact.

- [ ] **4.2 [A] — P1b: freeze `artifact_sha256.miniwob_human`.** Its own separate, reviewed commit.
      **PROOF:** `sha256sum runs/gate0_paid_v2_human_baseline/miniwob/human_metrics.json` equals the
      value written into `eval/fixtures/gate0_paid_v2_source_pins.json`, and the placeholder
      `PENDING_NOT_YET_CAPTURED_v2_seed_human_replay_not_run` is gone. Record the digest and the
      timestamp in the verdict report.

- [ ] **4.3 — P1c: the Red human baseline. ⚠ READ §6.1. THIS STEP HAS NO OWNER AND NO IMPLEMENTATION.**
      Not tickable as written. It decomposes into 4.3a/4.3b/4.3c in §6.1.

- [ ] **4.4 [A] — P5: freeze the run-produced artifact hashes.** Immediately after Phase 3 and
      **before** any scoring. Non-discretionary: hash exactly what the run produced, change nothing
      else. Three pins in `eval/fixtures/gate0_paid_v2_source_pins.json`:
      `artifact_sha256.red_agent`, `.miniwob_agent`, `.wake_boundary`.
      **PROOF:** each equals `sha256sum` of the corresponding file under `runs/gate0_paid_v2/`; no
      `PENDING_NOT_YET_CAPTURED_…` remains in the file; both values and the timestamp recorded in the
      verdict report.
      **⚠ P5 uncovers P1c.** Once `red_agent` loads, `_verify_sources` stops hitting `continue` at
      `eval/score_gate0.py:265-267` and evaluates the identity block — at which point
      `human_metric_identity:red` fires unless 4.3 is genuinely done.

---

### Phase 5 — Score and bank  *(no spend)*

- [ ] **5.1 [auto] — Re-run P6 in the scoring tree.** Same command as 2.2, same required value. The
      tree has moved since Phase 2.
- [ ] **5.2 [auto] — Score.** `python -m eval.score_gate0 <scratch>/v2_manifest.json` — the same
      manifest as 2.5, unedited. **PROOF:** the printed JSON. Exit 0 iff `readiness == "GO"`.
- [ ] **5.3 [D] — Bank as printed.** `reports/2026-07-13-minimum-north-star-gate-0-design.md:372-373`:
      *"Bank PASS/FAIL/INSUFFICIENT_DATA/CONSTANCY_BREACH as printed. Never rescue a marginal result
      with an informal rerun."* The verdict authority is `score()["overall"]`, **never**
      `audit()`'s own `overall`/`audit_overall` (prereg D-7, `:419-422`).
- [ ] **5.4 [A] — Write the verdict report.** Its first lines must state that Arm W ran on a
      **repaired interface** and **fresh seeds** and is not comparable to v1's Arm W (prereg
      `:962-965`), and — per 1.0 — which ROM Arm R was played on.

---

## 5. The four questions, answered explicitly

### 5.1 What is the minimum set of steps to a VALID verdict?

**A FAIL is a measurement and is a success of this process. A VOID is not.** `score()`'s precedence
chain is `leak → constancy → infra → source → capability → cheap` (`eval/score_gate0.py:357-370`,
**[V]**). A verdict is *valid capability evidence* only if `leak`, `constancy`, `infra` **and**
`source` are all empty — then `FAIL_CAPABILITY`, `FAIL_CHEAP` or `PASS` is what prints, and any of
the three is a real result. If `constancy` or `leak` is non-empty the attempt is **VOID** (prereg
D-5, §1's two frozen laws), which is what happened to v1.

**The irreducible minimum, in order:**

| # | Step | Why it cannot be dropped |
|---|---|---|
| 1 | Merge **#192** | Without `--mode` the run plays spent seeds, stamps the wrong mode, and writes into v1's tree. Three guaranteed source failures plus an un-reportable Arm W. |
| 2 | Apply the **§5.3 intervention** (1.1) | Otherwise v2 is a paid re-run of v1's failing brief. *(Technically a verdict is still reachable without it — it just re-tests a known failure. Dropping it makes the spend pointless, not invalid.)* |
| 3 | **Re-freeze Cascade B**, all eight rows, one commit (1.2-1.3) | Missing rows 1-4 → `pin_mismatch:task_sha256` on both arms → `CONSTANCY_BREACH` → **VOID**. Missing rows 5-7 → `expected_pins_hash_mismatch` / `expected_pins_hash_pin_missing` → `INSUFFICIENT_SOURCE`. |
| 4 | **P2** — live-breaker artifact (2.4) | `source_unreadable:live_breaker` + `live_breaker_artifact`. |
| 5 | **P6** — seed hash in the scoring tree (2.2, 5.1) | `frozen_seed_hash`. |
| 6 | **The run**, both arms, `--mode paid_gate0_v2` (3.1-3.2) | — |
| 7 | **P5** — freeze `red_agent`/`miniwob_agent`/`wake_boundary` (4.4) | `source_hash:*` on three artifacts. |
| 8 | **P1a + P1b** — MiniWoB human capture and freeze (4.1-4.2) | `source_unreadable:miniwob_human`, then `source_hash:miniwob_human`. |
| 9 | **P1c** — a Red human baseline stamped `paid_gate0_v2` (4.3 / §6.1) | `human_metric_identity:red`, which P5 un-masks. |

**Steps 1-8 are all fully specified and executable today. Step 9 is not** — see §6.1. **Every other
item in this runbook (#181, #188, #190, #191, the signature file, P7, the ROM ratification, the
deviation log) is discipline, hygiene, or governance — real obligations, but not mechanical
preconditions for the scorer to print a number.**

### 5.2 Which steps are human-only?

| Step | Why it cannot be delegated |
|---|---|
| **1.0** ROM ratification | A subject-matter decision about what the gate is testing. |
| **1.4, 1.6, 0.1-0.4** merges | Project law: David merges. |
| **2.1** move the primary checkout | It is David's checkout; the shared-checkout hazard is a standing law and two sessions have already tripped it. |
| **2.4** P2 write into `runs/` | Append-only raw data. Needs explicit OK. |
| **2.7** P7 adversarial review | Must be posted by a reviewer and *read* by David; the launch decision is his. |
| **2.8** the spend decision | Prereg `:33-34`. Nothing else authorizes spend. |
| **3.1, 3.2** the paid launches | Spend. |
| **4.1** P1a MiniWoB capture | **Physically human.** `--i-am-human` exists precisely to make a scripted stand-in impossible, and the rig requires a real interactive TTY when writing to the real baseline path. |
| **4.3 / §6.1** P1c Red capture | Same, if it is satisfied by a fresh playthrough. |
| **5.3** bank as printed | The one-attempt / no-rescue law. |

Everything else — 1.1, 1.2, 1.3, 1.5, 1.7, 4.2, 4.4, 5.4 and every `[auto]` proof command — is
delegable under the normal workflow.

### 5.3 Which steps cost money, and how much?

**Exactly two: 3.1 and 3.2.** Nothing else in this document spends anything. In particular the seam
checks, the dry score, the breaker regeneration, the parity checks and both human captures are `$0`.

| | Red | MiniWoB | Combined |
|---|---|---|---|
| **v1 actual [V]** | $0.41589 / 10.397 cr / 142 acts | $1.02958 / 25.739 cr / 97 acts | **$1.4455 / 36.14 cr** |
| **Prereg §8 expectation** (`:908-911`) | ~$0.50 | ~$1.30 | **~$1.80 / ~45 cr** |
| **H-d falsification ceiling** (`:912-914`) | ≤$1.00 / ≤25 cr | ≤$1.60 / ≤40 cr | **≤$2.60 / ≤65 cr** |
| **Frozen cap → `FAIL_CHEAP`** (`:921-923`, `eval/score_gate0.py:347-355`) | $5.00 / 125 cr | $2.00 / 50 cr | **$7.00 / 175 cr** |
| **Hard breaker → kill** | — | — | **250 cr** |

**Realistic expectation: $1.80-$2.60. Worst credible case before the cheap bar fails: $7.00. Absolute
ceiling before the process is killed: 250 credits ≈ $10 at the pinned 25 cr/USD.** Exceeding the H-d
row is a *recorded falsification*, not a failure — report it as such. Watch **MiniWoB**, not Red: v1
used 51.5% of its arm cap versus Red's 8.3%, and the repaired `press_key` means more steps per
episode.

The breaker is armed before the turn (`tools/gate0_appserver_arm.py:1294`, `:1308-1310`), so an
unbounded settle loop kills the process rather than the budget.

### 5.4 What is the earliest point at which the attempt can be aborted cheaply?

**Before a single dollar moves, in this order — and the first three are free and instant:**

1. **2.1 — `git rev-parse --abbrev-ref HEAD`.** The primary checkout is on
   `fix/miniwob-key-name-press` today. **[V]** If it is not on the launch commit, `world_mcp.py`'s
   blob is `967866ab…` instead of `b4ae7cf3…` and the launcher aborts at
   `tools/gate0_appserver_arm.py:1251` for $0. **This is the cheapest abort in the document and it
   is one command.**
2. **2.2 — `sha256sum` of the seed file.** `0e1861d3…` instead of `4ede74d3…` means CRLF, and every
   pin in the tree is suspect. $0.
3. **2.3 — `docker image inspect`.** A stale tag hard-fails at `:1240-1242` before any model call. $0.
4. **2.5 — the dry score.** This is the *diagnostic* abort: it exercises the entire `source` and
   `constancy` tier against the real fixtures and prints, in one line, exactly which preconditions
   are still open. Everything except the four run-produced artifacts is checkable here. $0.
5. **2.6 — seam checks.** Exercises the live MCP handshake and tool inventory. $0.
6. **Inside `_run_real`, before the model is invoked** — the credit-rate pin (`:1227`), docker
   resolution (`:1229`), image ID (`:1239-1242`), host-code-clean-at-HEAD (`:1243-1248`), host↔image
   parity (`:1249-1251`), and the live tool inventory vs the frozen allowlist (`:1272-1275`). All
   raise `SystemExit` at $0.

**After that, the next abort point is the credit breaker at 250 credits — i.e. roughly $10, not $0.**
There is no cheap abort mid-run. Run steps 1-5 in order and stop at the first failure.

---

## 6. Blockers with no owner — the honest list

### 6.1 ⚠ P1c is not implementable today, and no open PR touches it

This is the most important finding in this document.

**The scorer's requirement** (`eval/score_gate0.py:286-289`, **[V]**): the human artifact must
satisfy `(schema_version, arm, role, mode) == (1, "red", "human", "paid_gate0_v2")`.

**What exists:** `runs/gate0_human_baseline/red/human_metrics.json`, carrying
`"mode": "readiness_dev"` (**[V]**, read directly). Its sha256 is
`5144a5b36a29453c5f07ceba8336f3752055e0437e80f50d61418d61be686264`, and
`eval/fixtures/gate0_paid_v2_source_pins.json` **already points `artifact_paths.red_human` at it and
already pins that exact digest** (**[V]**). So the pin *matches* — and the mode is still wrong.

**What the prereg requires** (`:264-269`): *"P1c is satisfied by a FRESH CAPTURE under
`--mode paid_gate0_v2`, producing a new artifact. Not by editing…, not by hand-writing a `mode`
field, and not by any change that makes the scorer accept a `readiness_dev` artifact for a
`paid_gate0_v2` run."*

**Why it cannot be done today — [V], `tools/capture_gate0_baseline_red.py:59`:**

```python
MODE = "readiness_dev"   # the only mode this rig supports; the paid-seed human replay (if Red ever
                          # needs one -- Red has no held-out seed family, unlike MiniWoB) is out of
                          # scope for this readiness-phase capture rig.
```

There is **no `--mode` flag on the Red rig at all** — its argparse offers only `--rom`, `--state`,
`--out`, `--player`, `--test`, `--allow-retake` (`:371-377`). The prereg anticipated this: *"If the
capture tool cannot yet emit Red under that mode, extending it to do so is in-scope plumbing for the
P8/P9 batch"* (`:267-269`). **The P8/P9 batch has landed (#180) and that plumbing was not done.**

**So P1c decomposes into three steps that do not exist yet:**

- **4.3a [A]** — extend `tools/capture_gate0_baseline_red.py` with a `--mode` flag and a per-mode
  output directory, mirroring `capture_gate0_baseline_miniwob.py`'s `MODE_CONFIG`. Own plan, branch,
  PR, adversarial review.
- **4.3b [D] ⚠ HUMAN-ONLY ⚠ WRITES TO `runs/`** — David replays Red from the fixed bedroom start:
  starter acquisition, first rival battle, sustained exit. v1's human run took **233.288 s** of
  detected play, so this is minutes, not hours — but it is a real cold attempt under the one-attempt
  rule.
- **4.3c [A]** — re-point `artifact_paths.red_human` at the new artifact **and** re-freeze
  `artifact_sha256.red_human`, in the same commit. Both, or the pin breaks.

**Is there a cheaper route? Possibly — and it is David's call, not mine.** The existing artifact is
itself `"reconstructed": true`, derived by replaying an archived oracle trace through
`_red_success` row by row (its own `reconstruction_method` field). That archived trace **still
exists** — `E:\AI_Personas\10_pokemon_and_chess_and_office\ai-pokemon-red-prereg\runs\gate0_human_baseline\red\attempt_archive\oracle.incomplete1_1784594056.jsonl`
(**[V]**, it is on disk). Re-running the same reconstruction under the new mode would produce a new
artifact from the same human play, with no new playthrough.

**I am not recommending it.** It is arguably "producing the artifact under the correct mode rather
than hand-editing", which is what the prereg asks for — and it is arguably a re-derivation dressed
as a capture, which is what the prereg forbids. **The prereg is frozen and says "FRESH CAPTURE".
Choosing the reconstruction route is a deviation and must be logged as one, with David's explicit
sign-off, before it is done.**

**Bottom line: the sequence CAN reach a valid verdict, but not without work that nobody has started.**
P1c is the gap. Everything else in §5.1's minimum set is specified and executable.

### 6.2 The `_measured_against` block names a stale image tag

`eval/fixtures/gate0_paid_v2_source_pins.json`'s `_measured_against` records
`miniwob-mcp-world sha256:8bb3358e1421…` as the environment the 6-checkbox measurement was made
against. **[V]** `DAVID_BASELINES.md:110-112` calls `miniwob-mcp-world` *"stale by definition"*, and
the launcher hardcodes `miniwob-world` (`tools/gate0_appserver_arm.py:200`). The live pinned image is
now `sha256:ee12a2f0…`. Per prereg §4.1.2 the **frozen block binds, not the re-derivable rule**, so
this is **not** a licence to re-draw — but a post-#180 re-measurement disagreeing about which seed
renders six checkboxes would be a **finding against the rebuild**, and H-e's test case (`558952`)
rests on it. Worth one `$0` reset-only re-measurement before launch. Not a blocker.

### 6.3 P7 has no reviewer assigned and no deadline

Stated so it is not forgotten between now and Phase 2.

### 6.4 Two known-bad comment lines in `world_mcp.py`

`:250` claims "confirmed reading 4 at Stage 4" (it reads 3) and `:255` says "Only `>= 2` is
meaningful". Both are queued for a batched world PR. **Do not fix them as part of any step in this
runbook** — `world_mcp.py` is baked into both images, so touching it fires Cascade A (§3.1) and
forces a rebuild plus a ten-file re-pin. Out of scope here, deliberately.

---

## 7. UNVERIFIED register

Everything I could not check, and why. Nothing here was smoothed over.

| # | Claim | Why unverified |
|---|---|---|
| 1 | **The LF-forced `git archive \| docker build -` recipe.** The fragment `git -c core.autocrlf=false -c core.eol=lf archive HEAD` appears in five fixture provenance notes and at `HANDOFF.md:102`, but **the `\| docker build -` half exists nowhere in the repo** as a runnable command, and no build script exists. The only committed build lines are the CRLF-unsafe naive forms — `DAVID_BASELINES.md:95` (a real command) and `Dockerfile:7` (a comment example). | **Moot for v2** — §1.4 shows no rebuild is needed. But if one ever is, the recipe must be authored, and **I did not author or test one here.** I will not print a command I have not run. |
| 2 | **The rate-pin file path for 3.1/3.2.** Only one rate-pin JSON exists on disk (`runs/gate0_paid/red_exec_noop_2026-07-22/paid/credit_rate_pin.json`), and v1's receipts do not record which path was passed. | Not recoverable from artifacts. David must supply and verify it. |
| 3 | **`--seam-check` + `--mode` + an out-of-tree `--out-dir` post-#192** (step 2.6). #192 binds `--out-dir` to the mode's directory *on the real-run path only*, so it should be accepted, but I did not run #192's branch. | #192 is unmerged; running it would mean checking it out. |
| 4 | **The stock (non-hack) Pokémon Red ROM digest.** I verified the hack's digest and CGB flag; I did not obtain a stock ROM to contrast. | Out of scope, and I am not asserting provenance beyond the zip's own filename. |
| 5 | **Whether further reviews have landed on any of the five PRs** since this was written. GitHub's `reviews` array is empty for all five; the verdicts are comment-thread text. | Time-of-check. Re-read before merging. |
| 6 | **Whether the P9 seed block's 6-checkbox property survives the #180 rebuild** (§6.2). | Requires a `$0` reset-only re-measurement inside `miniwob-world` that I did not run. |
| 7 | **That `_red_success` is satisfiable by the §5.3 brief.** The prereg's §5.4 clause-by-clause proof is an argument, not a measurement; C6 and C8 were **never evaluated by v1** and are unproven in practice (prereg `:687`, `:689`). | Only the run can settle it. That is what the run is for. |

---

## Sources

All line references are against `origin/main` = `322499f` unless stated.

- `reports/2026-07-25-gate0-v2-prereg.md` — **FROZEN, not edited by this document.** §0 P-table `:55-72`, priority order `:69-71`, §0.2 `:82-103`, P1c `:240-269`, §4.1 `:531-602` (step 5 `:597-600`, step 6 `:601-602`), §5.3 `:648-659`, §6.1 `:769-785`, §6.2 `:787-812`, §6.3 `:815-818`, §6.4 `:820-831`, §6.5 `:833-859`, §7 `:874-899`, §8 `:903-923`, §10 `:950-965`
- `reports/2026-07-13-minimum-north-star-gate-0-design.md:273-276` (held-out ordering), `:372-373` (bank as printed)
- `reports/2026-07-18-gate0-prereg.md:81-83` (audit `overall` is not the verdict), `:117-119` (void law)
- `reports/2026-07-24-gate0-prereg-amendment-appserver.md:264-274` (the launch commands), `:85-95` (no code-enforced signature gate)
- `reports/2026-07-24-gate0-paired-verdict.md` (the banked v1 `CONSTANCY_BREACH`), `reports/2026-07-24-gate0-armR-verdict.md:14-19`
- `reports/2026-07-28-gate0-constancy-breach-addendum.md` (breach mechanism), `reports/2026-07-28-gate0-v2-deviations.md` (D1; append newest last)
- `eval/score_gate0.py` — `MODES` `:13-24`, `SOURCE_PIN_FILES` `:25-29`, `_verify_audit_paths` `:172-228`, `_verify_sources` `:231-309`, identity check `:286-289`, masking `continue` `:265-267`, precedence `:357-370`, caps `:347-355`, `score_manifest` `:386-427`, CLI `:430-440`
- `tools/gate0_appserver_arm.py` — `COMMON_TASK_SUFFIX` `:187-190`, `ARM_IMAGE_TAGS/IDS` `:200-204`, caps `:208-209`, `task_text_for` `:219-220`, code-hash paths `:402`/`:1244`, `build_arg_parser` `:944-971`, `_validate_args` `:974-998`, one-attempt guard `:920-937`, `_run_real` gates `:1227-1275`, TASK.md write `:1263`, `task_sha256` `:1286`, wake boundary `:1196`, `main` `:1361-1379`
- `tools/capture_gate0_baseline_miniwob.py` — docstring `:1-89`, argparse `:454-477`
- `tools/capture_gate0_baseline_red.py:59` (`MODE = "readiness_dev"`, the P1c blocker), argparse `:371-377`
- `tools/gate0_credit_breaker.py` — CLI `:292-315`
- `eval/fixtures/gate0_paid_v2_source_pins.json`, `gate0_paid_source_pins.json`, `gate0_readiness_dev_source_pins.json`, `gate0_expected_pins_{red,miniwob}{,.appserver}.json`, `gate0_signature.appserver.json`, `gate0_miniwob_paid_v2_seeds.json`
- `Dockerfile:25-27`, `Dockerfile.miniwob:40-41`, `.gitattributes:1-9`
- `DAVID_BASELINES.md:88-170` (the miniwob capture docker invocation and image precondition)
- `HANDOFF.md:102` (LF-forced rebuild claim), `:211-213` (#180 precedent gap), `:221` (#188 sequences the launcher re-freeze), `:247-258` (re-pin set, CRLF trap), `:252-253` (`ARM_IMAGE_IDS` uncross-checked)
- `runs/gate0_paid/{red,miniwob}/agent_metrics.json`, `runs/gate0_human_baseline/red/human_metrics.json` — read only, never written
