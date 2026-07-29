"""Offline reconstruction of David's Gate 0 Red human baseline from his archived COLD attempt-1.

Background: `tools/capture_gate0_baseline_red.py` detects task completion LIVE by running
`eval.score_gate0._red_success` after every sampled row and freezing wall_clock_s/primitive_actions
the instant it first returns True. David's attempt 1 (2026-07-21) was a genuinely cold run that, in
fact, completed the task -- but the pre-PR-#121 `_red_success` had a scorer bug (the glitch-row
filter was too narrow) that made it miss the real completion live, so the session was archived as
`human_metrics.INCOMPLETE_*.json` instead of the canonical baseline. David then played a SECOND,
no-longer-cold attempt. PR #121 fixed the detector on `main`.

Option A (David's call, 2026-07-21): reconstruct attempt 1's true completion numbers OFFLINE, using
the now-fixed `_red_success`, rather than bank attempt 2 (which is not a cold attempt) or discard the
cold data. This script does exactly that and nothing else: it never plays, never invents rows.

Logic (mirrors the live rig's own detection loop -- see capture_gate0_baseline_red.run()'s
`if not success and first_input_perf is not None: ok, failures = _red_success(rows)`):
  1. Replay the trace row by row; after each row, call `_red_success` on every row seen so far
     (imported from eval.score_gate0, never copied). The first prefix that succeeds pins the
     completion row index; that row's `t` is t_done.
  2. The live rig starts its clock on the first detected keypress. We mirror that: t_first_input is
     input_event_times[0] from the INCOMPLETE artifact (cross-checked against that artifact's own
     `started_at`, which the rig also sets at first-keypress time).
  3. wall_clock_s = t_done - t_first_input; primitive_actions = count of input_event_times <= t_done
     (matching the rig's "frozen the instant of detection" semantics); input_event_times themselves
     are trimmed to <= t_done so the artifact never carries post-completion presses as if they were
     part of the timed attempt.

Three modes, selected with a REQUIRED `--mode` (see "Why --mode has no default" below):
  * `readiness_dev` -- the readiness-phase mode. This is the mode the banked
    `runs/gate0_human_baseline/red/human_metrics.json` was reconstructed under, and the payload this
    tool produces under it is byte-identical to the pre-`--mode` tool's.
  * `paid_gate0` -- Gate 0 v1's paid mode.
  * `paid_gate0_v2` -- Gate 0 v2's paid mode.
Both paid modes require `--i-am-human` (see HELD_OUT_MODES), exactly as
tools/capture_gate0_baseline_red.py and tools/capture_gate0_baseline_miniwob.py do.

`--mode` selects the output directory as well as the stamp -- one directory PER MODE, mirroring
tools/capture_gate0_baseline_red.py's MODE_CONFIG:
    readiness_dev -> runs/gate0_human_baseline/red/          (the banked artifact -- see BANKED_DIR)
    paid_gate0    -> runs/gate0_paid_human_baseline/red/
    paid_gate0_v2 -> runs/gate0_paid_v2_human_baseline/red/

Usage:
    uv run python tools/reconstruct_gate0_red_baseline.py --mode paid_gate0_v2 --i-am-human \
        --trace <oracle.jsonl> --incomplete <human_metrics.INCOMPLETE_*.json> [--out <path>]

Refuses to overwrite an existing canonical human_metrics.json at the resolved --out -- the same
one-cold-attempt-per-task law the live rig enforces -- and refuses, in every mode and with every flag
combination, to write anywhere that resolves inside THIS repo root's BANKED_DIR (see write_artifact
for the guard, and _resolves_inside_banked for what it can and cannot decide; the guard is scoped to
this module's own repo root, so it does not bind a path aimed at a DIFFERENT checkout's runs/).

Why `--mode` has NO default (same decision as tools/capture_gate0_baseline_red.py's --mode, PR
#195): the defect it closes is a SILENT one. Until 2026-07-28 this tool hardcoded
`MODE = "readiness_dev"`, so every artifact it produced was stamped readiness_dev -- and
`_verify_sources` (score_gate0.py, the `human_metric_identity:<arm>` check) rejects that under any
paid mode, a failure discovered only at SCORING, after the paid run is spent. A default of
`readiness_dev` would preserve exactly that trap for anyone who forgets the flag. The choices are
read from `eval.score_gate0.MODES` itself (score_gate0_modes(), a function-local import matching
tools/capture_gate0_baseline_red.py's and tools/capture_gate0_baseline_miniwob.py's tools->eval
idiom), so this tool can never offer a mode the scorer cannot score.

RECOVERY PATH, NOT A CAPTURE PATH. A paid-mode reconstruction still needs a REAL capture session's
archived `oracle.jsonl` + `human_metrics.INCOMPLETE_*.json` as input -- this tool never plays and
never invents rows, so it cannot fabricate a baseline. Its paid modes exist for exactly one case:
a genuine held-out capture whose LIVE detector missed a real completion (the 2026-07-21 attempt-1
case this tool was built for, one scorer bug away from recurring). Note for whoever needs it:
reports/2026-07-25-gate0-v2-prereg.md's P1c names its satisfaction method as "a FRESH CAPTURE under
`--mode paid_gate0_v2`, producing a new artifact". A reconstruction of such a capture is not
literally that; if a reconstructed artifact is ever used to satisfy P1c, THAT use needs its own
entry in reports/2026-07-28-gate0-v2-deviations.md. Having the tool is not the deviation; using its
output as a precondition's satisfaction would be.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

# Running this file directly (`uv run python tools/reconstruct_gate0_red_baseline.py`, per this
# repo's convention -- see DAVID_BASELINES.md) makes Python add tools/, not the repo root, to
# sys.path[0], so the root-level `eval` package below would otherwise fail to import. Same shim as
# tools/gate3d_baselines.py.
_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from eval.score_gate0 import _red_success

ROOT = _REPO
ARM = "red"
ROLE = "human"
SCHEMA_VERSION = 1
# Per-mode output directory. Same three destinations, for the same reason, as
# tools/capture_gate0_baseline_red.py's MODE_CONFIG -- the reconstruct tool is that rig's recovery
# path and the two must land in the same place per mode or the scorer reads the wrong file. Values
# are `Path`, not the sibling's normpath'd `str`, because this module is Path-typed throughout
# (`--out` is `type=Path`, write_artifact takes a Path); that is the only shape difference.
# readiness_dev's entry is the exact directory this module's deleted `DEFAULT_OUT` pointed into.
MODE_CONFIG = {
    "readiness_dev": {"real_out": ROOT / "runs" / "gate0_human_baseline" / "red"},
    "paid_gate0": {"real_out": ROOT / "runs" / "gate0_paid_human_baseline" / "red"},
    "paid_gate0_v2": {"real_out": ROOT / "runs" / "gate0_paid_v2_human_baseline" / "red"},
}
# Modes whose artifact is a PRE-REGISTERED GATE DENOMINATOR. Same frozenset, same flag, same
# rationale as tools/capture_gate0_baseline_red.py's: what --i-am-human protects on this arm is the
# ARTIFACT, not a held-out seed family (Red has none). #195 already reframed the flag from "a human
# is playing" to "a human, not a script, is deliberately producing this denominator" -- that second
# reading is the one that transfers here, where nobody plays at all.
HELD_OUT_MODES = frozenset({"paid_gate0", "paid_gate0_v2"})
# The banked Red human baseline's directory. NOTHING this tool runs may write inside it, in any mode,
# with any flag combination -- see write_artifact(). It holds the append-only artifact that produced
# every Red number in the project, whose digest three source-pin fixtures freeze, plus the oracle
# trace those numbers were derived from.
BANKED_DIR = MODE_CONFIG["readiness_dev"]["real_out"]
# Windows extended-length path prefixes. `Path.resolve()` preserves them, so they must be stripped
# before BANKED_DIR containment is decided -- but AFTER `.resolve()`, never before. That ordering is
# load-bearing and got two live write vectors wrong once; see _strip_extended_prefix().
_EXT_PREFIX = "\\\\?\\"
_EXT_UNC_PREFIX = "\\\\?\\UNC\\"
# Clock-start cross-check tolerance: the live rig sets `started_at` and appends
# input_event_times[0] in the same loop iteration (see capture_gate0_baseline_red.run()); any
# larger gap in an archived INCOMPLETE artifact means our clock-start assumption doesn't hold there.
CLOCK_START_TOLERANCE_S = 0.01
RECONSTRUCTION_METHOD = (
    "Replayed the archived attempt-1 oracle trace through eval.score_gate0._red_success "
    "(imported, PR #121 fix included) row by row to find the first prefix that succeeds; "
    "wall_clock_s/primitive_actions/input_event_times are derived against that row's timestamp "
    "exactly as tools/capture_gate0_baseline_red.py freezes them against live detection."
)


def score_gate0_modes() -> dict:
    """`eval.score_gate0.MODES` -- the frozen scorer's own mode map, read from the scorer and NEVER
    re-declared here, so this tool cannot offer a mode the scorer cannot score.

    Function-local import, the same symbol and the same tools->eval idiom as
    tools/capture_gate0_baseline_red.py::score_gate0_modes and
    tools/capture_gate0_baseline_miniwob.py::run's `from eval.score_gate0 import MODES`. (This module
    already imports `_red_success` at module scope, so the sibling's "don't drag in eval/ on import"
    motive does not apply here; matching the sibling's shape so the three rigs stay one family, and a
    future shared helper is a rename not a redesign, is the reason.)"""
    from eval.score_gate0 import MODES
    return MODES


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _load_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def find_completion_row(rows: list[dict]) -> int | None:
    """First row index `i` such that `_red_success(rows[:i+1])` is True -- the same growing-prefix
    check the live rig performs after every sampled row once input has started."""
    for i in range(len(rows)):
        ok, _ = _red_success(rows[: i + 1])
        if ok:
            return i
    return None


def reconstruct(trace_path: Path, incomplete_path: Path, mode: str) -> dict:
    trace_bytes = trace_path.read_bytes()
    incomplete_bytes = incomplete_path.read_bytes()
    rows = _load_jsonl(trace_path)
    incomplete = json.loads(incomplete_bytes.decode("utf-8"))

    if not rows:
        raise SystemExit(f"{trace_path} has no rows -- refusing to reconstruct")

    completion_row_index = find_completion_row(rows)
    if completion_row_index is None:
        _, failures = _red_success(rows)
        raise SystemExit(
            f"{trace_path} never reaches a _red_success completion row "
            f"(final failures={failures}) -- refusing to reconstruct a false completion")
    t_done = rows[completion_row_index]["t"]

    input_event_times = incomplete.get("input_event_times") or []
    if not input_event_times:
        raise SystemExit(f"{incomplete_path} has no input_event_times -- cannot determine clock start")
    t_first_input = input_event_times[0]
    if t_first_input > t_done:
        raise SystemExit("first input event is after the detected completion row -- refusing (clock inversion)")

    started_at_str = incomplete.get("started_at")
    if started_at_str:
        recorded_start = datetime.fromisoformat(started_at_str).timestamp()
        if abs(recorded_start - t_first_input) > CLOCK_START_TOLERANCE_S:
            raise SystemExit(
                f"clock-start cross-check failed: {incomplete_path}'s started_at={recorded_start} "
                f"vs input_event_times[0]={t_first_input} (>{CLOCK_START_TOLERANCE_S}s apart)")

    trimmed_events = [t for t in input_event_times if t <= t_done]

    return {
        "schema_version": SCHEMA_VERSION,
        "arm": ARM,
        "role": ROLE,
        # Was the module-level constant MODE = "readiness_dev". eval/score_gate0.py::_verify_sources
        # requires this to EQUAL the mode being scored, so a hardwired stamp makes every paid-mode
        # reconstruction void -- and only at scoring. Required, never defaulted: see the module
        # docstring's "Why --mode has no default".
        "mode": mode,
        "wall_clock_s": round(t_done - t_first_input, 3),
        "primitive_actions": len(trimmed_events),
        "success": True,
        "failures": [],
        "player": incomplete.get("player"),
        "started_at": datetime.fromtimestamp(t_first_input, tz=timezone.utc).isoformat(),
        "completed_at": datetime.fromtimestamp(t_done, tz=timezone.utc).isoformat(),
        "rom_path": incomplete.get("rom_path"),
        "rom_sha256": incomplete.get("rom_sha256"),
        "savestate_path": incomplete.get("savestate_path"),
        "savestate_sha256": incomplete.get("savestate_sha256"),
        "oracle_path": str(trace_path),
        "test_mode": incomplete.get("test_mode", False),
        "attempt_number": 1,
        "retake_reason": "",
        "input_event_times": trimmed_events,
        # Reconstruction provenance -- a superset on top of the live rig's schema. The frozen
        # source-pin loader (eval.score_gate0._verify_sources) only reads a named-key allow-list off
        # the human artifact and never rejects extra keys -- see
        # tests/test_score_gate0.py::test_frozen_source_pins_load_exact_artifacts and this file's own
        # test_reconstructed_artifact_passes_frozen_verify_sources.
        "reconstructed": True,
        "reconstruction_method": RECONSTRUCTION_METHOD,
        "reconstruction_source_trace_sha256": _sha256_bytes(trace_bytes),
        "reconstruction_source_incomplete_sha256": _sha256_bytes(incomplete_bytes),
        "reconstructed_at": datetime.now(timezone.utc).isoformat(),
        "completion_row_index": completion_row_index,
    }


def _strip_extended_prefix(p: Path) -> Path:
    r"""Drop a caller-supplied Windows extended-length prefix (`\\?\`, `\\?\UNC\`).

    `Path.resolve()` deliberately PRESERVES such a prefix -- CPython's `ntpath.realpath` only strips
    one it added itself -- so `\\?\C:\x` and `C:\x` name the same file on disk and still compare
    unequal. Stripping is what makes the comparison in `_resolves_inside_banked` see one file
    instead of two.

    Called AFTER `.resolve()`, and that ordering is the whole ballgame. Two more spellings carry the
    bare `\\?\` prefix but do NOT continue with a drive letter:

        \\?\GLOBALROOT\GLOBAL??\C:\...\banked\x
        \\?\Volume{a9f08932-...}\...\banked\x

    Strip the prefix off either one FIRST and what is left (`GLOBALROOT\GLOBAL??\C:\...`,
    `Volume{...}\...`) is a RELATIVE path. `.resolve()` then anchors it to the CWD, so the comparison
    is made against a path in a completely unrelated place -- the drive matches the referent's, the
    UNC fail-closed rule below never fires, containment fails, and the write goes to the banked
    directory anyway through the original spelling, which Windows opens fine. Both spellings were live
    write vectors under the reverse order, in both filesystem states. Resolving FIRST collapses both
    aliases to `\\?\C:\...` -- `Path.resolve()` does normalise them -- so the strip only ever sees a
    drive letter and can only produce an absolute path.

    The one thing the reverse order did that this one does not: it refused
    `\\?\C:\a\elsewhere\..\banked\x`, because `\\?\` switches Windows path normalisation off, the `..`
    survives `.resolve()` as a literal component, and `banked` stays among the `.parents`. That
    refusal protected nothing. The same switched-off normalisation means Windows cannot OPEN such a
    path -- `OSError` [Errno 22] / WinError 123, at `mkdir`, at `write_text` and at a raw `open` alike
    -- so it is not a write vector in either order; it is pinned as a non-vector by
    tests/...::test_extended_length_dotdot_is_not_writable_at_all. A `..` in an ORDINARY path still
    normalises and still reaches the banked directory, and is still refused, under either order.

    Note this helper is NOT what refuses the plain `\\?\C:\...` spelling: the UNC fail-closed rule
    below subsumes that, since `Path(r"\\?\C:\x").drive` is `\\?\C:` and already starts with `\\`.
    What it buys is that a LEGITIMATE extended-length path -- how Windows addresses anything past
    MAX_PATH, which the deeply nested worktrees this repo runs in get close to -- is not over-refused.
    That is the one behaviour that distinguishes keeping it from deleting it, and it is pinned by
    tests/...::test_an_extended_length_path_outside_the_banked_dir_is_still_allowed."""
    s = str(p)
    if s.startswith(_EXT_UNC_PREFIX):
        return Path("\\\\" + s[len(_EXT_UNC_PREFIX):])
    if s.startswith(_EXT_PREFIX):
        return Path(s[len(_EXT_PREFIX):])
    return p


def _resolves_inside_banked(out_path: Path) -> bool:
    r"""Is `out_path`'s EFFECTIVE write target at or under BANKED_DIR?

    Resolved, not merely normalised: the thing that must be bound is where the write actually lands,
    not the string the caller typed. `Path.resolve()` is non-strict (the target need not exist yet)
    and follows symlinks in the existing parents, so `--out <symlink-into-runs>/human_metrics.json`
    is caught too. PR #195's review found exactly this hole in the sibling -- an explicit `--out`
    slipping past a check that had been applied only to the mode-derived path.

    Two Windows properties this must keep, both found by PR #196's review, both pinned by tests:

    * NO SAME-VOLUME ASSUMPTION, and it must not start making one. The `.resolve()` on the REFERENT
      side (`BANKED_DIR`) is load-bearing, not decoration. `runs/` on this machine already holds 26
      NTFS junctions pointing at another volume (`D:\ai_pokemon_runs\`); if `runs/gate0_human_baseline/`
      ever gets the same treatment, the referent is NAMED on one volume and LIVES on another, and only
      resolving both sides keeps them comparable. Dropping that one `.resolve()` leaves the entire
      suite green while the guard silently stops firing -- see
      tests/...::test_write_artifact_refuses_through_a_junctioned_parent, which is the mutant's
      counterexample.
    * SPELLINGS THAT NAME THE SAME FILE MUST NOT COMPARE UNEQUAL. `\\?\C:\x`, and the volume aliases
      `\\?\GLOBALROOT\GLOBAL??\C:\x` and `\\?\Volume{GUID}\x`, are handled by `.resolve()` followed by
      `_strip_extended_prefix` -- IN THAT ORDER, for the reason spelled out in that helper's docstring;
      the reverse order left the two volume aliases as live write vectors into this very directory.
      `\\localhost\C$\x` and `\\127.0.0.1\C$\x` also name the same file as
      `C:\x`, but nothing in pathlib maps a UNC admin share back to its drive letter, and no rule
      decides which hostnames mean "this machine" (an alias, the machine's own name, `::1`, a
      genuinely remote host that happens to be spelled the same way). Containment across the two
      naming universes is therefore UNDECIDABLE, so a UNC target measured against a drive-letter
      referent returns True: FAIL CLOSED. An unnecessary refusal costs a re-run with a different
      `--out`; a write into the banked tree is not recoverable.

      The rule is an XOR and BOTH of its terms are load-bearing. When both sides are UNC (repo hosted
      on a share) the ordinary comparison applies and nothing is over-refused -- widening it to `or`,
      or dropping the referent term, would refuse EVERY write on such a checkout, and left the whole
      suite green until tests/...::test_a_unc_referent_still_decides_a_target_on_the_same_share
      existed (mutations M23/M24). ⚠ That branch's own limit, since it is now claimed explicitly: with
      both sides UNC the comparison is ordinary string containment, and host aliases
      (`\\server\...` vs `\\10.0.0.5\...`) are as undecidable there as against a drive letter, so it
      can UNDER-refuse where the drive-letter branch fails closed. Unreachable here -- BANKED_DIR is
      derived from `Path(__file__).resolve().parents[1]` and is always drive-lettered -- and there is
      no correct answer to hardcode."""
    target = _strip_extended_prefix(out_path.resolve())
    banked = _strip_extended_prefix(BANKED_DIR.resolve())
    if target.drive.startswith("\\\\") != banked.drive.startswith("\\\\"):
        return True
    return target == banked or banked in target.parents


def write_artifact(artifact: dict, out_path: Path) -> None:
    # UNCONDITIONAL, and deliberately not overridable by any flag. This is the single choke point
    # every write goes through -- the mode-derived default and an explicit `--out` both arrive here
    # as the same `out_path` -- so no argument, mode, or flag combination ROUTES AROUND the check.
    # It is checked BEFORE the existence test and before any mkdir, so a refusal creates nothing on
    # disk. Two distinct reasons it is a path check rather than the existence check below: (1) the
    # existence check only protects files that happen to already be there, so in a fresh
    # checkout/container/worktree it protects nothing -- verified on origin/main, where a no-`--out`
    # run silently CREATED runs/gate0_human_baseline/red/human_metrics.json and exited 0; (2) it also
    # covers oracle.jsonl and everything else banked alongside it.
    #
    # SCOPE, stated rather than implied (PR #196's review). "Unreachable" is a claim about THIS
    # process's BANKED_DIR, which is derived from THIS module's own repo root
    # (Path(__file__).resolve().parents[1]). Run this tool from one worktree -- where `runs/` is
    # gitignored and typically absent -- and aim `--out` at ANOTHER checkout's
    # runs/gate0_human_baseline/red/ and the guard does not fire, because that path is not under this
    # root; the existence check does not fire either when the target is absent there. That is not a
    # defect to fix here (repo-relative is the only sane definition of BANKED_DIR) but it is a real
    # limit, and with many worktrees live in this checkout it is not hypothetical.
    if _resolves_inside_banked(out_path):
        raise SystemExit(
            f"refusing: {out_path} is inside the banked Red baseline directory {BANKED_DIR} -- "
            "that tree is append-only raw data (the artifact three source-pin fixtures freeze by "
            "digest, and the oracle trace its numbers came from). No flag overrides this. Pass "
            "--out somewhere else, or use the paid-mode directory for the mode you are "
            "reconstructing.")
    if out_path.exists():
        raise SystemExit(
            f"refusing: {out_path} already exists -- one cold attempt per task "
            "(DAVID_BASELINES.md re-run rule); this tool never overwrites a banked baseline")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(artifact, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def build_arg_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else "")
    # REQUIRED, NO DEFAULT -- see the module docstring's "Why --mode has no default". Choices come
    # from the frozen scorer's own MODES map, never a list re-declared here.
    ap.add_argument("--mode", required=True, choices=tuple(score_gate0_modes()),
                     help="which pre-registered Gate 0 mode this reconstruction belongs to; stamps "
                          "human_metrics.json's `mode` field (which eval/score_gate0.py requires to "
                          "equal the mode being scored) and selects the output directory. Both paid "
                          "modes additionally require --i-am-human. No default: an unstated mode is "
                          "an artifact the scorer rejects.")
    ap.add_argument("--trace", type=Path, required=True, help="attempt-1 oracle.jsonl trace")
    ap.add_argument("--incomplete", type=Path, required=True,
                     help="attempt-1 human_metrics.INCOMPLETE_*.json")
    ap.add_argument("--out", type=Path, default=None,
                     help="defaults to <the --mode directory>/human_metrics.json (see the module "
                          "docstring). Never permitted inside the banked baseline directory.")
    ap.add_argument("--i-am-human", action="store_true", dest="i_am_human",
                     help="required for every held-out mode (HELD_OUT_MODES: paid_gate0, "
                          "paid_gate0_v2) -- explicit, non-default acknowledgement that a real "
                          "human, not a script, is deliberately producing a paid-gate denominator. "
                          "A scripted invocation cannot satisfy this by accident.")
    return ap


def main() -> int:
    args = build_arg_parser().parse_args()

    # Mode resolution + the held-out guard, before a single file is read. Same order and same shape
    # as tools/capture_gate0_baseline_red.py::run(). The MODE_CONFIG membership test is not dead
    # code: --mode's choices come from the SCORER's MODES, so a mode added there but not here must
    # refuse rather than KeyError.
    mode = args.mode
    if mode not in MODE_CONFIG:
        print(f"refusing: unknown --mode {mode!r} (must be one of {sorted(MODE_CONFIG)}).",
              file=sys.stderr)
        return 2
    if mode in HELD_OUT_MODES and not getattr(args, "i_am_human", False):
        print(f"refusing: --mode {mode} requires --i-am-human -- this reconstructs the human "
              "denominator the paid gate's `agent <= 2.0x human` bar is measured against; a "
              "scripted or absent-minded invocation must never be able to produce it. Pass "
              "--i-am-human only when a real human is deliberately recovering a real capture "
              "session's archived evidence.", file=sys.stderr)
        return 2
    if args.out is None:
        args.out = MODE_CONFIG[mode]["real_out"] / "human_metrics.json"

    artifact = reconstruct(args.trace, args.incomplete, mode)
    write_artifact(artifact, args.out)

    print(f"wrote {args.out}")
    print(f"completion_row_index={artifact['completion_row_index']}")
    print(f"wall_clock_s={artifact['wall_clock_s']}")
    print(f"primitive_actions={artifact['primitive_actions']}")
    print(json.dumps(artifact, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
