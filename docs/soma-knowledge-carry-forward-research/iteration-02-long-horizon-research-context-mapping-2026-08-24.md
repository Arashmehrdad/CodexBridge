# Soma Knowledge Carry-Forward Research — Iteration 02

**Date:** 2026-08-24  
**Status:** research framing correction and architecture baseline  
**Supersedes:** Iteration 01 only where Iteration 01 overstates storage/consolidation failure as the primary problem  
**Programme scope:** long-horizon research context coverage across growing project histories

## 1. Owner correction

The owner clarified the observed failure more precisely:

- Soma continuation already preserves the current handoff/re-entry state;
- project research is already written durably into repository `docs/`;
- the failure appears after a research programme grows long enough that earlier but still-governing findings can be omitted from later effective context;
- the likely problem is therefore **context mapping / relevance coverage**, not basic retention.

This iteration rechecks Soma against that framing.

## 2. Corrected research question

> Given a durable research corpus and a current continuation handoff, how should Soma reliably map the current research question to all materially relevant prior findings—including old falsifications, constraints and superseded paths—without forcing the controller to maintain a brittle semantic schema?

The key distinction is:

```text
continuation = where we are now / how to re-enter
research docs = durable historical truth
context map = which historical facts still matter now
```

The symptom is a failure of the third layer.

## 3. Observed evidence

### 3.1 Final continuation architecture is intentionally minimal

`docs/sol-agentic-loop-realignment-research/iteration-30-final-synthesis-minimal-sol-semantic-reentry-2026-08-15.md` explicitly converged continuation to four authorities:

1. controller continuations;
2. contract revisions;
3. free-form handoffs;
4. effect links.

It explicitly removed model-maintained semantic structures such as:

- `continuation_sources`;
- source roles;
- decision basis;
- evidence frontiers;
- structured reasoning state.

The reason was architectural: Soma must not require Sol/ChatGPT to serialize and maintain its cognition in a rigid schema.

Therefore the long-horizon research map should **not** be solved by bloating continuation with a new semantic source registry.

### 3.2 Soma previously researched relevance coverage directly

`iteration-21-continuation-source-relevance-coverage-and-observation-strength-2026-08-15.md` explored a relevance/provenance registry for sources.

Iteration 21 found such a registry useful conceptually for re-entry, but also established that:

- registration cannot prove complete world coverage;
- semantic necessity must remain a controller judgment;
- a source registry must not become a second authority;
- terminal sources can remain relevant;
- automatic dependency/source graphs were rejected from continuation v1.

The final Iteration 30 then removed `continuation_sources` entirely to keep the continuation kernel minimal.

This historical result is highly relevant to the current problem: **research context mapping remains useful, but continuation is the wrong ownership boundary for it.**

### 3.3 Soma already has a research knowledge/context-packet architecture

`docs/SOMA_KNOWLEDGE_LAYER.md` defines a separate research platform intended to preserve and later retrieve:

- claims;
- supporting and contradictory evidence;
- questions;
- candidates;
- accepted/rejected/deferred/superseded decisions;
- relationships;
- context packets.

Its context packet is explicitly intended to join prior decisions, supersession, claims, evidence and unresolved questions for a later controller.

That architecture is much closer to the current need than continuation or the structural repository wiki.

### 3.4 But the research platform is manual by design

The same knowledge-layer contract states that the current operating workflow is explicit/manual:

1. controller performs research;
2. owner explicitly asks to preserve it;
3. controller manually imports source captures;
4. controller submits a structured research packet.

It lists automatic claim extraction as a deliberate non-goal.

This means ordinary project research documents written under `docs/research/` do **not** automatically become the claim/decision/relationship graph used by `build_context_packet`.

### 3.5 The live NSDN test case demonstrates the gap

Live NSDN research health during this iteration:

```text
sources              7
source_versions       7
claims                0
evidence_links        0
research_questions    0
design_decisions      0
relationships         0
context_packets       3
research index        not_configured
```

Yet the NSDN repository contains a large numbered research lineage under `docs/research/` and direct repository search retrieves the relevant Research 035/038 history.

Therefore the durable research corpus and the structured research-context plane are not currently equivalent representations of the project's research history.

### 3.6 Direct context-packet reproduction

A live `build_context_packet` query was issued for:

```text
Research 035 dendritic gating prior falsification constraints dynamic spine associative memory routing
```

Result:

```text
retrieved_passages = []
claims             = []
evidence           = []
questions          = []
candidates         = []
decisions          = []
entity_ids         = []
```

The same underlying question is answerable by direct repository search because Research 038 explicitly carries the Research 035 result forward.

This is the cleanest current reproduction of the failure mode.

### 3.7 Current `build_context_packet` cannot bridge that gap by itself

Source inspection of `soma/research/service.py` and `soma/research/store.py` shows:

- semantic passages are obtained only when the optional RAGFlow adapter is configured and source versions have corresponding indexed documents;
- otherwise the overlay searches already-preserved claims/questions/candidates/decisions;
- reviewed claims and linked evidence can be joined into the packet;
- it does not scan repository research documents directly;
- it does not derive research lineage from numbered Markdown files.

For NSDN, RAGFlow is not configured and the overlay contains no claims/decisions/relationships, so the empty packet is the expected mechanical outcome.

## 4. Corrected diagnosis

The primary problem is **not knowledge deletion**.

It is best described as:

> **long-horizon research context coverage failure**

or, more compactly:

> **research context-mapping failure**.

The failure path is:

```text
research iterations are durably preserved in docs
        ↓
continuation correctly preserves the latest working frontier
        ↓
research corpus grows over many iterations
        ↓
current context naturally emphasizes recent handoff/recent documents
        ↓
no complete derived map links the current question to all governing old results
        ↓
older falsifications/constraints can fall outside effective context
        ↓
later work can partially rediscover or accidentally retry an old path
```

This diagnosis is narrower and more accurate than Iteration 01's initial emphasis on retention/consolidation.

## 5. What the wiki does and does not solve

The current generated repository wiki is explicitly a **structural cache**. It maps repository shape, architecture, modules and validation.

A wiki rework could help **if** it gains a research-lineage view, but the wiki should not become the authority for research truth.

A safer authority split is:

```text
research docs                 = authoritative durable research record
continuation                  = current semantic handoff/re-entry
research context map/index    = derived navigation/relevance layer
wiki                          = optional human-readable projection of that map
```

This keeps the repo docs inspectable and avoids making a generated summary the source of truth.

## 6. Design constraints carried forward

Any future solution should preserve these already-accepted Soma principles:

1. **Do not require a controller-maintained cognition schema.**
2. **Do not make continuation own semantic dependencies.**
3. **Do not treat generated summaries or embeddings as authority.**
4. **The repository research documents remain inspectable evidence.**
5. **Old negative knowledge matters:** falsified or rejected paths must remain retrievable even when old.
6. **Recency alone must not control context selection.**
7. **Supersession must be visible:** a later result may narrow, replace or qualify an earlier one without erasing its history.
8. **A context map should be rebuildable from durable project state where practical.**

## 7. Emerging architecture hypothesis

The smallest promising direction is **not** “put all old research into every handoff.”

It is a derived research-lineage map over the repository's durable research documents, capable of answering questions such as:

```text
What earlier iterations are ancestors of the current question?
What mechanisms have already been falsified?
What decisions remain governing?
What findings were superseded or narrowed?
What protocol constraints still apply?
Which older document is relevant despite low recency?
```

The map could then drive bounded retrieval of the exact source documents/passages into the controller's current context.

Whether that map should be:

- deterministic metadata extracted from research-document conventions;
- hybrid lexical/semantic retrieval plus explicit lineage edges;
- the existing research overlay populated from repo research artifacts;
- a redesigned research wiki/index;
- or some combination

remains open and requires further research.

## 8. Important non-conclusion

This iteration does **not** establish that Soma needs a general knowledge graph.

It also does not establish that every research document should be parsed into claims automatically.

Those approaches may add complexity or recreate the model-maintained-schema problem. They must be compared against simpler alternatives.

## 9. Next research question

Iteration 03 should research the retrieval/context-mapping design space specifically for **long sequential research programmes**.

It should compare at least:

1. flat semantic search over all research docs;
2. hierarchical summaries / recursive retrieval;
3. explicit research-lineage or citation graphs;
4. hybrid sparse+dense retrieval with reranking;
5. durable "governing findings / falsifications / constraints" indexes;
6. the existing Soma research-overlay/context-packet system adapted to repository research docs.

Evaluation criteria should include:

- recall of old but governing findings;
- resistance to recency bias;
- negative-knowledge/falsification recall;
- supersession handling;
- context-token cost;
- rebuildability and auditability;
- controller maintenance burden;
- compatibility with Soma's accepted minimal continuation architecture.

No implementation or wiki rework is authorized by this iteration.
