# Soma Research Map

Status: production-ready v1

Soma Research Map is a repository-scoped carry-forward layer for reviewed research conclusions. It is navigation and retrieval infrastructure, not scientific authority and not a semantic reasoning controller.

## Authority model

The project research thread owns:

- which research documents are authoritative;
- whether a conclusion is materially useful for future work;
- relation wording and epistemic class;
- lifecycle and supersession decisions;
- whether a reviewed document is material or reviewed-no-material.

Soma owns only the mechanical layer:

- portable manifest validation;
- sidecar schema validation;
- deterministic relation identities;
- source hashing and exact-anchor verification;
- coverage and desired-state computation;
- immutable publication/sync/rebuild;
- read-only semantic retrieval;
- derived Graphiti/FalkorDB projection health.

Soma does not automatically generate scientific relations, choose materiality, reinterpret research, or infer next actions.

## Repository layout

A mapped repository has three distinct layers:

```text
tracked research Markdown
tracked _soma_map sidecars
ignored .soma/research-map runtime
```

The authoritative scientific source is always the tracked Markdown.

Tracked sidecars preserve reviewed carry-forward semantics. `.soma/research-map/` is local generated runtime and must remain Git-ignored. Graphiti/FalkorDB is a disposable, rebuildable projection of the tracked manifest and sidecars.

## Project scope

Research Map operations require the repository's exact ProjectScope identity.

Resolve it explicitly with:

```text
knowledge_query(operation="memory_scope", repo_name="...")
```

This returns the canonical opaque `project_id`. Scope discovery is separate from Research Map operations so a call never silently guesses which project it addresses.

## Portable manifest

Adoption creates or attaches the repository's `soma.project.json` contract. The manifest carries a stable repository identity and Research Map roots.

Conceptually:

```json
{
  "schema": "soma.project.v1",
  "repository_uid": "srepo_...",
  "research_map": {
    "enabled": true,
    "schema": "soma.research-map.v2",
    "roots": [
      {
        "path": "docs/research",
        "sidecar_dir": "_soma_map",
        "include": ["*.md"]
      }
    ]
  }
}
```

A clone preserves the tracked `repository_uid` and sidecars. Local ProjectScope identity and `.soma/research-map/` runtime are not portable source authority.

Repository discovery alone never auto-adopts a map.

## Sidecar v2

For an adopted repository, call:

```text
research_map_query(operation="authoring_contract", ...)
```

The response is the live mechanical contract for that repository, including:

- exact `soma.research-map.v2` JSON schema;
- configured research roots;
- sidecar placement rule;
- canonical source-hash rule;
- predicate registry;
- deterministic relation identity fields;
- the project/Soma authoring boundary.

A reviewed sidecar contains:

```text
schema_version
source.path
source.canonical_text_sha256
review.state
review.controller
review.materiality
facets
relations[]
```

A material relation carries at least:

```text
relation_id
subject {key,label}
predicate
object {key,label}
statement
locator.anchor
epistemic_class
lifecycle
```

A document with no durable carry-forward semantics is represented honestly as reviewed-no-material: reviewed state, materiality `none`, and no invented relations.

## Source hashing

`source.canonical_text_sha256` is SHA-256 over strict UTF-8 text after normalizing CRLF and CR line endings to LF. This prevents clone/checkout newline differences from creating false semantic drift.

Search results are verified against the current source hash and exact source anchor before they are returned.

## Deterministic relation IDs

Do not reproduce the relation-ID algorithm in project code or search Soma source.

Use:

```text
research_map_query(
  operation="relation_id",
  project_id="...",
  repo_name="...",
  source_path="...",
  subject_key="...",
  predicate="...",
  object_key="..."
)
```

Identity is derived from normalized repository-relative source path, subject key, registered predicate, and object key. Statement wording, labels, and anchor text are not relation identity fields, so semantic drift is detected separately by desired-state hashing.

## Public query gateway

`research_map_query` is read-only and exposes:

- `health` — adoption, manifest, coverage, publication and backend state;
- `coverage` — reviewed/unreviewed/stale/missing/deferred source coverage;
- `relation` — one exact reviewed relation;
- `search` — verified semantic retrieval from the published generation;
- `authoring_contract` — live sidecar/identity authoring contract;
- `relation_id` — canonical deterministic relation-ID generation.

Query operations never sync, rebuild, create sidecars, or choose materiality.

## Public action gateway

`research_map_action` exposes explicit mutations only:

- `adopt` — attach/create the portable manifest and local ignored runtime;
- `sync` — publish the current complete reviewed desired state;
- `rebuild` — deterministically rebuild the derived projection from tracked source.

Sync and rebuild publish only reopen-verified immutable generations. The currently published generation is never repaired in place.

## Normal project workflow

After every completed research iteration:

```text
1. save authoritative research Markdown first
2. project controller decides materiality
3. create/update the reviewed sidecar using authoring_contract + relation_id
4. use reviewed-no-material when appropriate
5. check Research Map health/coverage
6. explicitly sync
7. verify published_verified or already_current
8. update normal project continuation/wiki finishing touches
```

Projects should persist this workflow in their own `AGENTS.md` so future research iterations keep the map current.

Historical backfill is project-owned. Prefer the current frontier and high-value lineage first, then bounded batches. Coverage must remain truthfully partial until eligible sources have actually been reviewed.

## Search trust rule

A retrieved relation is candidate navigation context only.

Before a retrieved prior result materially changes a new scientific conclusion, design, falsification, or next experiment, reopen the exact authoritative Markdown and verify the returned source path/hash/anchor.

Do not treat rank 1 as an automatic scientific answer.

## Backend model

The production projection uses project-isolated Graphiti/FalkorDB with local FastEmbed embeddings. The reviewed Research Map path deliberately provides a `NoLLM` Graphiti client; Graphiti LLM extraction is forbidden.

The backend is optional derived infrastructure. Core Soma must continue to start and function when Research Map backend dependencies are absent.

Falkor query execution uses a Soma-owned bounded per-query timeout rather than inheriting an arbitrary server default, so scale behavior remains deterministic.

## Failure and recovery

If tracked source/sidecars are valid but the backend is absent or damaged:

- do not rewrite scientific Markdown;
- do not invent replacement semantic relations;
- keep the project-side source authoritative;
- rebuild the derived projection explicitly when appropriate.

If a sidecar becomes stale because its source changed, update/review that sidecar from the new authoritative source before publication.

If a project discovers an engine defect, preserve the scientific record and hand the smallest reproducible engine failure to the Soma implementation lane. The Soma lane may use read-only evidence or disposable clones, but does not take ownership of project scientific curation.

## Legacy boundary

The old RAGFlow research/context-packet service has been retired. New Research Map traffic must not route through `soma.research.v1` or revive RAGFlow.

There is no global all-project research graph in v1. Each repository has an independent identity and independently rebuildable Research Map.
