# Automatic repository discovery

CodexBridge automatically discovers Git repositories that are siblings of an explicitly configured repository.

For example, when `config.yaml` already contains a repository under:

```text
D:/Github/Stream_Alpha
```

CodexBridge treats `D:/Github` as an approved discovery root. Creating and initializing:

```text
D:/Github/SeedMind/.git
```

makes the project available immediately as:

```text
seedmind
```

No CodexBridge restart or additional `config.yaml` entry is required.

Folder names are normalized to lowercase identifiers. Runs of punctuation, spaces, dots, and hyphens become `_`, so `AI-Voice-Lead-Agent` becomes `ai_voice_lead_agent`.

Discovery rules:

- Explicit `repos:` entries always take priority.
- Discovery runs only after an unknown `repo_name` is requested.
- Approved roots are inferred from the parent folders of explicit repositories.
- Only direct child directories are scanned by default.
- Only folders containing `.git` are included.
- Symlinks are ignored.
- `.fallow` and `secrets` are excluded by default.
- A discovered repository is cached in memory after successful validation.

Optional environment variables:

```text
CODEXBRIDGE_AUTO_DISCOVER_REPOS=0
CODEXBRIDGE_REPO_ROOTS=D:/Github;E:/Projects
CODEXBRIDGE_REPO_EXCLUDES=.fallow,secrets,archive
CODEXBRIDGE_REPO_MAX_DEPTH=1
```

`CODEXBRIDGE_REPO_ROOTS` adds discovery roots and is useful when the static repository map is empty. Separate multiple Windows paths with semicolons.
