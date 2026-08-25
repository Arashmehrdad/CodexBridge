# RM3 — Read-Only Public Research-Map Gateway Acceptance

**Date:** 2026-08-25  
**Programme:** Soma Hybrid Research Map  
**Stage:** RM3  
**Status:** ACCEPTED  
**Implementation authority:** `docs/SOMA_HYBRID_RESEARCH_MAP_IMPLEMENTATION_PLAN_2026-08-24.md`  
**Accepted RM2 base HEAD:** `315fb9e71dc0cab16e4c6cb6583e121ea11cbcaa`  
**Branch:** `rollback/pre-core-hardening-20260823`

## 1. Accepted boundary

RM3 adds the separate, read-only public research-map gateway foundation only.

Accepted public gateway:

```text
research_map_query
```

Accepted operations:

```text
health
coverage
relation
search
```

`search` is intentionally schema-visible but returns bounded:

```text
backend_unavailable
```

until the later semantic backend stage. This keeps the public contract expansion to one deliberate gateway change while avoiding premature Graphiti/backend activation.

RM3 does **not** add `research_map_action`, adoption, runtime/index creation, Graphiti, FalkorDB, FastEmbed, semantic search execution, sidecar generation, sync/rebuild, or legacy knowledge-system changes.

## 2. Exact ProjectScope authority

Every RM3 public operation requires explicit:

```text
project_id
repo_name
```

The server first resolves the configured repository identity and then requires the exact active ProjectScope repository binding through the existing `ProjectScopeStore.resolve_repository(...)` authority.

There is no implicit project selection, repository_uid-to-local-scope substitution, or cross-project fallback.

## 3. Read-only behavior

The gateway scans the portable RM2 source/sidecar state only.

Accepted health behavior includes:

```text
not_adopted
disabled/degraded states
coverage state
sync state
backend state
repository_uid
semantic desired-state hash
issue/coverage counts
```

Coverage is bounded and cursor-based. Cursors are bound to the semantic desired-state hash, so a state change makes an old cursor stale rather than silently continuing against a different research-map state.

Exact relation lookup returns one relation only and fails closed on missing or duplicate relation IDs. The compact relation projection is byte-bounded, including pathological facet/qualifier payloads.

No query operation creates or mutates:

```text
soma.project.json
_soma_map sidecars
.soma/research-map runtime
backend/index state
tracked repository content
```

## 4. Public contract transition

The accepted public surface changes intentionally from 38 to 39 tools.

Two independent served-descriptor discovery passes produced exactly the same identities:

```text
tool_count: 39
public_schema_hash:
932fe027db3299bb06a2490298564a8727dc4dd2c7e34acc4476ccaef34bdb59

public_descriptor_hash:
0a07535c4ad11d8776cf7cc9ca0b418ee09ff961f0707156f16f1082de55af9f

input_schema_digest:
068fb9c88c6b247560667ef4b0fe4cbf5949ef3b16bb597224a3b869b37fad0c

output_schema_digest:
0355af3f2e5cb1ca2cfd4782fae2b365be0021859865bd83adae9b545a60e4dc

operation_inventory_hash:
badc4983a37d9c702c57348be63c5ca05a70f3ca92bf23d140d78c8faec8aca1
```

The corresponding public metadata, gateway inventory, CF1 operation inventory, flat-input contract, transport-content corpus, worker isolation baseline, and discovery tests were updated together.

`research_map_query` metadata is strictly read-only/non-destructive/idempotent/closed-world.

## 5. Focused acceptance evidence

Focused RM3 + public-contract validation:

```text
100 passed in 14.26s
```

This gate covered:

- public request-schema discrimination;
- exact ProjectScope acceptance/rejection;
- unadopted and malformed/degraded health;
- deterministic coverage pagination/cursor behavior;
- stale cursor rejection;
- exact relation retrieval;
- bounded pathological relation payloads;
- schema-visible search backend-unavailable behavior;
- public inventories/metadata;
- public schema and descriptor identity stability.

The three additional public-corpus omissions exposed by the first broad run were corrected and then passed an exact confirmation gate:

```text
3 passed in 4.45s
```

## 6. Broad regression evidence

Final RM3 acceptance regression used 12 pytest-xdist workers.

Result:

```text
3578 passed
36 skipped
1 xfailed
12 warnings
0 failures
244.90s / 4:04
```

The run intentionally deselected nine known non-RM3 baseline/environmental cases listed below.

## 7. Explicit deferred non-RM3 test debt

The following cases are not hidden RM3 acceptance failures and were excluded from the final broad acceptance gate:

```text
tests/test_cf1_run_query_baseline.py::test_cf1_query_plan_baseline_captures_current_index_behavior

tests/test_chat_footprint_acceptance.py::test_projection_overhead_and_full_retrieval_performance

tests/test_repo_candidate_validation_json_g6.py::test_g6_1_excessive_nesting_becomes_bounded_invalid_evidence

tests/test_parallel_powershell_acceptance.py::test_live_eight_process_cap_keeps_excess_children_pending_then_refills

tests/test_service_manager_script.py::test_direct_server_start_restart_stop_on_isolated_port

tests/test_service_manager_script.py::test_server_start_rolls_oversized_logs_and_prunes_archives

tests/test_service_manager_script.py::test_tui_start_restart_stop_on_isolated_port

tests/test_service_manager_script.py::test_interactive_menu_launches_and_displays_profile

tests/test_server.py::test_ssh_inspection_honors_response_budget
```

The final SSH case was isolated independently and failed by itself because the test assumes prior global `server.set_config(...)` state:

```text
RuntimeError: Soma config has not been loaded
```

Therefore it is a pre-existing test-isolation defect, not an RM3/xdist regression and not an RM3 production-source issue.

The interactive menu test also reconfirmed the already-deferred TUI/process-harness timeout class.

## 8. Static/diff hygiene

Final RM3 hygiene:

```text
git diff --check: PASS
ruff check soma/research_map/gateway.py tests/test_research_map_rm3.py: PASS
```

A broader file-wide Ruff invocation was not used as an RM3 acceptance blocker because large pre-existing files such as `soma/gateway_models.py` contain unrelated historical Ruff debt outside the RM3 changed lines.

## 9. Owner and architecture invariants preserved

RM3 preserves the governing boundaries:

1. research Markdown remains authoritative scientific truth;
2. reviewed `_soma_map` sidecars remain durable derived semantic projections;
3. `.soma/` remains local disposable runtime state;
4. exact local ProjectScope remains the authority boundary;
5. no semantic router, second reasoning model, or automatic next-action engine is introduced;
6. no Codex integration is introduced;
7. no legacy `knowledge_query` repair or research-context-packet revival is introduced;
8. no Graphiti/backend dependency is introduced;
9. no research-map mutation is possible through RM3;
10. the `arash-research` Skill remains untouched until the later programme finishing stage.

## 10. Verdict and next boundary

**ACCEPTED — RM3 READ-ONLY PUBLIC GATEWAY FOUNDATION IS COMPLETE.**

After commit and live service verification, the next permitted stage is:

```text
RM4 — explicit adoption and repo-local runtime lifecycle
```

RM4 must not start implicitly. It remains a separate stage with its own implementation and acceptance boundary.
