# Soma Hybrid Research Map — Canonical Implementation Plan

Date: 2026-08-24  
Status: ACTIVE IMPLEMENTATION AUTHORITY — RM0–RM8 ACCEPTED; RM9 NEXT
Repository: `D:\Github\Soma`  
Planning branch observed: `rollback/pre-core-hardening-20260823`  
Planning HEAD observed: `7e7450e08331aeed744867be955feb42149b18f4`  
Research authority: Iterations 01–12 under `docs/soma-knowledge-carry-forward-research/`  

## 1. Purpose

This plan converts the completed long-horizon research-context programme into a bounded production implementation programme.

The target is not a second memory authority, not an automatic scientific planner, and not a replacement for repository research reports.

The target is:

```text
repository research Markdown
        = authoritative scientific truth

Sol / ChatGPT
        = semantic understanding and adjudication

tracked reviewed sidecars
        = durable, rebuildable semantic projection

Soma
        = project scope, validation, health, explicit sync, safe retrieval

Graphiti + local embeddings
        = optional/disposable semantic retrieval index

repo-local .soma/research-map/
        = local derived runtime only
```

The owner’s intended workflow is:

```text
FIRST ADOPTION OF A RESEARCH PROJECT

explicit research-map adoption
→ configure research roots
→ review/backfill existing research in bounded batches
→ create tracked sidecars
→ build one local project index
→ verify coverage + sync independently

THEN AFTER EACH NEW RESEARCH ITERATION

save authoritative research report
→ Sol adjudicates material carry-forward meaning
→ create/update that report's tracked sidecar
→ explicitly sync the local research-map generation
→ verify read-back
```

The first bootstrap may be large. Normal post-research maintenance should be incremental and small.

---

# 2. Research authority and supersession

The implementation must follow the later research conclusions where they refine earlier ones.

Primary architectural authority:

```text
Iteration 09
  minimum hybrid scientific contract
  reviewed sidecars + disposable Graphiti

Iteration 10
  Axon multi-programme stress audit
  source-path identity, facets, epistemic class, qualifiers,
  composite authority, cross-project references

Iteration 11
  repo-local .soma runtime, portable soma.project.json,
  attach/adoption lifecycle, namespace and wiki exclusions

Iteration 12
  Axon deployment/persistence/crash pilot
  canonical UTF-8/LF source hashes, explicit FalkorDB SAVE,
  desired-state drift, primitive backend projection,
  crash detection and deterministic rebuild
```

Important corrections frozen by Iteration 12:

```text
DO NOT use raw filesystem SHA-256 as portable Markdown identity.
USE canonical UTF-8 text with CRLF/CR normalized to LF before SHA-256.

DO NOT assume FalkorDB Lite driver.close() persists.
USE explicit persistence + verified SAVE success.

DO NOT flatten the durable sidecar schema to match FalkorDB property limits.
PROJECT structured data through an adapter.
```

Historical Iterations 01–08 remain evidence and problem history. They do not override Iterations 09–12.

---

# 3. Non-negotiable architecture laws

## 3.1 Repository research documents remain authoritative

No graph edge, database row, sidecar field, embedding, rank, lifecycle timestamp, or Graphiti invalidation may replace the scientific report.

A retrieved relation is a navigation/context candidate. Sol must reopen the exact source document before materially relying on it.

## 3.2 Sol is the semantic adjudicator

Soma must not automatically decide:

```text
which scientific finding is true
what a failed experiment means
whether one mechanism supersedes another
whether a result transfers across datasets
whether a hypothesis became an observation
which next research action should happen
```

Sol performs that reasoning and writes the reviewed semantic sidecar.

## 3.3 No hidden semantic router or second reasoning model

Do not add:

```text
automatic research planner
next-action engine
semantic routing model
Graphiti LLM extraction path
Graphiti contradiction adjudication as truth
provider-native subagent path
```


## 3.4 Continuation remains unchanged

Continuation answers:

```text
where are we now?
how do we re-enter the current work?
```

Research map answers:

```text
what older scientific context may still govern this question?
```

Do not put historical research-map state into continuation.

## 3.5 Graph/index failure cannot destroy research knowledge

Deleting all of:

```text
.soma/research-map/
```

must not delete scientific meaning required to rebuild the map.

Tracked reports + reviewed sidecars must be sufficient for deterministic rebuild without another semantic reinterpretation pass.

## 3.6 Query operations are read-only

No research-map query may:

```text
create a packet
write a query record
update Graphiti
repair a stale index
advance CURRENT
rewrite a sidecar
invalidate a relation
```

The old `search_research` query-side context-packet mutation must not be reproduced.

## 3.7 Coverage and synchronization are separate truths

A project may legitimately be:

```text
sync_current = true
coverage_complete = false
```

Do not report a partial historical backfill as full scientific coverage merely because every reviewed sidecar is indexed.

---

# 4. Current repository baseline and implementation seams

Planning source identities at HEAD `7e7450e08331aeed744867be955feb42149b18f4` include:

```text
soma/repo_reader.py
  ea5fadd6380470140120b9049a8911c8b21699d77adb3c47b1015727e17dc03c

soma/repo_writer.py
  734f6f579ae6b3cefbcaafe4903921871db20196595898856c9fffc6a357f59d

soma/repo_wiki.py
  02df88b7381ff4cb782fd71989c3522195621eab7302bda95846125e95cc2d8b

soma/tool_owned_paths.py
  5790e18498ac43ab319cce86ed25697d78541ddcbd7659ffd7f67ab01aeb65de

soma/project_scope/models.py
  36b10e47ac1672a2009da5e1c2cadebd746c5735a17f21ee8f05872bf1b5d2a1

soma/gateway_models.py
  86304cc3cb453fd06ca6afcd9014f175cfc3695f21dd32c6629462fed961ec8a

soma/knowledge_tools_integration.py
  c26c5ab887a6956a2dd53f60083015e719f68aebce70bb8473c9584dc23cb0b9

soma/public_tool_metadata.py
  fb47c65f67c477c8f2b8cf48cf372c015ea6d9c2a1d3a398714bfb181e7caf08

soma/public_gateway_inventory.py
  9fbe8e2a5d1a599170830bc21e9077c71d42aa2e81c459fb1a64d2821d4cd7e8

soma/cf1_gateway_operation_inventory.py
  e31e952350a696e0e295322e62f6dcf0d278cfe6a6170efceea3924d606d3ff2

soma/server.py
  d524cd2786d96fe671cf4c90ed42b58917704af265efda5da9ab33fcf81c62d1

pyproject.toml
  5ac61bde08905fe815535c92c00691a3bd51b09408d49d5ad9bcc87492825ab3
```

These are planning drift anchors only. RM0 must re-read current source before implementation.

Current worktree at planning time also contains unrelated intended owner work:

```text
AGENTS.md modified
Iterations 01–12 untracked
```

No implementation stage may reset, clean, rewrite, commit, or discard unrelated work.

---

# 5. Key implementation decision — new narrow public tools

Do **not** add the new research map as more operations inside legacy `knowledge_query` / `knowledge_action`.

Reasons:

1. the old research runtime is not being reused;
2. `knowledge_query` currently mixes genuinely read-only operations with historically stateful context operations;
3. public metadata therefore cannot truthfully mark the whole tool read-only;
4. the new map has a stronger no-write query invariant;
5. a separate surface keeps future retirement of the old research runtime independent.

Create exactly two new public tools:

```text
research_map_query
research_map_action
```

Expected metadata:

```text
research_map_query
  read_only = true
  destructive = false
  idempotent = true

research_map_action
  read_only = false
  destructive = true or mutating
  idempotent by operation where mechanically possible
```

The public gateway inventory increases by exactly two names when activated.

No other new public tool is required in v1.

---

# 6. Target package structure

Preferred implementation package:

```text
soma/research_map/
├── __init__.py
├── models.py
├── canonical.py
├── manifest.py
├── sidecars.py
├── coverage.py
├── desired_state.py
├── runtime.py
├── backend.py
├── graphiti_backend.py
├── service.py
└── gateway.py
```

Responsibilities:

```text
models.py
  strict durable/public models and enums

canonical.py
  UTF-8/LF canonicalization, canonical JSON, deterministic hashes/IDs

manifest.py
  soma.project.json loading/validation/adoption helpers

sidecars.py
  sidecar discovery/validation/source-anchor verification

coverage.py
  eligible/reviewed/no-material/deferred/unreviewed/stale accounting

desired_state.py
  deterministic semantic desired-state construction

runtime.py
  repo-local .soma/research-map generations, locks, atomic CURRENT

backend.py
  backend-neutral protocol and projections

graphiti_backend.py
  optional Graphiti + local embedding + FalkorDB Lite implementation

service.py
  project-bound orchestration without public MCP concerns

gateway.py
  register_research_map_tools(mcp), bounded public projections
```

Do not put the new implementation in `soma/research/` or extend the old RAGFlow service.

---

# 7. Portable tracked contract

## 7.1 Project manifest

Tracked file:

```text
soma.project.json
```

Minimum v1 shape:

```json
{
  "schema": "soma.project.v1",
  "repository_uid": "srepo_<stable-generated-id>",
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

`repository_uid` is portable logical identity only.

It must never be accepted as repository-write authorization.

Forbidden tracked manifest fields include:

```text
absolute repository path
ProjectScope project_id
ProjectScope resource_id
scope_generation
repository_identity_hash derived from local path
backend port
backend process id
credentials
provider/API keys
machine name
current branch/HEAD
last-sync timestamps
Graphiti-specific configuration
```

Runtime resolution remains:

```text
repository_uid
+ explicit current project_id/repo_name
+ ProjectScope exact repository-root validation
```

## 7.2 Manifest path safety

Each configured research root must:

- be repository-relative;
- contain no drive/UNC/absolute syntax;
- contain no `..` traversal;
- not enter `.git` or `.soma`;
- not overlap another configured root in a way that double-owns one source;
- use bounded include patterns;
- use a sidecar directory relative to that root;
- not use the research root itself as the sidecar directory.

Malformed manifest degrades the research-map feature only.

It must not break ordinary repo tools, continuation, tasks, runs, wiki, or project memory.

---

# 8. Reviewed sidecar contract v2

Preferred placement:

```text
<research-root>/<source>.md
<research-root>/_soma_map/<source-stem>.json
```

## 8.1 Source envelope

Minimum:

```json
{
  "schema_version": "soma.research-map.v2",
  "source": {
    "path": "docs/research/038_example.md",
    "canonical_text_sha256": "..."
  },
  "review": {
    "state": "reviewed",
    "controller": "Sol",
    "materiality": "material"
  },
  "facets": {},
  "relations": []
}
```

Allowed review states for v1 implementation:

```text
reviewed
  materiality = material | none

deferred
  materiality omitted
  optional deterministic reason
```

Interpretation:

```text
missing sidecar
  = unreviewed

reviewed + materiality=none + relations=[]
  = explicitly reviewed; no material carry-forward relation

deferred
  = deliberately postponed; not coverage-complete
```

No generated timestamp is required in tracked sidecars.

## 8.2 Canonical Markdown hash

For research Markdown:

```text
read bytes
→ decode strict UTF-8
→ normalize CRLF to LF
→ normalize remaining CR to LF
→ encode UTF-8
→ SHA-256
```

Field:

```text
canonical_text_sha256
```

Raw byte SHA may be emitted as diagnostic metadata but cannot determine portable freshness.

Git blob OID may be supplementary provenance for committed records but cannot replace worktree canonical-text validation.

## 8.3 Record identity

Human research numbers are metadata only.

Compute internally:

```text
logical_record_id
  = deterministic hash of normalized repository-relative source path

record_version_id
  = deterministic hash of logical_record_id + canonical_text_sha256
```

This handles Axon's real duplicate research-number cases without renaming history.

## 8.4 Relation shape

Each material relation contains at least:

```json
{
  "relation_id": "rel_<deterministic-id>",
  "subject": {"key": "...", "label": "..."},
  "predicate": "QUALIFIES",
  "object": {"key": "...", "label": "..."},
  "statement": "reviewed nuanced semantic statement",
  "locator": {"anchor": "exact source text"},
  "epistemic_class": "observed",
  "lifecycle": "current",
  "supersedes": [],
  "facets": {},
  "qualifiers": {}
}
```

### Deterministic relation ID

Identity input:

```text
source relative path
+ subject key
+ predicate
+ object key
```

Do not include display labels, statement wording, rank, timestamp, or backend fields.

A refinement to the same relation statement retains relation identity but changes the sidecar/desired-state hash, forcing index refresh.

A genuinely different predicate/object creates a new relation identity.

## 8.5 Epistemic class

Initial registry:

```text
observed
inference
hypothesis
decision
requirement
constraint
interpretation
unknown
```

Retrieval must never silently promote `hypothesis` to `observed`.

## 8.6 Relation lifecycle

Initial registry:

```text
current
superseded
disputed
archived
rejected
```

Successor-owned supersession remains the rule:

```text
new relation contains supersedes=[old_relation_id]
old sealed sidecar does not need rewriting
```

Graphiti `invalid_at` is not scientific lifecycle authority.

## 8.7 Predicate registry

Initial scientific family, grounded in the NSDN/Axon research:

```text
ALLOWS
CONSTRAINS
FALSIFIES
FORBIDS
LIMITS
MOTIVATES
NARROWS
PRESERVES
QUALIFIES
REQUIRES
SUPPORTS
```

Initial governance family:

```text
GOVERNS
AMENDS
AUDITS
ACCEPTS
SUPERSEDES
RECONCILES
CLOSES
REOPENS
AUTHORIZES
PARKS
```

Initial provenance/transfer family:

```text
INFORMED_BY
IMPORTS_EVIDENCE_FROM
DERIVES_FROM
REPRODUCES
REPLAYS
```

Do not add generic `RELATED_TO` as a substitute for scientific meaning.

A future predicate can be added only through a schema/registry revision with tests.

## 8.8 Facets and qualifiers

Facets classify the record/relation without becoming identity:

```text
programme
thread
phase_or_generation
dataset
mechanism
record_role
evidence_surface
execution_stage
```

Additional reviewed facet keys are allowed by schema design.

Qualifiers restrict applicability, for example:

```json
{
  "dataset": ["PathMNIST"],
  "evidence_role": ["historical-comparator"],
  "claim_limit": ["descriptive-only"],
  "test_state": ["official-test-consumed"]
}
```

Structured facets/qualifiers remain structured in tracked sidecars even if a backend requires serialized projection.

---

# 9. Desired-state identity

Relation-ID equality is insufficient.

Compute a backend-independent semantic desired state from canonical inputs including:

```text
manifest research_map section
repository_uid
research-map schema version
predicate-registry version
sorted eligible source paths
canonical source text hashes
canonical sidecar bytes/hashes
review state/materiality
relation content including statement/lifecycle/facets/qualifiers/locators
```

Output:

```text
semantic_desired_state_sha256
```

Separately compute a projection contract identity from:

```text
backend adapter/version
Graphiti projection schema version
embedding model identity/version/dimension
relation/node UUID derivation version
backend property encoding version
```

Output:

```text
projection_contract_sha256
```

Changing scientific semantic state or changing retrieval projection requirements must therefore make the published generation stale for the appropriate reason.

---

# 10. Local runtime layout — immutable generations

Use the existing wiki generation pattern as a reliability precedent, but do not couple the implementations.

Preferred layout:

```text
repo/.soma/research-map/
├── CURRENT.json
├── .sync.lock
└── generations/
    ├── <generation-A>/
    │   ├── DESIRED.json
    │   ├── RELATIONS.json
    │   ├── HEALTH.json
    │   └── index/
    │       └── backend-private state
    └── <generation-B>/
        └── ...
```

### Why immutable generations

Iteration 12 proved saved-but-unpublished backend mutation is detectable.

Production should improve the transaction further:

```text
NEVER mutate the published current generation in place.
```

Sync flow:

```text
current generation A remains readable
        |
        v
create staging generation B
        |
        v
build/copy + reconcile B
        |
        v
read-back verify B
        |
        v
explicit backend persistence
        |
        v
close + reopen verify B
        |
        v
atomically publish CURRENT -> B
```

If the process dies before publication, A remains the published generation.

An orphan/staging B may be deleted later because it is derived state.

## 10.1 Incremental update without mutating current

Initial project bootstrap may perform a full build.

For normal after-research updates, prefer:

```text
copy verified current generation index into new staging generation
→ compare relation projection hashes
→ add/update/remove only the delta
→ reconcile complete desired relation set
→ SAVE + reopen verify
→ publish new generation
```

If incremental copy/reconcile cannot be trusted, fall back to full deterministic rebuild of the staging generation.

The published generation is never edited in place.

---

# 11. `.soma/` repository perimeter

Before any database is placed under `.soma/`, reserve the namespace in code.

Required changes:

```text
repo_reader.py
  block `.soma` in every path segment

repo_writer.py
  generic repository mutation inherits the `.soma` block

repo_wiki.py
  always exclude `.soma`, including filesystem fallback

tool_owned_paths.py
  classify `.soma/` as Soma-owned local runtime
```

Dedicated research-map runtime code may access `.soma/research-map/` internally after exact repository scope validation.

Generic repository tools may not.

## 11.1 Local Git exclusion

Explicit research-map adoption must idempotently ensure:

```text
/.soma/
```

in the repository-local Git exclude resolved via:

```text
git rev-parse --git-path info/exclude
```

Do not silently edit tracked `.gitignore`.

A repository may separately choose to commit a `.gitignore` rule, but Soma does not require that.

## 11.2 Wiki exclusion for tracked sidecars

Tracked `_soma_map/` files remain readable by ordinary authorized repo reads and by the research-map service.

But they must be excluded from generated code wiki source candidates by default.

Reason:

- avoid duplicate semantic content;
- avoid wiki churn after every research-map update;
- protect the current `MAX_SOURCE_FILES = 2000` budget;
- keep the wiki a code/repository navigation surface.

---

# 12. Public query contract

Create:

```text
research_map_query
```

Recommended v1 operations:

```text
health
coverage
search
relation
```

Every call requires exact project scope:

```text
project_id
repo_name
```

No implicit project selection.

## 12.1 `health`

Returns compact independent dimensions:

```text
adoption_state
manifest_state
coverage_state
sync_state
backend_state
repository_uid
semantic_desired_state_sha256
published_generation
projection_contract_sha256
stale_sidecar_count
unreviewed_count
```

## 12.2 `coverage`

Bounded/paginated source statuses:

```text
reviewed_material
reviewed_no_material
deferred
unreviewed
stale
missing_source
```

This is the bootstrap/resumption navigation surface.

## 12.3 `search`

Input:

```text
query
limit default 5
limit max 20
include_noncurrent false by default
```

Before search:

1. resolve exact ProjectScope;
2. validate manifest;
3. recompute live semantic desired-state identity;
4. require live desired state == CURRENT semantic state;
5. require projection contract == CURRENT projection contract;
6. require published index integrity/read-back contract;
7. only then search.

If stale/unhealthy:

```text
return degraded/stale health
return no claim of current semantic-map completeness
perform zero repair writes
```

Search result item includes at minimum:

```text
rank
relation_id
predicate
statement
epistemic_class
lifecycle
subject/object labels
facets
qualifiers
source path
source canonical_text_sha256
source anchor
external reference metadata if present
verification_required = true
```

Rank 1 is never presented as automatic scientific truth.

## 12.4 `relation`

Exact relation retrieval by `relation_id`, for progressive disclosure after a search hit.

Must remain read-only.

---

# 13. Public action contract

Create:

```text
research_map_action
```

Recommended initial operations:

```text
adopt
sync
rebuild
```

No delete/purge/rekey/federation operations in v1.

## 13.1 `adopt`

Explicit owner-authorized mutation.

Behavior when no manifest exists:

1. resolve exact ProjectScope/repository;
2. validate requested research roots;
3. generate one stable `repository_uid`;
4. create `soma.project.json` atomically;
5. ensure local `/.soma/` Git exclude;
6. initialize local runtime root if needed;
7. report initial coverage;
8. do not generate semantic sidecars automatically;
9. do not build Graphiti unless separately requested through sync.

Behavior when manifest exists:

- validate it;
- preserve repository_uid;
- establish local Git exclusion/runtime if missing;
- return idempotent attachment result;
- refuse incompatible requested roots rather than silently rewriting tracked configuration.

Repository discovery remains read-only. Merely mentioning/opening a repo does not adopt it.

## 13.2 `sync`

Normal after-research explicit update.

Behavior:

```text
validate docs + sidecars
→ compute coverage + semantic desired state
→ construct a new immutable local generation
→ incremental reconcile or full build
→ exact relation read-back
→ explicit backend persist
→ close/reopen verify
→ atomic CURRENT publish
```

No semantic extraction occurs.

## 13.3 `rebuild`

Discard/rebuild local derived index from current tracked sidecars.

Use for:

```text
missing local DB after clone
backend corruption
projection-contract change
manual recovery
forced acceptance test
```

It must not rewrite sidecars or scientific reports.

---

# 14. Backend-neutral contract

Define a narrow backend protocol before Graphiti implementation.

Conceptual methods:

```text
build_empty(...)
clone_from_current(...)
upsert_nodes(...)
upsert_relations(...)
remove_relations(...)
read_relation_manifest(...)
search(...)
persist(...)
close(...)
reopen_and_verify(...)
```

The service owns scientific desired state.

The backend owns only projection/storage/search.

No backend is allowed to infer semantic lifecycle.

---

# 15. Graphiti adapter contract

Graphiti remains optional and derived.

Production adapter must preserve the pilot boundary:

```text
LLM client
  local NoLLM implementation that raises if called

embeddings
  local BAAI/bge-small-en-v1.5 baseline

cross encoder
  no external model requirement in v1

telemetry
  GRAPHITI_TELEMETRY_ENABLED=false
```

Do not consume external model/provider credentials; the RM5 backend must remain locally self-contained.

Do not call:

```text
Graphiti.add_episode()
Graphiti.add_triplet()
```

for reviewed semantic ingestion if those paths invoke Graphiti LLM resolution.

Write reviewed entities/relations through the deterministic direct projection path proven in the pilots.

## 15.1 Primitive backend projection

Durable sidecar data remains structured.

If FalkorDB requires primitive values:

```text
facets       -> canonical facets_json
qualifiers   -> canonical qualifiers_json
```

This is an adapter representation only.

## 15.2 One DB per repository

Do not depend on FalkorDB `group_id` full-text isolation in v1.

Each adopted repository has one local research-map index.

Cross-project references are local external-reference stubs, not merged global graphs.

---

# 16. FalkorDB Lite conditional contract

FalkorDB Lite may remain the first backend only if implementation conformance reproduces Iteration 12.

Mandatory transaction rule:

```text
write/reconcile staging generation
→ exact read-back verify
→ explicit Redis SAVE
→ require SAVE success
→ close
→ reopen
→ exact verify again
→ publish CURRENT
```

`driver.close()` alone is forbidden as a durability boundary.

Backend conformance must test the actual supported Soma host/runtime.

If the tested production host cannot run the pinned Lite backend reliably, RM5 stops `BLOCKED` and selects another local backend behind the same interface.

Do not make core Soma startup depend on the backend.

---

# 17. Dependency isolation

Current core Soma dependencies are intentionally small:

```text
fastmcp
pydantic
pyyaml
```

Graphiti/FastEmbed/FalkorDB dependencies must not become unconditional startup imports.

Preferred packaging:

```toml
[project.optional-dependencies]
research-map = [
  "graphiti-core==<accepted-version>",
  "fastembed==<accepted-version>",
  "falkordb-lite==<accepted-version>",
  "httpx>=0.27,<1"
]
```

Exact versions are frozen only after RM5 backend conformance on the production runtime.

Requirements:

- lazy import inside `graphiti_backend.py`;
- missing optional dependency returns `backend_unavailable` health;
- Soma server startup remains healthy;
- continuation/repo/task/run/wiki remain unaffected;
- no provider API key becomes required.

A shared local embedding-model cache may live in Soma machine runtime/cache outside project Git state. The project database itself remains repo-local.

---

# 18. Cross-project references

A reviewed relation may point at an external record stub:

```json
{
  "kind": "external_record",
  "repository_uid": "srepo_<other-project>",
  "path": "docs/research/025_....md",
  "canonical_text_sha256": "..."
}
```

The current project's DB stores the reference, not the other project's full graph.

V1 search behavior:

```text
return external reference stub
→ Sol decides whether it matters
→ Sol explicitly opens/queries the other attached project
→ verify exact external source
```

Do not implement global graph federation in this programme.

If multiple attached clones carry the same repository_uid and resolution is ambiguous, fail closed.

---

# 19. Concurrency and interruption semantics

## 19.1 One sync writer

Use:

```text
.soma/research-map/.sync.lock
```

with stale-lock detection compatible with Soma operation-lock conventions where practical.

Two sync/rebuild writers for one repository may not mutate staging state concurrently.

## 19.2 Queries during sync

A query reads only the currently published immutable generation.

If tracked sidecars changed and live desired state no longer matches CURRENT, query reports stale and refuses semantic completeness.

If a forced rebuild is running for an unchanged desired state and current generation is still healthy, serving the current generation is permissible.

## 19.3 Stream interruption

A cut after the report but before sidecar creation is visible as:

```text
source exists
sidecar missing
```

A cut after sidecar creation but before sync is visible as:

```text
live desired state != CURRENT
```

A cut while staging a new generation leaves the prior immutable generation published.

Repeated sync must be idempotent with respect to semantic desired state.

---

# 20. Research workflow integration

The backend does not automatically interpret new research.

After the core capability is accepted, update the research workflow/Skill guidance so Sol performs:

```text
BEFORE NEW RESEARCH
- inspect existing research numbering to avoid duplicate iteration documents
- if project is research-map adopted, query relevant old semantic context
- reopen authoritative source docs before relying on retrieved candidates

AFTER RESEARCH
- save authoritative report under docs/
- semantically adjudicate material findings
- create/update that exact source sidecar
- explicitly run research_map_action(sync)
- verify health
```

If Graphiti/backend sync fails:

```text
research report remains valid and complete
sidecar remains durable if already written
map reports stale/degraded
continuation remains usable
```

Map failure must never force rewriting scientific findings.

Do not add a hidden post-save hook that automatically invents sidecar semantics.

---

# 21. Delivery dependency graph

```text
RM0  authority/preflight
 |
 v
RM1  repository perimeter + base models
 |
 v
RM2  manifest/sidecar/coverage/desired-state engine
 |
 +---------------------+
 |                     |
 v                     v
RM3 read-only gateway   RM4 explicit adoption/runtime lifecycle
 |                     |
 +----------+----------+
            |
            v
RM5 backend protocol + Graphiti/Lite conformance
            |
            v
RM6 immutable-generation sync/rebuild
            |
            v
RM7 semantic search activation + crash/read-only acceptance
            |
            v
RM8 research workflow integration acceptance
            |
            v
RM9 NSDN controlled rollout
            |
            v
RM10 Axon controlled rollout + scale acceptance
            |
            v
RM11 final capability/docs/legacy-boundary acceptance
```

Do not skip ahead to historical backfill before RM7 is accepted.

---

# 22. RM0 — authority freeze and drift preflight

## Goal

Reconcile this plan against live Soma before changing source.

## Required actions

1. inspect branch, HEAD, worktree, active runs and repository locks;
2. preserve all unrelated `AGENTS.md` and research-doc changes;
3. re-read Iterations 09–12;
4. re-read exact current source seams named in Section 4;
5. confirm current public gateway inventories/metadata conventions;
6. confirm repo wiki generation and ProjectScope behavior have not materially changed;
7. record the exact file/symbol set expected for RM1;
8. do not install Graphiti dependencies yet.

## Acceptance

```text
current assumptions reconciled
no source mutation
no unrelated file touched
implementation file list frozen
```

STOP after RM0 acceptance.

---

# 23. RM1 — repository perimeter + canonical models

## Scope

Implement only backend-independent invariants.

Expected source seams:

```text
soma/tool_owned_paths.py
soma/repo_reader.py
soma/repo_writer.py
soma/repo_wiki.py
soma/research_map/models.py
soma/research_map/canonical.py
```

## Required behavior

- `.soma/` blocked from generic repo read/write/indexing;
- `.soma/` classified as tool-owned local runtime;
- `_soma_map/` excluded from code wiki only;
- canonical UTF-8/LF text hash helper;
- canonical JSON helper;
- strict manifest/sidecar/relation models;
- predicate, epistemic, lifecycle registries;
- deterministic record/relation identity helpers;
- Unicode round-trip tests.

## Acceptance tests

At minimum:

1. generic repo reader refuses `.soma/research-map/...`;
2. generic repo writer refuses `.soma/...`;
3. wiki Git scan excludes `.soma/`;
4. wiki filesystem fallback excludes `.soma/`;
5. wiki excludes tracked `_soma_map/*.json`;
6. ordinary repo reads can still read tracked `_soma_map/*.json`;
7. LF and CRLF copies of the same UTF-8 Markdown produce identical canonical text SHA;
8. a substantive character change produces a different canonical text SHA;
9. Unicode anchor text round-trips exactly;
10. duplicate/invalid predicate/lifecycle/schema values fail closed.

No Graphiti dependency is permitted in RM1.

---

# 24. RM2 — manifest, sidecar validation, coverage and desired-state engine

Expected modules:

```text
manifest.py
sidecars.py
coverage.py
desired_state.py
service.py
```

## Required behavior

- load/validate `soma.project.json` read-only;
- enumerate configured research roots deterministically;
- match each source to its expected sidecar path;
- validate canonical source hash;
- validate exact anchors;
- detect duplicate relation IDs;
- resolve successor-owned supersession state;
- classify coverage independently from sync;
- produce deterministic semantic desired-state hash;
- expose no DB dependency.

## Required coverage states

```text
reviewed_material
reviewed_no_material
deferred
unreviewed
stale
missing_source
```

## Acceptance

- deterministic output across repeated scans;
- ordering independent of filesystem enumeration order;
- duplicate numeric research IDs do not collide;
- two same-content clones with LF/CRLF checkout produce same semantic desired state;
- modifying reviewed statement changes desired-state hash even if relation_id remains the same;
- missing sidecar is not confused with reviewed-no-material;
- deferred is not counted as complete review;
- malformed sidecar affects research-map health only.

---

# 25. RM3 — separate read-only public gateway foundation

Expected seams:

```text
soma/gateway_models.py
soma/research_map/gateway.py
soma/server.py
soma/public_tool_metadata.py
soma/public_gateway_inventory.py
soma/cf1_gateway_operation_inventory.py
```

Add:

```text
research_map_query
```

Initial operations may activate `health`, `coverage`, and exact `relation` before semantic backend search is available.

`search` may be schema-visible but return `backend_unavailable` until RM7, or may be activated once RM5/6 are accepted. Choose one approach in RM0 and keep one public-contract change if practical.

## Acceptance

- public metadata declares query tool read-only;
- query invocation changes no tracked or local durable research-map state;
- exact project scope required;
- unadopted repo returns bounded `not_adopted` health;
- malformed manifest returns degraded research-map health, not server failure;
- operation inventory/schema hashes stabilize across two discovery passes;
- old `knowledge_query` behavior remains unchanged.

---

# 26. RM4 — explicit adoption and repo-local runtime lifecycle

Add:

```text
research_map_action(action="adopt")
```

Expected behaviors:

- exact ProjectScope binding required;
- explicit roots required for first adoption;
- create one portable repository_uid;
- atomically create `soma.project.json` only when absent;
- idempotently ensure local `/.soma/` Git exclude;
- initialize `.soma/research-map/` runtime;
- never generate semantic sidecars;
- never build an index merely because repo discovery occurred.

## Clone behavior

For a clone that already contains `soma.project.json` and sidecars:

```text
adopt/attach
→ validate existing manifest
→ preserve repository_uid
→ establish local .soma exclusion
→ report DB missing/stale
```

Actual rebuild remains an explicit `sync`/`rebuild` operation.

## Acceptance

- first adoption dirties only intended tracked manifest plus local exclude/runtime;
- second identical adoption is idempotent;
- conflicting roots fail closed;
- manifest never contains local ProjectScope IDs/paths;
- moving/cloning repository can create a new local ProjectScope while preserving repository_uid;
- ambiguous duplicate attached clones with same repository_uid do not auto-resolve cross-project writes.

---

# 27. RM5 — backend protocol and Graphiti/FalkorDB conformance

Implement backend protocol first.

Then implement Graphiti adapter behind lazy optional imports.

Production runtime policy after RM5 conformance: Docker is not a normal Soma or Research Map runtime dependency. Backend processes must remain lazy/on-demand and independent of Soma startup. Disposable Docker may be used for bounded conformance testing only; production storage may use an on-demand local runtime such as WSL or another conforming local server behind the same backend protocol.

Native FalkorDB Lite is not required on Windows. If the pinned Lite implementation is not host-compatible, preserve the same protocol and use a conforming server-backed local FalkorDB transport instead.

## Conformance corpus

Reuse the exact difficult Axon slice from Iteration 12:

```text
14 authoritative source documents
38 reviewed relations
20 adversarial natural-language questions
```

## Backend acceptance before production activation

1. no provider/API credential required;
2. Graphiti LLM path raises if invoked;
3. local BGE embedding dimension is expected/stable;
4. direct deterministic entity/edge projection works;
5. structured sidecar facets survive round-trip through adapter encoding;
6. close without explicit SAVE is covered by a negative regression test;
7. explicit SAVE persists across process restart;
8. relation read-back exactly matches desired projection set;
9. repeated reopen/query gives deterministic Top-5 list on fixed corpus;
10. group_id isolation is not relied on;
11. backend unavailable does not break Soma startup.

If the production host/runtime cannot satisfy these, stop RM5 as BLOCKED and select another backend behind the same interface.

---

# 28. RM6 — immutable-generation sync/rebuild engine

Add actions:

```text
research_map_action(sync)
research_map_action(rebuild)
```

## Required transaction

```text
validate current semantic desired state
→ acquire one sync writer lock
→ create new staging generation
→ full build or verified copy+delta
→ exact relation projection reconciliation
→ backend read-back
→ explicit persistence
→ close
→ reopen and reconcile again
→ write generation health/artifact metadata
→ atomically switch CURRENT
→ release lock
```

## Crash acceptance points

Inject failure:

```text
before staging creation
after staging creation
mid relation writes
after read-back
before SAVE
after SAVE
before CURRENT publish
after CURRENT publish
```

Expected invariant:

- before publish: previous current generation remains authoritative;
- after publish: new generation must be fully reopen-verified;
- orphan staging generations never become current;
- deterministic rebuild restores a corrupted/missing local index.

## Stale semantic change acceptance

Change an existing relation statement while preserving relation_id.

Required:

```text
live desired hash changes
old current becomes stale
query refuses current-completeness claim
sync creates new generation
new query recovers corrected relation
```

---

# 29. RM7 — semantic search activation and integrated safety acceptance

Activate `research_map_query(search)` against the accepted backend/generation service.

## Retrieval acceptance

NSDN frozen benchmark:

```text
15 adversarial questions
required Top-5 governing-fact coverage: 15/15
```

Axon difficult slice:

```text
20 adversarial questions
required Top-5 governing-fact coverage: 20/20
```

Hit@1 is reported but is not the primary acceptance target.

The controller is expected to reason over a small candidate set and reopen sources.

## Read-only acceptance

Snapshot before/after repeated search calls:

```text
tracked repo status
CURRENT.json hash
published generation files/hashes
sidecar hashes
relation manifest
```

Required:

```text
no persistent research-map mutation caused by search
```

Any backend transient runtime material must live outside immutable published generation content or be proven non-authoritative and cleaned without changing current scientific/index state.

## Source verification acceptance

Every returned candidate must resolve to:

```text
exact repo
exact source path
matching canonical source hash
exact anchor
```

A stale/missing source invalidates that candidate's current verification status.

---

# 30. RM8 — research workflow integration acceptance

After RM7 acceptance, validate the controller-visible end-to-end research-map workflow so every adopted project thread can follow the same start/re-entry and finishing-touch discipline through the accepted public surfaces.

RM8 does **not** publish or modify `arash-research`. Reusable Skill publication is explicitly deferred until after RM11 and full Research Map roadmap acceptance.

This is controller workflow validation, not hidden routing. Soma does not choose what is scientifically relevant, generate semantic relations automatically, or mark research complete on Sol's behalf.

## Required workflow behavior

Validate and document the research-map workflow below without changing the reusable research Skill.

The controller workflow must remain capability-aware so the same research process is safe both before and after research-map production activation:

```text
research-map feature unavailable or repo not adopted
  → continue evidence-first research from authoritative sources
  → save the required durable research report
  → do not invoke legacy RAGFlow/context-packet research as a substitute
  → report research-map finishing touch as unavailable/not-adopted when material

research-map feature available + repo adopted
  → use the research map as a retrieval/navigation aid
  → reopen exact authoritative sources before relying on retrieved context
  → finish research in authoritative Markdown
  → perform reviewed semantic sidecar finishing touch
  → explicitly sync/reconcile map
  → verify health/read-back
```

## Required end-to-end research workflow

```text
start/re-enter research
→ duplicate-iteration guard before a numbered report is created
→ inspect map health/coverage when repo is adopted
→ query relevant prior map context when current enough to be useful
→ reopen exact source docs and verify provenance
→ conduct evidence-first research
→ save authoritative research report under docs/
→ Sol adjudicates material carry-forward semantics
→ create/update that source's reviewed sidecar, including reviewed-no-material when appropriate
→ validate source canonical hash + locators
→ explicitly sync/reconcile the repo-local research map
→ read-back verify desired/current relation state and health
→ report research result + coverage/sync state
```

The map step is the **standard finishing touch** of every completed research iteration in an adopted project. It must not be skipped merely because the current Chat already remembers the result.

## Completion semantics

Scientific durability and map availability remain distinct.

The authoritative report is never rolled back or rewritten because indexing fails. Graphiti/backend availability must not become authority over whether the scientific work happened.

However, once a project has adopted the research map, the workflow must not silently claim a fully closed research-map cycle if the finishing touch did not complete. The controller must end in one of these explicit states:

```text
research_saved + map_synced_verified
research_saved + sidecar_saved + map_sync_degraded
research_saved + map_finishing_touch_unavailable
```

If sync fails, preserve the report and sidecar state, expose the degraded/pending map condition, and allow the next thread to resume the finishing touch idempotently.

## Interruption/duplicate safety

The RM8 acceptance workflow must explicitly check existing research records before creating a new numbered iteration. After a stream cut, it must inspect whether each stage already exists before repeating it:

```text
research report
reviewed sidecar
published map generation
```

Repeating a sidecar/sync operation must converge on the same desired state rather than create duplicate semantic facts.

## Research-map trust rule

Retrieved graph relations are candidate context only. The controller must always reopen exact source Markdown before a retrieved prior finding materially affects a conclusion, design decision, falsification, or next research action.

Do not revive `soma.research.v1`, RAGFlow, or query-time context-packet persistence to satisfy this workflow.

## Post-roadmap Skill finishing touch

Only after RM11 is accepted and the full Research Map roadmap is complete, publish a new current revision of `arash-research` that incorporates the accepted finishing-touch workflow. That post-roadmap Skill revision is not part of RM8 acceptance and must not be activated earlier.

---

# 31. RM9 — controlled NSDN rollout

NSDN is the first real adoption because its corpus is smaller and already has a fixed semantic benchmark.

Recommended order:

```text
1. adopt NSDN research root(s)
2. backfill the existing 21 gold-source sidecars first
3. reproduce 15/15 Top-5 benchmark
4. backfill remaining research files in bounded batches
5. explicitly mark reviewed-no-material records
6. reach complete source coverage
7. test one newly completed research iteration end-to-end
```

Do not bulk-generate sidecars mechanically from filenames or embeddings.

Sol must review historical documents in bounded batches.

Acceptance:

```text
all eligible NSDN research docs classified
0 stale sidecars
sync_current true
fixed benchmark 15/15 Top-5
clone/rebuild succeeds
new research incremental update succeeds
```

---

# 32. RM10 — Axon rollout and scale acceptance

Axon is the complexity/scale proving ground, not the first implementation target.

Start with the Iteration-12 difficult slice and current scientific frontier.

Then staged backfill priority:

```text
A. current controlling frontier
B. terminal positive/negative findings
C. programme reconciliations and cross-lane bridges
D. protocol/governance composites
E. older implementation/audit detail
```

Do not require chronological 1→460 review before the map becomes useful.

Coverage must truthfully remain partial until all eligible records are classified.

Scale acceptance should measure:

```text
eligible source count
sidecar validation time
desired-state computation time
initial full build time
incremental one-research sync time
query open latency
search latency
index size
embedding cache behavior
rebuild time
peak memory
```

No threshold should be invented before measurement, except semantic correctness and safety invariants.

If incremental update is too slow, optimize the derived projection path without weakening tracked semantics.

---

# 33. RM11 — final rollout, documentation and legacy boundary

## Required final state

- `research_map_query` and `research_map_action` appear in public inventories;
- public capability/schema identities are refreshed and stable;
- self-check reports research-map optional backend health without breaking core health;
- `.soma/` namespace protection is documented;
- `soma.project.json` contract is documented;
- sidecar v2 contract is documented;
- project adoption/backfill/update workflow is documented;
- NSDN rollout evidence is preserved;
- Axon partial/full coverage state is honestly reported;
- no continuation change;
- no RAGFlow dependency;
- no old research subsystem repair performed merely for this programme.

The legacy `soma.research.v1` runtime remains historical/dormant unless separately authorized in the future.

Do not route new research-map calls through it.

---

# 34. Acceptance matrix

| ID | Requirement | Acceptance evidence |
|---|---|---|
| A01 | Research docs authoritative | search result always returns source path/hash/anchor + verification-required flag |
| A02 | Sol semantic authority | no automatic LLM extraction/contradiction path in ingestion |
| A03 | No external provider dependency | backend conformance requires no external model/provider credentials |
| A04 | Continuation unchanged | continuation source/schema diff absent |
| A05 | `.soma/` protected | repo reader/writer/wiki/tool-owned tests pass |
| A06 | Sidecars tracked | `_soma_map` visible to Git/repo reads and excluded only from wiki |
| A07 | Portable source hash | LF/CRLF clone test yields identical canonical_text_sha256 |
| A08 | Duplicate research IDs safe | Axon duplicate 091/077 cases produce distinct record identities |
| A09 | Epistemic class preserved | hypothesis/observed retrieval records remain distinguishable |
| A10 | Scoped authority preserved | R089→R091 and R162+164+166 composite cases resolve correctly |
| A11 | Cross-project isolation | NSDN reference stored as external stub, not merged global graph |
| A12 | Query truly read-only | repeated searches produce zero persistent map mutations |
| A13 | Missing sidecar visible | unreviewed != reviewed-no-material |
| A14 | Coverage separate from sync | partial coverage/current sync reported simultaneously |
| A15 | Statement drift detected | unchanged relation_id + changed statement makes old generation stale |
| A16 | Backend optional | server starts and core tools work with research-map extra absent |
| A17 | Graphiti LLM forbidden | NoLLM path test fails if invoked |
| A18 | Falkor persistence explicit | close-only negative regression + SAVE positive restart test |
| A19 | Immutable current generation | sync never mutates currently published index in place |
| A20 | Crash before publish safe | previous CURRENT remains valid; orphan generation never served |
| A21 | Reopen verification | newly published generation reopens and exactly reconciles desired relations |
| A22 | Deterministic rebuild | delete index → rebuild from sidecars → same relation manifest |
| A23 | NSDN retrieval | 15/15 gold questions have governing fact in Top-5 |
| A24 | Axon retrieval | 20/20 difficult questions have governing fact in Top-5 |
| A25 | Git hygiene | `.soma/` absent from Git status after adopt/sync |
| A26 | Manifest portability | clone preserves repository_uid but not local ProjectScope identity |
| A27 | No hidden auto-adoption | repo discovery alone creates no manifest/runtime |
| A28 | No hidden semantic post-hook | saving research alone does not invent a sidecar |
| A29 | Skill/workflow incremental path | new research → sidecar → sync → health works end-to-end |
| A30 | Legacy isolation | old RAGFlow/context-packet runtime untouched by new map path |

Any failure of A01–A22 blocks production rollout.

A23–A24 block semantic acceptance.

A25–A30 block integrated rollout acceptance.

---

# 35. Explicitly out of scope

This implementation programme does not include:

```text
a global all-project knowledge graph
server-side automatic scientific interpretation
automatic relation extraction from all Markdown
Graphiti LLM extraction
Graphiti automatic contradiction truth
RAGFlow revival
legacy research context-packet repair
continuation redesign
semantic next-action engine
provider/subagent research routing
automatic Git commit/push of sidecars
automatic historical backfill without Sol review
```

A future optional federation layer may be researched only after project-isolated maps are accepted in real use.

---

# 36. Implementation execution rules

1. Implement one RM stage at a time.
2. Every stage ends in exactly one state:

```text
ACCEPTED
BLOCKED
FAILED
```

3. Do not silently redesign a failed stage inside the implementation batch.
4. If source drift invalidates the plan, stop and reconcile.
5. Preserve all unrelated worktree changes.
6. No commit or push unless separately authorized.
7. Do not repair dormant legacy research code unless a later owner decision explicitly chooses to reuse it.
8. Save acceptance records under `docs/soma-knowledge-carry-forward-research/` or a dedicated implementation-acceptance subdirectory before declaring a stage accepted.
9. Refresh the repository wiki only where appropriate; `_soma_map` is intentionally excluded from code-wiki content.
10. Maintain a current Soma continuation/handoff only if the owner explicitly chooses to track this implementation through continuation; continuation is not part of research-map semantics.

---

# 37. Definition of production-ready v1

V1 is ready when all of the following are true:

```text
portable manifest accepted
sidecar v2 accepted
.soma namespace protection accepted
coverage/desired-state engine accepted
separate read-only query gateway accepted
explicit adoption/sync/rebuild action gateway accepted
optional backend isolation accepted
immutable generation transaction accepted
explicit persistence/reopen verification accepted
NSDN benchmark accepted
Axon difficult benchmark accepted
clone/rebuild accepted
new-research incremental workflow accepted
legacy research runtime remains isolated
core Soma works with backend absent
```

Full Axon historical sidecar coverage is a project-data rollout milestone, not a prerequisite for calling the Soma implementation itself structurally correct.

The system must always report whether Axon coverage is partial or complete.

---

# 38. Exact next action

The next action after owner approval of this plan is:

```text
RM0 — authority freeze and implementation preflight only
```

RM0 performs no production source mutation.

After RM0 acceptance, implementation begins with RM1.

Do not jump directly to Graphiti dependency installation or Axon/NSDN backfill.
