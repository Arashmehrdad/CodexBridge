# Soma Knowledge Carry-Forward Research — Iteration 04

**Date:** 2026-08-24  
**Status:** practical usage / integration audit  
**Question:** can existing projects be used directly or partially to save implementation time on Soma's long-horizon research context-mapping problem?

## 1. Scope correction retained

This iteration retains the corrected architecture boundary from Iteration 02:

```text
Soma continuation = current semantic handoff / re-entry
repository research docs = durable project research truth
context mapping = recover the old + recent research that matters to the current question
```

Continuation is not being redesigned.

The old Soma structured research platform is not treated as the default solution merely because it exists. The goal here is to determine whether maintained external implementations can eliminate or sharply reduce new Soma code.

## 2. Research method

This iteration followed the enabled `arash-research` Skill and inspected current official repositories/documentation for:

- LongMemEval-V2 / AgentRunbook-C V2;
- OpenAI Codex Memories;
- HippoRAG 2;
- Graphiti;
- SodaMem.

The comparison prioritizes practical reuse:

1. input shape — can it consume our Markdown research corpus without semantic duplication?
2. query path — can it produce bounded evidence for the current question?
3. provenance — can retrieved context be traced back to exact durable research files?
4. update burden — what happens when another research document is added?
5. infrastructure — model servers, graph databases, embedding services, daemons, GPUs;
6. integration surface — Python library, CLI, MCP, HTTP, or benchmark-only code;
7. authority compatibility — can `docs/` remain truth and the external system remain disposable/derived?
8. maturity/licensing where supported by official sources.

## 3. LongMemEval-V2 / AgentRunbook-C V2

Official sources:

- https://github.com/xiaowu0162/LongMemEval-V2
- https://xiaowu0162.github.io/longmemeval-v2/agentrunbook-c-v2/
- `memory_modules/agentrunbook_c_v2.py`
- `memory_modules/agentrunbook_online_learning.py`

License reported by the official repository: Apache-2.0.

### 3.1 What it actually is

LongMemEval-V2 is primarily an evaluation framework and collection of memory backends, not a turnkey memory daemon intended to be installed beside an arbitrary application.

Its general memory contract is simple:

```text
Insert(history_item)
Query(question) -> bounded context items
Reader(question, context) -> answer
```

A custom backend implements `insert(...)` and `query(...)`; the evaluation harness enforces a memory-context token limit.

AgentRunbook-C is the file-based branch: trajectory/history material is stored as files and an agent actively searches/reads those files to gather evidence.

### 3.2 V2 usage model

The current AgentRunbook-C V2 research update states that retrieval is dominated by file search and file reading. V2 therefore uses a much smaller harness built around only two broad abilities:

- shell/search/execution;
- file editing for persistent strategy updates.

The implementation is built with the OpenAI Agents SDK rather than requiring the whole Codex coding-agent harness for the query controller.

The optional online-learning component maintains `LEARNED_RETRIEVAL_STRATEGY.md`. The code validates sections such as:

```text
# Learned Retrieval Strategy
## Past Queries
## Strategies
```

and stores reusable information about what was being sought, evidence status, what was found, applicability/guards, and a fast retrieval path.

A separate consolidation process updates that strategy after completed queries.

### 3.3 What can be reused for Soma

**High value to reuse:**

- file-first retrieval rather than duplicating project truth into a new memory store;
- active multi-step search/read behavior;
- bounded final context rather than loading the entire history;
- retrieval-strategy learning as an optional optimization later;
- its benchmark framing for gotchas and premise-awareness tests.

**Low value to reuse directly:**

- benchmark-specific trajectory insertion/layout;
- evaluation harness wiring;
- the optional Codex-based strategy consolidation path as a prerequisite.

### 3.4 Practical conclusion

AgentRunbook-C V2 is best treated as an **algorithm/design donor and evaluation reference**, not a drop-in Soma dependency.

Attempting to embed its full benchmark backend would likely save less time than adapting its file-search discipline to Soma's existing repository read/search tools.

## 4. OpenAI Codex Memories — newly important direct reference

Official sources:

- https://github.com/openai/codex/blob/main/codex-rs/memories/README.md
- https://github.com/openai/codex/blob/main/codex-rs/memories/write/templates/memories/consolidation.md
- https://github.com/openai/codex/blob/main/codex-rs/ext/memories/templates/memories/read_path.md

### 4.1 Why it matters

Current Codex has a production file-memory pipeline with **progressive disclosure**, which closely resembles the context-routing layer Soma is missing.

The pipeline is split into:

```text
Phase 1: per-thread / rollout extraction
Phase 2: global consolidation
```

Phase 2 materializes a file hierarchy including:

```text
memory_summary.md
MEMORY.md
rollout_summaries/
skills/
```

The read path uses these from general to specific.

### 4.2 Codex read behavior

`memory_summary.md` is prompt-loaded and is intentionally dense, navigational, and discriminative enough to guide retrieval.

`MEMORY.md` is the searchable registry/handbook.

Exact rollout summaries and source material are opened only when needed.

The current read instructions specify a quick memory pass approximately as:

```text
1. use the already-loaded summary to extract task-relevant keywords;
2. search MEMORY.md;
3. open only 1-2 directly referenced relevant summaries/skills;
4. search exact rollout evidence only when precision is needed;
5. stop if no useful match exists.
```

The guidance targets roughly 4–6 search steps before main work rather than broad scans of all history.

This is a direct implementation example of:

```text
small always-visible routing map
        ↓
searchable richer index
        ↓
exact durable source evidence
```

### 4.3 Codex write/consolidation behavior

Current Codex does not merely append recent summaries. Its consolidation prompt explicitly tells the memory writer to:

- use workspace diffs to identify changed entries;
- expand into unchanged entries with enough coverage to avoid missing important older context;
- preserve known failures and landmines;
- preserve epistemic status;
- keep the high-level summary navigational rather than turning it into a replacement for detailed memory;
- ensure every top-level task group in the richer memory handbook is represented by the routing summary.

The runtime still uses bounded selection of stage-1 inputs and usage/recency criteria, so its exact retention policy should **not** be copied blindly for scientific research where an old falsification may remain governing indefinitely.

### 4.4 What can be reused for Soma

This is probably the **highest-value design to borrow immediately** because Soma already has the expensive part Codex Phase 1 is trying to create: durable, deliberately written research documents.

For Soma, a reduced adaptation could conceptually start at the Codex Phase-2/read-path layer:

```text
existing docs/research/*.md
        ↓
derived research routing summary / map
        ↓
searchable research handbook/index
        ↓
exact original Markdown sections
```

No rollout extraction step is inherently required because the research docs are already curated artifacts.

### 4.5 Practical conclusion

Do **not** port Codex's entire memory runtime.

Borrow the progressive-disclosure architecture, coverage guardrails, search procedure, and possibly compatible prompt patterns. That is likely much faster and safer than adding a graph database first.

## 5. HippoRAG 2

Official source:

- https://github.com/OSU-NLP-Group/HippoRAG

License: MIT.

### 5.1 Install/use shape

Current installation is straightforward:

```text
Python 3.10 environment
pip install hipporag
```

The high-level API accepts ordinary strings:

```python
hipporag = HippoRAG(...)
hipporag.index(docs=[...])
results = hipporag.retrieve(queries=[...], num_to_retrieve=N)
```

This is highly compatible with a research corpus: each research document or document section can be emitted as one string while Soma retains a side mapping to path/hash/section identity.

### 5.2 Storage and infrastructure

HippoRAG can use local Parquet-backed embedding storage by default. It also supports Qdrant, ChromaDB and Milvus. Therefore a first pilot does **not** require running a separate database service.

It still needs model capability during indexing because its graph/knowledge integration uses LLM/OpenIE machinery, plus an embedding model or endpoint.

Official examples support OpenAI-compatible LLM/embedding endpoints and local deployments.

### 5.3 Strength for Soma

HippoRAG is strong for **semantic distance and multi-hop association**:

```text
current wording
  -> related concept/entity
  -> older differently-worded research
  -> supporting source chunk
```

This is precisely where plain grep or one-shot embedding similarity can miss an old relevant finding.

### 5.4 Weakness for Soma

Its central strength is associative retrieval, not first-class scientific supersession semantics.

A retrieved old finding still needs source inspection to determine whether it remains governing, was superseded, or is only historical.

### 5.5 Practical conclusion

HippoRAG is the **best first off-the-shelf challenger** for an empirical pilot:

- simple Python API;
- direct string corpus input;
- no mandatory external DB service;
- mature research project;
- local persistent index;
- strong multi-hop retrieval.

It should remain a derived index. Original repo research docs remain authority.

## 6. Graphiti

Official source:

- https://github.com/getzep/graphiti

License: Apache-2.0.

### 6.1 Install/use shape

Core installation:

```text
pip install graphiti-core
```

Information is ingested as **episodes**. An episode may be text or structured JSON. A typical text ingestion call supplies:

```text
name
body
source description
reference time
optional group/project identity
```

Graphiti automatically extracts entities and relationships and keeps the episode as provenance.

Basic query is `graphiti.search(...)`, which performs hybrid semantic + BM25 retrieval, with graph-aware reranking/search recipes available.

### 6.2 Why it matches the scientific-history problem

Graphiti explicitly represents facts with temporal validity and preserves the old fact rather than deleting it when it becomes invalid. Derived facts trace back to raw episodes.

That is a natural fit for concepts such as:

```text
hypothesis introduced
hypothesis tested
hypothesis rejected
candidate narrowed
later result supersedes earlier interpretation
```

provided extraction represents those relations correctly.

### 6.3 Infrastructure

Graphiti requires a graph backend. Current supported paths include Neo4j and FalkorDB; Kuzu is deprecated.

The official project also supports:

```text
pip install graphiti-core[falkordblite]
```

for an embedded FalkorDB Lite path, but that option requires Python 3.12+.

Soma's current `pyproject.toml` only declares `requires-python = ">=3.10"`. Therefore an embedded Graphiti pilot can be isolated in Python 3.12, but it must not be assumed compatible with every current Soma runtime environment.

Graph construction also depends on an LLM that reliably emits structured output. The project warns that small/local models may produce schema failures.

### 6.4 Operational cost

Graphiti therefore introduces more moving parts than HippoRAG or a file-only mapper:

- graph backend/runtime;
- embeddings;
- LLM-driven extraction;
- graph schema/index management;
- incremental ingestion lifecycle.

Graphiti also has anonymous telemetry enabled by default, though the official project documents `GRAPHITI_TELEMETRY_ENABLED=false` to disable it.

### 6.5 Practical conclusion

Graphiti should **not** be the first integration simply to save engineering time.

It remains the strongest challenger if evaluation proves that temporal/supersession relationships are the specific failure a simpler file/index approach cannot solve.

## 7. SodaMem

Official source:

- https://github.com/SodaMem/SodaMem

License: Apache-2.0.

### 7.1 Install/use shape

The project provides a compact Python path:

```text
pip install "sodamem[chroma,llm]"
```

A store is opened locally, messages/events are ingested, and a prompt-ready bounded context is built with:

```text
mem.build_context(query, ..., token_budget=...)
```

The standard `search` / `build_context` read path is deterministic BM25 + vector + entity fusion and makes zero LLM calls after ingestion. Context includes citations.

It also exposes HTTP and MCP surfaces.

### 7.2 Interesting capabilities

SodaMem has explicit event/provenance orientation and exposes timeline / graph exploration functionality. Its design emphasizes when a memory became invalid and what source event produced it.

Its dependency posture is intentionally small: base retrieval uses a limited dependency set; Chroma adds local vector search and a local embedding model.

### 7.3 Mismatch with our current corpus

Its primary ingest contract is oriented around conversational/user-session events, not repository Markdown documents.

We could transform research documents into synthetic events/facts, but that would create a second semantic representation that must be generated correctly and maintained.

The project is also very young as of this audit. Its own server documentation currently requires exactly one worker because per-user stores are SQLite databases without WAL; horizontal scaling requires a different job-store architecture.

### 7.4 Practical conclusion

SodaMem is impressive and quick to stand up, but **not the fastest faithful mapping of our existing research docs**. It is more attractive if Soma later needs a general temporal agent-memory service beyond research-document retrieval.

## 8. Practical reuse ranking

### Rank 1 — Codex Memories read architecture + AgentRunbook-C V2 file-search discipline

**Reuse style:** design/prompt/control-flow reuse, minimal new infrastructure.

Why first:

- our research already exists as curated files;
- no second truth store is required;
- Soma already has repository enumeration/search/read capabilities;
- progressive disclosure solves context budget explicitly;
- AgentRunbook demonstrates that active file search can outperform heavier memory retrieval systems on long agent histories;
- exact source verification remains natural.

What we should not copy blindly:

- Codex's usage/recency retirement policy for durable scientific constraints;
- benchmark-specific AgentRunbook trajectory machinery;
- online strategy consolidation as a prerequisite.

### Rank 2 — HippoRAG 2

**Reuse style:** off-the-shelf retrieval index / challenger.

Why second:

- `pip install hipporag`;
- plain string corpus ingestion;
- local storage without mandatory server;
- strong associative/multi-hop retrieval;
- easy to keep disposable and path/hash-backed.

Use it to answer:

> does a real associative retriever recover old governing findings that file-first active search misses?

### Rank 3 — Graphiti

**Reuse style:** temporal context-graph challenger.

Use only if gold tests demonstrate a real need for:

- historical validity;
- contradiction/supersession relationships;
- graph expansion across long research lineages.

It costs more infrastructure and model-derived graph state.

### Rank 4 — SodaMem

**Reuse style:** general temporal memory service reference or later service integration.

Not preferred for the first research-doc pilot because the native ingest abstraction is events/conversation rather than files/documents.

### LongMemEval-V2 repository itself

Use its benchmark/harness ideas and AgentRunbook code as a reference. Do not treat the entire repository as a dependency that must be embedded into Soma.

## 9. Fastest credible pilot architecture

A first pilot can avoid any new database entirely.

Conceptual shape:

```text
current question
    |
    v
small derived research-routing map
    |
    v
active search across docs/research/**
    |          \
    |           -> search falsified / rejected / superseded / constraint vocabulary
    v
candidate research docs
    |
    v
open exact source sections + follow explicit Research-N references
    |
    v
bounded evidence packet containing paths + source hashes/line ranges
    |
    v
Sol reasons normally
```

This borrows Codex progressive disclosure and AgentRunbook active file exploration while retaining Soma's accepted architecture.

The map is **derived navigation**, not authority.

## 10. Minimal challenger experiment

After the file-first pilot exists, index the same frozen research corpus in HippoRAG and run the same gold questions.

Evaluate at least:

```text
old governing finding recall
old falsification recall
superseded-path detection
semantic-distance recall
near-match rejection
exact-source provenance
context tokens returned
query latency
index/update cost
```

Only escalate to Graphiti if file-first + HippoRAG still fail specifically on temporal/supersession reasoning.

## 11. Key time-saving conclusion

We do **not** need to choose between "build everything ourselves" and "adopt a whole memory platform".

The most economical path is compositional:

```text
Codex Memories       -> progressive-disclosure routing pattern
AgentRunbook-C V2    -> active file-search/context-gathering pattern
Soma repo tools      -> actual authoritative search/read substrate
HippoRAG 2           -> plug-in associative retrieval challenger
Graphiti             -> only if temporal graph semantics prove necessary
```

This preserves continuation unchanged and uses the research docs we already produce rather than duplicating them into an unused structured research subsystem.

## 12. Next research step

Before implementation, build a small gold set from real existing project histories and run **usage-level feasibility tests**, not another architecture essay.

A good first gate is 20–40 questions containing:

- an old falsification that must be remembered;
- a later supersession of an older result;
- an enduring protocol constraint;
- same concept under different terminology;
- a tempting but wrong near-match;
- a question requiring two distant research iterations together.

Then compare:

1. direct/active file retrieval inspired by Codex + AgentRunbook;
2. HippoRAG over the identical corpus;
3. Graphiti only if the first two expose a temporal-lineage gap.

No production integration is authorized by this iteration.
