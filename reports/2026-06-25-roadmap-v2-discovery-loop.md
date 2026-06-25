# ROADMAP v2 (PROPOSED) — the per-world unit becomes "run the discovery loop," not "hand-build a perceiver"

**Status:** PROPOSED (2026-06-25). **Gated** on the ADR-002 grounding probe (§9 of
`reports/2026-06-25-adr-002-ontology-discovery.md`). Companion to — does **not** replace — `ROADMAP.md`.
On the gate's PASS this is promoted into `ROADMAP.md`; on FAIL it is discarded and `ROADMAP.md` (ADR-001) stands.
Read ADR-002 §9 (the gate) + §11 (anti-drift) before acting on anything here.
**Companion:** `reports/2026-06-25-design-backlog-future-experiments.md` — the running backlog of ideas, principles,
hypotheses & issues (the senses toolbox, `focus`/foveation, the spatial scratchpad, the parked It3+ VLA items, and
the cheap-probe list). All of it is gate-sequenced; consult it when a rung opens.

---

## What v2 changes — and what it does NOT

**Unchanged: the ladder.** It1 Pokémon → It2 a 2nd 2D game → It3 3D/real-time → It4 sim→real → It5 robot, plus the
desktop/web track. The worlds, the order, the two discontinuities (real-time at It3, sim→real at It4), and the
invariants (no privileged state · cheap/dual-process · learning-boundary · behaviour=truth) all stand.

**Changed: the per-world unit of work.** ROADMAP.md's bet is *"a new world = +1 tool-API + 1 **hand-coded
perceiver** + 1 constitution."* ADR-002 moves the hand-code line **down**, so the per-world unit becomes:

> A new world = **+1 tool-API + 1 constitution + run the hypothesize→ground→compile loop.** No new hand-coded
> perceiver. The only hand-code is the **one-time sensorimotor floor** in `core/`, reused on every rung.

| | ROADMAP.md (ADR-001) | ROADMAP v2 (ADR-002) |
|---|---|---|
| Per-world deliverable | hand-code a perceiver | run the discovery loop (brain hypothesizes, behaviour grounds) |
| Hand-code total | grows by one perceiver per world | fixed floor, written once |
| "Constancy" proven by | how little the brain changes | how little changes **including** the perceiver — the *loop* is the constant |
| New-world cost | engineering (write+debug a perceiver) | runtime discovery (the agent grounds its own ontology) |

This **strengthens** the original bet rather than replacing it: ADR-001 froze the brain; v2 additionally frees the
perceiver, so a new world changes even less. It is also **riskier** — hence gated.

## The critical path (near-term, gate-first)

**Rung 0 — THE GATE (the only thing being built now).** Evolve `world_mcp.py` into a minimal sensorium: add the
2–3 primitives the probe needs (`read_text` + `whats_changed` + a pixels-only `consequence` signal) + a thin
hypothesize/confirm surface. Run the HUD-grounding probe: the brain hypothesizes *"region R = my life"*; **score
its grounded life-detector against the RAM oracle** across a Cave Noire run, with a pre-stated pass/fail (ADR-002
§9). This rung decides whether v2 is real.

- **PASS** → the load-bearing claim (behaviour grounds a brain-hypothesized ontology beyond walkability) holds.
  Promote ADR-002 → Accepted, promote this doc → `ROADMAP.md`, proceed to Rung 1.
- **FAIL** → v2 dies here, cheap. Fall back to `ROADMAP.md` (ADR-001, hand-coded perceivers); the gate cost was
  one probe, not a rewrite.

**Rung 1 (POST-PASS only) — the sensorimotor floor.** Build out the remaining primitives (blob-segment+track,
general glyph-read — the ones the gate didn't already need) as clean `core/` ops. Still no per-game perception
logic; the floor is world-agnostic-within-a-sensory-class.

**Rung 2 (POST-PASS only) — re-prove constancy on Cave Noire combat WITHOUT a bespoke perceiver.** The deliverable
is the agent grounding *entities + threat + objective* via the loop — the same worlds ROADMAP.md already validated
for navigation, now reached by discovery instead of hand-code. This is the v2 analogue of the 3-camera-class
constancy result, raised from "swap the perceiver" to "the perceiver builds itself."

**Rung 3+ — back onto the existing ladder (It2, It3…),** each new world running the loop, each a falsification
test of "the loop is the constant."

## Rung 0 — execution plan & open blockers (from the 2026-06-25 adversarial review)

The gate is **not blocked by design — it's blocked by three unverified empirical facts and one missing number.**
None of the architecture above matters until these are resolved. Execute in order:

**Phase A — cheap empirical pre-checks (do FIRST; read-only on `runs/cn_open.state`; no new code). These can
invalidate the gate's shape, so they gate Phase B.**
1. **HUD format:** is Cave Noire's life shown as **digits** (→ `read_text`/OCR is right) or **hearts/pips/a bar**
   (→ OCR is wrong; you'd need count-the-icons = *segmentation*, a Rung-2 primitive)? **Nobody has looked.**
2. **Independent pixel consequence:** find a pixels-only "I took damage / died" event (damage flash? knockback?
   death/reset screen?) that is **NOT** "the life number went down" — else the loop grounds life against itself
   (circularity) and the keystone primitive is undefined.
3. **The life RAM oracle does not exist yet.** `games/cave_noire` watches **position only** (`0xC504/0xC503`);
   there is no life register. Run `find_ram_addr` to locate it — without it there is **nothing to score against.**

**Phase B — operationalize the gate (ADR-002 §9 is still a vibe).** §9 states the two PASS arms (grounds truth +
rejects decoy) but **no metric, threshold, run length, or scoring procedure** — the §11 "gate that can't fail"
risk, self-inflicted. Pin, *after* Phase A (the numbers depend on how often life changes): the agreement metric +
**≥X%** threshold, the **≤Y%** decoy-agreement bound, run length M, the scoring procedure, the **region-candidate
source** (a fixed coarse grid / hand-specified HUD boxes — **no segmentation** in Rung 0), and the decoy set.
**Downgrade the "on PASS" clause:** PASS is **N=1** (one scalar, one game) — it licenses *building the next probe*
(a 2nd instance + the consequence-generality probe), **not** a wholesale ADR-002 promotion.

**Phase C — build the minimal sensorium:** `read_text` *or* icon-count (per Phase A) · `whats_changed` · the
pixels-only `consequence` signal · a thin hypothesize/confirm surface on `world_mcp.py`.

**Phase D — run it, score vs the oracle, decide PASS/FAIL.** PASS → next probe (not promotion); FAIL → ADR-002
dies cheap, `ROADMAP.md`/ADR-001 stands.

## Parked for It3+ (the real-time regime — do NOT build before then)

When a world stops pausing (It3: 3D/real-time), "wake System 2 at decisions" breaks and the VLA+policy question
opens up. Two parked ideas, both touching invariants — to be taken up as conscious ADRs at It3, never by drift:
- **Sequential / action-chunk execution + a consequence-triggered interrupt.** Today's `goto`/`explore` (a coarse
  intent that expands into a System-1 sequence) is the turn-based version; the real-time version is open-loop
  action chunks halted by the pixels-only consequence monitor when reality diverges. Only testable in a non-pausing
  world (Doom/Portal).
- **System-2-as-expert → distill a *learned* fast policy (a VLA).** Hypothesis (David, 2026-06-25): System 2 acts
  through System 1 across many episodes, self-generating + self-labelling traces (free — removes the human-teleop
  cost that makes real VLAs expensive), then a fast policy is trained to imitate it. This is the *neural*
  instantiation of "distill System 2 into System 1." **It deliberately revises the no-per-world-training north star
  and adds neural/GPU infra the project has so far avoided (CPU-only)** — so it is an explicit invariant-revision
  ADR, gated, only where a compiled *symbolic* policy can't express the needed reactivity. Realistically iterative
  (DAgger-style on-policy correction), not "train once and System 2 retires."

## What stays exactly as ROADMAP.md has it

The ladder rungs and their hard axes; the two discontinuities; the desktop/web + small-worker tracks; Cradle as
the baseline to beat (it hand-engineers six perception modules per the same GPT-4o-every-step cost catastrophe —
v2's discovery loop is the direct improvement on *their* perception bottleneck, the documented place Cradle fails).
The learning-boundary law and its planned It4 expiry are untouched.

## Anti-drift (inherits ADR-002 §11 — the load-bearing ones)

- **Gate first.** Build/promote/claim nothing past Rung 0 until the probe PASSES vs the oracle.
- **No bespoke combat perceiver.** Writing game-specific perception logic is the exact drift v2 exists to kill —
  the deliverable is the LOOP.
- **This doc stays PROPOSED.** Do not edit `ROADMAP.md` or `ARCHITECTURE.md` until PASS.
- **The `consequence` signal is pixels-only.** Oracle = scorer, never an agent input.
