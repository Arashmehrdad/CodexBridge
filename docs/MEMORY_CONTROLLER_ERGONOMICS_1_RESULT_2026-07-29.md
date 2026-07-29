# MEMORY-CONTROLLER-ERGONOMICS-1 — Result

**Date:** 2026-07-29
**Status:** executed. Two additive changes, verified live.
**Authorisation:** owner instruction in session. **This lane had no prior
decision document** — unlike every earlier memory lane, its scope was chosen at
start time rather than fixed in advance. That is recorded here as the deviation
it is; see §Scope, and how it was bounded.
**Follows:** [`MEMORY_REAL_PROJECT_TRIAL_1_RESULT_2026-07-28.md`](MEMORY_REAL_PROJECT_TRIAL_1_RESULT_2026-07-28.md) (closed)
**Branch:** `lane/memory-integration-foundation-1`

## Scope

Chosen from the friction the closed trial actually measured, deliberately
excluding the tempting item:

| Friction | In lane? |
|---|---|
| Scope must be known in advance | **yes** |
| `memory_save` demands a path per write | **yes** |
| Retrieval answers keywords, not questions | **no** — see below |

Making lexical retrieval survive natural-language phrasing means stopword
handling and ranking, which is the custom retrieval engine the architecture
forbids. It was declined during the trial for that reason and is declined again
here. Nothing in this lane touches retrieval behaviour.

## Change 1 — `memory_scope` discovery

Every memory operation needs an opaque `project_id`. The only ways to obtain
one were to already know it or to read it out of a decision document, so a
fresh controller could reach the gateway and still be unable to address its own
project.

`knowledge_query(operation="memory_scope", repo_name=...)` resolves the binding
through ProjectScope and returns the scope object ready to send back verbatim,
with canonical health and the vault root.

**The limit that makes this safe: discovery returns a scope, it does not become
one.** `MemoryScopeInput` still requires the scope named exactly on every call.
Accepting `repo_name` alone at call time would reintroduce precisely what
[`SOMA_CANONICAL_MEMORY_VAULT_DECISION`](SOMA_CANONICAL_MEMORY_VAULT_DECISION_2026-07-28.md)
forbids — a memory operation quietly deciding which project it addressed, and a
vault root inferred from ambient context. Discovery stays a separate, visible
step, and a test asserts a call without `scope` is still refused.

## Change 2 — derived `vault_path`

`vault_path` was the one thing every caller had to invent per write. It is now
derived from `kind` and `title` when omitted: `lessons/counts-are-not-membership.md`.

Four properties, each deliberate:

- **deterministic** — the same note always resolves to the same path;
- **explicit wins** — a caller-supplied path is never overridden, because the
  owner's own filing of their vault outranks a generated name;
- **refuses rather than invents** — a title with no usable ASCII stem is
  rejected; a placeholder name would put an unfindable record in the vault;
- **always echoed** — the resolved path is in every acknowledgement and is on
  the projection keep-list, so a budget squeeze can never drop the one field
  telling a caller where its own record landed.

The slug ASCII-folds accented Latin titles and truncates on a word boundary
rather than mid-word. A title with no usable ASCII stem—including a
Persian-only title—is refused unless the caller supplies `vault_path`
explicitly.

## Verified live

Against the real vault on the restarted build:

| Check | Result |
|---|---|
| `memory_scope repo_name="soma"` | returns the exact scope, `healthy`, 9 records, real vault root |
| save with **no** `vault_path` | landed at `decisions/controllers-discover-memory-scope-they-never-have-it-inferred.md`, echoed in the acknowledgement |
| health after that write | `healthy`, 10/10, **0 drifted** |

The zero drift also confirms the trailing-newline fix from the trial holds on a
fresh real write, which was previously only proven on repaired records.

Full suite: 2252 passed, 35 skipped.

## Boundaries

Additive only. No retrieval change, no schema removal, no personal scope, no
legacy import, no semantic activation, no change to how the vault root is
configured. Existing callers that pass `vault_path` and a full `scope` are
unaffected.

## Operational connector note

The restarted Soma server and fresh MCP discovery exposed `memory_scope`, while
an already-open ChatGPT connector session initially retained the previous
`knowledge_query` schema. The separate
[`MEMORY-CONNECTOR-REFRESH-VERIFY-1`](MEMORY_CONNECTOR_REFRESH_VERIFY_1_RESULT_2026-07-29.md)
gate proved this was stale client discovery: after refresh, ChatGPT discovered
`memory_scope`, returned the exact explicit scope, reused it successfully for
healthy 10/10 memory, and still refused an unscoped call.

The earlier cross-controller trial remains closed: Claude Code, ChatGPT, and
Hermes were already verified end to end for the pre-existing memory flow. This
lane and its successor verification do not reopen those completed results.

## Still open

- Semantic retrieval stays disabled until index membership can be proven.
- Natural-language retrieval remains out of reach by design.
