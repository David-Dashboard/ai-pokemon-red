# Plan grounding + failure modes — anchoring the whole design in prior art (2026-06-22)

Before we fix-and-continue, this grounds **every component of the plan** in real systems, with their
**documented failure modes** and the **guard we carry**. Companion to `reports/2026-06-22-prior-art-scan.md`
(who's doing what) and `reports/2026-06-22-research-takeaways-for-experiments.md` (component lessons).

**Headline:** several of our *own* verified findings independently match textbook failure modes — we
rediscovered them from scratch. That's a strong signal the design is sound, not improvised.

---

## Part 1 — Self-improvement: how a "skill" actually improves, and how it fails
The question "how does a SKILL improve?" has been tried hard. The consensus: **improvement only works with an
outcome-grounded validation gate; self-reflection alone drifts.**

- **Voyager (Minecraft, GPT-4; arXiv 2305.16291).** Mechanism = three parts: an **automatic curriculum**
  (proposes next task), a **skill library** (stores *code* skills, retrieved by embedding), and **iterative
  prompting with self-verification** (a critic checks success). **Ablations:** remove the curriculum → item
  discovery plummets; remove the library → no zero-shot transfer; **remove self-verification → buggy code
  accumulates in the library.** **Failure modes:** GPT-4 proposes impossible tasks (craft non-existent items),
  writes code with invalid assumptions / non-existent API calls, high cost. **Known limit:** *skills are added
  only on success, never refined by a reward signal.* → **Lesson:** the **self-verification gate is
  load-bearing** (matches our gate); "add-only-on-success" is exactly the limit we improve on with a real
  *held-out* gate + versioned refinement.
- **Reflexion (arXiv 2303.11366).** Mechanism = "verbal reinforcement": turn an outcome into a written lesson,
  re-inject next attempt. **Failure modes:** self-reflections **repeat earlier misconceptions and don't
  introduce new reasoning paths** on hard cases; **verbal reflection is not a substitute for an exploration
  strategy** (telling it "try different search terms" doesn't converge); memory is a **sliding window of only
  1–3** reflections. → **Lesson:** reflection needs a *crisp, actionable, external* signal; self-talk alone
  loops. Our novelty/outcome signals + the gate are what make reflection more than a loop.
- **"LLMs Cannot Self-Correct Reasoning Yet" (Huang et al., ICLR'24; arXiv 2310.01798).** Finding: with
  **intrinsic** self-correction (no external feedback), LLMs **struggle to self-correct and performance often
  DEGRADES.** → **Lesson:** *this is the citation for our non-negotiable rule* — the validation gate must be
  **outcome-grounded, not self-judged.** An agent grading its own edit is the documented way to get worse.
- **Model collapse / data autophagy / reward hacking (self-improvement survey arXiv 2603.25681; "Escaping
  Collapse" 2502.08924).** Training on self-generated data **decays diversity and performance** ("data
  autophagy"); **reward hacking** = high nominal reward, nonsense output; **feedback contamination** = the
  agent reshapes its own evaluator and "scores highly on its own criteria while drifting from meaningful
  behavior." → **Lesson:** never train/tune on **unverified** self-generated labels; keep **behaviour=truth**,
  a **never-tuned held-out**, and **data provenance**. This is your earlier "model collapse / mental illness in
  your own head" worry, confirmed by the literature.

**Net for us:** our self-improvement loop (review → propose → **validate on held-out** → curate) is the
right shape, and our *probe-first + adversarial-verification + held-out* culture is precisely the gate the
field says is mandatory. The opportunity vs. Voyager: **refine** skills (not add-only-on-success) under a
grounded gate.

---

## Part 2 — Per-component grounding (closest prior art · status · failure mode to avoid · our guard)

| Component | Closest prior art | Status | Documented failure mode | Our guard |
|---|---|---|---|---|
| **Dual-process S1/S2** | SwiftSage, DPT-Agent, Optimus-3 | **validated** (well-trodden) | coupling: S1 freq vs S2 latency | defer-up on novelty/low-conf only |
| **Screen-only general control** | Cradle (GPT-4o GCC) | **validated + cautionary** | perception wall: VLM can't localize objects in 2D; GPT-4o-every-step cost | cheap perceiver, wake LLM only at decisions |
| **Affordance = behaviour-grounded** | WVN, V-STRONG, BADGR; Interaction-Exploration | **validated** (robotics, online) | embeddings vs hash is **domain-dependent** | hash for pixel-art; CLIP deferred to complex/3D; fail-safe to novel |
| **Self-localization / odometry** | monocular VO/SLAM; ORB-SLAM3; optical-flow VO (survey PMC11415689; MVOFormer 2606.16474) | **known-hard, well-studied** | **pure rotation + textureless/low-gradient = THE classic failures**; scale ambiguity; motion blur | *we already hit this:* optical-flow ego-motion (not frame-diff); flag dark-wall FNs; discrete not metric |
| **World model / spatial memory** | semantic SLAM; Semantic MapNet; MapNav (2502.13451) | **active research** | free-space + object **misclassification** in the map | occupancy from behaviour; map is interpretable so failures are debuggable |
| **Topological / portals** | place-graphs; ObjectNav survey | **known-hard** | "stuck in **visually similar but spatially incorrect** regions" | *exactly our portal lump/fragment + hash-alias bug* → place-ID reliability is S6 |
| **Goal-conditioned / instruction nav** | ObjectNav, VLN (SR/SPL metrics); LM-Nav, CoW | **active, mid-maturity** | failures = **62% time-outs, 29% near-miss**; ambiguous goals | named/semantic layer + arrival check; objective-injection is the easy part |
| **Skill generation (S2→S1)** | Voyager, Cradle skill curation, Reflexion | **validated + cautionary** | buggy-skill accumulation; self-reflection loops; add-only-on-success | held-out validation gate + versioning + promotion |
| **Cross-game generalization** | NitroGen, GATO, PORTAL (all training-heavy) | **our bet (zero-training)** | their cost/data-hunger | structure not weights; held-out game split |
| **Computer-use track** | Cradle; OpenAI CUA; OSWorld/WebArena; UI-CUBE (2511.17131) | **frontier, partly solved** | **OSWorld ~38–61%, WebArena ~60% vs human 78%**; desktop ≪ web; dynamic-UI 73% read-fail; agents need **1.4–2.7× more steps** | human-grade bar (vs human baseline); strategy games first (safe + scored); pixels-only honest |
| **Across-run learning** | self-improving LLMs; model-collapse work | **deferred (It4)** | data autophagy / reward hacking / feedback contamination | blank-each-run to TEST distillation; promote only proven-general, as code |

---

## Part 3 — Where our verified findings MATCH the textbook (independent validation)
- **3D ego-motion:** the VO literature names **pure rotation** and **textureless/low-gradient** scenes as the
  canonical monocular-VO failure modes. Our 3D-gate verification found *exactly* these: whole-frame frame-diff
  can't separate **rotation** from translation, and **dark/flat-wall** approaches give false-negatives. We
  rediscovered the textbook — and our fix (optical flow; treat as discrete ego-motion) is the textbook remedy.
- **Spatial memory:** ObjectNav reports failures are dominated by agents **"stuck exploring visually similar
  but spatially incorrect regions."** That is *precisely* our all-zeros-hash alias (visually-similar tiles
  conflated) and our portal lump/fragment bug. Same failure, independently found.
- **Self-correction:** we made the validation gate non-negotiable from our own three reversals; Huang et al.
  proves intrinsic self-correction degrades performance. Same conclusion, independently reached.

**Reading:** we are not off in the weeds. The design's load-bearing claims line up with what the field has
already learned the hard way — and our cheap/online/behaviour-grounded/held-out combination remains the open
gap (per the prior-art scan).

## Sources
- Voyager: https://arxiv.org/abs/2305.16291 · https://voyager.minedojo.org/
- Reflexion: https://arxiv.org/abs/2303.11366
- LLMs Cannot Self-Correct Reasoning Yet (Huang et al., ICLR'24): https://arxiv.org/abs/2310.01798
- Self-Improvement of LLMs (overview): https://arxiv.org/pdf/2603.25681 · Escaping Collapse: https://arxiv.org/pdf/2502.08924
- Monocular VO/SLAM survey: https://pmc.ncbi.nlm.nih.gov/articles/PMC11415689/ · MVOFormer (flow-semantic VO): https://arxiv.org/html/2606.16474
- Object Goal Navigation survey: https://orca.cardiff.ac.uk/id/eprint/167432/1/ObjectGoalNavigationSurveyTASE.pdf · MapNav: https://arxiv.org/pdf/2502.13451
- Computer-use: OpenAI CUA https://openai.com/index/computer-using-agent/ · UI-CUBE https://arxiv.org/pdf/2511.17131
