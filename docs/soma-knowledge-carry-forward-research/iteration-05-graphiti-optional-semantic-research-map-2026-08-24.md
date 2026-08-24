# Soma Knowledge Carry-Forward Research — Iteration 05

**Date:** 2026-08-24  
**Status:** research architecture candidate — owner direction incorporated  
**Programme scope:** long-horizon research context coverage  
**Owner boundary:** Codex integration with Soma is forbidden  
**Candidate:** Graphiti as an optional, non-authoritative semantic research map

## 1. Owner correction and design intent

The owner rejected all Codex integration with Soma and clarified the desired direction:

- Soma continuation remains unchanged and continues to provide durable handoff/re-entry;
- research continues to be recorded in repository `docs/`;
- Graphiti may be used as an **optional research workflow**;
- after a research iteration is understood and written, Sol/ChatGPT should update the semantic map;
- research/knowledge relationships that require understanding must not be inferred only by mechanical filename, chronology, keyword, or parser rules;
- the map should help later Sol recover old-but-governing findings, relationships, contradictions, supersession, and research lineage.

This iteration evaluates that architecture specifically.

## 2. Hard boundary: no Codex integration

Codex is removed from the Soma solution space.

Soma must not add, invoke, embed, route through, depend on, or configure:

- Codex CLI;
- Codex App Server;
- Codex APIs/model generation;
- Codex subagents;
- Codex-derived runtime or memory components.

This owner boundary has also been corrected in `AGENTS.md`.

External observations about other systems may remain historical research evidence, but they are not implementation candidates for Soma.

## 3. Authority model

The proposed Graphiti role is deliberately narrow:

```text
repository research docs = authoritative durable research record
Soma continuation        = durable current handoff/re-entry
Sol / ChatGPT             = semantic understanding and relationship judgment
Graphiti                  = optional derived semantic map + retrieval aid
```

Graphiti must not become:

- a replacement for repository research documents;
- a replacement for continuation;
- an authority that can override source documents;
- an autonomous research planner;
- a hidden next-action engine;
- a reason for Soma to trust mechanically generated relationships.

If Graphiti and the repository research source disagree, the repository source wins.

## 4. Why Graphiti fits the problem

Graphiti is a temporal knowledge-graph framework designed around discrete ingestion events called **episodes**. Current documentation states that episodes may be text, message, or structured JSON and that graph entities/facts retain links to the episodes from which they were produced. This gives Graphiti a native provenance concept rather than only a vector similarity result.

Graphiti also supports:

- `group_id` isolation;
- semantic and keyword/graph search;
- fact search with edge-type filters;
- `valid_at` / `invalid_at` temporal filtering;
- explicit episode timestamps;
- ordered `saga` membership and predecessor episode links;
- custom entity types;
- custom edge/fact types;
- edge-type maps constraining which relationship types are allowed between entity classes;
- direct `add_triplet` insertion that bypasses ordinary episode extraction;
- provenance retrieval for entities/facts created from specific episodes.

Sources reviewed:

- Graphiti adding-episodes documentation: https://help.getzep.com/graphiti/core-concepts/adding-episodes
- Graphiti core source: https://github.com/getzep/graphiti/blob/main/graphiti_core/graphiti.py
- Graphiti MCP server: https://github.com/getzep/graphiti/blob/main/mcp_server/src/graphiti_mcp_server.py
- Graphiti MCP README: https://github.com/getzep/graphiti/blob/main/mcp_server/README.md
- Graphiti custom edge types: https://github.com/getzep/graphiti/blob/main/mcp_server/src/models/edge_types.py

These facilities map naturally to long research programmes where an old result can remain relevant even after many later iterations.

## 5. Important Graphiti limitation

Graphiti's normal `add_episode` / MCP `add_memory` path is not purely mechanical storage.

It invokes an LLM-backed extraction/resolution pipeline to identify entities, facts, duplicates and contradictions. The current MCP can accept custom extraction instructions and configured entity/edge types, but extraction remains model-mediated.

That is useful for convenience but conflicts with the owner's requirement if it is treated as the sole authority for semantic research relationships.

Therefore automatic extraction should not be trusted as the reviewed research map by itself.

## 6. Preferred workflow: understand first, graph second

The proposed optional research workflow is:

```text
1. Research normally.
2. Verify evidence and draw conclusions in Sol.
3. Save the completed research iteration under repository docs/.
4. Sol identifies the materially useful semantic relationships.
5. Update Graphiti with the research episode + reviewed semantic relations.
6. Verify the graph update succeeded.
7. Future research uses Graphiti to discover relevant historical nodes/facts.
8. Before relying on a retrieved fact, reopen/verify the linked repository research source when material.
```

The critical ordering is:

```text
UNDERSTAND → RECORD SOURCE → MAP SEMANTICS
```

not:

```text
PARSE FILE → ASSUME PARSER GRAPH = KNOWLEDGE
```

## 7. What Sol should decide semantically

After completing a research iteration, Sol should decide which relations materially help future reasoning.

Candidate relation vocabulary for evaluation:

```text
SUPPORTS
CONTRADICTS
FALSIFIES
REPLICATES
FAILS_TO_REPLICATE
SUPERSEDES
NARROWS
QUALIFIES
DEPENDS_ON
DERIVED_FROM
TESTS
IMPLEMENTS
VALIDATES
INVALIDATES
REQUIRES
GOVERNS
MOTIVATES
RELATED_TO
```

These names are provisional and should remain small. The objective is not to encode every sentence.

The graph should emphasize relationships whose loss could materially change future research decisions.

Examples:

```text
Research 035
  FALSIFIES
  upstream dendritic/context-gating formulation

Research 038
  NARROWS
  admissible future routing mechanisms

Research 038
  DEPENDS_ON
  Research 035 result

future dynamic-spine hypothesis
  MUST_NOT_REPEAT / constrained-by equivalent
  generic upstream gating already tested in Research 035
```

The exact ontology needs testing; no implementation ontology is approved yet.

## 8. Distinguish episodes from reviewed semantic links

A useful Graphiti integration should preserve two conceptual layers.

### Layer A — research episode/provenance

Each completed research iteration can be represented as one Graphiti episode containing bounded source material or a Sol-authored research summary plus exact repository identity:

- repository/project identity;
- research iteration identifier;
- document path;
- document SHA-256;
- research date/reference time;
- title;
- optional current conclusion summary.

The episode provides temporal and provenance anchoring.

### Layer B — Sol-reviewed relations

Material relationships are then explicitly supplied or confirmed by Sol.

Graphiti's `add_triplet` operation is relevant because it bypasses ordinary extraction and writes a source-entity → fact → target-entity relationship directly while still using Graphiti for entity resolution and embeddings.

For stronger provenance, reviewed relations should themselves link back to a stable ResearchDocument/ResearchIteration node or otherwise carry the exact source path/hash in a way the integration can verify.

This may require a thin Soma adapter around Graphiti rather than exposing raw Graphiti MCP calls directly.

## 9. Project and research-line isolation

Graphiti `group_id` provides a natural hard partition.

Candidate mapping:

```text
group_id = stable Soma project/repository identity
```

Research programmes inside one project can additionally use Graphiti's current `saga` feature when sequential ordering is useful.

Conceptually:

```text
project/group: NSDN
saga: associative-retrieval-programme
episodes: Research 034 → 035 → 035A → ... → 038
```

Saga membership should be a navigation aid, not authority. A research result may relate across sagas or programmes.

## 10. Retrieval workflow

Before beginning or materially redirecting a research question, the optional research context step could be:

```text
current research question
        ↓
Graphiti search_memory_facts / node search
        ↓
historical concepts + related findings
        ↓
graph neighborhood / temporal relations
        ↓
source document references
        ↓
Soma repo read of exact authoritative docs/passages
        ↓
Sol reasons with verified evidence
```

This directly targets the observed failure where early research exists but falls outside later effective context.

Graphiti therefore acts as a **semantic recall/navigation layer**, not a truth oracle.

## 11. Negative knowledge should be first-class

The use case especially benefits from preserving negative research knowledge:

- hypothesis falsified;
- approach failed;
- result did not replicate;
- mechanism was ruled out under a specific scope;
- candidate was superseded;
- later research narrowed the admissible design space.

Graphiti's temporal facts retain historical validity rather than requiring destructive overwrite, which is attractive for this use case.

However, the Graphiti MCP has a currently reported limitation: one July 2026 issue notes that its default search recipe can return facts that have since been superseded and exposes limited search-ranking configurability. Therefore Soma must not assume the stock MCP's default top results automatically equal the current governing truth.

Source: https://github.com/getzep/graphiti/issues/1645

A Soma integration should explicitly test current-vs-invalidated fact behavior.

## 12. Backend / deployment finding

Graphiti itself supports Python 3.10+, but its embedded FalkorDB Lite option currently requires Python 3.12+.

Current Graphiti quick-start source shows FalkorDB Lite as an embedded option using an `AsyncFalkorDB` client, while FalkorDB's own documentation describes the embedded database as self-contained and persistent.

Sources:

- https://github.com/getzep/graphiti/blob/main/examples/quickstart/quickstart_falkordb.py
- https://github.com/FalkorDB/docs/blob/main/operations/falkordblite/falkordblite-py.md
- https://github.com/getzep/graphiti/blob/main/pyproject.toml

Current Soma declares Python `>=3.10` and has a deliberately small base dependency set (`fastmcp`, `pydantic`, `pyyaml`).

Therefore Graphiti should initially be isolated as an **optional workflow/runtime**, not dropped into Soma's core base dependencies.

Possible pilot deployment options:

1. separate Python 3.12 Graphiti environment using FalkorDB Lite;
2. Graphiti MCP + FalkorDB via a separately managed local service/container;
3. direct Graphiti-core integration behind a Soma optional adapter later, only if the pilot validates the approach.

No deployment choice is approved yet.

## 13. Why optional is the correct boundary

The system should continue functioning if Graphiti is absent, stale, rebuilding or temporarily unavailable.

Research truth remains in `docs/`.

Continuation still resumes current work.

Without Graphiti, Sol can fall back to repository search/read, although long-horizon recall may be less efficient.

This avoids making an experimental retrieval component a single point of failure.

## 14. Candidate Soma workflow contract

Conceptual only:

```text
research_finish
    -> save research doc
    -> optional semantic_map_update
         input: project + exact research doc identity
         semantic content: chosen by Sol
         output: Graphiti episode/fact IDs + provenance refs
```

At the start of later research:

```text
research_context
    -> query Graphiti if enabled/healthy
    -> retrieve candidate facts/nodes/relations
    -> resolve repository source refs
    -> verify material claims against docs
    -> provide bounded context to Sol
```

The semantic map update should be an explicit normal tool operation made by Sol after the research conclusion, not a hidden automatic parser that runs merely because a Markdown file changed.

## 15. Adversarial checks

### A — Graphiti hallucinates a relationship during automatic episode extraction

Expected behavior: that extracted relation is non-authoritative; it cannot override the research doc. A Sol-reviewed relation or source verification is required for material use.

### B — old false hypothesis remains semantically similar to the new query

Expected behavior: graph should expose the falsification/supersession edge and the source research; future Sol verifies it rather than treating similarity as support.

### C — Graphiti unavailable

Expected behavior: research can continue using repository sources and continuation. Graphiti failure is degraded recall convenience, not loss of truth.

### D — new research overturns an old conclusion

Expected behavior: preserve history, add temporal/supersession relationship, retain provenance to both research iterations, and make the current relationship discoverable.

### E — Sol does not understand a claimed relationship sufficiently

Expected behavior: do not invent the edge. Preserve the source research and leave relationship uncertainty explicit.

## 16. Provisional conclusion

Graphiti is now the strongest candidate for the optional long-horizon research context map.

The owner-proposed architecture is coherent with Soma's accepted authority split if three rules hold:

1. **Sol decides semantic links after understanding the research.**
2. **Graphiti remains derived and optional; repository research docs remain authoritative.**
3. **Retrieved graph facts are navigation/context candidates; material claims are verified against linked source research.**

This directly addresses the observed problem without modifying continuation or resurrecting the unused Soma structured research platform.

## 17. Next research iteration

Before implementation, perform one final design/audit iteration around a minimal Graphiti pilot:

- choose the smallest entity vocabulary;
- choose the smallest relation vocabulary;
- decide how reviewed links preserve exact repo path/hash provenance;
- decide whether to use Graphiti MCP or a narrow Soma adapter;
- determine project `group_id` and optional research `saga` semantics;
- define stale/rebuild behavior;
- define a 15–30 case gold test set using real old/new research relationships;
- test superseded/invalidated-fact retrieval specifically;
- estimate dependency/runtime footprint on the owner's machine;
- design zero-Graphiti fallback behavior.

No Graphiti installation or source implementation is authorized by this research iteration alone.
