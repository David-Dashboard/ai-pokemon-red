r"""Gate 0 Arm R human-baseline capture rig (Pokemon Red, bedroom -> starter -> rival win).

HARD LAW: this script only launches the emulator, times, records, and writes artifacts. It never
presses a button and never decides an action -- the actual playthrough must be performed by a human
(David) on the real keyboard, watching the real PyBoy SDL2 window. That is what makes the resulting
wall_clock_s/primitive_actions numbers a valid human baseline for the R0 "<=2.0x human" bar
(reports/2026-07-13-minimum-north-star-gate-0-design.md "Capability bar"; provenance requirement
from reports/2026-07-18-gate0-prereg.md precondition 6, "who/when").

Reuses, rather than reinvents:
  * games.pokemon_red.memory_map.read_state / world_mcp.GAMES["pokemon_red"]["watch"] for the exact
    RAM addresses the real agent-facing oracle uses (never duplicated/guessed here).
  * eval.score_gate0._red_success -- the SAME frozen end-state predicate the paid scorer will run
    against the agent's own trajectory -- to detect completion live and to score this human run.
    (eval/score_gate0.py landed on `main` via PR #114 on 2026-07-18, merged same day as this rig's
    branch point; earlier readiness/pre-reg drafts describing it as "not yet on main" are stale.)
  * games.pokemon_red.emulator.ensure_sdl_dll_path + PyBoy's own default SDL2 keymap (arrows=d-pad,
    'a'=A, 's'=B, Enter=Start, Backspace=Select -- see human_play.py), same convention as the
    project's other human-play scripts (human_play.py, play_record.py).

Three modes, selected with a REQUIRED `--mode` (see "Why --mode has no default" below):
  * `readiness_dev` -- the readiness-phase capture. This is the mode the banked
    `runs/gate0_human_baseline/red/human_metrics.json` was produced under. Every capture path is
    byte-identical to the pre-`--mode` rig -- same effective output directory, same artifact, same
    exit codes -- with FOUR measured, enumerated exceptions (see the deviations log's D5 for the
    full table; three refuse where the old rig wrote, one suppresses a warning that was false):
    `--test` under a paid mode's real path, an `--out` under a paid mode's real path without
    `--test`, and both of those reached via a differently-SPELLED path (UPPER/lower/mixed case, a
    junction, an 8.3 short name -- review D3). The fourth is that last spelling change seen from the
    other side: a non-`--test` `--out` naming readiness_dev's OWN directory in a different case no
    longer prints "outside the canonical real baseline path", because it is not outside it. Nothing
    that used to be written stops being written, and nothing new is written anywhere.
  * `paid_gate0` -- Gate 0 v1's paid mode.
  * `paid_gate0_v2` -- Gate 0 v2's paid mode (reports/2026-07-25-gate0-v2-prereg.md P1c).

Unlike Arm W, Red has NO held-out seed family: the design doc's "Red uses the same fixed start for
agent and human" means every mode replays the SAME savestate against the SAME frozen predicate. So
`--mode` here changes exactly two things -- the `mode` field stamped into `human_metrics.json` (which
eval/score_gate0.py::_verify_sources requires to EQUAL the mode being scored) and which directory the
artifact lands in. It does NOT change the task, the seeds, the predicate, or what David is shown.
Both paid modes are still gated behind `--i-am-human`, for the reason in HELD_OUT_MODES' comment.

Usage (see DAVID_BASELINES.md for the full walkthrough):
    uv run python tools/capture_gate0_baseline_red.py --mode readiness_dev
    uv run python tools/capture_gate0_baseline_red.py --mode paid_gate0_v2 --i-am-human

Writes, on a DETECTED SUCCESS (oracle-only end-state, exactly eval.score_gate0._red_success):
    <out>/human_metrics.json   -- schema_version 1, arm=red, role=human, mode=<--mode>,
                                   wall_clock_s, primitive_actions (+ provenance extras)
    <out>/oracle.jsonl          -- append-only watch-row trace (raw data law)

`<out>` defaults per mode (all gitignored under runs/, never committed) -- one directory PER MODE so
a paid capture's DEFAULT output cannot collide with, or be confused with, the banked readiness_dev
one:
    readiness_dev -> runs/gate0_human_baseline/red/          (unchanged; the banked artifact)
    paid_gate0    -> runs/gate0_paid_human_baseline/red/
    paid_gate0_v2 -> runs/gate0_paid_v2_human_baseline/red/
Separate defaults are NOT on their own a safety property, and this docstring used to overclaim that
they were: an explicit `--out` can still name another mode's directory. What binds that is the
WRITE-PATH GUARD in run() (see the block marked "THE WRITE-PATH GUARD"): every write this rig makes
lands inside `args.out`, so `args.out` is the single choke point both the mode-derived default and
an explicit `--out` pass through, and the guard sits there. It has three clauses:
  (a0) UNC/device `--out` (`\\host\share\...`, `\\localhost\C$\...`, `\\.\C:\...`,
      `\\?\Volume{GUID}\...`, `\\?\GLOBALROOT\GLOBAL??\C:\...`) is refused outright, because clauses
      (a)/(b) provably cannot answer for it -- see _is_unc_or_device_path. Conditional on every
      MODE_CONFIG referent being a drive path, so a share-hosted checkout is not bricked; the
      residual that leaves is spelled out at the clause and in DAVID_BASELINES.md.
  (a) UNCONDITIONAL, every mode, every flag -- `--out` may never be at or under a DIFFERENT mode's
      real baseline path. Referent is MODE_CONFIG, a module constant, never fixture contents.
  (b) `--test` additionally may never write under the selected mode's OWN real path, so a smoke test
      can never touch any of the three.
None is overridable by --test/--i-am-human/--allow-retake, (a)/(b) compare NORMALISED paths (see
_under_real_path, and read its docstring before touching it -- both the symmetry and the union of
two normalisations are load-bearing invariants that a plausible-looking simplification breaks), all
are directory-wide (so the append-only oracle.jsonl is covered, not just human_metrics.json), and
all run before the exists() test and before any mkdir, so a refusal creates nothing on disk. Shape
ported from PR #196's write_artifact() guard.
require_fixture_points_here is a SEPARATE, weaker question -- "will the scorer read what I am about
to write?" -- and is deliberately NOT the thing standing between a paid mode and the banked tree:
review D1 showed that binding safety to a fixture-derived comparison made the answer correct only by
accident, and that today's fixtures invert the accident into a blessing.
This mirrors tools/capture_gate0_baseline_miniwob.py's MODE_CONFIG exactly. It is NOT derived from
the mode's source-pins fixture, deliberately: all three fixtures currently pin `artifact_paths.
red_human` at the readiness_dev path, so deriving the OUTPUT from the pin would make a v2 capture
overwrite a banked artifact that three fixtures freeze by digest -- precisely what the prereg
(:264-269) forbids when it requires "a FRESH CAPTURE ... producing a new artifact". The pin is used
as a CROSS-CHECK instead (see require_fixture_points_here).

An incomplete/quit/crashed attempt writes a distinctly-named
`human_metrics.INCOMPLETE_<unix-ts>.json` instead of the canonical file, so a botched capture can
never silently masquerade as a banked baseline (see DAVID_BASELINES.md's re-run rule).

Clock/press-count discipline: `wall_clock_s`/`primitive_actions` are FROZEN the instant the oracle
(`_red_success`) first detects the real end-state, not whenever David happens to notice and close
the window. The window then auto-closes itself a few seconds later (COMPLETION_GRACE_SECONDS) as an
unmissable, reaction-time-independent "you're done" signal -- no informal wandering time can leak
into the banked numbers.

One cold attempt per task (the exam law -- see DAVID_BASELINES.md "Re-run rule"): this script
refuses to overwrite an existing canonical `human_metrics.json` unless `--allow-retake "<reason>"`
is passed; the artifact then records `attempt_number` (1 for a first attempt) and `retake_reason`
(empty for a first attempt).

Why `--mode` has NO default (same decision as tools/gate0_appserver_arm.py's --mode, PR #192): the
defect this argument closes is a SILENT one. Until 2026-07-28 this rig hardcoded
`MODE = "readiness_dev"`, so every artifact it produced was stamped readiness_dev -- and
`_verify_sources` (score_gate0.py, the `human_metric_identity:<arm>` check) rejects that under any
paid mode, a failure discovered only at SCORING, after the paid run is spent. A default of
`readiness_dev` would preserve exactly that trap for anyone who forgets the flag. The choices are
read from `eval.score_gate0.MODES` itself (score_gate0_modes(), a function-local import matching
tools/capture_gate0_baseline_miniwob.py's existing tools->eval idiom), so this rig can never offer a
mode the scorer cannot score.
"""
from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# Running this file directly (`uv run python tools/capture_gate0_baseline_red.py` -- the form
# DAVID_BASELINES.md documents and the one David is handed) puts tools/, not the repo root, on
# sys.path[0], so the root-level `eval` / `world_mcp` / `games` imports below raise
# ModuleNotFoundError. Same 3-line shim three sibling tools already carry
# (tools/reconstruct_gate0_red_baseline.py, tools/smoke_sweep.py, tools/gate3d_baselines.py); it is
# needed at MODULE scope here, not just inside run(), because build_arg_parser() reads the scorer's
# MODES to populate --mode's choices -- without it even `--help` tracebacks.
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
ARM = "red"
# Per-mode output directory. Same shape and same purpose as
# tools/capture_gate0_baseline_miniwob.py's MODE_CONFIG -- the two rigs are peers and any divergence
# between them is how the missing `--mode` survived here for a week after it landed there.
# readiness_dev's entry is the exact literal this module used to hold as the unconditional REAL_OUT,
# so that mode's output path is unchanged.
MODE_CONFIG = {
    "readiness_dev": {
        "real_out": os.path.normpath(str(ROOT / "runs" / "gate0_human_baseline" / "red")),
    },
    "paid_gate0": {
        "real_out": os.path.normpath(str(ROOT / "runs" / "gate0_paid_human_baseline" / "red")),
    },
    "paid_gate0_v2": {
        "real_out": os.path.normpath(str(ROOT / "runs" / "gate0_paid_v2_human_baseline" / "red")),
    },
}
# Modes whose artifact becomes a PRE-REGISTERED GATE DENOMINATOR: they require --i-am-human and are
# cross-checked against their own source-pins fixture before a single frame is emulated.
#
# The rationale differs from MiniWoB's and that difference is deliberate, not an oversight. There,
# HELD_OUT_MODES protects held-out SEEDS (the rig also suppresses the task utterance for them). Red
# has no held-out seed family at all -- the task text is public, printed in full, and identical in
# every mode -- so there is nothing here to suppress. What --i-am-human protects on this arm is the
# ARTIFACT: a paid-mode human_metrics.json is the denominator the `agent <= 2.0x human` bar is
# measured against, and it must never be produced by a casual or scripted invocation.
HELD_OUT_MODES = frozenset({"paid_gate0", "paid_gate0_v2"})
# Backward-compatible alias: the DEV real path as a module constant, same as the MiniWoB rig exposes.
REAL_OUT = MODE_CONFIG["readiness_dev"]["real_out"]
# Rows sampled continuously (not one-per-keypress): the frozen predicate needs 10 CONSECUTIVE watch
# rows showing a sustained battle exit, which idle/movement time must also be able to satisfy.
SAMPLE_EVERY_FRAMES = 15   # ~0.25s at ~60fps
# How long the window stays open, purely for cosmetic wind-down, after the oracle detects success
# and the metrics are already frozen -- then it closes itself so "David didn't notice the message"
# can never inflate the banked wall_clock_s/press_count.
COMPLETION_GRACE_SECONDS = 4.0


def _sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _strip_extended_prefix(p: str) -> str:
    r"""Drop a Win32 extended-length prefix: `\\?\C:\x` -> `C:\x`, `\\?\UNC\host\share\x` ->
    `\\host\share\x`. Both spellings open exactly the same object, and NEITHER `realpath` nor
    `abspath` touches them -- the prefix exists precisely to tell Win32 "do not normalise this" --
    so without this the guard below compares a prefixed candidate against an unprefixed referent and
    returns False for the same directory (review E1)."""
    for prefix, keep in (("\\\\?\\unc\\", "\\\\"), ("\\\\?\\", "")):
        if p[:len(prefix)].lower() == prefix:
            return keep + p[len(prefix):]
    return p


def _is_unc_or_device_path(p: str) -> bool:
    r"""Does `p` reach the filesystem through a share or a device namespace (`\\host\share\...`,
    `\\localhost\C$\...`, `\\127.0.0.1\C$\...`, `\\.\C:\...`, `\\?\Volume{GUID}\...`,
    `\\?\GLOBALROOT\GLOBAL??\C:\...`) rather than a drive letter, after any extended-length prefix
    is stripped?

    `_under_real_path` CANNOT answer for these and no amount of normalisation will make it: every
    host alias (`localhost`, `127.0.0.1`, `::1`, the machine name, a DNS alias, an IPv6-literal
    name) is a different spelling of the same admin share, and the set is unbounded. run() therefore
    REFUSES them outright rather than trying to compare them -- see the write-path guard's (a0)."""
    q = _strip_extended_prefix(p)
    if q[:1] in ("\\", "/") and q[1:2] in ("\\", "/"):
        return True
    # An extended-length prefix that did NOT reveal a drive letter is a DEVICE-NAMESPACE path
    # (`\\?\Volume{GUID}\...`, `\\?\GLOBALROOT\GLOBAL??\C:\...`, both of which any user can spell --
    # `mountvol C: /L` prints the GUID, no admin, no setup). Without this, the strip itself is what
    # hides them: it leaves a remainder that is neither `\\`-prefixed nor drive-rooted, so the clause
    # above sees a non-separator first character AND `_under_real_path` resolves the remainder as a
    # RELATIVE path against the cwd -- both miss, and review E6 drove `--test --mode paid_gate0_v2`
    # through each into a stand-in banked directory, renaming its append-only oracle.jsonl away.
    return q != p and not os.path.splitdrive(q)[0]


def _under_real_path(out: str, real_out: str = REAL_OUT) -> bool:
    r"""Is `out` at, or inside, `real_out`?

    THE INVARIANT, STATED BECAUSE IT IS OTHERWISE INVISIBLE AND A REFACTOR COULD SILENTLY BREAK IT:
    every normalisation here is applied SYMMETRICALLY, to the MODE_CONFIG referent as well as to the
    candidate. That symmetry -- not the normalisation strength -- is what makes this guard immune to
    a junction anywhere on a SHARED prefix: `runs/` already holds 26 NTFS junctions into another
    volume, and if a Gate-0 directory were junctioned off-volume tomorrow both sides would resolve
    through it and the comparison would still hold. A guard that resolves only the candidate against
    a literal referent (the shape #197 uses) escapes on every spelling in that situation. Do not
    "simplify" either side to a raw string.

    UNION, NEVER REPLACEMENT -- also stated because getting this wrong once already cost a round.
    The previous version REPLACED `normpath`+`abspath` with `normcase`+`realpath`. That closed five
    spellings (UPPER, lower, mixed-case leaf, a `mklink /J` junction, an 8.3 short name -- review D3,
    each of which had written an INCOMPLETE artifact into a stand-in banked directory and renamed its
    append-only oracle.jsonl away) and OPENED two, because the two normalisations see different
    things and neither dominates:

      * `realpath` sees through junctions and 8.3 short names, and asks the filesystem for the
        on-disk case -- but only for a path that ALREADY EXISTS, and it leaves a trailing dot or
        space on the leaf verbatim.
      * `abspath` goes through Win32 `GetFullPathNameW`, which STRIPS trailing dots and spaces
        (`...\red.` and `...\red ` both open `...\red`) -- but is blind to junctions and short names.

    So `--mode readiness_dev --out "<paid_v2 dir>."` walked past the replacement and wrote into the
    paid directory (review E2, a regression the replacement introduced). Comparing the UNION of both
    forms can only ever refuse MORE, never less, so it cannot reintroduce a false negative; the
    negative controls in the tests are what keep it from over-matching. `normcase` is load-bearing on
    top of both: it collapses case for a path that does not exist yet, which is the fresh-checkout
    case where `realpath` cannot.

    Does NOT answer for UNC/device paths -- see `_is_unc_or_device_path`, which run() refuses
    outright before this is ever consulted."""
    def forms(p: str) -> set[str]:
        p = _strip_extended_prefix(p)
        return {os.path.normcase(os.path.realpath(p)),
                os.path.normcase(os.path.normpath(os.path.abspath(p)))}

    return any(a == b or a.startswith(b + os.sep)
               for a in forms(out) for b in forms(real_out))


def score_gate0_modes() -> dict:
    """`eval.score_gate0.MODES` -- the frozen scorer's own mode map, read from the scorer and NEVER
    re-declared here, so this rig cannot offer a mode the scorer cannot score.

    Function-local import, matching tools/capture_gate0_baseline_miniwob.py's existing tools->eval
    idiom (`from eval.score_gate0 import MODES` inside run()), so importing this module does not drag
    in eval/."""
    from eval.score_gate0 import MODES
    return MODES


def pinned_red_human_path(mode: str) -> Path:
    """The absolute path `mode`'s source-pins fixture pins for `red_human`, resolved EXACTLY as
    eval/score_gate0.py::_verify_sources resolves it -- relative entries against the scorer's own
    ROOT, absolute ones left alone, and NO `.resolve()` on top, because the scorer applies none --
    and REJECTING (by raising) the fixtures _verify_sources would reject outright.

    The schema_version/mode guard mirrors _verify_sources' `source_pins_schema_or_mode` failure
    exactly. Without it this helper would happily read `red_human` out of a fixture the scorer
    refuses to trust at all, so a capture could pass the cross-check below and still score
    INSUFFICIENT_DATA -- the very "discovered only at scoring" class this guard exists to pre-empt.
    Raising rather than returning a message keeps it on require_fixture_points_here's existing
    fail-closed path.

    DUPLICATION, DECLARED: PR #192 has an identical `pinned_artifact_path(mode, key)` in
    tools/gate0_appserver_arm.py. Reusing it was the intent and is not possible here -- #192 is not
    merged, so the symbol does not exist on `origin/main` (this branch's base), and that file is
    off-limits to this change. Two resolutions of one pin is exactly the drift class this whole
    workstream exists to remove, so this copy is a KNOWN TEMPORARY: once both land, lift one shared
    helper and delete both. Flagged in the PR body, not left for a reader to discover.

    Kept deliberately in step with #192 rather than merely similar: its own review (G-series) removed
    the trailing `.resolve()` for exactly this reason -- the scorer does not symlink-resolve, so a
    second resolution here would BE the drift -- and pushed symlink resolution down to the one
    comparison that needs it. Same shape here (see require_fixture_points_here). #192 additionally
    raises SystemExit from its version; this one must NOT, because SystemExit derives from
    BaseException and would sail straight through require_fixture_points_here's `except Exception`
    fail-closed path and out of run(), turning a clean exit-2 refusal into an unhandled unwind. This
    file's guards refuse by returning a message; that difference is a deliberate match to THIS rig's
    style, not drift from #192's."""
    from eval.score_gate0 import ROOT as SCORER_ROOT, SOURCE_PIN_FILES
    pins = json.loads(SOURCE_PIN_FILES[mode].read_text(encoding="utf-8"))
    if pins.get("schema_version") != 1 or pins.get("mode") != mode:
        raise ValueError(f"source_pins_schema_or_mode: schema_version="
                         f"{pins.get('schema_version')!r} mode={pins.get('mode')!r}, "
                         f"expected 1 and {mode!r}")
    path = Path(pins["artifact_paths"]["red_human"])
    return path if path.is_absolute() else SCORER_ROOT / path


def require_fixture_points_here(mode: str, out_dir: str) -> str | None:
    """VALIDATE AND REFUSE: does `mode`'s own source-pins fixture actually point at the file this
    capture is about to write? Returns a refusal message, or None if it does.

    `out_dir` is the EFFECTIVE write target -- run() passes `args.out` (after the per-mode default
    has been filled in), never the mode's `real_out`. Binding it to `real_out` instead was a real
    defect: with the v2 fixture re-pointed, `--mode paid_gate0_v2 --out <the banked readiness_dev
    directory>` validated the directory it was NOT about to write and returned None, letting a
    paid-mode capture land on top of an append-only artifact whose digest three fixtures freeze. The
    guard now answers the question its first sentence asks.

    THIS GUARD IS NOT A SAFETY GUARD, and a previous round of this PR shipped believing it was.
    Its verdict is a function of FIXTURE CONTENTS, so what it permits moves when a fixture moves.
    Before `args.out` was passed in, the comparison happened to refuse `--mode paid_gate0_v2 --out
    <banked dir>` -- for the wrong reason, because it was comparing the wrong directory. Passing
    `args.out` made the comparison honest and thereby made it `pinned == target`, which today's
    fixtures satisfy at the banked directory: the fix removed the only thing blocking that write and
    replaced it with a blessing (review D1, reproduced). What actually protects the banked tree is
    the unconditional write-path guard in run(), whose referent is MODE_CONFIG, a module constant.
    Keep these two separate: this one answers "will the scorer read what I write?", that one answers
    "am I allowed to write here at all?", and only the second may ever be the last line of defence.

    Without this the failure is silent and expensive in the way this project keeps getting caught by:
    the capture succeeds, the artifact is perfect, and the scorer reads a DIFFERENT file -- the
    banked readiness_dev one, whose `mode` is wrong -- so the verdict is `human_metric_identity:red`
    -> INSUFFICIENT_DATA anyway, discovered only after the paid run.

    Deriving the output directory from the pin instead would NOT fix that; it would reinstate a worse
    defect (#192's F2 lesson). All three fixtures pin `red_human` at the SAME banked file today, so a
    derived output would send a v2 capture straight into `runs/gate0_human_baseline/red/`, overwriting
    an append-only artifact whose digest all three fixtures freeze -- breaking readiness_dev and
    paid_gate0 scoring at the same time. Validate and refuse; never derive.

    HELD-OUT MODES ONLY, and that scoping is deliberate rather than convenient: readiness_dev's
    baseline is already captured, already banked, and its pin is already frozen to exactly this file,
    so re-checking it at capture time protects nothing and would add a new way for a legitimate
    --allow-retake to fail. It also keeps the readiness_dev path literally untouched by this change,
    which is what the differential in the PR body proves."""
    if mode not in HELD_OUT_MODES:
        return None
    target = Path(os.path.join(out_dir, "human_metrics.json")).resolve()
    try:
        pinned = pinned_red_human_path(mode)
    except Exception as exc:
        return (f"refusing: cannot read {mode!r}'s source-pins fixture to confirm where the scorer "
                f"will look for the Red human baseline ({exc}).")
    # Symlink resolution happens HERE, at the one comparison that needs it, and never inside
    # pinned_red_human_path -- same split as #192's pinned_artifact_path/_validate_args. The pin is
    # reported to the operator unresolved, i.e. as the scorer will actually open it; only the
    # equality test is taken on resolved forms, so a symlinked or 8.3-shortened repo path cannot
    # manufacture a false refusal.
    if pinned.resolve() != target:
        return (
            f"refusing: eval/score_gate0.py will read the {mode!r} Red human baseline from\n"
            f"    {pinned}\n"
            f"but this capture writes to\n"
            f"    {target}\n"
            f"so the artifact you are about to spend your time producing would never be scored.\n"
            f"Fix the FIXTURE, not this rig, and not the banked artifact: set artifact_paths."
            f"red_human in eval/fixtures/gate0_{'paid_v2' if mode == 'paid_gate0_v2' else 'paid'}"
            f"_source_pins.json to the second path above (leaving artifact_sha256.red_human as its "
            f"PENDING_ placeholder until this capture exists), in its own reviewed commit -- prereg "
            f"P1c. Editing runs/gate0_human_baseline/red/human_metrics.json instead is explicitly "
            f"forbidden (reports/2026-07-25-gate0-v2-prereg.md:264-269): it is append-only raw data "
            f"and three fixtures freeze its digest.")
    return None


def _atomic_write_json(path: str, payload: dict) -> None:
    """temp file + os.replace so a crash mid-write can never leave a truncated/corrupt artifact at
    `path` -- matches the append-only/fail-closed treatment the rest of the rig already gives
    oracle.jsonl and INCOMPLETE files. On a crash the temp file itself is also cleaned up, so
    neither `path` nor a stray partial file survives."""
    tmp = f"{path}.tmp{os.getpid()}"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, sort_keys=True)
            f.write("\n")
        os.replace(tmp, path)
    except BaseException:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise


def _build_metrics(args, *, rom_sha256: str, state_sha256: str, oracle_path: str,
                    wall_clock_s: float, press_count: int, success: bool, failures: list[str],
                    started_at, completed_at, attempt_number: int, retake_reason: str,
                    input_event_times: list[float]) -> dict:
    """Pure artifact-shape builder, factored out so the schema (mode/attempt_number/retake_reason/
    input_event_times included) is unit-testable without a real PyBoy/SDL2 window -- see
    tests/test_capture_gate0_baseline_red.py."""
    return {
        "schema_version": 1,
        "arm": ARM,
        "role": "human",
        # Was the module-level constant MODE = "readiness_dev". eval/score_gate0.py::_verify_sources
        # requires this to EQUAL the mode being scored, so a hardwired stamp makes every paid-mode
        # capture void -- and only at scoring. Prereg P1c.
        "mode": args.mode,
        "wall_clock_s": round(wall_clock_s, 3),
        "primitive_actions": press_count,
        "success": success,
        "failures": failures,
        "player": args.player if not args.test else f"TEST:{args.player}",
        "started_at": started_at.isoformat() if started_at else None,
        "completed_at": completed_at.isoformat(),
        "rom_path": os.path.normpath(args.rom),
        "rom_sha256": rom_sha256,
        "savestate_path": os.path.normpath(args.state),
        "savestate_sha256": state_sha256,
        "oracle_path": os.path.normpath(oracle_path),
        "test_mode": bool(args.test),
        # one-cold-attempt bookkeeping (DAVID_BASELINES.md "Re-run rule"): attempt_number is 1 for a
        # normal first capture; retake_reason is only ever non-empty when --allow-retake overrode an
        # existing canonical human_metrics.json.
        "attempt_number": attempt_number,
        "retake_reason": retake_reason,
        # Per-input-event epoch timestamps (time.time()), independent of the aggregate
        # primitive_actions count -- lets a future auditor check press cadence directly instead of
        # trusting the aggregate alone (fairness review Minor 2). Includes any presses during the
        # post-detection grace window; the first `primitive_actions` entries are the ones the banked
        # wall_clock_s/primitive_actions numbers were frozen against.
        "input_event_times": input_event_times,
    }


def run(args, max_frames: int | None = None) -> int:
    """`max_frames` is a Python-only testability seam (never exposed on the CLI, see main()): it caps
    the interactive loop so an in-process test can exercise the full boot/log/write path without a
    real window-close or Ctrl-C. It never presses a button; a capped run with zero human input simply
    writes an INCOMPLETE artifact, exactly like a human closing the window immediately would."""
    # --- mode resolution + the two mode guards, before any file is touched -----------------------
    # Same order and same shape as tools/capture_gate0_baseline_miniwob.py::run().
    mode = getattr(args, "mode", None)
    if mode not in MODE_CONFIG:
        print(f"refusing: unknown --mode {mode!r} (must be one of {sorted(MODE_CONFIG)}).",
              file=sys.stderr)
        return 2
    real_out = MODE_CONFIG[mode]["real_out"]
    if args.out is None:
        args.out = real_out

    # Held-out law, this arm's version (see HELD_OUT_MODES): an explicit, un-default-able
    # acknowledgement that a real human is about to play. Fires for EVERY paid-mode invocation,
    # canonical path or not -- the sensitive thing is producing a paid-mode denominator at all, not
    # just where it lands.
    if mode in HELD_OUT_MODES and not getattr(args, "i_am_human", False):
        print(f"refusing: --mode {mode} requires --i-am-human -- this captures the human "
              "denominator the paid gate's `agent <= 2.0x human` bar is measured against; a "
              "scripted or absent-minded invocation must never be able to produce it. Pass "
              "--i-am-human only when a real human is about to play this task at the keyboard.",
              file=sys.stderr)
        return 2

    # Cross-checked against args.out -- the directory this invocation will ACTUALLY write -- not
    # against MODE_CONFIG's real_out, so an explicit --out cannot walk past it (see the guard's
    # docstring).
    refusal = require_fixture_points_here(mode, args.out)
    if refusal is not None:
        print(refusal, file=sys.stderr)
        return 2

    if not os.path.exists(args.rom):
        print(f"ROM not found: {args.rom}", file=sys.stderr)
        return 2
    if not os.path.exists(args.state):
        print(f"savestate not found: {args.state} -- see DAVID_BASELINES.md "
              "(and runs/gate0_readiness_2026-07-14/ receipts) for how to obtain it.", file=sys.stderr)
        return 2

    # --- THE WRITE-PATH GUARD ---------------------------------------------------------------------
    # Everything run() writes lands inside args.out: os.makedirs(args.out), the oracle.jsonl archival
    # rename, the oracle handle, and both _atomic_write_json calls all derive their path from it and
    # nothing else. So args.out, once the per-mode default above has been filled in, is this rig's
    # single write choke point -- the one place the mode-derived default and an explicit --out arrive
    # as the same value -- and gating it here gates every write. Shape ported from PR #196's
    # write_artifact() guard, with the four properties that make it structural rather than incidental:
    # it is checked at the choke point (an explicit --out cannot route around it), it compares
    # RESOLVED paths (see _under_real_path), it is DIRECTORY-wide so it covers the append-only
    # oracle.jsonl and not just human_metrics.json, and it runs BEFORE the exists() test and before
    # any mkdir, so a refusal creates nothing on disk. No flag overrides it.
    #
    # What differs from #196, deliberately: that tool must never write into the banked directory at
    # all, so its guard names one fixed BANKED_DIR. This rig legitimately writes there under --mode
    # readiness_dev -- that IS the banked artifact's own mode -- so the invariant is relative: a mode
    # may never write under a DIFFERENT mode's real baseline path. The referent is MODE_CONFIG, a
    # module constant, never fixture contents. That is the whole point of review D1: binding the
    # question to a fixture-derived value made the answer correct only by accident, and today's
    # fixtures (all three still pinning red_human at the banked readiness_dev artifact) turned that
    # accident into a blessing -- `--mode paid_gate0_v2 --i-am-human --out <the banked directory>
    # --allow-retake "..."` renamed the banked oracle.jsonl away and wrote a paid-stamped artifact in.
    #
    # (a0) A UNC or device-namespace --out is REFUSED OUTRIGHT, before the two clauses below, because
    # they cannot answer for it: `\\localhost\C$\...`, `\\127.0.0.1\C$\...`, `\\?\UNC\...`,
    # `\\?\Volume{GUID}\...` and `\\?\GLOBALROOT\GLOBAL??\C:\...` all open the same directory as the
    # drive-letter spelling, but no normalisation maps them back to it -- the set of host aliases is
    # unbounded. Review E1 drove `--test --mode readiness_dev --out "\\?\<banked>"` into a stand-in
    # banked directory, and review E6 did the same through the two device-namespace spellings: the
    # append-only oracle.jsonl was renamed away and an INCOMPLETE artifact written in, by the one flag
    # whose stated invariant is that it may never write under ANY mode's real baseline path.
    # (`\\?\<drive-letter>` itself IS handled, by _strip_extended_prefix; only the share/device forms
    # have to be refused.) No legitimate capture needs one -- but if this repo itself were checked out
    # on a share, every real_out would be UNC too and refusing would break the only thing this rig
    # exists to do, so the refusal is conditioned on the referents being drive paths.
    #
    # THE RESIDUAL THAT CONDITION LEAVES, stated because it is invisible from the code: on a
    # share-hosted checkout (a0) switches itself off, and a UNC/device --out then falls through to
    # _under_real_path, which over UNC is an ordinary string comparison and does NOT recognise
    # `\\server.corp.example.com\...`, `\\127.0.0.1\...` and `\\localhost\...` as one directory. Not a
    # regression -- every earlier version of this rig behaved that way unconditionally -- and
    # unreachable from a drive-letter checkout, but real. DAVID_BASELINES.md says so out loud.
    if _is_unc_or_device_path(args.out) and not any(_is_unc_or_device_path(cfg["real_out"])
                                                    for cfg in MODE_CONFIG.values()):
        print(f"refusing: --out {args.out!r} names a UNC share or device path. Every baseline "
              "directory on this checkout is a drive path, and a share spelling of one of them "
              "(\\\\localhost\\C$\\..., \\\\127.0.0.1\\C$\\..., \\\\?\\UNC\\...) opens the same "
              "directory while defeating the path comparison that keeps a capture out of another "
              "mode's append-only baseline tree. Pass a drive-letter --out. No flag overrides this.",
              file=sys.stderr)
        return 2
    blocked = sorted(m for m, cfg in MODE_CONFIG.items()
                     if _under_real_path(args.out, cfg["real_out"]))
    foreign = [m for m in blocked if m != mode]
    if foreign:
        which = "; ".join(f"{m} -> {MODE_CONFIG[m]['real_out']}" for m in foreign)
        print(f"refusing: --out {args.out!r} is under another mode's real baseline path ({which}), "
              f"but this capture runs as --mode {mode}. A mode may never write under a different "
              "mode's baseline directory: that tree is append-only raw data whose digest the "
              "source-pin fixtures freeze, and an artifact stamped with the wrong mode fails "
              "eval/score_gate0.py's human_metric_identity check anyway. No flag overrides this. "
              "Fix the FIXTURE, not the destination.", file=sys.stderr)
        return 2
    # --test may never write under ANY mode's real baseline path, whatever --mode/--out/
    # --allow-retake say -- including, unlike the guard above, the selected mode's OWN one. The word
    # "unconditional" is used advisedly and only as far as it is proven: over mode x target x
    # --i-am-human x --allow-retake x PATH SPELLING, the last axis added after review D3 found the
    # previous flags-only matrix certifying a helper that five spellings of one path walked past.
    # Scoping this to the selected mode's real_out (inherited verbatim
    # from tools/capture_gate0_baseline_miniwob.py) was the one place copying the sibling WEAKENED
    # this rig against origin/main, where _under_real_path had a single referent and `--test`
    # therefore could never touch runs/gate0_human_baseline/red. Demonstrated: `--test --mode
    # paid_gate0_v2 --out runs/gate0_human_baseline/red` wrote an INCOMPLETE artifact into the banked
    # directory and renamed the banked append-only oracle.jsonl away.
    if args.test and blocked:
        which = "; ".join(f"{m} -> {MODE_CONFIG[m]['real_out']}" for m in blocked)
        print(f"--test refuses to write under ANY mode's real baseline path; --out {args.out!r} is "
              f"under {which}. Pass a scratch --out.", file=sys.stderr)
        return 2
    if not args.test and not _under_real_path(args.out, real_out):
        print(f"warning: --out {args.out!r} is outside the canonical real baseline path "
              f"{real_out!r} (fine for a manual dry run; DAVID_BASELINES.md uses the default).",
              file=sys.stderr)

    # One cold attempt per task (the exam law): refuse to clobber an existing canonical artifact
    # unless David explicitly says this is a legitimate re-take and why.
    allow_retake = (args.allow_retake or "").strip()
    canonical_path = os.path.join(args.out, "human_metrics.json")
    attempt_number = 1
    retake_reason = ""
    if os.path.exists(canonical_path):
        if not allow_retake:
            print(f"refusing: {canonical_path} already exists -- one cold attempt per task (see "
                  "DAVID_BASELINES.md's re-run rule). Pass --allow-retake \"<reason>\" if this is a "
                  "legitimate re-take of a genuinely botched capture, not a rerun to chase a better "
                  "score.", file=sys.stderr)
            return 2
        try:
            prior = json.loads(Path(canonical_path).read_text(encoding="utf-8"))
            attempt_number = int(prior.get("attempt_number") or 1) + 1
        except Exception:
            attempt_number = 2
        retake_reason = allow_retake

    os.makedirs(args.out, exist_ok=True)

    # This rig appends to <out>/oracle.jsonl and the success check re-reads that WHOLE file, so any
    # stale trace left over from an earlier session (a legitimate --allow-retake, or a crash/abort
    # before the canonical write) would have its rows prepended to the new attempt's, corrupting the
    # party/battle/exit index logic in eval.score_gate0._red_success. Archive whenever a prior trace
    # exists at session start, regardless of whether a canonical human_metrics.json exists -- same
    # pattern as the MiniWoB rig (PR #119). Renamed, never deleted -- append-only law -- and never
    # clobbered on same-second name collisions.
    prior_oracle_path = os.path.join(args.out, "oracle.jsonl")
    if os.path.exists(prior_oracle_path):
        base = os.path.join(args.out, f"oracle.attempt{max(attempt_number - 1, 1)}_{int(time.time())}")
        archive_path, n = f"{base}.jsonl", 0
        while os.path.exists(archive_path):
            n += 1
            archive_path = f"{base}_{n}.jsonl"
        os.replace(prior_oracle_path, archive_path)
        print(f"[stale oracle trace from a previous session archived -> {archive_path}]")

    rom_sha256 = _sha256_file(args.rom)
    state_sha256 = _sha256_file(args.state)
    oracle_path = os.path.join(args.out, "oracle.jsonl")

    import world_mcp
    from eval.score_gate0 import _red_success
    from games.pokemon_red.emulator import ensure_sdl_dll_path

    watch_spec = world_mcp.GAMES["pokemon_red"]["watch"]   # single source of truth for RAM addresses

    ensure_sdl_dll_path()
    from pyboy import PyBoy
    import sdl2

    # PyBoy/SDL2 window construction + savestate load, guarded: a corrupt/incompatible savestate or
    # any other setup failure here now goes through the same clean-abort path as the rest of the
    # rig (no orphaned SDL2 window, an INCOMPLETE artifact instead of a bare traceback + nothing).
    pb = None
    try:
        pb = PyBoy(args.rom, window="SDL2")
        pb.set_emulation_speed(1)
        with open(args.state, "rb") as f:
            pb.load_state(f)
        pb.tick(4, render=True)
    except Exception as exc:
        if pb is not None:
            pb.stop(save=False)
        metrics = _build_metrics(
            args, rom_sha256=rom_sha256, state_sha256=state_sha256, oracle_path=oracle_path,
            wall_clock_s=0.0, press_count=0, success=False,
            failures=[f"setup_failed:{type(exc).__name__}"], started_at=None,
            completed_at=datetime.now(timezone.utc), attempt_number=attempt_number,
            retake_reason=retake_reason, input_event_times=[])
        metrics_path = os.path.join(args.out, f"human_metrics.INCOMPLETE_{int(time.time())}.json")
        _atomic_write_json(metrics_path, metrics)
        print(f"ERROR during PyBoy/savestate setup ({type(exc).__name__}: {exc}) -- wrote "
              f"{metrics_path}", file=sys.stderr)
        return 2

    rd = lambda a: pb.memory[a]

    def read_watch() -> dict:
        return {name: int(rd(addr)) for name, addr in watch_spec.items()}

    fresh_party = read_watch().get("party")
    if fresh_party != 0:
        print(f"warning: loaded state already has party={fresh_party} (expected a fresh 0) -- "
              "this is not a fresh bedroom baseline start; the predicate will reject it.",
              file=sys.stderr)

    oracle = open(oracle_path, "a", encoding="utf-8")
    rows: list[dict] = []
    step_n = 0

    def log_row() -> None:
        nonlocal step_n
        row = {"step": step_n, "t": time.time(), "frame": pb.frame_count, "watch": read_watch()}
        rows.append(row)
        oracle.write(json.dumps(row) + "\n")
        oracle.flush()
        step_n += 1

    # PyBoy's default SDL2 keymap (human_play.py), expressed as SCANCODES (physical keys), not
    # KEYCODES: SDL_GetKeyboardState() returns a SCANCODE-indexed array -- indexing it with a KEYCODE
    # (e.g. pyboy.plugins.window_sdl2.KEY_DOWN's SDLK_UP == 1073741906) reads out of bounds and
    # segfaults. play_record.py's own hotkeys() polls the same way, via SDL_SCANCODE_* constants.
    gameplay_scancodes = [
        sdl2.SDL_SCANCODE_UP, sdl2.SDL_SCANCODE_DOWN, sdl2.SDL_SCANCODE_LEFT, sdl2.SDL_SCANCODE_RIGHT,
        sdl2.SDL_SCANCODE_A, sdl2.SDL_SCANCODE_S, sdl2.SDL_SCANCODE_RETURN, sdl2.SDL_SCANCODE_BACKSPACE,
    ]
    held = {sc: False for sc in gameplay_scancodes}
    nkeys = ctypes.c_int(0)

    print(f"Loaded {args.rom} ({rom_sha256[:12]}...) + {args.state} ({state_sha256[:12]}...).")
    print(f"Fresh state party count: {fresh_party}.")
    print("Controls (PyBoy defaults): arrows=move  A=A  S=B  Enter=Start  Backspace=Select.")
    print('Task: "From the fresh bedroom start, obtain your first Pokemon from Professor Oak and '
          'win the first rival battle."')
    print(f"The timer starts on your FIRST button press. The window auto-closes "
          f"{COMPLETION_GRACE_SECONDS:.0f}s after the task is detected complete -- or close it "
          "yourself (or Ctrl-C) any time to finish early or abort.")

    log_row()   # row 0: the fresh state, before any human input

    first_input_perf: float | None = None
    started_at = None
    press_count = 0
    input_event_times: list[float] = []
    success = False
    failures: list[str] = ["red_not_fresh_party_zero"] if fresh_party != 0 else ["no_input_yet"]
    frames_since_sample = 0
    # Frozen at the instant of oracle-detected completion (fairness review Major 1) -- everything
    # after that is cosmetic wind-down and must never change the banked numbers.
    frozen_wall_clock_s: float | None = None
    frozen_press_count: int | None = None
    grace_deadline: float | None = None

    try:
        frame_i = 0
        while max_frames is None or frame_i < max_frames:
            frame_i += 1
            if not pb.tick(1, True):
                break
            ks = sdl2.SDL_GetKeyboardState(ctypes.byref(nkeys))
            for scancode in gameplay_scancodes:
                now = bool(ks[scancode])
                if now and not held[scancode]:
                    press_count += 1
                    input_event_times.append(time.time())
                    if first_input_perf is None:
                        first_input_perf = time.perf_counter()
                        started_at = datetime.now(timezone.utc)
                        print("[timer started -- first input detected]")
                held[scancode] = now
            frames_since_sample += 1
            if frames_since_sample >= SAMPLE_EVERY_FRAMES:
                frames_since_sample = 0
                log_row()
                if not success and first_input_perf is not None:
                    ok, failures = _red_success(rows)
                    if ok:
                        success = True
                        frozen_wall_clock_s = time.perf_counter() - first_input_perf
                        frozen_press_count = press_count
                        grace_deadline = time.perf_counter() + COMPLETION_GRACE_SECONDS
                        print("=" * 60)
                        print(f"[TASK COMPLETE -- presses={frozen_press_count} "
                              f"wall_clock={frozen_wall_clock_s:.1f}s -- metrics frozen]")
                        print(f"[window auto-closes in {COMPLETION_GRACE_SECONDS:.0f}s -- "
                              "or close it now]")
                        print("=" * 60)
            if grace_deadline is not None and time.perf_counter() >= grace_deadline:
                print("[auto-close: grace period elapsed]")
                break
    except KeyboardInterrupt:
        pass
    finally:
        log_row()
        oracle.close()
        pb.stop(save=False)

    if frozen_wall_clock_s is not None:
        wall_clock_s = frozen_wall_clock_s
        final_press_count = frozen_press_count
    else:
        wall_clock_s = (time.perf_counter() - first_input_perf) if first_input_perf is not None else 0.0
        final_press_count = press_count
    completed_at = datetime.now(timezone.utc)

    metrics = _build_metrics(
        args, rom_sha256=rom_sha256, state_sha256=state_sha256, oracle_path=oracle_path,
        wall_clock_s=wall_clock_s, press_count=final_press_count, success=success,
        failures=failures, started_at=started_at, completed_at=completed_at,
        attempt_number=attempt_number, retake_reason=retake_reason,
        input_event_times=input_event_times)
    name = "human_metrics.json" if success else f"human_metrics.INCOMPLETE_{int(time.time())}.json"
    metrics_path = os.path.join(args.out, name)
    _atomic_write_json(metrics_path, metrics)

    print(("PASS" if success else "INCOMPLETE") + f" -- wrote {metrics_path}")
    print(json.dumps(metrics, sort_keys=True))
    return 0 if success else 1


def build_arg_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    # REQUIRED, NO DEFAULT -- see the module docstring's "Why --mode has no default". Choices come
    # from the frozen scorer's own MODES map, never a list re-declared here.
    ap.add_argument("--mode", required=True, choices=tuple(score_gate0_modes()),
                     help="which pre-registered Gate 0 mode this capture belongs to; stamps "
                          "human_metrics.json's `mode` field (which eval/score_gate0.py requires to "
                          "equal the mode being scored) and selects the output directory. Both paid "
                          "modes additionally require --i-am-human. No default: an unstated mode is "
                          "an artifact the scorer rejects.")
    ap.add_argument("--rom", default=str(ROOT / "roms" / "PokemonRed.gb"))
    ap.add_argument("--state", default=str(ROOT / "runs" / "red_start.state"))
    ap.add_argument("--out", default=None,
                     help="defaults to the canonical real path for --mode (see module docstring).")
    ap.add_argument("--player", default="David")
    ap.add_argument("--i-am-human", action="store_true", dest="i_am_human",
                     help="required for every held-out mode (HELD_OUT_MODES: paid_gate0, "
                          "paid_gate0_v2) -- explicit, non-default acknowledgement that a real human "
                          "is about to play this task. A scripted invocation cannot satisfy this by "
                          "accident.")
    ap.add_argument("--test", action="store_true",
                     help="throwaway smoke-test mode: refuses to write under the real baseline path")
    ap.add_argument("--allow-retake", metavar="REASON", default=None,
                     help="required to overwrite an existing canonical human_metrics.json -- state "
                          "why this is a legitimate re-take (a botched capture), not a rerun to "
                          "chase a better score.")
    return ap


def main() -> int:
    return run(build_arg_parser().parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
