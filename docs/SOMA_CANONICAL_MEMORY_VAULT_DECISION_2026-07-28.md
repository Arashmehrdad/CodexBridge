# SOMA-CANONICAL-MEMORY-VAULT-1 — Production Vault Root Decision

**Date:** 2026-07-28
**Status:** owner-decided, locally configured, and documentation-closed.
**Decision level:** C — canonical owner-data location and privacy boundary.
**Architecture:** [`SOMA_SHARED_MEMORY_ARCHITECTURE_DECISION_2026-07-28.md`](SOMA_SHARED_MEMORY_ARCHITECTURE_DECISION_2026-07-28.md)
**Implementation result:** [`MEMORY_INTEGRATION_FOUNDATION_1_RESULT_2026-07-28.md`](MEMORY_INTEGRATION_FOUNDATION_1_RESULT_2026-07-28.md)
**Machine-readable decision:** [`soma-canonical-memory-vault-decision-2026-07-28.json`](soma-canonical-memory-vault-decision-2026-07-28.json)

## Decision

The production canonical memory vault root is:

```text
D:\SomaMemory
```

The live ignored `config.yaml` is configured as:

```yaml
canonical_memory:
  canonical_vault_root: "D:/SomaMemory"
  canonical_vault_kind: "external_private_vault"
```

`CanonicalMemoryConfig.resolve_vault_root()` therefore resolves project memory to:

```text
D:\SomaMemory\projects\<project_id>
```

The root is intended to be opened directly as the owner-facing Obsidian vault; this decision does not alter Obsidian application configuration.

## Why this location

- It is outside `D:\Github\Soma`, every code repository, and `runs/`.
- It is not placed under a cloud-synchronised user folder by default.
- The short, space-free path is stable for Windows services and local tools.
- One root can hold project, later personal, and explicitly shared memory without making any code repository the owner of cross-project memory.
- The root may later become a private Git repository or use another private backup mechanism, but backup is not required for canonical correctness and is not activated by this decision.

## Local topology created

```text
D:\SomaMemory\
├── projects\
├── personal\
└── shared\
```

The directories are empty scaffolding. No owner memory, personal memory, legacy records, or synthetic pilot notes were copied into them.

## Authority and safety

- Owner-readable Markdown under this root is canonical.
- Soma owns identity, scope, lifecycle, provenance, integrity, health, and controller contracts.
- SQLite catalogs and provider indexes remain disposable projections outside canonical authority.
- Basic Memory semantic retrieval remains disabled because indexed membership cannot be proven through the accepted provider interface.
- Project memory continues to require exact active ProjectScope identity.
- Personal scope remains modelled but refused until a later owner-authorised lane.
- The vault root must never be silently inferred from the current repository, current working directory, active Obsidian vault, or provider defaults.

## Operational result

The production path exists locally, `config.yaml` points to it, and `soma-service.cmd validate-config` passed. No service restart, Obsidian application reconfiguration, owner-memory import, Git initialisation, cloud sync, deployment, or push is authorised by this decision.

## Next permitted lane

A bounded real-project trial may use the existing Soma project only after explicit owner authorisation. It may create a small reviewed set of canonical project memories and verify retrieval through fresh ChatGPT, Claude Code, and Hermes sessions. It may not activate personal scope, bulk-import legacy memory, enable unprovable semantic retrieval, or push.
