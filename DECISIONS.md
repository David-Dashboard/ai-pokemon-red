# DECISIONS.md — contract-change log (append-only)

`tests/test_contract_frozen.py` requires every approved frozen-contract change to land an entry here
(see `CONTRACT.md` for the process). None have happened in this repo yet — the contract has been
stable since the scaffold. Architecture decisions in general are recorded as ADRs in `reports/`
(e.g. `reports/2026-07-03-adr002-gate-plan.md`); this file is only for changes to the frozen layer.

Entry format:

```
## [YYYY-MM-DD] <one-line decision>
- Gap: <what the contract couldn't express>
- Why not soft-layer: <why no data-blob convention / runner change covered it>
- Migration: <impact + steps taken>
- New hash: <PINNED_SHA256> · Golden vectors: <contracts/golden_vectors_vN.json>
- Approved: David (CONTRACT-CHANGE-APPROVED)
```

<!-- append entries below, newest last -->
