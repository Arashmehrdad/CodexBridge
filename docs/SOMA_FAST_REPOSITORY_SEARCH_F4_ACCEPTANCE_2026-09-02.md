# Soma Fast Repository Search — F4 Acceptance

Date: 2026-09-02
Branch: `rollback/pre-core-hardening-20260823`

## 1. Accepted implementation chain

- F1 contract/baseline: `c30487e778490f66795d911ff6706ec7b7620601`
- F2 tracked fast search: `3c137120d74f0bf650ad7b34cba5da0c0490c8b1`
- F3 bounded working-tree search + F4 integration: `dc1d52b6040a280242c96e6427580209f6faf6a0`

The public surface remains the existing `repo_query` gateway with additive operation `search_fast`; no new top-level MCP tool was introduced.

## 2. Root cause and preserved compatibility

The original `repo_query(search_text)` remains unchanged as the evidence-grade snapshot/hash-bound search path. Its public request always carries a response budget, which selects the bounded snapshot implementation and can spend substantial time recursively discovering and hashing the candidate corpus before matching.

F1 measured direct tracked Git search at roughly 39-44 ms median while the old public path ranged from about one second to multi-second timeouts. During F4, a trivial repo-wide old-path lookup for `gateway-operations.v31` reproduced the problem at 62.547 seconds before timeout.

`search_fast` is deliberately separate so the old evidence semantics remain backward compatible.

## 3. Accepted scope semantics

### `scope=tracked` — default

- engine: Git grep
- searches Git-tracked working-tree content
- literal matching by default; regex only when explicit
- no recursive Python filesystem walk
- no corpus SHA-256 pre-scan
- no mutation of Git/index/worktree

### `scope=working_tree` — explicit

- engine: ripgrep
- tracked plus ordinary untracked working-tree files
- honors repository ignore rules
- excludes Soma-blocked/secret/generated/heavy roots

### `scope=directory` — explicit

- engine: ripgrep
- requires a validated repository-relative directory
- can inspect an explicitly selected ignored safe subtree
- cannot escape the repository root or enter Soma-blocked secret paths

### `scope=all` — explicit opt-in only

- engine: ripgrep with ignore rules disabled and hidden files considered
- still enforces hard blocked/secret/generated/heavy-root exclusions
- never selected implicitly

All fast-search results are navigation evidence only. Exact source must be reopened through repository read before source-dependent conclusions.

## 4. Ripgrep availability contract

F3 found that `rg.exe` exists on the machine but is not present on the Soma service process PATH. The implementation therefore does not require a global PATH mutation or copy a binary.

Discovery is bounded and deterministic:

1. existing process PATH via `shutil.which("rg")`;
2. known VS Code / VS Code Insiders ripgrep locations under `LOCALAPPDATA` and Program Files.

The live machine resolved the VS Code bundled ripgrep executable successfully. Missing ripgrep returns structured `rg_unavailable` rather than falling back to a slow recursive Python walk.

## 5. Safety and resource bounds

The fast path retains:

- hard end-to-end subprocess timeout;
- maximum result count;
- maximum serialized response bytes;
- maximum file size;
- bounded context lines;
- safe glob validation;
- deterministic ordering;
- redacted snippets;
- no symlink-following added;
- blocked secret/environment paths;
- explicit heavy-root exclusions for broad ripgrep scopes.

No semantic router, model call, automatic next-action logic, or hidden reasoning component exists in the search path.

## 6. Validation evidence

Focused F3 suite:

```text
20 passed in 9.37s
```

F4 integration suite (`-n 12`) across fast-search, full repository-reader, gateway-model, and CF1 inventory tests:

```text
203 passed in 182.74s (0:03:02)
```

Additional gates:

- new fast-search test file Ruff: PASS
- dependency integrity (`pip check`): PASS
- changed Python compilation: PASS
- `git diff --check`: PASS
- final F3/F4 pre-commit worktree/lock/run audit: PASS

## 7. Final performance acceptance

Seven-run source-level matrix on the Soma repository after F3/F4:

| Case | Engine | p50 | p95/max |
|---|---|---:|---:|
| tracked common symbol | git-grep | 31 ms | 47 ms |
| tracked rare symbol | git-grep | 47 ms | 63 ms |
| tracked no-match | git-grep | 46 ms | 47 ms |
| tracked case-insensitive | git-grep | 47 ms | 47 ms |
| tracked regex | git-grep | 62 ms | 63 ms |
| tracked directory | git-grep | 46 ms | 47 ms |
| tracked truncation | git-grep | 47 ms | 63 ms |
| working tree | ripgrep | 109 ms | 110 ms |
| explicit directory | ripgrep | 62 ms | 63 ms |
| explicit all | ripgrep | 250 ms | 297 ms |

Frozen F1 tracked target was `p50 <= 100 ms`, `p95 <= 500 ms`. Every tracked case passes with large margin.

## 8. Architecture audit

F3/F4 changed only:

- `soma/repo_reader.py`
- `soma/gateway_models.py`
- `soma/cf1_gateway_operation_inventory.py`
- `tests/test_repo_search_fast.py`
- `tests/test_cf1_gateway_operation_inventory.py`

F2 had already added the minimal `server.py` dispatch for `search_fast` in commit `3c137120...`.

The programme did not change MCP startup/reconciliation, transport, tunnel/networking, server readiness, continuation semantics, Research Map, Task/Run authority, Docker, or service management.

## 9. Activation boundary

Source implementation is accepted, but the currently running Soma MCP process intentionally has not been restarted during this work. The live process therefore still serves its previously loaded build/schema while disk source contains the accepted `search_fast` implementation.

This activation is deliberately deferred because recent evidence showed ChatGPT/OpenAI MCP thread/session state can behave badly around Soma restart/capability transitions. Before activation, durable continuation must be checkpointed. After activation, verify:

1. Soma restart/reload completes cleanly;
2. `capability_identity` converges;
3. connector/tool discovery exposes `repo_query(search_fast)` correctly;
4. a read-only tracked fast-search smoke succeeds;
5. existing ChatGPT thread/session remains attached rather than falling back to normal chat.

No restart is part of this acceptance record.
