# RM4 — Explicit Adoption and Repo-Local Runtime Lifecycle Acceptance

**Date:** 2026-08-25  
**Programme:** Soma Hybrid Research Map  
**Stage:** RM4  
**Status:** ACCEPTED  
**Implementation authority:** `docs/SOMA_HYBRID_RESEARCH_MAP_IMPLEMENTATION_PLAN_2026-08-24.md`  
**Accepted RM3 base HEAD:** `4b5765be3e77b9da6183620fbfd8ccc37eff02e4`  
**RM4 implementation commit:** `a1dd73670143a655a0ac3110852983f2db5644bc`  
**Branch:** `rollback/pre-core-hardening-20260823`

## 1. Accepted boundary

RM4 adds the explicit write-side adoption/attachment lifecycle only:

```text
research_map_action(action="adopt")
```

RM4 does not add semantic sidecar generation, Graphiti/FalkorDB/FastEmbed, embedding execution, index construction, sync, rebuild, semantic search execution, automatic repository adoption, or any legacy research-system repair.

## 2. Exact ProjectScope authority

Every public RM4 adoption requires explicit:

```text
project_id
repo_name
```

The gateway resolves the configured repository and then requires the exact active `ProjectScopeStore.resolve_repository(...)` binding before any repository mutation is allowed.

A mismatched project/repository pair fails closed as `scope_mismatch`.

Portable `repository_uid` never substitutes for local ProjectScope write authority. Two clones may legitimately preserve the same portable repository UID while still requiring their own exact local ProjectScope bindings.

## 3. First adoption

When no `soma.project.json` exists, first adoption requires explicit research roots.

Accepted behavior:

```text
validate explicit roots
→ create one stable srepo_<id> repository_uid
→ atomically publish soma.project.json without replacement
→ resolve Git's local info/exclude path
→ idempotently ensure /.soma/
→ initialize .soma/research-map/generations/
→ report backend/index state as unavailable/missing
```

The tracked manifest contains only portable logical configuration. It does not contain local ProjectScope IDs, resource IDs, repository absolute paths, or local runtime state.

The first adoption creates no `_soma_map` sidecars and builds no semantic index.

## 4. Existing-manifest / clone attachment

When a valid existing manifest is present:

```text
validate manifest
→ preserve repository_uid
→ validate any explicitly supplied roots against manifest roots
→ ensure local /.soma/ exclude
→ initialize local runtime directories if absent
→ report CURRENT as missing or stale/unverified
```

The operation never rewrites a valid existing manifest merely because a clone has a different local ProjectScope identity.

Conflicting roots fail closed as `root_conflict`.

Malformed manifests fail closed and are not repaired or replaced automatically.

## 5. Idempotency and bounded public response

A second identical adoption is idempotent:

- repository UID remains unchanged;
- manifest bytes remain unchanged;
- Git exclude rule is not duplicated;
- runtime directories are not recreated unnecessarily;
- no sidecars are generated;
- no index is built.

The public acknowledgement remains bounded even with the maximum configured root count. It reports `root_count` plus a deterministic `roots_sha256` rather than echoing the full root configuration.

## 6. Public contract transition

RM4 intentionally changes the public surface from 39 to 40 gateways by adding:

```text
research_map_action
```

Live post-restart capability identity:

```text
actions_count: 40
operation_inventory_gateway_count: 40

public_schema_hash:
2bd41e87b1a537af14b934b8776b162484d1cd1280f9b0c2256d5713410bed44

public_descriptor_hash:
bc7880f873d8cae4be1f2a882e11e3b7e72659c661cf0d955936df9242249c0a

operation_inventory_hash:
4fc5ced416c4c47b81340386b8341c9020475e767f1f67f6ab0cce03fb761376

server_build_hash:
342d3130809bb3108f4e5188e1dc234ed3197a0f76a91440904f4a70383579da
```

The public metadata, public gateway inventory, CF1 operation inventory, flat-input contract, descriptor identity tests, transport-content corpus, discovery tests, and worker-isolation baseline were updated together.

## 7. Focused validation

Final focused RM4 + RM3/public-contract validation:

```text
313 passed
28 skipped
0 failures
18.24s
```

Durable run:

```text
20260825T183554Z_executable_profile_6c95d9da
```

This gate covers:

- first adoption;
- explicit-root requirement;
- portable manifest contents;
- Git local exclude behavior;
- repo-local runtime initialization;
- second-adoption idempotency;
- conflicting-root refusal;
- clone attachment and UID preservation;
- stale/unverified CURRENT reporting without rebuild;
- malformed-manifest refusal;
- exact ProjectScope duplicate-clone write isolation;
- bounded maximal-root acknowledgement;
- public schema/inventory/transport regression coverage.

## 8. Broad regression evidence

The completed interrupted RM4 validation state also ran the full 12-worker regression successfully before the acceptance checkpoint:

```text
3592 passed
37 skipped
1 xfailed
12 warnings
0 failures
239.18s / 3:59
```

Durable run:

```text
20260825T172354Z_executable_profile_c22e5c9b
```

The warnings are the existing Pydantic settings forward-reference warning class and are not RM4 failures.

## 9. Static/diff hygiene

Final RM4 hygiene against the accepted source bytes:

```text
git diff --check: PASS
ruff check soma/research_map/adoption.py tests/test_research_map_rm4.py: PASS
```

Durable run:

```text
20260825T183642Z_executable_profile_bf2a910c
```

## 10. Live activation

The committed RM4 source was activated through a bounded server-only restart.

Restart run:

```text
20260825T183854Z_executable_profile_000073cd
exit_code: 0
```

The expected transient 502 occurred while the local server was restarting. After recovery, live capability discovery returned the 40-tool contract and hashes recorded above.

## 11. Architecture invariants preserved

RM4 preserves the governing boundaries:

1. repository research Markdown remains authoritative scientific truth;
2. Sol remains the semantic adjudicator;
3. tracked reviewed sidecars remain rebuildable semantic projections;
4. `.soma/research-map/` remains local derived runtime;
5. continuation remains a separate re-entry mechanism;
6. repository discovery alone creates no research-map state;
7. adoption never creates semantic relations automatically;
8. Graphiti/backend work remains deferred to RM5;
9. sync/rebuild remains deferred to RM6;
10. the reusable research Skill remains unchanged during RM0-RM11 and is updated only after the whole Research Map roadmap is complete and accepted.

## 12. Verdict and next boundary

**ACCEPTED — RM4 EXPLICIT ADOPTION AND REPO-LOCAL RUNTIME LIFECYCLE IS COMPLETE.**

The next permitted implementation stage is:

```text
RM5 — backend protocol + Graphiti/FalkorDB conformance
```

RM5 must remain behind optional/lazy backend imports and must not turn the derived backend into scientific authority.
