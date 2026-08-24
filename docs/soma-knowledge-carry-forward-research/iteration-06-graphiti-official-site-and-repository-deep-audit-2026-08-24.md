# Soma Knowledge Carry-Forward Research — Iteration 06

**Date:** 2026-08-24  
**Status:** official-site / official-repository deep audit complete  
**Scope:** Graphiti as an optional semantic research-context map for Soma  
**Implementation authority:** none; this is research only  
**Primary upstream:** Zep `getzep/graphiti`

## 1. Naming correction

The project under investigation is **Graphiti**, ending in `i`.

Authoritative upstream naming:

- Project: **Graphiti**
- Python package: `graphiti-core`
- Repository: `https://github.com/getzep/graphiti`
- Documentation: `https://help.getzep.com/graphiti/`

`Graphity` is a different product/name and is not the Zep temporal-context-graph project.

## 2. Soma problem being evaluated

This audit does **not** treat Graphiti as a replacement for Soma continuation or repository research documents.

The owner-defined boundary is:

```text
Soma continuation = durable handoff / re-entry
repository docs    = authoritative research record
Sol / ChatGPT      = semantic understanding and adjudication
Graphiti candidate = optional derived semantic map for old/current research relationships
```

The target failure is long-horizon **research context mapping**: older research remains durably present in `docs/`, but later reasoning can omit an old result that is still governing, especially when the later question uses different wording or traverses a long research lineage.

The desired Graphiti use is therefore not mechanical file linking. The candidate workflow is:

```text
research completed and saved in docs
        ↓
Sol understands/adjudicates the result
        ↓
reviewed semantic relationships are added to a derived map
        ↓
future question searches the map
        ↓
map identifies potentially governing old work
        ↓
Sol re-opens/verifies the authoritative research document
```

Graphiti must never outrank the repository research record.

## 3. Research method

This iteration followed the enabled `arash-research` method:

1. inspect official Graphiti documentation;
2. inspect current `getzep/graphiti` source and package metadata;
3. inspect the current MCP implementation rather than assuming its README contract;
4. inspect recent open issues only where they materially attack the proposed Soma use;
5. reconcile issue claims against current source/release state when possible;
6. separate observed upstream behavior from Soma design inference.

Primary official sources inspected:

- `https://help.getzep.com/graphiti/getting-started/overview`
- `https://help.getzep.com/graphiti/getting-started/quick-start`
- `https://help.getzep.com/graphiti/core-concepts/adding-episodes`
- `https://help.getzep.com/graphiti/core-concepts/custom-entity-and-edge-types/`
- `https://help.getzep.com/graphiti/core-concepts/graph-namespacing`
- `https://help.getzep.com/graphiti/working-with-data/searching`
- `https://help.getzep.com/graphiti/working-with-data/adding-fact-triples`
- `https://github.com/getzep/graphiti`
- `https://github.com/getzep/graphiti/blob/main/pyproject.toml`
- `https://github.com/getzep/graphiti/blob/main/graphiti_core/graphiti.py`
- `https://github.com/getzep/graphiti/blob/main/graphiti_core/edges.py`
- `https://github.com/getzep/graphiti/blob/main/graphiti_core/utils/maintenance/edge_operations.py`
- `https://github.com/getzep/graphiti/blob/main/mcp_server/README.md`
- `https://github.com/getzep/graphiti/blob/main/mcp_server/src/graphiti_mcp_server.py`
- `https://github.com/getzep/graphiti/releases`

Material current issue/advisory evidence inspected:

- `https://github.com/getzep/graphiti/issues/1728`
- `https://github.com/getzep/graphiti/issues/1707`
- `https://github.com/getzep/graphiti/issues/1666`
- `https://github.com/getzep/graphiti/issues/1664`
- `https://github.com/getzep/graphiti/issues/1661`
- `https://github.com/getzep/graphiti/issues/1645`
- `https://github.com/getzep/graphiti/security/advisories/GHSA-gg5m-55jj-8m5g`

## 4. What Graphiti actually is

Official documentation describes Graphiti as an open-source framework for building and querying **temporal knowledge graphs**, branded as **Context Graphs**.

Its graph contains three especially important concepts:

```text
entity nodes
relationship/fact edges
episodic nodes (ingestion/source events)
```

Unlike a static document graph, Graphiti is explicitly designed around information that changes with time. It incrementally adds new episodes, extracts or accepts entities/facts, resolves duplicates/contradictions, and keeps temporal metadata on facts.

The official distinction is:

```text
Graphiti = open-source temporal context-graph framework
Zep      = managed/enterprise product built on Graphiti
```

For Soma we are evaluating **Graphiti OSS**, not Zep Cloud.

## 5. Current package/repository state

Current package metadata observed from upstream `pyproject.toml`:

```text
package          graphiti-core
version          0.29.3
license          Apache-2.0
Python           >=3.10,<4
```

The project is actively developed and the repository has a large active issue/PR surface. That is positive for maintenance, but it also means behavior is moving quickly and pinning/version-specific validation would be mandatory for a Soma integration.

Current release history includes:

```text
v0.29.3  FalkorDB and other optimizations
v0.29.2  FalkorDB bug fixes
v0.29.1  optimizations and efficiencies
v0.29.0  major efficiency/internal architecture changes
v0.28.2  security hardening for search-filter Cypher injection
```

Any pilot must use a version at least as new as the security-fixed line; current research should target the current stable release, not stale examples.

## 6. Core storage and execution model

Graphiti itself is a Python library plus a graph backend and model/embedding clients.

Officially supported/currently documented backends include:

- Neo4j;
- FalkorDB;
- Amazon Neptune.

Kuzu appears in historical/current source paths but is explicitly deprecated because the upstream Kuzu project is unmaintained; it is not a sensible new Soma choice.

The Graphiti constructor accepts injected:

```text
graph_driver
llm_client
embedder
cross_encoder
```

Defaults use OpenAI-compatible components when custom clients are not supplied.

This means Graphiti is not merely a passive graph database. Its normal ingestion pipeline performs multiple LLM-backed semantic operations, including extraction, entity resolution/deduplication, edge resolution, attribute extraction, and contradiction handling.

## 7. FalkorDB deployment options

For the official MCP server, FalkorDB is the default/recommended setup. The repository ships a combined Docker setup containing FalkorDB and the MCP server.

The documented combined deployment exposes roughly:

```text
Graphiti MCP HTTP   :8000/mcp/
FalkorDB/Redis      :6379
FalkorDB Web UI     :3000
```

The Docker documentation notes that the default FalkorDB password is empty, so a real local/private deployment must not inherit that production-unsafe default blindly.

Embedded FalkorDB Lite support is also shown in the current quick-start source. It removes the separate database service but currently carries important constraints:

- requires Python 3.12+;
- is an optional path rather than the broadest supported runtime;
- prior upstream design discussion noted platform/single-process constraints that should be revalidated before relying on it.

Soma itself currently supports Python >=3.10 and has a deliberately small dependency set. Therefore the cleanest candidate remains **an isolated optional Graphiti service/environment**, not adding Graphiti/FalkorDB to Soma's core runtime.

## 8. Episodes: Graphiti's strongest provenance primitive

Official docs define an **episode** as one ingestion event. Supported episode forms include:

```text
text
message
json
```

An episode is itself a graph node. Entities identified from an episode are connected through episodic provenance edges (`MENTIONS` in the conceptual docs).

This is highly relevant to Soma because one completed research iteration can naturally map to one or more episodes containing:

- research-iteration identity;
- exact research-document path;
- document SHA-256;
- research question;
- reviewed synthesis;
- perhaps exact governing findings/constraints.

Graphiti supports an explicit `reference_time`, separating ingestion time from the time represented by the source. Entity facts carry temporal fields such as:

```text
created_at
valid_at
invalid_at
expired_at
reference_time
episodes[]
```

The `episodes` list on an entity edge is specifically documented in current source as the episode IDs referencing that edge.

This makes the episode path materially stronger for provenance than a bare manually-added triplet.

## 9. Episode ingestion is semantic/LLM-driven

Current `add_episode()` accepts domain controls including:

- `entity_types`;
- `excluded_entity_types`;
- `edge_types`;
- `edge_type_map`;
- `custom_extraction_instructions`;
- `previous_episode_uuids`;
- `group_id`;
- saga fields.

The normal path still asks Graphiti's configured LLM to:

1. extract entities;
2. classify/deduplicate them;
3. extract relations;
4. classify/deduplicate relations;
5. identify possible contradictions;
6. potentially extract structured custom attributes.

Therefore “we gave Graphiti the authoritative research document” does **not** imply “the graph representation is authoritative.” It remains a model-derived projection.

This aligns with the owner's desired boundary: Sol must retain semantic authority.

## 10. Custom ontology support is a strong fit

Graphiti supports Pydantic-defined custom entity and edge models.

Official docs allow:

```python
entity_types = {...}
edge_types = {...}
edge_type_map = {
    ("TypeA", "TypeB"): ["AllowedEdgeType"],
}
```

`edge_type_map` constrains which custom relationship types can be produced between entity-type pairs. Search can later filter on node labels and edge types.

For a Soma research pilot, plausible entities include:

```text
ResearchIteration
Finding
Hypothesis
Mechanism
Constraint
Experiment
Decision
SourceDocument
Dataset
Metric
```

Plausible semantic edges include:

```text
SUPPORTS
CONTRADICTS
FALSIFIES
SUPERSEDES
NARROWS
QUALIFIES
DEPENDS_ON
MOTIVATES
REPLICATES
FAILS_TO_REPLICATE
EVALUATES
```

These are hypotheses for a later ontology-design iteration, not an accepted schema yet.

Important nuance: custom ontology improves extraction discipline; it does not remove model judgment from extraction.

## 11. Namespacing is directly useful for Soma

Graphiti uses `group_id` as a graph namespace. Official docs describe namespaces as isolated graph environments within one Graphiti instance.

A natural Soma mapping is:

```text
one active repository/project -> one stable Graphiti group_id
```

This can prevent NSDN/Axon/Soma research facts from contaminating each other's retrieval.

Cross-project knowledge should not be silently merged merely because the graph backend can store multiple groups. If later cross-project research is desired, Sol can issue explicit searches across selected namespaces and merge results at the reasoning layer.

## 12. Search architecture

The core Graphiti search path is substantially richer than simple vector retrieval.

Official Graphiti search combines:

- semantic/vector similarity;
- BM25/full-text retrieval;
- Reciprocal Rank Fusion;
- optional graph-distance reranking from a focal node.

The advanced API exposes configurable `SearchConfig` / `SearchFilters` and can return graph entities across node, edge, episode and community scopes depending on recipe/configuration.

Search filters can constrain:

- entity/node types;
- edge types;
- connected node identities;
- source episode IDs;
- temporal fields including `valid_at` and `invalid_at`.

This is a strong match for the target failure: an old finding can be reached both by semantic similarity and by graph relationships even when its wording differs from the current research question.

## 13. Temporal model: useful but must not become scientific authority

Graphiti represents fact lifetime using `valid_at` / `invalid_at` plus ingestion-related timing.

This is attractive for changing knowledge. In a research programme we could distinguish:

```text
Research 012 proposes X
Research 020 tests X
Research 020 falsifies X under scope S
Research 031 narrows the rejected form into Y
```

However, Graphiti's normal contradiction/invalidation path is not a purely deterministic truth-maintenance system.

Current edge-resolution source shows an LLM response provides `duplicate_facts` and `contradicted_facts`. Those chosen candidates feed subsequent invalidation logic.

Therefore `invalid_at` is at least partly the result of **model adjudication**.

For ordinary agent memory that may be acceptable. For scientific research lineage it is too strong to use as an authority without safeguards.

## 14. Critical current issue: unrelated edge invalidation (#1728)

Open issue #1728, filed 2026-08-04 against behavior based on 0.29.3, reports a particularly relevant failure:

- duplicate candidate search remained scoped;
- invalidation candidate search could range across semantically similar edges in the whole `group_id`;
- contradiction judging receives bare fact strings without sufficient endpoint/entity context;
- a wrong model judgment can mark an unrelated still-valid fact with `invalid_at`;
- the reporter observed substantial collateral invalidation in a production graph.

The issue's mechanism is supported by current-source discussion in the report, and the issue remains open at the time of this audit.

For Soma, this is a **stop condition against trusting automatic invalidation as research truth**.

Even if Graphiti is adopted, a research fact must not disappear from default context simply because Graphiti's contradiction resolver decided another semantically similar fact superseded it.

## 15. Model dependence of contradiction detection (#1666)

Open issue #1666 reports measured degradation in contradiction detection when using a non-reasoning small model for Graphiti's edge dedupe/contradiction judge.

The reporter's test found duplicates remained comparatively reliable while contradiction identification degraded sharply.

Regardless of exact benchmark generality, this confirms an architectural point already visible in source:

```text
model behavior materially influences which facts Graphiti treats as contradicted
```

That is another reason Soma should encode scientific relationships explicitly and treat Graphiti's automatic temporal invalidation as a convenience projection, not source authority.

## 16. Fact triples: useful, but earlier provenance assumption was wrong

Official Graphiti docs expose `add_triplet(source_node, edge, target_node)` for manually adding a fact.

The current MCP exposes a simplified `add_triplet` taking:

```text
source_node_name
edge_name
fact
target_node_name
group_id
optional source/target UUIDs
```

It constructs a bare `EntityEdge` containing name/fact/group/source/target/created_at and delegates to core.

### Important correction

A stock MCP `add_triplet` does **not** create an episode and does not populate episode provenance.

The MCP's separate `get_episode_entities()` provenance tool works from episode UUIDs. Therefore a triplet inserted directly by the stock MCP cannot automatically be traced back through that episode mechanism.

This invalidates an optimistic statement from the preceding Soma research iteration that direct triplets were already the ideal provenance-preserving Sol-reviewed write path.

They are not, at least not through the stock MCP contract.

### Additional nuance

The Graphiti docs say direct triplet addition bypasses extraction, but Graphiti still performs entity/edge resolution and deduplication. The presence of `resolve_extracted_edge` in the core path means “bypasses extraction” should not be interpreted as “bypasses all LLM judgment.”

Before a Soma adapter uses direct triplets, its exact core behavior must be pinned and tested against contradiction/invalidation effects.

## 17. Provenance strategy implied for Soma

The safest candidate is currently one of these two forms:

### Option A — reviewed semantic episode

Sol writes a compact, reviewed semantic digest after finishing the authoritative research document. That digest includes stable document provenance and is ingested as an episode under a constrained research ontology.

Benefits:

- first-class episode provenance;
- Graphiti can relate facts back to an episode;
- historical source event is inspectable.

Risk:

- Graphiti still extracts/normalizes relationships with its LLM.

### Option B — thin Soma Graphiti adapter with explicit provenance attributes

Soma uses Graphiti core rather than stock MCP `add_triplet` and stores explicit attributes/identities such as:

```text
repo_name
research_path
research_sha256
iteration_id
source_section / locator
reviewed_by = Sol
reviewed_relation = true
```

Benefits:

- relationships are controller-reviewed rather than blind extraction;
- provenance can be exact.

Risk:

- requires a small amount of integration code and tests;
- must carefully avoid or control Graphiti's automatic invalidation path.

A hybrid of A+B may ultimately be best, but implementation is not yet authorized.

## 18. MCP server is officially experimental

The current Graphiti MCP README explicitly labels the MCP server **experimental**.

It provides useful tools for general agent memory:

- `add_memory`;
- `add_triplet`;
- `search_nodes`;
- `search_memory_facts`;
- episode retrieval/deletion;
- edge retrieval/deletion;
- saga summaries;
- community building;
- `get_episode_entities` provenance lookup.

But “official MCP exists” is not sufficient reason to plug it directly into Soma's trusted research workflow.

## 19. Critical current MCP issue: acknowledged write can be lost (#1707)

The stock MCP `add_memory` queues an episode and returns immediately.

Current source explicitly says the function returns immediately and processes episode addition in the background.

Open issue #1707 reports that a queued episode can later fail/drop while the caller has already received a successful “queued” response, with no failure signal returned to that caller.

This failure mode is unacceptable for Soma's proposed post-research checkpoint:

```text
research complete
→ Graphiti update says success
→ episode silently never becomes durable
```

Therefore a Soma integration needs an **acknowledged-completion verification** step rather than equating queue acceptance with successful graph update.

This can be solved by a thin adapter or explicit polling/verification, but stock `add_memory` alone does not provide the durability contract we need.

## 20. MCP search freshness problem (#1645) remains relevant

Open issue #1645 reports that the MCP fact search historically mixed invalidated/superseded facts with current facts, used a fixed recipe, capped results, and omitted richer ranking controls.

Current MCP source has improved date-range and edge-type filtering controls, but it still does not expose a simple semantic contract such as:

```text
current_facts_only = true
```

When no invalidation bounds are provided, `search_memory_facts` delegates to the normal Graphiti search and serializes returned edges.

For Soma this means the stock MCP response must not be interpreted as “these are the current governing research facts.”

A Soma wrapper can instead:

- query with a larger bounded candidate set;
- explicitly retain/display `invalid_at` status;
- filter current vs historical results according to the current research question;
- preserve superseded facts when historical reasoning needs them.

## 21. Reconciliation: the older `reference_time` issue has been fixed in current source

Issue #1661 reported that `EntityEdge.reference_time` was persisted but missing from read projections in an earlier 0.29.x state.

The current release notes include a fix for returning `reference_time`, and current `edge_db_queries.py` now explicitly projects:

```text
e.reference_time AS reference_time
```

Therefore #1661 should **not** be presented as a current known defect at the audited source state.

This is an example of why open-issue status alone is not sufficient; source/release reconciliation is required.

## 22. Security history and minimum version

Graphiti had a high-severity Cypher-injection vulnerability in search-filter handling affecting versions <=0.28.1. The official GitHub advisory states the issue was patched in 0.28.2.

The vulnerability was particularly relevant to MCP deployments because an LLM could be induced by prompt injection to call search tools with malicious type/filter values.

The Graphiti releases page also records an MCP release that raised the minimum Graphiti core requirement to the patched version.

Implication:

- never deploy an older Graphiti build for a Soma pilot;
- pin an audited version;
- do not expose the optional Graphiti service broadly;
- keep it project-local/private;
- treat search/filter arguments as untrusted input despite coming from an LLM.

## 23. Telemetry

Graphiti core emits anonymous initialization telemetry unless disabled.

Current source records provider/backend categories; the MCP README states anonymous system/configuration data is collected and graph content/API keys are not.

Official quick-start and MCP docs provide:

```text
GRAPHITI_TELEMETRY_ENABLED=false
```

For a private Soma research-map pilot, disable telemetry by default unless the owner explicitly wants it enabled.

## 24. Sagas

Current Graphiti source includes a `SagaNode` concept: an ordered group of related episodes.

Sagas support:

- membership (`HAS_EPISODE`);
- episode ordering;
- an incrementally generated LLM summary;
- separate ingestion-time and episode-time summary watermarks.

This may be useful for a research subprogramme such as:

```text
NSDN associative retrieval programme
Research 026 → ... → Research 038
```

But the saga summary is LLM-generated and therefore should remain **navigation only**. It is not a replacement for the research docs or reviewed semantic relations.

## 25. Communities

Graphiti can build communities over densely connected entities and generate higher-level community summaries.

This could eventually help broad research navigation (e.g. “all work related to bounded associative memory”), but it is unnecessary for the first Soma pilot and would add another generated-summary layer.

Defer communities until the basic exact-provenance/retrieval contract works.

## 26. Graphiti's benchmark claims

Official Graphiti documentation publishes strong retrieval numbers on LoCoMo and LongMemEval and cites associated papers.

Those numbers support Graphiti as a serious candidate, but they should not be treated as proof for Soma's specific workload. Our target is unusually strict:

- research documents rather than conversational memory;
- negative/falsifying knowledge has high value;
- historical supersession must not silently erase context;
- every material relation must be auditable back to source;
- a wrong graph edge must not override scientific source truth.

A Soma-specific known-answer evaluation remains necessary.

## 27. What Graphiti solves well for Soma

### Strong fit

1. **Semantic distance** — hybrid vector/BM25/graph retrieval can find old work with different wording.
2. **Relationship traversal** — research can be linked through mechanism/result/decision relationships rather than date alone.
3. **Provenance via episodes** — raw source events remain graph-addressable.
4. **Temporal history** — the data model retains validity/invalidation fields rather than destructively overwriting history.
5. **Custom ontology** — research-specific entities/relations can be constrained.
6. **Project isolation** — `group_id` maps naturally to repository/project boundaries.
7. **Incremental updates** — one new research iteration can update the map without rebuilding the whole corpus.
8. **Open source / Apache-2.0** — suitable for a local optional subsystem.

## 28. What Graphiti does not solve safely out of the box

### Material gaps for Soma research

1. **Automatic contradiction/invalidation is model-mediated** and currently has an open collateral-invalidation issue.
2. **Stock MCP direct triplets lack episode provenance.**
3. **Stock MCP episode writes are queue acknowledgements, not durable completion receipts.**
4. **Stock MCP search does not give a clean current-vs-history governing-fact contract.**
5. **Generated entity/relationship extraction can be wrong.**
6. **Model quality affects dedupe/contradiction behavior.**
7. **The MCP server is officially experimental.**
8. **Graph database/service operation adds complexity versus Soma's core.**

These are not reasons to reject Graphiti. They define the boundary of a safe integration.

## 29. Adversarial alternatives

### Alternative A — Use stock Graphiti MCP unchanged

**Rejected for research authority.**

It is easy to deploy, but the asynchronous write acknowledgment, missing direct-triplet episode provenance, current search semantics and automatic invalidation risks are too loose for the proposed scientific context map.

### Alternative B — Let Graphiti ingest every research doc and automatically decide the ontology

**Rejected as the primary authority path.**

This repeats the exact owner concern: mechanical/model extraction would decide which relationships matter. Graphiti could still ingest source material for retrieval, but important governing links must be Sol-reviewed or independently verified.

### Alternative C — Treat Graphiti temporal invalidation as canonical supersession

**Rejected.**

Graphiti's contradiction judge can be wrong, and issue #1728 directly attacks this assumption. Soma research should encode explicit semantic relationships such as `FALSIFIES`/`SUPERSEDES` rather than allowing `invalid_at` alone to decide scientific status.

### Alternative D — Reject Graphiti because it is imperfect

**Also rejected.**

The core capabilities—hybrid search, temporal graph, custom ontology, episode provenance and project namespacing—are unusually aligned with Soma's actual failure. A narrow optional adapter can isolate the risky parts without reimplementing the graph/retrieval system ourselves.

## 30. Provisional Soma architecture after deep audit

The best current hypothesis is:

```text
                         AUTHORITATIVE
                  repository research docs
                           path + hash
                               │
                               │ read / understand
                               ▼
                         Sol / ChatGPT
                    semantic adjudication
                               │
                   reviewed semantic update
                               ▼
       OPTIONAL / DERIVED GRAPHITI RESEARCH MAP
      group_id = stable Soma project/repository identity
                               │
           entities + semantic relations + provenance
                               │
                     hybrid/graph search
                               ▼
                     candidate old context
                               │
                         path/hash refs
                               ▼
                re-open authoritative docs
                               │
                               ▼
                       Sol verifies/uses
```

Graphiti failure must degrade retrieval convenience, **not erase or modify research truth**.

Continuation remains completely separate.

## 31. Recommended integration safety rules

If implementation is later authorized, the pilot should enforce these rules:

1. Graphiti is optional and isolated from Soma core startup.
2. No Codex integration of any kind.
3. One stable `group_id` per Soma project/repository.
4. Repository research docs remain canonical.
5. Every reviewed semantic edge must resolve to explicit source provenance: repo, path, SHA-256, iteration and preferably section/locator.
6. A Graphiti retrieval result is a navigation hint until the source document is re-read.
7. Do not let Graphiti automatic `invalid_at` silently define accepted/falsified/superseded research status.
8. Prefer explicit research relations (`FALSIFIES`, `SUPERSEDES`, `NARROWS`, etc.) over destructive/current-only semantics.
9. Every post-research graph update must have a completion receipt and read-back verification; queue acceptance is insufficient.
10. Retrieval must distinguish current governing relations from historical/superseded material explicitly.
11. Disable Graphiti telemetry by default.
12. Pin a security-fixed Graphiti version and validate upgrade changes before changing it.
13. Do not automatically ingest unrelated repo contents or secrets.
14. Do not make graph unavailability block ordinary Soma continuation or ordinary repository research.

## 32. Deployment recommendation for a future pilot

For the first pilot, prefer an isolated local service rather than embedding Graphiti in Soma's Python environment.

Current practical candidate:

```text
Graphiti core 0.29.3/current pinned release
+ FalkorDB
+ private/local binding
+ telemetry disabled
+ dedicated project namespaces
+ thin Soma adapter with verification
```

The official combined FalkorDB+MCP Docker image is useful as a quick reference deployment, but because the MCP server is experimental and its write/read semantics do not fully meet Soma's requirements, the final Soma surface should probably be a small controlled adapter over Graphiti core/FalkorDB rather than exposing every stock MCP tool unchanged.

Embedded FalkorDB Lite can be reconsidered later if its Python/platform requirements fit the target Soma runtime and persistence behavior is validated.

## 33. Final verdict of Iteration 06

**Graphiti remains the strongest current candidate for Soma's optional semantic research map, but only behind a Soma-specific trust boundary.**

The deep audit strengthens the case for Graphiti's core data/retrieval model while weakening the case for using its stock MCP server directly.

The key correction is:

> Graphiti should help Sol find and traverse research context; Graphiti must not decide scientific truth, silently retire governing facts, or serve as the only provenance record.

The most important upstream primitives worth reusing are:

- episode provenance;
- `group_id` project namespacing;
- custom entity/edge ontology;
- hybrid semantic + BM25 + graph retrieval;
- temporal fields/history;
- incremental graph updates.

The most important upstream behaviors to contain are:

- LLM-driven contradiction/invalidation;
- asynchronous unverified MCP ingestion;
- direct-triplet provenance limitations;
- stale/current result ambiguity in stock MCP search.

## 34. Next research question

Before any implementation, Iteration 07 should design and adversarially audit the **minimal Soma-reviewed Graphiti contract**:

1. exact entity/edge ontology;
2. exact provenance representation (`repo/path/hash/section/iteration`);
3. how Sol writes reviewed relationships without allowing Graphiti to silently change their scientific meaning;
4. whether Graphiti's automatic invalidation can be disabled/bypassed or must be isolated from reviewed edges;
5. exact write-completion/read-back verification;
6. exact query flow that returns current + historical relationships without stale-fact confusion;
7. a tiny known-answer NSDN test corpus that proves old governing research is recovered.

Only after that contract survives audit should a local Graphiti pilot be implemented.
