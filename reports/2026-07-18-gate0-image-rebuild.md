# Gate 0 precondition 9 — world image rebuild + C0 parity receipt (2026-07-18)

**Result: parity all-match YES.** Both pinned Gate 0 world images rebuilt from a clean checkout of
`origin/main` and pass canonical host/image code parity per `Get-CanonicalCodeSha256`
(`tools/run_gate0_codex.ps1`, post-#114 `d75e8be`).

## Checkout

Fresh WSL clone (`~/gate0-image-rebuild`), branch `main-clean` tracking `origin/main`,
`git status --porcelain` empty. **HEAD** `154e8dfae102a5783506f6030ac4942980530f5c` (merges PR #115
on top of PR #114 `a689192`; `gh pr view 114` confirms `state=MERGED`). `origin/main` has since
advanced to `b45b47f` (PR #116, unrelated); `154e8df` remains an ancestor — nothing rewritten.

## Images built

Docker Desktop was down at start; started it, polled (4x15s) to `docker info` OK. No containers were
running (all `Created`/`Exited`) — none stopped/removed.

| Image | Dockerfile | Image ID (sha256) |
|---|---|---|
| `gb-mcp-world:latest` | `Dockerfile` | `5bfabc7513ce037ed077e955fd34445ef564a7b51037bd7fdddeef0cdb900d00` |
| `miniwob-world:latest` | `Dockerfile.miniwob` | `8bb3358e1421dc97c72c07809fdef048f63d64bdfddb170c4d0188337fe6fd0f` |

## Parity (replicates launcher scheme verbatim, not run end-to-end — no Codex/ROM involved)

Host: `git diff --quiet HEAD -- <path>` (clean) then `git cat-file blob HEAD:<path> | sha256sum`.
Image: `docker run --rm --network none --entrypoint python <id> -c '<hashlib sha256 of open(p,"rb").read()>' /app/world_mcp.py /app/core/miniwob_world.py`.

| File | Host blob sha256 | `gb-mcp-world` in-image | `miniwob-world` in-image | Match |
|---|---|---|---|---|
| `world_mcp.py` | `967866ab...9fc9` | `967866ab...9fc9` | `967866ab...9fc9` | YES |
| `core/miniwob_world.py` | `f98b0dc9...3ce54` | `f98b0dc9...3ce54` | `f98b0dc9...3ce54` | YES |

(Full hashes: `967866ab5ddcfcef17747aab1d83070a95a32c2cb05bc0b6252defce7b519fc9` and
`f98b0dc9846bff0fceb96c8f77eee8b4261b9db894abd793a8d7b1145a23ce54`.) All 4 host/image comparisons
match — both files, both images — the same check `run_gate0_codex.ps1` gates a launch on.

## Deviations

- Reused an existing WSL clone left from the prior Docker-Desktop-down attempt, after confirming it
  was clean at `origin/main`; it had no artifacts to preserve (died before producing any).
- Did not run `tools/run_gate0_codex.ps1` end-to-end (needs Codex auth + ROM/state, out of scope for
  precondition 9); replicated its hashing scheme directly, per the task's instruction.
- Branch pinned to `154e8df` exactly, not the now-advanced `origin/main` tip, so the report's claims
  stay consistent with what was actually built/hashed; confirmed still an ancestor of `origin/main`.

## Remaining

None for precondition 9. Other Gate 0 preconditions (3, 4, 6, 8) remain open — out of scope here.
