# Gate 0 human baselines -- what David runs

Two scripts, one for each Gate 0 arm. Both only launch, time, and record -- **you** play every
step; the rig never presses a button or picks a click. Total time: **about 10 minutes**
(~5 min Red, ~5 min MiniWoB).

This is precondition 6 of `reports/2026-07-18-gate0-prereg.md` ("Human baselines recorded
(who/when)"). Running the two commands below is what makes that precondition `MET` -- this PR ships
the rig, not the captured numbers.

## 1. Pokemon Red (Arm R) -- bedroom -> starter -> rival win

You need `roms/PokemonRed.gb` and `runs/red_start.state` locally (both gitignored, never
committed). If you don't already have `red_start.state`, build one with `human_play.py` (see its
docstring) or copy the one from an existing checkout/readiness run
(`runs/gate0_readiness_2026-07-14/`).

```
uv run python tools/capture_gate0_baseline_red.py
```

What you'll see: a real PyBoy window opens straight into the fresh bedroom. The terminal prints the
fresh party count (must read `0` -- if it doesn't, you've got the wrong savestate, Ctrl-C and fix
it) and the task verbatim:

> From the fresh bedroom start, obtain your first Pokemon from Professor Oak and win the first
> rival battle.

Controls are PyBoy's defaults (same as `human_play.py`): arrow keys move, **A** = the `a` key,
**B** = the `s` key, **Start** = Enter, **Select** = Backspace. Just play it -- the timer starts on
your very first keypress. Once the rig detects the real end state (party count `0->1`, then a
trainer battle, then a sustained exit with your HP never hitting zero, then you move to at least 2
different tiles), it prints `[task complete ...]` in the terminal -- close the window (or Ctrl-C)
to finish and write the baseline.

Writes to `runs/gate0_human_baseline/red/`:
- `human_metrics.json` -- your wall-clock time and button-press count (the exact fields
  `eval/score_gate0.py` reads for the human side of the `<=2.0x` Capability bar), plus `player`,
  `started_at`/`completed_at` (ISO 8601 UTC), and `rom_sha256`/`savestate_sha256` for provenance.
- `oracle.jsonl` -- the raw watch-row trace (append-only, same RAM fields the real agent's oracle
  would log: x, y, map, party, badges, in_battle, party_hp_hi/lo).

## 2. MiniWoB click-checkboxes (Arm W) -- 5 fresh DEV episodes

MiniWoB only runs inside the Docker/Selenium image (`miniwob`/`selenium` are intentionally never
installed in the main project env -- see `Dockerfile.miniwob`). Build it once if you haven't:

```
docker build -f Dockerfile.miniwob -t miniwob-mcp-world .
```

Then run the capture script inside that image (bind-mount the single script file over the image
root so `import world_mcp` still resolves, and mount `runs/` so the artifacts land on your host):

```
docker run -it --rm \
  -v "$PWD/tools/capture_gate0_baseline_miniwob.py:/app/capture_gate0_baseline_miniwob.py" \
  -v "$PWD/runs:/app/runs" \
  --entrypoint python miniwob-mcp-world capture_gate0_baseline_miniwob.py
```

(On Windows PowerShell, use `${PWD}` or an absolute path in place of `$PWD` if your shell doesn't
expand it inside `-v`.)

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

Writes to `runs/gate0_human_baseline/miniwob/`:
- `human_metrics.json` -- same schema shape as Red's (`schema_version`, `arm`, `role="human"`,
  `mode`, `wall_clock_s`, `primitive_actions`), plus `player`/timestamps/`expected_seeds`.
- `oracle.jsonl` -- `MiniWobSession`'s own oracle writer, unmodified (episode/seed/step/task/
  reward/done/abandoned rows).
- `ep<N>_step<K>.png` -- exactly what you were shown at each decision, for provenance.

## Re-run rule (the exam law)

A baseline is **one cold attempt per task**
(`reports/2026-07-13-minimum-north-star-gate-0-design.md`: "one attempt per world, with artifacts
and verdict banked as-is").

- **A botched capture may be re-taken.** Rig crashed, wrong savestate loaded, your machine
  restarted mid-run, Docker died -- just re-run the command. A fresh `human_metrics.json` is
  written on the next success; any earlier `human_metrics.INCOMPLETE_<timestamp>.json` files stay
  on disk (append-only, never overwritten or deleted -- they're the raw-data record of the botched
  attempts, not junk to clean up).
- **A bad score may NOT be re-taken.** If the rig genuinely detected success but your time or press
  count came out worse than you'd like, that *is* the baseline. Re-running to chase a better number
  is exactly the "informal rerun to rescue a marginal result" the design doc forbids ("Bank
  PASS/FAIL/... as printed. Never rescue a marginal result with an informal rerun.").
- Neither script checks whether `human_metrics.json` already exists before writing -- that
  discipline is on you, not enforced by the file system. If in doubt, ask before re-running.

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
