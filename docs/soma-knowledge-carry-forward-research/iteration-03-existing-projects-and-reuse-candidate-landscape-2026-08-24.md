# Soma Knowledge Carry-Forward Research — Iteration 03

**Date:** 2026-08-24  
**Status:** external-project landscape / reuse candidates  
**Scope:** long-horizon context mapping over existing project research documents  
**Non-goals:** changing Soma continuation; reviving Soma's unused structured research platform; implementing a new memory authority

## 1. Research question

> Are there existing open-source projects that already address Soma's actual failure mode — retrieving old but still-governing knowledge from a very large accumulated history — well enough that Soma should reuse or adapt one instead of inventing a new subsystem?

Owner constraints carried into this iteration:

- Soma continuation is already in the correct architectural place and should remain unchanged.
- Research documents under each repository's `docs/` tree remain the durable research record.
- The failure is context selection over a long research lineage: early findings can become absent from later effective context even when still relevant.
- The old Soma structured research/context-packet subsystem was not part of the real working practice and must not be treated as the default solution merely because it exists.

This iteration follows the enabled `arash-research` Skill revision R8-I1: primary sources first, facts separated from inference, plausible alternatives compared, and uncertainty preserved.

## 2. Evaluation criteria

Candidates are judged against the Soma problem, not against generic "agent memory" marketing.

Required or highly desirable properties:

1. can operate over a growing corpus without copying the whole corpus into every prompt;
2. can retrieve **old but currently relevant** evidence instead of ranking mainly by recency;
3. can recover negative knowledge, gotchas, prior failures, falsifications, and premise corrections;
4. can preserve or recover exact source provenance so the controller can verify the original research document;
5. can cope with updates, contradictions, or supersession;
6. can keep repository research docs as authority rather than replacing them with opaque generated memory;
7. can be rebuilt when derived state is lost;
8. does not require Soma continuation to become a semantic planner or source registry;
9. should have a plausible path to local/self-hosted operation;
10. implementation and operational complexity must be justified by measured retrieval gain.

## 3. Candidate A — LongMemEval-V2 / AgentRunbook-C V2

### Source-supported facts

LongMemEval-V2 is an open benchmark and implementation repository from Di Wu et al. for long-term agent memory. Its benchmark formulation is unusually close to Soma's problem: a memory system consumes a very large history and, for a current question, returns **compact evidence** to a downstream reader under a memory-context token budget.

The official repository currently reports:

- 451 manually curated questions;
- five target memory abilities;
- up to 500 trajectories per haystack;
- up to 115M tokens in the largest histories;
- explicit evaluation of answer accuracy and query latency.

The five benchmark abilities include **environment gotchas** and **premise awareness**, both directly analogous to Soma needing to recover an old failure or falsification before retrying an invalid research direction.

The official August 2026 AgentRunbook-C V2 update says its retrieval controller is dominated by **file search and file reading** and therefore uses a deliberately lean harness built around two main tools: a shell/search-execution tool and a file editor for persistent updates.

V2 also adds a learned retrieval-strategy note. After each question, a consolidation component extracts reusable retrieval experience such as successful search strategies, useful paths, and previously exhausted directions. The query-side instructions explicitly warn that these learned notes are only candidate search leads and that current cited evidence must independently verify the answer.

The current implementation even distinguishes prior evidence statuses including:

- `directly_supported`;
- `contradicts_premise`;
- `near_match_only`;
- `insufficient`.

Its query guidance states that a learned note is not proof for the current question and that current trajectory evidence must be inspected before passing a conclusion onward.

The project is Apache-2.0 licensed.

### Why it matches Soma

This is the strongest conceptual match to Soma's **existing source-of-truth model**:

```text
research remains files
        ↓
current question drives active search/read
        ↓
retriever gathers a bounded evidence set
        ↓
controller reasons from exact evidence
```

It does not require the authoritative history to become a graph first.

Most importantly, it demonstrates that long-history retrieval can be treated as an **agentic context-gathering problem over files**, rather than as a requirement to maintain one perfect summary or stuff all old documents into the current handoff.

### Direct adoption problem

AgentRunbook-C V2 is itself a separate memory-controller agent/harness. Directly embedding that controller as a second semantic agent inside Soma would conflict with Soma's accepted architecture in which Sol/ChatGPT is the reasoning head.

Therefore the reusable object is more likely its **retrieval protocol and file-first design**, not necessarily its controller architecture verbatim.

A Soma-compatible adaptation could let the same Sol controller invoke a bounded research-retrieval Skill/tool flow over project docs, preserving exact source verification and avoiding a hidden second planner.

### Research verdict

**Highest-priority baseline / design donor.** It should be tested before adding graph infrastructure.

Primary sources:

- https://github.com/xiaowu0162/LongMemEval-V2
- https://xiaowu0162.github.io/longmemeval-v2/agentrunbook-c-v2/
- https://arxiv.org/abs/2605.12493

## 4. Candidate B — Graphiti

### Source-supported facts

Graphiti by Zep is an open-source temporal context-graph framework. Its documentation says it:

- ingests structured or unstructured information as episodes;
- keeps episode provenance;
- tracks how facts and relationships change over time;
- uses explicit temporal validity on graph edges;
- supports incremental updates rather than requiring complete graph recomputation;
- combines vector similarity, BM25 full-text search, and graph traversal in hybrid retrieval;
- supports custom entity/edge types;
- supports Neo4j, FalkorDB, and Amazon Neptune;
- ships an MCP server.

The Graphiti docs specifically contrast it with static document GraphRAG because Graphiti is designed for changing information and precise historical queries.

### Why it matches Soma

Graphiti is attractive for the part AgentRunbook-C does not model explicitly: **supersession and historical validity**.

For Soma research, a derived graph could potentially represent relationships such as:

```text
Research 035 --tested--> mechanism X
Research 035 --rejected/narrowed--> mechanism X
Research 038 --inherits/references--> Research 035
Research 038 --proposes--> mechanism Y
```

while each derived relationship retains provenance to the source episode/document.

Its hybrid retrieval could help recover a remote old finding through both semantic and graph relationships rather than exact words alone.

### Risks

Graph construction relies on model-based entity/relation extraction. That means a derived graph can mis-extract or over-generalize scientific semantics. It must therefore remain **non-authoritative navigation/index state**, with exact repository source verification before a claim governs work.

It also introduces a graph database and ingestion lifecycle. That is materially more infrastructure than the file-first option.

### Research verdict

**Strong second candidate**, especially if the benchmark shows that plain active file search misses supersession/lineage cases. Do not adopt before measuring whether the extra graph machinery buys enough recall.

Primary sources:

- https://github.com/getzep/graphiti
- https://help.getzep.com/graphiti/getting-started/overview
- https://help.getzep.com/graphiti/getting-started/mcp-server

## 5. Candidate C — HippoRAG 2

### Source-supported facts

HippoRAG 2 from Ohio State is an open-source long-term-memory/RAG framework whose stated goal is to recognize and use connections across newly accumulated external knowledge.

Its design combines knowledge graphs with Personalized PageRank and targets:

- factual memory;
- associative / multi-hop retrieval;
- sense-making across large contexts;
- continual integration of knowledge across documents.

The official project describes HippoRAG 2 as improving associativity and sense-making without sacrificing simpler factual retrieval, and as requiring fewer offline resources than several other graph-based systems in its experiments.

The repository is MIT licensed.

### Why it matches Soma

The strongest fit is **associative retrieval across distant research iterations**. A current research idea may use new terminology while an old experiment contains the governing result under very different language. Graph propagation is specifically intended to bridge those multi-hop associations.

### Risks

HippoRAG is principally a retrieval architecture rather than a temporal/supersession model. It is less naturally aligned than Graphiti with statements such as "this was true before Research 035 but was later rejected".

It also depends on extracted graph structure, so exact source verification remains mandatory.

### Research verdict

**Worth benchmarking as the strongest associative-retrieval challenger**, but not yet the leading integration candidate.

Primary sources:

- https://github.com/OSU-NLP-Group/HippoRAG
- https://arxiv.org/abs/2502.14802
- https://arxiv.org/abs/2405.14831

## 6. Candidate D — SodaMem

### Source-supported facts

SodaMem is a very recent 2026 open-source project and paper for evidence-grounded temporal graph memory.

Its current design emphasizes:

- a provenance chain from derived FactEvent to SourceSpan to raw source turn;
- separate occurrence, validity, document, and storage times;
- ADD-only corrections with a `SUPERSEDES` relationship rather than destructive replacement;
- hybrid BM25/vector retrieval;
- prompt-ready context construction that can run without an LLM at read time;
- MCP and several agent-framework integrations.

Its paper also models `SUPERSEDES`, `CONTRADICTS`, and `UPDATES` edges. The paper reports strong LongMemEval-S results but explicitly notes that the same model was used as reader and judge for the reported accuracy and that some cross-system cost comparisons are estimates, so those benchmark claims should not be treated as a clean independent bake-off.

The repository is Apache-2.0 licensed.

### Why it matches Soma

Architecturally, its provenance + supersession model is strikingly close to scientific research history. It explicitly tries to answer both:

- what is currently valid?;
- where did this fact come from?

### Risks

It is extremely young compared with Graphiti and HippoRAG. At the time of this research its GitHub project has a small adoption footprint. Its primary abstraction is memory extracted from conversational turns, so using repository research Markdown as the source corpus may require an adapter and careful validation.

### Research verdict

**Excellent design reference and experimental temporal challenger, but too young to choose as Soma's first production dependency without a local bake-off.**

Primary sources:

- https://github.com/SodaMem/SodaMem
- https://arxiv.org/abs/2608.08055

## 7. Comparison for Soma's actual problem

| Candidate | Uses existing files naturally | Old/distant association | Explicit temporal/supersession | Exact provenance model | Extra infrastructure | Soma architecture fit |
|---|---:|---:|---:|---:|---:|---|
| AgentRunbook-C V2 pattern | **Excellent** | Good, agentic search | Limited / implicit | **Excellent if exact file passages are returned** | Low | **Excellent if Sol remains controller** |
| Graphiti | Good via episode ingestion | **Excellent** | **Excellent** | Strong episode provenance | Medium/high | Good as derived index |
| HippoRAG 2 | Good via indexing | **Excellent** | Limited | Moderate/strong with source mapping | Medium | Good as derived retriever |
| SodaMem | Adapter likely needed | Good | **Excellent** | **Excellent** | Medium | Promising, maturity risk |

No row above is an implementation approval. The comparison describes fit to the present research question.

## 8. Adversarial alternative — why not just install Graphiti now?

Graphiti initially looks like the obvious answer because our research history has temporal relationships and supersession.

However, jumping directly to a graph can create a new failure mode:

```text
correct research docs
    ↓
LLM extraction error
    ↓
incorrect graph edge / summary
    ↓
retrieval confidently surfaces the wrong governing relationship
```

Soma already possesses exact, well-structured Markdown research files and powerful repository search/read tools. AgentRunbook-C's results show that active file navigation can be a serious long-history retrieval method in its own right.

Therefore a graph dependency should have to **beat a file-first baseline on our own known-answer corpus** before it earns architectural complexity.

## 9. Current recommendation

The best next move is not to pick a production dependency yet. It is to run a small **Soma-specific retrieval bake-off**.

### Baseline 1 — current behavior

Current continuation + ordinary/recent-context behavior, with targeted repo search only when the controller happens to realize it is needed.

### Baseline 2 — AgentRunbook-C-inspired file-first context gatherer

Do not add a second reasoning authority. Instead, define a bounded retrieval procedure/Skill for the existing Sol controller:

1. enumerate/manifest the research corpus;
2. search across all research documents, not only recent ones;
3. deliberately search for rejection/falsification/failed/constraint/supersession language as well as positive matches;
4. follow references between research iterations;
5. read exact candidate passages;
6. reject near matches;
7. return only a bounded evidence packet with exact paths/locators;
8. let Sol reason normally from that packet.

This tests whether **better retrieval discipline alone** solves most of the issue.

### Challenger 1 — Graphiti

Build a disposable derived index from the same research docs and test whether temporal/hybrid graph retrieval finds governing old evidence that file-first retrieval misses.

### Challenger 2 — HippoRAG 2

Test associative/multi-hop retrieval on the same corpus, especially queries whose terminology differs substantially from the old evidence.

### Optional Challenger 3 — SodaMem

Use only if an adapter from repository research documents can be created cheaply enough for the experiment. Treat it as a temporal/provenance design challenger, not a production choice.

## 10. Proposed evaluation corpus

Before testing any candidate, construct a gold set from a real long research programme such as NSDN, where the symptom has already appeared.

Each case should contain:

```text
current-style question
required old finding(s)
authoritative research document(s)
exact supporting passage(s)
relationship to later work
whether the result is positive, negative, superseded, qualified, or still governing
```

The corpus should deliberately include:

- early falsifications that remain binding much later;
- rejected approaches that must not be repeated;
- protocol invariants from old preregistrations;
- later refinements that supersede only part of an older finding;
- same-concept/different-vocabulary cases;
- tempting near matches;
- questions where the correct result is "the premise was already disproven".

Primary metrics:

- governing-evidence recall within a fixed context-token budget;
- negative/falsification recall;
- supersession correctness;
- exact-source citation fidelity;
- false-positive / near-match rate;
- query latency;
- derived-index update cost;
- operational complexity.

## 11. Iteration conclusion

Existing projects do address the problem closely enough that Soma should **not design a bespoke context-mapping subsystem yet**.

The most important discovery is that there are two credible families:

```text
A. active file-first evidence gathering
   LongMemEval-V2 / AgentRunbook-C V2

B. derived temporal/associative graph retrieval
   Graphiti / HippoRAG 2 / SodaMem
```

For Soma's current architecture, **AgentRunbook-C V2 is the best first design donor and baseline** because it works with the representation we already trust: files. Graphiti is the strongest likely integration challenger because it adds exactly the temporal/supersession semantics that file search lacks.

The correct decision point is empirical:

> If file-first active retrieval reaches high recall on Soma's real old-governing-finding benchmark, keep the architecture simple. If it systematically misses lineage/supersession/semantic-distance cases and Graphiti materially closes that gap, adopt Graphiti only as a rebuildable derived context index while repository research docs remain authoritative.

## 12. Next research question

Iteration 04 should design the **gold benchmark and failure taxonomy before any candidate is installed**.

It should determine:

- how many test cases are sufficient to distinguish the candidates;
- how to sample early/middle/recent research fairly;
- how to score partial retrieval and supersession mistakes;
- what context-token and latency budgets reflect normal Soma usage;
- which NSDN cases are suitable without contaminating the gold set;
- what threshold would justify adding Graphiti/HippoRAG infrastructure over the file-first approach.

No integration, installation, wiki rework, or continuation change is authorized by this iteration.
