# ROADMAP — the multi-month arc

_The durable, version-controlled statement of where this project is going. Pinned here so it can't drift.
Companion docs: [`HANDOFF.md`](HANDOFF.md) (current status + the near-term plan), `ai-aria/PROMPT_ARCHITECTURE.md`
(the prompt/brain architecture). Last painted: 2026-06-20._

## The one bet

We are **not** building six agents. We are building **one brain** and testing whether a single abstraction —
**the BRAIN acts on a WORLD through coarse skill-tools** — holds as the world gets harder. If the abstraction
is right, every new world is just *"implement a tool API + a perceiver + a constitution,"* and the brain is
untouched. Each rung below is a falsification test of that bet, at increasing stakes.

**Pokémon is the entertaining testbed for designing the harness — not a game to beat.**

## The invariant (unchanged on every rung)

- **`ai-aria` = the BRAIN** — owns cognition + within-run memory; authors its own System 1 policies; acts via tools.
- **The WORLD exposes coarse skill-tools** (observe / move / interact / …). Pokémon today; digital life / 3D sim /
  reality later.
- **Dual process:** System 1 (fast, cheap, eventually self-authored) drives; it defers **up** to System 2 only on
  **necessity** (novelty / low confidence) or **override** (a surprise preempts). Cost scales with novelty, not steps.
- **Brain-agnostic (provider AND capability tier).** The brain is swappable across providers (litellm already)
  *and* model sizes — Haiku for routine worlds, **Opus 4.8 when a world needs it**. Dial the brain to the world's
  difficulty; *"cheap-first" = the cheapest model that clears the bar, not always-cheap.* Dual-process + the
  cost-breaker are what make an expensive brain affordable (System 2 fires only at decisions).
- **Constitution-first prompt** (purpose = the immutable cached top layer) + the **learning-boundary law**.

A new world = **+ 1 tool-API + 1 perceiver + 1 constitution.** Nothing else should change.

## The ladder (iterations)

| # | World | New hard axis it adds | Regime |
| --- | --- | --- | --- |
| **It1** | **Pokémon Red** *(now)* | establishes the primitives (nav/interact as tools, perception seam, System 1/2, constitution) | 2D · turn-based · sim |
| **It2** | **A 2nd 2D game** (Pokémon Ruby?) | **generalization** — proves the primitives are reusable *tools*, not Red-specific hacks | 2D · turn-based · sim |
| **It3** | **FPS / TPS** (3D game; e.g. **Portal 1/2**) | **3D perception + real-time control** *(discontinuity #1)* — System 1 must own a fast loop; System 2 advisory | 3D · real-time · sim |
| **It4** | **Drone / self-driving car in the home** | **sim → real** *(discontinuity #2)* — noisy sensors, latency, irreversibility, safety, **persistent home-memory** | 3D · real-time · **real** |
| **It5** | **Legged + armed robot** (C3PO/R2D2) | **manipulation + locomotion** — full embodiment, open-ended real world (capstone; funding-gated) | 3D · real-time · **real** |

**Orthogonal track — the small worker:** aria as an ephemeral, localized-context, short-lived sub-agent that does
a small task and is then deconstructed. This is a **lifecycle/orchestration** axis, *not* embodiment — it doesn't
need the ladder and is parallelizable. Treat it as a **capability of the mature brain**, not a separate brain:
a compiled System-1 policy ≈ a frozen small worker; a delegated sub-task ≈ a fresh aria with localized context.
(Developing it as its own small track is reasonable — just don't fork the architecture for it.)

## Not a strict line — a PORTFOLIO behind one brain

The iterations above are the *embodiment spine*, but worlds are unified by the one brain, so reach for whichever
world best tests the next capability. Two axes sit alongside the spine:
- **Desktop / web (in scope) — the "digital real-world" axis.** Real consequences (a sent email, a purchase) but
  no physical body. The **companion deployment already lives here** (gmail/gcal/web tools), so it's the *cheapest
  place to prove cross-world transfer* — same brain, swap the GamePlugin. (Targets like OSWorld / WebArena /
  AndroidWorld test *transfer + grounding*, not raw IQ.)
- **Portal 1/2 — the reasoning + embodiment capstone.** The rare world where hard multi-step reasoning
  (portal/momentum/physics puzzles) and realistic 3D real-time control *coincide* instead of pulling apart. It
  stress-tests the **whole** architecture at once: 3D perception-invariance + dual-process + an **Opus-tier
  System 2** at the puzzle. A single world that proves the entire bet.
- **Cheap generalization probes — Crafter / Craftax** (procedurally-generated 2D survival, free + fast,
  memorization-resistant): a richer GateWorld for debugging the brain↔gateway↔perceiver loop and testing *real*
  generalization. Drive it from its **pixel render** (not its semantic state) to honor perception-invariance.

**Perception-invariance is a co-equal invariant with the tool interface** — transfer needs *both* the frozen
tool contract AND a constant `pixels → SymbolicState` seam. An identical tool API with a different perception
regime does **not** transfer.

## Why this order (isolate one variable per rung)

Each rung changes **one** thing, so a failure has one cause (the same scientific discipline as the GateWorld probe).
- **It2 is the cheapest, highest-ROI rung** and the most important early validation: it changes only the *skin*, so
  it directly answers the north-star question — *are the primitives real tools or hacks?* Do this soon.
- **It1–It2 are skin changes.** The architecture is genuinely *tested* only at the two discontinuities below;
  everything else is "new tool API + new perceiver."

## The two real discontinuities (where the bet is tested)

1. **Real-time (entering 3D, It3).** Breaks today's load-bearing assumption *"wake the LLM at decisions."* A game
   that doesn't pause means System 2 can't be in the control loop — **System 1 must own a fast loop.** This is why
   System-1 authoring (self-compiled policies) graduates from *optimization* to *necessity* here.
2. **Sim → real (entering the home, It4).** Irreversibility + safety + real sensor noise. And it **forces the
   across-run-memory decision**: the learning-boundary "blank every run" law is right for fair *game-iteration*
   comparison, but an embodied agent in your house must remember the house. So the law has a **planned expiry around
   It4** — revise it deliberately there, never by drift.

The role-named `SymbolicState` seam (`core/perception.py`: *"only the representation behind each role is
environment-specific"*) was built to survive 2D→3D. **It3 is where we find out if that bet paid off.**

## Phasing (relative, not dates)

It1 → It2 near-term (the generalization proof) · It3 mid-term (first real architectural stress) · It4 real-world-
gated · It5 the funded capstone · small-worker parallelizable whenever useful.
