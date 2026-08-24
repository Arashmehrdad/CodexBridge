# Soma Knowledge Carry-Forward Research — Iteration 07

**Date:** 2026-08-24  
**Status:** COMPLETE — standalone Graphiti pilot passed with integration caveats  
**Scope:** empirical Graphiti evaluation against existing research documents before any Soma integration

## 1. Owner direction

Test Graphiti separately first and measure how well it performs on the project's real research history before designing or implementing a Soma integration.

The intended architecture is not automatic document understanding. The repository research documents remain authoritative. Sol/ChatGPT understands and adjudicates completed research, then Graphiti stores a derived semantic map that helps later Sol recover old governing findings.

```text
research docs = truth
continuation  = current handoff
Sol           = semantic understanding
Graphiti      = derived research map / retrieval aid
```

Codex integration remains forbidden.

## 2. Isolation boundary actually used

No Soma runtime dependency, continuation implementation, or source module was changed for this pilot.

The disposable pilot was built outside the repository:

- Windows pilot root: `D:\Services\GraphitiPilot`;
- WSL pilot root: `/home/arash/graphiti-pilot`;
- Graphiti: `0.29.3`;
- FalkorDB Lite: `0.10.0`;
- FastEmbed: `0.8.0`;
- local embedding model: `BAAI/bge-small-en-v1.5`, 384 dimensions;
- telemetry disabled for Graphiti and Hugging Face paths used by the pilot;
- no external model-provider API key was used;
- no Codex component was used.

The authoritative corpus was NSDN `docs/research/` at the live repository state. The benchmark harness is outside both repos at:

`D:\Services\GraphitiPilot\nsdn_benchmark.py`

Machine-readable result:

`D:\Services\GraphitiPilot\nsdn_benchmark_results.json`

Durable Soma execution record for the full benchmark:

`20260824T104246Z_executable_profile_bed0334e`

## 3. Setup findings before the benchmark

### 3.1 Current packaging rough edge

Installing `graphiti-core==0.29.3` resolved current `openai==3.3.1`. That package supplied `httpx2`, while Graphiti itself directly imports `httpx`. The first Graphiti import therefore failed with:

`ModuleNotFoundError: No module named 'httpx'`

Installing `httpx>=0.27,<1` in the isolated pilot environment corrected the import. This is an environment/dependency compatibility issue in the tested package combination, not a scientific retrieval result.

### 3.2 Kuzu is unsuitable for this pilot

Graphiti 0.29.3 itself warns that the Kuzu backend is deprecated because upstream Kuzu is unmaintained.

A fresh Kuzu 0.11.3 database repeatedly failed Graphiti hybrid search because the expected edge full-text index `edge_name_and_fact` was absent. `KuzuDriver.build_indices_and_constraints()` is a no-op in the installed Graphiti source because Kuzu schema/index creation is expected during driver setup.

The failure reproduced after deleting and recreating the database. Kuzu was therefore rejected as a valid benchmark backend; no patch was made to the deprecated backend.

### 3.3 FalkorDB Lite worked

Graphiti 0.29.3 + FalkorDB Lite 0.10.0 operated correctly in WSL. Directly saved nodes and edges were immediately readable from the graph. Edge embeddings were stored as FalkorDB native `Vectorf32` values.

### 3.4 `Graphiti.add_triplet()` is not a pure reviewed-write path

Installed Graphiti 0.29.3 source shows that `add_triplet()` still performs node resolution, searches existing/related edges, and calls LLM-backed edge resolution. Therefore it is not suitable for the owner-requested contract:

```text
Sol understands research
    -> Sol supplies reviewed semantic relation
    -> storage must not reinterpret the relation
```

For this pilot, reviewed facts were instead persisted through the lower-level Graphiti node/edge model:

- `EntityNode.generate_name_embedding()`;
- `EntityEdge.generate_embedding()`;
- `EntityNode.save()`;
- `EntityEdge.save()`.

A fail-closed local `LLMClient` subclass was supplied to Graphiti only because its internal client model requires an `LLMClient` instance. Any attempted LLM generation raises an exception. No LLM extraction, contradiction judgment, or invalidation was allowed during the benchmark.

## 4. FalkorDB namespacing defect found in smoke testing

A one-edge smoke test established a current behavior that matters for any later Soma integration.

For the query:

> What previous result rules out reusing generic dendritic routing as the new solution?

against a reviewed Research-035 falsification edge:

- vector similarity with `group_ids=['nsdn-smoke']` returned the correct edge even at the default `0.6` similarity threshold;
- full-text search with the same `group_id` returned zero;
- full-text search without the `group_id` returned the correct edge;
- stock Graphiti hybrid search without `group_id` returned the correct edge;
- stock Graphiti hybrid search with `group_id` returned zero.

Therefore project-level `group_id` namespacing cannot yet be trusted with the tested FalkorDB hybrid path. To measure retrieval quality rather than this plumbing defect, the benchmark used one isolated graph database for NSDN and did not pass a group filter.

This workaround is acceptable for an isolated pilot, but it must be resolved or structurally avoided before a production Soma workflow.

## 5. Benchmark construction

The benchmark tests the proposed **Sol-reviewed semantic-map workflow**, not Graphiti's automatic extraction quality.

Thirty material facts were manually adjudicated from real NSDN research documents. They deliberately include positive findings, negative findings, prohibitions, narrowing conclusions and experimental-governance constraints. Examples include:

- Research 035 dendritic/context-gating specificity failure;
- Research 038 prohibition on relabelling generic upstream dendritic gating as a new solution;
- the narrower routing classes still allowed by Research 038;
- Research 037's prohibition on simply repeating scalar-retention/key/value-width tuning;
- Research 037C's distinction between backend-readiness failure and D1 mechanism rejection;
- Research 025's prohibition on projecting the spatial predictive margin onto language;
- the full-prefix FFT decode prohibition;
- spent-REPORT irreversibility;
- bounded state not being sufficient evidence of practical efficiency;
- parity-before-timing requirements;
- BLT remaining a control/reference rather than the NSDN backbone.

Before graph insertion, every fact's quoted anchor was required to exist in its actual Markdown source. The harness then recorded the live source path, SHA-256, anchor line and anchor text on the semantic edge. The run failed closed if an anchor was absent.

All 30 facts passed source verification.

The resulting test graph contained:

- 53 semantic entity nodes;
- 30 reviewed research edges;
- zero LLM-extracted edges.

Fifteen adversarial questions were then asked. They were phrased as realistic future-research questions, not copied source sentences. Several deliberately invite a scientifically wrong revival or overclaim.

## 6. Retrieval results

| Method | Hit@1 | Hit@3 | Hit@5 | MRR | Mean retrieval latency |
|---|---:|---:|---:|---:|---:|
| Graphiti hybrid | **60.0%** | **93.3%** | **100.0%** | 0.7578 | 56.74 ms |
| Vector only | 73.3% | 86.7% | 86.7% | **0.7889** | **4.96 ms** |
| Full text only | 20.0% | 66.7% | 86.7% | 0.4467 | 5.97 ms |

The key result for Soma is **hybrid Hit@5 = 15/15**.

Every adversarial question recovered at least one expected governing fact in the first five Graphiti hybrid results. Fourteen of fifteen recovered an expected fact in the first three.

The only hybrid case outside the top three was the question asking whether the programme should simply retune retention coefficients or key/value widths after bounded retrieval failed. The exact Research-037 prohibition was still returned at rank 5.

### 6.1 Why vector-only is not enough

Vector-only retrieval had the strongest Hit@1 and slightly higher MRR, but it entirely missed the expected fact from the first five results on two difficult questions, including the generic-dendritic-revival case and retention-retuning case.

This matters more than the rank-1 difference for Soma. The failure being addressed is omission of an old but governing constraint. A method that puts the right fact at rank 3 or rank 5 is safer than one that often ranks well but sometimes omits the governing fact completely.

### 6.2 Why hybrid is promising

Hybrid retrieval combined semantic and lexical evidence and recovered old negative/narrowing findings despite differently phrased questions.

Representative outcomes:

- generic dendritic revival -> exact `must not relabel` constraint at rank 3;
- poor D1 GPU utilization -> `backend-readiness failure, not D1 rejection` at rank 1;
- spatial result projected to language -> non-transfer constraint at rank 1;
- full-prefix FFT during generation -> prohibition at rank 2;
- spent REPORT reconstruction -> irreversibility constraint at rank 2;
- bounded state implies efficiency -> qualification at rank 1;
- what transfers from C2 -> primitive-not-module finding at rank 1;
- raw D1 failure kills curvature-aware class -> narrowing correction at rank 1;
- remaining adaptive routing space -> narrow associative-substrate routing at rank 1;
- empty exit-code file as success proof -> evidence warning at rank 1;
- retroactively rewriting Stage-1 language evidence -> preservation rule at rank 1;
- timing an implementation that fails parity -> parity-before-timing rule at rank 1.

This is the behavior the research-context map was intended to provide.

## 7. What the benchmark does and does not establish

### Established

Graphiti's graph plus hybrid retrieval layer is capable of recovering old, governing NSDN research constraints with high recall when the graph contains **Sol-reviewed semantic facts with provenance**.

The specific first-pilot target passed:

> Can a bounded semantic map retrieve old negative/narrowing research findings that a later research question must not silently ignore?

For this 30-fact, 15-query adversarial set: **yes**. Hybrid retrieval achieved 100% Hit@5 and 93.3% Hit@3.

### Not established

This does not show that Graphiti's automatic extraction understands research reliably. Automatic extraction was deliberately not tested and is not the proposed authority path.

This does not yet prove performance on hundreds or thousands of reviewed research facts.

This does not prove current `group_id` isolation is safe in the tested FalkorDB search path; the smoke test found the opposite.

This does not prove that Graphiti's automatic contradiction/invalidation machinery is suitable for scientific semantics. That machinery was bypassed.

This does not justify replacing research documents, continuation, or Sol reasoning with Graphiti.

## 8. Adversarial interpretation

A plausible alternative explanation is that the benchmark is easy because the reviewed fact sentences were already compact and semantically explicit.

That explanation is partly valid. The test measures the intended **post-understanding map**, not retrieval over raw 500-line research papers. Compact reviewed facts are exactly what the proposed workflow would store after Sol understands a completed research iteration.

The stronger concern is scale: with only 30 facts, distractor density is modest. The present result therefore establishes feasibility, not final production recall.

Another adverse finding is that Graphiti's stock API is less suitable for our trust boundary than its data/search layer:

- `add_triplet()` still invokes semantic LLM resolution;
- Kuzu is unusable/deprecated for this purpose;
- FalkorDB group-filtered hybrid search behaved incorrectly in the smoke test;
- current packaging needed an explicit `httpx` correction.

These are real integration costs and should not be hidden by the strong retrieval score.

## 9. Iteration-07 verdict

**PASS FOR CONTINUED EVALUATION / NOT YET AN INTEGRATION APPROVAL.**

Graphiti is now empirically justified as the leading candidate for Soma's optional research semantic map.

The result is stronger than a design-only argument: on an adversarial set derived from actual NSDN research history, the Graphiti hybrid layer recovered an expected governing fact in the top five for every query.

The preferred architectural direction remains:

```text
research iteration completed and saved under docs/
        -> Sol adjudicates what it means
        -> reviewed semantic facts/relations + source provenance
        -> Graphiti derived map
        -> later research question
        -> hybrid retrieval of relevant old + recent findings
        -> Sol reopens/verifies authoritative source docs
        -> reasoning continues
```

Graphiti remains optional. Failure or absence of Graphiti must not impair continuation, normal Soma operation, or access to the underlying research corpus.

## 10. Recommended next research step

Do not integrate Graphiti into Soma yet.

The next useful test is a **scale-and-update pilot** using a substantially larger reviewed graph, with deliberate supersession/contradiction chains and incremental post-research updates. It should test whether the 100% Hit@5 coverage survives higher distractor density and whether an old governing fact remains recoverable after many later updates.

That second pilot should also compare two project-isolation strategies until the FalkorDB `group_id` issue is understood:

1. one Graphiti database per project;
2. one shared database with an independently verified fixed/alternative namespace search path.

Only after that test should Soma integration design be treated as justified.
