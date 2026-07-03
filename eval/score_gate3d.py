"""eval/score_gate3d.py -- GATE-3D scorer implementing GATE-3D-A1 (reports/2026-07-04-vizdoom-3d-floor-
design.md AMENDMENT A1 SS A1.4) as re-pinned by AMENDMENT A2 (SS A2.2, after the perception-free-decoy
guard fired on PR #75's free baselines: alternating spinner 3.66 >= the A1.4 bar 3.375). The gate
statements there are pre-registered LAW: every constant below (1.5, 1.15, 1.5x KPS, 10 shots, 0.90,
20, 0.50, 3, 25) is copied from those sections, not re-derived or re-tuned here. Stricter-only:
thresholds change ONLY via a further amendment to that document.

Consumes a run directory produced by world_mcp.DoomDtcSession against `scenarios/dtc_gate.cfg`:
  <run>/oracle.jsonl     -- {episode, seed, step, tic, health, ammo2, killcount, finished, abandoned}
  <run>/grounding.jsonl   -- {episode, seed, step, tic, commanded, direction, dx_px, confidence}
plus the pinned seeds list (eval/fixtures/gate3d_seeds.json -- the same file DoomDtcSession's
--seeds-file was launched with) and the committed FREE-baseline record (eval/fixtures/gate3d_baselines.json,
written from tools/gate3d_baselines.py's A2.3 re-run). Per SS A2.3 the baselines file is this scorer's
ONLY source for D and KPS_spinner -- never constants in code:
  * D               = max mean final KILLCOUNT over ALL policy entries in the file (every top-level
                      key not starting with "_" is a policy; the D set is add-only per SS A2.2 --
                      adding a reviewer-proposed decoy = adding an entry, which can only raise D).
  * KPS_spinner     = the `kps` of the strongest-K spinner variant (the "spinner*"-named entry with
                      the highest mean_killcount), per SS A2.2.

ARM (a) -- task (SS A2.2 verbatim, BOTH discriminators required):
  (a-1) Kill margin over the strongest decoy:  K >= max(D + 1.5, 1.15 * D),
        K = mean final oracle KILLCOUNT over the 30 pinned-seed episodes.
  (a-2) Ammo efficiency:  KPS_brain >= 1.5 * KPS_spinner, where KPS = (sum final KILLCOUNT) /
        (sum shots) over episodes; per episode shots = ammo2_first - ammo2_last from oracle.jsonl
        rows. dtc has no ammo pickups, so ammo2 is monotonically non-increasing; ANY increase is
        reported loudly and the episode excluded (from BOTH KPS sums -- excluding it from the shots
        sum alone, A2.2's letter, would leave its kills inflating KPS_brain, the looser direction,
        which a stricter-only amendment cannot mean). Guard: the brain must fire >= 10 shots total
        across the run, else ARM (a-2) is INSUFFICIENT_DATA (not a pass).

ARM (b) -- grounding honesty (A1.4 verbatim, carried over unchanged by A2): from grounding.jsonl,
sign-agreement between `commanded` turn direction and P1's own `direction` reading >= 0.90 over >= 20
scored commanded-turn steps; P1 None-rate on turn steps <= 0.50. Fewer than 20 scored turn steps =
ARM (b) NOT PASSED (no vacuous pass).

DEGENERATE GUARDS (A1.4, all carried over by A2 unchanged; any fires => no PASS is recordable):
  * one-attempt-per-seed: enforced by the HARNESS (DoomDtcSession._advance_seed), not re-derived here --
    this scorer's job is to USE the abandoned-episode rows (final killcount at abandonment) exactly like
    any other episode row, never drop them (A1.4: "no re-rolling a bad start").
  * completion floor: < 25/30 episodes present in oracle.jsonl (by distinct episode index over the 30
    pinned seeds) => INSUFFICIENT_DATA.
  * variation guard: the (up to) 30 final killcounts must span >= 3 distinct values AND episode lengths
    (final tic) must not all be identical => else DEGENERATE.
  * alignment: oracle/grounding rows are joined by (episode index, step/tic) ONLY -- no wall-clock
    anywhere in this file (PR #55 sev-1 lesson, carried forward verbatim).
The A1.4 decoy guard ("each decoy must score under the bar") is structural under (a-1): every measured
decoy is <= D < max(D + 1.5, 1.15 * D) by construction (SS A2.2's closing note).

Verdicts: PASS / FAIL / DEGENERATE / INSUFFICIENT_DATA. PASS requires (a-1) AND (a-2) AND (b).

Usage:
    uv run python -m eval.score_gate3d runs/<run>/oracle.jsonl runs/<run>/grounding.jsonl \\
        eval/fixtures/gate3d_seeds.json eval/fixtures/gate3d_baselines.json
"""
from __future__ import annotations

import argparse
import json
import sys

# Pinned per GATE-3D-A1 SS A1.4 as amended by SS A2.2 -- verbatim, stricter-only from here.
N_EPISODES = 30
COMPLETION_FLOOR = 25            # < 25/30 completed episodes -> INSUFFICIENT_DATA
MIN_DISTINCT_KILLCOUNTS = 3      # variation guard: final killcounts must span >= this many distinct values
ARM_B_SIGN_AGREEMENT_MIN = 0.90
ARM_B_MIN_TURN_STEPS = 20
ARM_B_NONE_RATE_MAX = 0.50
ARM_A1_ADDITIVE_MARGIN = 1.5       # (a-1): K >= D + 1.5            (SS A2.2)
ARM_A1_MULTIPLICATIVE_FACTOR = 1.15  # (a-1): K >= 1.15 * D         (PASS requires the MAX of the two)
ARM_A2_KPS_FACTOR = 1.5            # (a-2): KPS_brain >= 1.5 * KPS_spinner  (SS A2.2)
ARM_A2_MIN_SHOTS = 10              # (a-2): < 10 total shots -> INSUFFICIENT_DATA for (a-2), not a pass


def load_jsonl(path: str) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def load_seeds(path: str) -> list[int]:
    with open(path, encoding="utf-8") as f:
        return [int(s) for s in json.load(f)]


def load_baselines(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def gate_bar(d: float) -> float:
    """The pinned (a-1) PASS bar (SS A2.2): max(D + 1.5, 1.15 * D), D = strongest perception-free decoy."""
    return max(d + ARM_A1_ADDITIVE_MARGIN, ARM_A1_MULTIPLICATIVE_FACTOR * d)


# ---------------------------------------------------------------------------
# Baselines file -> D and KPS_spinner (SS A2.3: the file is the ONLY source; the D set is add-only).
# ---------------------------------------------------------------------------

def policy_entries(baselines: dict) -> dict[str, dict]:
    """Every top-level key not starting with "_" is a measured perception-free policy. The D set is
    add-only (SS A2.2): a reviewer-proposed decoy lands as a new entry here and can only RAISE D."""
    return {k: v for k, v in baselines.items() if not k.startswith("_") and isinstance(v, dict)}


def d_from_baselines(baselines: dict) -> tuple[float, str]:
    """D = max mean final KILLCOUNT over the measured policy set; returns (D, which policy)."""
    entries = policy_entries(baselines)
    if not entries:
        raise ValueError("baselines file has no policy entries -- cannot derive D")
    name = max(entries, key=lambda k: float(entries[k]["mean_killcount"]))
    return float(entries[name]["mean_killcount"]), name


def kps_spinner_from_baselines(baselines: dict) -> tuple[float, str]:
    """KPS_spinner = the KPS of the strongest-K spinner variant (SS A2.2: "multi-hot vs alternating"),
    i.e. among entries named spinner*, the one with the highest mean_killcount; returns (kps, name)."""
    entries = policy_entries(baselines)
    spinners = {k: v for k, v in entries.items() if k.startswith("spinner")}
    if not spinners:
        raise ValueError("baselines file has no spinner* entries -- cannot derive KPS_spinner")
    name = max(spinners, key=lambda k: float(spinners[k]["mean_killcount"]))
    kps = spinners[name].get("kps")
    if kps is None:
        raise ValueError(f"strongest-K spinner entry {name!r} has no kps -- re-run the A2.3 baselines")
    return float(kps), name


# ---------------------------------------------------------------------------
# ARM (a-1): per-episode final KILLCOUNT, over the pinned seed list.
# ---------------------------------------------------------------------------

def _rows_by_episode(oracle: list[dict], seeds: list[int]) -> dict[int, list[dict]]:
    """Group oracle rows by episode index (only indices inside the pinned seed list), each episode's
    rows sorted by step -- the ONLY join key anywhere in this file (never wall-clock)."""
    by_episode: dict[int, list[dict]] = {}
    for rec in oracle:
        ep = rec.get("episode")
        if ep is None or int(ep) < 0 or int(ep) >= len(seeds):
            continue   # a stray episode index outside the pinned seed list -- not scoreable
        by_episode.setdefault(int(ep), []).append(rec)
    for rows in by_episode.values():
        rows.sort(key=lambda r: r.get("step", 0))
    return by_episode


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
    final: dict[int, float] = {}
    for ep, rows in _rows_by_episode(oracle, seeds).items():
        for rec in reversed(rows):
            kc = rec.get("killcount")
            if kc is not None:
                final[ep] = float(kc)
                break
    return final


def _final_tic_by_episode(oracle: list[dict], seeds: list[int]) -> dict[int, int]:
    return {ep: int(rows[-1].get("tic", 0)) for ep, rows in _rows_by_episode(oracle, seeds).items()}


# ---------------------------------------------------------------------------
# ARM (a-2): brain KPS from oracle.jsonl ammo2 (SS A2.2's formula + guards).
# ---------------------------------------------------------------------------

def _brain_kps(oracle: list[dict], seeds: list[int], final_kc: dict[int, float]) -> dict:
    """Per SS A2.2: per episode shots = ammo2_first - ammo2_last over the episode's oracle rows (the
    first and last NON-NULL ammo2 readings, by step order); any ammo2 INCREASE across consecutive
    non-null readings (dtc has no ammo pickups) is reported loudly and the episode is excluded from
    the KPS sums (both -- see the module docstring). KPS_brain = (sum final KILLCOUNT) / (sum shots)
    over the included episodes. Guard: < ARM_A2_MIN_SHOTS total shots -> status INSUFFICIENT_DATA."""
    total_kills = 0.0
    total_shots = 0.0
    excluded: list[dict] = []
    for ep, rows in sorted(_rows_by_episode(oracle, seeds).items()):
        ammo_series = [r["ammo2"] for r in rows if r.get("ammo2") is not None]
        if not ammo_series or ep not in final_kc:
            excluded.append({"episode": ep, "reason": "no readable ammo2 rows" if not ammo_series
                             else "no readable killcount"})
            continue
        increased = any(b > a for a, b in zip(ammo_series, ammo_series[1:]))
        if increased:
            # LOUD per SS A2.2: an ammo2 increase in a world with no ammo pickups means the log cannot
            # be trusted for this episode's shot count -- excluded and reported, never silently kept.
            excluded.append({"episode": ep, "reason": "ammo2 INCREASED mid-episode (dtc has no ammo "
                                                      "pickups -- log untrustworthy for shots)"})
            continue
        total_kills += final_kc[ep]
        total_shots += float(ammo_series[0]) - float(ammo_series[-1])

    enough_shots = total_shots >= ARM_A2_MIN_SHOTS
    kps = (total_kills / total_shots) if total_shots else None
    return {"total_kills": total_kills, "total_shots": total_shots, "kps_brain": kps,
            "excluded_episodes": excluded, "enough_shots": enough_shots}


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

    d, d_policy = d_from_baselines(baselines)
    kps_spinner, kps_spinner_policy = kps_spinner_from_baselines(baselines)
    bar = gate_bar(d)
    result["D"] = d
    result["D_policy"] = d_policy
    result["gate_bar"] = bar
    result["kps_spinner"] = kps_spinner
    result["kps_spinner_policy"] = kps_spinner_policy
    result["kps_bar"] = ARM_A2_KPS_FACTOR * kps_spinner

    final_kc = _final_killcount_by_episode(oracle, seeds)
    final_tic = _final_tic_by_episode(oracle, seeds)
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

    # ARM (a-1): kill margin over the strongest decoy (SS A2.2).
    arm_a1 = K >= bar
    result["arm_a1"] = arm_a1

    # ARM (a-2): ammo efficiency (SS A2.2), with the >= 10-shots guard.
    kps_detail = _brain_kps(oracle, seeds, final_kc)
    result["arm_a2_detail"] = kps_detail
    if not kps_detail["enough_shots"]:
        result["arm_a2"] = "INSUFFICIENT_DATA"
        arm_a2_passed = False
    else:
        arm_a2_passed = kps_detail["kps_brain"] >= ARM_A2_KPS_FACTOR * kps_spinner
        result["arm_a2"] = "PASS" if arm_a2_passed else "FAIL"

    # ARM (a) requires BOTH discriminators (SS A2.2).
    arm_a = arm_a1 and arm_a2_passed
    result["arm_a"] = arm_a

    arm_b_detail = _arm_b(grounding)
    arm_b = arm_b_detail["passed"]
    result["arm_b"] = arm_b
    result["arm_b_detail"] = arm_b_detail
    result["verdict"] = "PASS" if (arm_a and arm_b) else "FAIL"
    return result


def format_report(r: dict) -> str:
    lines = ["=== GATE-3D-A1 (as amended by A2) score ==="]
    lines.append(f"pinned seeds: {r.get('n_pinned_seeds')}  completed episodes: "
                f"{r.get('n_completed_episodes')}/{N_EPISODES}")
    if r["verdict"] == "INSUFFICIENT_DATA" and "K" not in r:
        lines.append(f"\nVERDICT: INSUFFICIENT_DATA ({r.get('reason')})")
        return "\n".join(lines)

    lines.append(f"D (strongest perception-free decoy, from eval/fixtures/gate3d_baselines.json): "
                f"{r['D']:.3f} [{r['D_policy']}]")
    lines.append(f"(a-1) bar = max(D+{ARM_A1_ADDITIVE_MARGIN}, {ARM_A1_MULTIPLICATIVE_FACTOR}*D) = "
                f"{r['gate_bar']:.3f}")
    lines.append(f"KPS_spinner (strongest-K spinner variant [{r['kps_spinner_policy']}]): "
                f"{r['kps_spinner']:.4f}  ->  (a-2) bar = {ARM_A2_KPS_FACTOR} * KPS_spinner = "
                f"{r['kps_bar']:.4f}")
    lines.append(f"K (mean final KILLCOUNT over {len(r['killcounts'])} episodes): {r['K']:.3f}")
    lines.append(f"  killcounts: {r['killcounts']}")
    lines.append(f"  distinct killcount values: {r['n_distinct_killcounts']}  "
                f"distinct episode lengths (tics): {r['n_distinct_episode_lengths']}")

    if r["verdict"] == "DEGENERATE":
        lines.append(f"\nVERDICT: DEGENERATE ({r.get('reason')})")
        return "\n".join(lines)

    a2 = r["arm_a2_detail"]
    if a2["excluded_episodes"]:
        lines.append(f"  !! KPS-excluded episodes ({len(a2['excluded_episodes'])}): "
                    + "; ".join(f"ep {e['episode']}: {e['reason']}" for e in a2["excluded_episodes"]))
    kps_str = "n/a" if a2["kps_brain"] is None else f"{a2['kps_brain']:.4f}"
    lines.append(f"\nARM (a-1) kill margin (K >= bar): {'PASS' if r['arm_a1'] else 'FAIL'}  "
                f"({r['K']:.3f} vs bar {r['gate_bar']:.3f})")
    lines.append(f"ARM (a-2) ammo efficiency (KPS_brain >= {ARM_A2_KPS_FACTOR}*KPS_spinner): "
                f"{r['arm_a2']}  (KPS_brain={kps_str} over {a2['total_shots']:.0f} shots / "
                f"{a2['total_kills']:.0f} kills vs bar {r['kps_bar']:.4f}"
                + (f"; < {ARM_A2_MIN_SHOTS} total shots -- not a pass" if not a2["enough_shots"] else "")
                + ")")
    lines.append(f"ARM (a) = (a-1) AND (a-2): {'PASS' if r['arm_a'] else 'FAIL'}")
    b = r["arm_b_detail"]
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
