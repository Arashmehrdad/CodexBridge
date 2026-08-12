# G3 DAG Admission and FanIn Acceptance - 2026-08-12

STATUS: ACCEPTED

## Authority and range

- Canonical implementation plan: `docs/agent-worker-research/AGENT_WORKER_IMPLEMENTATION_PLAN_2026-08-12.md`
- Canonical plan SHA-256: `fa2afb72e51e5cc4494f29b7470eb33cd8a951144a2bc78db5e65a6d8301bea2`
- G2 accepted baseline: `87785542204eb05069df892fcb17217c073d998c`
- G3 implementation head before this acceptance record: `79342f4c1a6e199937d69ea19b07897c542f20f1`
- Branch: `lane/memory-integration-foundation-1`

G3 implementation checkpoints:

1. `e3ac1f89d3af84e87e2accd47b8c9afc6cc025a9` - immutable dependency proof schema;
2. `4fd5c327b57350c02a958a2d0f52cb73d8cffb43` - initial bounded proof/admission integration;
3. `95986e8ababdb6e03c5cb036470f341727137015` - canonical G3 repair, deterministic DAG admission/coordinator and FanIn;
4. `2eae8edb3fac97da05d3bb27afdffee8dae760ef` - C1/C2/C4/C8 concurrency/recovery proof;
5. `79342f4c1a6e199937d69ea19b07897c542f20f1` - stale pre-G2 worker-substrate test invariant corrected after the first full-suite run.

## Accepted architecture

G3 preserves the frozen authority chain:

`Mission -> PlanRevision -> WorkPackage DAG -> dependency proof -> WorkPackageAttempt -> canonical Task -> backend -> EvidenceSubmission -> FanIn -> Sol adjudication`.

No WorkPlan or second WorkPackage lifecycle was introduced. `Task` remains the execution-attempt lifecycle. The admission coordinator is stateless and bounded; it does not persist a scheduler/readiness state machine.

### Dependency proofs

Company Kernel schema version 3 adds immutable `dependency_satisfaction_proofs` with exact same-plan edge/package foreign-key identity. The mechanical evaluator owns exactly the frozen predicates:

- `accepted_outcome`;
- `published_success`;
- `evidence_available`;
- `settled`.

`published_success` remains an exact Run-backed predicate; reasoning Tasks do not fabricate a `run_id`. `settled` binds the exact known attempt-set hash and requires one known head plus terminal or explicit containment evidence.

Proof identity excludes observation timestamp and observed kernel-state-version churn. A durable replay therefore returns the original stored observation metadata while preserving the same proof identity.

### WorkPackageAttempt admission

A downstream Attempt freezes the exact dependency proof refs/hashes into the final provider-neutral `ReasoningSpecV1`, route request hash, WorkPackageAttempt request hash, and canonical Task request identity.

Exact controller replay reconstructs the frozen assignment from durable Attempt/proof state and does not re-evaluate current upstream facts. This prevents later dependency changes from invalidating a previously admitted Attempt.

`single_active` is enforced mechanically. A new route is blocked while an existing Attempt is active or uncontained. A successor must explicitly name the exact current head through `supersedes_attempt_id`; the prior head must be terminal or mechanically contained. Changed proof/route material therefore creates a new Attempt rather than mutating the previous identity.

Current `PlanRevision` and `plan_state_version` expectations are revalidated inside the package admission transaction. ProjectScope project/resource/generation remains part of the frozen route authority.

### Bounded coordinator

The current-plan coordinator:

- accepts at most 32 prepared WorkPackages;
- supports only canonical C1/C2/C4/C8 concurrency limits;
- derives deterministic per-package controller request identities;
- orders candidate work by immutable `package_key`;
- counts active nonterminal/uncontained Attempts;
- admits only within the remaining canonical capacity;
- treats unsatisfied current dependencies as deterministic `not_ready` deferral without consuming a new-admission slot;
- replays already-owned package identities without another Task/backend start;
- rechecks current plan revision/version at each lower-level admission;
- performs one bounded pass and never loops, sleeps, waits, or becomes a durable scheduler.

A repeated bounded scan may discover later work after earlier work settles, but an already-owned WorkPackageAttempt/Task/backend start never duplicates.

### Deterministic FanIn

Canonical FanIn lives with provider-neutral worker evidence, not in a parallel orchestration plane. `FanInV1` provides:

- exact expected/collected/missing unit coverage;
- explicit partial/blocked/uncertain units;
- immutable submission/evidence/artifact/provenance/retrieval pointers;
- assignment-provided structured fact keys only;
- exact structured conflicts without choosing a semantic winner;
- exact duplicate facts distinguished from conflicts;
- unresolved uncertainty references;
- aggregate usage and exact counts;
- deterministic ordering;
- 48 KiB normal target and 64 KiB hard ceiling with bounded externalization/truncation metadata.

Execution, retrieval/scout, and reasoning producers use the same EvidenceSubmission/FanIn shape. Provider/backend identity remains provenance, not synthesis semantics. Sol remains the semantic adjudicator.

## Interrupted implementation repair

During the original G3 work an interrupted tool/compaction sequence left an incomplete parallel `soma/fanin` draft, including a truncated dependency module and orphan FanIn files. Acceptance was withheld once the actual Git state was independently inspected.

The repair deliberately followed the canonical plan rather than preserving the interrupted layout:

- mechanical dependency evaluation/persistence moved to `soma/company_kernel/dependencies.py`;
- canonical FanIn moved to `soma/worker_evidence/fanin.py`;
- the broken/orphan `soma/fanin` layer was removed;
- admission replay and `single_active` semantics were hardened before proceeding;
- broad affected regression evidence was re-established before the C1/C2/C4/C8 gate.

This was implementation/tooling interruption, not a research-assumption invalidation. No frozen architecture principle required weakening.

## G3.5 frozen mechanics proof

One immutable eight-WorkPackage fixture and the same prepared assignment routes were exercised under C1, C2, C4, and C8. Only the canonical concurrency ceiling changed.

The deterministic fake backend produced:

- six successful units;
- one provider rejection;
- one deterministic timeout.

For every fresh C1/C2/C4/C8 fixture the durable database contained exactly:

- 8 WorkPackageAttempts;
- 8 canonical reasoning Tasks;
- 8 reasoning backend rows;
- 8 reasoning start-attempt rows;
- 8 distinct backend refs.

Additional proofs:

- duplicate coordinator replay created no duplicate Attempt, Task, backend row, or provider-send boundary;
- process/controller restart through new TaskManager, ProjectScope store, Reasoning store and fake backend objects completed the remaining work with exactly eight provider creates in aggregate;
- a cancelled long-running unit remained cancelled after reconnect and was not restarted;
- FanIn over the six successful EvidenceSubmissions reported exact missing units `unit-07` and `unit-08`;
- provider failure/timeout evidence did not become fabricated successful EvidenceSubmissions.

Dedicated stress result: `7 passed`.

## Validation evidence

Focused and affected gates during G3:

- dependency evaluator + graph/schema contracts: `49 passed`;
- EvidenceSubmission + FanIn contracts: `23 passed`;
- hardened admission/dependency coordinator gate: `20 passed`;
- repaired cross-plane regression gate: `184 passed`;
- frozen C1/C2/C4/C8 stress fixture: `7 passed`;
- G3.5 checkpoint gate: `41 passed`;
- stale full-suite invariant correction gate: `53 passed`.

Ruff check, Ruff format-check and `git diff --check` passed for the G3 source/tests at their checkpoint gates.

### Full-suite Gate 3

First full suite run:

- run: `20260812T103801Z_executable_profile_fa4f172f`;
- result: `2852 passed, 35 skipped, 1 xfailed, 1 failed`;
- duration: `777.25s`;
- the sole failure was `tests/test_worker_substrate_foundation.py::test_interaction_commands_do_not_add_task_or_backend_lifecycle_kinds`.

That test was a stale pre-G2 compatibility assertion expecting only `durable_command` / `soma_durable_run`, even though G2 had already deliberately accepted the internal reasoning Task/backend pair. Production code was not changed. The test was corrected to protect the intended invariant: worker interaction commands add no additional lifecycle beyond the established durable + reasoning pair. The correction passed `53` targeted Task/substrate/reasoning tests.

Authoritative second full suite:

- run: `20260812T105538Z_executable_profile_c07a1559`;
- result: `2853 passed, 35 skipped, 1 xfailed`;
- failures: `0`;
- duration: `693.76s (0:11:33)`;
- exit code: `0`.

Gate 3 therefore has both affected regression evidence and a clean full repository suite.

## Negative-boundary verification

G3 did not:

- launch a real reasoning provider;
- spend OpenAI, Codex, Claude, or other provider quota;
- add a real protected mutation path;
- grant provider-native agents mutation authority;
- add public MCP/tools or change the accepted 32-tool public schema;
- modify `server.py` or public gateway metadata/inventory for G3 activation;
- restart Soma;
- refresh the ChatGPT connector;
- refresh the repository wiki merely because it is stale;
- push any commit;
- touch the protected canonical-memory draft or concurrent patch-auto-repair research files.

The running Soma service remains the pre-G3 runtime. G3 is accepted as source/internal architecture only.

## Observations

### bug - Soma PowerShell group child identity bookkeeping

An earlier `powershell_group` exposed child IDs inconsistent with its `launched_run_ids`, leaving a ghost child displayed as queued while querying that exposed child ID returned `Run not found`. Repository preflight showed no remaining lock/run and direct single durable commands behaved normally. Critical G3 acceptance runs therefore used single `run_start` executions rather than the group surface.

Material impact on G3 architecture: none. Tooling bug remains worth separate repair.

### implementation-friction - interrupted G3 file transport

An interrupted file-creation/preview sequence produced incomplete/orphan G3 files. Independent Git inspection detected the mismatch before Gate 3 acceptance. Canonical paths were rebuilt and revalidated as described above.

Material impact: repaired before acceptance; no research assumption invalidated.

## Gate verdict

G3 is ACCEPTED.

Soma now has deterministic same-plan DAG admission, immutable dependency satisfaction proofs, provider-neutral reasoning Task reservation/recovery, bounded C1/C2/C4/C8 fan-out mechanics, restart/reconnect/cancellation idempotency, and bounded deterministic FanIn suitable for Sol semantic adjudication.

The next implementation gate is G4 - Protected mutation broker. No real provider or external mutation experiment is authorized by this acceptance.
