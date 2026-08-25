# RM7 — Semantic Search and Read-Only Acceptance

**Date:** 2026-08-26
**Programme:** Soma Hybrid Research Map
**Stage:** RM7
**Status:** ACCEPTED
**Implementation authority:** `docs/SOMA_HYBRID_RESEARCH_MAP_IMPLEMENTATION_PLAN_2026-08-24.md`
**Accepted RM6 base HEAD:** `2e90eaf485ebcd79167ca9cde7e8056874b93a54`
**RM7 implementation commit:** `89890b41bf32c050281a4496d6af0e37a6910abb`
**Branch:** `rollback/pre-core-hardening-20260823`
**Push:** none

## 1. Accepted boundary

RM7 activates the already schema-visible `research_map_query(search)` operation against only an accepted RM6 published generation.

The accepted query path is read-only. It does not invoke `sync`, `rebuild`, adoption, sidecar generation, backend startup, backend persistence, or any hidden repair path.

RM7 does not modify `arash-research`, does not introduce a semantic router/planner, does not add a second reasoning head, and does not make the optional research-map backend a normal Soma startup dependency.

The public tool count remains **40**.

## 2. Accepted search trust chain

A successful search now follows this mechanical trust chain:

```text
exact project/repository scope
→ healthy reviewed tracked semantic state
→ complete research-map coverage
→ verified CURRENT.json
→ immutable published RELATIONS.json
→ exact repository UID / desired-state / projection-contract match
→ exact live backend relation-manifest match
→ semantic search only against CURRENT.database
→ returned relation IDs resolved against immutable published relations
→ lifecycle filter
→ exact current source reopen
→ canonical source-hash verification
→ exact-anchor verification
→ bounded candidate projection
```

Search never promotes backend text to scientific authority. The immutable reviewed relation artifact identifies the candidate; the current authoritative source is reopened and verified before the candidate is returned as verified.

## 3. Failure-closed behavior

RM7 rejects or bounds the following without mutation:

- research map not adopted or disabled;
- degraded semantic state or incomplete coverage;
- missing, corrupt, stale, or metadata-mismatched published generation;
- invalid published source path/hash metadata;
- backend relation-manifest drift;
- backend outage/runtime failure;
- backend search hit outside the published relation set;
- stale/missing/non-UTF-8/oversized source;
- source canonical-hash mismatch;
- missing exact anchor;
- pathological result text or backend diagnostics that would exceed response budgets.

No failure path stages a generation or repairs scientific/index state implicitly.

## 4. Lifecycle and response semantics

Default search excludes non-current relations.

`include_noncurrent=true` explicitly allows reviewed historical/non-current relations to appear.

Each returned candidate includes:

- rank;
- deterministic relation ID;
- backend score when available;
- source/target semantic keys;
- predicate and reviewed statement;
- exact source path;
- canonical source SHA-256;
- exact source anchor;
- epistemic class;
- lifecycle;
- `source_verification = verified`.

The query echo is bounded to a preview plus a query SHA-256. Candidate statement/anchor fields are bounded, result lists shrink to the requested byte budget, and public error diagnostics are capped and further reduced if necessary.

## 5. Focused RM3–RM7/public-contract validation

Final focused validation:

```text
70 passed
0 failed
1 warning
15.66s
```

Durable run:

```text
20260825T223304Z_executable_profile_c981a4c6
```

The warning is Graphiti 0.29.3's existing Pydantic-v2 deprecation warning and is not a Soma failure.

An earlier focused run exposed only one historical RM3 assertion that still expected the pre-RM7 `backend_unavailable` stub. The test was updated to the intentional RM7 stage semantics (`published_generation_missing` for an adopted repository that has never published a generation) while preserving the original no-runtime-mutation assertion. Production semantics were not weakened to satisfy the old snapshot.

## 6. Frozen NSDN scientific retrieval acceptance

RM7 re-used the exact frozen NSDN reviewed corpus/questions from the accepted standalone pilot rather than inventing a new benchmark:

```text
30 reviewed relations
15 adversarial natural-language questions
required Top-5 coverage = 15/15
```

Final real-backend result:

```text
Top-5 coverage = 15/15
Hit@1 = 8/15 = 53.3333333333%
misses = []
ranks = [3, 4, 1, 1, 2, 2, 5, 1, 1, 1, 2, 1, 1, 3, 1]
repeat_top5_exact = true
source_verification_all = true
persistent_state_unchanged = true
reopen_verified = true
```

## 7. Frozen Axon scientific retrieval acceptance

RM7 re-used the exact difficult Axon slice from the accepted persistence/backend research:

```text
38 reviewed relations
20 adversarial natural-language questions
required Top-5 coverage = 20/20
```

Final real-backend result:

```text
Top-5 coverage = 20/20
Hit@1 = 10/20 = 50%
misses = []
ranks = [1, 4, 1, 2, 1, 3, 3, 1, 1, 2, 1, 1, 1, 1, 1, 2, 3, 2, 2, 2]
repeat_top5_exact = true
source_verification_all = true
persistent_state_unchanged = true
reopen_verified = true
```

Hit@1 is reported descriptively only; the canonical RM7 primary retrieval target is Top-5 governing-fact coverage.

## 8. Independent reproduction of the frozen retrieval gate

The complete 35-question real-backend acceptance was executed twice.

First complete pass:

```text
20260825T222751Z_executable_profile_2960ef04
```

Final post-hardening reproduction:

```text
20260825T223357Z_executable_profile_84c71c42
```

Both runs produced the exact same NSDN and Axon rank vectors, 35/35 combined Top-5 coverage, no misses, exact repeat Top-5 lists on a second query pass, complete current-source verification, and unchanged persistent state.

The second run is the final RM7 scientific acceptance authority because it was executed after the last failure-classification/response-bounding hardening.

## 9. Read-only mutation proof

The real-backend harness snapshots the authoritative/persistent state before and after repeated search calls.

Verified unchanged:

```text
tracked repository content/status
CURRENT.json
published immutable generation files/hashes
tracked sidecars
backend relation manifest
```

Both NSDN and Axon report:

```text
persistent_state_unchanged = true
repeat_top5_exact = true
```

Therefore the accepted RM7 search path is a reader of accepted state, not an implicit maintainer/writer.

## 10. Source verification proof

Every candidate returned by the frozen benchmark passed:

```text
exact repository
exact repo-relative source path
matching LF-normalized canonical source SHA-256
exact anchor present in the current authoritative source
```

Both final corpora report:

```text
source_verification_all = true
```

Unit regressions additionally cover stale source, malformed published source path, corrupt generation artifacts, and exact-anchor failure boundaries.

## 11. Real backend and explicit startup boundary

The scientific gate used the same disposable real FalkorDB conformance setup already accepted by RM6:

```text
falkordb/falkordb:v4.20.4
host = 127.0.0.1
port = 16379
```

The backend was explicitly started outside the query path. RM7 search itself never starts/configures the backend.

The disposable container was removed after acceptance:

```text
20260825T223714Z_executable_profile_72219222
```

Docker Desktop had been started only for this conformance session and was cleanly stopped afterward:

```text
20260825T223729Z_executable_profile_4dbc79ec
DOCKER_DESKTOP_STOPPED
```

No test container is part of normal Soma runtime or RM7 query semantics.

## 12. Public-contract identity

Final pre-activation contract measurement:

```text
tool_count = 40
public_schema_hash = ebb3e321a991058d1f4f96e566b462e585c42bbf8e098cca76a486f592ae6828
input_schema_digest = 5513e3bd3bce5edd38f47295ec7027f1cfdadc0c79d1d2c29126e5c4deaaf6c9
output_schema_digest = 34ee85b1e7fe62572c6974e0607f53ab072e6e9dd9cfa7dc22b6e2244576c21a
operation_inventory_hash = b5308c14459684fbd5601846e81a40a3731a9d7aad4eb1c26897604749066aad
public_descriptor_hash = 2486021181876f30e042b1c9497f83f7c8f16a5b4f97cc4dd1c3c169731e67d2
```

Durable measurement:

```text
20260825T224858Z_executable_profile_11086a04
```

Relative to RM6:

- tool count: unchanged;
- public input schema: unchanged;
- public output schema: unchanged;
- public schema hash: unchanged;
- operation shape/inventory hash: unchanged;
- public descriptor hash: intentionally changed because `research_map_query` now truthfully describes active read-only semantic search over verified published generations rather than search availability only.

Thus RM7 activates an already schema-visible operation without expanding the public input/output shape.

## 13. Static hygiene

Final proportionate RM7 hygiene:

```text
Ruff on RM7 implementation/test surface: PASS
git diff --check: PASS
```

Durable run:

```text
20260825T224842Z_executable_profile_af7061ea
```

A deliberately broader Ruff attempt (`20260825T224653Z_executable_profile_771e8e3b`) also surfaced pre-existing style debt in already-existing public-contract files/tests. RM7 corrected its new-code import/exception issues but did not widen scope into unrelated baseline refactors.

## 14. Baseline-equivalent broad regression

RM7 re-used exactly the same nine inherited RM3/RM5 exclusions as RM6 and added no RM7-specific exclusion.

Final 12-worker broad regression:

```text
3630 passed
37 skipped
1 xfailed
13 warnings
0 failed
233.24s / 3:53
```

Durable run:

```text
20260825T224942Z_executable_profile_9373aca5
```

The nine inherited exclusions are exactly:

1. `tests/test_cf1_run_query_baseline.py::test_cf1_query_plan_baseline_captures_current_index_behavior`
2. `tests/test_chat_footprint_acceptance.py::test_projection_overhead_and_full_retrieval_performance`
3. `tests/test_repo_candidate_validation_json_g6.py::test_g6_1_excessive_nesting_becomes_bounded_invalid_evidence`
4. `tests/test_parallel_powershell_acceptance.py::test_live_eight_process_cap_keeps_excess_children_pending_then_refills`
5. `tests/test_service_manager_script.py::test_direct_server_start_restart_stop_on_isolated_port`
6. `tests/test_service_manager_script.py::test_server_start_rolls_oversized_logs_and_prunes_archives`
7. `tests/test_service_manager_script.py::test_tui_start_restart_stop_on_isolated_port`
8. `tests/test_service_manager_script.py::test_interactive_menu_launches_and_displays_profile`
9. `tests/test_server.py::test_ssh_inspection_honors_response_budget`

RM7 contributes nine additional passing tests relative to the RM6 baseline-equivalent count.

## 15. Live service activation

After committing RM7 implementation at `89890b41bf32c050281a4496d6af0e37a6910abb`, the Soma service was restarted using the repository's accepted service manager.

Durable restart run:

```text
20260825T225456Z_executable_profile_a949fe23
exit_code = 0
```

The connector briefly returned a transient 502 during process turnover, then recovered normally.

Live capability identity after restart:

```text
actions_count = 40
operation_inventory_hash = b5308c14459684fbd5601846e81a40a3731a9d7aad4eb1c26897604749066aad
public_schema_hash = ebb3e321a991058d1f4f96e566b462e585c42bbf8e098cca76a486f592ae6828
public_descriptor_hash = 2486021181876f30e042b1c9497f83f7c8f16a5b4f97cc4dd1c3c169731e67d2
server_build_hash = a1f5a7ce3120bf9a44d2e2bc77916c4e9fd048544dbb683118f52913558eaee4
```

The live descriptor exactly matches the pre-activation RM7 measurement while the public schema remains unchanged.

Live `self_check` passed **10/10** checks, including imports, packages, config, run store, startup reconciliation, supervisor state/config, service identity, and comprehensive validation.

## 16. Canonical RM7 acceptance criteria

### Retrieval acceptance — PASS

```text
NSDN Top-5 governing-fact coverage = 15/15
Axon Top-5 governing-fact coverage = 20/20
combined = 35/35
```

Hit@1 was measured and reported but was not substituted for the frozen Top-5 target.

### Read-only acceptance — PASS

Repeated search calls left tracked files, CURRENT, immutable generation artifacts, sidecars, and backend relation manifests unchanged.

### Source verification acceptance — PASS

Every returned candidate passed exact source path, canonical source hash, and exact-anchor verification against the current authoritative repository source.

## 17. Preserved programme boundaries

RM7 preserves:

- research Markdown as authoritative scientific truth;
- Sol/ChatGPT as semantic adjudication authority;
- reviewed sidecars as tracked semantic judgments;
- immutable published generations as derived/rebuildable runtime state;
- continuation as current-position/re-entry state rather than scientific truth;
- no automatic semantic sidecar generation;
- no automatic semantic planner/router;
- no second reasoning head;
- no provider/API credential requirement;
- no normal Docker requirement;
- no automatic backend startup;
- no hidden sync/rebuild/repair in query paths;
- `arash-research` remains unchanged during the roadmap;
- reusable Skill publication remains deferred until after RM11/full roadmap acceptance;
- no push.

## 18. Verdict

**RM7 ACCEPTED.**

Semantic search over accepted immutable published generations now satisfies the frozen NSDN/Axon retrieval targets, repeated-query read-only proof, exact source verification, bounded failure semantics, unchanged public schema, baseline-equivalent regression, and live-service activation requirements.

The next implementation boundary is:

```text
RM8 — research workflow integration acceptance
```

RM8 is controller workflow validation only. It must remain capability-aware, reopen exact authoritative sources before relying on retrieved context, finish authoritative Markdown before reviewed semantic sidecar/sync/read-back finishing touches, preserve duplicate-iteration guards, avoid hidden semantic routing/automatic relation generation, and **must not modify or publish `arash-research`**.
