# Gate 0 v2 — executable runbook, from today's state to a scored verdict

**Written 2026-07-28 against `origin/main` = `322499f`. $0, docs only. This document launches
nothing, merges nothing, and spends nothing.**

> **Revision 2, 2026-07-28**, after the adversarial review of PR #194
> ([comment `5107941602`](https://github.com/David-Dashboard/ai-pokemon-red/pull/194#issuecomment-5107941602),
> verdict MERGE-WITH-EDITS). Three things changed materially and an operator who read revision 1
> must re-read: **(a)** the landing order does **not** avoid a rebase — every deviation-appending PR
> conflicts with every other, in any order, and Phase 0 now carries the resolution procedure;
> **(b)** the hard-breaker ceiling is **per arm, per process** — the worst case is **~$20 combined,
> not $10**; **(c)** the PR landscape moved — **#193 is the old step 1.1** (and is currently
> **BLOCKING**), **#195 is the old step 4.3a**, and both are now Phase 0 merges. Phase 0 and Phase 1
> were **renumbered**, not patched. Phases 2-5 keep their numbers.

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

**`runs/` is append-only source of truth. SIX steps in this runbook write into it**, and the list is
exhaustive:

| Step | What it writes | Gate |
|---|---|---|
| **2.4** | `runs/gate0_live_breaker/live_breaker_dry_run_trip.json` (P2) | ⚠ David's explicit OK |
| **2.6** | `runs/gate0_seam_check_v2/<arm>/seam_check.json` ×2 | ⚠ tell David; `$0`, new dirs, overwrites nothing |
| **3.1 / 3.2** | the whole of `runs/gate0_paid_v2/{red,miniwob}/` + `runs/gate0_paid_v2/wake_boundary.json` | ⚠ spend decision |
| **4.1** | `runs/gate0_paid_v2_human_baseline/miniwob/` (P1a) | ⚠ human-only |
| **4.3b** | `runs/gate0_paid_v2_human_baseline/red/` (P1c) | ⚠ human-only |

Every one is flagged **⚠ WRITES TO `runs/`** at the step itself. **2.6 was unflagged in revision 1
and that was a defect** — `_run_seam_check` calls `_write_json(out_dir / "seam_check.json", …)`
twice (once on the early-refusal path, once at the end), and `main()` does
`out_dir.mkdir(parents=True, exist_ok=True)` **before** dispatch, so the directory appears whether or
not the check succeeds. **[V]** read by symbol at `9d8ee51` (code identical to `origin/main`).

**A seventh write is possible by accident and is not a step: aborting a launch leaves residue.** See
§1.4 and §5.4 item 1 — *check*, do not *try*.

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

### 1.2 The SEVEN open PRs — none merged

Revision 1 said "five". **#193 was opened one minute before this document and #195 twenty-eight
minutes after it.** Both are steps this runbook already contains, written by other hands.

| PR | Branch | Latest review verdict, re-read 2026-07-28 | Touches Gate-0 v2? |
|---|---|---|---|
| **#181** | `feat/gate0-v2-pin-freeze` | **APPROVED — HELD.** "Do not merge until prereg items 1-2 are re-frozen." | Yes — freezes §6.2 items **8a/8b**, **and carries three other things worth salvaging** (§3.3) |
| **#188** | `fix/audit-verdict-not-gate-verdict` | **APPROVE** (delta review at `7d6b2ee`; was MERGE-WITH-FIXES) | Yes — edits `tools/gate0_appserver_arm.py`, moves the launcher blob hash |
| **#190** | `fix/ex09-arc-game-id` | **APPROVE** (delta review at `ce26c7e`) | **No.** ARC/EX09 only; its `.gitattributes` addition scopes to `eval/fixtures/arcagi3_wa30_banked/*.jsonl` |
| **#191** | `fix/red-glitch-row-signature` | **MERGE-WITH-EDITS** (delta review #4 at `bef7797`: "the predicate half PASSES, provably"; one Major in D3's *prose*) | Yes — widens `_red_success`'s corruption filter |
| **#192** | `fix/gate0-launcher-mode` | **APPROVE** (delta review at `e664074`) | **Yes — without it a v2 launch is impossible.** See §2.5 |
| **#193** | `feat/gate0-v2-task-brief` | ⛔ **BLOCKING** at `ce43fbb` — the row-yield arithmetic behind the amendment is wrong by 2×; the reviewer finds a compliant reading landing at **8 rows against a bar of 10** | **Yes — this IS the §5.3 intervention** (§2.2). Its head will move; **its `task_sha256` will move with it.** |
| **#195** | `fix/gate0-red-capture-mode` | **MERGE WITH EDITS** at `a4e5969` | **Yes — this IS P1c's 4.3a** (§6.1) |

**[V]** verdicts read 2026-07-28 from the PR comment threads via
`gh pr view <n> --json comments --jq '.comments[-1].body'`. GitHub's own `reviews` array is **empty
for all seven** — these are comment-thread reviews by subagents, not GitHub review objects. **This
row set is time-of-check and closes revision 1's UNVERIFIED #5; re-read it again before merging** —
three verdicts had already moved between revision 1 and revision 2.

#### The landing order does NOT avoid a rebase — corrected

Revision 1 called `#188 → #191 → #192` **[V]** and *"non-negotiable"* because each PR already claims
a distinct `## D<n>`. **The distinct numbers prevent a *renumber*. They do not prevent a *conflict*,
and revision 1 was wrong to imply they did.** All six deviation-appending PRs append at **EOF** of
`reports/2026-07-28-gate0-v2-deviations.md`, so **every pair conflicts, in every order.** GitHub
reports them all `MERGEABLE` only because each is tested against `main` independently; the second one
to land conflicts.

**[V] — measured here**, sequential `git merge` into a throwaway detached worktree off
`origin/main` (`322499f`), nothing pushed, primary checkout untouched:

```
#188  ->  MERGED CLEAN
#191  ->  CONFLICT: reports/2026-07-28-gate0-v2-deviations.md   (1 hunk)
#192  ->  CONFLICT: reports/2026-07-28-gate0-v2-deviations.md   (1 hunk)
#195  ->  CONFLICT: reports/2026-07-28-gate0-v2-deviations.md   (1 hunk)
#193  ->  CONFLICT: reports/2026-07-28-gate0-v2-deviations.md   (1 hunk)
#190  ->  MERGED CLEAN  (touches no deviation file)
```

**Only that one file ever conflicts.** `tools/gate0_appserver_arm.py` is edited by #188, #192 **and**
#193 and git auto-merged all three cleanly — **[V]**, the merged tree carries #192's `--mode` and
#193's `COMMON_TASK_SUFFIX` simultaneously. The conflict is a documentation append, not a code
collision, and the resolution is mechanical. **The procedure is in Phase 0's preamble; do not start
merging without reading it.**

**Order that still matters, and why:**

1. **`#195` (D5) before `#193` (D6)**, so `grep '^## D'` stays monotonic with no gaps without a
   renumber. This constraint did not exist in revision 1 and it is the only ordering the deviation
   file imposes.
2. **`#181` last**, unchanged: #188, #192 and #193 all move `tools/gate0_appserver_arm.py`, and
   #181's whole content is a hash freeze. See §3.3 — **rebase it, do not close it.**
3. **`#190` anywhere.**

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
— **[V]**, and that is **not** `b4ae7cf3…`. A launch from the primary checkout as it stands today
*would* abort at `tools/gate0_appserver_arm.py:1251` (`"world image is stale: host/image code parity
check failed."`) for **$0**.

> ⚠ **CHECK, DO NOT TRY.** "$0" is not "no side effects". `main()` does
> `out_dir.mkdir(parents=True, exist_ok=True)` **before** dispatch, and `_run_real` then creates
> `codex_home/` **with seeded auth** (`resolve_isolated_codex_home` → `seed_codex_auth`),
> `out_dir/world/` and `out_dir/launch/.codex/` — **all of them before** the image-ID check at
> `:1239-1242` and the parity check at `:1249-1251`. **[V]**, read by symbol. So *launching and
> letting it abort* costs nothing but leaves directories, including credential material, inside
> `runs/gate0_paid_v2/` — a write into the append-only tree that nobody authorised. **The check is
> `git rev-parse`, in the primary checkout, without invoking the launcher at all.** §5.4 item 1.

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

**These are receipts of what v1 actually cost. They are not ceilings, and nothing in the launcher
enforces them.** The `$7.00` / `175`-credit combined caps and the `250`-credit `hard_breaker_exceeded`
check all live in `eval/score_gate0.py`'s **`cheap` block** — they are computed **after** the run,
from banked `agent_metrics.json`, and they set a *verdict*, not a *limit*. The only thing that can
stop a live run is `LiveCreditGuard` (`tools/gate0_appserver_arm.py:209` `HARD_CREDIT_CAP`), and it
is **per arm, per process**. See §5.3, which revision 1 got wrong by a factor of two.

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

### 2.2 The intervention is not on `main` — **SURVIVES, but #193 now implements it, and NOT verbatim.**

> ⚠ **Revision 1 said "No open PR applies it. [V]". That is now false, and following revision 1's
> Phase 1 literally would have commissioned a duplicate PR that conflicts with #193 on the same
> file.** #193 (`feat/gate0-v2-task-brief`) applies it. It is Phase 0's step **0.5**.

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

**Without it, a v2 run re-tests the exact brief that produced v1's `red_no_sustained_battle_exit`
miss** (prereg §1, `:293-296`). It would be a paid re-run of a known-failing condition.

#### ⚠ #193's brief is deliberately NOT the prereg §5.3 text — deviation **D6**

This is the single most dangerous staleness in revision 1. Revision 1's step 1.1 said *"Replace
`COMMON_TASK_SUFFIX` with the prereg §5.3 text **verbatim**"* with PROOF *"matches the prereg text
character-for-character"*. **Executed literally today, that PROOF reverts #193's amendment.**

#193's first commit (`2a4daad`) did apply §5.3 verbatim. Its third (`ce43fbb`) amended it in four
places and logged the amendment as **D6**, **authorised by David explicitly on 2026-07-28** after he
read #193's own adversarial review. The reason, quoted from D6 and independently checkable in the
frozen prereg: **§5.4's own defences are mutually contradictory.** C5
(`red_no_sustained_battle_exit`) buys its margin from *"a single `explore` call alone produces ~41"*
rows; C7 (`red_map_changed_during_battle_exit_span`) rules out exactly that call, because
`World._run_autopilot` serves both `explore` and `goto` and is frontier-seeking. §5.3's actual
wording takes the C7-safe path and thereby discards the margin C5 was computed on, leaving the
primitive path — whose arithmetic §5.4 never wrote down.

**The amended text yields ≥ 24 post-battle rows against `_red_success`'s `watches[i:i+10]` window of
ten**, per D6's own worst-case table. ⛔ **That table is exactly what #193's current review verdict
BLOCKS on** — the reviewer argues the round unit is 1 row, not 2, giving a compliant reading at
**8 against a bar of 10**. **Treat the brief as unsettled until #193's head moves and is re-reviewed.**

**Digests, re-derived here — not copied from #193.** AST-extracted `COMMON_TASK_SUFFIX` and
`ARM_TASK_SENTENCES` from each revision's blob and recombined by `task_text_for`'s own formula
(`ARM_TASK_SENTENCES[arm] + "\n" + COMMON_TASK_SUFFIX + "\n"`, confirmed unchanged at both
revisions):

| arm | at `origin/main` `322499f` (v1) | at #193 `ce43fbb` (D6) |
|---|---|---|
| red | `306751c34627f6d5c6a8c94ac2f714e358f0dcbc5867866c273e434de7f4b7c4` | `aa8f1a7a4e409d03c42843e622df896fdc61c7ff8a74d51905defdcbfcb06d88` |
| miniwob | `845638c874df2f2de2adaebdd1d6c9318c689a46d0032fa76a9393e1e47512d1` | `24e4d9b27aa8277c8e2d35639c3b1d0bc53d7343a3b00efa46c34ba79daae440` |

**[V]** both columns reproduced independently. **The right-hand column is provisional and must not be
transcribed into any fixture** — #193 is BLOCKING, so its head will move and these will move with it.
**Step 1.1 recomputes them at the merge commit. That is the rule; the values above are an
illustration of the rule, not an input to it.**

**The launcher blob moves too, and it is NOT #193's number.** #193's PR body quotes
`715d89a9… → ae6442b0…`. **[V]** — `ae6442b0adf04b05e7c889366acced0afb98188247383867436b8002350fedb0`
is the blob at `ce43fbb` and reproduces exactly; but `715d89a9dfe4f848…` is **#193's own second
commit `ec881e4`**, not `origin/main`. The `origin/main` blob is
`23f4ca019a39bf0d5625b766e47c0c34c13395b0005a2e6e18bb1fabce5da618`. That pair describes an
*intra-PR* transition and **must not be used as a signature value.** Measured here:

| tree | canonical blob sha256 of `tools/gate0_appserver_arm.py` |
|---|---|
| `origin/main` `322499f` | `23f4ca01…` |
| #188 alone | `dabfac94…` |
| #192 alone | `229df7ab…` |
| #193 alone (`ce43fbb`) | `ae6442b0…` |
| #188+#192 | `36c47dce…` |
| #188+#191+#192+#195+#193 | `212634aa…` |

**Six launcher-touching combinations, six different digests. `expected_launcher_sha256` (§3.4, step
1.5) is only knowable at the launch commit, after every launcher-touching PR has landed.** Note also
that the canonical recipe is `git cat-file blob`, **not** `sha256sum <file>`: on this Windows
checkout the working-tree file hashes to `a2ce8984…` because it materializes CRLF — `.gitattributes`
pins `eol=lf` only for `*.sh` and the `eval/fixtures/gate0_*` fixtures, **not** for `*.py`. **[V]**

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
**today's** targets; the moment the suffix lands, #181's two digests are stale. **That is the only
part of #181 that goes stale — see §3.3.**

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

### 2.6 A sixth thing: #193 adds a pre-turn pin gate — and it is NOT a licence to re-freeze less

#193's second commit (`ec881e4`) adds `refuse_if_expected_pins_stale(receipt, arm)`, called at what
its own comment calls **"THE LAST `$0` INSTANT"** in `_run_real` — immediately after the handshake
receipt is written, immediately before the app-server client opens. **[V]**, read by symbol at
`ce43fbb`. It covers **all 20 `PIN_FIELDS`** by delegating to the frozen
`check_gate0_codex._expected_failures`, so it is the same comparison `_finalize_real_run` would have
run *after* the money was spent. It exempts nothing on the real path (`--dry-run` and `--seam-check`
never reach `_run_real`).

**This is a genuine, large improvement to the abort story: it turns "spend $2, then discover the
fixture was stale, then VOID the attempt and burn the held-out seed block" into a `$0` refusal.** It
is added to §5.4 as a seventh `$0` gate.

> ⛔ **DO NOT relax §5.1 row 3 on the strength of it. This is the inference an operator will reach
> for and it is wrong.**
>
> `refuse_if_expected_pins_stale` compares against **`gate0_expected_pins_{arm}.appserver.json`** —
> the launcher's docstring at `:23-24` says in as many words that this module *"is the ONLY consumer
> of the `.appserver.json` fixtures anywhere in this repo"*.
>
> **`eval/score_gate0.py` re-audits the banked run against a different file.** `audit_paths.<arm>.expected_pins`
> in `eval/fixtures/gate0_paid_v2_source_pins.json` is `eval/fixtures/gate0_expected_pins_red.json`
> / `…_miniwob.json` — the **non-`.appserver`** pair. **[V]**, dumped from the fixture.
>
> **Therefore: re-freezing only the `.appserver` pair passes the pre-turn gate, spends the money,
> and still voids at scoring on `pin_mismatch:task_sha256`.** #193's own docstring says so
> (*"NOT WIDENED to the mode's `audit_paths.<arm>.expected_pins`"*). **All four fixtures, one commit.
> §5.1 row 3 stands exactly as written.**

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
| `eval/fixtures/gate0_expected_pins.SOURCES.md` | the `task_sha256` provenance row | **added in revision 2** — see below |

**NINE files, six of them shared with Cascade A. Revision 1 said eight and was wrong**, by its own
argument: it added SOURCES.md as Cascade A's tenth file *"provenance record"* and did not apply the
identical reasoning here. `eval/fixtures/gate0_expected_pins.SOURCES.md:24` **is** the provenance row
for `task_sha256`, and `:76-83` states that if `tools/run_gate0_codex.ps1` changes, `task_sha256`
*"must be re-derived the same way … never hand-edited."* **[V]**, read at `9d8ee51`. Leaving it
un-updated is the drift that §6.5 describes.

Note the `.appserver` pair is **not** itself hash-pinned by any source-pins file — **[V]**, only the
non-appserver pair is — so editing it costs no further cascade. **It is still mandatory** (§2.6): the
launcher's own pre-turn gate reads it, and the scorer reads the other pair. Freezing one and not the
other buys a `$0` pass and a paid VOID.

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

**Sequencing that follows, and it is not optional.** All nine rows above must be recomputed **in one
commit, after the suffix lands** — i.e. after **#193** merges, not before. Doing #181 first and the
suffix second means #181's digests are wrong. This is §4 Phase 1 step **1.1**, and #181 is rebased
onto it at step **1.2**.

### 3.3 What #181 carries besides the two stale digests — **do not close it**

**[V]**, read from `git diff $(git merge-base refs/rb/pr181 origin/main) refs/rb/pr181`. #181 is two
files, and only **one field** in it goes stale:

| What | Stale after the suffix lands? |
|---|---|
| `expected_pins_sha256.{red,miniwob}` = `67b95a29…` / `8c191853…` | **YES.** These are pre-intervention. Step 1.1 recomputes them. |
| `_measured_against`: `miniwob-mcp-world` → `miniwob-world`, `world_image_id` → `sha256:ee12a2f0…`, new `superseded_world_image_id` | **No.** This is *exactly* the staleness §6.2 complains about, already fixed. |
| `_measured_against.re_measured_post_p8` + `re_measured_post_p8_on` | **No.** This is the answer to **UNVERIFIED #6** — see §6.2. |
| `paid_gate0_v2` added to two parametrized tests in `tests/test_gate0_source_pins.py` | **No.** Pure regression coverage. |

**Revision 1's step 1.4 offered "close it as superseded" as a first option. That would throw away
work this document elsewhere asks for**, and step 1.3's PROOF reproduced none of it. Corrected:
**rebase only.** §4 Phase 1 step 1.2.

### 3.4 Also: `gate0_signature.appserver.json` is a blank template, not a fixture

**[V]** — every value in it is a `REPLACE_WITH_…` placeholder, and its own `_comment` says
*"TEMPLATE ONLY -- not a real signature"* and that `tools/gate0_appserver_arm.py` **does not**
implement a mechanical gate that reads it. Filling it is **manual orchestrator discipline**, and it
needs more than the two fields the prereg's item 9 names:

**Fillable BEFORE the launch, from the launch commit** — `frozen_commit`, `arm` (**one signature per
arm**), `signed_by`, `signed_at`, `notes`, the five-field `credit_rate_pin` block, and five blob
hashes: `expected_launcher_sha256` (`tools/gate0_appserver_arm.py`),
`expected_credit_breaker_sha256` (`tools/gate0_credit_breaker.py`),
`expected_credit_accountant_sha256` (`tools/gate0_credit_accountant.py`),
`expected_credit_rate_sha256` (`tools/gate0_codex_credit_rate.py`),
`expected_appserver_launch_sha256` (`tools/gate0_appserver_launch.py`).

**⚠ NOT fillable before the launch — two more fields, which revision 1 omitted:**
`expected_config_sha256` and `expected_codex_mcp_list_sha256`. Both read
`PENDING_RECOMPUTE_AT_LAUNCH -- this launch's freshly computed handshake…` in the template
(**[V]**, dumped at `9d8ee51`), and both are *this launch's own handshake-receipt values* — a
function of the launch invocation (the `-OutputDir`-derived absolute docker mount paths inside
`config.toml`; see `eval/fixtures/gate0_expected_pins.SOURCES.md`'s `config_sha256` row, which calls
them *"launch-invocation-dependent"*). **They are unknowable in Phase 1.**

**Consequence for the step:** revision 1's step 1.7 PROOF was *"no `REPLACE_WITH_` string
survives"*, which **passes with both of these still unfilled**, because they are
`PENDING_RECOMPUTE_AT_LAUNCH` strings, not `REPLACE_WITH_` strings. The step therefore *looked*
finishable in Phase 1 and was not. **Step 1.5 now straddles the launch explicitly: 1.5a before,
1.5b after 3.1/3.2.**

The canonical hash recipe is given in the file's own `_comment_launcher_hash`:
`git diff --quiet HEAD -- <path> && git cat-file blob HEAD:<path> | sha256sum`. **Use it verbatim —
`sha256sum <path>` on this Windows checkout hashes CRLF bytes and gives a different answer** (§2.2).

---

## 4. The ordered sequence

Tick these in order. Anything unticked at Phase 3 is a launch abort.

---

### Phase 0 — Land what is already reviewed  *(no spend, no `runs/` writes)*

> ### ⚠ READ THIS BEFORE MERGING ANYTHING — the deviation-file conflict
>
> **Steps 0.2 through 0.5 will each stop with a merge conflict.** This is expected, it is the same
> conflict every time, and it is not a sign anything is wrong. Revision 1 did not mention it and
> would have stranded you at step 0.2.
>
> **Why.** `reports/2026-07-28-gate0-v2-deviations.md` on `main` ends with the `## D1` block. Each of
> #188/#191/#192/#195/#193 appends its own `## D<n>` block at **EOF**. Git sees five different
> continuations of the same final line. Only the **first** merge is clean.
>
> **The resolution, every time.** One hunk, one file. Git will produce:
>
> ```
> <<<<<<< HEAD
> ## D<lower>  … the block already on main …
> =======
> ## D<higher> … the incoming block …
> >>>>>>> <the branch being merged>
> ```
>
> **Keep BOTH blocks, lower `D` number first, with the file's existing separator between them:**
> delete the `<<<<<<< HEAD` line, delete the `>>>>>>> …` line, and replace the `=======` line with a
> blank line, `---`, blank line. Change nothing inside either block. Then check for a **doubled
> `---`** — #193's block carries its own leading `---`, so resolving it naively produces two in a
> row; delete one.
>
> **[V] — the whole sequence was executed here** in a throwaway detached worktree off `origin/main`
> (nothing pushed, primary checkout untouched, `runs/` never written). All four conflicts had exactly
> this shape and this resolution, and the file ended at **D1 → D2 → D3 → D4 → D5 → D6**, monotonic,
> no gaps.
>
> **PROOF after every resolution — all three must hold:**
> ```
> grep -c '^<<<<<<<\|^=======$\|^>>>>>>>' reports/2026-07-28-gate0-v2-deviations.md   # -> 0
> grep -n '^## D' reports/2026-07-28-gate0-v2-deviations.md                            # -> D1..Dn, +1 each, no gaps
> python -c "import re,sys; L=open('reports/2026-07-28-gate0-v2-deviations.md',encoding='utf-8').read().splitlines(); print([i+1 for i,l in enumerate(L) if l=='---' and i and L[i-1]=='---'] or 'no doubled ---')"
> ```
>
> ⚠ **`git checkout --ours` / `--theirs` on this file loses a whole deviation entry. Never use them
> here.**

- [ ] **0.1 [D]** Merge **#188** (`fix/audit-verdict-not-gate-verdict`) — **claims `## D2`**. Latest
      review APPROVE at `7d6b2ee`. **This one merges clean.**
      **PROOF:** `git -C <repo> fetch origin && git log --oneline -1 origin/main` names #188;
      `grep -c '^## D2' reports/2026-07-28-gate0-v2-deviations.md` → `1`.
- [ ] **0.2 [D]** Merge **#191** (`fix/red-glitch-row-signature`) — **claims `## D3`**.
      ⚠ **CONFLICT — resolve per the preamble.** **PROOF:** the three preamble commands, plus
      `grep -c '^## D3' …` → `1`.
- [ ] **0.3 [D]** Merge **#192** (`fix/gate0-launcher-mode`) — **claims `## D4`**. ⚠ **CONFLICT.**
      **PROOF:** preamble commands for `## D4`, **and**
      `python -c "import tools.gate0_appserver_arm as m; p=m.build_arg_parser(); a=next(x for x in p._actions if x.dest=='mode'); print(a.required, sorted(a.choices))"`
      → `True ['paid_gate0', 'paid_gate0_v2', 'readiness_dev']`.
- [ ] **0.4 [D]** Merge **#195** (`fix/gate0-red-capture-mode`) — **claims `## D5`**. ⚠ **CONFLICT.**
      **This is P1c's step 4.3a** (§6.1); revision 1 had it as unstarted work with no owner.
      Reviewed MERGE-WITH-EDITS at `a4e5969` — **check the edits landed before merging.**
      **PROOF:** preamble commands for `## D5`, **and**
      `python -c "import tools.capture_gate0_baseline_red as m; print(sorted(m.MODE_CONFIG), m.MODE_CONFIG['paid_gate0_v2']['real_out'], sorted(m.HELD_OUT_MODES))"`
      names `paid_gate0_v2` and the directory `runs/gate0_paid_v2_human_baseline/red`. **[V]** both
      read from `refs/pull/195/head`.
- [ ] **0.5 [D]** Merge **#193** (`feat/gate0-v2-task-brief`) — **claims `## D6`**. ⚠ **CONFLICT.**
      **This is the §5.3 intervention** (§2.2); revision 1 had it as step 1.1, an unwritten PR.
      **⛔ DO NOT MERGE AT `ce43fbb`.** Its latest review is **BLOCKING** on D6's row-yield table
      (the round unit: 1 row vs 2, i.e. 8 rows against a bar of 10). **Merge only after the blocking
      finding is resolved and re-reviewed.** Everything downstream that depends on the brief —
      step 1.1's four `task_sha256`, the six `expected_pins_sha256`, `expected_launcher_sha256` —
      is computed at **the merge commit**, never copied from the PR body (§2.2).
      **PROOF:** preamble commands for `## D6`, **and**
      `python -c "import hashlib; from tools.gate0_appserver_arm import task_text_for; [print(a, hashlib.sha256(task_text_for(a).encode('utf-8')).hexdigest()) for a in ('red','miniwob')]"`
      prints two digests that are **not** `306751c3…` / `845638c8…`. Record them; step 1.1 consumes
      exactly these.
- [ ] **0.6 [D]** Merge **#190** if you want it — Gate-0-neutral, order-free, touches no deviation
      file and merges clean anywhere in the sequence. **PROOF:** suite green.
- [ ] **0.7 [auto]** Full suite on the merged tree. **PROOF:**
      `UV_PROJECT_ENVIRONMENT=.venv-win uv run --frozen python -m pytest -q` → `0` failures.
      Baseline at `322499f` was **1676 passed, 18 skipped**; the count will rise, not fall.

> **Do NOT merge #181 here.** It is APPROVED-but-HELD for a correct reason and one of its fields is
> about to go stale. **It is rebased, not closed** — step **1.2**, and §3.3 for what it carries.

---

### Phase 1 — The ROM gate and the Cascade-B re-freeze  *(no spend, no `runs/` writes)*

> **Restructured in revision 2.** Revision 1's 1.1 (apply the intervention) is now **#193**, merged
> in Phase 0. Revision 1's 1.2 and 1.3 said *"in the same PR as 1.1"* — **unfollowable**, because
> #193 touches **no fixture** (its files are the deviation log, `tests/test_gate0_appserver_arm.py`,
> and `tools/gate0_appserver_arm.py`). They are now one **follow-on** PR, step **1.1**, opened after
> #193 lands.

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
      **PROOF:** a line in `reports/2026-07-28-gate0-v2-deviations.md` **as `## D7`** or in the launch
      record, naming the digest and the decision, signed and dated.
      ⚠ **Revision 1 said `## D5`. That number is taken** — current allocation is **D1** (on `main`),
      **D2** #188, **D3** #191, **D4** #192, **D5** #195, **D6** #193. **[V]**, read from each branch
      head 2026-07-28. **D7 is the first free slot.** Re-check with
      `grep '^## D' reports/2026-07-28-gate0-v2-deviations.md` on the post-Phase-0 tree before
      writing, because further PRs may have claimed slots since.

- [ ] **1.1 [A] — Cascade B: re-freeze all nine rows, ONE PR, after #193 has merged.** §3.2. This is
      revision 1's 1.2 + 1.3 combined, and it is the whole of the P4 re-pin for the task-text change.
      **Every digest is computed at the merge commit. Nothing is transcribed from a PR body, from
      §2.2's illustration table, or from #181.**
      1. four `task_sha256`: `eval/fixtures/gate0_expected_pins_{red,miniwob}{,.appserver}.json`
      2. six `expected_pins_sha256`: `gate0_paid_source_pins.json`,
         `gate0_readiness_dev_source_pins.json`, `gate0_paid_v2_source_pins.json` (**8a/8b**)
      3. `eval/fixtures/gate0_expected_pins.SOURCES.md`'s `task_sha256` provenance row — say plainly
         that the value is now derived from `tools/gate0_appserver_arm.py`'s `COMMON_TASK_SUFFIX`,
         **not** from `tools/run_gate0_codex.ps1`'s `$CommonTask` as `:24` and `:76-83` currently
         claim (§6.5).
      **⚠ All four expected-pins fixtures, in one commit** — the `.appserver` pair for the launcher's
      pre-turn gate, the non-`.appserver` pair for the scorer. §2.6 explains why doing only one pair
      buys a `$0` pass and a paid VOID.
      **PROOF:**
      ```
      python -c "import hashlib; from tools.gate0_appserver_arm import task_text_for; \
        [print(a, hashlib.sha256(task_text_for(a).encode('utf-8')).hexdigest()) for a in ('red','miniwob')]"
      sha256sum eval/fixtures/gate0_expected_pins_red.json eval/fixtures/gate0_expected_pins_miniwob.json
      python -c "import json; [print(f, json.load(open('eval/fixtures/'+f))['expected_pins_sha256']) \
        for f in ('gate0_paid_source_pins.json','gate0_readiness_dev_source_pins.json','gate0_paid_v2_source_pins.json')]"
      ```
      The first command's two digests must appear as `task_sha256` in **all four** expected-pins
      files and must not be `306751c3…` / `845638c8…`. All three source-pins files must print the
      same pair, equal to the two `sha256sum` outputs, and none may remain
      `PENDING_NOT_YET_FROZEN_…`, `67b95a29…`, or `8c191853…`.
      **PROOF (regression):** `tests/test_gate0_source_pins.py` passes.

- [ ] **1.2 [D] — REBASE #181 onto 1.1. Do NOT close it.** ⚠ **Revision 1 offered "close as
      superseded" and that was wrong** — #181 is the only place three other things live (§3.3): the
      `_measured_against` image-tag fix that §6.2 complains about, the `re_measured_post_p8` block
      that answers this document's own **UNVERIFIED #6**, and `paid_gate0_v2` coverage in two
      parametrized tests. Only `expected_pins_sha256` goes stale.
      **Either** rebase #181 onto 1.1 and let it carry the recomputed digests, **or** fold its three
      salvageable parts into 1.1's PR and close #181 **explicitly naming what was carried across**.
      **Do not merge it as it stands** — `67b95a29…` / `8c191853…` are pre-intervention values.
      **PROOF:** on the merged tree,
      `python -c "import json; d=json.load(open('eval/fixtures/gate0_paid_v2_source_pins.json')); m=d['_measured_against']; print(m['world_image'], m['world_image_id'][:20], 're_measured_post_p8' in m, d['expected_pins_sha256'])"`
      → `miniwob-world sha256:ee12a2f0e54a True {…the 1.1 digests…}`; and
      `grep -c paid_gate0_v2 tests/test_gate0_source_pins.py` is non-zero.

- [ ] **1.3 [A] — Append the D7 deviation entry.** In `reports/2026-07-28-gate0-v2-deviations.md`,
      newest last, matching the existing `## D<n> — <clause> (<mechanism>)` + `**Landed by:**` /
      `**Touches:**` + five `###` subsections format. The ROM ratification (1.0), if it was recorded
      there. **1.1 itself owes no deviation** — re-freezing pins onto a landed brief is prereg §6.1
      being *satisfied*. **The brief's own deviation is D6 and #193 already wrote it.**
      **PROOF:** `grep '^## D' reports/2026-07-28-gate0-v2-deviations.md` is monotonic with no gaps.

- [ ] **1.4 [D]** Merge the 1.1 PR (and 1.2's rebased #181) after adversarial review.
      **PROOF:** suite green on `main`. **This commit is the launch commit** — record
      `git rev-parse HEAD` now; steps 1.5a, 2.1 and 3.1/3.2 all refer to it.

- [ ] **1.5a [A] — Fill `gate0_signature.appserver.json`, as far as it can be filled BEFORE the
      launch.** One record **per arm** (§3.4). All hashes from the 1.4 launch commit.
      **PROOF:** for each of the five pinned tools,
      `git diff --quiet HEAD -- <path> && git cat-file blob HEAD:<path> | sha256sum` equals the value
      written; `frozen_commit` equals `git rev-parse HEAD`; `arm`, `signed_by`, `signed_at` and the
      `credit_rate_pin` block are filled; **no `REPLACE_WITH_` string survives.**
      ⚠ `expected_config_sha256` and `expected_codex_mcp_list_sha256` **still read
      `PENDING_RECOMPUTE_AT_LAUNCH` at this point, and that is correct** — they are the launch's own
      handshake-receipt values and cannot exist yet (§3.4). **Do not invent them, and do not treat
      the "no `REPLACE_WITH_`" proof as meaning the file is finished.**
      ⚠ `expected_launcher_sha256` is **only** knowable here: §2.2 measures six different launcher
      blobs across six merge combinations. Compute it at HEAD; never copy one from a PR body.
      *(Note: nothing in code reads this file — `eval/fixtures/gate0_signature.appserver.json`'s own
      `_comment`. It is a discipline artifact. Its absence will not stop a launch, which is exactly
      why it must be ticked by hand.)*

- [ ] **1.5b [A] — after 3.1/3.2, fill the two launch-dependent fields.** See Phase 4, step 4.5.

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

- [ ] **2.3a [auto] — `$0` VALIDATE THE CREDIT-RATE PIN. New in revision 2.**
      `--credit-rate-pin` is **refused** for any non-real run (`_validate_args`: *"only meaningful for
      a real, turn-running launch"*) and **required** for a real one, and it is loaded on the very
      first line of `_run_real` (`:1227`). **[V]** So neither the seam check nor the dry run can
      exercise it, and without this step David's first contact with the file is the command that
      spends money — compounding **UNVERIFIED #2**, where the path itself is unknown.
      `load_credit_rate_pin(path, expected_model)` is a plain importable function
      (`tools/gate0_codex_credit_rate.py:112`) that raises `CreditRateNotPinned` (`:107`) on every
      failure mode. Call it directly, at `$0`, with the exact path and model you will pass to 3.1:
      ```
      python -c "from pathlib import Path; from tools.gate0_codex_credit_rate import load_credit_rate_pin; \
        import json; print(json.dumps(load_credit_rate_pin(Path(r'<path-to-signed-rate-pin.json>'), 'gpt-5.6-sol'), sort_keys=True))"
      ```
      **PROOF:** it prints the pin and exits 0 — no `CreditRateNotPinned`. Read the printed
      `credits_per_usd` and check it against §5.3's cost table before going further; that number is
      what turns the 250-credit hard breaker into a dollar figure.
      **⚠ [UNVERIFIED]** the path. The only rate-pin JSON on disk is
      `runs/gate0_paid/red_exec_noop_2026-07-22/paid/credit_rate_pin.json` (`credits_per_usd: 25`,
      `model: gpt-5.6-sol`) and v1's receipts do not record which path was passed (§7 #2).
      **David supplies the file; this step is what makes supplying the wrong one cheap.**

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
      **Anything else in the `source` or `constancy` lists — in particular any `constancy` entry, any
      `frozen_seed_*`, any `source_hash:live_breaker`, any `source_hash:red_human`, or any
      `audit_path_mismatch` — is a launch abort at $0.**
      **⚠ `failures["capability"]` is NOT empty pre-run, and that is expected — do not stop on it.**
      Roughly eight entries appear (`red:red_not_fresh_party_zero`, `red:task_predicate_failed`,
      `miniwob:task_predicate_failed`, and five `miniwob_episode_N_terminal_count`). They are
      artefacts of the *absent* agent artifacts, not findings, and `score()`'s precedence chain
      (`leak → constancy → infra → source → capability → cheap`) never consults `capability` while
      `source` is non-empty. This is stated in the committed deviation log's own **D1** entry —
      *"emits capability failures … that are artefacts of the missing source rather than real
      findings"*. **[V]**, read on `main`. **Revision 1 said "anything else in that list is a launch
      abort" without this carve-out, which at 2am is a false stop.**
      *(Absent `red_agent` also masks `human_metric_identity:red` — the `continue` at
      `eval/score_gate0.py:285`, guarded by `not isinstance(agent, dict) or not isinstance(human,
      dict)` at `:284`. **Revision 1 cited `:265-267`, which is the `source_hash` continue** — both
      are in the chain, but `:285` is the one that skips the identity block. **[V]** This dry check
      therefore **cannot** clear P1c. See §6.1.)*

- [ ] **2.6 [auto] ⚠ WRITES TO `runs/` — `$0` seam checks, both arms.**
      **Tell David before running.** This creates `runs/gate0_seam_check_v2/{red,miniwob}/` and writes
      `seam_check.json` into each. It overwrites nothing (both directories are new) and it is `$0`,
      but it is a write into the append-only raw-data tree and **revision 1 marked it plain
      `[auto]` with no ⚠ at all** — `_run_seam_check` calls `_write_json(out_dir / "seam_check.json",
      …)` on both its exit paths, and `main()` mkdirs `out_dir` before dispatch. **[V]** by symbol.
      ```
      python -m tools.gate0_appserver_arm --arm red     --mode paid_gate0_v2 --out-dir runs/gate0_seam_check_v2/red     --seam-check
      python -m tools.gate0_appserver_arm --arm miniwob --mode paid_gate0_v2 --out-dir runs/gate0_seam_check_v2/miniwob --seam-check
      ```
      **PROOF:** `seam_check.json` in each dir with `"ok": true`; exit 0.
      **[V] — the `--mode` / out-of-tree `--out-dir` interaction post-#192 is now VERIFIED, closing
      revision 1's UNVERIFIED #3.** Executed `build_arg_parser()` + `_validate_args()` from
      `refs/pull/192/head` in a throwaway worktree ($0, argparse only, no `runs/` created):
      `--seam-check` with `--out-dir runs/gate0_seam_check_v2/red` is **ACCEPTED**; so is a
      completely out-of-tree scratch path. The pinned-out-dir binding is inside `if real_run:`, and
      `real_run = not args.dry_run and not args.seam_check`. A **real** run with that same out-dir is
      **REFUSED**, as designed. **The commands above stand as written.**
      ⚠ `--out-dir` is resolved to an absolute path **against the process cwd** (`_validate_args`'s
      2026-07-25 fix), so run these from the repo root of the launch tree, not from anywhere else.
      ⚠ Note the seam check inspects by pinned **ID**, not by tag, so `image_id_matches_pin` is
      near-tautological; **2.3's tag→id comparison is the meaningful one.**
      *(On the one-attempt guard: it is in **Phase 3's preamble blockquote**, not in step 3.1 —
      revision 1 misdirected you. It keys on `transcript.raw_appserver.jsonl` / `agent_metrics.json`,
      neither of which a seam check writes, so a seam check into `runs/gate0_paid_v2/<arm>` would not
      burn the attempt. You do not need to: the out-of-tree path is accepted.)*

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
      is the one thing the launcher's only hard money-gate protects against. **Step 2.3a validates
      it at `$0` before you get here. Do not skip it.** A mis-priced pin does not merely mis-report
      cost: `credits_per_usd` is what converts the 250-credit hard breaker into dollars, so a wrong
      rate moves the only live kill switch there is (§5.3).

- [ ] **3.2 [D] — Arm W second.**
      ```
      python -m tools.gate0_appserver_arm --arm miniwob --mode paid_gate0_v2 \
          --model gpt-5.6-sol --out-dir runs/gate0_paid_v2/miniwob \
          --credit-rate-pin <path-to-signed-rate-pin.json>
      ```
      **PROOF:** as 3.1, for `runs/gate0_paid_v2/miniwob/`.
      **⚠ This is a SECOND process, with a SECOND, INDEPENDENT 250-credit hard breaker.** The kill
      ceiling does not carry over from 3.1. §5.3.

- [ ] **3.3 [auto] — Infra-death triage, if it happens.** Verbatim law, prereg `:957-961`:
      *"Relaunch only on infra death before ~10 decisions… Infra death AT or AFTER ~10 decisions =
      the attempt is spent: score whatever artifacts exist with the frozen scorer and bank that
      verdict (`INSUFFICIENT_DATA` is a legitimate outcome). No relaunch without David's explicit OK."*

---

### Phase 4 — Denominators and the post-run freeze  *(⚠ WRITES TO `runs/`; ⚠ P1c may be impassable — read §6.1 first)*

Everything here happens **after** Phase 3's artifacts are banked (§2.1's ordering).

> ⚠ **Phase 4 is the one phase NOT in tick order. Do 4.4 FIRST.** §4's preamble says *"tick these in
> order"*; 4.4 says *"immediately after Phase 3 and before any scoring"* while sitting last. 4.4 wins,
> and the reason is diagnostic, not cosmetic: **4.4 (P5) is what un-masks P1c.** Freezing
> `red_agent` makes `_verify_sources` stop hitting the `continue` at `eval/score_gate0.py:285` and
> start evaluating the identity block, so `human_metric_identity:red` only becomes visible after 4.4.
> Running 4.1 first hides the one failure 4.3 exists to fix. **Order: 4.4 → 4.1 → 4.2 → 4.3b → 4.3c
> → 4.5.**

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

- [ ] **4.3 — P1c: the Red human baseline. ⚠ READ §6.1.** Decomposes into 4.3a/4.3b/4.3c.
      **4.3a now has an owner: it is #195, merged at step 0.4.** Revision 1 said *"THIS STEP HAS NO
      OWNER AND NO IMPLEMENTATION"* — true when written, false now. **4.3b and 4.3c remain open.**

- [ ] **4.4 [A] — P5: freeze the run-produced artifact hashes.** Immediately after Phase 3 and
      **before** any scoring. Non-discretionary: hash exactly what the run produced, change nothing
      else. Three pins in `eval/fixtures/gate0_paid_v2_source_pins.json`:
      `artifact_sha256.red_agent`, `.miniwob_agent`, `.wake_boundary`.
      **PROOF:** each equals `sha256sum` of the corresponding file under `runs/gate0_paid_v2/`; no
      `PENDING_NOT_YET_CAPTURED_…` remains in the file; both values and the timestamp recorded in the
      verdict report.
      **⚠ P5 uncovers P1c, which is why this step runs FIRST in Phase 4** (see the phase preamble).
      Once `red_agent` loads, `_verify_sources` stops hitting the `continue` at
      `eval/score_gate0.py:285` and evaluates the identity block — at which point
      `human_metric_identity:red` fires unless 4.3 is genuinely done.

- [ ] **4.5 [A] — 1.5b: close out `gate0_signature.appserver.json`.** The two fields step 1.5a could
      not fill — `expected_config_sha256` and `expected_codex_mcp_list_sha256` — are now knowable:
      they are this launch's own handshake-receipt values (§3.4).
      **PROOF:** for each arm, both fields equal the corresponding values in
      `runs/gate0_paid_v2/<arm>/handshake-receipt.json`, and no `PENDING_RECOMPUTE_AT_LAUNCH` or
      `REPLACE_WITH_` string survives anywhere in the file.

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
| 1 | Merge **#192** (0.3) | Without `--mode` the run plays spent seeds, stamps the wrong mode, and writes into v1's tree. Three guaranteed source failures plus an un-reportable Arm W. |
| 2 | Land the **§5.3 intervention** — **this is #193** (0.5) | Otherwise v2 is a paid re-run of v1's failing brief. *(Technically a verdict is still reachable without it — it just re-tests a known failure. Dropping it makes the spend pointless, not invalid.)* ⛔ **#193 is currently BLOCKING; this row is not tickable until that is resolved.** |
| 3 | **Re-freeze Cascade B**, all **nine** rows, one commit (1.1) | Missing rows 1-4 → `pin_mismatch:task_sha256` on both arms → `CONSTANCY_BREACH` → **VOID**. Missing rows 5-7 → `expected_pins_hash_mismatch` / `expected_pins_hash_pin_missing` → `INSUFFICIENT_SOURCE`. **⚠ Both the `.appserver` and non-`.appserver` pairs, one commit — see the note below this table.** |
| 4 | **P2** — live-breaker artifact (2.4) | `source_unreadable:live_breaker` + `live_breaker_artifact`. |
| 5 | **P6** — seed hash in the scoring tree (2.2, 5.1) | `frozen_seed_hash`. |
| 6 | **The run**, both arms, `--mode paid_gate0_v2` (3.1-3.2) | — |
| 7 | **P5** — freeze `red_agent`/`miniwob_agent`/`wake_boundary` (4.4) | `source_hash:*` on three artifacts. |
| 8 | **P1a + P1b** — MiniWoB human capture and freeze (4.1-4.2) | `source_unreadable:miniwob_human`, then `source_hash:miniwob_human`. |
| 9 | **P1c** — a Red human baseline stamped `paid_gate0_v2` (4.3 / §6.1) | `human_metric_identity:red`, which P5 un-masks. **4.3a is now #195** (0.4); **4.3b/4.3c still open.** |

> ⛔ **Row 3 is NOT relaxable by #193's new pre-turn pin gate.** The gate reads
> `gate0_expected_pins_{arm}.appserver.json`; the scorer's `audit_paths.<arm>.expected_pins` is the
> **non-`.appserver`** pair. Re-freezing only the `.appserver` pair passes the gate, spends the
> money, and still voids at scoring. **All four fixtures, one commit.** §2.6.

**Steps 1-8 are fully specified. Step 2 is now blocked on #193's review, not on unwritten work, and
step 9 lost its hardest third to #195** — see §6.1. **Every other item in this runbook (#181, #188,
#190, #191, the signature file, P7, the ROM ratification, the deviation log) is discipline, hygiene,
or governance — real obligations, but not mechanical preconditions for the scorer to print a
number.**

### 5.2 Which steps are human-only?

| Step | Why it cannot be delegated |
|---|---|
| **0.1-0.6** merges, **1.2**, **1.4** | Project law: David merges. **0.5 additionally carries a spend-adjacent judgement** — merging #193 ratifies the amended brief the paid brain will read. |
| **1.0** ROM ratification | A subject-matter decision about what the gate is testing. |
| **2.1** move the primary checkout | It is David's checkout; the shared-checkout hazard is a standing law and two sessions have already tripped it. |
| **2.4** P2 write into `runs/` | Append-only raw data. Needs explicit OK. |
| **2.6** seam-check writes into `runs/` | Same tree, lower stakes — tell him, do not ask twice. |
| **2.7** P7 adversarial review | Must be posted by a reviewer and *read* by David; the launch decision is his. |
| **2.8** the spend decision | Prereg `:33-34`. Nothing else authorizes spend. |
| **3.1, 3.2** the paid launches | Spend. |
| **4.1** P1a MiniWoB capture | **Physically human.** `--i-am-human` exists precisely to make a scripted stand-in impossible, and the rig requires a real interactive TTY when writing to the real baseline path. |
| **4.3b / §6.1** P1c Red capture | Same. Post-#195 the Red rig enforces it too: `paid_gate0_v2` is in `HELD_OUT_MODES` and requires `--i-am-human`. |
| **5.3** bank as printed | The one-attempt / no-rescue law. |

Everything else — 1.1, 1.3, 1.5a, 1.5b, 4.2, 4.3c, 4.4, 4.5, 5.4 and every `[auto]` proof command —
is delegable under the normal workflow. **2.3a is `[auto]` but the file it validates is David's to
supply.**

### 5.3 Which steps cost money, and how much?

**Exactly two: 3.1 and 3.2.** Nothing else in this document spends anything. In particular the seam
checks, the dry score, the rate-pin validation, the breaker regeneration, the parity checks and both
human captures are `$0`.

> ⚠ **Revision 1 stated the worst case as "250 credits ≈ $10" combined. That is wrong by 2×.**
> Corrected below, verified by symbol.

**First, the distinction revision 1 lost. Only ONE of these numbers is a limit; the rest are
verdicts.**

| Mechanism | Where | Live or post-hoc? |
|---|---|---|
| `LiveCreditGuard(limit=HARD_CREDIT_CAP, …)` | constructed **inside `_run_real`** (`tools/gate0_appserver_arm.py:1308`), fed by `_combined_observer`, and on trip closes the client and `kill_process_tree(pid)` | **LIVE. The only kill switch that exists.** `HARD_CREDIT_CAP = LIMIT_NORMALIZED_CREDITS = 250` (`:209`, `tools/gate0_credit_breaker.py:51`). |
| `SoftCapWatcher(ARM_SOFT_CREDIT_CAPS[arm], …)` (`:1294`; 125 red / 50 miniwob) | same process | **NEITHER — it only sets `self.warned = True`.** Its own comment: *"this watcher never raises."* It stops nothing. |
| arm caps `$5.00 / 125 cr`, `$2.00 / 50 cr`; combined `$7.00 / 175 cr`; `hard_breaker_exceeded` at `> 250 cr` | `eval/score_gate0.py`'s **`cheap` block** | **POST-HOC SCORING.** Computed from banked `agent_metrics.json` after both arms finish. Each *records* an overrun as `FAIL_CHEAP`. **None can stop a running process.** |

**All [V], read by symbol at `9d8ee51`.**

**Second, the ceiling itself. `LiveCreditGuard` is constructed inside `_run_real` — per arm, per
process — and steps 3.1 and 3.2 are two separate launches.** Each gets its own guard, its own
`AppServerUsageTracker`, and its own running total starting at zero. Nothing is carried between them.

| | Red | MiniWoB | Combined |
|---|---|---|---|
| **EXPECTED — v1 receipts [V]** | $0.41589 / 10.397 cr / 142 acts | $1.02958 / 25.739 cr / 97 acts | **$1.4455 / 36.14 cr** |
| **EXPECTED — prereg §8** (`:908-911`) | ~$0.50 | ~$1.30 | **~$1.80 / ~45 cr** |
| **H-d falsification ceiling** (`:912-914`) — *a reporting threshold, not a limit* | ≤$1.00 / ≤25 cr | ≤$1.60 / ≤40 cr | **≤$2.60 / ≤65 cr** |
| **Post-hoc cap → `FAIL_CHEAP`** — *scored after the money is gone* | $5.00 / 125 cr | $2.00 / 50 cr | **$7.00 / 175 cr** |
| **⚠ HARD CEILING — the live kill, per arm** | **250 cr ≈ $10** | **250 cr ≈ $10** | **500 cr ≈ $20** |

**Read it this way:**

- **Expect $1.45-$2.60.** Everything in the first three rows is an expectation or a reporting
  threshold. Exceeding the H-d row is a *recorded falsification*, not a failure — report it as such.
- **$7.00 combined is where the verdict turns `FAIL_CHEAP`. It is not where spending stops.** A run
  that blows through it keeps running until the live guard trips or the turn ends.
- **⚠ The most you can lose, before anything kills anything, is ~$20 — about 14× the expected
  spend.** 250 credits per arm at the rate pin's `credits_per_usd: 25`, times two launches. If the
  rate pin carries a different rate, **this number moves** — which is why step 2.3a makes you read
  it at `$0` first.
- The `250` in `eval/score_gate0.py`'s `hard_breaker_exceeded` **is** a combined figure, and revision
  1 conflated it with the guard. It fires only if the *sum* of both banked arms exceeds 250, i.e. it
  is a post-mortem note that a per-arm guard let something through. **It has never stopped anything
  and cannot.**

Watch **MiniWoB**, not Red: v1 used 51.5% of its arm cap versus Red's 8.3%, and the repaired
`press_key` means more steps per episode. The guard is armed before the turn opens
(`:1294`, `:1308-1310`), so an unbounded settle loop — precisely what the amended §5.3 brief asks
for — kills the process rather than the budget. **That is the mechanism the ~$20 figure describes,
and the settle instruction is what makes it worth stating honestly rather than optimistically.**

### 5.4 What is the earliest point at which the attempt can be aborted cheaply?

**Before a single dollar moves, in this order — and the first three are free and instant:**

1. **2.1 — `git rev-parse --abbrev-ref HEAD`, in the primary checkout.** It is on
   `fix/miniwob-key-name-press` today. **[V]** If it is not on the launch commit, `world_mcp.py`'s
   blob is `967866ab…` instead of `b4ae7cf3…` and a launch *would* abort at
   `tools/gate0_appserver_arm.py:1251` for $0. **This is the cheapest abort in the document and it
   is one command.** ⚠ **Run `git rev-parse` — do NOT run the launcher to "see if it aborts".** The
   abort happens *after* `main()` has mkdir'd the out-dir and `_run_real` has created
   `codex-home/` with seeded auth, `world/` and `launch/.codex/`. Free, but it litters the
   append-only tree with credential material. §1.4.
2. **2.2 — `sha256sum` of the seed file.** `0e1861d3…` instead of `4ede74d3…` means CRLF, and every
   pin in the tree is suspect. $0.
3. **2.3 — `docker image inspect`.** A stale tag hard-fails at `:1240-1242` before any model call. $0.
4. **2.3a — `load_credit_rate_pin(path, model)` called directly.** New in revision 2. The
   `--credit-rate-pin` flag is *refused* on every $0 path, so this is the only way to prove the file
   before the command that spends. $0. **It also tells you the rate that sets §5.3's ~$20 ceiling.**
5. **2.5 — the dry score.** This is the *diagnostic* abort: it exercises the entire `source` and
   `constancy` tier against the real fixtures and prints, in one line, exactly which preconditions
   are still open. Everything except the four run-produced artifacts is checkable here. $0.
6. **2.6 — seam checks.** Exercises the live MCP handshake and tool inventory. $0.
7. **Inside `_run_real`, before the model is invoked** — the credit-rate pin (`:1227`), docker
   resolution (`:1229`), image ID (`:1239-1242`), host-code-clean-at-HEAD (`:1243-1248`), host↔image
   parity (`:1249-1251`), and the live tool inventory vs the frozen allowlist (`:1272-1275`). All
   raise `SystemExit` at $0.
8. **⚠ NEW, post-#193 — `refuse_if_expected_pins_stale(receipt, arm)`, at "THE LAST `$0` INSTANT".**
   Immediately after the handshake receipt is written, immediately before the app-server client
   opens. Covers **all 20 `PIN_FIELDS`** via the frozen `check_gate0_codex._expected_failures`, so a
   stale fixture is a `$0` refusal instead of a full-price VOID that burns the held-out seed block.
   Not reachable from `--dry-run` or `--seam-check` (neither enters `_run_real`).
   **⛔ CAVEAT — it reads the `.appserver` pair ONLY.** The scorer re-audits against the
   non-`.appserver` pair. **Passing this gate is not evidence that the re-freeze was complete.**
   §2.6, and §5.1 row 3.

**After that, the next abort point is the live credit guard at 250 credits — per arm, i.e. roughly
$10 for that arm, not $0, and not combined.** There is no cheap abort mid-run. Run steps 1-6 in
order and stop at the first failure; 7 and 8 are the launcher's own, and you do not get to choose
whether they run.

---

## 6. Blockers with no owner — the honest list

### 6.1 ⚠ P1c is three steps, not one — and one of them now exists

This is the most important finding in this document. **Revision 1's heading said *"no open PR touches
it"*. #195 (`fix/gate0-red-capture-mode`) touches it — it *is* 4.3a — and #195's own body says
*"PR #194's runbook reached the same conclusion independently."* The decomposition below was right;
only the ownership line was stale.

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

- **4.3a [A] — ✅ DONE, this is PR #195**, merged at step **0.4**. It adds a required `--mode` with
  no default (choices read from `eval.score_gate0.MODES`), a per-mode `MODE_CONFIG` mirroring
  `capture_gate0_baseline_miniwob.py`'s, `HELD_OUT_MODES = {paid_gate0, paid_gate0_v2}` requiring
  `--i-am-human`, and `MODE_CONFIG["paid_gate0_v2"]["real_out"] =
  runs/gate0_paid_v2_human_baseline/red`. **[V]** read from `refs/pull/195/head`.
- **4.3b [D] ⚠ HUMAN-ONLY ⚠ WRITES TO `runs/`** — David replays Red from the fixed bedroom start:
  starter acquisition, first rival battle, sustained exit. v1's human run took **233.288 s** of
  detected play, so this is minutes, not hours — but it is a real cold attempt under the one-attempt
  rule. Post-#195 the command is
  `uv run python tools/capture_gate0_baseline_red.py --mode paid_gate0_v2 --i-am-human`;
  `--out` defaults correctly per mode.
- **4.3c [A]** — re-point `artifact_paths.red_human` at the new artifact **and** re-freeze
  `artifact_sha256.red_human`, in the same commit. Both, or the pin breaks.
  **#195's D5 makes this a pre-registration deviation in its own right, not merely plumbing:** the
  prereg says P1c *"is satisfied by a FRESH CAPTURE … producing a new artifact"* and names no third
  step, but all three source-pin fixtures pin `artifact_paths.red_human` at the banked
  `readiness_dev` file with the same frozen digest `5144a5b3…`, so a fresh capture either
  **overwrites an append-only banked artifact** or lands somewhere **nothing reads**. D5 records
  that gap. **Do not treat 4.3c as optional cleanup.**

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

**Bottom line: the sequence CAN reach a valid verdict. P1c is still the narrowest part of it, but it
is now one merge (4.3a = #195), one human replay (4.3b) and one fixture commit (4.3c)** — not, as
revision 1 had it, three pieces of unstarted work with no owner.

### 6.2 The `_measured_against` block names a stale image tag — **already fixed in #181**

⚠ **Revision 1 wrote this section and then, at step 1.4, offered to close the PR that fixes it.**

`eval/fixtures/gate0_paid_v2_source_pins.json`'s `_measured_against` records
`miniwob-mcp-world sha256:8bb3358e1421…` as the environment the 6-checkbox measurement was made
against. **[V]** `DAVID_BASELINES.md:110-112` calls `miniwob-mcp-world` *"stale by definition"*, and
the launcher hardcodes `miniwob-world` (`tools/gate0_appserver_arm.py:200`). The live pinned image is
now `sha256:ee12a2f0…`. Per prereg §4.1.2 the **frozen block binds, not the re-derivable rule**, so
this is **not** a licence to re-draw — but a post-#180 re-measurement disagreeing about which seed
renders six checkboxes would be a **finding against the rebuild**, and H-e's test case (`558952`)
rests on it.

**Both halves are already answered by #181, which is why §3.3 says rebase it rather than close it:**

1. **The stale tag is fixed.** #181 rewrites `_measured_against` to `miniwob-world` /
   `sha256:ee12a2f0…` and adds `superseded_world_image_id` for the old one. **[V]** from its diff.
2. **The `$0` re-measurement this section asks for has been done, and it agrees.** #181's
   `re_measured_post_p8` records a reset-only render of the five frozen seeds against the new image:
   **417545 = 5, 662948 = 5, 660918 = 2, 981149 = 2, 558952 = SIX** — exactly the frozen block. It
   also records Submit's measured top-y as **161 / 161 / 104 / 104 / 180**, so `558952` still renders
   Submit 3 px outside the 177 px clickable band and **H-e is still a live test**. The method was
   validated against the *superseded* image first, reproducing the same counts, so the agreement is a
   fact about the two images rather than an artifact of a new instrument. No seed was changed.

**This closes revision 1's UNVERIFIED #6 — by citation, not by my own measurement.** I read #181's
diff; **I did not re-run the render.** If #181 is closed rather than rebased, this evidence leaves the
tree and #6 reopens.

### 6.3 P7 has no reviewer assigned and no deadline

Stated so it is not forgotten between now and Phase 2.

### 6.4 Two known-bad comment lines in `world_mcp.py`

`:250` claims "confirmed reading 4 at Stage 4" (it reads 3) and `:255` says "Only `>= 2` is
meaningful". Both are queued for a batched world PR. **Do not fix them as part of any step in this
runbook** — `world_mcp.py` is baked into both images, so touching it fires Cascade A (§3.1) and
forces a rebuild plus a ten-file re-pin. Out of scope here, deliberately.

### 6.5 ⚠ `tools/run_gate0_codex.ps1` keeps the v1 brief, and SOURCES.md still points at it

**Out of scope for the v2 verdict — in scope for not launching the wrong thing.**

`tools/run_gate0_codex.ps1:687` holds **its own copy** of the v1 task text
(`$CommonTask = 'Use only the connected world MCP tools … Stop when the stated task is complete.'`)
and `:688` builds `$Task = $TaskSentence + "`n" + $CommonTask + "`n"` — the same formula
`task_text_for` uses. **[V]**, read at `9d8ee51`. **Nothing cross-checks the two launchers**, and
step 1.1 scopes the change to `gate0_appserver_arm.py` only. After #193 lands, the two diverge.

Two consequences, and the second is the one that bites:

1. **An operator could reach for the wrong launcher.** The `.ps1` is the *exec-path* launcher; the v2
   attempt uses the **app-server** launcher (`python -m tools.gate0_appserver_arm`). Post-#193 the
   `.ps1` would launch the **v1** brief at full price. Nothing stops it. **Phase 3's commands are the
   only launch commands in this document; there is no `.ps1` variant of them.**
2. **`eval/fixtures/gate0_expected_pins.SOURCES.md` records the wrong provenance.** `:24` says
   `task_sha256` is *"AST-extracted and evaluated from `tools/run_gate0_codex.ps1`'s
   `$BrainConfigText`/`$TaskSentence`/`$CommonTask` assignments"*, and `:76-83` names
   `run_gate0_codex.ps1` — **not** the app-server arm — as the file whose change triggers
   re-derivation. **After step 1.1 the committed `task_sha256` is no longer derivable from the file
   SOURCES.md says it comes from, and a future re-derivation "by the book" would silently restore the
   v1 digest.** This is why SOURCES.md is Cascade B's ninth row (§3.2) and why step 1.1 item 3 asks
   for that row to be corrected explicitly.

Revision 1 scoped the `.ps1` out under §5 and that scoping is still right for the *verdict*. It was
written when the divergence was zero; it is now three revisions wide.

---

## 7. UNVERIFIED register

Everything I could not check, and why. Nothing here was smoothed over.

**Revision 2 closed three of the seven and changed the handling of a fourth. Nothing was promoted
without a check; where the answer came from someone else's evidence rather than my own execution,
the row says so.**

| # | Status after revision 2 |
|---|---|
| **#3** — `--seam-check` + `--mode` + out-of-tree `--out-dir` post-#192 | ✅ **CLOSED by execution.** See step 2.6. |
| **#5** — whether further reviews landed | ✅ **CLOSED, and it mattered** — three verdicts had moved, one to **BLOCKING**. See §1.2. Re-check again before merging; this row is permanently time-of-check. |
| **#6** — does the 6-checkbox property survive the #180 rebuild | ⚠ **ANSWERED BY CITATION, not by my own measurement.** #181's `re_measured_post_p8`. See §6.2. **Reopens if #181 is closed.** |
| **#2** — the rate-pin path | ⚠ **STILL UNVERIFIED, but no longer a 2am surprise** — step **2.3a** makes it a `$0` check instead of first contact at the moment of spend. |
| **#1, #4, #7** | Unchanged. Still open, still marked. |

| # | Claim | Why unverified |
|---|---|---|
| 1 | **The LF-forced `git archive \| docker build -` recipe.** The fragment `git -c core.autocrlf=false -c core.eol=lf archive HEAD` appears in five fixture provenance notes and at `HANDOFF.md:102`, but **the `\| docker build -` half exists nowhere in the repo** as a runnable command, and no build script exists. The only committed build lines are the CRLF-unsafe naive forms — `DAVID_BASELINES.md:95` (a real command) and `Dockerfile:7` (a comment example). | **Moot for v2** — §1.4 shows no rebuild is needed. But if one ever is, the recipe must be authored, and **I did not author or test one here.** I will not print a command I have not run. |
| 2 | **The rate-pin file path for 3.1/3.2.** Only one rate-pin JSON exists on disk (`runs/gate0_paid/red_exec_noop_2026-07-22/paid/credit_rate_pin.json`), and v1's receipts do not record which path was passed. | **STILL OPEN.** Not recoverable from artifacts; David must supply and verify it. **⚠ Revision 2: marking it was NOT adequate on its own.** `--credit-rate-pin` is refused on every `$0` path (`_validate_args`) and first loaded at `_run_real:1227` — *inside* the paid launch — so David's first contact with an unproven file was the command that spends. **Step 2.3a now calls `load_credit_rate_pin(path, model)` directly at `$0`.** The path is still unknown; discovering it is the wrong one is now free. |
| 3 | ~~**`--seam-check` + `--mode` + an out-of-tree `--out-dir` post-#192**~~ | ✅ **CLOSED 2026-07-28, by execution.** Ran `build_arg_parser()` + `_validate_args()` from `refs/pull/192/head` in a throwaway detached worktree: `--seam-check` with `--out-dir runs/gate0_seam_check_v2/red` is **ACCEPTED**, as is a fully out-of-tree scratch path; a **real** run with that same out-dir is **REFUSED**. The pinned-out-dir binding sits inside `if real_run:`, and `real_run = not args.dry_run and not args.seam_check`. **Step 2.6's commands stand as written.** $0, argparse only, no `runs/` directory created. |
| 4 | **The stock (non-hack) Pokémon Red ROM digest.** I verified the hack's digest and CGB flag; I did not obtain a stock ROM to contrast. | Out of scope, and I am not asserting provenance beyond the zip's own filename. |
| 5 | **Whether further reviews have landed on the open PRs** since this was written. GitHub's `reviews` array is empty for all of them; the verdicts are comment-thread text. | ✅ **CHECKED 2026-07-28 for revision 2, and it mattered** — #188 and #192 had moved to APPROVE, #190 to APPROVE, and **#193 to BLOCKING**. §1.2's table is current as of that check. **Permanently time-of-check: re-read before every merge.** |
| 6 | **Whether the P9 seed block's 6-checkbox property survives the #180 rebuild** (§6.2). | ⚠ **ANSWERED, by citation rather than by my own measurement.** #181's `re_measured_post_p8` records the reset-only re-render against `sha256:ee12a2f0…`: 417545=5, 662948=5, 660918=2, 981149=2, **558952=SIX**, Submit top-y 161/161/104/104/180, method validated against the superseded image first. **I read #181's diff; I did NOT re-run the render.** §6.2. **Reopens if #181 is closed rather than rebased** (§3.3). |
| 7 | **That `_red_success` is satisfiable by the brief.** The prereg's §5.4 clause-by-clause proof is an argument, not a measurement; C6 and C8 were **never evaluated by v1** and are unproven in practice (prereg `:687`, `:689`). | **STILL OPEN, and revision 2 makes it sharper rather than closing it.** §5.4's proof is not merely unmeasured — it is **internally inconsistent**: its C5 margin is computed on the `explore` path its own C7 defence rules out (§2.2, deviation D6). #193 amended the brief for exactly this reason, and **#193's own review BLOCKS on whether the amended arithmetic clears the ten-row bar** (8 vs 10 under one compliant reading). **Only the run can settle it — but do not launch while that argument is unresolved.** |

---

## Sources

All line references are against `origin/main` = `322499f` unless stated. **Revision 2's own
verifications were read at `9d8ee51`** (this PR's head, whose code files are byte-identical to
`origin/main`) **and at the PR head commits named below**; where a symbol was cited, the commit it
was read at is given beside it.

**Read for revision 2, at the commits named:**

- **PR #193** `refs/pull/193/head` = `ce43fbb` (commits `2a4daad` → `ec881e4` → `ce43fbb`) —
  `COMMON_TASK_SUFFIX`, `refuse_if_expected_pins_stale`, `PIN_FIELDS` scope comment, D6
- **PR #195** `refs/pull/195/head` = `a4e5969` — `MODE_CONFIG`, `HELD_OUT_MODES`, D5
- **PR #192** `refs/pull/192/head` = `e664074` — `_validate_args`' `if real_run:` out-dir binding
  (executed, not only read)
- **PR #181** `refs/pull/181/head` = `c4b642f` — `_measured_against`, `re_measured_post_p8`
- **PR #188** `7d6b2ee`, **PR #191** `bef7797`, **PR #190** `ce26c7e` — deviation blocks D2/D3, and
  the current review verdicts
- `tools/gate0_appserver_arm.py` @ `9d8ee51` — `HARD_CREDIT_CAP` `:209`, `SoftCapWatcher` `:709-732`,
  `LiveCreditGuard(limit=…)` `:1308`, `_run_seam_check` `:1007-1055`, `_run_real` `:1222-1262`,
  `main` `:1361-1379`
- `tools/gate0_appserver_launch.py` — `class LiveCreditGuard` `:453`
- `tools/gate0_credit_breaker.py` — `LIMIT_NORMALIZED_CREDITS = 250` `:51`
- `tools/gate0_codex_credit_rate.py` — `CreditRateNotPinned` `:107`, `load_credit_rate_pin` `:112`
- `tools/run_gate0_codex.ps1:687-688` — the v1 `$CommonTask` / `$Task`
- `eval/score_gate0.py` — the identity-masking `continue` `:285` (guard `:284`), the `source_hash`
  `continue` `:267`, `cheap` block and `hard_breaker_exceeded`
- `eval/fixtures/gate0_expected_pins.SOURCES.md:24`, `:76-83` — `task_sha256` provenance
- `eval/fixtures/gate0_signature.appserver.json` — the two `PENDING_RECOMPUTE_AT_LAUNCH` fields

**Revision 1's original source list follows, unchanged:**

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
