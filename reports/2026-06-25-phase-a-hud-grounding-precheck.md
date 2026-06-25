# 2026-06-25 — Phase A pre-checks for the ADR-002 HUD-grounding gate (+ the Claude-over-MCP test method)

Roadmap-v2 Rung-0 **Phase A** = the three cheap, read-only empirical checks that gate the gate (they can
invalidate its shape before any code). Run against `runs/2026-06-23_cavenoire_explore` (frames + `ram.bin`,
n=4000). **Verdict: the gate's shape is CONFIRMED on 2 of 3; the consequence channel is the live risk.**

## Check 1 — HUD format: DIGITS, and visible during gameplay (GREEN)
- Frame 500 (item menu): "HP. **10/10**". Frame 1500 (in-dungeon **gameplay**): the bottom status bar reads
  "**HP 8/10   ENEMY 1/3   B 2F**". So life is shown as **digits** (not hearts/pips), and it is **on-screen
  during normal play**, not only in menus.
- ⇒ `read_text`/OCR is the right primitive (not icon-count/segmentation), and life can be grounded
  **continuously**, not just at menu moments. The "digits vs pips" risk is closed.

## Check 3 — the life RAM oracle EXISTS and is found: `0xD389` (GREEN)
- Scanning `ram.bin` for the byte that reads **7 at frame 100** (visible HP 7/10) **AND 10 at frame 500**
  (visible 10/10) returns a **unique** address: **`0xD389` = current HP** (max HP = 10; range 0–15 over the run,
  8 distinct values, behaviourally steps down on damage). Plausible max-HP regs: `0xD08B`/`0xD589` (read 10 at
  both, few distinct) — not needed (max is the displayed "/10").
- ⇒ The plan's hardest blocker ("the life RAM oracle does not exist yet — nothing to score against") is
  **RESOLVED**. Wired into the oracle log (NOT the wire): `watch={"x":0xC504,"y":0xC503,"hp":0xD389}` in
  `world_mcp.py` + `play_cave_noire.py`.
- **Bonus — a free decoy set for the gate's rejection arm:** the same status bar carries **ENEMY count (1/3)**
  and **floor (B 2F)** — plausible-but-wrong digit regions to hand the loop as decoys (it must reject them).

## Check 2 — an independent pixel consequence: AMBER (the live risk)
- The keystone the plan flagged. Of the 29 HP-drop (damage) events, the inspected one (frame 233, HP 10→8) was
  a **menu/floor-transition** ("B 1F"), not a clean in-combat damage flash — i.e. **several HP deltas are
  confounded with screen transitions** (a whole-screen pixel change that isn't specific to damage).
- A clean pixels-only "I took damage" event *independent of* the HP digits and *independent of* a transition
  was **not isolated** in this recording. The on-screen enemies + the ENEMY counter are a candidate consequence
  channel, but the keystone consequence primitive is **not yet demonstrated**.
- ⇒ This is the real open risk and where Phase B/C effort goes: either find/curate a combat-focused capture with
  clean damage events, or accept a transition-aware consequence signal. **Do not hand-wave it** — without a
  consequence independent of the digits, the loop can ground life only against itself (circularity), which is the
  ADR-002 §9 decoy arm's whole point.

## Net + next
Phase A **greenlights the gate's shape** (digits · groundable continuously · life oracle exists · decoys free)
and **localizes the one hard problem to the consequence channel** (Check 2). Proceed to **Phase B** (operationalize
§9: pin the agreement metric + ≥X% threshold, the ≤Y% decoy bound, run length, region-candidate source = a fixed
coarse grid / hand-specified HUD boxes — NO segmentation in Rung 0), then **Phase C** (build `read_text` +
`whats_changed` + the consequence signal on `world_mcp.py`). Gate discipline (ADR-002 §11) unchanged.

## Testing method (NEW, 2026-06-25) — tests run via a real Claude over MCP
**From now on, evaluation uses a real Claude (a Claude Code instance) as the System-2 brain, connected to this
project's `world_mcp.py` over MCP** — not `ScriptedBrain`/`ExploreBrain`. This realizes the ADR-001 S4 seam as
the standing test harness: the world is the MCP server (System 1 + perception), the agent is the MCP client.
- **The ADR-002 gate is run this way:** the live Claude brain hypothesizes "region R = my life" through the MCP
  tool surface, and its grounded life-detector is scored against the `hp=0xD389` oracle in `oracle.jsonl`
  (RAM stays off the wire — scoring only).
- **Launcher:** a clean-slate fresh Claude Code brain in `../aria-mcp-test/` (`.mcp.json` + thin brief), wired to
  an in-cavern state. `ExploreBrain` remains the *free System-1 autopilot* the brain delegates routine tiles to
  (via `explore`/`goto`) — it is no longer the *evaluated* policy; the evaluated policy is the Claude brain.
