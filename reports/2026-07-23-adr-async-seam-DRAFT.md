# ADR (DRAFT / PROPOSED) — Async Seam for Real-Time Worlds

**Status:** DRAFT — for David, not a decision. A seam change is constitutional (ADR-001's own
"Revisit only when surprised" clause names this exact case: "a real-time world ... makes the
per-decision wake untenable and System 1 must own a tighter loop. A revision is a new ADR, made
deliberately — never by drift"). Nothing here is implemented; `ARCHITECTURE.md` and
`core/contracts.py` are untouched by this document. Mirrors ADR-003's convention: doc-only, gated,
not inlined into `ARCHITECTURE.md` until a rung forces it and a gate passes.

**Origin:** capability-map A1 (`reports/2026-07-05-northstar-capability-map.md:32-37`) predicted this
exact evolution: "today the world pauses while the brain thinks; real time removes the pause, which
eventually makes the seam asynchronous ... the one place the contract should be EXPECTED to
legitimately bend." F3 (`reports/2026-07-23-f3-latency-window.md`, PR #136) has now measured the
number this ADR was blocked on.

## The problem

ADR-001's seam is synchronous by construction: the world advances on press/tick, System 2 is woken at
a decision, and the world waits for the answer before it moves again ("the agent is woken at
decisions, not every frame" — `ARCHITECTURE.md` "The seam"). Every world beaten so far tolerates this
because the world itself waits. Real-time worlds don't: MKDS advances every frame with zero input
(idle drift 12.22%/frame mean, banked `FINDINGS.md:329`), so a brain that "waits to be asked" loses by
forfeit while it deliberates. Synchronous wake-answer-continue cannot survive a clock that doesn't stop.

## The design constraint — F3's measured window

F3 measured the survivable-deliberation window on MKDS 50cc, start-straight -> turn 1:
**~2.0s survivable, fatal by ~2.5s**, with a *fixed* reflex holding the kart on the straight. Two
qualifiers shape the design, not just the number:
- The window is **feature- and speed-dependent** (collapses toward ~0 mid-turn; shrinks at higher CC)
  — there is no single constant, only a floor to design against.
- A **fixed open-loop reflex only holds a straight**; rounding a turn needs a **closed-loop**
  (perception-driven) reflex, which the NDS lane hasn't built (F3 "Requirements spec for A5" #2-3). The
  contract below must assume the reflex is a *policy consuming fresh percepts*, not a stopgap constant.

## Proposed shape (sketch, not a spec)

Split the one blocking request/response into two channels terminating at the SAME `SymbolicState`
boundary — no new field, no new brain-side type:

1. **Fast channel (already exists; sharpened):** world -> System 1, every frame. Not new — ADR-001's
   existing reflex loop — but real-time worlds require it to run a **closed-loop policy** (F3's ~2s
   floor as the minimum hold time), not autopilot-until-decision.
2. **Slow channel (the bend):** world -> agent `SymbolicState` **stream**, not a single blocking call
   -> agent intent, landing whenever it lands. The world does not wait for it; when an intent arrives,
   System 1 hands back control at the next safe point, not mid-turn.
3. **Synchronous worlds are the degenerate case of the same shape, not a second code path:** when the
   world always waits, the slow-channel latency is defined as always inside the survivable window
   (an infinite window), so today's wake-answer-continue behavior falls out for free with zero harness
   changes for any existing world. That equivalence is the load-bearing constancy argument here.

## What stays frozen vs. what bends

- **Frozen:** `SymbolicState`'s shape, the no-leak rule (oracle never crosses), System 2 living
  unchanged in `ai-aria`, `core/contracts.py` v1's fields and hash pin, every synchronous world's
  harness code.
- **Bends:** the seam's *delivery discipline* — from one blocking call per decision to a stream the
  agent reads/writes asynchronously, with System 1 as the live default in between. This is an
  additive delta gated on a forcing rung, same discipline ADR-003 already applies to the UEC — never
  a v1 rewrite.

## Falsifier — when would async break constancy?

Constancy breaks if making a world real-time requires **hand-written, per-world System-1 control code
that dwarfs the perceiver** (capability-map A6's falsifier, same shape here) — i.e. if "the reflex
layer" turns out to mean bespoke controller code per genre instead of a small closed-loop primitive
consuming the same `SymbolicState`. It also breaks if ANY synchronous world needs ITS harness changed
to accommodate the new channel — the degenerate-case equivalence above is the first thing to check,
and the first thing that would falsify this ADR if it doesn't hold.

## Cheapest validation before adopting

Do not build the async channel yet. The cheapest next step is already on the paid track:
**P1, the MKDS build + A/B** (capability-map Track P item 1), which requires exactly the closed-loop
track-follower F3 identified as missing — a perception primitive, not a contract change. Gate that
first. Only if a closed-loop reflex demonstrably holds a real-time world across turns, using nothing
but `SymbolicState`-shaped input, should this ADR graduate from sketch to a real `CONTRACT_VERSION`
proposal with its own gate — per capability-map's own Exit 4 ("the async-seam ADR informed by F3's
window") and its explicit hold ("Async-seam ADR: held until F3's number exists").

## References

- `reports/2026-07-05-northstar-capability-map.md` — A1 (real time), A5 (reflexes), A6 falsifier;
  Track P item 1, Exit 4, and the explicit "held until F3" note.
- `reports/2026-07-23-f3-latency-window.md` (PR #136) — the measured ~2.0-2.5s window and its
  perception-gated (not reflex-quantity-gated) diagnosis.
- `ARCHITECTURE.md` — ADR-001, the frozen synchronous seam; "Revisit only when surprised."
- `reports/_archive/2026-07-01-adr-003-embodiment-north-star-contract.md` — ADR-003, the
  staged-convergence / gated-additive-delta discipline this draft follows.
