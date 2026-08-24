# Soma Knowledge Carry-Forward Research — Iteration 09

**Date:** 2026-08-24  
**Status:** COMPLETE — minimum hybrid scientific contract selected and empirically validated  
**Scope:** define the smallest durable reviewed research-map contract that can preserve scientific meaning across long research sequences while keeping repository research documents authoritative and Graphiti disposable

## 1. Owner direction

The owner agreed with the hybrid direction after the native Soma research/memory re-audit.

The target remains:

```text
repository research docs = authoritative scientific record
Sol / ChatGPT            = semantic understanding and adjudication
Soma                     = project scope, provenance, health and safe workflow
Graphiti                  = optional derived semantic retrieval/index layer
```

The old RAGFlow-centric `soma.research.v1` runtime is not to be reactivated or repaired merely because some of its data types are useful. Its semantics may be reused where they improve the new contract.

Codex integration remains forbidden.

## 2. Interruption/duplicate lesson carried into this iteration

The preceding stream interruption produced two documents labelled Iteration 08. They were reconciled before this iteration began.

This is not proof that the old research subsystem caused the stream cut. The more plausible operational explanation is that one audit document had already been written before the stream context was lost, and the resumed thread no longer knew that exact write had occurred.

Iteration 09 therefore treats interruption safety as part of the knowledge-map contract rather than as incidental tooling behavior.

Before creating this document, the research directory was explicitly enumerated and confirmed to contain Iterations 01 through 08 only.

## 3. Evidence baseline

### 3.1 Graphiti pilot

Iteration 07 established that a 30-fact Sol-reviewed NSDN graph retrieved an expected governing fact on all 15 adversarial questions within the top five:

```text
Graphiti hybrid
Hit@1  60.0%
Hit@3  93.3%
Hit@5 100.0%
```

The graph used no LLM extraction or contradiction adjudication. Sol-reviewed facts were written directly as Graphiti entities/edges and embedded with local `BAAI/bge-small-en-v1.5`.

### 3.2 Native Soma audit

Iteration 08 established that:

- NSDN's rich `soma.research.v1` overlay was essentially unpopulated;
- RAGFlow semantic retrieval was not configured;
- the native project-memory semantic provider was deliberately disabled because index membership could not be proved;
- exact future-style natural-language queries returned 0/15 through current native memory retrieval;
- `search_research` was exposed as read-only but persisted `context_packets`, a real read/write contract defect;
- native provenance, review, lifecycle and supersession semantics are still useful design material.

### 3.3 Current NSDN research corpus

A live listing found 78 entries under `docs/research`, consisting of `.gitkeep` plus 77 Markdown research documents through Research 039A.

The standalone gold graph's 30 material facts came from 21 of those research documents.

This distinction matters: a production carry-forward layer must distinguish **reviewed with no material relation** from **never reviewed for carry-forward**. It must not infer that absence of graph edges means a document was irrelevant.

## 4. Design constraints

The minimum contract must satisfy all of the following:

1. repository research Markdown remains the scientific source of truth;
2. Sol decides which findings/constraints/relations are materially worth carrying forward;
3. no automatic LLM extraction is required to rebuild the map;
4. deleting Graphiti must not delete reviewed semantic judgments;
5. a changed research document must make its prior semantic projection visibly stale;
6. query/search operations must be genuinely read-only;
7. a stream cut after any write stage must be detectable and resumable;
8. repeating a completed update must not create duplicate semantic facts;
9. project isolation must not rely on the currently defective FalkorDB `group_id` full-text path;
10. Graphiti failure must reduce retrieval convenience, not research durability;
11. no RAGFlow deployment is required;
12. no continuation redesign is involved.

## 5. Alternatives tested

### A. Graphiti-only semantic state

Rejected as the durable contract.

It gives excellent retrieval, but if the Graphiti database is deleted the Sol-reviewed semantic judgments disappear. Reconstructing them would require a new semantic interpretation of all historical research documents, which violates the desired deterministic recovery boundary.

### B. Reuse the old `soma.research.v1` SQLite overlay as the canonical semantic map

Rejected as the primary path.

It would revive a broad subsystem with source archives, RAGFlow lifecycle, context packets, research packets, candidate/experiment structures and known read-side mutation behavior. It also changes the authority model toward a second structured research store.

### C. Reuse canonical project-memory vault records for every scientific relation

Rejected as the primary durable representation.

The vault has good source/lifecycle/supersession semantics, but creating a separate canonical memory record for every scientific relation unnecessarily duplicates the repository research record.

### D. Put the semantic projection inline inside each research Markdown document

Not selected.

Co-location is attractive, but exact whole-document provenance becomes awkward because a semantic block containing the document's own hash would be self-referential. The block also adds machine-oriented material to scientific reports.

### E. One reviewed sidecar per research document, stored under `docs/`

**Selected.**

A sidecar is derived, compact, source-hash-bound, rebuildable and can be validated independently. It does not replace the Markdown report. If the report changes, the sidecar becomes stale rather than silently following it.

## 6. Selected durable architecture

```text
AUTHORITATIVE
research Markdown
      |
      | Sol reads/writes and understands
      v
REVIEWED DERIVED PROJECTION
small deterministic sidecar under docs/
      |
      | schema + hash + exact anchor validation
      v
DISPOSABLE SEMANTIC INDEX
Graphiti + local embeddings
      |
      v
future semantic query
      |
      v
candidate reviewed relations
      |
      v
reopen exact Markdown source
      |
      v
Sol reasons from authoritative evidence
```

The sidecar is durable reviewed metadata, not independent scientific authority.

## 7. Sidecar placement

Preferred repository-local convention:

```text
docs/research/<research-file>.md
docs/research/_soma_map/<research-file-stem>.json
```

For projects with another research root, `_soma_map/` sits under that research root.

Reasons:

- keeps machine-oriented files out of the main research-file listing;
- sidecar and source remain naturally colocated;
- no machine-specific project identity is embedded in the file path;
- discovery is deterministic;
- deleting the external Graphiti database does not affect sidecars.

## 8. Runtime project identity does not belong inside the sidecar

The empirical prototype initially stored:

```text
project_id
repo_name
```

inside every sidecar.

That is unnecessary and was pruned from the minimum design.

A sidecar already lives inside one bound Git repository. Soma's runtime `ProjectScope` should determine which repository/database is being used. Embedding a machine/runtime-specific project identifier in durable scientific metadata would reduce portability across clones, moves or future scope reconstruction.

At Graphiti sync time, Soma may attach the current project identity to the derived graph records. It is not part of the source-side semantic record.

## 9. Minimum sidecar envelope

Proposed v1 shape:

```json
{
  "schema_version": "soma.research-map.v1",
  "source": {
    "path": "docs/research/038_end_to_end_associative_geometry_attribution_preregistration.md",
    "sha256": "<exact Markdown SHA-256>"
  },
  "review": {
    "state": "reviewed",
    "controller": "Sol"
  },
  "relations": []
}
```

No timestamps are required in the durable representation. Omitting generated timestamps makes repeated semantic review output capable of being byte-identical and avoids turning bookkeeping into scientific identity.

A sidecar with `relations: []` is valid and means:

> Sol reviewed this completed research document for carry-forward significance and found no material semantic relation worth indexing.

That is materially different from a missing sidecar, which means carry-forward review has not been proven.

## 10. Minimum relation record

```json
{
  "relation_id": "rel_<deterministic-id>",
  "subject": {
    "key": "research:038",
    "label": "Research 038"
  },
  "predicate": "FORBIDS",
  "object": {
    "key": "mechanism:generic-upstream-dendritic-gating",
    "label": "generic upstream dendritic gating revival"
  },
  "statement": "Research 038 must not relabel generic upstream dendritic/context gating as a new solution because that formulation was already directly tested and failed to earn specificity credit.",
  "locator": {
    "anchor": "must therefore not relabel generic upstream dendritic gating as a new solution"
  },
  "lifecycle": "current",
  "supersedes": []
}
```

### Why each field survives the minimum test

- `relation_id`: stable identity for idempotent graph writes and later supersession links;
- `subject.key` / `object.key`: deliberate semantic identity, not merely display text;
- labels: human-readable retrieval output;
- `predicate`: preserves relationship meaning;
- `statement`: preserves the nuanced scientific conclusion and supplies the main semantic-retrieval text;
- exact `anchor`: allows the controller to relocate the evidence inside the authoritative report;
- `lifecycle`: explicit status when the relation itself is disputed/rejected/archived;
- `supersedes`: allows later research to replace an earlier semantic relation without rewriting the old sealed sidecar.

The adapter can calculate line number and anchor SHA at validation/sync time. Persisting those derived values in the sidecar is not necessary.

## 11. Deterministic relation identity

A relation ID should be derived from stable semantic/source components rather than a random UUID or timestamp.

Candidate identity input:

```text
source relative path
+ subject key
+ predicate
+ object key
```

The repository/project scope is added when deriving the Graphiti UUID, not baked into the portable sidecar identity.

Implications:

- repeating an interrupted sidecar generation produces the same relation identity;
- re-running Graphiti sync upserts the same edge;
- a genuinely changed predicate/object becomes a different relation rather than silently mutating history;
- explicit `supersedes` links can retire the prior relation safely.

## 12. Predicate vocabulary

The current 30-fact NSDN gold set empirically used only 11 predicates:

```text
ALLOWS       1
CONSTRAINS   2
FALSIFIES    2
FORBIDS      6
LIMITS       1
MOTIVATES    1
NARROWS      2
PRESERVES    2
QUALIFIES    8
REQUIRES     3
SUPPORTS     1
```

These distinctions should not be collapsed to generic `RELATED_TO`; the differences are scientifically meaningful.

The minimum v1 vocabulary should preserve those 11 and add `SUPERSEDES`, which is required for lifecycle recovery even though the 30-fact retrieval benchmark did not need it.

Additional predicates such as `CONTRADICTS`, `REPLICATES`, `FAILS_TO_REPLICATE` or `DEPENDS_ON` can be added in a schema-compatible later revision when a real research case requires them. Do not pre-populate a large ontology merely because Graphiti supports one.

## 13. Lifecycle and supersession

Reuse the strongest principle from Soma canonical memory:

> supersession is established by the successor's link; correctness must not depend on rewriting the predecessor.

For research-map relations:

```text
old sidecar remains immutable historical record
new sidecar relation carries supersedes=[old_relation_id]
        ↓
effective state of old relation becomes superseded
```

This avoids rewriting sealed research history and survives interruption between successor creation and any derived projection update.

Automatic Graphiti `invalid_at` is **not** the source of this state. Scientific supersession comes from reviewed sidecar links.

## 14. Source provenance and stale detection

The sidecar stores the exact whole-file SHA-256 of its source Markdown.

Before any relation is accepted into Graphiti:

1. resolve the sidecar's relative source path inside the bound repository;
2. compute the live file SHA-256;
3. require exact equality with `source.sha256`;
4. require each exact anchor to occur in the file;
5. reject duplicate relation IDs;
6. validate the predicate vocabulary and schema.

If the Markdown changes after semantic review:

```text
source SHA mismatch
        ↓
sidecar = stale
        ↓
do not treat its relations as current verified map input
        ↓
Sol reopens revised source and re-adjudicates
```

A formatting-only edit may therefore require re-review. That is intentionally conservative. Research reports are normally sealed; silent semantic carry-forward from edited evidence is a worse failure than requiring a small recheck.

## 15. Coverage proof

The old Basic Memory semantic provider was disabled partly because Soma could not prove which canonical files belonged to an index generation.

The sidecar architecture can prove membership deterministically.

For each configured research root, health can report:

```text
research_markdown_count
reviewed_sidecar_count
missing_sidecar_count
stale_sidecar_count
relation_count
sidecar_generation
Graphiti_generation
```

`sidecar_generation` can be the SHA-256 of the sorted `(sidecar path, sidecar content SHA-256)` manifest.

Graphiti sync writes the same generation marker into its local derived state.

Semantic retrieval is fully healthy only when:

```text
stale_sidecar_count = 0
missing_sidecar_count = 0
graph_generation = sidecar_generation
```

During staged historical backfill, health should report `partial`, not pretend coverage is complete.

## 16. Query contract must be genuinely read-only

The old `search_research` bug must not be reproduced.

A future semantic query operation should:

```text
query Graphiti
→ validate/attach source-sidecar state
→ return candidates
```

and perform **zero persistent writes**.

No context-packet insertion, query logging, automatic invalidation or graph update is permitted through the query path.

If implemented through Soma's existing public gateway, a likely operation would be conceptually:

```text
knowledge_query(operation="research_map_search", ...)
```

with a separate explicit action for synchronization/rebuild.

The exact public operation name is an implementation decision, not frozen by this research iteration.

## 17. Retrieval result semantics

A Graphiti hit is a **candidate context relation**, not scientific truth.

A useful result record should expose:

```text
relation_id
subject / predicate / object
statement
effective lifecycle
source path
source SHA
source locator
retrieval score/rank
sidecar validity
```

Controller flow:

```text
future research question
      ↓
Graphiti candidate retrieval
      ↓
Sol sees governing + historical candidates
      ↓
reopen source Markdown for material facts used in reasoning
      ↓
verify source/hash/anchor
      ↓
reason from source
```

Do not automatically hide falsified/historical relations merely because they are old. The whole failure being addressed is loss of old constraints.

## 18. Graphiti mapping

The successful pilot supports a simple edge-centric mapping:

```text
subject key/label → EntityNode
object key/label  → EntityNode
relation          → EntityEdge
statement         → edge fact / embedding text
sidecar provenance→ edge attributes
```

Graph attributes should include at least:

```text
relation_id
source_path
source_sha256
sidecar_sha256
locator anchor
reviewed_by = Sol
effective lifecycle
```

Embeddings remain derived and are rebuilt locally.

No Graphiti LLM extraction, `add_episode()` interpretation, stock MCP `add_triplet()` resolution or automatic contradiction invalidation is required for this workflow.

## 19. Project isolation

Until the tested FalkorDB `group_id` full-text defect is resolved and independently revalidated, use:

```text
one Graphiti database per Soma project/repository
```

rather than one shared graph partitioned only by `group_id`.

This is operationally simple for the owner's small number of active research repositories and removes cross-project retrieval risk from the first implementation.

The sidecars themselves remain repository-local and do not contain the runtime DB identity.

## 20. Update transaction

A completed research iteration has three durable/derived stages:

```text
A. authoritative research Markdown saved
B. reviewed sidecar saved and validated
C. Graphiti synchronized and read back
```

### Stage A → B

Sol semantically reviews the final saved report and emits only material carry-forward relations. The sidecar is written atomically through repository tooling.

### Stage B → C

The adapter validates all hashes/anchors and writes deterministic nodes/edges. Completion is not a queue acknowledgment; it requires graph read-back of the expected relation IDs and generation marker.

### Failure semantics

- cut before A completes: ordinary research-doc recovery;
- cut after A but before B: health shows a missing sidecar;
- cut after B but before C: graph generation does not match sidecar generation;
- repeating B produces the same deterministic file;
- repeating C must be idempotent;
- Graphiti unavailable: B remains durable, C is visibly pending/degraded and can be rebuilt later.

Graphiti unavailability must not invalidate the scientific report.

## 21. Empirical hybrid-contract probe

A new standalone research harness was created outside both repositories:

```text
D:\Services\GraphitiPilot\hybrid_contract_probe.py
```

Generated sidecar corpus:

```text
D:\Services\GraphitiPilot\hybrid_contract_sidecars\
```

Machine-readable result:

```text
D:\Services\GraphitiPilot\hybrid_contract_probe_results.json
```

Durable execution run:

```text
20260824T123808Z_executable_profile_47875164
```

### 21.1 Source corpus

The probe parsed the same 30 Sol-reviewed facts and 15 adversarial questions used by Iteration 07, then grouped the facts by source Markdown.

Result:

```text
sidecar files = 21
relations     = 30
predicates    = 11 observed predicates
```

### 21.2 Deterministic sidecar rewrite

The complete sidecar set was generated twice from the same reviewed facts.

Result:

```text
deterministic_rewrite = true
```

The aggregate byte digest was identical across generations.

This directly reduces duplicate-document risk after a stream interruption: repeating a completed semantic projection does not create a new semantic identity merely because the controller resumed.

### 21.3 Stale-source rejection

The probe deliberately replaced one sidecar's source SHA with 64 zeroes and attempted validation.

Result:

```text
stale_source_rejected = true
error = STALE_SOURCE .../_stale_probe.json
```

The invalid sidecar was rejected before graph construction.

### 21.4 Idempotent graph replay

The 30 validated sidecar relations were written to a fresh FalkorDB-Lite Graphiti database using deterministic node/edge UUIDs.

After first write:

```text
edge count = 30
```

The exact same relation set was written a second time.

After second write:

```text
edge count = 30
duplicate_save_error = none
```

Therefore the tested low-level Graphiti/Falkor path is idempotent for these deterministic edge identities.

This is particularly important after the observed Iteration-08 stream-cut duplicate.

### 21.5 Retrieval after complete Graphiti loss/rebuild

The graph was rebuilt solely from the generated sidecars, not from the hard-coded previous graph state, and the exact same 15 adversarial questions were replayed.

Result:

```text
Hit@1 = 60.0%
Hit@3 = 93.3%
Hit@5 = 100.0%
MRR   = 0.7611
mean hybrid retrieval ≈ 61.06 ms
```

Per-query expected-fact ranks:

```text
3, 2, 1, 1, 2, 2, 4, 1, 1, 1, 1, 1, 1, 3, 1
```

This preserves the headline Iteration-07 retrieval result while adding deterministic recoverability.

## 22. What the probe establishes

The minimum hybrid architecture can preserve the exact property we need:

```text
review once semantically
        ↓
persist reviewed relations durably beside research
        ↓
destroy Graphiti completely
        ↓
rebuild without semantic re-extraction
        ↓
recover the same long-horizon constraints
```

It also demonstrates that the proposed update can be replay-safe under the tested Graphiti low-level persistence path.

## 23. What the probe does not establish

It does not yet prove:

- retrieval quality with hundreds or thousands of reviewed relations;
- the best exact predicate vocabulary beyond the observed corpus;
- how much historical backfill is worth performing initially;
- concurrency behavior if two research sessions update the same sidecar simultaneously;
- production lifecycle/service behavior for Graphiti;
- whether a future Graphiti release fixes the `group_id` defect;
- whether a stronger local embedding model materially improves ranking.

None of those uncertainties requires changing the selected durability boundary.

## 24. Adversarial alternative: skip sidecars and regenerate semantics from Markdown when needed

Rejected.

This would save files but recreate the exact long-horizon problem in another form. A future controller/model could interpret old research differently, omit negative findings or lose the original reviewed relationship judgment. The map would no longer be deterministically rebuildable.

The sidecar cost is small: one compact reviewed projection per research report, often with zero or only a few material relations.

## 25. Adversarial alternative: put every sentence/result into the map

Rejected.

The owner explicitly does not want mechanical knowledge linking. The purpose is not to vectorize the whole research archive.

Workflow rule:

> Every completed research document receives a Sol carry-forward review, but only materially useful scientific relationships are written as relations.

An empty reviewed sidecar is better than mechanically manufacturing low-value edges.

## 26. Reuse from old Soma work

The selected design reuses **principles**, not the old research runtime:

### Reused

- exact project/repository scoping at runtime;
- source hashes and locators;
- reviewed vs unreviewed distinction;
- lifecycle vocabulary where needed;
- successor-owned supersession links;
- fail-closed health reporting;
- deterministic IDs/idempotency;
- clear separation between canonical source and derived index.

### Not reused as runtime dependencies

- RAGFlow;
- research SQLite overlay as scientific authority;
- persistent query context packets;
- source-archive duplication for repository research Markdown;
- research candidates/experiment/generated-summary tables;
- old semantic-provider path.

## 27. Minimum health contract

A future optional research-map capability should be able to answer at least:

```text
configured research roots
research Markdown count
reviewed sidecar count
missing sidecar count
stale sidecar count
relation count
sidecar generation hash
Graphiti availability
Graphiti relation count
Graphiti generation hash
sync state: healthy / partial / stale / unavailable
```

This health surface is more important than pretending semantic search is always available.

If membership cannot be proved, publish partial/degraded state rather than silently returning incomplete context.

## 28. Recommended implementation boundary

If the owner later authorizes implementation, the first implementation should be deliberately thin:

1. sidecar schema + validator;
2. sidecar discovery and generation/coverage health;
3. isolated Graphiti/FalkorDB adapter with local embeddings and no LLM;
4. deterministic sync/rebuild/read-back verification;
5. read-only semantic search returning provenance-rich candidates;
6. known-answer acceptance test using the current NSDN 30-fact / 15-query corpus.

Do **not** begin by repairing the old research platform or integrating Graphiti's full MCP/automatic extraction stack.

## 29. Iteration-09 verdict

**PASS — FREEZE THE HYBRID DURABILITY BOUNDARY FOR THE NEXT DESIGN/IMPLEMENTATION STAGE.**

The strongest current architecture is:

```text
research Markdown
    = authoritative scientific truth

reviewed sidecar under docs/
    = durable Sol-authored semantic projection

Soma
    = repo scope + validation + coverage health + synchronization contract

Graphiti/FalkorDB + local embeddings
    = disposable semantic index and hybrid retrieval

Sol
    = decides relationships and verifies retrieved sources before reasoning
```

The standalone probe proves that this architecture can regenerate the 30-fact graph from durable reviewed sidecars, reject stale provenance, tolerate repeated synchronization without duplicates, and preserve 100% Hit@5 on the existing adversarial benchmark.

The old `soma.research.v1` runtime should remain dormant unless a separate future requirement genuinely needs its external-source archive/RAGFlow-oriented functions.

## 30. Next research question

Before source implementation, the remaining useful research is a **scale/backfill and operational acceptance design**:

- how many historical research docs should be manually backfilled initially;
- how to define full vs partial semantic coverage across the 77 current NSDN research Markdown documents;
- how many relations/distractors are required for a credible scale gate;
- exact acceptance thresholds for recall, negative/falsification recall, stale detection, rebuild equivalence and latency;
- concurrency/atomicity behavior for sidecar creation;
- local Graphiti service lifecycle and storage location;
- exact safe fallback when Graphiti is unavailable;
- whether to run the map update automatically as a finishing step after every completed research iteration once the optional feature is enabled.

Only after that acceptance contract is frozen should production implementation begin.
