# Repository knowledge system

Soma combines a generated repository wiki with persistent project memory.

Source-grounded external research is handled separately by the Soma research
platform described in [`SOMA_KNOWLEDGE_LAYER.md`](SOMA_KNOWLEDGE_LAYER.md).
Its raw archive and structured SQLite overlay are authoritative; this legacy
wiki/Markdown system is not a substitute for research provenance, claims, or
evidence.

## Knowledge hierarchy

1. **Live source code** is the current truth.
2. **Repository wiki** is a generated map of the current repository.
3. **Repository-scoped memory** stores decisions, validation history, and facts that cannot be inferred reliably from source.
4. **Global memory** stores deliberately shared preferences and cross-project policy.

The wiki is a cache. Critical claims must still be checked against live source before edits.

## Generated wiki

Each repository receives a local generated wiki under:

```text
.soma/wiki/
├── overview.md
├── architecture.md
├── modules.md
├── validation.md
└── manifest.json
```

The generator:

- indexes supported text and source files;
- skips `.git`, virtual environments, build outputs, caches, secrets, credentials, and known sensitive file formats;
- extracts Python classes, functions, docstrings, and imports;
- extracts JavaScript and TypeScript symbols and imports;
- detects project types, conventional entry points, important files, and likely validation commands;
- writes a Mermaid dependency map;
- records source hashes in `manifest.json`;
- returns `unchanged` when no indexed source hashes changed.

The first implementation regenerates the affected wiki pages as a group when any indexed source file changes. The manifest makes later section-level incremental refresh possible without changing the external contract.

## Memory scoping

All memory records remain in one SQLite database, but retrieval can be scoped by `repo_name` or `project_key`.

Repository-scoped searches do not return records from another repository. Shared global memories are included only when `include_global_memory=true` is requested explicitly.

Repository-scoped context assembly uses the target repository name, preventing unrelated project decisions from entering generated reports or inert handoff artifacts.

## MCP tools

### `knowledge_action` (`action: "refresh_wiki"`)

Generate or refresh the wiki for a whitelisted repository.

Inputs:

- `repo_name`
- `force` (optional)

### `knowledge_query` (`operation: "read_wiki"`)

Read one safe wiki page such as `overview.md` or `architecture.md`.

### `knowledge_query` (`operation: "search"`)

Search both the generated wiki and repository-scoped memory.

Inputs:

- `repo_name`
- `query`
- `limit`
- `include_global_memory` (optional, default `false`)

### `knowledge_action` (`action: "remember_decision"`)

Persist an accepted decision under one repository.

## Deployment

The knowledge gateways expose strict discriminated schemas. After pulling the implementation:

1. Run the relevant tests.
2. Restart the Soma server.
3. Refresh the Soma connector/action catalog in ChatGPT.

A full disconnect and reconnect is not normally required.
