# 2026-06-25 — Phase A pre-checks for the ADR-002 HUD-grounding gate (+ the Claude-over-MCP test method)

Roadmap-v2 Rung-0 **Phase A** = the three cheap, read-only empirical checks that gate the gate (they can
invalidate its shape before any code). Run against `runs/2026-06-23_cavenoire_explore` (frames + `ram.bin`,
n=4000; offline RAM/frame inspection — **no MCP session, no Claude brain**; that harness is for the gate run
itself, Phase D). **Verdict: 2 of 3 pre-conditions met; the gate's shape is NOT yet confirmed — Check 2 (the
independent consequence channel) is the keystone and is still AMBER, so the §9 decoy-rejection arm cannot yet
be scored.**

## Check 1 — HUD format: DIGITS, and visible during gameplay (GREEN)
- Frame 500 (item menu): "HP. **10/10**". Frame 1500 (in-dungeon **gameplay**): the bottom status bar reads
  "**HP 8/10   ENEMY 1/3   B 2F**". So life is shown as **digits** (not hearts/pips), and it is **on-screen
  during normal play**, not only in menus.
- ⇒ `read_text`/OCR is the right primitive (not icon-count/segmentation), and life can be grounded
  **continuously**, not just at menu moments. The "digits vs pips" risk is closed.

## Check 3 — the life RAM oracle EXISTS and is found: `0xD389` (GREEN, reproducible)
- Scanning `ram.bin` for the byte that reads **7 at frame 100** (visible HP 7/10) **AND 10 at frame 500**
  (visible 10/10) returns **exactly one** address: **`0xD389` = current HP** (distinct values over the full run
  `{0,2,4,5,7,8,10,15}`, behaviourally steps down on damage). Plausible max-HP regs: `0xD08B`/`0xD589` (read 10
  at both, few distinct) — not needed (max is the displayed "/10").
- **Reproducible from a clean checkout** via a committed 18 KB fixture (the two anchor frames + their
  screenshots — no full corpus needed): `uv run python -m eval.find_hp_addr eval/fixtures/cavenoire_hp_oracle
  --anchors 0:7 1:10` → `['0xD389']`. (The full-run distribution above needs the gitignored recording; the
  fixture proves the *uniqueness-against-the-anchors* claim, which is the load-bearing one.)
- **Caveat (the byte reads above its max):** max HP = 10, but the byte hits **15 on 4 of 4000 frames**
  (`477,478,561,645` — all at screen transitions). That's 0.1% transient garbage (mid-transition reads), not a
  steady second meaning, so `0xD389` is a clean-enough oracle **if scoring clamps to "valid only when ≤ max"**
  and skips transition frames. It is single-run evidence: re-confirm `0xD389` (and this 0–10 invariant) on a
  fresh capture before leaning on it for a real gate score.
- ⇒ The plan's hardest blocker ("the life RAM oracle does not exist yet — nothing to score against") is
  **RESOLVED**. Wired into the oracle log (NOT the wire): `watch={"x":0xC504,"y":0xC503,"hp":0xD389}` in
  `world_mcp.py` + `play_cave_noire.py`.
- **Bonus — a decoy set is *enumerable* for the gate's rejection arm:** the same status bar carries **ENEMY
  count (1/3)** and **floor (B 2F)** — plausible-but-wrong digit regions to hand the loop. They are not yet
  *usable*: §9 rejects a decoy by **consequence-correlation failure**, which needs the Check-2 consequence
  signal. Free to enumerate now; pending Check 2 before they can score the rejection arm.

## Check 2 — an independent pixel consequence: AMBER (the live risk, keystone)
- The keystone the plan flagged. There are **29 HP-drop (damage) events**; **one was inspected** (frame 233,
  HP 10→8) and it was a **menu/floor-transition** ("B 1F"), not a clean in-combat damage flash. So **at least
  that one HP delta is confounded** with a screen transition (a whole-screen pixel change not specific to
  damage); **the confounding frequency across the other 28 is unmeasured** — quantifying it (clean vs
  transition-confounded) is Phase B work and decides whether the corpus is mostly usable or needs a
  combat-focused recapture.
- A clean pixels-only "I took damage" event *independent of* the HP digits and *independent of* a transition
  was **not isolated** in this recording. The on-screen enemies + the ENEMY counter are a candidate consequence
  channel, but the keystone consequence primitive is **not yet demonstrated**.
- ⇒ This is the real open risk and where Phase B/C effort goes: either find/curate a combat-focused capture with
  clean damage events, or accept a transition-aware consequence signal. **Do not hand-wave it** — without a
  consequence independent of the digits, the loop can ground life only against itself (circularity), which is the
  ADR-002 §9 decoy arm's whole point.

## Net + next
Phase A clears **2 of 3 pre-conditions** (digits · groundable continuously · life oracle exists + a decoy set
enumerable) and **localizes the one hard problem to the consequence channel** (Check 2). The gate's shape is
**not confirmed**: Check 2 is the keystone (§9's decoy-rejection arm structurally needs an independent
consequence signal) and it is AMBER, so a "looks-right = pass" call here would be the exact over-claim ADR-002
§11 warns against. **Before the gate can be declared sound, Check 2 must go green** (isolate a clean pixels-only
damage consequence) **or the gate must be redesigned** to not require an independent consequence. Proceed to
**Phase B** (operationalize
§9: pin the agreement metric + ≥X% threshold, the ≤Y% decoy bound, run length, region-candidate source = a fixed
coarse grid / hand-specified HUD boxes — NO segmentation in Rung 0), then **Phase C** (build `read_text` +
`whats_changed` + the consequence signal on `world_mcp.py`). Gate discipline (ADR-002 §11) unchanged.

## Testing method (NEW, 2026-06-25) — the gate run (Phase D) will use a real Claude over MCP
**Protocol declaration, not what produced Phase A.** Phase A above was **offline inspection of a prerecorded
RAM dump + frames** — no MCP, no Claude brain. **From the gate run onward (Phase D)**, evaluation uses a real
Claude (a Claude Code instance) as the System-2 brain, connected to this project's `world_mcp.py` over MCP —
not `ScriptedBrain`/`ExploreBrain`. This realizes the ADR-001 S4 seam as the standing test harness: the world
is the MCP server (System 1 + perception), the agent is the MCP client.
- **The ADR-002 gate is run this way:** the live Claude brain hypothesizes "region R = my life" through the MCP
  tool surface, and its grounded life-detector is scored against the `hp=0xD389` oracle in `oracle.jsonl`
  (RAM stays off the wire — scoring only).
- **Launcher:** a clean-slate fresh Claude Code brain in `../aria-mcp-test/` (`.mcp.json` + thin brief), wired to
  an in-cavern state. `ExploreBrain` remains the *free System-1 autopilot* the brain delegates routine tiles to
  (via `explore`/`goto`) — it is no longer the *evaluated* policy; the evaluated policy is the Claude brain.
