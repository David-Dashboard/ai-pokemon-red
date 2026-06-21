# Prompt architecture — constitution-first layering (design principles)

**Why this doc exists (anti-drift).** The agent's *purpose* keeps getting absorbed into the
*persona*. Today `persona.yaml` carries the mission ("sole purpose is to play Pokémon Red… defeat
the Elite Four"). If someone rewrites the persona for another deployment, the purpose — and the
caching/dedup behaviour that depends on it — silently goes with it. These principles pin the
structure so a persona rewrite can't drift it. They are the **original** design intent
(`20260521_wishes.txt:46` "something static, unchangeable, to keep it in place";
`20260521_agentic_workflow.txt:159-164` "a small system + orientation as the cached anchor") —
the code drifted from them, this doc restores them.

## The unified spine — ONE structure for every deployment

Order blocks by **decreasing stability**. The same five layers serve any agent; a deployment just
fills them differently, and empty layers vanish (dormant-until-seeded). Top layers are the cache
anchor; bottom layers change every wake.

| # | Layer | What it is | Companion (Aria) | Trainer (Red) | Cache |
|---|---|---|---|---|---|
| 0 | **Constitution** | irreducible PURPOSE, human-authored, never retrieved | companion charter | `POKEMON_SYSTEM` | immutable → cached top |
| 1 | **Persona** | voice / style / constraints (the *how*, not the *why*) | warm companion | terse trainer | static, below constitution |
| 2 | **Derived durable knowledge** | learned facts/lessons, grow *below* the human-authored line | grows over time | thin (harness owns within-run) | near-static |
| 3 | **Retrieval** | push (by relevance) + pull (by need), over derived tiers only | relevant past | thin | volatile |
| 4 | **Working state** | the current observation/transcript | this message | this frame | never cached |

## The principles (durable — do not drift)

1. **Constitution is its own layer, above persona, and is the cache anchor.** Purpose is the most
   stable text the agent has; it belongs at the very top of the static system prefix, *separate from*
   persona. (`prompt.py:_STATIC` should gain `constitution` as its first member.)
2. **Persona is voice-only.** The persona block/`persona.yaml` must NOT contain purpose, mission, or
   objective — those live in the constitution. This is the headline anti-drift rule.
3. **Order by decreasing stability for caching.** static → near-static → volatile maps to BP1 → BP2 →
   user message (`prompt.py:55-77`). The cacheable prefix must clear the provider minimum
   (**Haiku-4.5 = 4096 tokens**); a sub-floor prefix caches *nothing* (`CODEBASE.md:1093`). The
   constitution being big + stable is what lifts the prefix over the floor.
4. **State purpose once.** Don't restate the objective across persona + place + goals (today the
   "beat the Elite Four" mission appears in `persona.yaml` *and* `place.yaml:self_concept`). One
   constitution slot dedupes it.
5. **Never replay the constitution in the volatile tail.** The transcript must not re-embed the
   constitution (today the harness staples `POKEMON_SYSTEM` into the user message, which the journal
   stores and `_transcript` replays ~6×/wake — `prompt.py:496-507`). Constitution rides the cached
   prefix once.
6. **Push + pull retrieval are scoped, not redundant.** Push = proactive relevance to *this*
   observation; pull (`memory_recall`) = agent-initiated precise lookup. Both operate **only over
   derived tiers** — the constitution and goals are *always-pushed, never retrieved*
   (`memory.yaml:index_tiers` is already derived-only). Don't query retrieval on the whole prompt.
7. **One owner for within-run memory (don't double-book).** The harness owns within-run memory by the
   learning-boundary law (it *stores + re-injects* the per-run lesson buffer + transcript;
   `core/brains.py:282,503-507`); aria *authors* lessons (`<lesson>` tags) but should not also keep
   its own per-run journal/transcript/recap for an agent the harness already tracks. Pick one store.
8. **Generalize via dormant-until-seeded, not "modes".** No `if game:` branches — each layer is a
   config-sourced slot; a deployment that doesn't set a layer simply doesn't render it (the existing
   `goals`/`entities`/`file_exchange` pattern).

## Current state vs target (where the code diverges)

- The 3-tier stability split ALREADY exists (`prompt.py:55-77`) — but the top is `persona`, **there is
  no `constitution` slot**, and purpose is diffused into persona + place.
- The trainer's constitution (`POKEMON_SYSTEM`) rides the **uncacheable user message** (harness,
  `core/brains.py:565`), so it duplicates ~7×/wake and the cacheable prefix stays sub-4096 → ~34%
  cached vs the companion's ~80%. Fixing layer 0 fixes caching *and* the duplication at once.

## Open decision (record) — who owns the trainer's within-run memory?

- **α (leaning):** aria is a *stateless* brain for the trainer; the harness owns within-run memory and
  feeds it in the observation. Matches the learning-boundary *author-vs-store* split; removes the
  duplication. 
- **β:** aria owns within-run memory (generalize its tiers); harness stops duplicating. More "pure
  aria" but couples the trainer to aria persistence.

Status: **undecided** — α preferred. (See the cost root-cause in
`ai-pokemon-red/reports/2026-06-20-cost-investigation.md`.)
