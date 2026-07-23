# F3 / A1 — the survivable-deliberation window (MKDS latency injection)

**Status:** free offline probe, $0, no paid LLM. Answers capability-map A1's "cheapest next probe"
(`reports/2026-07-05-northstar-capability-map.md:38-40`): scripted System-2 latency injection in
Mario Kart DS — how long can the brain be SILENT (a fixed System-1 reflex holding a default) before
the race is ruined? That window is the requirements spec for A5's reflex layer.

Harness: `eval/mkds_latency_window.py`. Native py-desmume on the banked savestate
`runs/nds3d_probe/mkds_race_start.state` (Figure-8 Circuit, 50cc, standing start). **Ruin oracle**
= LE u32 forward-speed at RAM `0x0237438C` (found this session; ~22 at rest, plateau **V_top =
2,031,638** at top speed, →22 pinned on a wall). Oracle is OFFLINE labelling only — the reflex reads
no memory (mirrors the `perception_plugin` no-leak rule). Speed=0 ruin was eyeball-confirmed:
straight-hold ends nose-pinned in the turn-1 "DANGER" barrier.

## Measured (frames @ 59.83 fps; horizon 500f = 8.4s)

Idle/accel drift reproduces banked FINDINGS (12.47/33.37 vs 12.22/33.23%) — the world advances every
frame with zero input; a **null reflex never launches** (speed 0 forever → race lost by forfeit).

**A. Fixed open-loop reflex horizon** (whole System-1 = a fixed input, no perception):

| Reflex (fixed, open-loop) | Outcome | Horizon from GO |
|---|---|---|
| null (no input) | never moves; forfeits | 0 |
| accel + hold-RIGHT (wrong way) | instant inside-wall crash | 29f / **0.49s** |
| accel only (hold straight) | tops out, then dead-stops in turn-1 wall | 180f / **3.0s** |
| accel + hold-LEFT (full, right way) | rounds more, still walls | 224f / **3.7s** |
| accel + **pulse-LEFT (half strength)** | **clears turn 1, holds top speed** | >500f / **>8.4s (no ruin)** |

**B. Survivable System-2 silence at the first turn** — good policy = pulse-left (clears turn 1);
inject N frames of straight-hold silence right after GO, then the good policy resumes:

| Silence N | 0–120f (0–2006ms) | 150f (2507ms) |
|---|---|---|
| clears turn 1? | **yes** (survives full window) | **no** (crashes like straight) |

**N\* = 120f = ~2.0s** survivable; fatal by ~2.5s. (First failure is *position*-commitment: at N=150
the kart is still at top speed but too deep to make the corner.)

## The window

**On MKDS 50cc's start-straight → turn-1, the survivable-deliberation window is ~2.0–2.5s** with a
null (straight-hold) reflex and a competent policy resuming. It is **feature-dependent**: a straight
gives seconds; *inside* a turn (continuous steering required) it collapses toward ~0 — cf. wrong-way
bias ruining in 0.49s. It is also **speed-dependent**: 50cc is the slowest class; 100/150cc shrink it.

## Requirements spec for A5 (the payload)

1. Between deliberations, A5 must keep the kart on-track for ≥ one System-2 decision latency.
   Measured budget: ~2.0s at 50cc turn-1 approach; less at higher CC; ~0 mid-turn.
2. A **hold-last-input** reflex meets this ONLY on a straight and only for ~2s — it cannot round a
   turn. A fixed reflex *can* hold the race (pulse-left did), **but only when hand-matched to that
   turn's curvature/direction**: the opposite sign crashes in 0.49s, over-strong same-sign still
   walls. Matching the bias per turn requires *sensing* the turn — i.e. a **closed-loop** reflex.
3. That closed-loop track-follower is gated on a perception primitive (track-edge / minimap-heading)
   the NDS lane has **not** built (rotating non-tile minimap + free-font breaks, `FINDINGS.md`;
   deferred `region_*`, `2026-07-04-continuous-time-stopwhen-design.md` §3). **Real-time MKDS is
   perception-gated, not reflex-quantity-gated** — the sharpened pin for the real-time attempt.

**Falsifier (map A1) NOT triggered:** an achievable fixed reflex *did* hold turn 1. But only a
closed-loop one generalizes across turns. *Inference (labelled):* a vision-LLM tool-call decision is
~1–10s; even at the forgiving 50cc, the ~2s window ≈ one decision — no margin, hence closed-loop.

## Honest notes / negatives banked

- **Infra:** Docker daemon down here; native py-desmume in `.venv-win` runs the state faithfully. The
  Linux-made savestate prints "error loading … probably corrupt" on Windows desmume but simulates
  correctly (idle/accel drift matches FINDINGS) — the warning is benign.
- **Discarded first Measurement B:** a piecewise opener steered during frames 30–90 = *before* GO
  (~f108), i.e. during the countdown; countdown-wiggle pre-angled the launch and gave a misleading
  L\*≈1.0s. Replaced with the GO-anchored silence injection above. Trust the second number.
- **Scope:** one savestate, one track, one CC, screen-space + RAM-speed only; no lap-completion or
  multi-turn/crossover data. The ~2s is the start-straight→turn-1 case, an upper bound on the window.
