# Prior-art scan — who's doing something similar? (2026-06-22, quick)

Question: is anyone doing what we do — a **cheap, screen-only, ONLINE behaviour-grounded, dual-process
agent that generalizes across games** (and toward 3D/reality)? Short answer: **the pieces are each
well-trodden, but our specific COMBINATION sits in a real gap.** Where we overlap = reuse; where we're
alone = the bet worth making.

## Closest works
- **Cradle — General Computer Control (BAAI, GPT-4o, ICML 2025)** — the flagship *screen-only* general
  agent: screenshots in, keyboard/mouse out; modular (info-gather, self-reflect, task-infer, **skill
  curation**, planning, memory); runs RDR2 / Stardew / Cities:Skylines + real software. **Crucial for us:
  its headline limitation is PERCEPTION** — "GPT-4o struggles to recognize/locate objects near the player
  in 2D games," real-time combat, timing. That directly VALIDATES our thesis: perception (cheap, accurate,
  localized) is THE bottleneck, and GPT-4o-every-step is the wrong hammer. *Our edge: dual-process +
  cheap behaviour-grounded perception instead of an expensive VLM per step.*
- **Self-supervised traversability — WVN (Wild Visual Navigation, RSS'23), V-STRONG, BADGR-lineage** — the
  ROBOTICS analog of our tile→function map: learn "where I drove = traversable" from the robot's OWN
  experience and generalize by visual features; WVN does it **online, real-time, adapting in <5 min**. This
  is the closest analog to our behaviour=truth → appearance-generalizes idea. **Tension worth noting:** they
  make *visual-feature embeddings* (DINO/ViT) work for traversability via online + contrastive learning —
  whereas we found embeddings (CLIP) FAIL cross-tileset for GB walkability and a hash won. Likely a domain
  gap (natural terrain: appearance↔function correlates; GB tilesets: it doesn't). *Adopt: their online
  supervision + fast-adaptation; possibly a light online-adapted feature for the cross-tileset case the hash
  defers on.*
- **Dual-process System-1/2 for real-time games — DPT-Agent, Optimus-3 (Minecraft MoE), SwiftSage** —
  exactly our ADR-001 split: "small/fast System-1 visuomotor loop + LLM System-2 selective reasoning reduces
  cost"; the coupling dilemma (S1 high-freq/low-latency vs S2 low-freq/deep) is openly discussed. *So our
  architecture is well-grounded; the split itself is NOT our novelty.*
- **Cross-game generalist agents — NitroGen (2026), GATO, PORTAL** — generalize across many games, but via
  the OPPOSITE method: internet-scale **behavior cloning** on gameplay video (NitroGen, +52% on unseen
  games), pixel-sequence transformers (GATO), or LLM-generated behavior trees (PORTAL, 1000s of 3D games).
  All expensive / data-hungry / training-heavy. *Our niche: cheap, online, NO training, screen-only.*
- Also: **Orak** (LLM-agent game benchmark, 2026), **Tile Embedding** (proc-gen level representation),
  **Interaction Exploration / "What can I do here"** (affordances from the agent's own attempts).

## Where we are well-trodden (REUSE, don't reinvent)
- Dual-process S1/S2 (SwiftSage/DPT-Agent) · skill curation (Cradle) · behaviour-grounded affordance from
  own experience (WVN/Interaction-Exploration) · screen-only general control (Cradle).

## Where we're genuinely in a gap (the bet)
**The intersection nobody occupies:** cheap + screen-only + **online, no-training** + behaviour=truth
appearance→function world model + dual-process + **explicit cross-GAME perception-generalization with a
held-out methodology** + a deliberate 2D→3D→reality ladder. Cradle is screen-only-general but
GPT-4o-every-step + perception-weak; WVN is behaviour-grounded-online but robotics + embeddings; NitroGen
is cross-game but big-behavior-cloning. We sit at their centre for *games, cheaply, online*.

## Adopt / Avoid
- **Adopt:** WVN's online self-supervised supervision + fast adaptation; Cradle's skill curation (already
  flagged for S5); the validated S1-small/S2-LLM cost split.
- **Avoid:** internet-scale behavior cloning (NitroGen/GATO) — against the cheap thesis; GPT-4o-every-step
  (Cradle) — the cost + perception trap we're explicitly routing around.

## Sources
- Cradle: https://arxiv.org/abs/2403.03186 · https://baai-agents.github.io/Cradle/
- WVN: https://www.roboticsproceedings.org/rss19/p054.pdf · V-STRONG: https://arxiv.org/pdf/2312.16016
- DPT-Agent: https://arxiv.org/html/2502.11882v3 · Optimus-3: https://arxiv.org/pdf/2506.10357 · SwiftSage: https://arxiv.org/pdf/2305.17390
- NitroGen: https://arxiv.org/pdf/2601.02427 · PORTAL (1000s of 3D games): https://arxiv.org/html/2503.13356v1 · Orak: https://arxiv.org/pdf/2506.03610
- LLM-and-Games survey: https://arxiv.org/pdf/2402.18659 · GPA-LM list: https://github.com/BAAI-Agents/GPA-LM
- Interaction Exploration affordances: https://arxiv.org/pdf/2008.09241 · Tile Embedding: https://arxiv.org/pdf/2110.03181
