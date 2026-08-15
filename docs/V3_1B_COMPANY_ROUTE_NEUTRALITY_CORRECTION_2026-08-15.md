# V3-1B Company Route Neutrality Correction - 2026-08-15

Status: CORRECTED

Lane: Autonomous Company architecture correction only
Branch: `lane/memory-integration-foundation-1`
Primary correction commit: `a9fe3ae32f5b26a8b8a7e0764431df2f8f62cda2`
Vocabulary cleanup commit: `b03065cfa51c2d43cf6d9d67c178e1038b2b8e2e`

## 1. Owner boundary

This record corrects an unauthorized architecture drift. It does **not** activate, unfreeze, continue, or otherwise authorize the Autonomous Company roadmap.

The Company roadmap remains frozen. V3-3 and every later Company lane remain inactive unless the owner explicitly reopens them.

No Codex/provider subagent, push, deploy, connector refresh, or Company-roadmap progression was authorized or performed by this correction.

## 2. Drift corrected

The leaked implementation had made a generic Company concept - executing a `WorkPackage` through a `WorkPackageAttempt` - synonymous with a reasoning-provider route:

```text
WorkPackage
  -> ReasoningSpec
  -> TaskKind.REASONING
  -> BackendKind.SOMA_REASONING
  -> reasoning provider
```

That coupling appeared in generic admission, coordinator preparation, public attempt admission, and reasoning-provider enablement checks. It violated the earlier Company architecture in which provider/executor choice belongs to the route selected for a canonical Task, not to the WorkPackage abstraction itself.

The restored Company relationship is:

```text
Sol / Work selects an appropriate action/route
  -> Company WorkPackageAttempt
  -> provider-neutral canonical Task request
       -> durable command, or
       -> optional reasoning specialist route
```

Company therefore owns the durable Mission / PlanRevision / WorkPackage / WorkPackageAttempt identities. `TaskManager` owns backend launch after the shared Attempt + Task reservation commits. Reasoning is an optional specialist route, never a generic Company prerequisite.

## 3. Corrected route contract

`AdmissionRequestV1` now carries a discriminated `CompanyTaskRequestV1` rather than a mandatory generic `ReasoningSpecV1`.

The currently supported canonical Task route variants reuse the existing Task plane:

- `DurableCommandTaskRequestV1` -> `durable_command` / `soma_durable_run`;
- `ReasoningTaskRequestV1` -> `reasoning` / `soma_reasoning`, only when explicitly selected.

No third Company-specific executor was invented.

A WorkPackageAttempt freezes the selected canonical Task route and its request identity. Company does not choose a provider after reservation and does not reinterpret one route as another.

## 4. Generic admission and TaskManager ownership

The generic admission entry point is now `admit_work_package(...)` with `admit_work_package_batch(...)` for bounded batch admission.

The former production symbols `admit_reasoning_work_package`, `admit_reasoning_batch`, and `PreparedReasoningAdmissionV1` were removed from `soma/`.

`TaskManager.start_reserved_task(...)` launches an already-reserved canonical Task after the Company reservation transaction commits. It verifies the persisted Task kind, backend kind, request hash, ProjectScope binding, and route-specific launch material before dispatch.

This keeps backend lifecycle ownership in the canonical Task plane rather than Company.

## 5. Coordinator boundary

The Company coordinator now accepts `PreparedTaskAdmissionV1` carrying an exact `task_request`.

It remains a bounded mechanical readiness/admission boundary. It does not select providers, invent a next business action, create a hidden semantic plan, or decide what Sol/Work should do next.

Semantic judgment remains outside the Company coordinator and belongs to Sol / ChatGPT Work at the appropriate executive boundary.

## 6. Route schema preservation

The leaked reasoning-coupled attempt descriptor had already used:

`work_package_attempt_route.v1`

That schema is not reinterpreted as the corrected architecture.

The correction establishes:

- `work_package_attempt_route.v1` = legacy reasoning-coupled historical evidence, frozen and non-replayable;
- `work_package_attempt_route.v2` = corrected provider-neutral executable Company attempt route.

A live read-only database check found zero persisted Company WorkPackageAttempts in `runs/soma.sqlite3`, so no user data migration or durable record rewrite was required.

## 7. Public Company route remains frozen

The existing public `reserve_attempt` wire schema still contains the historical `reasoning_spec` field solely to preserve the already-accepted public schema while Company is frozen.

That field is explicitly marked in source as a frozen legacy wire field. It does not define the corrected Company architecture and is not executable through public Company admission.

`company_action(reserve_attempt)` remains disabled and now refuses independently of `config.reasoning.enabled`, stating that the corrected provider-neutral canonical Task admission route requires explicit owner activation.

Company capability projection reports the corrected distinction:

- attempt admission disabled;
- canonical Task route model provider-neutral;
- reasoning attempt route disabled;
- reasoning-provider configuration informational only.

Any future public `reserve_attempt` schema redesign requires a separate owner-authorized public-schema review/activation; this correction deliberately does not perform it.

## 8. Agent/Worker compatibility

Agent/Worker benchmark/runtime code was adapted to request `ReasoningTaskRequestV1` explicitly when it needs a reasoning specialist.

This preserves Agent/Worker reasoning capability without allowing that capability to define generic Company execution.

## 9. Key behavioral proofs

Focused route-neutrality acceptance run:

`20260815T055948Z_executable_profile_cf0af6ff`

Result:

- 46 passed;
- Ruff clean;
- corrected Company modules format-clean;
- `git diff --check` clean.

The focused suite proves, among other things:

- a Company WorkPackage can admit and launch a `durable_command` canonical Task while `TaskManager._reasoning_backend is None`;
- the durable route is recorded under `work_package_attempt_route.v2` and contains no generic `reasoning_spec` route dependency;
- selecting an explicit reasoning route while no reasoning backend is configured fails before an Attempt or Task is reserved;
- reasoning enablement does not control generic Company public admission;
- public `reserve_attempt` remains frozen whether reasoning is enabled or disabled;
- the legacy v1 reasoning-coupled route is non-replayable;
- Agent/Worker can still explicitly select a reasoning route.

Dependency-surface audit run:

`20260815T061837Z_executable_profile_22a77dce`

Coverage included canonical Task plane, reasoning backend/store/contract/integration, Company admission/concurrency/public gateway, Agent/Worker benchmark/adjudication, and public gateway/schema inventories.

Result:

- 131 passed;
- Ruff clean;
- `git diff --check` clean.

Post-vocabulary cleanup run:

`20260815T062210Z_executable_profile_4494e11e`

Result:

- 16 passed;
- Ruff clean;
- `git diff --check` clean.

## 10. Whole-suite audit and unrelated failures

A whole-suite regression was attempted with the correct TradingLab import root. The Soma executable profile reached its 10-minute ceiling before completion.

The failure markers encountered before timeout were isolated to three tests outside this Company correction:

1. `test_cf1_run_query_baseline_captures_current_index_behavior` - SQLite selects `idx_runs_created_run_id_desc` while the baseline test expects `idx_runs_created_at`;
2. `test_pytest_launcher_creates_missing_nested_parent_and_preserves_siblings` - nested Windows pytest collection reaches `C:\Documents and Settings` and receives WinError 5;
3. the G2 patch-repair f-string hazard test - the Python tokenizer reports `token_spans_deletion_cut` instead of `next_token_not_logical_newline`; both outcomes reject the unsafe cut.

Those three tests also fail when run directly and do not touch the Company route-neutrality files. They are recorded here as unrelated existing audit blockers and were not modified under this correction.

## 11. Public compatibility

Live capability identity remained:

- public actions: 34;
- operation-inventory gateways: 34;
- accepted public schema hash: `00afcf876e27fbc549c1510dd2e946e56c5531f55e13db6595c24a3feacf82a9`;
- runtime/live input schema hash: same accepted hash.

No public tool was added. No public request schema was changed. No connector refresh is required by this correction.

## 12. Concurrent-work boundary

Concurrent Sol agentic-loop research and `docs/CANONICAL_PROJECT_MEMORY_CONTRACT.md` remained outside this correction and were not absorbed into either correction commit.

At acceptance-record time the worktree contained 18 such pre-existing untracked research/memory files: the canonical-memory draft, Sol research iterations 01 through 16, and the Sol-loop re-audit. They are intentionally preserved as concurrent work.

Historical `.soma/wiki/generations/` records that mention the old reasoning-specific symbols remain immutable historical snapshots. Refreshing the current wiki generation must not rewrite those historical generations.

## 13. Verdict

The unauthorized reasoning-provider leakage into generic Company WorkPackage execution is CORRECTED.

The durable Company abstraction is again:

`WorkPackage -> WorkPackageAttempt -> canonical Task`

with route choice supplied explicitly by Sol/Work and backend lifecycle owned by the canonical Task plane.

Reasoning remains available only as an explicitly selected optional specialist route.

The Company roadmap remains frozen. This correction grants no authority to start V3-3 or any later Company implementation lane.
