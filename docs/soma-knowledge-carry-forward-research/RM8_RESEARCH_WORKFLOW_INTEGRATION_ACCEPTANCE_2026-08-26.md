# RM8 — Research Workflow Integration Acceptance

**Date:** 2026-08-26
**Programme:** Soma Hybrid Research Map
**Stage:** RM8
**Status:** ACCEPTED
**Implementation authority:** `docs/SOMA_HYBRID_RESEARCH_MAP_IMPLEMENTATION_PLAN_2026-08-24.md`
**Accepted RM7 seal HEAD:** `9d116a100a72ab81f46ad50ccd70b9289415b64e`
**RM8 workflow-validation commit:** `4aecd33ecbe2b9f3f77ce4f4681321c17c32e96e`
**RM8 public-surface strengthening commit:** `c62c9848b7741b64999638f36caafa6794751bc8`
**Branch:** `rollback/pre-core-hardening-20260823`
**Push:** none

## 1. Acceptance boundary

RM8 is accepted as **controller workflow integration validation only**.

No production workflow engine, semantic router, automatic next-action mechanism, hidden research orchestrator, automatic sidecar generator, or second reasoning head was added.

RM8 changed only:

```text
tests/test_research_map_rm8_workflow.py
```

The accepted production surfaces from RM6/RM7 already compose correctly for the required research workflow.

`arash-research` was not modified or published. Skill publication remains deferred until after RM11/full roadmap acceptance.

## 2. Controller workflow proven

The accepted RM8 workflow is:

```text
start/re-enter research
→ duplicate-iteration guard before creating a numbered report
→ inspect map health/coverage when adopted
→ use semantic search only as navigation/candidate context
→ reopen exact authoritative Markdown before material reliance
→ conduct evidence-first research
→ save authoritative Markdown report first
→ Sol adjudicates carry-forward semantics
→ save reviewed sidecar or reviewed-no-material sidecar
→ explicitly sync/reconcile research map
→ read-back relation/health state
→ report scientific result and map completion/degraded state separately
```

This is controller discipline over explicit public capabilities. Soma does not decide scientific relevance or completion.

## 3. Capability-aware fallback acceptance

The non-adopted workflow is proven to continue evidence-first research and preserve the authoritative report without creating research-map runtime state.

Accepted terminal state:

```text
research_saved + map_finishing_touch_unavailable
```

The research report remains durable even when the map feature is not adopted.

Legacy RAGFlow/context-packet research is not revived as a substitute.

## 4. Adopted successful workflow acceptance

The adopted workflow proves all of the following in order:

1. a reviewed prior relation is published;
2. prior semantic context is queried;
3. returned candidate reports `source_verification = verified`;
4. the exact reported source path is reopened;
5. the exact source anchor is verified in current authoritative Markdown;
6. the new numbered research report is created once;
7. duplicate report creation is refused by the controller-side existence guard;
8. coverage becomes incomplete while the new authoritative report lacks a reviewed sidecar;
9. a reviewed sidecar is written only after the report exists;
10. explicit sync publishes the new desired state;
11. health reports complete coverage and verified publication;
12. exact relation read-back verifies the new anchor;
13. repeated sync converges to `already_current` without creating another generation.

Accepted terminal state:

```text
research_saved + map_synced_verified
```

## 5. Exact-source trust rule acceptance

RM8 preserves the Research Map trust rule:

```text
retrieved graph relation = candidate navigation context
current exact source Markdown = scientific authority
```

A retrieved relation is not treated as authoritative merely because semantic search returned it.

The workflow explicitly reopens the exact source path and verifies the exact anchor before the prior result can materially affect the next research action.

## 6. Duplicate/interruption safety acceptance

The controller-side report helper refuses creation when the numbered report path already exists.

The accepted workflow independently distinguishes these durable stages:

```text
research report
reviewed sidecar
published map generation
```

Repeated finishing-touch execution is proven idempotent:

```text
first explicit sync → synchronized
repeat explicit sync → already_current
published generation set unchanged
```

Therefore a stream cut can resume from the first missing stage rather than duplicate a scientific iteration or semantic fact.

## 7. Degraded-sync acceptance

RM8 injects a backend persistence failure after both the authoritative report and reviewed sidecar exist.

The failure proves:

```text
report bytes unchanged
sidecar bytes unchanged
no CURRENT generation published
scientific result not rolled back
```

Accepted degraded terminal state:

```text
research_saved + sidecar_saved + map_sync_degraded
```

After the injected outage is removed:

```text
resume sync → synchronized
repeat sync → already_current
exact relation read-back → found
```

Thus map failure is exposed as a finishing-touch degradation rather than being allowed to erase or rewrite completed scientific work.

## 8. Reviewed-no-material acceptance

RM8 explicitly proves that a completed authoritative report with no material carry-forward semantics still requires a reviewed sidecar.

Before the reviewed-no-material sidecar:

```text
coverage_state = incomplete
```

After a reviewed sidecar with:

```text
review.state = reviewed
review.materiality = none
relations = []
```

and explicit sync:

```text
relation_count = 0
coverage_state = complete
sync_state = published_verified
```

This closes coverage without inventing semantic facts.

## 9. Public ProjectScope surface composition

The final strengthening test validates the controller workflow through Soma's actual project-scoped public server wrappers rather than relying only on direct engine composition.

The test composes:

```text
server.research_map_action(sync)
→ server.research_map_query(health)
→ server.research_map_query(relation)
```

with exact ProjectScope binding metadata.

Verified on every applicable response:

```text
resource_id = res_rm8
scope_generation = 8
```

The public sync returns:

```text
status = synchronized
```

Public health returns:

```text
coverage_state = complete
sync_state = published_verified
```

Public relation read-back returns:

```text
status = found
anchor = public exact anchor
```

This closes the final RM8 acceptance-strength gap: the workflow is proven through the accepted public ProjectScope surfaces, not merely inferred from lower-level tests.

## 10. Focused RM6–RM8 validation

An initial RM8 focused run found two test-harness errors because the new tests assumed a nonexistent Boolean `coverage_complete` field.

Durable run:

```text
20260825T230347Z_executable_profile_4656116a
2 failed, 31 passed
```

The production contract was not changed. The harness was corrected to the already accepted public contract:

```text
coverage_state ∈ {not_adopted, disabled, degraded, empty, incomplete, complete}
```

Corrected focused gate:

```text
20260825T230516Z_executable_profile_afe23a90
33 passed
```

After adding the explicit public ProjectScope surface composition test, the final focused gate is:

```text
20260825T234100Z_executable_profile_b4121dc7
34 passed
0 failed
9.67s
```

The first failure therefore strengthened the test model; it did not reveal or motivate a production-contract change.

## 11. Static hygiene

Final RM8 hygiene:

```text
Ruff on tests/test_research_map_rm8_workflow.py: PASS
git diff --check: PASS
```

Durable final run:

```text
20260825T234124Z_executable_profile_212355ca
RM8_STATIC_HYGIENE_PASS
```

## 12. Baseline-equivalent broad regression

RM8 uses exactly the same nine inherited exclusions as RM6/RM7 and adds no RM8-specific exclusion.

Pre-strengthening broad gate:

```text
20260825T230624Z_executable_profile_f4b85591
3634 passed
37 skipped
1 xfailed
13 warnings
0 failed
222.18s / 3:42
```

Final broad gate after the public-surface strengthening:

```text
20260825T234138Z_executable_profile_201ecbb7
3635 passed
37 skipped
1 xfailed
13 warnings
0 failed
227.42s / 3:47
```

Relative to RM7's 3,630-pass baseline-equivalent suite, RM8 contributes exactly five new passing integration tests.

The inherited exclusions remain exactly:

1. `tests/test_cf1_run_query_baseline.py::test_cf1_query_plan_baseline_captures_current_index_behavior`
2. `tests/test_chat_footprint_acceptance.py::test_projection_overhead_and_full_retrieval_performance`
3. `tests/test_repo_candidate_validation_json_g6.py::test_g6_1_excessive_nesting_becomes_bounded_invalid_evidence`
4. `tests/test_parallel_powershell_acceptance.py::test_live_eight_process_cap_keeps_excess_children_pending_then_refills`
5. `tests/test_service_manager_script.py::test_direct_server_start_restart_stop_on_isolated_port`
6. `tests/test_service_manager_script.py::test_server_start_rolls_oversized_logs_and_prunes_archives`
7. `tests/test_service_manager_script.py::test_tui_start_restart_stop_on_isolated_port`
8. `tests/test_service_manager_script.py::test_interactive_menu_launches_and_displays_profile`
9. `tests/test_server.py::test_ssh_inspection_honors_response_budget`

## 13. Live public identity

RM8 modifies tests only, so a service restart would not activate any new served code and would add unnecessary operational risk.

Live capability identity remains the accepted RM7 identity:

```text
actions_count = 40
operation_inventory_hash = b5308c14459684fbd5601846e81a40a3731a9d7aad4eb1c26897604749066aad
public_schema_hash = ebb3e321a991058d1f4f96e566b462e585c42bbf8e098cca76a486f592ae6828
public_descriptor_hash = 2486021181876f30e042b1c9497f83f7c8f16a5b4f97cc4dd1c3c169731e67d2
server_build_hash = a1f5a7ce3120bf9a44d2e2bc77916c4e9fd048544dbb683118f52913558eaee4
```

Live `self_check` passed **10/10** checks after the final RM8 test-only commits.

Therefore RM8 introduces no public contract drift and requires no runtime reload.

## 14. Preserved architecture boundaries

RM8 preserves:

- authoritative scientific truth in research Markdown;
- Sol/ChatGPT as semantic adjudication authority;
- reviewed sidecars as explicit tracked semantic judgments;
- graph/search results as navigation candidates only;
- exact authoritative source reopening before material reliance;
- explicit, not hidden, map sync/reconcile;
- scientific durability independent of backend/index availability;
- duplicate/interruption safety by inspecting durable stages;
- no semantic planner/router;
- no automatic next-action engine;
- no automatic relation generation;
- no second reasoning model;
- no RAGFlow/context-packet revival;
- no normal Docker requirement;
- no `arash-research` modification or publication;
- no push.

## 15. Verdict

**RM8 ACCEPTED.**

The existing RM6/RM7 production capabilities are sufficient for the canonical controller-visible research workflow. RM8 therefore correctly closes as an integration-acceptance stage with test-only changes, rather than adding hidden orchestration to Soma.

The next implementation boundary is:

```text
RM9 — controlled NSDN rollout
```

RM9 may adopt/backfill NSDN according to the canonical rollout order and fixed 15/15 Top-5 benchmark. It must not start Axon RM10, must not mechanically bulk-generate semantic sidecars, and must not modify/publish `arash-research` before RM11/full-roadmap acceptance.
