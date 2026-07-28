# PILOT-OBSIDIAN-MCP-1 — Preflight and Source Freeze

**Date:** 2026-07-28
**Status:** execution triggered and started; **halted on one bounded blocker** before the first provider operation.
**Gate:** [`PILOT_OBSIDIAN_MCP_1_GATE_2026-07-28.md`](PILOT_OBSIDIAN_MCP_1_GATE_2026-07-28.md)
**Outcome:** **none declared.** No provider behavior was observed, so none of the four outcomes is evidenced.

Machine-readable record: [`pilot-obsidian-mcp-1-preflight-2026-07-28.json`](pilot-obsidian-mcp-1-preflight-2026-07-28.json)

## Repository preflight — pass

| Item | Observed |
|---|---|
| repo root | `D:\Github\Soma` |
| HEAD | `cd6d90436baf1fff65eedabee3ae8f8d0686efde` |
| worktree | clean |
| running / queued runs | 0 / 0 |
| locks | 0 |
| capability epoch | `1632dc6ed895-42bdb69d96fb` |
| `runs/pilots/` | exists, empty |
| push | not performed (5 commits remain unpushed) |

No parallel Basic Memory or Codebase Memory pilot is running. One controller, no coding agents, no subagents.

## Source integrity freeze — pass

Frozen before any install step, as the gate requires.

| Item | Value |
|---|---|
| plugin id | `mcp-tools-istefox` |
| repository | `istefox/obsidian-mcp-connector` |
| release | **0.28.1**, published 2026-07-22T20:13:10Z |
| license | MIT |
| manifest `minAppVersion` | 1.7.2 |
| `isDesktopOnly` | true |

Published SHA-256 digests:

```text
main.js        4be75215e84f94944f1887e69171f4455a5745c04b69d8a2d749151e142bcae8  (2,591,536 B)
manifest.json  5b8484320f27027eec9f14bee0ada6b024ed28896bf9e3909fb0810f165f47fc  (389 B)
*.mcpb         ebe7536656c9be6d8f08dd3194866573079d323f3559ec6974e5b7247d6de46c  (3,577 B)
```

The release **matches the gate's reviewed version exactly**. The plugin is listed in the
official community store (`obsidianmd/obsidian-releases`, 6,116 entries), so BRAT is not
required and that stop condition does not fire.

Two facts recorded rather than glossed:

- the store listing states the plugin **has not been manually reviewed by Obsidian staff**;
- the release ships an `.mcpb` auto-client-configuration bundle, which this gate forbids. It
  was neither downloaded nor used.

No artifact was downloaded. Digests were read from the release metadata.

## Bounded blocker — Obsidian is not installed

Gate boundary 1 requires inventorying the installed stable Obsidian version before any change.
There is no installed version to inventory.

Searched and absent: `%LOCALAPPDATA%`, `%PROGRAMFILES%`, `%PROGRAMFILES(X86)%`, HKLM and HKCU
uninstall keys, PATH, `%APPDATA%\obsidian`, a depth-4 `Obsidian.exe` scan of `C:\Users\arash`
and `D:\`, and a depth-3 `.obsidian` vault scan of `D:\`. No vault exists on the host. No
`winget`, `scoop`, or `choco` is available either.

MCP Connector runs **in-process inside Obsidian**. Without the application there is no
endpoint, no `tools/list`, no vault binding and no retrieval, so every required check group is
blocked — transport and authentication, Windows reliability, structured access, retrieval and
provenance, the write phase, and rebuild/removal.

### Why the controller did not resolve this itself

1. Installing the Obsidian desktop application is a **global, non-disposable host change**. No
   gate boundary authorizes it; the gate confines pilot state to disposable roots under
   `runs/pilots/obsidian-mcp-1/` and treats installer-driven global configuration changes as a
   stop condition.
2. The gate mandates the **official Obsidian CLI**, which shipped in desktop **v1.12.0**. So the
   real floor is 1.12.0, not the manifest's 1.7.2.
3. Community-store installation and provider configuration — Core tool profile, bearer token,
   fixed loopback port — are **desktop GUI operations** requiring owner interaction.
4. Dropping plugin files into `.obsidian/plugins/` is a **sideload**; the gate treats
   non-community-store installation as a stop for owner review.

This is one bounded blocker, which the gate anticipates. It is not a `reject_*` result: nothing
about MCP Connector failed.

## Boundaries preserved

Nothing was installed, downloaded, enabled or created. No vault exists. Live ProjectScope, Soma
stores, `.soma/wiki/`, Hermes memory, MCP schemas and repository source files are untouched. No
bearer token exists to record. Not pushed.

The gate document itself was left unmodified, including its `execution_started` field, so the
owner's own verification script continues to pass unchanged.

## Resume path

Install official stable Obsidian **1.12.0 or later** from `https://obsidian.md`, then reissue
the execution instruction. No gate parameter changes. Execution resumes at host inventory and
proceeds through vault creation, the 16–24 note bilingual set, Phase A read-only checks, and
onward.
