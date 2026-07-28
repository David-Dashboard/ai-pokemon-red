# Sweep group manifest — exact savestates behind every uniqueness count

The savestates themselves are throwaway scratch (443 in the session scratch dir + 14 in `s12/`,
457 total) and are NOT committed, per convention. This file pins **which** of them formed each
group so the counts in `reports/2026-07-28-kirby-gba-level-oracle.md` are checkable rather than
guessable. Names are as emitted by the drive plans; `s12/` is the greedy-search snapshot dir.

Read a group with the committed sweeper:

```
python kgba_ram.py cands u8 "<comma-joined GROUP_1>" "<comma-joined GROUP_2>"
python kgba_ram.py trace 0x030023ec:u8 <state> [<state> ...]
```

## GROUP S11 — "inside stage 1-1, or on the map / title card" (23 states, all read 0)

Spans 5 distinct rooms of stage 1-1, the goal sequence, both world-map states, the stage-1-1
replay *after* 1-1 was cleared, and the post-continue level title card.

```
p0_gr7.state e1_left120.state e2_L26.state
a1_r02.state a1_r10.state a1_r18.state
a2_r30.state a2_r44.state
a3_r04.state a3_r12.state
a4_r02.state a4_r10.state a4_r20.state
d3_R92.state d5_K3.state
d6_P1.state          # goal / star sequence of stage 1-1
g1_c13.state         # Vegetable Valley map, immediately after clearing 1-1
k1_k07.state         # Vegetable Valley map, after GAME OVER -> CONTINUE
q1_L12.state rp2_r00.state rp2_r04.state rp2_r08.state   # stage 1-1 REPLAYED after clearing it
b1_r25.state         # post-continue "LEVEL 1: VEGETABLE VALLEY" title card -- NOT a game-over frame
```

## GROUP S12 — "inside stage 1-2" (21 states, all read 1)

Four independent playthroughs of stage 1-2, including its deep rooms and the mini-boss arena.

```
m2_N12.state m2_N16.state
b1_r02.state b1_r08.state b1_r14.state
c1_r02.state c1_r08.state c1_r14.state c1_r18.state c1_r25.state c1_r30.state
c2_r02.state c2_r10.state c2_r30.state
s12/s002.state s12/s008.state s12/s013.state
bs_f00.state bs_f10.state
bx_g12.state bx_g29.state
```

## GROUP GO — "GAME OVER menu, after dying in stage 1-2" (6 states, all read 1)

Full `GAME OVER / CONTINUE / QUIT` menu frames. Committed as
`evidence/07_gameover_continue.png` (montage) and `evidence/08_gameover_frames_read_1.png`
(the r17–r25 sequence). `b1_r17` is the wipe-in and `b1_r24` the fade-out; both are excluded as
transitional.

```
b1_r18.state b1_r19.state b1_r20.state b1_r21.state b1_r22.state b1_r23.state
```

## The two sweep designs

| design | zero side | one side | u8 / u16 / u32 survivors |
|---|---|---|---|
| **A** — GO reads as stage-1-2 state ("most recently entered stage") | S11 | S12 + GO | **4 / 3 / 2**, `0x030023ec` the only `[0,1]` |
| **B** — GO reads as a non-stage screen | S11 + GO | S12 | **0 / 0 / 0** |

Design B returning zero survivors across all of IWRAM+EWRAM at every width is not a
disqualification of the candidate — it says **no address anywhere in RAM** behaves that way, i.e.
"game over is not in a stage" is not a distinction the game's RAM draws. Design A is the grouping
the data supports.

## Full-corpus tally (all 457 states, no grouping)

`0x030023ec` u8 over every savestate on disk: **255 x `1`, 202 x `0`** — no third value ever
observed, which is exactly the open question (see the report's "What is NOT established").
