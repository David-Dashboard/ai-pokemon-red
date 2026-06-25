# Cave Noire HP-oracle fixture (minimal, committed)

Backs the report claim "`0xD389` is the **unique** WRAM byte matching the visible HP at two known frames"
(`reports/2026-06-25-phase-a-hud-grounding-precheck.md`, Check 3) so a reviewer can verify it from a clean
checkout — without the full 32 MB recording (gitignored corpus on D:).

Contents (the 2 anchor frames sliced out of `runs/2026-06-23_cavenoire_explore`):
- `ram.bin` — two 8 KB WRAM snapshots (`0xC000..0xDFFF`): fixture frame **0** = source frame 100 (screen reads
  **HP 7/10**); fixture frame **1** = source frame 500 (**HP 10/10**).
- `frame_000000.png`, `frame_000001.png` — the matching screenshots (read the HP off these yourself).

Reproduce (exactly one byte must match both anchors):

    uv run python -m eval.find_hp_addr eval/fixtures/cavenoire_hp_oracle --anchors 0:7 1:10
    # -> byte(s) matching ALL anchors: ['0xD389']

This proves *uniqueness against the two anchors*, which is the claim. The full-run value distribution
(`{0,2,4,5,7,8,10,15}` incl. the 4 transition frames reading 15) needs the full recording — regenerate it via
`record.py` if you want to re-derive that part.
