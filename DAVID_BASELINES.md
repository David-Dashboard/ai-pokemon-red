# Gate 0 human baselines -- what David runs

Two scripts, one for each Gate 0 arm. Both only launch, time, and record -- **you** play every
step; the rig never presses a button or picks a click. Total time: **about 10 minutes**
(~5 min Red, ~5 min MiniWoB).

This is precondition 6 of `reports/2026-07-18-gate0-prereg.md` ("Human baselines recorded
(who/when)"). Running the two commands below is what makes that precondition `MET` -- this PR ships
the rig, not the captured numbers.

> **These are DEV-seed readiness numbers, NEVER the paid gate's human denominator.** Both scripts
> hard-pin `"mode": "readiness_dev"` (Red always; MiniWoB against seeds `0..4`, never
> CLI-overridable). The design doc (W0 section) is explicit: DEV-seed human runs are a readiness
> estimate only -- the formal human-relative `<=2.0x` score for the paid Gate 0 attempt uses a
> **separate** human replay against the held-out paid seeds (`1000..1004` for MiniWoB; the prereg's
> Arm W paid-oracle seeds), run AFTER the agent's paid Arm-W attempt is banked, via
> `tools/capture_gate0_baseline_miniwob.py --mode paid_gate0 --i-am-human` (see the launch checklist
> in `reports/2026-07-21-gate0-readiness-final-v2.md` §6 step 4). Do not point `gate0_paid_source_pins.json`'s
> `miniwob_human`/`red_human` at this rig's output -- `eval.score_gate0._verify_sources` will refuse
> a mode mismatch, but don't rely on that as the only line of defense.

## Re-run rule (the exam law) -- read this before you press anything

A baseline is **one cold attempt per task**
(`reports/2026-07-13-minimum-north-star-gate-0-design.md`: "one attempt per world, with artifacts
and verdict banked as-is"). Both scripts now enforce this mechanically, not just by discipline:

- **A botched capture may be re-taken freely.** Rig crashed, wrong savestate loaded, your machine
  restarted mid-run, Docker died: if the run never reached a detected SUCCESS, no canonical
  `human_metrics.json` was ever written (only a distinctly-named
  `human_metrics.INCOMPLETE_<timestamp>.json`, which stays on disk -- append-only, never overwritten
  or deleted). Just re-run the command; nothing extra needed. (For MiniWoB, any partial
  `oracle.jsonl` the crashed session left behind -- including real terminal rows from episodes it
  did complete -- is auto-archived at the start of the re-run, so stale rows can never poison the
  fresh score. Red does the same: any `oracle.jsonl` left behind by an aborted/crashed session is
  auto-archived to `oracle.attempt<N>_<timestamp>.jsonl` at the start of the next run, so a fresh
  attempt never appends onto a prior one's rows.)
- **A bad-but-genuine score may NOT be casually re-taken.** If the rig genuinely detected success
  but your time or press count came out worse than you'd like, that *is* the baseline -- re-running
  to chase a better number is exactly the "informal rerun to rescue a marginal result" the design
  doc forbids. Both scripts now **refuse to overwrite an existing canonical `human_metrics.json`**
  and exit non-zero unless you pass `--allow-retake "<reason>"` (e.g.
  `--allow-retake "Docker died right after the success print, human_metrics.json never actually
  wrote on my first try"`). The written artifact then records `attempt_number` (2, 3, ...) and your
  `retake_reason` verbatim -- `attempt_number` is always `1` and `retake_reason` is always empty for
  a normal first capture. If in doubt whether your situation qualifies, ask before re-running.

## 1. Pokemon Red (Arm R) -- bedroom -> starter -> rival win

You need `roms/PokemonRed.gb` and `runs/red_start.state` locally (both gitignored, never
committed). If you don't already have `red_start.state`, build one with `human_play.py` (see its
docstring) or copy the one from an existing checkout/readiness run
(`runs/gate0_readiness_2026-07-14/`).

```
UV_PROJECT_ENVIRONMENT=.venv-win uv run --frozen python \
    tools/capture_gate0_baseline_red.py --mode readiness_dev
```

(Windows: that is the form used everywhere in this repo. On Linux/Pi, drop the two `UV_` bits and
use `uv run python ...`. Either way, running the file directly works -- the script puts the repo
root on `sys.path` itself, so you do not need `PYTHONPATH=.` or `python -m`. Both this command and
`--help` were executed as written on 2026-07-28 before this was documented; `--help` exits 0 and the
capture command reaches the ROM/savestate checks.)

`--mode` is **required and has no default** (2026-07-28), exactly like the MiniWoB rig's. It stamps
`human_metrics.json`'s `mode` field -- which `eval/score_gate0.py` requires to equal the mode being
scored -- and picks the output directory:

| `--mode` | writes to | extra flag |
|---|---|---|
| `readiness_dev` | `runs/gate0_human_baseline/red/` | -- |
| `paid_gate0` | `runs/gate0_paid_human_baseline/red/` | `--i-am-human` |
| `paid_gate0_v2` | `runs/gate0_paid_v2_human_baseline/red/` | `--i-am-human` |

Red has **no held-out seeds** (the design doc's "Red uses the same fixed start for agent and human"),
so the task, the savestate and the predicate are identical in every mode -- you play exactly the same
thing. `--i-am-human` is required for the paid modes anyway, because that artifact becomes the
denominator the `agent <= 2.0x human` bar is measured against.

For the Gate 0 v2 paid baseline (prereg P1c), the command is:

```
UV_PROJECT_ENVIRONMENT=.venv-win uv run --frozen python \
    tools/capture_gate0_baseline_red.py --mode paid_gate0_v2 --i-am-human
```

A paid-mode capture **refuses to start** unless that mode's source-pins fixture already points
`artifact_paths.red_human` at the directory above. Today all three fixtures still point at
`runs/gate0_human_baseline/red/`, so the command above refuses until that re-point lands (prereg
P1c) -- executed as written on 2026-07-28, it prints that refusal and exits `2`, which is the
correct behaviour today, not a breakage. The refusal names the exact fixture field to change. Do
**not** work around it by pointing `--out` at the banked dev directory: that file is append-only raw
data and three fixtures freeze its digest.

`--out` will not get you there. The rig refuses, before it creates anything, any `--out` that lands
at or under **another mode's** real baseline directory -- and the banked dev directory is another
mode's, for both paid modes. No flag turns that off: not `--test`, not `--i-am-human`, not
`--allow-retake`.

Spelling the path differently does not get you there either, but read what that does and does not
claim. Each spelling below is pinned by a test that drives the real `run()` against a stand-in
baseline directory and asserts nothing was written, moved or renamed -- in **both** states, the
directory existing and the directory not yet created (the live one today: neither paid directory
exists on this checkout):

| spelling | how it is stopped |
|---|---|
| case (`UPPER`, `lower`, mixed-case leaf), trailing separator, forward slashes, `..` round-trip | compared after `normcase` |
| a `mklink /J` junction, an 8.3 short name | compared after `realpath` (applied to **both** sides, so a junction on a shared prefix cancels) |
| a trailing dot or space (`...\red.`, `...\red `) | compared after `abspath`, which strips them as Win32 does |
| `\\?\C:\...` extended-length | the prefix is stripped, then compared |
| `\\localhost\C$\...`, `\\127.0.0.1\C$\...`, `\\?\UNC\...`, `\\.\C:\...` | **not compared at all -- refused outright.** No normalisation maps a share back to a drive letter and the set of host aliases is unbounded, so the rig refuses any UNC or device `--out` instead of pretending to check it |

The comparison takes the **union** of two normalisations because neither dominates: `realpath` sees
through junctions and short names but leaves a trailing dot verbatim, while `abspath` strips the
trailing dot but is blind to junctions. A previous round *replaced* one with the other and thereby
opened the trailing-dot escape it now closes (review E1/E2). What is **not** claimed: that this
enumeration is exhaustive. It is the set that has been executed.

An earlier draft of this paragraph said `--out` could not get you there *because the refusal is
checked against the directory the run would actually write*. That reason was **wrong, and backwards
in exactly this window**: it described the fixture cross-check, whose verdict follows the fixtures,
and today all three fixtures point at the banked directory -- so that check **blesses** the write
rather than blocking it. What blocks it is the separate path guard described above, which does not
consult a fixture at all. Recorded because a false reassurance here is worse than none.

What you'll see: a real PyBoy window opens straight into the fresh bedroom. The terminal prints the
fresh party count (must read `0` -- if it doesn't, you've got the wrong savestate, Ctrl-C and fix
it) and the task verbatim:

> From the fresh bedroom start, obtain your first Pokemon from Professor Oak and win the first
> rival battle.

Controls are PyBoy's defaults (same as `human_play.py`): arrow keys move, **A** = the `a` key,
**B** = the `s` key, **Start** = Enter, **Select** = Backspace. Just play it -- the timer starts on
your very first keypress. Once the rig detects the real end state (party count `0->1`, then a
trainer battle, then a sustained exit with your HP never hitting zero, then you move to at least 2
different tiles), it prints a loud `[TASK COMPLETE ...]` banner **and freezes your wall-clock time
and press count right there** -- anything you do after that (closing the window, wandering around)
never changes the banked numbers. The window then **auto-closes itself a few seconds later**
(`COMPLETION_GRACE_SECONDS`) so you don't have to notice the message or react quickly; you can also
close it yourself (or Ctrl-C) any time, including before completion, to finish early or abort.

Writes to the `--mode` directory in the table above (`runs/gate0_human_baseline/red/` for
`readiness_dev`):
- `human_metrics.json` -- your wall-clock time and button-press count, frozen at detection (the
  exact fields `eval/score_gate0.py` reads for the human side of the `<=2.0x` Capability bar), plus
  `player`, `started_at`/`completed_at` (ISO 8601 UTC), `rom_sha256`/`savestate_sha256`,
  `attempt_number`/`retake_reason`, and `input_event_times` (a raw per-keypress timestamp list, for
  auditing press cadence independently of the aggregate count) for provenance.
- `oracle.jsonl` -- the raw watch-row trace (append-only, same RAM fields the real agent's oracle
  would log: x, y, map, party, badges, in_battle, party_hp_hi/lo).

A setup failure (bad ROM, corrupt/incompatible savestate, PyBoy/SDL2 error before you ever get to
play) is caught cleanly too -- no orphaned window, an `INCOMPLETE` artifact instead of a bare
traceback.

## 2. MiniWoB click-checkboxes (Arm W) -- 5 fresh DEV episodes

MiniWoB only runs inside the Docker/Selenium image (`miniwob`/`selenium` are intentionally never
installed in the main project env -- see `Dockerfile.miniwob`). Build it once if you haven't:

```
docker build -f Dockerfile.miniwob -t miniwob-world .
```

**Precondition -- check this before capturing, or the capture is silently wrong.** Confirm the image
you are about to run is the pinned one:

```
docker image inspect --format '{{.Id}}' miniwob-world
```

It must equal `world_image_id` in `eval/fixtures/gate0_expected_pins_miniwob.json`. If it does not,
rebuild (above) before capturing. A stale image lacks `MiniWobSession._resolve_key`, so every
`key NAME` dies on `ValueError: invalid literal for int()` -- which means no scrolling, which means
Submit stays unreachable on 6-checkbox layouts and the run is unwinnable for reasons that have
nothing to do with your performance. (Historic trap: an older, superseded copy of this image was
tagged `miniwob-mcp-world`. That tag is no longer used anywhere -- if you have one lying around, it
is stale by definition; use `miniwob-world`.)

Then run the capture script inside that image. The image (`Dockerfile.miniwob`) only bakes in
`core/` + `world_mcp.py` -- it does NOT contain `tools/` or `eval/`, which the script needs
(`from eval.score_gate0 import MODES, _miniwob_success`, which itself imports
`tools.check_gate0_codex`). Mount BOTH directories, preserving their real repo-root nesting under
`/app` (a flat single-file mount breaks `ROOT = Path(__file__).resolve().parents[1]`'s path math),
and invoke via `-m` so the `tools`/`eval` packages resolve:

```
docker run -it --rm \
  -v "$PWD/tools:/app/tools" \
  -v "$PWD/eval:/app/eval" \
  -v "$PWD/runs:/app/runs" \
  --entrypoint python miniwob-world -m tools.capture_gate0_baseline_miniwob
```

(On Windows PowerShell, use `${PWD}` or an absolute path in place of `$PWD` if your shell doesn't
expand it inside `-v`. On Git Bash, set `MSYS_NO_PATHCONV=1` first -- otherwise Git Bash silently
mangles the container-side `/app/...` paths into Windows paths and the mount fails.)

The MiniWoB image itself is parity-pinned (Gate 0 pre-reg precondition 9 + C0) -- this fix only
changes the `docker run` invocation, never `Dockerfile.miniwob`, so no image rebuild or re-pin is
needed.

**Why not a live interactive browser window?** MiniWoB exists only inside that headless
Selenium/Chromium image. Making it truly click-with-your-mouse-live would need either host GUI
passthrough or the base image's bundled noVNC, *and* reverse-engineering the Farama-rewrite's
internal JS/webdriver state well enough to recognize a native OS click as an episode-terminating
action -- neither is inspectable or testable in this environment (the package is Docker-image-only,
never installed on the host). Instead this rig reuses the exact same code path the paid agent will
use (`world_mcp.MiniWobSession.call()`), and asks you to look at each step's real screenshot (the
same pixels the agent would see) and type the click/type/key action you want performed. That is
still screen-pixels-in + keyboard-mediated-mouse-out (the design doc's human control vocabulary),
it is the smallest glue that needed zero new dependencies, and it is the one path actually
exercised by this PR's automated tests (see "Verification" below) -- the live-browser path could
not be. If you'd rather drive a real visible browser, that is a separate, larger follow-up; this PR
deliberately does not attempt it.

What you'll see: the terminal prints the task exactly as MiniWoB gives it to a human (e.g. `Select
the words that are checked and click Submit.`), and pops open a screenshot PNG of the current page
in your default image viewer after every step. Look at the picture, then type your action at the
terminal prompt:

```
click X Y      click pixel (X, Y) in the screenshot -- (0,0) is top-left, viewport is 160x177
type TEXT      type TEXT into whatever currently has focus
key NAME       press a named key (e.g. Enter)
quit           abort -- writes an INCOMPLETE artifact, does not count as a bad attempt
```

Episodes advance automatically once one ends -- 5 fresh DEV-seed episodes (seeds `0..4`, frozen at
`eval/fixtures/gate0_miniwob_dev_seeds.json`; the script refuses to run against any other seed
list, so you can never accidentally touch the held-out paid seeds `1000..1004`).

The script requires a real interactive terminal (`docker run -it`, as shown above, gives you one)
when writing to the real baseline path -- this guards against a scripted stand-in silently answering
for you and writing to the real path; `--test` dry runs are exempt.

Writes to `runs/gate0_human_baseline/miniwob/`:
- `human_metrics.json` -- same schema shape as Red's (`schema_version`, `arm`, `role="human"`,
  `mode`, `wall_clock_s`, `primitive_actions`), plus `player`/timestamps/`expected_seeds`,
  `attempt_number`/`retake_reason`, `capture_modality` (`"screenshot_relay_typed_action"` --
  records that this was a typed-coordinate relay, not native mouse clicking, for a future
  verdict-writer interpreting the `<=2.0x` wall-clock bar), and `input_event_times` (a raw
  per-action timestamp list).
- `oracle.jsonl` -- `MiniWobSession`'s own oracle writer, unmodified (episode/seed/step/task/
  reward/done/abandoned rows). If an `oracle.jsonl` already exists when a run starts -- whether
  from a scored attempt being legitimately re-taken with `--allow-retake` OR from a crashed/quit
  partial attempt that never reached the canonical write -- it is archived (renamed, never
  deleted) to `oracle.attempt<N>_<timestamp>.jsonl` first, so every run scores against a clean
  trace instead of the terminal-count check seeing stale terminal rows from a prior session.
- `ep<N>_step<K>.png` -- exactly what you were shown at each decision, for provenance.

## Where a future scorer will point

`eval/score_gate0.py`'s `SOURCE_PIN_FILES` (`eval/fixtures/gate0_readiness_dev_source_pins.json` /
`gate0_paid_source_pins.json`) don't exist yet -- freezing them is a separate, still-open
precondition (pre-reg precondition 3). Whoever authors that fixture should point its
`red_human`/`miniwob_human` `artifact_paths` at:

```
runs/gate0_human_baseline/red/human_metrics.json
runs/gate0_human_baseline/miniwob/human_metrics.json
```

## Discrepancy note (code vs. reports)

`reports/2026-07-18-gate0-prereg.md`'s precondition table, as drafted, describes PR #114
(`eval/score_gate0.py` + the R0/W0/C0 readiness report) as "OPEN, not merged" and states
`eval/score_gate0.py` is "absent from main". As of this branch's base commit
(`main`@`154e8df`, 2026-07-18), both PR #114 and PR #115 are already merged: `eval/score_gate0.py`
and `reports/2026-07-14-gate0-readiness.md` are present on `main`. That text in the pre-reg doc is
stale relative to current `main`, not wrong at the time it was written. This rig was built and
tested directly against the merged `eval/score_gate0.py` (its `_red_success`/`_miniwob_success`
functions are imported, not re-implemented), so the artifact schema here is exactly what the code
checks, per `tests/test_score_gate0.py::test_frozen_source_pins_load_exact_artifacts`.
