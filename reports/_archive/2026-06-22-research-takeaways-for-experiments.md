# Research takeaways to carry into our experiments (2026-06-22)

Companion to `reports/2026-06-22-prior-art-scan.md` (the who's-doing-what + sources). This file is the
**operational** version: the concrete lessons from other researchers we should hold in mind *while running
experiments*, plus a component-by-component map of **what we're trying to do vs. what everyone else is trying
to do vs. what we should do.** Keep it open during the cross-game + 3D work.

The one-line frame (from the prior-art scan): **the pieces are each well-trodden; our specific combination
is open.** So the discipline is — *reuse the validated pieces, and spend our novelty budget only on the
combination* (cheap + screen-only + online/no-training + behaviour=truth + dual-process + held-out cross-game).

---

## PART A — Cross-cutting lessons (carry these into EVERY experiment)

These are the field-level findings that should shape how we design and read our own runs, regardless of which
component we're testing.

1. **Perception is the bottleneck, not planning — and it's the documented wall of the closest system.**
   Cradle (GPT-4o, screen-only, runs RDR2/Stardew) reports its headline failure is *perception*: "GPT-4o
   struggles to recognize/locate objects near the player in 2D games." This is the single most important
   external validation we have — it says the expensive-VLM-every-step route hits a perception wall, exactly
   where we're investing. **Carry:** when a run fails, suspect perception first; protect the cheap-perception
   thesis; don't "fix" a perception gap by calling a bigger model more often.

2. **Behaviour = truth generalizes — others proved it in robotics, online, in <5 min.** Wild Visual
   Navigation (WVN, RSS'23) and V-STRONG/BADGR learn "where I drove = traversable" from the robot's *own*
   experience and generalize by appearance — the exact shape of our tile→function map, and they do it online
   with fast adaptation. **Carry:** our centerpiece is not exotic; it's a known-good pattern. Borrow their
   online-supervision + fast-adaptation framing. But note the tension in #3.

3. **Appearance→function is domain-dependent: embeddings won for them, a hash won for us.** WVN makes learned
   visual-feature embeddings (DINO/ViT) work for traversability; we found CLIP *fails* cross-tileset for GB
   walkability and a perceptual hash beat it (leave-one-MAP-out 81% vs CLIP 26.9%). Likely a real domain gap:
   natural terrain has appearance↔function correlation an embedding captures; pixel-art tilesets have *exact
   recurrence* a hash captures and arbitrary appearance/function decoupling an embedding blurs. **Carry:** do
   NOT assume the hash-beats-CLIP result transfers to richer/3D worlds — re-test the appearance representation
   per domain. CLIP is deferred, not dead; its real jobs are graded-novelty distance + semantics + natural
   images, not GB walkability.

4. **Dual-process S1/S2 is grounded, not novel — so don't spend novelty budget defending the split.**
   SwiftSage, DPT-Agent, Optimus-3 all run a fast cheap System-1 loop + an LLM System-2 woken selectively, and
   openly discuss the coupling dilemma (S1 high-freq/low-latency vs S2 low-freq/deep) we live in. **Carry:**
   cite them, reuse the pattern, and put our effort into the *seam* and the *cross-game* claim instead.

5. **Cross-game generalization is currently bought with training, not structure — that's the gap we bet on.**
   NitroGen (+52% on unseen games), GATO, PORTAL all generalize via internet-scale behavior cloning / big
   pretrained policies. We're trying to generalize with *zero training* — structure (a perceiver swap + a
   behaviour-grounded world model) instead of weights. **Carry:** our held-out cross-game result is the
   headline experiment of the whole iteration; it's also where we're most alone, so verify it hardest.

6. **The honest-metric discipline is on us — the field's failures are usually hidden by the wrong metric or
   hold-out.** Our own two reversals (cross-tileset wall-recall = 0% hidden by aggregate accuracy; the offline
   nav-savings ceiling that stranded the agent closed-loop; the 3D off-by-one that *under*-reported the signal)
   are the same class of error that inflates published numbers. **Carry, non-negotiable:** (a) pick the metric
   that matches the downstream cost (don't-walk-into-walls = wall-recall, not accuracy); (b) hold out the right
   UNIT (whole tileset / whole game, not one map); (c) measure closed-loop when the policy's outputs change its
   inputs; (d) adversarially re-derive any good-looking generalization number before trusting it.

7. **Skill curation / System-2→System-1 compilation is the proven way to amortize the expensive brain.**
   Cradle's skill-curation and Voyager's skill-library both grow a reusable policy set the cheap loop can
   replay. This is exactly our deferred S5 (PolicyMemory). **Carry:** when we get there, read Cradle's Skill
   Curation first; don't reinvent it.

8. **Affordances from the agent's OWN attempts are a known primitive.** "Interaction Exploration / What can I
   do here" learns affordances by trying actions and watching what changes — the generalized form of our
   interaction-probe (face a wall, press A, watch for a mode change). **Carry:** our probe is a special case of
   a validated idea; generalize it deliberately rather than treating it as a Pokémon hack.

9. **One maze / one game / one policy is not evidence of generality — name the slice every time.** Our 3D gate
   is one ViZDoom maze under a forward-biased *random* policy; the cross-game corpus is early-game slices. The
   field over-claims by testing the easy slice. **Carry:** every result states its slice (which game, which
   region, which policy, which camera model), and the next experiment attacks the untested slice.

---

## PART B — What we're trying to do vs. what others are trying to do vs. what we should do

Read each row as: **our goal** · **the field** · **our move (ADOPT / AVOID / OPEN)**. The components are the
swap-points of the World Interface (per-game) and the invariants we protect (the brain + core + seam).

### 1. Self-localization / odometry  *(per-game — the biggest varier)*
- **We:** estimate self-motion from the screen with NO privileged state — by *camera-model class*
  (follow-scroll / static-sprite / forced-scroll / fixed). 2D: dead-reckoning + best-shift on the scroll. 3D
  (verified greenlight): a cheap discrete ego-motion classifier (advance / turn-L / turn-R / stuck) from
  **optical flow**, NOT scalar frame-diff (which can't tell rotation from translation).
- **Others:** robotics has decades of visual/inertial odometry + SLAM; WVN/BADGR assume a pose source and
  focus on traversability on top. Game agents mostly *sidestep* odometry — Cradle leans on the VLM + UI text;
  RAM-based Pokémon bots read coordinates directly (privileged, what we forbid).
- **DO:** **ADOPT** the camera-model-class decomposition as the per-game swap unit; **ADOPT** optical-flow for
  3D ego-motion (column-shift sign → turn; expansion flow → advance). **AVOID** treating frame-diff as
  odometry, and **AVOID** assuming metric distance is recoverable cheaply (graded distance corr ≈ +0.02 in 3D
  — it's a *discrete* classifier). **OPEN:** can one detector auto-pick the camera model offline across the
  dev corpus? This is the NEXT build.

### 2. Affordance / traversability perception  *(per-game — the centerpiece)*
- **We:** an ONLINE behaviour-labelled appearance→function map (walk→walkable, bump→blocked, probe→
  interactable), keyed by a cheap fingerprint; advisory + behavioural veto; fail-safe to "novel→explore" on a
  new tileset rather than confidently mispredict.
- **Others:** WVN/V-STRONG/BADGR — the direct robotics analog, online, behaviour-grounded, embedding-keyed,
  generalizes on natural terrain. Tile Embedding learns proc-gen tile representations. Interaction Exploration
  learns affordances from own attempts.
- **DO:** **ADOPT** WVN's online supervision + fast-adaptation mindset and Interaction-Exploration's
  try-and-watch affordance discovery. **AVOID** assuming a learned embedding is the right key everywhere — for
  pixel-art it isn't (hash won). **OPEN:** for richer/3D worlds, is the right key a hash, a light online-adapted
  feature, or both (a BM25-style sparse+dense hybrid)? Re-test per domain; this is the gated CLIP arm.

### 3. Mode / context detection  *(per-game)*
- **We:** classify the screen's mode (overworld / menu / dialog / battle / keyboard) cheaply from pixels, to
  route the loop (auto-advance vs. wake). Known weak spot: full-screen bright menus misread as `battle`.
- **Others:** Cradle has explicit info-gathering / self-reflection / task-inference modules driven by the VLM;
  most LLM-game agents let the model infer context from the screenshot every step (expensive, and the
  perception wall bites here too).
- **DO:** **ADOPT** the idea of an explicit mode/context state that gates expensive reasoning. **AVOID** paying
  a VLM per step to decide "what screen is this" — it's a cheap classifier's job. **OPEN:** a general cheap
  mode-detector across games (each game has different menus/fonts) — likely per-game templates + a generic
  "is this a full-screen UI vs a world view" prior.

### 4. Text / OCR  *(per-game)*
- **We:** template-default + RapidOCR-fallback (gen-1 dialog/battle is ~90% of text where the free template is
  ~100%). Text is a perception channel, not the plan.
- **Others:** Cradle and most computer-control agents lean heavily on OCR / accessibility text — it's the one
  perception channel VLMs + OCR do reliably, and it carries a lot of UI agents' competence.
- **DO:** **ADOPT** OCR as a high-reliability channel (the field's strongest perception result). **AVOID**
  over-investing where a free template already wins. **OPEN:** per-game font tables don't generalize — is a
  small general OCR (RapidOCR) the cross-game default once we leave gen-1?

### 5. Entity / object detection  *(per-game)*
- **We:** mostly deferred. Today: motion-saliency (idle-animating NPCs as ROIs) + the interaction-probe
  (non-walkable tile that reacts to A = interactable). No semantic entity ID.
- **Others:** open-vocab detectors (YOLO-world, Florence-2, GroundingDINO) and VLMs — but our probes + the
  Cradle finding show fine-grained sprite/entity semantics FAIL on tiny low-res game sprites. This is the
  field's documented weak spot, not a solved tool we can grab.
- **DO:** **ADOPT** behaviour-grounded entity discovery (motion-saliency + probe) over semantic detection for
  now. **AVOID** betting on off-the-shelf sprite-level semantic detection (it fails on GB frames; Cradle
  confirms 2D object localization is hard for GPT-4o). **OPEN:** when entities matter (combat, NPCs), is the
  answer a behaviour-labelled entity store (the tile-map idea applied to sprites) rather than a detector?

### 6. Action space / motion contract  *(per-game)*
- **We:** a per-game contract for what a button does (move vs. jump/attack; single-step vs. two-tile press;
  turn-absorbed-in-press). We learned the hard way that the *step granularity* is a per-world property the
  driver injects (`single_step`) — core stays agnostic.
- **Others:** GATO/VPT/SIMA learn the action mapping from data; Cradle hard-codes keyboard/mouse skills per
  game; PORTAL generates behavior trees. Nobody we found treats the motion contract as an explicitly *measured*
  per-game seam the way we do (we probe `[d]` vs `[d,d]` on the live emulator).
- **DO:** **ADOPT** our own measured-motion-contract discipline (probe the emulator, don't assume). **AVOID**
  baking one game's contract into core. **OPEN:** can the recorder's raw (frame, buttons, next-frame) triples
  let us *learn* the motion contract offline per game, instead of hand-probing each?

### 7. World model / spatial memory  *(per-game representation, agnostic machinery)*
- **We:** a behaviour-labelled tile→function map + occupancy/frontier graph (2D); for 3D, NOT the tile grid —
  a 3D spatial representation TBD. Built online, no training, discarded per run (learning-boundary).
- **Others:** semantic SLAM / Bayesian occupancy grids (robotics); Voyager's growing skill+world knowledge;
  GATO's implicit world model in weights. Most game agents have a thin or VLM-implicit world model.
- **DO:** **ADOPT** the occupancy/affordance-map structure (robotics-proven). **AVOID** a single grid
  representation across camera models — 3D needs its own. **OPEN:** what's the cheapest 3D spatial
  representation that behaviour=truth can populate (occupancy from optical-flow ego-motion + bump events)?

### 8. Reflexive controller (System 1)  *(agnostic core, partly per-genre)*
- **We:** a free local autopilot (frontier-explore BFS + battle reflexes) that drives routine steps and defers
  UP to System 2 only on novelty / low-confidence / override. Frontier-explore is top-down-only; platformers
  need their own.
- **Others:** SwiftSage's Swift module, DPT-Agent's fast loop, VPT's learned low-level policy. The split is
  standard; the *coupling* (when to defer up) is the open research question everyone discusses.
- **DO:** **ADOPT** the selective-defer design (it's the whole cheap-first thesis). **AVOID** assuming one S1
  controller spans genres (top-down explore ≠ platformer). **OPEN:** the defer-up trigger — our novelty/
  no-progress signal vs. their learned confidence; this is a core experiment.

### 9. Outcome / learning signal  *(agnostic core, within-run only)*
- **We:** within-run only (HARD LAW until It4): occupancy, OutcomeMemory, disconfirm detector, novelty/seen-
  states, the missed-text transcript — injected per wake, discarded at run end. No across-run weight learning.
- **Others:** VPT/GATO/NitroGen learn across episodes into weights (the opposite of our law); Voyager persists
  a skill library; WVN adapts online within a deployment (closest to our within-run stance).
- **DO:** **ADOPT** WVN-style within-deployment online adaptation as the model for within-run learning.
  **AVOID** across-run weight learning this iteration (it's a deliberate later ADR, not a default). **OPEN:**
  the It4 decision — when (if) across-run learning is allowed, and whether it's weights or a curated skill/
  fact store (Voyager-style) that respects the screen-only/cheap constraints.

### 10. Decision-taking (System 2)  *(the INVARIANT — ai-aria, protected)*
- **We:** the LLM brain (aria) is woken only at decisions; owns cognition + within-run memory + identity
  (constitution). Reused UNCHANGED across worlds — success = how little the brain changes per game.
- **Others:** Cradle/Voyager/SwiftSage all have an LLM planner, but it's usually *coupled* to the game and
  called far more often (Cradle: GPT-4o every step). None hold the brain fixed across games as the headline
  metric.
- **DO:** **PROTECT** the brain as the invariant; that constancy IS our contribution. **AVOID** leaking game-
  specifics into the brain or calling it per-step. **OPEN:** how much per-game knowledge must live in the
  constitution (config) vs. be decoded from the screen — the decode-aligned-vs-told tension (we currently
  *tell* it the Kanto map; stripping the seed is the harder, truer test).

### 11. Generalizability (the meta-goal)  *(the bet)*
- **We:** ONE agent + a swappable perceiver across a 2D→3D→reality ladder, generalizing by STRUCTURE (perceiver
  swap + behaviour-grounded world model), zero training, with an explicit held-out cross-game split.
- **Others:** generalization-by-DATA (GATO/NitroGen/PORTAL/SIMA — big behavior cloning across many games);
  generalization-by-online-adaptation (WVN, robotics). Nobody combines screen-only + zero-training + dual-
  process + held-out cross-GAME generalization on a ladder toward reality.
- **DO:** **this is the experiment of record.** Build odometry/affordance OFFLINE on the dev corpus, verify on
  the held-out 4 (one per perception axis) via `eval/cross_game.py`, never tuning on held-out. **AVOID** the
  data-hungry path (against the thesis) and silent slice-narrowing. **OPEN:** does "the brain barely changes"
  actually hold past game #2, or does each new camera model / genre force a new S1 controller (the real risk)?

---

## The shortlist to actually read before the next builds
- **Cradle** (perception bottleneck + skill curation) — before S5 and before trusting any VLM-per-step idea.
- **Wild Visual Navigation / V-STRONG** (online behaviour-grounded traversability) — the template for the
  affordance map's online supervision; read before generalizing the tile→function map cross-game/3D.
- **Interaction Exploration** ("what can I do here") — before generalizing the interaction-probe.
- **SwiftSage / DPT-Agent** (defer-up trigger) — before tuning the System-1→System-2 coupling.

## ADOPT / AVOID — the compressed table
- **ADOPT:** behaviour=truth online supervision (WVN); camera-model-class odometry; optical-flow 3D ego-motion;
  OCR as the reliable text channel; skill curation for S5 (Cradle/Voyager); the selective defer-up S1/S2 split;
  honest metric/hold-out/closed-loop discipline.
- **AVOID:** GPT-4o (or any VLM) every step; internet-scale behavior cloning; assuming hash-beats-CLIP transfers
  to 3D/natural images; off-the-shelf sprite-level semantic detection; one grid/one S1 across all camera models;
  across-run weight learning this iteration; reporting the easy slice without naming it.
- **BIGGEST OPEN RISKS:** (1) does "the brain barely changes" survive past game #2? (2) does the appearance→
  function key need to change per domain (hash vs. embedding)? (3) is a cheap 3D spatial world model populable
  by behaviour=truth alone? (4) the defer-up trigger across games. (5) the It4 across-run-learning decision.
