# CLAUDE.md

## What this project is

The **embodiment stone layer**: a frozen contract that lets one domain-agnostic
Brain drive many embodiments — pixel-games, turn-based, RTS, FPS, the real
desktop, and drone/robot — by *naming skills* rather than emitting coordinates
or motor commands. Architecture and rationale: `CONTRACT.md`. Everything not yet
constant (risk ledger, staleness rejection, multi-agent stepping, severity
policy) and the adversarial review findings behind those calls: `HYPOTHESES.md`.

This is the sibling of the Arena tool-call stone layer. A `DomainPlugin` here
generalizes Arena's `GamePlugin`; the freeze discipline, the JSON wire, and the
§3 change process are inherited wholesale.

## ⛔ STANDING ORDER: the stone layer is frozen

These paths are FROZEN and must never be edited, renamed, moved, reformatted,
re-typed, or "improved" — regardless of what a task seems to require:

- `core/contracts.py`
- `contracts/golden_vectors_v*.json`
- `tests/test_contract_frozen.py`
- `scripts/pre-commit`

Do not update `PINNED_SHA256` to make a failing test pass, do not add fields,
do not modernize typing, do not delete "redundant" comments. The hash pin
failing after your edit is the system working, not a bug.

If a task genuinely seems to require a contract change: **STOP.** Draft an RFC
per `CONTRACT.md` §3 and present it. Only a human executes contract changes,
with the `CONTRACT-CHANGE-APPROVED` commit token. In almost every case what
looks like a needed contract change is solved in the soft layer — a convention
inside `data`, a Controller/Gateway change, or a plugin-side encoder. Check
`HYPOTHESES.md` first: most "missing" structure is deliberately deferred there.

## Implementation workflow (follow for every change)

1. **Plan with Opus.** Design the change in Opus (plan mode); get the plan
   agreed before any code is written. For anything touching the contract
   boundary, the plan must cite which `CONTRACT.md` invariant or `HYPOTHESES.md`
   entry it relies on.
2. **Feature branch.** Cut a branch off `main` before implementing — never work
   on `main` directly.
3. **Implement with a Sonnet agent.** Hand the agreed plan to a Sonnet subagent
   to do the build.
4. **PR + adversarial review loop before merge.** Open a PR, then send out
   review agents (**fewer than 5**) to critique it adversarially — each posts
   findings as PR comments (`/code-review --comment`, or reviewer subagents).
   Bias the reviewers toward the standing adversaries in `HYPOTHESES.md`
   (concurrency, safety/red-team, type-evolution, multi-agent, learnability,
   eval-integrity) so review pressure matches the contract's known weak axes.
   The implementer addresses every comment; repeat review → fix until confident
   it's safe. Only then merge to `main`.

## Verification ritual

Before and after any work session:

    python -m pytest tests/test_contract_frozen.py -q

All green = the stone layer is intact. Red = stop and tell the human; never
"fix" by editing a frozen path.

## Hard rules inherited from the contract (obey when writing soft code)

- All Brain→world interaction goes through the Gateway. A Brain never calls a
  plugin method directly.
- Errors are observations: return `Outcome(ok=False, ...)`, never raise across
  the boundary.
- Everything on the wire is plain JSON. Deep-copy at the Gateway boundary (wire
  dataclasses are only shallowly frozen).
- Import wire types from `core.contracts`; never copy their definitions.
- The Brain names a `Skill.handle` and fills typed params. It never emits
  coordinates or motor commands — those are the Controller's job.
- Real-world embodiments implement `DomainPlugin` only — never fake `Replayable`
  (`reset`/`terminal`) on a drone or a live desktop.
- Mutating, irreversible, or high-cost skills on real-world plugins must route
  through a Gateway permission policy that is NOT allow-all. AI never gets
  unsupervised write access to real systems — approval queue required.

## Layout

    core/        contracts.py                              (FROZEN)
    core/        gateway, controllers, brains, runner      (soft — churn freely)
    contracts/   golden vector files                       (FROZEN)
    domains/     one folder per embodiment plugin          (soft)
    experiments/ YAML configs                              (soft)
    tests/       test_contract_frozen.py is FROZEN; rest soft
    scripts/     pre-commit hook                           (FROZEN)
