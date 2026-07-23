# Label dataset v3

13 games · 250 labelled frames · 1146 boxes · 82 read-values (text/health).
**OCR-value coverage is sparse:** only 82/661 (12%) of text+health boxes carry a read string — the HUD-gate OCR ground truth is a milestone, **not yet cross-world** (concentrated in the early games). Treat accordingly.
Frames live in `runs/<game>/` (corpus, gitignored); these JSONs are the annotations.

| game | frames | avatar | enemy | item | text | health | exit | npc | values | modes |
|---|---|---|---|---|---|---|---|---|---|---|
| 2026-06-23_cavenoire_explore | 50 | 47 | 16 | 60 | 78 | 42 | 40 | 0 | 55 | gameplay:40,menu:8,transition:2 |
| 2026-06-23_crystalis_explore | 20 | 12 | 0 | 1 | 45 | 14 | 12 | 3 | 0 | gameplay:13,transition:4,menu:2,title:1 |
| 2026-06-23_f1race_explore | 20 | 7 | 5 | 0 | 55 | 0 | 0 | 0 | 0 | menu:13,gameplay:6,transition:1 |
| 2026-06-23_ffa_explore | 20 | 15 | 9 | 0 | 40 | 11 | 0 | 0 | 0 | gameplay:12,menu:7,transition:1 |
| 2026-06-23_gauntlet_ramplay | 10 | 8 | 29 | 6 | 43 | 0 | 2 | 0 | 8 | gameplay:9,menu:1 |
| 2026-06-23_gold_explore | 20 | 20 | 0 | 45 | 14 | 0 | 0 | 6 | 0 | gameplay:8,dialog:6,menu:4,transition:2 |
| 2026-06-23_kirby_ramplay | 10 | 8 | 11 | 0 | 12 | 19 | 0 | 0 | 11 | gameplay:9,menu:1 |
| 2026-06-23_metroid_ramplay | 10 | 9 | 2 | 1 | 14 | 0 | 0 | 0 | 5 | gameplay:8,menu:1,transition:1 |
| 2026-06-23_red_resume | 10 | 3 | 0 | 0 | 40 | 8 | 0 | 0 | 0 | menu:10 |
| 2026-06-23_sml_explore | 20 | 13 | 3 | 18 | 28 | 0 | 2 | 0 | 0 | gameplay:13,transition:6,menu:1 |
| 2026-06-23_spaceinv_auto | 10 | 8 | 10 | 0 | 10 | 8 | 0 | 0 | 3 | gameplay:8,menu:1,transition:1 |
| 2026-06-23_tetris_auto | 20 | 0 | 0 | 0 | 58 | 0 | 0 | 0 | 0 | gameplay:16,transition:2,menu:2 |
| 2026-06-23_zelda_explore | 30 | 21 | 1 | 6 | 100 | 22 | 7 | 19 | 0 | gameplay:17,menu:6,dialog:3,title:2,transition:2 |
| **TOTAL** | **250** | **171** | **86** | **137** | **537** | **124** | **63** | **28** | **82** | gameplay:159,menu:57,transition:22,dialog:9,title:3 |
