# Soma Knowledge Carry-Forward Research — Iteration 08

**Date:** 2026-08-24  
**Status:** COMPLETE — native Soma research/memory audit  
**Scope:** audit existing Research / Claim / Evidence / Decision / Context-Packet / Project-Memory capabilities against the same NSDN long-horizon benchmark used for Graphiti

## 1. Owner direction

Before doing more Graphiti work, determine whether Soma's already-existing research and knowledge machinery can solve the long-horizon scientific carry-forward problem by itself.

Do not revive an old subsystem merely because it exists. Test what is live, what is populated, what retrieval semantics it actually provides, and whether it can recover the same old governing NSDN findings that the standalone Graphiti pilot recovered.

Repository research documents remain authoritative. Continuation is out of scope and remains unchanged. Codex integration remains forbidden.

## 2. Evaluation baseline

Iteration 07 created a 30-fact, 15-question adversarial NSDN benchmark from real `docs/research/` findings. Graphiti hybrid retrieval over Sol-reviewed semantic facts achieved:

| Method | Hit@1 | Hit@3 | Hit@5 |
|---|---:|---:|---:|
| Graphiti hybrid | 60.0% | 93.3% | **100.0%** |
| vector only | 73.3% | 86.7% | 86.7% |
| full text only | 20.0% | 66.7% | 86.7% |

The exact 15 natural-language questions were reused unchanged for the native Soma comparison.

## 3. Native Soma knowledge surfaces found

Soma currently exposes three relevant but distinct project-scoped families:

1. **Research platform (`soma.research.v1`)**
   - immutable source archive / source versions;
   - claims and claim-evidence links;
   - research questions;
   - design candidates and decisions;
   - relationships;
   - context packets;
   - optional RAGFlow passage retrieval.

2. **Canonical project memory / knowledge vault**
   - decisions, lessons, preferences and other controller memory;
   - lifecycle state;
   - review state;
   - revision and integrity hashes;
   - source references / locators;
   - supersession links;
   - context-packet packaging.

3. **`search_knowledge` project knowledge projection**
   - another read projection over the same canonical 31-record NSDN knowledge corpus rather than a separate hidden semantic research index.

The generated repository wiki is separate from all three and remains primarily a structural/codebase map.

## 4. NSDN research-platform state

Live `research_health` for NSDN project:

`proj_repo_ee86415665bff49a2063068e`

reported:

```text
archive objects           7
sources                   7
source versions           7
analysis runs             0
research packets          0
claims                    0
evidence links            0
research questions        0
design candidates         0
design decisions          0
experiment proposals      0
generated summaries       0
relationships             0
audit events              0
context packets           4
semantic index            NOT CONFIGURED
```

`list_research_questions` returned `[]`.

`list_research_decisions` returned `[]`.

Therefore the rich structured research schema is real, but the ongoing NSDN research workflow did not populate it.

## 5. What `search_research` actually does

Source audit of `soma/research/service.py` establishes the current retrieval contract.

`ResearchPlatformService.build_context_packet()` starts with no passages. Semantic source retrieval occurs only when a `RagFlowGateway` is configured:

```text
RAGFlow configured
    -> retrieve chunks from project dataset
    -> map chunk to immutable source version
    -> attach citation / source hash / locator
    -> enrich structured overlay
```

When RAGFlow is absent, there is no semantic passage retrieval.

NSDN currently has no RAGFlow configured. `research_health` therefore reports the index as `not_configured`, and `rebuild_index()` would refuse because there is no RAGFlow service.

This is not a transient ranking problem. The semantic retrieval leg is absent.

### Structured overlay fallback

Source audit of `soma/research/store.py::build_overlay_context()` shows that claims, research questions, candidates and decisions are matched using the normalized **entire query as a SQL LIKE substring**.

That can be enriched when RAGFlow returns a source version linked to reviewed claims, but NSDN currently has:

- zero claims;
- zero evidence links;
- zero questions;
- zero decisions;
- zero relationships.

Consequently there is nothing for the overlay to contribute.

## 6. Empirical research-platform probes

The exact difficult question:

> What previous result rules out reusing generic dendritic routing as the new solution?

returned:

```text
retrieved_passages = []
citations          = []
```

Even the favorable literal query:

> Research 035 dendritic context gating

returned no passages or citations.

A full `build_context_packet` for the difficult query contained:

```text
retrieved_passages = []
citations          = []
claims              = []
evidence            = []
questions           = []
candidates          = []
decisions           = []
entity_ids          = []
```

Because RAGFlow is absent and the overlay tables are empty, this behavior is structural for the current NSDN state rather than an isolated query miss.

## 6A. Query-side persistence defect discovered during re-audit

A later source-level re-audit found a contract defect that was not captured by the initial benchmark.

The public `knowledge_query` surface presents `search_research` / `build_context_packet` as query/read operations. Both route through `ResearchPlatformService.build_context_packet()`, which calls `ResearchOverlayStore.build_overlay_context()`.

`build_overlay_context()` always calculates a context-packet identity and executes:

```sql
INSERT OR IGNORE INTO context_packets (...)
```

for each distinct query result. Therefore a nominal research search can persist derived state:

```text
knowledge_query(search_research)
    -> build_context_packet
    -> build_overlay_context
    -> INSERT OR IGNORE context_packets
```

The live re-audit stopped further `search_research` benchmarking once this behavior was proven, to avoid creating additional state merely by reading. There is no evidence that this mutation caused the Chat stream interruption observed during the audit; causation is unproven. The defect is nevertheless real and violates the intended read-only query boundary.

Per owner direction, no source repair is authorized merely because this dormant subsystem is defective. If any runtime portion of `soma.research` is later selected for reuse, making research search genuinely read-only and separating optional context-packet persistence from retrieval is a mandatory precondition.

## 7. Canonical project-memory state

Live project-memory health reported:

```text
canonical health       healthy
canonical count        31
indexed count          31
malformed              0
unadopted              0
integrity drift        0
generation             1
provider health        degraded
retrieval mode         catalog_lexical
```

The vault itself is mechanically healthy.

### Valuable native semantics already present

The data model is materially useful. Records can carry:

- `kind`;
- `authority_class`;
- current / disputed / rejected / archived lifecycle;
- `review_state`;
- `valid_from` / `valid_until`;
- revision and `content_sha256`;
- source references and locators;
- `supersedes_ids`.

Real NSDN examples prove that supersession is already useful:

- the standard UTF-8 correction supersedes the earlier custom binary-token interpretation;
- the clear-naming Research-002 revision supersedes the shorthand version;
- the full Stage-1 retrieval audit supersedes a series of provisional diagnostic hypotheses.

These are good native primitives and should not be discarded.

## 8. Why project-memory semantic retrieval is disabled

Source audit of `soma/knowledge_tools_integration.py::_memory_retrieval_state()` shows this is intentional.

The previously accepted Basic Memory provider could not prove which files belonged to a particular index generation. Soma therefore deliberately refuses to present that provider as authoritative semantic retrieval.

When provider membership cannot be proved, Soma publishes:

```text
provider_health = degraded
retrieval_mode  = catalog_lexical
```

This is a sound trust decision, but it means there is no semantic retrieval layer today.

`memory_context` does not solve this independently; it packages the result of the same memory search.

## 9. Canonical lexical retrieval behavior

Source audit of `soma/knowledge/memory_service.py::search()` confirms the current catalog retrieval requires all query terms to match literally.

The implementation itself warns when a natural-language multi-term query returns nothing:

> no record contains every query term; canonical lexical retrieval matches literal terms, not natural-language questions

This is exactly the failure mode being investigated: future research questions are usually semantically related to old findings without repeating their exact wording.

## 10. Exact 15-question benchmark replay

The same 15 natural-language questions used in Iteration 07 were replayed unchanged against native `memory_search`, with non-current records permitted so the native system received the most favorable fair chance.

Result:

```text
native project-memory exact-query retrieval
Hit@1 = 0 / 15
Hit@3 = 0 / 15
Hit@5 = 0 / 15
```

All fifteen calls returned zero records and the all-terms lexical warning.

This does **not** mean the vault is useless. It means its current retrieval contract is unsuitable for semantic future-question -> old-governing-fact recovery.

For comparison:

```text
Graphiti hybrid, same questions, reviewed 30-fact graph
Hit@5 = 15 / 15
```

## 11. Coverage/ingestion failure is separate from retrieval failure

The lexical failure is only half of the problem.

Favorable single-keyword probes reveal that the 31-record vault itself is concentrated in the early NSDN programme:

- Research 001-008 decisions;
- Stage-0 / Stage-1 authorization and audit state;
- Stage-1B / Stage-1C diagnostic lessons;
- early adversarial retrieval-diagnosis work;
- the freeze/reopen spatial-micro-lab decision;
- a later GPU-use preference.

Direct probes established:

```text
"035"          -> no record
"Research 037" -> no record
"Research 038" -> no record
```

A `REPORT` keyword returns early Stage-1 diagnostic records, not the Research-035 spent-REPORT constraint.

A `parity` keyword returns an early Stage-1 authorization record, not the Research-037C parity-before-timing rule.

Therefore most of the later gold facts are **not in canonical memory at all**. Even replacing lexical search with a perfect semantic retriever would not recover facts that were never ingested.

This confirms two independent gaps:

```text
Gap A: later research was not continuously written into native memory/research structures
Gap B: current native retrieval is not semantic
```

## 12. `search_knowledge` is not a hidden third solution

`knowledge_health` reports the same healthy 31-record corpus.

The hard natural-language query returned zero records.

A favorable `dendritic` query exposed the same early Research-004/005/006/008 and Stage-1 diagnostic records seen through `memory_search`.

Therefore `search_knowledge` is another projection over the same canonical knowledge population, not an independently populated semantic scientific index.

## 13. What the old research platform actually was

This audit corrects an important conceptual ambiguity.

The native `soma.research.v1` system was primarily designed as:

```text
immutable external/source archive
        +
RAGFlow passage retrieval
        +
reviewed claims / evidence / questions / decisions overlay
        +
context packet projection
```

That is useful research infrastructure, especially for literature/source provenance.

It is **not**, in its current design or populated state, the desired automatic long-horizon semantic relationship map over sequential repository research documents.

Therefore the earlier instinct not to revive it wholesale was justified.

## 14. Adversarial alternative: could we simply populate/fix the native system?

A plausible alternative is:

> The schemas are already good. Why not just start writing every research iteration into claims, evidence, questions and decisions, and turn semantic indexing back on?

That is technically plausible, but it is not a zero-work reuse path.

It would require at least:

1. a new reliable continuous ingestion workflow for every completed repository research iteration;
2. semantic indexing whose corpus membership and generation coverage can be proved;
3. semantic retrieval over changing vocabulary;
4. reviewed negative/falsifying/supersession relations;
5. rebuild semantics from authoritative docs;
6. known-answer evaluation comparable to the Graphiti benchmark.

At that point the main unsolved component is precisely the semantic mapping/retrieval layer under investigation.

The native schemas remain valuable, but their existence alone does not eliminate the need for that layer.

## 15. Native primitives worth retaining

The audit does **not** recommend deleting or ignoring the native knowledge work.

The following pieces are strong and directly reusable in a future design:

- stable project scoping;
- canonical vault semantics;
- immutable source versions;
- exact SHA-256 provenance;
- lifecycle and review state;
- explicit supersession;
- claim -> evidence representation;
- research question / decision types;
- citations and source locators;
- durable context-packet snapshots;
- fail-closed provider-health disclosure;
- refusal to call unprovable retrieval `semantic`.

These solve trust, provenance and lifecycle problems that Graphiti by itself does not solve as cleanly.

## 16. What should not be revived wholesale

Do not restore the old RAGFlow-centric research platform as the default solution merely to reuse existing code.

Do not make context packets a second continuation system.

Do not backfill every repository document mechanically into claims/decisions and call that understanding.

Do not re-enable an unprovable semantic provider merely to obtain vector search.

Do not treat canonical memory as the authoritative copy of research; repository `docs/research/` remains the source of truth.

## 17. Comparison with Graphiti after the audit

| Capability | Native research v1 | Native project memory | Graphiti pilot |
|---|---|---|---|
| Project scoping | strong | strong | workaround needed in tested Falkor path |
| Provenance / hashes | strong | strong | supplied by our adapter |
| Review / lifecycle | strong schema | strong live model | not sufficient by itself |
| Supersession | structured | live and useful | possible, but automatic invalidation is unsafe for authority |
| Claims / evidence / decisions | strong schema, unpopulated | coarse decision/lesson records | relation graph |
| Current NSDN coverage | 7 sources, overlay empty | 31 mostly early records | 30 selected gold facts for pilot |
| Semantic retrieval today | absent: RAGFlow not configured | deliberately disabled | working |
| Exact 15-query Hit@5 | structurally empty current packet | **0/15** | **15/15** |
| Source-of-truth role | no | no | no |

The systems are therefore complementary rather than interchangeable.

## 18. Iteration-08 verdict

**DO NOT REPLACE GRAPHITI WITH THE CURRENT NATIVE RESEARCH/MEMORY RETRIEVAL PATH.**

The user's earlier research work was not silly. The native data contracts contain several high-value trust and provenance primitives.

However, the system currently fails the actual long-horizon problem for two independent reasons:

1. later scientific research was never continuously represented there;
2. semantic retrieval is absent/disabled.

The exact native memory replay returned 0/15 results for the same questions on which the reviewed Graphiti pilot achieved 15/15 Hit@5.

The correct conclusion is not `discard native Soma` and not `discard Graphiti`.

The stronger direction is:

```text
AUTHORITATIVE
repository research docs
        |
        v
Sol / ChatGPT understands and adjudicates
        |
        +---- native Soma trust primitives
        |     project scope
        |     source hash / locator
        |     review state
        |     lifecycle / supersession
        |     claim/evidence/decision shapes where useful
        |
        +---- optional semantic relationship/retrieval layer
              Graphiti remains current leading candidate
        |
        v
future research query
        |
semantic candidate retrieval
        |
reopen exact authoritative source docs
        |
Sol reasons from verified evidence
```

## 19. Recommended next research step

Do not implement yet.

The next useful design research should determine the **minimum hybrid contract** rather than choosing one system wholesale:

- which native Soma fields should remain the durable trust/provenance envelope;
- which semantic relations actually need Graphiti;
- whether reviewed semantic facts should also be saved as tiny rebuildable sidecars under `docs/`;
- whether one Graphiti DB per project is preferable to relying on the currently defective Falkor `group_id` full-text path;
- how a completed research iteration updates this layer without mechanical semantic inference;
- how source-hash mismatch or graph loss causes safe rebuild/fallback;
- how retrieval explicitly distinguishes governing/current, historical, falsified, narrowed and superseded evidence.

Only after that contract is frozen should implementation be considered.
