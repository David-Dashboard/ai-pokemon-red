# Codex CLI 0.144.3 — headless MCP tool-call trust research ($0, no exec run)

Method: local-only inspection (`codex --help`, `codex mcp --help/add/get/list`, `codex doctor`,
`~/.codex/config.toml`, `~/.codex/state_5.sqlite` schema) plus web/GitHub research. No `codex exec`
against a model was run; no bypass flag was invoked or scripted.

## Q1 — What governs MCP auto-approve vs interactive approval? Is there a persisted per-server trust?

No. `mcp_servers.<name>` in config.toml only supports `command`/`args`/`env`/`env_vars`/`cwd`/
`enabled_tools`/`disabled_tools`/`startup_timeout_sec`/`tool_timeout_sec` — confirmed empirically by
`codex mcp add probe_srv -- echo hello` then `codex mcp get probe_srv --json` (full field dump, no
trust/approval field). This contrasts with hooks, which do have persisted trust
(`[hooks.state.'<path>:<event>:...']  trusted_hash = "sha256:..."` in config.toml, unlocked by
`--dangerously-bypass-hook-trust`) — there is no MCP analogue. `~/.codex/state_5.sqlite` has no
trust/approval table either; the only related column is `threads.approval_mode` (per-thread shell
approval mode, not an MCP allow-list).

Root cause (confirmed via GitHub, not guessed): all MCP tool calls route through
`maybe_request_mcp_tool_approval()` in `core/src/mcp_tool_call.rs`, which is meant to gate only the
built-in `codex_apps` server (`CODEX_APPS_MCP_SERVER_NAME`) but is called unconditionally for every
MCP server — an acknowledged, currently **open**, unfixed regression
([openai/codex#15824](https://github.com/openai/codex/issues/15824), assigned to a maintainer, no
fix merged). The approval path calls `RequestUserInput`, which is not supported in `exec` mode; with
stdin closed, that reads EOF and is treated as decline → "user cancelled MCP tool call"
([openai/codex#16685](https://github.com/openai/codex/issues/16685)). This exactly matches the
Gate0 symptom.

## Q2 — Any config key/env var that pre-approves MCP calls without disabling the sandbox?

None found, and none is claimed to work by anyone who has tried it. `codex mcp add/list/get` have no
trust/approve subcommand. GitHub issue [openai/codex#24135](https://github.com/openai/codex/issues/24135)
(filed v0.130.0, still **open**) is an exhaustive negative result from another user hitting this exact
problem; confirmed **none** of these work: `approval_policy="never"`, `default_tools_approval_mode="never"`,
`tools_require_approval=false`, `mcp_approval_policy="never"`, `trusted_mcp_servers=[...]`,
`[projects."<cwd>"].trust_level="trusted"`, `[mcp_servers.<name>].approval_policy="never"` — a superset of
what our Gate0 investigation already ruled out. `--strict-config` parse-probing turned out uninformative:
it does **not** enforce `deny_unknown_fields` on unrecognized keys anywhere we tested (confirmed with
deliberately bogus keys — all "accepted"), so a clean parse proves nothing; only the empirical `mcp add`/`get`
round-trip and the GitHub reports are load-bearing evidence. `features list` shows `guardian_approval=true`
and `tool_call_mcp_elicitation=true` (both stable, both already ruled out), plus `request_permissions_tool`
and `exec_permission_approvals` — both `under development`/`false`, unusable in 0.144.3. A merged PR,
[openai/codex#19431](https://github.com/openai/codex/pull/19431) ("Route opted-in MCP elicitations through
Guardian", merged 2026-05-06), lets specific first-party integrations (e.g. Browser Use) tag an elicitation
`codex_request_type="approval_request"` in their own server code to route through Guardian — explicitly
**not** an auto-approve, needs server-side code changes, not a config override an arbitrary Docker MCP
server can opt into.

## Q3 — Does interactive trust persist for a later headless `codex exec`?

Only one persisted trust concept exists: `[projects.'<path>'].trust_level = "trusted"` (present in our
real config.toml for this project already). Per official docs this only controls whether project-scoped
`.codex/` config/hooks/rules load — unrelated to MCP tool-call approval. The #24135 reporter set this to
`"trusted"` and confirmed it did **not** stop MCP-call cancellation. No "approve this MCP server once,
persisted for exec" flow exists, analogous to hook trust.

## Q4 — Bottom line
**NOT ACHIEVABLE** cleanly on codex-cli 0.144.3. This is a live, upstream, unresolved bug/gap (issues
#24135, #16685, #15824 all open as of 2026-07-22), not a missing launcher flag — no config key, `-c`
override, or persisted trust file exists to fix it. Options: (a) accept
`--dangerously-bypass-approvals-and-sandbox` — David's security call; (b) wait for the unmerged,
unassigned-ETA fix to #15824; (c) a different harness — experimental `codex app-server`/`--remote`
exposes approval/elicitation requests as RPC over a socket rather than the stdin-EOF path `codex exec`
uses, so a custom client *might* answer approvals programmatically without disabling the sandbox —
untested, needs its own spike.

## Note on sources

Two low-signal, non-maintainer comments on #24135 included a link to an unaffiliated third-party
"helper" tool; it was not downloaded or run. Only the maintainer-filed issue bodies, the merged PR,
and the empirical local checks are load-bearing for this verdict.
