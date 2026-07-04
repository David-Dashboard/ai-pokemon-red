---
name: session-wrap-up
description: Invoke at the end of any ai-pokemon-red working session — updates HANDOFF.md, auto-memory, and LEARNINGS.md, writes David's summary, and commits/pushes the feature branch so a fresh (possibly weaker) session can continue.
---

# Session wrap-up

Goal: a fresh session with ZERO context must be able to continue from what you leave behind.
Run this checklist top to bottom. Do not skip steps because the session "was small".

## 0. Get the real date first

```powershell
Get-Date -Format yyyy-MM-dd
```
Use the actual clock output, always as an absolute date (`2026-07-04`), never "today"/"yesterday".
The repo CLAUDE.md session rule is explicit: "date = actual clock, check it".

## 1. Update HANDOFF.md (`E:\AI_Personas\10_pokemon_and_chess_and_office\ai-pokemon-red\HANDOFF.md`)

HANDOFF.md is a stack of dated blocks, newest on top. To add yours:

1. **Demote the previous newest block.** The current top block starts with a line like
   `**⇒⇒ NEWEST (2026-07-03, day close) — <headline> ⇒⇒**`. Leave its content in place —
   it simply becomes the second block. Do NOT delete or rewrite old blocks.
2. **Update the `_Last updated:_` line** (near the top of the file, after the intro paragraph)
   to your date + a one-sentence headline of this session. The old `_Last updated:_` text
   moves down to become a `_Prior update: <old text>_` line sitting between your new block
   and the demoted one (this is the existing pattern in the file — see lines around the
   2026-07-03 blocks).
3. **Insert your new block above the demoted one**, in the same shape:

```markdown
**⇒⇒ NEWEST (2026-07-04) — <one-line headline of the session> ⇒⇒**
1. **DONE:** <each completed item, with evidence: PR #, file path, run dir, verdict, cost>
2. **DONE:** ...
3. **PENDING / NOT DONE:** <each item started but unfinished, and exactly where it stands>

**⇒ NEXT (priority order):** (1) ...; (2) ...; (3) ...
```

Rules for the block:
- **State done vs pending EXPLICITLY.** Never leave a task's status implied. A reader must
  not have to guess whether something ran, passed, or was abandoned.
- Every claim of "done"/"pass" needs the evidence pointer produced this session
  (report path under `reports/`, run dir under `runs/`, PR number) — per `.claude/PROTOCOL.md` §2.
- If paid runs happened, include costs (the existing blocks carry a
  "**Paid ledger today (<date>)**" line with per-run $ and a running total — keep that pattern).
- Absolute dates everywhere inside the block too.

## 2. Write the summary for David (in chat, not a file)

Format (from `~/.claude/CLAUDE.md` "Output" rules — files touched + what changed, NOT a
paragraph of reasoning):

- **Files touched:** one line per file — path + what changed in it.
- **Run outcomes + costs:** each paid/long run — verdict + $ figure.
- **Awaits David:** merges he must do, decisions he must make, PRs open for his eyes.

Keep it terse. No reasoning narrative.

## 3. Update auto-memory

Memory dir: `C:\Users\Succe\.claude\projects\E--AI-Personas-10-pokemon-and-chess-and-office\memory\`

- **Update existing files over creating duplicates.** E.g. a new entity-gate result goes into
  the existing `entity-v3-verdict.md`, not a new file. Only create a new file for a genuinely
  new topic.
- Each topic file gets a matching **one-line index entry in `MEMORY.md`** of the form:
  `- [Title](filename.md) — <one-line current state>`. When you update a file, update its
  index line too so the line reflects the LATEST state.
- **Delete memories that turned out wrong** (or correct them in place) — stale memory is
  worse than no memory.
- Memory files are the exception to "don't write report files": they are read by future
  sessions, not the parent agent.

## 4. LEARNINGS.md — only if the session produced a durable lesson

`E:\AI_Personas\10_pokemon_and_chess_and_office\ai-pokemon-red\reports\LEARNINGS.md` is the
chronological per-iteration log. If this session produced a method lesson or a gate result
(pass OR fail with diagnosis), append a dated bullet section at the top area following the
existing pattern (`## 2026-07-03 (latest) — <headline>` with `- **What:**` / `- **The finding:**`
/ `- **Method note:**` bullets). Skip this step for pure-infra sessions with nothing to teach.

## 5. Commit and push — feature branch only

```powershell
git -C E:\AI_Personas\10_pokemon_and_chess_and_office\ai-pokemon-red status
git -C E:\AI_Personas\10_pokemon_and_chess_and_office\ai-pokemon-red rev-parse --abbrev-ref HEAD
```

- You must be on a **feature branch**, never `main` (repo CLAUDE.md: "never work on `main`
  directly"). If you find yourself on `main` with changes, branch first.
- Commit the wrap-up changes (HANDOFF.md, LEARNINGS.md, any session artifacts) with a
  descriptive message, then push. Push **via the PowerShell tool** (`git -C ... push -u origin <branch>`) —
  `Bash(git push*)` is deny-listed by design so pushes route through PowerShell's prompt; using
  PowerShell is the sanctioned route, NOT a safety-invariants §9 route-around.
- If `pretool_commit_gate` denies the commit because the fast invariant tests fail, do NOT bypass it
  (no `--no-verify`, no reworded command): leave the wrap-up files in the working tree, record the
  red state + the uncommitted paths in the HANDOFF block and the chat summary, and surface it to David.
- **Do NOT merge anything during wrap-up.** Merging happens only through the separate
  review loop (PR + posted adversarial review comments + green CI); genuinely contentious
  or large changes wait for David regardless. Wrap-up = commit + push, stop there.
- Remote: `https://github.com/David-Dashboard/ai-pokemon-red.git` (origin).

## 6. Leave disarmed things alone

- `LEDGER.md.disarmed` exists at the repo root. David disabled the ledger hooks by renaming
  it. Do NOT rename it back to `LEDGER.md`, delete it, or "helpfully" re-arm it — anything
  David disabled stays disabled unless he says otherwise.
- Same principle for any other `.disarmed` / commented-out hook or config you notice.

## Final check before ending the turn

- [ ] HANDOFF.md: new NEWEST block on top, `_Last updated:_` refreshed, previous block demoted intact
- [ ] Done vs pending explicit, with evidence pointers and costs
- [ ] David summary posted in chat: files touched / run outcomes + costs / awaits David
- [ ] Memory files + MEMORY.md index lines updated (edited in place, wrong ones removed)
- [ ] LEARNINGS.md bullet appended if the session earned one
- [ ] Committed and pushed to the feature branch; nothing merged
- [ ] `LEDGER.md.disarmed` untouched

## Sources

- `E:\AI_Personas\10_pokemon_and_chess_and_office\ai-pokemon-red\HANDOFF.md` (block structure, `_Last updated:_`/`_Prior update:_` lines, paid-ledger pattern)
- `E:\AI_Personas\10_pokemon_and_chess_and_office\ai-pokemon-red\CLAUDE.md` (session rules: date = actual clock, done vs pending explicit; branch/PR workflow)
- `E:\AI_Personas\10_pokemon_and_chess_and_office\ai-pokemon-red\.claude\PROTOCOL.md` (§2 grounded progress — evidence for every "done")
- `E:\AI_Personas\10_pokemon_and_chess_and_office\ai-pokemon-red\reports\LEARNINGS.md` (entry format)
- `C:\Users\Succe\.claude\projects\E--AI-Personas-10-pokemon-and-chess-and-office\memory\MEMORY.md` (index-line format)
- `C:\Users\Succe\.claude\projects\E--AI-Personas-10-pokemon-and-chess-and-office\memory\review-process.md` (merge authorization scope — why wrap-up itself never merges)
- `C:\Users\Succe\.claude\CLAUDE.md` (David's summary format, absolute dates, session-note rule)
