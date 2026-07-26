# PILOT-OPENCLAW-1 — External Shell Boundary

**Date:** 2026-07-27
**Status:** Decided.
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

## Decision

> **OpenClaw is not adopted as a tool router. Controllers connect to Soma's MCP
> endpoint directly. OpenClaw remains a candidate for presentation and channels
> only, and is not adopted in that role by this pilot either — it was not
> measured for it.**

This is not a workaround. It is what the accepted authority rule already
required:

> OpenClaw may retain only the exact Soma identifier and a projection.

A shell that routes tools is on the path of every capability call, and the
measured consequence was exactly the failure mode the rule exists to prevent:
Soma became reachable only through one vendor's catalog. Removing the shell from
the tool path removes the coupling entirely, and costs nothing, because the
direct route already works for both controllers.

## What this means for the shell question

The Cortana ambition is unaffected. It simply separates into two independent
questions that were previously conflated:

1. **How do controllers reach Soma's capabilities?** Answered: directly over
   MCP. Neutral, measured, working today for two different vendors.
2. **What provides voice, channels, and presence?** Still open. OpenClaw remains
   the leading candidate, but as a presentation surface that talks to a
   controller — not as something Soma's capability calls pass through.

Question 2 was not tested here and should not be inferred as answered.

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
correctness invariant rather than a convenience. Any future OpenClaw work must
verify the isolation boundary empirically rather than trusting the flag, and
removing a pilot cleanly means deleting two directories, not one.

## Secondary findings

- **OAuth installed `@openclaw/codex` with an unpinned npm install record.** A
  pinned shell that pulls an unpinned dependency during authentication is not
  fully pinned. Worth checking before any future OpenClaw work.
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
and no channel was configured. Removing the pilot requires deleting **both**
`~/.openclaw-somapilot/` and `~/.openclaw/` per Finding 4; neither touches Soma
state. Both are left in place pending the owner's decision. The Soma repository was not used as an
agent workspace at any point. The Codex direct-route test used a config override
and persisted nothing.

## Stop conditions

None were triggered. The pilot stayed inside its boundaries, created no second
authority, and produced a decision. The tool-projection defect is recorded as an
OpenClaw portability limitation rather than a Soma defect, and nothing in Soma
was changed to accommodate it.
