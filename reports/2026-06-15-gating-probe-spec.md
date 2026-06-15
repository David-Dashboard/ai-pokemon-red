# The gating probe — spec + free plumbing result (2026-06-15)

**One line:** a minimal synthetic world that isolates **means-ends reasoning with backtracking**
(the *gate* / dependency problem) and is built to tell **reasoning** apart from **recall** — the leak
that contaminates every reasoning claim made on Pokémon. Implemented in `games/gateworld/`, run by
`eval/gating_probe.py`.

Ties to: [Iteration 01](2026-06-13-iteration-01.md) (perception is the bottleneck),
[the perception spec §9](2026-06-13-iteration-02-perception-spec.md) (the documented recall leak),
and the [consolidated report §7](2026-06-15-consolidated-report.md) (how close to a new world).

---

## 1. What it tests, and why nothing else does

A **gate** is a dependency: you can't reach the goal until you acquire something that sits *off the
path to the goal* — so you must leave your goal direction, fetch it, and come back. Pokémon is
wall-to-wall gates (Route 1 behind the starter; later Cut / Surf / Strength / each badge). The
reasoning a gate demands is **class-2**: recognise the block → infer the missing precondition → set a
subgoal → **backtrack** to satisfy it → return → apply. The free autopilot only does **class-1**
reactive navigation (explore frontiers); it *cannot* do this. So gating is exactly where an expensive
brain has to earn its cost.

But you **cannot measure this on Pokémon honestly**: the model already memorised Pokémon Red, so
solving the Oak gate might be *recall of a walkthrough*, not *reasoning*. That contamination is the
single biggest threat to any generalisation claim (logged in the perception spec §9).

## 2. The design: same structure, two skins, one neutral prompt

GateWorld is **fully synthetic** — no walkthrough exists for it — and ships the identical world under
two surface **themes**:

- **`familiar`** — a *locked door* + a *key*: invokes the universal "key opens door" prior (recall-
  friendly).
- **`novel`** — a *humming barrier* + a *glowing fragment*: no semantic open-relationship; the link
  must be **inferred from the observed mechanic**, not the words.

Both run under one **neutral, world-agnostic system prompt** (`NEUTRAL_SYSTEM` in
`eval/gating_probe.py`) — no "Pokémon", no "key", and no hint *binding the specific object to the
specific gate*. It does carry one generic, **skin-identical** dynamics note ("you may need to find
and carry an object to get past an obstacle") — a scaffold of the action space, not the solution, and
because it's identical across skins it can't differentially help, so the solve-delta still isolates
recall. The verdict is the **solve-delta**:

| solved `familiar` | solved `novel` | conclusion |
|---|---|---|
| ✓ | ✓ | **reasoning that transfers** — the capability is real |
| ✓ | ✗ | **recall-leaning** — it leaned on the prior, didn't infer |
| ✗ | ✗ | can't do class-2 gating yet |

Two levels of leak control stack here: GateWorld-vs-Pokémon removes the *Pokémon-specific* recall
(the big one); `familiar`-vs-`novel` additionally strips the *generic* "key→door" prior.

## 3. The world contract — why the SAME agent runs unchanged

GateWorld is a `GamePlugin` (no reset/step/terminal, like the Pokémon world) that deliberately reuses
the interfaces the existing agent already speaks, so **no brain code changes** to run on it:

- **Action surface = the Game Boy button contract** (`press_button` / `press_sequence` / `wait`); `A`
  is the context-sensitive *interact* (pick up when on the item; unlock when adjacent to the gate +
  carrying it). `GATEWORLD_SANDBOX` is the same allowlist shape as `POKEMON_SANDBOX`.
- **Observation = the same role-named `SymbolicState`** the perceiver emits (`pose` /
  `spatial_memory{map, frontiers}` / `affordances` / `last_action` / `context`), plus reasoning
  extras in the text. It is god's-eye (synthetic), so it reports ground-truth walls for visited
  cells — no perceiver needed, and there is **no privileged RAM-like channel** at all.
- **Turn-then-move semantics**: a press toward a direction you're not facing turns you (no move);
  pressing the way you face steps. This is exactly what `ExploreBrain`'s `[d,d]` ("turn, then move")
  assumes — getting it wrong (move-per-press) made the autopilot overshoot and oscillate forever in
  the first cut; matching it fixed it. (A small fidelity lesson: a new world must honour the *motion
  contract* the controller assumes, not just the button names.)

Layout (default `GATE_MAP`): a wall column splits start-side from goal-side with a single gate
opening; the item sits in a side branch on the start-side, **away from the gate's row**, so reaching
it is a genuine detour. The autopilot explores the start-side for free, finds the item and the gate,
but — pressing no buttons but moves — **cannot open the gate**; it runs out of frontier and
`HybridBrain` wakes the reasoner. That wake is the event the probe measures.

## 4. What's measured

Per skin: `solved?`, `solve_step` (decisions to reach the goal), and `reasoner_wakes_at_solve` (how
many times the expensive brain was actually needed — the rest were free autopilot steps).

## 5. Free plumbing result (scripted oracle)

`uv run python -m eval.gating_probe` runs a **`ScriptedReasoner`** — a free, deterministic *oracle*
that reads the item/gate/goal positions and plans BFS. It is **not the experiment**; it is the
plumbing check and the upper bound the LLM is measured against. Result:

```
familiar : PASS  (solved in 27 decisions, 6 reasoner wakes)
novel    : PASS  (solved in 27 decisions, 6 reasoner wakes)
```

This proves: the world is solvable; the **same** `HybridBrain(ExploreBrain, reasoner)` loop drives it
end-to-end; the autopilot handled 21/27 decisions for free and the reasoner did only the 6 means-ends
actions. Both skins are identical here **because the oracle reads coordinates, not theme words** — the
reasoning-vs-recall split only appears with the real LLM (which reads the themed text). Confirmed
separately by `test_autopilot_alone_cannot_open_the_gate`: exploration alone never opens the gate.

## 6. The real measurement (credit-gated)

```
ARIA_BEARER_TOKEN=... uv run python -m eval.gating_probe --brain llm --backend aria
```

Swaps the oracle for `LLMButtonBrain` with `NEUTRAL_SYSTEM` and `use_vision=False`. Everything else —
world, router, scoring — is identical. This is the only step that touches a paid brain; it produces
the actual reasoning-vs-recall verdict from the solve-delta in §2.

## 7. What the probe also exercises (and a limitation it already surfaced)

Running the existing loop in a brand-new world is itself a generalisation test, and it integration-
tests the Iteration-03 seams: stuck-wake routing, `goto`/BFS navigation, and the outcome loop.

**Finding (honest):** the outcome loop's effectiveness signature
(`state_signature = (context, area, pose)` in `core/outcome.py`) is **movement-centric**. Picking up
the item changes *inventory*, not pose/area/context — so the signature is unchanged and the loop
records the `A` press as "no effect". After two such presses it would mark `A` "dead" and warn the
planner off it *exactly when it's the right move*. The scripted oracle ignores `avoid` and solves
anyway, and an LLM still sees "you picked up the …" in the text — so it's friction, not a hard
blocker — but it's a concrete generalisation TODO: the effectiveness signal should include
inventory/affordance/state deltas, not just pose. The probe surfacing this is the probe doing its job.

## 8. Open / future hardening
- A **distractor** item (two objects, one wrong) so success can't be "grab the only thing".
- A **two-gate chain** (key A behind gate B behind key C) to test multi-step backtracking depth.
- Partial observability (fog beyond line-of-sight) to fold in a search component once reasoning is
  established.
- Generalise `state_signature` (the §7 finding) and re-run to confirm the outcome loop helps rather
  than hinders here.
