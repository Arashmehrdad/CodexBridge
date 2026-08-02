# V3-1B-SCHEMA-MODELS-1 — Company Kernel Schema and Models Result

**Date:** 2026-08-02
**Status:** accepted and closed in source
**Gate:** [`V3_1B_SCHEMA_MODELS_1_GATE_2026-08-02.md`](V3_1B_SCHEMA_MODELS_1_GATE_2026-08-02.md)
**Architecture:** [`V3_1B_KERNEL_OF_ONE_ARCHITECTURE_PROPOSAL_2026-08-02.md`](V3_1B_KERNEL_OF_ONE_ARCHITECTURE_PROPOSAL_2026-08-02.md)
**Runtime activation:** not performed and not authorised
**Push:** not performed and not authorised

## 1. Accepted outcome

The bounded schema/models package is accepted. Soma now has an inactive additive `company_kernel` component containing only the irreducible Company Kernel v1 structure:

- Company;
- Mission;
- immutable accepted PlanRevision;
- immutable bounded WorkPackage;
- immutable WorkPackageAttempt linkage;
- immutable AcceptanceCommit;
- immutable bounded reconciliation receipts;
- deterministic canonical JSON, domain-separated hashes and opaque identifiers;
- route-independent outcome identity separated from route-specific attempt identity;
- explicit ordered component migration and honest schema-state inspection.

The package exposes no Company, Mission, plan, package, attempt, acceptance or reconciliation action. It creates no Task or Run, registers no gateway, starts no provider, changes no live runtime configuration and advertises `active_capability: false` even after the schema is present.

## 2. Source added

- `soma/company_kernel/models.py`
  - strict frozen Pydantic records;
  - unknown-field rejection;
  - canonical sorted compact JSON;
  - lowercase SHA-256 validation;
  - domain-separated deterministic identity helpers;
  - route-specific contract-key exclusion from WorkPackage/outcome material.
- `soma/company_kernel/schema.py`
  - Company Kernel component version `1` in `soma_schema_migrations`;
  - seven additive tables;
  - composite same-company, same-mission, same-outcome and fixed-executive foreign keys;
  - one-successor and one-winner uniqueness;
  - immutable-fact triggers;
  - Mission mutation restricted to current-plan/version/timestamp fields;
  - exact schema-object completeness reporting.
- `soma/company_kernel/store.py`
  - inert constructor;
  - read-only state inspection;
  - explicit migration entry point only;
  - no domain write API;
  - exact installation result requires version `1` plus every required table, trigger and index.
- `soma/company_kernel/__init__.py`
  - exports only the inactive schema, records and identity helpers.
- `tests/test_company_kernel_schema_models.py`
  - fresh, idempotency, rollback, corruption, compatibility, authority, relationship, immutability, route-identity and API-boundary proof.

No incumbent source file was changed by the implementation package.

## 3. Authority proof

The implementation preserves the accepted authority split:

- ProjectScope remains the repository/project/resource/generation authority;
- canonical Task remains admission and task-state authority;
- canonical Run/process/lock/cancellation remains execution authority;
- WorkerSubstrateStore remains provider-session and interaction authority;
- ResultPublication remains public result identity authority;
- Company Kernel owns only company intent, accepted plan/package facts, route linkage and substantive outcome acceptance facts.

Mechanical inspection found no WorkPackage or WorkPackageAttempt status, state, PID, process, lease, lock, worker, cancellation, recovery, result or publication column. `CompanyKernelStore` has exactly five public methods: `connect`, `init_db`, `is_installed`, `schema_state` and `table_counts`. Search found no import or registration outside `soma/company_kernel`; the server and public gateway inventories remain unchanged.

The root executive is still a later trusted bootstrap input, not a caller-created grant. Database constraints require Mission owner and acceptance authority to match the immutable Company executive, then carry that authority through PlanRevision, WorkPackage and AcceptanceCommit. The package does not implement bootstrap or any authority-changing operation.

## 4. Fresh and copied-live migration proof

### Fresh/negative proof

Final focused run `20260802T220701Z_executable_profile_2b871343` passed Ruff and all 12 focused tests. It proved:

- construction and import are inert;
- absent schema is reported as version `0`, incomplete and inactive;
- a marker-only/corrupt version-1 state is not reported installed;
- fresh migration applies `[1]`, replay applies `[]`;
- a failing migration rolls back every kernel object and marker;
- exact tables, triggers and partial index exist;
- foreign-key and integrity checks pass;
- cross-authority, cross-outcome and attempt/task mismatches fail;
- valid single-executive relationships succeed;
- immutable facts reject update/delete while Mission CAS fields remain available;
- one-winner AcceptanceCommit and one-successor attempt constraints hold;
- route details cannot enter route-independent outcome identity;
- models are strict, frozen, canonical and hash checked;
- no company-domain action API exists.

### Final copied-live proof

Run `20260802T220728Z_executable_profile_18346bc2` used SQLite backup from the live database into a temporary repo-owned copy. It never migrated the live database. Results:

- no Company Kernel object existed before migration;
- first apply: `[1]`;
- second apply: `[]`;
- `PRAGMA integrity_check`: `ok`;
- `PRAGMA foreign_key_check`: zero rows;
- 29 incumbent tables content-hashed before and after: zero changes;
- 54 incumbent table/index/trigger/view definitions compared before and after: zero changes;
- all seven new Company Kernel tables contained zero rows;
- exact migration row: `company_kernel / 1 / company_kernel_foundation`;
- 12 workflow rows and 21 supervisor rows remained unchanged;
- final schema state reported complete version `1`, `up_to_date: true`, `active_capability: false`.

No workflow, supervisor, Task, Run, interaction, publication or domain row was converted or backfilled.

## 5. Regression evidence

- `20260802T215226Z_executable_profile_1941fd6a` — 121/121 adjacent ProjectScope, canonical Task, durable Run and worker-substrate tests passed.
- `20260802T220745Z_executable_profile_82f141d2` — final repository gate passed with **2,685 passed, 35 skipped and 1 expected xfail** in 587.22 seconds. Exit code `0`; published result hash `1af8cd668acb3a166b14ed6ff07c72826eb72e5e97354a3447bc7aedf27f3f77`.
- `20260802T221917Z_executable_profile_60abc019` — changed-line whitespace check passed; only the expected new package and test were untracked before documentation closure.
- `20260802T221932Z_executable_profile_f4305c6a` — final five-file whitespace/API boundary scan passed.

The earlier full run `20260802T215359Z_executable_profile_e4afde7f` also passed 2,684 tests before the marker-only corruption test was added, but it is superseded by the final full run above.

## 6. Incidents and corrections

All material diagnostics are retained in the reliability ledger. In summary:

- the first import used LibreOffice's PATH Python and lacked project dependencies;
- one combined venv retry and one combined final boundary scan were blocked before execution by the platform safety classifier;
- the first pytest basetemp path lacked its parent directory;
- one negative Task fixture omitted required `backend_ref`;
- Ruff found two unnecessary test f-strings;
- one edit preview used a stale expected hash and was rejected before mutation;
- an expanded `terminal` query used unsupported fields and was replaced by the documented `output` operation;
- final review found a genuine pre-commit schema-state honesty defect: a migration marker without objects could report up to date;
- the first hardening pass omitted two schema-object imports, caught immediately by Ruff.

Every implementation defect was corrected before acceptance. Failed diagnostics were not used as evidence.

## 7. Acceptance decision

`V3-1B-SCHEMA-MODELS-1` satisfies its gate and is closed.

This acceptance authorises no subsequent behavior by implication. Company/Mission bootstrap, current-plan selection, WorkPackage creation, route reservation, Task/Run coordination, AcceptanceCommit creation, projections, `reconcile_one`, public gateways, providers, departments, scheduling, external mutation and runtime activation remain inactive until a separate bounded gate is written and activated after canonical-memory refresh.
