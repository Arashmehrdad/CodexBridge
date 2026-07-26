# PILOT-OPENCLAW-1 — External Shell Boundary

**Date:** 2026-07-27
**Status:** Closed — evaluated and rejected.
**Constraint honoured:** isolated `somapilot` profile, loopback only, pinned
2026.7.1, no public channels, no third-party skills, no production authority, no
Windows service installed.

## Purpose

Determine whether OpenClaw is a worthwhile owner-facing shell around Soma
without becoming a second task, schedule, memory, or evidence authority.

## Environment

| Component | Version |
|---|---|
| OpenClaw | 2026.7.1 (2d2ddc4), pinned |
| Node | 24.18.0 (upgraded from 24.14.0 to satisfy OpenClaw's engine range) |
| Claude Code | 2.1.220 |
| Codex | 0.145.0 |
| Soma MCP | `http://127.0.0.1:8000/mcp`, streamable-http, loopback |

Node was upgraded because OpenClaw 2026.7.1 requires
`>=22.22.3 <23 || >=24.15.0 <25 || >=25.9.0` and 24.14.0 fell in the gap. Both
coding agents were re-verified with authenticated structured invocations
afterwards and remained functional before the pilot proceeded.

---

## Finding 1 — the transport works; the projection does not

`openclaw mcp add soma --url … --transport streamable-http` succeeds, and
`openclaw mcp probe soma` connects and enumerates Soma's full surface, including
`soma__repo_query`. The shell can reach Soma.

What fails is the step after that: projecting those tools into the agent
runtime. With the profile's OpenAI/Codex-backed agent, `mcp__soma__*` never
appeared in the agent's tool catalog. Scoping the projection explicitly to the
`main` agent with a trusted approval mode did not change it. `/codex mcp` listed
only `codex_apps`; local `soma` was absent.

## Finding 2 — the only working shell route was vendor-specific

A genuine model-driven invocation did eventually succeed, but through
`mcp__codex_apps__soma_repo_query` — Codex's own hosted app catalog — not
through OpenClaw's local MCP projection.

| Route | Result |
|---|---|
| `mcp__codex_apps__soma_repo_query` | worked, 4.77s, returned live Soma data |
| local `mcp__soma__repo_query` projection | absent from the catalog |

This route was rejected by the owner, correctly. It binds Soma access to one
vendor's account-scoped app catalog, which violates the first governing
principle — controller neutrality — and would make OpenClaw a Codex client
rather than a neutral shell.

## Finding 3 — routing tools through the shell was never necessary

Both controllers reach Soma's MCP endpoint **directly**, with no shell in the
path. Measured, not asserted:

**Claude Code → Soma.** `repo_query(operation=compact_status, repo_name=soma)`
returned live data: branch `feature/chatgpt-companion-cycle`, recent commits,
diff stat, and the CF1 compact projection with `projection_version`,
`server_build_hash`, and `schema_hash`.

**Codex → Soma.** With `mcp_servers.soma` supplied as a config override so
nothing persisted to the user's `~/.codex/config.toml`, Codex emitted a genuine
`mcp_tool_call` item — `{"type":"mcp_tool_call","server":"soma","tool":"repo_query",
"arguments":{"operation":"compact_status","repo_name":"soma"}}` — and reported
the correct branch.

Same endpoint, same transport, no vendor catalog, no adapter, no shell.

## Final decision

> **Retain direct controller-to-Soma MCP. Retain Hermes as Soma's established
> companion and capability integration. Reject OpenClaw from the target
> architecture. Perform no further OpenClaw version, Claude-backend, ACPX,
> voice, or channel testing.**

This is not a workaround. It is what the accepted authority rule already
required:

> OpenClaw may retain only the exact Soma identifier and a projection.

A shell that routes tools is on the path of every capability call, and the
measured consequence was exactly the failure mode the rule exists to prevent:
Soma became reachable only through one vendor's catalog. Removing the shell from
the tool path removes the coupling entirely, and costs nothing, because the
direct route already works for both controllers.

## Incumbent and incremental-value gates

OpenClaw does not satisfy an unmet requirement:

1. **Controller capability access is already solved.** Claude Code and Codex
   both reach Soma directly over the same vendor-neutral MCP endpoint.
2. **The companion and capability layer already has an incumbent.** Hermes is
   accepted, integrated, and wired to Soma.
3. **A second shell would duplicate architecture.** OpenClaw would add another
   state, dependency, update, isolation, and failure surface without replacing a
   measured deficiency.

There is therefore no unresolved OpenClaw presentation, voice, channel, or
presence role. Future work in those areas starts from a measured
Hermes-specific gap. It does not reopen OpenClaw by default.

## Finding 4 — `--profile` isolation is partial

`--profile somapilot` isolates configuration and authentication into
`~/.openclaw-somapilot/` (`openclaw.json`, the agent auth-state SQLite). It does
**not** isolate everything. The agent workspace and TUI state were written into
the *default* root instead:

```
~/.openclaw/
├── tui/last-session.json
└── workspace-somapilot/          <- profile-named, default-rooted
    ├── AGENTS.md  BOOTSTRAP.md  HEARTBEAT.md
    ├── IDENTITY.md  SOUL.md  TOOLS.md
    └── openclaw-workspace-state.json
```

`~/.openclaw` did not exist before this pilot; it was created despite every
invocation passing `--profile`. The naming shows the intent — the workspace
carries the profile suffix — but the root does not follow the profile.

This matters beyond tidiness. A shell whose isolation boundary is partial is a
poor fit for per-project scoping, which is the property Soma treats as a
correctness invariant rather than a convenience. Removing the rejected pilot
cleanly requires deleting both profile-specific and default-root state.

## Secondary findings

- **OAuth installed `@openclaw/codex` with an unpinned npm install record.** A
  pinned shell that pulls an unpinned dependency during authentication is not
  fully pinned and weakens the value of the pinned-build precondition.
- **A bundled ClawHub installer skill appears in the runtime prompt**, although
  no external ClawHub skills were installed. The no-third-party-skills
  precondition held in substance, but the surface is present by default.
- **A Windows `UV_HANDLE_CLOSING` assertion** occurred once during a provider
  probe and did not recur. Recorded separately from authentication state,
  because a CLI cleanup assertion is not an auth failure.
- **A pre-existing `mcp.vercel.com` MCP server in `~/.codex/config.toml` fails
  auth** on every Codex run (`invalid_token`, no authorization provided). It is
  unrelated to this pilot and harmless, but it produces recurring stderr noise.

## Pilot hygiene

The gateway is stopped, port `18789` is free, no Windows service was installed,
and no channel was configured. The Soma repository was not used as an agent
workspace at any point. The Codex direct-route test used a config override and
persisted nothing.

### Preserved cleanup inventory

Nothing in this inventory has been deleted. Cleanup is blocked until this
closure record is reviewed and the owner explicitly approves removal.

| Scope | Exact target | Evidence at closure |
|---|---|---|
| Isolated profile state | `C:\Users\arash\.openclaw-somapilot\` | 7,602 files, 2,177,314,286 bytes; includes configuration, OAuth/auth state, logs, agent sessions, downloaded packages, and evidence |
| Downloaded Codex provider project | `C:\Users\arash\.openclaw-somapilot\npm\projects\openclaw-codex-8902d781d4\` | 2,199 files, 2,083,098,645 bytes; nested inside the isolated profile and contains `@openclaw/codex` |
| Pilot-created default-root state | `C:\Users\arash\.openclaw\` | 27 files, 39,785 bytes; contains `state\`, `tui\last-session.json`, and `workspace-somapilot\` |
| Global OpenClaw package | `C:\Users\arash\AppData\Roaming\npm\node_modules\openclaw\` | OpenClaw 2026.7.1; 31,999 files, 301,955,573 bytes |
| Global npm launchers | `C:\Users\arash\AppData\Roaming\npm\openclaw`, `openclaw.cmd`, and `openclaw.ps1` | all present at closure |

The downloaded Codex project is listed separately because it is the largest
pilot artifact and preserves the supply-chain evidence, even though removal of
the parent profile would also remove it.

The Node 24.18.0 installation is **not** an automatic cleanup target. Node is a
shared machine dependency, and reverting or removing it requires a separate
owner decision after checking other consumers. The pre-existing
`mcp.vercel.com` configuration is unrelated to this pilot and is also outside
cleanup scope.

## Stop conditions

None were triggered. The pilot stayed inside its boundaries, created no second
authority, and produced a decision. The tool-projection defect is recorded as an
OpenClaw portability limitation rather than a Soma defect, and nothing in Soma
was changed to accommodate it.

The decision is final for the current architecture catalogue: no further
OpenClaw version, Claude-backend, ACPX, voice, or channel testing is authorised.
`PILOT-SCOPE-1` and `PILOT-MEMORY-1` remain separate, inactive gates.
