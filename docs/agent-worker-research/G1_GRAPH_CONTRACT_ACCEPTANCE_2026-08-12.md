# G1 Graph Contract Acceptance

Date: 2026-08-12
Status: ACCEPTED
Repository: `D:\Github\Soma`
Branch: `lane/memory-integration-foundation-1`
Pre-G1 accepted HEAD: `679d549136c733eeb6344f18a619d3ea70381d2e`
G1 implementation HEAD: `b7a78bce76aed840cdd5ad6532e106d49a33f964`

## 1. Acceptance decision

Implementation Gate 1 is accepted.

Soma now has an inactive internal Company Kernel v2 graph contract consisting of:

- pure bounded `PlanGraphManifestV1` and dependency-proof models;
- additive immutable graph storage;
- one internal atomic graph-capable PlanRevision acceptance transaction;
- deterministic request/content replay and conflict handling;
- normalized graph reconstruction and exact manifest hash/JSON verification;
- crash/CAS rollback proof on disposable stores.

No public Company Kernel action, Task/backend/provider launch, reasoning backend, scheduler, service restart, connector refresh, wiki refresh, or live Company Kernel activation is part of G1.

## 2. G1 checkpoint commits

### G1.1 - pure graph and dependency contracts

Commit:

`fbc7b60fc78f0b1768d1053494e9f6caa073028b`

Title:

`Soma: add pure company graph contracts`

Added:

- `soma/company_kernel/graph_models.py`
- `tests/test_company_kernel_graph_contracts.py`

Frozen contract includes:

- graph schema `plan_graph_manifest.v1`;
- dependency proof schema `dependency_satisfaction_proof.v1`;
- maximum 32 packages / 128 edges;
- same-plan, acyclic, conjunctive graph v1;
- dependency requirements `accepted_outcome`, `published_success`, `evidence_available`, `settled`;
- canonical order-independent graph identity;
- strict tagged dependency satisfaction proofs;
- proof identity that excludes observation timestamp and unrelated kernel-version churn;
- mandatory `attempt_set_hash` for `settled`.

### G1.2 - additive Company Kernel schema v2

Commit:

`b6c0d99ed267072c4853aa5b1b25c798632777ae`

Title:

`Soma: add Company Kernel graph schema v2`

Migration 1 remains unchanged. Migration 2 adds:

- `idx_work_package_plan_membership`;
- immutable `plan_graph_manifests`;
- immutable `work_package_dependencies`;
- exact dependency vocabulary/selector/self-edge/same-plan constraints;
- immutable-table update/delete triggers.

Company Kernel schema version is exactly `2`. `active_capability` remains false.

### Pre-activation reconstruction correction

Commit:

`888b105729bcf47f4d2c7af6b6f3b8bc08a73540`

Title:

`Soma: preserve graph evidence requirement identity`

Classification:

`implementation-friction`

Observed issue:

`PlanGraphManifestV1` includes optional `evidence_requirements_hash`, but the original Company Kernel WorkPackage row stored only opaque `evidence_requirements_ref`. The ref was not defined as content-addressed. Without the hash, normalized WorkPackage/dependency rows could not independently reconstruct the complete graph-manifest identity required by G1.3.

Correction before any live activation:

- migration 2 also adds `work_packages.evidence_requirements_hash`;
- value is immutable with the WorkPackage row;
- legacy v1 rows receive only the empty default, with no semantic backfill;
- model requires evidence requirements ref/hash to appear together;
- schema remains version 2;
- migration 1 remains untouched.

Conclusion:

This was a concrete research-to-implementation storage gap, not an invalidation of the agent/worker architecture.

### G1.3 - atomic graph acceptance service

Commit:

`b7a78bce76aed840cdd5ad6532e106d49a33f964`

Title:

`Soma: add atomic Company Kernel graph acceptance`

Added internal-only:

- `soma/company_kernel/service.py`
- `tests/test_company_kernel_graph_service.py`

The service uses one `BEGIN IMMEDIATE` transaction to:

1. verify Company Kernel v2 and inactive internal gate;
2. resolve exact Company/Mission/acceptance authority;
3. verify active ProjectScope identity/generation/resource binding;
4. resolve exact request replay or conflict;
5. validate the complete bounded manifest and exact WorkPackage material;
6. bind graph schema/hash into the accepted PlanRevision contract;
7. derive immutable Mission-scoped PlanRevision identity;
8. insert PlanRevision;
9. derive and insert immutable WorkPackages/outcomes;
10. insert immutable same-plan dependency rows;
11. store exact canonical graph manifest;
12. reconstruct the manifest from normalized WorkPackage/dependency rows;
13. require exact reconstruction hash and JSON equality;
14. CAS Mission current-plan, plan version, and kernel version;
15. commit.

The service contains no Task start, Run start, provider call, scheduler, gateway registration, or public activation path.

Replay rules proven by tests:

- exact controller request replay returns the committed immutable graph;
- same request ID with different normalized request content fails closed;
- reordered identical graph under a new request ID converges by exact content;
- content-identical replay with changed immutable request metadata fails closed;
- historical state remains immutable after later ProjectScope generation change.

## 3. Crash and recovery proof

The disposable graph-service suite proves rollback for:

- rejection before graph mutation;
- failure after PlanRevision insert;
- failure after partial WorkPackage insertion;
- failure after partial dependency insertion;
- normalized reconstruction/hash mismatch;
- current-plan CAS race;
- failure after successful Mission CAS but before outer transaction commit.

After each injected failure, candidate PlanRevision/package/edge/manifest rows are absent and Mission current-plan/version state is restored.

Exact response-loss replay is represented by successful commit followed by identical controller request replay.

## 4. Gate validation

Gate run group:

`20260812T041923Z_powershell_group_4ffd4233`

Results:

```text
Company Kernel schema/model + graph contract + graph service:
55 passed in 6.52s

Canonical Task plane regression:
41 passed in 10.37s

ProjectScope foundation regression:
21 passed in 6.53s

ProjectScope quarantine/adjudication regression:
22 passed in 7.99s
```

Total focused/affected gate result:

`139 passed`

No full repository suite was run because the affected contract and shared-database regression suites were sufficient for this gate.

## 5. SQLite integrity evidence

Graph happy-path and migration tests explicitly require:

```text
PRAGMA integrity_check -> ok
PRAGMA foreign_key_check -> []
```

The v1 -> v2 migration test proves:

- incumbent Company/Mission/PlanRevision/WorkPackage row counts are preserved;
- no graph manifest/dependency rows are backfilled;
- legacy WorkPackage `evidence_requirements_hash` receives only empty default;
- migration 2 rollback leaves no partial graph tables/indexes/triggers/version marker after injected failure.

## 6. Source boundary

Committed range `679d549..b7a78bc` changes exactly nine files:

```text
soma/company_kernel/__init__.py
soma/company_kernel/graph_models.py
soma/company_kernel/models.py
soma/company_kernel/schema.py
soma/company_kernel/service.py
soma/company_kernel/store.py
tests/test_company_kernel_graph_contracts.py
tests/test_company_kernel_graph_service.py
tests/test_company_kernel_schema_models.py
```

Range size:

`2750 insertions, 7 deletions`

No files under the following were changed by G1:

- `soma/tasks/`;
- `soma/project_scope/`;
- `soma/server.py`;
- `soma/gateway_models.py`;
- public gateway inventory/metadata;
- Hermes integration;
- workflow/supervisor runtime.

The public tool surface therefore remains outside the G1 mutation boundary.

## 7. Ruff and newline evidence

Gate quality run:

`20260812T042012Z_powershell_group_a059322d`

Results:

```text
Ruff check across all nine G1 source/test files:
All checks passed!

Ruff format --check on the four new G1 Python files:
4 files already formatted
```

EOL diagnostics:

```text
soma/company_kernel/__init__.py: LF only
soma/company_kernel/graph_models.py: LF only
soma/company_kernel/models.py: LF only
soma/company_kernel/schema.py: LF only
soma/company_kernel/service.py: LF only
soma/company_kernel/store.py: LF only
tests/test_company_kernel_graph_contracts.py: LF only
tests/test_company_kernel_graph_service.py: LF only
tests/test_company_kernel_schema_models.py: LF only
```

No mixed newline file was introduced.

## 8. Negative-boundary verification

G1 did not:

- expose a public Company Kernel action;
- change the 32 public tool names or schemas;
- change canonical Task kinds/backends;
- launch a Task from the Company Kernel graph path;
- launch a Run from the Company Kernel graph path;
- implement a reasoning backend;
- call OpenAI/Codex/Claude or any other reasoning provider;
- create a scheduler or second work-unit lifecycle;
- initialize a Hermes reasoning runtime;
- restart Soma;
- refresh the ChatGPT connector;
- refresh the repository wiki;
- mutate canonical project memory;
- push the branch.

The durable `run_start` calls used during implementation were validation infrastructure only; the graph acceptance service itself remains launch-free.

## 9. Implementation observations

### Observation A

Classification:

`implementation-friction`

Finding:

The original v1 `evidence_requirements_ref` was insufficient for exact normalized graph reconstruction because the frozen manifest identity includes `evidence_requirements_hash`.

Resolution:

Corrected pre-activation in migration 2 and covered by migration/service tests.

Material impact after correction:

None. Architecture remains valid.

### Observation B

Classification:

`implementation-friction`

Finding:

Two temporary syntax errors during implementation were caused by malformed assistant `repo_preview` replacement payload strings. Inspection of the preview/file evidence showed Soma applied exactly the malformed requested text.

Resolution:

Large new files were switched to whole-file `create_file` previews; existing-file edits were kept small/context-bounded.

Material impact:

None. Both errors were caught by focused tests before commit and are not Candidate-B/Soma routing defects.

### Candidate-B organic UX monitoring

No new wrong-tool routing, misleading tool description, unnecessary confirmation, tool-card ambiguity, or public-surface regression was observed during G1.

`repo_query`, `repo_preview`, `repo_apply`, `repo_commit`, `run_start`, `run_query`, and concurrent `powershell_group` validation all routed to their intended Soma capabilities.

The previously recorded generic connector-inventory discoverability/cache oddity remains the only Candidate-B observation.

## 10. Gate decision

```text
G1: ACCEPTED
Company Kernel schema: v2
Company Kernel active capability: false
public Company Kernel action: none
canonical Task modification: none
reasoning backend: none
provider use: none
scheduler: none
service restart: none
connector refresh: none
push: none
```

The next implementation gate is G2, beginning with pure bounded `EvidenceSubmissionV1` and `ReasoningSpecV1` contracts. G2 remains deterministic/provider-neutral; no real provider is authorized by this acceptance.
