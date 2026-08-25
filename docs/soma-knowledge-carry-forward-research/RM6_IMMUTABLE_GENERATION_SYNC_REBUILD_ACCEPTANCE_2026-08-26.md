# RM6 — Immutable Generation Sync/Rebuild Acceptance

**Date:** 2026-08-26
**Programme:** Soma Hybrid Research Map
**Stage:** RM6
**Status:** ACCEPTED
**Implementation authority:** `docs/SOMA_HYBRID_RESEARCH_MAP_IMPLEMENTATION_PLAN_2026-08-24.md`
**Accepted RM5 base HEAD:** `340af1f18f6700105217babfa6647c4f2cb24e1d`
**RM6 implementation commit:** `b2158b727e518643ae25abf72bb1d263d5424839`
**Branch:** `rollback/pre-core-hardening-20260823`
**Push:** none

## 1. Accepted boundary

RM6 adds the immutable repo-local research-map generation protocol and explicit `sync` / `rebuild` actions on the existing `research_map_action` gateway.

RM6 does not activate semantic search, does not generate semantic sidecars, does not mutate the `arash-research` Skill, does not redesign continuation, and does not make Graphiti/FalkorDB/Docker a Soma startup dependency.

The public tool count remains **40**.

## 2. Local generation protocol

RM6 materializes derived runtime under:

```text
.soma/research-map/
├── CURRENT.json
├── .sync.lock
└── generations/<generation>/
    ├── DESIRED.json
    ├── RELATIONS.json
    └── HEALTH.json
```

Accepted properties:

- every build targets a fresh immutable generation directory;
- `DESIRED.json`, `RELATIONS.json`, and `HEALTH.json` are written before publication;
- file contents are flushed and fsynced;
- `CURRENT.json` is replaced atomically;
- CURRENT contains and verifies hashes for all published artifacts;
- generation/database/hash fields are validated before they can address local runtime paths;
- malformed or corrupt CURRENT/artifacts are not silently trusted;
- orphan staging generations are never authoritative merely because they exist.

## 3. Crash-safe single-writer boundary

The initial create/delete lock-file design was hardened before acceptance because a hard-killed process could leave a stale pathname and wedge later syncs.

The accepted `SyncWriterLock` uses an OS advisory lock:

- Windows: `msvcrt.locking` non-blocking byte lock;
- POSIX: `fcntl.flock` non-blocking exclusive lock.

The `.sync.lock` file may persist, but ownership is the kernel lock, not file existence. A hard-killed process therefore releases ownership automatically.

A real subprocess test exits through `os._exit(23)` without Python cleanup and proves the next writer can acquire the lock.

## 4. Sync/rebuild transaction

The accepted transaction is:

```text
validate reviewed semantic desired state
→ require complete coverage
→ acquire one writer lock
→ create fresh staging generation
→ build exact backend projection
→ exact relation-manifest read-back
→ explicit backend persistence
→ close/reopen exact reconciliation
→ write verified HEALTH
→ atomically publish CURRENT
→ release writer lock
```

`rebuild` always stages a fresh generation.

`sync` may return `already_current` only when:

1. CURRENT semantic desired-state hash matches;
2. projection-contract hash matches;
3. relation count matches; and
4. the live backend relation manifest is reopened and matches exactly.

CURRENT metadata alone is never treated as proof of live backend health.

## 5. Drift versus backend outage

RM6 distinguishes two cases that must not be conflated:

**Verified backend manifest mismatch**

```text
CURRENT metadata matches desired state
but backend relation set differs
→ treat current backend as drifted
→ stage and publish a fresh verified generation
```

**Backend verification exception/outage**

```text
CURRENT metadata matches desired state
but backend cannot be checked
→ fail bounded as backend_runtime_failure
→ do not stage a replacement generation
→ leave existing CURRENT untouched
```

This prevents temporary backend unavailability from being misclassified as semantic/index drift.

## 6. Crash-injection acceptance

RM6 covers all canonical crash boundaries:

```text
1. before staging creation
2. after staging creation
3. mid relation writes
4. after read-back reconciliation
5. before explicit SAVE
6. after explicit SAVE
7. before CURRENT publication
8. after CURRENT publication
```

Accepted invariant:

```text
Before CURRENT publication:
    old CURRENT remains authoritative.

After CURRENT publication:
    new CURRENT points only to a generation that already passed
    explicit persistence + close/reopen exact reconciliation.
```

The after-publication injected failure intentionally leaves the newly verified generation current because publication is the transaction boundary.

## 7. Stale semantic statement with stable relation identity

RM6 explicitly tests statement drift where the deterministic `relation_id` remains unchanged.

Sequence:

```text
publish statement one
→ change reviewed sidecar statement only
→ semantic_desired_state_sha256 changes
→ read-only health reports sync_state=stale
→ explicit sync publishes a new generation
→ exact relation query returns statement two
→ sync_state=published_verified
```

Thus relation identity stability cannot hide substantive semantic statement drift.

## 8. Read-only publication health

`research_map_query(health)` now reports immutable publication state without backend/model/server initialization.

Relevant states include:

```text
missing
stale
degraded
published_verified
```

For published generations, `backend_state=not_checked` unless an explicit sync action actually reconciles the live backend.

`published_verified` means the generation passed persistence and reopen verification at publication time; it is not a claim that the backend was checked during the current read-only query.

## 9. Public action contract

The existing `research_map_action` tool now exposes:

```text
adopt
sync
rebuild
```

No new MCP tool was added.

The action gateway remains exact-ProjectScope-bound. `sync` and `rebuild` do not accept research roots and never generate semantic sidecars.

Because `rebuild` intentionally creates a fresh generation, the gateway metadata is correctly non-idempotent.

Live post-restart discovery confirms:

```text
tool_count = 40
research_map_action enum = adopt | sync | rebuild
```

## 10. Public capability identity

Final source identity and live served identity match exactly:

```text
public_schema_hash
  ebb3e321a991058d1f4f96e566b462e585c42bbf8e098cca76a486f592ae6828

input_schema_digest
  5513e3bd3bce5edd38f47295ec7027f1cfdadc0c79d1d2c29126e5c4deaaf6c9

output_schema_digest
  34ee85b1e7fe62572c6974e0607f53ab072e6e9dd9cfa7dc22b6e2244576c21a

operation_inventory_hash
  b5308c14459684fbd5601846e81a40a3731a9d7aad4eb1c26897604749066aad

public_descriptor_hash
  4a90f7523a625aef6e21daf16b0355068d9800cefab047f4d14468e5fe006d86
```

The output-schema digest is unchanged from RM5; the input, operation-inventory, and descriptor identities changed intentionally because the existing action gateway gained `sync` / `rebuild` semantics and metadata.

Final source identity run:

```text
20260825T215131Z_executable_profile_e984ad08
```

Server-only activation restart:

```text
20260825T215604Z_executable_profile_e1cf0038
```

Post-restart server build:

```text
e3aa3f1e432a6c5d4358e1b54ac2938e471322c1d730c7a97d990d356991f337
```

## 11. Deterministic fake-backend acceptance

The RM6 fake backend deliberately separates live and persisted relation state so `close()` cannot accidentally count as persistence.

Final RM6-only test bytes:

```text
20 passed
0 failed
5.48s
```

Durable run:

```text
20260825T214810Z_executable_profile_eb870cbd
```

This set includes:

- exact first publication;
- unchanged live verification with no republish;
- backend drift repair;
- all eight crash points;
- corruption recovery;
- crash-safe writer lock;
- hard-process-kill lock recovery;
- publication/staleness health;
- runtime metadata/path hardening;
- bounded backend runtime failure;
- backend outage without accidental rebuild;
- public sync/rebuild schema and server dispatch;
- corrected-relation read-back after stale statement resync.

## 12. Real Graphiti/FalkorDB RM6 orchestrator proof

RM6 also ran the production transaction engine against the production `GraphitiFalkorBackend` using a disposable pinned FalkorDB server.

Durable run:

```text
20260825T215303Z_executable_profile_6a8dd99f
```

Observed sequence:

```text
initial sync        = synchronized
unchanged sync      = already_current
explicit rebuild    = rebuilt
statement mutation  = health stale
corrected sync      = synchronized
corrected readback  = real statement two
generation_count    = 3
reopen_verified     = true
```

This proves RM6 orchestration works against the real RM5 adapter rather than only against the deterministic fake backend.

The test repository was temporary and removed after the run.

## 13. Docker/resource boundary

Docker remains **conformance-only** and is not a normal Research Map or Soma runtime requirement.

For the real RM6 proof:

- Docker Desktop was started only for the disposable test;
- one pinned FalkorDB container was created on a non-default host port;
- the container was removed after conformance;
- Docker Desktop was explicitly shut down;
- a final Docker health check confirmed the engine was no longer running.

Relevant durable runs:

```text
20260825T215153Z_executable_profile_e08a4575   Docker temporary start
20260825T215232Z_executable_profile_e3ac93ec   FalkorDB disposable start
20260825T215358Z_executable_profile_71187a1d   container removal + Docker shutdown
```

## 14. Focused regression evidence

Final expanded focused slice on final test bytes:

```text
288 passed
1 upstream Graphiti deprecation warning
0 failed
42.53s
```

Durable run:

```text
20260825T214810Z_executable_profile_eb870cbd
```

The warning is Graphiti 0.29.3's existing Pydantic-v2 deprecation behavior and is not a Soma failure.

## 15. Broad regression evidence

RM6 reused exactly the same nine inherited RM3/RM5 exclusions and added no new exclusions.

The first broad RM6 diagnostic exposed two intentional public-contract test snapshots that still described the RM4 adoption-only surface:

```text
test_tested_inventory_covers_every_public_gateway
test_research_map_action_metadata_is_explicit_and_nonsemantic
```

Those tests were corrected to the intentional RM6 discriminated-union/non-idempotent contract. No production semantics were weakened to satisfy them.

Targeted correction validation:

```text
35 passed
0 failed
```

Durable run:

```text
20260825T214248Z_executable_profile_d8a40b66
```

The unchanged baseline-equivalent 12-worker broad rerun then passed:

```text
3621 passed
37 skipped
1 xfailed
13 warnings
0 failed
250.74s / 4:10
```

Durable run:

```text
20260825T214305Z_executable_profile_8c68a694
```

The nine inherited exclusions remain exactly those already documented by RM3/RM5; RM6 introduces no additional exclusion.

## 16. Static/dependency hygiene

Proportionate final hygiene passed on RM6-new and previously-clean touched files:

```text
Ruff: PASS
git diff --check: PASS
pip check: PASS
```

Durable run:

```text
20260825T215046Z_executable_profile_ff875abd
```

A deliberately over-broad whole-file Ruff attempt was not used as an acceptance gate because it surfaced pre-existing style debt throughout legacy giant gateway files unrelated to RM6. RM6 did not perform unrelated broad style refactors.

## 17. Preserved programme boundaries

RM6 preserves:

- research Markdown as authoritative scientific truth;
- Sol/ChatGPT as semantic adjudication authority;
- reviewed sidecars as tracked semantic judgments;
- continuation unchanged as current-position/re-entry state;
- no automatic semantic sidecar generation;
- no automatic semantic planner/router;
- no second reasoning head;
- no provider credential requirement;
- no normal Docker requirement;
- no automatic backend startup;
- `arash-research` remains R8-I1 during the roadmap;
- the Skill finishing touch remains post-RM11 only;
- no packaging/editable-install baseline fix during the roadmap;
- no push.

## 18. Verdict

**RM6 ACCEPTED.**

The immutable generation, explicit sync/rebuild, persistence/reopen, crash-safety, stale-state, public-contract, real-backend, and live-activation boundaries are complete.

The next implementation boundary is:

```text
RM7 — semantic search + crash/read-only acceptance
```

RM7 must consume only an accepted published generation and must preserve the rule that query paths are read-only: no repair, rebuild, sync, backend startup policy mutation, or sidecar generation may be hidden inside a query.
