# Soma Fast Repository Search — F1 Contract and Baseline

Date: 2026-09-02
Owner instruction: implement a fast repository-wide lexical search path, plan-first, in small gates.
Current implementation gate: **F1 only — contract + baseline; no search implementation change.**

## 1. Problem statement

`repo_query(search_text)` is the evidence-grade repository text-search surface, but its current public path is unsuitable for fast repository navigation. Simple lexical questions such as “where is this symbol mentioned?” can spend seconds to tens of seconds walking and hashing repository material before matching text.

This is distinct from Research Map semantic navigation and from exact-file inspection.

Desired workflow:

```text
fast lexical search -> candidate paths/lines -> exact repo read -> reasoning
Research Map          -> semantic/conceptual navigation
```

Fast lexical search is navigation evidence only. Exact source must be reopened before substantive conclusions rely on it.

## 2. Root cause established in F1

The fast ripgrep implementation already exists in `soma/repo_reader.py` as `_search_with_ripgrep()`.

However, the public gateway path always supplies `response_budget_bytes` to `search_repo_text()`. The current dispatch condition is effectively:

```python
if file_path or cursor or response_budget_bytes is not None:
    return _search_repo_text_bounded(...)
```

Because the public `RepoSearchTextQuery.response_budget_bytes` always has a value, normal public calls always enter `_search_repo_text_bounded()` and do not reach `_search_with_ripgrep()`.

`_search_repo_text_bounded()` currently:

1. recursively walks the selected filesystem scope;
2. gathers candidate files;
3. binary-checks/stat-checks each candidate;
4. computes SHA-256 for every searchable candidate to construct a search snapshot;
5. only then scans lines for the requested literal.

The search deadline is established before this work, but the expensive candidate discovery/hash phase is not deadline-checked per file. Therefore a nominal search budget does not bound end-to-end latency.

## 3. Baseline evidence

Baseline machine/repository state at F1:

- repository: `D:\Github\Soma`
- branch: `rollback/pre-core-hardening-20260823`
- HEAD at baseline: `a5b4040f36b15d2852a95df6fa8e31b09d7b9902`
- tracked files: **867**
- tracked bytes: approximately **13.4 MB**

### 3.1 Direct tracked lexical baseline

Seven-run `git grep -F -I -n` measurements over the tracked repository:

| Query class | Query | Median |
|---|---|---:|
| ordinary symbol | `continuation_query` | **38.74 ms** |
| no match | `definitely_no_match_9f3b1c7d` | **40.36 ms** |
| common gateway symbol | `repo_query` | **43.58 ms** |

These results prove that the repository itself is not inherently expensive to search.

### 3.2 Current public path

Observed current `repo_query(search_text)` behavior:

- `directory="soma"`, Python-filtered lexical searches: approximately **0.98–1.11 s**;
- `directory="tests"`, `file_patterns=["*.py"]`, query `search_repo_text`: **5.047 s**, `search_timeout`, zero hits returned, after pre-scanning **229 files**;
- prior live repository-wide audit searches on this same implementation reached tens of seconds because the snapshot walk/hash dominates before useful matching.

The key acceptance gap is therefore end-to-end search-path design, not Git/NTFS lexical-search capability.

## 4. F2/F3 request contract

The existing public MCP tool name remains `repo_query`. No new top-level tool is introduced.

Add an explicit fast lexical operation rather than silently changing the semantics of the existing evidence-grade `search_text` operation:

```text
operation = "search_fast"
```

Initial request fields:

```text
repo_name          required
query              required
scope              tracked | working_tree | directory | all
match_mode         literal | regex
case_sensitive     bool
directory          optional bounded subtree
file_patterns      optional bounded glob list
max_results        bounded
context_lines      0..5
result_mode        matches | files | count
budget_ms          hard end-to-end subprocess/search budget
response_budget_bytes bounded
```

Defaults:

```text
scope = tracked
match_mode = literal
case_sensitive = false
max_results = 100
context_lines = 0
result_mode = matches
```

`scope=all` must never be selected implicitly.

## 5. Engine contract

### 5.1 `scope=tracked` — primary optimized path

Primary engine: `git grep` over tracked files.

Requirements:

- no Python recursive filesystem walk;
- no pre-search SHA-256 of every file;
- literal search is the primary optimized case;
- regex uses Git grep regex semantics only if explicitly requested;
- no mutation and no Git index/worktree change.

### 5.2 Working-tree/untracked path

Primary engine: `rg`.

This is F3, not F2.

It must use explicit bounded exclusions for generated/heavy roots and a hard subprocess timeout. `scope=all` is opt-in only.

## 6. Response contract

Each match result must contain enough provenance for an exact follow-up read:

```text
path
line
column, when mechanically available
snippet
optional bounded context
```

Response-level metadata:

```text
ok
status
repo_name
query
scope
match_mode
case_sensitive
engine
git_head
match_count
files_matched
duration_ms
truncated
has_more / continuation metadata if needed
response_bytes
```

The response must explicitly declare that results are navigation evidence and should be reopened through exact repository read before source-dependent conclusions.

## 7. Safety and architecture invariants

The fast-search implementation must not alter:

- MCP server lifecycle or readiness;
- tool registration timing;
- tunnel/networking;
- server/capability identity except the normal schema hash change caused by an additive gateway operation;
- continuation semantics;
- Research Map behavior;
- Run/Task authority;
- repository files or Git state during a query.

There is no semantic router, no automatic next-action logic, and no model call in this path.

## 8. Performance acceptance

For `scope=tracked` on a Soma-sized repository:

```text
p50 <= 100 ms
p95 <= 500 ms
```

The acceptance suite must include:

1. common literal symbol;
2. rare literal symbol;
3. no-match literal;
4. case-insensitive literal;
5. explicit regex;
6. directory restriction;
7. max-result truncation.

End-to-end latency must be bounded by the selected searchable corpus and must not scale with ignored/untracked `runs/`, datasets, artifacts, caches, or generated output when `scope=tracked`.

## 9. Correctness acceptance

At minimum:

- literal result parity with direct `git grep`;
- regex parity for the declared regex mode;
- case behavior is deterministic;
- tracked scope excludes untracked/generated data;
- F3 working-tree scope includes an intentional untracked fixture;
- directory restriction cannot escape repository root;
- safe glob handling;
- deterministic ordering;
- bounded output/truncation;
- hard timeout behavior;
- spaces and Unicode paths;
- clear behavior for non-Git repositories;
- dirty worktree remains unchanged;
- returned HEAD is current;
- existing `repo_query` operations remain backward compatible.

## 10. Gate sequence

### F1 — contract + baseline

- establish root cause;
- capture baseline;
- freeze request/response/performance/safety contract;
- no search implementation change.

### F2 — tracked fast search

- add `repo_query(operation="search_fast")`;
- implement `scope=tracked` literal + explicit regex with Git-native search;
- add focused unit/gateway tests;
- benchmark against F1 baseline;
- stop before working-tree search.

### F3 — bounded working-tree search

- add `rg` working-tree/directory/all scopes;
- explicit heavy-root policy and hard timeout;
- add untracked-fixture and exclusion tests.

### F4 — integration/acceptance

- backward-compatibility audit;
- public schema/inventory tests;
- performance acceptance;
- architecture audit;
- local commit and exact evidence seal.

## 11. F1 decision

F1 concludes that a dedicated additive `search_fast` operation is justified. The existing `search_text` behavior is retained for compatibility and evidence-grade snapshot/cursor semantics; F2 must not silently repurpose it.

**F1 stop boundary:** no source implementation is authorized by this document itself. F2 begins only under the owner instruction that opened this fast-search programme and after this F1 contract is committed/accepted.
