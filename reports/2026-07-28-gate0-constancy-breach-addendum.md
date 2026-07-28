# Gate 0 — CONSTANCY_BREACH addendum: mechanical cause, proven (2026-07-28)

Addendum to `reports/2026-07-24-gate0-paired-verdict.md`. Scope: prove, mechanically and at $0, why
both banked paid Gate-0 arms carry `audit_overall: "CONSTANCY_BREACH"`, and close the one open
question that report left flagged.

**No paid run, no LLM call, no episode re-execution, no docker.** Every result below is a pure
function over artifacts already on disk. Nothing under `runs/` was modified, moved, or added.

Reproduction scripts (committed): `reports/probes/2026-07-28-gate0-breach-addendum/reproduce_breach.py`
and `reports/probes/2026-07-28-gate0-breach-addendum/diff_tool_schema_bytes.py`.

---

## 1. Governance outcome — decided, stated first, not up for reinterpretation

**The banked `CONSTANCY_BREACH` stands. Both paid arms remain void as Gate-0 evidence.**

`reports/2026-07-18-gate0-prereg.md:117-118`, verbatim:

> **What aborts vs banks:** `NO_LEAK` or `CONSTANCY_BREACH` void the attempt as evidence — "the
> result is a constancy breach, not a capability verdict" (design doc:117-118); constancy/no-leak
> checks run before task scoring, so neither is a capability outcome.

`reports/2026-07-13-minimum-north-star-gate-0-design.md:372-373`, verbatim:

> 7. Bank PASS/FAIL/INSUFFICIENT_DATA/CONSTANCY_BREACH as printed. Never rescue a
>    marginal result with an informal rerun.

Knowing the cause was benign is precisely the circumstance those rules exist to defeat. A
pre-registration that can be reinterpreted once the result is visible is decorative. This addendum
converts "banked breach, cause unclear" into "banked breach, cause proven" — so that the
fixture-lifecycle bug is fixed before the next attempt. **It does not restore the result.**

---

## 2. What fired, and what did not

`tools/check_gate0_codex.py::audit()` returns four independent failure lists and picks `overall` by
strict precedence (`check_gate0_codex.py:282-291`): leak → constancy → run → accounting → the
permanent `NO_GO_INSUFFICIENT_WAKES` floor.

| list | miniwob | red | meaning |
|---|---|---|---|
| `leak_failures` | `[]` | `[]` | no non-target MCP server, no non-allowlisted tool, no forbidden item type, transcript well-formed. `no_leak: "PASS"` on both arms. |
| `constancy_failures` | 2 | 2 | **the breach.** Both entries are `pin_mismatch:*`. |
| `run_failures` | `[]` | `[]` | no `turn.failed`, no `error` event. |
| `accounting_failures` | `[]` | `[]` | token usage observable and well-typed on every `turn.completed`. |

Two fields in the receipts are **non-events** and must never be read as run outcomes:

- `readiness: "NO_GO_INSUFFICIENT_WAKES"` and `paid_execution_enabled: false` are **hardcoded
  constants** at `tools/gate0_appserver_arm.py:476-477`, required *verbatim* by
  `tools/check_gate0_codex.py:50-53` (`readiness_not_fail_closed` / `paid_execution_not_disabled`).
  Verified: all **14** `handshake-receipt.json` files in the repo (12 under `runs/`, 2 committed
  copies under `reports/`) carry the identical pair. They describe the harness's fail-closed wake
  accounting and the absence of a `codex exec` path, not what this run did.

---

## 3. Reproduction — both arms, both modes ($0, pure function)

`reproduce_breach.py` calls the frozen `audit()` against each arm's banked artifacts. The receipt
`audit()` reads is `handshake-receipt.json` (`schema_version: 2`, the 20 `PIN_FIELDS`) — *not*
`run-receipt.json`, which is a separate `schema_version: 1` summary carrying `audit_overall` and
`launcher_sha256`.

**Mode A — raw fixture** (`eval/fixtures/gate0_expected_pins_{arm}.appserver.json` verbatim). This is
what the launcher at the banked `launcher_sha256` actually did.

| arm | `overall` | `constancy_failures` |
|---|---|---|
| miniwob | `CONSTANCY_BREACH` | `['pin_mismatch:config_sha256', 'pin_mismatch:codex_mcp_list_sha256']` |
| red | `CONSTANCY_BREACH` | `['pin_mismatch:config_sha256', 'pin_mismatch:codex_mcp_list_sha256']` |

Both reproduce the banked `audit_overall` exactly. `leak_failures`, `accounting_failures`,
`run_failures` all `[]` on both arms.

**Mode B — post-fix `resolve_expected_pins()` substitution** (what the current launcher does):

| arm | `overall` | `constancy_failures` |
|---|---|---|
| miniwob | `NO_GO_INSUFFICIENT_WAKES` | `[]` |
| red | `NO_GO_INSUFFICIENT_WAKES` | `[]` |

**The RED arm reduces to exactly the same two placeholder fields as MiniWoB** — this had not been
checked before. Not a different or larger failure set: identical.

Both failures are a real 64-hex hash compared against the literal placeholder string
`CONSTRAINT:launch-invocation-dependent-recompute-at-signature`, pinned at
`eval/fixtures/gate0_expected_pins_miniwob.appserver.json:21-22` and
`eval/fixtures/gate0_expected_pins_red.appserver.json:20-21`. The remaining **18** `PIN_FIELDS` match
exactly on both arms — including `world_image_id`, `tool_schema_sha256`, `brain_config_sha256`,
`task_sha256`, the MCP server/tool inventory, and host-vs-image code parity
(`host_code_sha256 == image_code_sha256`, i.e. no `stale_world_image`).

**Reading Mode B correctly — `NO_GO_INSUFFICIENT_WAKES` here is not a verdict.** What Mode B proves
is that with the pin resolution applied, **both arms' failure lists are empty** — `constancy`,
`leak`, `accounting`, and `run` all `[]`. The accompanying `overall: "NO_GO_INSUFFICIENT_WAKES"` is
`audit()`'s *terminal value for any clean run*: `check_gate0_codex.py:290-291` is the final `else`
after the four failure-list branches, and `wakes`/`wake_accounting` are hardcoded literals at
`:297-298`. A clean audit cannot report anything else on that field. It is a floor, not a finding.

Do not quote it as the gate result. `reports/2026-07-18-gate0-prereg.md:81-83`, verbatim:

> - `tools/check_gate0_codex.py`'s own `overall`/`no_leak`/`wake_accounting` fields (e.g.
>   `NO_GO_INSUFFICIENT_WAKES`) are an **intermediate per-arm audit input** consumed by
>   `score_gate0.py`, not the gate's printed verdict — do not quote them as the Gate 0 result.

The Gate-0 verdict is `eval/score_gate0.py::score()["overall"]`, which **does** reach `PASS`/`GO`
(`score_gate0.py:359-360`, the terminal `else`). `score()` consumes only the four failure lists —
`leak_failures`/`constancy_failures`/`run_failures` at `:307-310` and `accounting_failures` at
`:326` — and never reads `audit["overall"]`. Wakes have been **deferred and explicitly non-gating**
since David's 2026-07-21 decision (`score_gate0.py:263-270`, `:290-291`, and the verdict payload's
`wake_accounting: {"status": "DEFERRED"}` at `:366-372`). Gate 0 was structurally unpassable for
exactly one day — 2026-07-21, while the pre-amendment scorer still required
`wake_accounting == "PASS"` — documented and closed at
`reports/2026-07-13-minimum-north-star-gate-0-design.md:412-415`.

So: Mode B does not show the harness is unpassable. It shows the *pin chain* would have been clean.

**And the harness was not what stopped these arms.** Both frozen capability predicates ran and
returned `False` on real, substantive grounds, independent of every pin issue in this addendum:
Arm R on `red_no_sustained_battle_exit` (`reports/2026-07-24-gate0-paired-verdict.md:37`) and Arm W
on `miniwob_episode_1_terminal_not_success` — seed 1001 at reward 0.667, a genuine partial (`:49`).

**But a clean pin chain would not have produced a capability verdict either.** `score()`'s
precedence (`eval/score_gate0.py:347-360`) is leak → constancy → **infra → source** → capability →
cheap. The banked attempt carries **20 `source` failures** that have nothing to do with the pins
(`reports/2026-07-24-gate0-paired-verdict.md:212-233` — e.g. `source_unreadable:miniwob_human`,
`frozen_seed_hash`, the `missing_or_invalid_metric:*` set). With the pins fixed, the printed verdict
would be `INSUFFICIENT_DATA` / `INSUFFICIENT_SOURCE` — the scorer would short-circuit at the source
tier and never reach `capability`. This is exactly what `HANDOFF.md:187-189` already says ("do not
read this as `INSUFFICIENT_DATA`; that is what a fixed pin-chain would return"), and this addendum
must not be read as contradicting it.

So, precisely: **real capability shortfalls were observed by the frozen predicates, while the gate's
printed verdict was — and would remain — blocked at the source tier until the MiniWoB paid-seed
human baseline exists.** The gate did not discriminate on capability; the predicates did. The breach
is a measurement-chain defect that voided the attempt, not the reason the arms fell short, and
nobody should read this addendum as blaming the harness for the outcome.

---

## 4. Commit-timing proof — the launcher that ran predates the fix

`run-receipt.json:launcher_sha256` on **both** arms is
`b21d30124737e224190f8a94cc2c51a97c29d0e1dc4ee97ef26dd1673e01464f`. Verified byte-exact against
`git show c838355:tools/gate0_appserver_arm.py | sha256sum` → same digest. That commit's
`_finalize_real_run` passed the RAW fixture straight to `audit()`.

The fix — `resolve_expected_pins()`, substituting the run's own pre-turn receipt values for the two
placeholder fields — landed in `3c3f704` ("fix(gate0-appserver): resolve expected-pins gap causing a
benign CONSTANCY_BREACH").

| event | timestamp (+0200) |
|---|---|
| `c838355` committed (the launcher that ran) | 2026-07-24 15:53:42 |
| **Arm R (red)** finished — `run-receipt.json` written | 2026-07-24 **16:00:11** |
| **Arm W (miniwob)** finished — `run-receipt.json` written | 2026-07-24 **23:44:26** |
| `3c3f704` authored / committed (the fix) | 2026-07-24 23:56:06 / **23:57:02** |

The fix postdates the miniwob arm by **12m36s** and the red arm by **7h56m51s**. Neither run could
have used it.

Corroborating, independent of timestamps: `expected-pins.resolved.json` — which the post-fix path
writes to the run dir (`gate0_appserver_arm.py:1180`) — is **absent from both run directories**.
Verified programmatically, not by eye.

---

## 5. The third failure: `pin_mismatch:tool_schema_sha256` — CLOSED, byte-level

`eval/score_gate0.py` (the actual Gate-0 scorer, distinct from `check_gate0_codex.py`) is hard-pinned
by `eval/fixtures/gate0_paid_source_pins.json:audit_paths` to the **non-**`.appserver` exec-era
fixtures. Reproduced (Mode C in `reproduce_breach.py`):

| arm | `overall` | `constancy_failures` | `peer_constancy` |
|---|---|---|---|
| miniwob | `CONSTANCY_BREACH` | `['pin_mismatch:config_sha256', 'pin_mismatch:codex_mcp_list_sha256', 'pin_mismatch:tool_schema_sha256']` | `PASS` |
| red | `CONSTANCY_BREACH` | `['pin_mismatch:config_sha256', 'pin_mismatch:codex_mcp_list_sha256', 'pin_mismatch:tool_schema_sha256']` | `PASS` |

`reports/2026-07-24-gate0-paired-verdict.md:281-296` flagged this as "flagged, not fixed, not
certain", guessing "whitespace/key-order". **It is a serialization difference. The guess was right in
kind and wrong in detail: key order is identical.** Two byte streams, both already on disk:

- **PS (exec era)**: `runs/gate0_readiness_2026-07-14/{red-v3,miniwob-v2}/mcp-tools.json` — PowerShell
  5.1 `ConvertTo-Json -Depth 20 -Compress` + trailing LF. These hash to
  `e55bb819…7ffa71` (red) and `6c3d4131…5647e805` (miniwob) — i.e. they *are* the bytes behind the
  frozen exec-era pins.
- **PY (app-server)**: `runs/gate0_paid/{red,miniwob}/mcp-tools.json` — `json.dumps(tools) + "\n"`.
  Hash to `102e4cb3…c877c3e` (red) and `d3eb9d0f…d3d1c17` (miniwob) — the banked receipt values.

Decoded, the two streams are **the same object**: `json.loads(PS) == json.loads(PY)` is `True` on both
arms, key order identical, tool-name lists identical to the frozen allowlists. **The tool surface
never changed.** First divergent byte is at offset **9** — inside `[{"name":` — i.e. before any
content.

Exactly three serialization axes differ:

1. **Separators.** PS `-Compress` emits `","` / `":"`; Python `json.dumps` defaults to `", "` / `": "`.
   Both arms. (red 2811 → 2936 bytes; miniwob 2501 → 2633 bytes.)
2. **Non-ASCII escaping.** The tool descriptions contain `U+2014` EM DASH. PS emits it as raw UTF-8;
   Python defaults to `ensure_ascii=True`, emitting the six ASCII bytes `\u2014`. Both arms.
3. **ASCII apostrophe escaping.** PowerShell 5.1 escapes `'` (`U+0027`) as `\u0027`; Python never
   does. **Red only** — the red tool descriptions contain 4 apostrophes ("your last move's outcome"),
   the miniwob descriptions contain 0.

Proof, not inference — re-serializing the *banked app-server object* with the PS recipe reproduces the
frozen exec-era pin bytes exactly:

- miniwob: `json.dumps(obj, separators=(",",":"), ensure_ascii=False).encode() + b"\n"`
  → `6c3d413199eae79f197ec219019bc6e8f82bb947d51f601f319a52bc5647e805` — **byte-identical** to
  `runs/gate0_readiness_2026-07-14/miniwob-v2/mcp-tools.json` and equal to
  `eval/fixtures/gate0_expected_pins_miniwob.json:tool_schema_sha256`.
- red: the same, plus `.replace("'", "\\u0027")`
  → `e55bb8193f0c3ecb531519db2b93a3a597dbd97d9cb42468e63334c1ae7ffa71` — **byte-identical** to
  `runs/gate0_readiness_2026-07-14/red-v3/mcp-tools.json` and equal to
  `eval/fixtures/gate0_expected_pins_red.json:tool_schema_sha256`.
  (Axes 1+2 alone yield `efa7764a…` ≠ the pin — axis 3 is load-bearing for red and inert for miniwob.)

Ruled out explicitly, measured not assumed: **not** key ordering (identical), **not** a trailing
newline (both streams end in exactly one LF), **not** a BOM (neither has one), **not** CRLF (zero CRLF
in either stream).

`eval/fixtures/gate0_expected_pins_{arm}.appserver.json` already re-derived this pin under the Python
recipe on 2026-07-24/25, which is why the `.appserver` audit shows only two failures and the
exec-fixture audit shows three. The exec-era fixtures were never migrated; nothing here suggests they
should be — they are frozen for the exec path.

---

## 6. Where the cause sits

`reports/2026-07-24-gate0-paired-verdict.md:272-280` already diagnoses the pin-freeze gap correctly
(structural, pre-existing, identical in exec-era and appserver-era fixtures, not a real config
divergence). This addendum does not restate it — see there. What this addendum adds is the mechanical
proof: reproduced verdicts for both arms in both modes, the launcher-hash-to-commit binding, the
timestamps, the absent `expected-pins.resolved.json`, and the byte-level close-out above.

---

## 7. What must change before the next attempt

**The fixture placeholder lifecycle must be fixed so that a correctly-executed run cannot breach on
launch-dependent pins.** Concretely (design only — not implemented here):

1. **A fixture must never ship a placeholder into `audit()`'s `expected_pins` argument.** Today, a
   `PIN_FIELD` whose true value cannot be known until launch is stored as a literal sentinel string
   that `_expected_failures()` — correctly, being a dumb equality check — can only ever report as a
   mismatch. `resolve_expected_pins()` patches this one layer above `audit()`, which works, but it is
   opt-in per launcher: any future launcher that forgets the call reproduces this breach exactly.
   The placeholder-resolution step belongs in the **fixture-loading path**, not in one launcher.

2. **Make the launch-dependent fields structurally distinguishable from real pins.** Move
   `config_sha256` / `codex_mcp_list_sha256` out of the flat `PIN_FIELDS` namespace into an explicit
   `launch_resolved` block in the fixture schema (`schema_version: 3`), so the *schema itself* says
   these are resolved at launch. A loader then either resolves them or refuses to run — it cannot
   silently compare a hash to a sentinel. This also stops the placeholder from being mistakable for a
   frozen pin during review.

3. **Add a pre-launch dry-run gate.** Before any paid turn spawns, run `audit()` against the
   *pre-turn* receipt and the resolved fixture. If `constancy_failures` is non-empty at that point,
   abort **before** spending — every field in it is launch-mechanics, knowable at $0. A paid run
   should never be the thing that discovers a pin-chain bug.

4. **Close the coverage the substitution costs.** `resolve_expected_pins()`'s own docstring
   (`gate0_appserver_arm.py:575-584`) states honestly that comparing `config_sha256` to itself is a
   tautology, leaving the *world half* of `config.toml` (`default_tools_approval_mode`, timeouts,
   `--network none`, mount `readonly` flags, `--out`/`--init-state`) with no independent pin. The
   fixture-schema change in (2) should carry a real field-level pin on that world half, analogous to
   `brain_config_sha256` for the brain half.

5. **Reconcile the exec-era vs app-server `tool_schema_sha256` recipes explicitly.** §5 proves the two
   are the same inventory under two serializers. Whichever fixture the next attempt's scorer is
   pinned to must be the one matching the launcher's actual write recipe, and the pin's
   `_source_*` note must name the serializer byte-for-byte. Do not "fix" this by editing the frozen
   exec fixtures.

None of this is a re-run authorization. It is the precondition for the *next* pre-registered attempt.

---

## 8. Downstream citations needing a void caveat

Every location below cites the paired Gate-0 result as evidence. Each was re-read on 2026-07-28 and
still says what is claimed here.

**Edited in this change** (one line each, pointing here — the surrounding text is untouched):

- `HANDOFF.md:181-185` — Arm W "DONE", 4/5 at reward 1.0.
- `HANDOFF.md:186-193` — frozen scorer run verbatim, 6 `pin_mismatch` + 20 source failures.
- `.claude/skills/world-lanes-frontier/SKILL.md:27` — MiniWoB lane row, "Gate-0 checkboxes 4/5 reward
  1.0 (2026-07-25)".
- `.claude/skills/world-lanes-frontier/SKILL.md:176-178` — "Checkboxes RAN", 5 episodes / 4-of-5.
  (:180-182 already notes the verdict is `CONSTANCY_BREACH`/`NO_GO`; the added line at :183 supplies
  the *void* consequence and the pointer, which that note does not.)
- `.claude/skills/world-lanes-frontier/SKILL.md:258` — paired-verdict listed among banked verdicts.
- `.claude/skills/world-lanes-frontier/SKILL.md:267` — `HANDOFF.md:23-28` cross-reference.

  (Cited line numbers for SKILL.md are post-edit; the added line shifted the pre-edit `:257`/`:266`
  by one. `HANDOFF.md`'s cited lines are unshifted — the caveat was appended below them, at `:196`.)

**Not edited — the report is itself the banked artifact and stays as printed** (this addendum is the
caveat; it is linked from the two documents above):

- `reports/2026-07-24-gate0-paired-verdict.md` §2b (:45-63) — Arm W predicate + per-episode table.
- `reports/2026-07-24-gate0-paired-verdict.md` §4 (:189-300) — frozen scorer walk-through.
- `reports/2026-07-24-gate0-paired-verdict.md` §5 (:350-356) — Arm W in detail.
- `reports/2026-07-24-gate0-paired-verdict.md` §6 (:370) — "MiniWoB solved 4/5 held-out seeds
  perfectly".

The per-episode measurements in those sections remain real observations of what the agent did. What
is void is their use **as Gate-0 evidence** — the gate is what the breach voids, not the telemetry.

---

## 9. Corrections to the prior audit

- **The red arm did not finish at 23:44.** That is the miniwob arm. Red's `run-receipt.json` was
  written at 2026-07-24 **16:00:11 +0200** — 7h56m before the fix commit, not 13 minutes. The
  "13 minutes after" framing holds for miniwob only (12m36s, receipt 23:44:26 → commit 23:57:02).
- **The audited receipt is `handshake-receipt.json`, not `run-receipt.json`.** `run-receipt.json` is
  `schema_version: 1` and lacks every `PIN_FIELD`; it would fail `_receipt_shape_failures` on
  `receipt_schema` alone. `run-receipt.json` is where `launcher_sha256` and `audit_overall` live —
  that part of the prior audit is right — but the pin comparison runs against the handshake receipt.
- **The red fixture placeholder is at :20-21, not :21-22.** `:21-22` is correct for miniwob only; the
  red fixture has one fewer leading `_`-comment key.
- **"Whitespace/key-order" was the wrong detail.** Key order is identical between the two
  serializations. The axes are separators, non-ASCII escaping, and PowerShell-5.1-specific apostrophe
  escaping (§5).

Everything else in the prior audit checked out: the two-field failure list, the empty leak/accounting/
run lists, the 18 matching pins, the launcher-hash-to-`c838355` binding, the absent
`expected-pins.resolved.json`, the `:476-477` / `:50-53` hardcoded-constant chain, and "identical in
all 14 handshake receipts" (12 under `runs/`, 2 committed under `reports/` — verified, all 14 carry
the identical pair).
