# RM5 — Backend Protocol and Graphiti/FalkorDB Conformance Acceptance

**Date:** 2026-08-25
**Programme:** Soma Hybrid Research Map
**Stage:** RM5
**Status:** ACCEPTED
**Implementation authority:** `docs/SOMA_HYBRID_RESEARCH_MAP_IMPLEMENTATION_PLAN_2026-08-24.md`
**Accepted RM4 base HEAD:** `a07dcf7b120ba7db670a4b1c380865f417844d22`
**RM5 implementation commit:** `e373cbe18d3ef9b9530704b48bb9a7a6537c9465`
**Branch:** `rollback/pre-core-hardening-20260823`

## 1. Accepted boundary

RM5 adds the backend-neutral deterministic Research Map projection protocol and one lazy optional Graphiti/FalkorDB adapter.

RM5 does not add sync/rebuild publication, immutable generations, automatic repository adoption, automatic research-map startup, semantic sidecar generation, or a new public MCP gateway.

The public Research Map write/read surface therefore remains the RM4 40-tool contract.

## 2. Runtime/resource policy

Docker is **not** a normal Soma or Research Map runtime dependency.

RM5 used one disposable pinned FalkorDB server container only to prove the server-backed adapter on the production Windows host. The container was removed after conformance and Docker Desktop was stopped successfully.

Normal Research Map backend execution must remain lazy/on-demand and independent of Soma startup. A future backend process may be hosted by an on-demand local runtime such as WSL or another conforming local server behind the same protocol. RM5 does not authorize a permanently resident Docker backend.

Native `falkordblite==0.10.0` was explicitly tested on Windows and rejected because its `redislite` dependency aborts on `win32`. Production code was therefore not coupled to FalkorDB Lite.

## 3. Backend-neutral protocol

New module:

```text
soma/research_map/backend.py
```

The protocol deterministically projects reviewed Research Map desired state into backend-safe nodes and relations without importing Graphiti, FalkorDB, FastEmbed, or provider SDKs.

The projection preserves the reviewed semantic identity and relevant source/provenance payload needed for exact read-back reconciliation.

Backend structured values are encoded canonically rather than relying on graph-database support for arbitrary nested dictionaries.

## 4. Optional Graphiti/FalkorDB adapter

New module:

```text
soma/research_map/graphiti_backend.py
```

Accepted properties:

- Graphiti imports are lazy and optional;
- backend absence does not break core Soma imports/startup;
- no provider/API credentials are required;
- the Graphiti LLM path is replaced by a fail-closed NoLLM implementation;
- local BGE embedding is used;
- direct deterministic `EntityNode` / `EntityEdge` saves are used;
- model-mediated `add_episode()` / semantic triplet extraction is not used;
- Graphiti search is invoked without relying on `group_id` isolation;
- explicit persistence is separate from `close()`;
- relation read-back is checked against Soma-owned deterministic relation identities.

## 5. Optional dependency contract

`pyproject.toml` keeps the existing core dependency list unchanged:

```text
fastmcp
pydantic
pyyaml
```

RM5 adds only an optional extra:

```text
research-map = [
  graphiti-core==0.29.3,
  fastembed==0.8.0,
  falkordb==1.7.1,
  httpx==0.28.1,
]
```

`falkordblite` is intentionally absent from the Windows optional extra.

The validated host environment reported no broken Python requirements after installation.

## 6. RM5 roadmap acceptance criteria

The canonical RM5 contract lists eleven backend conditions. All are accepted:

1. **No provider/API credential required — PASS.**
2. **Graphiti LLM path raises if invoked — PASS.**
3. **Local BGE embedding dimension stable — PASS, 384 dimensions.**
4. **Direct deterministic entity/edge projection — PASS.**
5. **Structured sidecar facets survive adapter encoding/round-trip — PASS.**
6. **Close without explicit SAVE covered negatively — PASS.**
7. **Explicit SAVE persists across process restart — PASS.**
8. **Relation read-back exactly matches desired projection set — PASS.**
9. **Repeated reopen/query deterministic Top-5 on fixed corpus — PASS.**
10. **No `group_id` isolation dependency — PASS.**
11. **Backend unavailable does not break Soma startup/core import path — PASS by lazy optional boundary and negative dependency test.**

## 7. Exact Axon conformance corpus

RM5 reused the difficult Iteration-12 Axon slice:

```text
14 authoritative source documents
38 reviewed relations
20 adversarial natural-language questions
```

The historical disposable pilot sidecars were converted only inside a temporary conformance directory to the current production v2 schema. The authoritative Axon source documents and original pilot repository were not modified.

One historical vocabulary alias required normalization in that disposable conversion:

```text
design_requirement -> requirement
```

After conversion, the production scanner reported:

```text
records: 14
relations: 38
queries: 20
coverage_complete: true
health: healthy
issues: []
```

## 8. Retrieval and persistence conformance

First independent server-backed process:

```text
relation_count = 38
embedding_dimension = 384
explicit SAVE = true
Hit@1 = 0.40
Hit@3 = 0.95
Hit@5 = 1.00
MRR = 0.6708333333333333
```

All 20 adversarial questions recovered at least one expected governing relation inside Top-5.

A second completely separate Python process reopened the persisted graph and produced:

```text
relation_count = 38
Hit@1 = 0.40
Hit@3 = 0.95
Hit@5 = 1.00
MRR = 0.6708333333333333
exact_top5_match = true
```

Thus every Top-5 list for all 20 questions matched the first process exactly after persistence/reopen.

Durable conformance runs include:

```text
20260825T194256Z_executable_profile_6ddcab44
20260825T194355Z_executable_profile_3a23a283
```

## 9. Focused and Research Map regression evidence

Focused RM5 backend tests after the final negative regressions:

```text
8 passed
0 failed
```

Research Map RM1-RM5 regression slice:

```text
51 passed
0 failed
```

The only Graphiti warning is upstream Pydantic-v2 deprecation behavior inside Graphiti 0.29.3 and is not a Soma failure.

## 10. Static/dependency hygiene

Final RM5 hygiene passed:

```text
ruff: PASS
git diff --check: PASS
pip check: PASS
```

No Docker runtime remains active from the conformance test.

## 11. Broad regression and inherited baseline debt

The first unrestricted 12-worker diagnostic run produced:

```text
3602 passed
37 skipped
1 xfailed
7 failed
```

All seven failures are part of the nine cases that RM3 had already explicitly documented as inherited baseline/environmental debt before RM4 and before RM5:

```text
tests/test_cf1_run_query_baseline.py::test_cf1_query_plan_baseline_captures_current_index_behavior
tests/test_chat_footprint_acceptance.py::test_projection_overhead_and_full_retrieval_performance
tests/test_repo_candidate_validation_json_g6.py::test_g6_1_excessive_nesting_becomes_bounded_invalid_evidence
tests/test_parallel_powershell_acceptance.py::test_live_eight_process_cap_keeps_excess_children_pending_then_refills
tests/test_service_manager_script.py::test_direct_server_start_restart_stop_on_isolated_port
tests/test_service_manager_script.py::test_server_start_rolls_oversized_logs_and_prunes_archives
tests/test_service_manager_script.py::test_tui_start_restart_stop_on_isolated_port
```

RM3 additionally documents two inherited exclusions that did not fail in the unrestricted RM5 diagnostic:

```text
tests/test_service_manager_script.py::test_interactive_menu_launches_and_displays_profile
tests/test_server.py::test_ssh_inspection_honors_response_budget
```

The RM4 record had described its 3592-pass run as a broad/full regression but did not state that these same nine cases were deselected. The authoritative RM4 run input confirms the exclusions. RM5 therefore uses the already-established RM3 baseline explicitly rather than treating those cases as new RM5 failures.

The final baseline-equivalent RM5 acceptance command used **exactly those nine existing exclusions and no new exclusions**.

A first attempt exposed one unrelated xdist temp-path flake in:

```text
test_pytest_launcher_creates_missing_nested_parent_and_preserves_siblings
```

That case passed immediately in isolation:

```text
1 passed in 1.66s
```

It was **not** added to the exclusion set.

The unchanged repeat 12-worker baseline-equivalent acceptance gate then passed cleanly:

```text
3600 passed
37 skipped
1 xfailed
13 warnings
0 failures
236.26s / 3:56
```

Durable run:

```text
20260825T202419Z_executable_profile_3b50c08d
```

This establishes zero new RM5 failures relative to the accepted RM3/RM4 baseline.

## 12. Soma package/import diagnosis is deferred

During investigation of the inherited service-manager tests, the current `.venv` was found not to contain Soma as an installed/editable distribution. `import soma` therefore succeeds from the repository working directory but not from an arbitrary temporary directory.

The RM5 optional dependency installation did not uninstall or replace Soma; its pip transcript only added the optional Graphiti/FalkorDB stack. The same service-manager tests were already explicitly deferred by RM3.

Per owner direction, whether Soma should later be installed editable or the launcher should explicitly provide the source module path is deferred until **after the Research Map roadmap and subsequent baseline bug-fix phase**. RM5 makes no unrelated packaging change.

## 13. Public/architecture invariants

RM5 preserves:

- research Markdown as authoritative scientific truth;
- reviewed tracked sidecars as semantic judgments;
- continuation unchanged as current-position/re-entry state;
- Sol/ChatGPT as the semantic reasoning authority;
- no hidden semantic router/planner or second reasoning head;
- no automatic sidecar generation;
- no automatic backend startup;
- no provider credential dependency;
- no normal Docker dependency;
- one backend protocol independent of a particular local process host;
- `arash-research` remains unchanged during the RM0-RM11 roadmap.

## 14. Verdict

**RM5 ACCEPTED.**

The backend protocol and Graphiti/FalkorDB conformance boundary is complete. The next authorized implementation boundary is:

```text
RM6 — immutable-generation sync/rebuild engine
```

RM6 must preserve RM5's explicit persistence/read-back contract and must not begin by mutating the currently published generation in place.
