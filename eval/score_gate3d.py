"""eval/score_gate3d.py -- GATE-3D-A1 scorer, implementing
reports/2026-07-04-vizdoom-3d-floor-design.md AMENDMENT A1 SS A1.4 VERBATIM. The gate statement there is
pre-registered LAW: every constant below (2.0, 1.5, 0.90, 20, 0.50, 3, 25) is copied from that section,
not re-derived or re-tuned here.

Consumes a run directory produced by world_mcp.DoomDtcSession against `scenarios/dtc_gate.cfg`:
  <run>/oracle.jsonl     -- {episode, seed, step, tic, health, ammo2, killcount, finished, abandoned}
  <run>/grounding.jsonl   -- {episode, seed, step, tic, commanded, direction, dx_px, confidence}
plus the pinned seeds list (eval/fixtures/gate3d_seeds.json -- the same file DoomDtcSession's
--seeds-file was launched with) and the committed FREE-baseline record (eval/fixtures/gate3d_baselines.json,
written by tools/gate3d_baselines.py -- this is where R, the mean random-policy killcount, comes from;
"measured and written into the scorer BEFORE the paid run", A1.4).

ARM (a) -- task: K = mean final oracle KILLCOUNT over the 30 episodes. PASS requires
    K >= max(R + 2.0, 1.5 * R)
where R is READ from the committed baselines file, never re-derived here (A1.4: "measured ... BEFORE
the paid run").

ARM (b) -- grounding honesty: from grounding.jsonl, sign-agreement between `commanded` turn direction
and P1's own `direction` reading, over commanded-turn steps (commanded in {"left", "right"}) with a
non-None P1 reading counted toward agreement -- >= 0.90 sign-agreement over >= 20 scored turn steps;
P1 None-rate on turn steps <= 0.50. Fewer than 20 scored turn steps = ARM (b) NOT PASSED (no vacuous
pass, A1.4 verbatim).

DEGENERATE GUARDS (A1.4, all fire before either arm is even evaluated as PASS -- "any fires => no PASS
is recordable"):
  * one-attempt-per-seed: enforced by the HARNESS (DoomDtcSession._advance_seed), not re-derived here --
    this scorer's job is to USE the abandoned-episode rows (final killcount at abandonment) exactly like
    any other episode row, never drop them (A1.4: "no re-rolling a bad start").
  * completion floor: < 25/30 episodes present in oracle.jsonl (by distinct episode index over the 30
    pinned seeds) => INSUFFICIENT_DATA.
  * variation guard: the (up to) 30 final killcounts must span >= 3 distinct values AND episode lengths
    (final tic) must not all be identical => else DEGENERATE.
  * alignment: oracle/grounding rows are joined by (episode index, step/tic) ONLY -- no wall-clock
    anywhere in this file (PR #55 sev-1 lesson, carried forward verbatim).

Verdicts: PASS / FAIL / DEGENERATE / INSUFFICIENT_DATA. Both arms are required for PASS.

Usage:
    uv run python -m eval.score_gate3d runs/<run>/oracle.jsonl runs/<run>/grounding.jsonl \\
        eval/fixtures/gate3d_seeds.json eval/fixtures/gate3d_baselines.json
"""
from __future__ import annotations

import argparse
import json
import sys

# Pinned per GATE-3D-A1 SS A1.4 -- verbatim, stricter-only from here.
N_EPISODES = 30
COMPLETION_FLOOR = 25            # < 25/30 completed episodes -> INSUFFICIENT_DATA
MIN_DISTINCT_KILLCOUNTS = 3      # variation guard: final killcounts must span >= this many distinct values
ARM_B_SIGN_AGREEMENT_MIN = 0.90
ARM_B_MIN_TURN_STEPS = 20
ARM_B_NONE_RATE_MAX = 0.50
ARM_A_ADDITIVE_MARGIN = 2.0      # K >= R + 2.0
ARM_A_MULTIPLICATIVE_FACTOR = 1.5  # K >= 1.5 * R  (PASS requires the MAX of the two bars)


def load_jsonl(path: str) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def load_seeds(path: str) -> list[int]:
    with open(path, encoding="utf-8") as f:
        return [int(s) for s in json.load(f)]


def load_baselines(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def gate_bar(r: float) -> float:
    """The pinned PASS bar for ARM (a): max(R + 2.0, 1.5 * R)."""
    return max(r + ARM_A_ADDITIVE_MARGIN, ARM_A_MULTIPLICATIVE_FACTOR * r)


# ---------------------------------------------------------------------------
# ARM (a): per-episode final KILLCOUNT, over the pinned seed list.
# ---------------------------------------------------------------------------

def _final_killcount_by_episode(oracle: list[dict], seeds: list[int]) -> dict[int, float]:
    """One-attempt-per-seed discipline: the harness enforces exactly one attempt per pinned seed
    (abandoned episodes recorded at abandonment killcount, per DoomDtcSession._advance_seed). This
    scorer therefore takes, for each episode index present, the LAST oracle row (by step order) THAT
    HAS A NON-NULL killcount -- not blindly the last row overall.

    Why: core.vizdoom_world.VizdoomWorld.game_variables() returns None once is_episode_finished() is
    already True (its own guard against reading a dead game). DoomDtcSession._log_oracle calls
    game_variables() to build the terminal row, so an episode that ends NATURALLY (death/timeout, as
    opposed to being abandoned by an early new_episode) can have its LAST row carry killcount=null even
    though every prior row this same episode has a real value -- the true final killcount is simply the
    last row that actually observed it, one step earlier. Falling back to the latest non-null row is
    strictly more faithful to "use those rows, not drop them" than either (a) taking the literal last
    row and losing the episode's last real reading to a logging artifact, or (b) dropping the episode
    from scoring altogether."""
    by_episode: dict[int, list[dict]] = {}
    for rec in oracle:
        ep = rec.get("episode")
        if ep is None:
            continue
        by_episode.setdefault(int(ep), []).append(rec)

    final: dict[int, float] = {}
    for ep, rows in by_episode.items():
        if ep < 0 or ep >= len(seeds):
            continue   # a stray episode index outside the pinned seed list -- not scoreable
        rows_sorted = sorted(rows, key=lambda r: r.get("step", 0))
        for rec in reversed(rows_sorted):
            kc = rec.get("killcount")
            if kc is not None:
                final[ep] = float(kc)
                break
    return final


def _final_tic_by_episode(oracle: list[dict]) -> dict[int, int]:
    by_episode: dict[int, list[dict]] = {}
    for rec in oracle:
        ep = rec.get("episode")
        if ep is None:
            continue
        by_episode.setdefault(int(ep), []).append(rec)
    out: dict[int, int] = {}
    for ep, rows in by_episode.items():
        rows_sorted = sorted(rows, key=lambda r: r.get("step", 0))
        out[ep] = int(rows_sorted[-1].get("tic", 0))
    return out


# ---------------------------------------------------------------------------
# ARM (b): sign-agreement + None-rate over commanded-turn grounding rows.
# ---------------------------------------------------------------------------

def _turn_rows(grounding: list[dict]) -> list[dict]:
    """Rows where a turn was actually commanded (commanded in {"left","right"}) -- ATTACK rows
    (commanded=None) are excluded from ARM (b), per A1.4 ("commanded turn direction")."""
    return [r for r in grounding if r.get("commanded") in ("left", "right")]


def _arm_b(grounding: list[dict]) -> dict:
    turns = _turn_rows(grounding)
    n_turns = len(turns)
    n_none = sum(1 for r in turns if r.get("direction") is None)
    scored = [r for r in turns if r.get("direction") is not None]
    n_scored = len(scored)
    n_agree = sum(1 for r in scored if r["direction"] == r["commanded"])
    sign_agreement = (n_agree / n_scored) if n_scored else 0.0
    none_rate = (n_none / n_turns) if n_turns else 1.0

    # A1.4 verbatim: "Fewer than 20 scored turn steps = ARM (b) NOT PASSED (no vacuous pass)." Scored
    # here means turn steps with a P1 reading present -- the denominator sign-agreement is computed over.
    enough_steps = n_scored >= ARM_B_MIN_TURN_STEPS
    passed = (enough_steps
              and sign_agreement >= ARM_B_SIGN_AGREEMENT_MIN
              and none_rate <= ARM_B_NONE_RATE_MAX)
    return {
        "n_turn_steps": n_turns, "n_scored_turn_steps": n_scored,
        "sign_agreement": sign_agreement, "none_rate": none_rate,
        "enough_steps": enough_steps, "passed": passed,
    }


# ---------------------------------------------------------------------------
# Top-level scorer.
# ---------------------------------------------------------------------------

def score(oracle_path: str, grounding_path: str, seeds_path: str, baselines_path: str) -> dict:
    oracle = load_jsonl(oracle_path)
    grounding = load_jsonl(grounding_path)
    seeds = load_seeds(seeds_path)
    baselines = load_baselines(baselines_path)

    result: dict = {"n_pinned_seeds": len(seeds)}

    r = float(baselines["random"]["mean_killcount"])
    bar = gate_bar(r)
    result["R"] = r
    result["gate_bar"] = bar

    final_kc = _final_killcount_by_episode(oracle, seeds)
    final_tic = _final_tic_by_episode(oracle)
    n_completed = len(final_kc)
    result["n_completed_episodes"] = n_completed

    # COMPLETION FLOOR (A1.4): < 25/30 episodes completed -> INSUFFICIENT_DATA. This fires before any
    # other guard or arm is evaluated -- there isn't enough data to trust anything downstream of it.
    if n_completed < COMPLETION_FLOOR:
        result["verdict"] = "INSUFFICIENT_DATA"
        result["reason"] = (f"only {n_completed}/{N_EPISODES} pinned-seed episodes completed "
                            f"(< {COMPLETION_FLOOR})")
        return result

    killcounts = [final_kc[ep] for ep in sorted(final_kc)]
    tics = [final_tic[ep] for ep in sorted(final_kc) if ep in final_tic]
    K = sum(killcounts) / len(killcounts)
    result["K"] = K
    result["killcounts"] = killcounts

    # VARIATION GUARD (A1.4): >= 3 distinct final killcount values AND episode lengths not all
    # identical -- a constant kill signature (or a constant episode length) indicates a scripted
    # artifact, not a brain actually playing 30 independent episodes.
    n_distinct_kc = len(set(killcounts))
    n_distinct_tic = len(set(tics))
    result["n_distinct_killcounts"] = n_distinct_kc
    result["n_distinct_episode_lengths"] = n_distinct_tic
    if n_distinct_kc < MIN_DISTINCT_KILLCOUNTS or n_distinct_tic < 2:
        result["verdict"] = "DEGENERATE"
        result["reason"] = (f"final killcounts span {n_distinct_kc} distinct value(s) "
                            f"(need >= {MIN_DISTINCT_KILLCOUNTS}) and episode lengths span "
                            f"{n_distinct_tic} distinct tic value(s) (need >= 2) -- looks scripted, "
                            "not 30 independently-played episodes")
        return result

    arm_a = K >= bar
    arm_b_detail = _arm_b(grounding)
    arm_b = arm_b_detail["passed"]
    result["arm_a"] = arm_a
    result["arm_b"] = arm_b
    result["arm_b_detail"] = arm_b_detail
    result["verdict"] = "PASS" if (arm_a and arm_b) else "FAIL"
    return result


def format_report(r: dict) -> str:
    lines = ["=== GATE-3D-A1 score ==="]
    lines.append(f"pinned seeds: {r.get('n_pinned_seeds')}  completed episodes: "
                f"{r.get('n_completed_episodes')}/{N_EPISODES}")
    if r["verdict"] == "INSUFFICIENT_DATA" and "K" not in r:
        lines.append(f"\nVERDICT: INSUFFICIENT_DATA ({r.get('reason')})")
        return "\n".join(lines)

    lines.append(f"R (random-policy baseline, from eval/fixtures/gate3d_baselines.json): {r['R']:.3f}")
    lines.append(f"gate bar = max(R+2.0, 1.5*R) = {r['gate_bar']:.3f}")
    lines.append(f"K (mean final KILLCOUNT over {len(r['killcounts'])} episodes): {r['K']:.3f}")
    lines.append(f"  killcounts: {r['killcounts']}")
    lines.append(f"  distinct killcount values: {r['n_distinct_killcounts']}  "
                f"distinct episode lengths (tics): {r['n_distinct_episode_lengths']}")

    if r["verdict"] == "DEGENERATE":
        lines.append(f"\nVERDICT: DEGENERATE ({r.get('reason')})")
        return "\n".join(lines)

    b = r["arm_b_detail"]
    lines.append(f"\nARM (a) task (K >= gate bar): {'PASS' if r['arm_a'] else 'FAIL'}  "
                f"({r['K']:.3f} vs bar {r['gate_bar']:.3f})")
    lines.append(f"ARM (b) grounding honesty: {'PASS' if r['arm_b'] else 'FAIL'}  "
                f"sign_agreement={b['sign_agreement']:.3f} (need >= {ARM_B_SIGN_AGREEMENT_MIN}), "
                f"none_rate={b['none_rate']:.3f} (need <= {ARM_B_NONE_RATE_MAX}), "
                f"scored_turn_steps={b['n_scored_turn_steps']} (need >= {ARM_B_MIN_TURN_STEPS})")
    lines.append(f"\nGATE: {r['verdict']}")
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("oracle", help="path to <run>/oracle.jsonl")
    ap.add_argument("grounding", help="path to <run>/grounding.jsonl")
    ap.add_argument("seeds", help="path to the pinned seeds JSON (eval/fixtures/gate3d_seeds.json)")
    ap.add_argument("baselines", help="path to the committed FREE-baseline record "
                                      "(eval/fixtures/gate3d_baselines.json)")
    args = ap.parse_args(argv)
    result = score(args.oracle, args.grounding, args.seeds, args.baselines)
    print(format_report(result))
    return 0 if result.get("verdict") in ("PASS", "FAIL", "DEGENERATE") else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
