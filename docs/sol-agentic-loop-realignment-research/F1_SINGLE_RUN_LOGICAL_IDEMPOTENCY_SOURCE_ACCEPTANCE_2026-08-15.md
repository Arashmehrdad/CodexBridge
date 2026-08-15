# F1 Single-Run Logical Request Idempotency - Source Acceptance

Date: 2026-08-15
Programme: Sol Semantic Continuation + Soma Portable Skill Layer
Stage: F1 - Single-Run logical request idempotency
Status: ACCEPTED
Activation state: SOURCE ACCEPTED, NOT LIVE ACTIVATED

---

## Stage report

Stage:

```text
F1 - Single-Run logical request idempotency
```

Status:

```text
ACCEPTED
SOURCE ACCEPTED, NOT LIVE ACTIVATED
```

Branch / HEAD at implementation acceptance:

```text
branch: lane/memory-integration-foundation-1
F1 base: 1873c8522160d3b8ed850839975a4bc2a811bd36
F1 implementation commit: d6f51f01875660eb2593df50db8a76dd34f85bef
```

Implementation commit subject:

```text
Implement F1 single-Run logical request idempotency
```

Push:

```text
no
```

---

# 1. Executive verdict

F1 is mechanically accepted at source level.

The participating public `run_start` single-Run operations are exactly:

```text
powershell
remote_powershell
hermes_companion
```

The following operations remain explicitly outside F1:

```text
powershell_group
hermes_service
```

The accepted implementation now provides stable logical request replay for the three participating single-Run operations without changing canonical `run_id` semantics.

Required behavior is proven:

```text
new logical_run_request_id
  -> one canonical Run

same logical_run_request_id + same normalized effect request
  -> same canonical run_id
  -> no second worker launch

same logical_run_request_id + changed effect request
  -> logical_run_request_hash_conflict

N concurrent identical requests
  -> one Run row
  -> one launch
  -> same canonical run_id for all callers

lost/crashed response or controller process around admission/launch
  -> durable Run remains authoritative
  -> startup recovery retains the same run_id
  -> later retry replays the same Run
```

No continuation-specific middleware was introduced in F1.

---

# 2. Files changed

The F1 implementation commit changes exactly 11 tracked files:

```text
soma/gateway_models.py
soma/hermes_companion_client.py
soma/job_manager.py
soma/operation_locks.py
soma/run_store.py
soma/server.py

tests/test_hermes_companion_client.py
tests/test_job_manager.py
tests/test_public_descriptor_identity.py
tests/test_run_store.py
tests/test_tool_gateway_models.py
```

Exact implementation range:

```text
1873c8522160d3b8ed850839975a4bc2a811bd36
  ..
d6f51f01875660eb2593df50db8a76dd34f85bef
```

Range audit:

```text
11 files changed
1307 insertions
21 deletions
```

The range contains no continuation schema/service implementation, no Skill implementation, no Company changes, no canonical-memory changes, and no unrelated research files.

---

# 3. Schema and migration impact

F1 extends the authoritative `runs` table additively with:

```text
logical_run_request_id TEXT NOT NULL DEFAULT ''
request_hash            TEXT NOT NULL DEFAULT ''
```

It adds the partial unique index:

```text
idx_runs_logical_request
ON runs(logical_run_request_id)
WHERE logical_run_request_id <> ''
```

Historical rows retain empty values and remain readable.

The canonical identities remain distinct:

```text
run_id                 = canonical execution/effect identity
logical_run_request_id = logical invocation/replay identity
request_hash           = normalized effect request identity
```

A hand-built pre-F1 SQLite `runs` schema was migrated by constructing the current `RunStore`; the historical row remained readable and the two new columns plus partial unique index appeared additively.

No historical Run row is rewritten to invent a logical request identity.

---

# 4. RunStore authority changes

F1 adds a narrow caller-owned reservation seam:

```text
reserve_run_in_connection(...)
```

Behavior:

```text
new logical request ID
  -> insert launch_pending canonical Run

same ID + same request hash
  -> return existing Run, created=False

same ID + different request hash
  -> RunRequestConflict
```

F1 also adds:

```text
find_by_logical_request_in_connection(...)
find_by_logical_request(...)
reserve_next_unlocked_launch(...)
```

The lock-free relaunch reservation exists specifically so keyed `hermes_companion` Runs retain their established no-repository-lock behavior while still receiving conservative crash recovery and lease-generation CAS.

The ordinary historical `create_run()` API remains available and unchanged in meaning for existing unkeyed callers.

---

# 5. Normalized effect request identity

F1 computes the logical Run request hash from normalized effect-defining input before run-ID/lease-bound staging metadata is added.

It includes the effective Run tool, canonical repo/host identity, and normalized effect input such as applicable profile/executable, argv, working directory, environment, stdin, timeout, remote-PowerShell request envelope, and Hermes companion metadata.

It excludes response-only controls such as:

```text
return_when
wait_seconds
```

This is mechanically proven by a test where the same local effect is first requested with:

```text
return_when=accepted
wait_seconds=0
```

and then replayed with:

```text
return_when=terminal_or_timeout
wait_seconds=0
```

Both resolve to the same canonical Run.

Changed argv and changed stdin both produce `logical_run_request_hash_conflict` for a reused request ID.

---

# 6. Operation-lock integration

For keyed lock-requiring single-Run starts, F1 performs logical replay/admission, operation-lock acquisition, Run reservation, and lock-to-Run binding inside one short `BEGIN IMMEDIATE` transaction.

The transaction never spans worker execution.

This gives the required distinction:

```text
same logical request already persisted
  -> replay existing Run

concurrent identical keyed request
  -> converge on existing canonical run_id

unrelated repository busy
  -> ordinary repository-busy refusal
  -> logical request ID is not consumed
```

The existing legacy unkeyed launch path remains the default when `logical_run_request_id` is omitted.

F1 does not redefine operation locks as logical request identity.

---

# 7. Crash and startup recovery

F1 explicitly covers the difficult crash window after durable Run reservation but before launch artifacts are materialized or the worker is spawned.

For keyed Runs, startup reconciliation rebuilds run-ID/lease-bound durable input for the next lease generation and rematerializes exact launch artifacts before relaunch.

Local executable-profile crash proof:

```text
Run reserved as launch_pending
hard synthetic process interruption before run directory materialization
run directory absent
startup reconciliation
same run_id retained
lease generation advances 1 -> 2
staging manifest rebuilt for generation 2
input.json recreated
inputs/stdin.bin recreated with exact original bytes
same logical request later replays same run_id
```

Lock-free Hermes companion crash proof:

```text
Run reserved as launch_pending
no repository operation lock exists
hard synthetic interruption
startup reconciliation uses RunStore CAS relaunch reservation
same run_id retained
lease generation advances 1 -> 2
staging manifest rebuilt
no repository lock introduced
same logical request replays same run_id
```

This proves the accepted guarantee is stronger than duplicate prevention alone: the stranded canonical Run is recoverable through existing Soma startup recovery rather than requiring creation of another Run identity.

---

# 8. Public contract impact

F1 adds optional:

```text
logical_run_request_id
```

only to:

```text
run_start.powershell
run_start.remote_powershell
run_start.hermes_companion
```

It is not present on:

```text
run_start.powershell_group
run_start.hermes_service
```

Cross-operation schema tests explicitly reject attempts to supply it to the two excluded variants.

Public topology remains:

```text
public gateway count:     34
operation schema count:  264
```

No gateway and no operation was added.

Final fresh-source identity evidence:

```text
run: 20260815T121504Z_executable_profile_2dae13c2

public_schema_hash:
f233334aa321d4cb8621c46777d49b4c2eb8a7db3fe010e96f384d45eaef54b0

public_descriptor_hash:
2197483f531081738a5fc2a1560dcb1cad49b89568762970da8494557371528a

operation_inventory_hash:
71fa4cd300e4ac6cb4cfbe15d8bc779149a2e2f523d84f28d7cf65154b440588

operation_inventory_gateway_count: 34
operation_schema_count: 264
discovery_passes_converged: true
```

Final participating operation schema hashes:

```text
run_start.powershell
a20c7d64460204f4b8def5bb07977316896e391282cdbd0e0fd31e91bc5b0e24

run_start.remote_powershell
439a9e6f1a23b1d636bded9634faa49aee4f8bcaf898702272913ff4363a56c2

run_start.hermes_companion
6f2968303820e17c9834b56fc9d415bddefe74c847c857040e67926f5fcf4594
```

The two excluded operation schemas remained byte-identical to the pre-F1 running baseline:

```text
run_start.powershell_group
683c294968eb5719b5d19411d6928f7e407be0596cd389a7dc51219276cc753a

run_start.hermes_service
17ffb09310432c11e6666ad3a0c7bb23d014dd9263b03fc31d8945668c10265a
```

The operation inventory hash also remains unchanged, confirming topology did not expand.

---

# 9. Tests run

## Initial compatibility sweep

Durable run:

```text
20260815T114449Z_executable_profile_3734ba6e
```

Result:

```text
224 passed
2 failed
```

Both failures were expected stale fake-call assertions because the internal helper calls now included the backward-compatible default:

```text
logical_run_request_id = ""
```

No Run lifecycle behavior failed. Those fixture expectations were updated.

## Targeted F1 replay/concurrency gate

Durable run:

```text
20260815T115220Z_executable_profile_867e17da
```

Result:

```text
11 passed
194 deselected
Ruff: pass
```

## Migration and excluded-operation gate

Durable run:

```text
20260815T115340Z_executable_profile_52e1bf6c
```

Result:

```text
F1 RunStore migration/replay tests: pass
powershell_group / hermes_service negative schema control: pass
Ruff: pass
```

## Broad pre-final gate

Durable run:

```text
20260815T115405Z_executable_profile_be52246f
```

Result:

```text
467 passed
1 failed
```

The one failure was the intentionally stale public-schema hash fixture after `run_start` schema movement. No operation inventory/topology failure occurred. The fixture was advanced to the measured F1 source hash.

## Crash-recovery focused final gate

Durable run:

```text
20260815T120747Z_executable_profile_f272e010
```

Result:

```text
5 passed
79 deselected
Ruff: pass
```

This includes both post-commit/no-artifact local recovery and lock-free Hermes recovery.

## Final expanded F1 acceptance sweep

Durable run:

```text
20260815T120820Z_executable_profile_a962dee4
```

Covered:

```text
tests/test_run_store.py
tests/test_operation_locks.py
tests/test_job_manager.py
tests/test_tool_gateway_models.py
tests/test_hermes_companion_client.py
tests/test_remote_powershell.py
tests/test_cf1_gateway_operation_inventory.py
tests/test_mcp_flat_input_contract.py
tests/test_mcp_action_discovery.py
tests/test_public_tool_metadata.py
tests/test_capabilities.py
tests/test_public_descriptor_identity.py
tests/test_canonical_task_plane.py
tests/test_project_scope_foundation.py
```

Then Ruff over relevant source/tests and `git diff --check` in the same durable run.

Result:

```text
531 passed in 241.07s
Ruff: All checks passed!
git diff --check: pass
exit code: 0
```

This is the authoritative F1 source-acceptance test run.

---

# 10. Mandatory F1 behavioral proofs

The implementation has direct tests for the plan's required behaviors:

```text
new request creates one Run                                   PASS
same ID + same payload -> same run_id                         PASS
same ID + changed argv -> conflict                            PASS
same ID + changed stdin -> conflict                           PASS
changed response-only wait controls -> replay                 PASS
8 concurrent identical local requests -> one Run/one launch   PASS
identical request while canonical lock exists -> replay       PASS
unrelated busy request -> ordinary busy refusal                PASS
busy refusal does not consume future retry key                PASS
6 concurrent lock-free Hermes requests -> one Run/one launch  PASS
lost/crashed response window -> same Run retained              PASS
historical unkeyed rows remain readable                       PASS
crash after reservation before launch -> recoverable Run      PASS
crash/retry never creates a second run_id                      PASS
powershell_group does not gain F1 request field                PASS
hermes_service does not gain F1 request field                  PASS
```

---

# 11. Compatibility result

Backward compatibility is preserved intentionally:

- callers omitting `logical_run_request_id` retain the established unkeyed behavior;
- `run_id` remains canonical execution identity;
- canonical Task remains valid and continues to reserve its own backend Run identity;
- ProjectScope tests remain green;
- historical Runs with no F1 logical identity remain readable;
- operation-lock behavior for unassociated/legacy starts remains separate from logical request replay;
- `powershell_group` semantics are unchanged;
- `hermes_service` semantics are unchanged;
- no continuation requirement is imposed on ordinary Run starts.

The final expanded acceptance sweep includes canonical Task and ProjectScope tests specifically because F1 changes the shared Run persistence substrate.

---

# 12. Architecture invariants checked

```text
Sol remains the reasoning head                              PASS
F1 is general Run infrastructure, not continuation logic   PASS
one canonical run_id remains execution identity            PASS
logical identity remains replay identity only              PASS
no second Run executor introduced                          PASS
worker execution occurs after short DB transaction         PASS
repository lock is not treated as replay identity          PASS
unrelated busy refusal does not consume request ID         PASS
Hermes companion remains lock-free                         PASS
response controls excluded from effect hash                PASS
historical Runs remain readable                            PASS
Task/ProjectScope compatibility retained                   PASS
powershell_group remains separate                          PASS
hermes_service remains separate                            PASS
public topology remains 34 / 264                           PASS
```

---

# 13. Known limitations and explicit boundaries

## Strong guarantee is opt-in during migration

The strong replay guarantee applies only when the caller supplies non-empty:

```text
logical_run_request_id
```

Calls omitting it retain prior behavior by design.

## Parallel groups remain out of scope

`powershell_group` still has its separately researched future group-idempotency problem. F1 does not claim to solve it.

## Hermes service remains out of scope

`hermes_service` is not a RunStore single-Run start and does not receive F1 identity semantics.

## Source is not live yet

At acceptance time the running Soma process intentionally still serves the pre-F1 build.

Current source/runtime identity check reports:

```text
source_server_build_hash:
3fecfa1f72f52095485c3778dfdb09d22732cfd38fab59af5bdb0cea0cdc6127

running_server_build_hash:
25dff6c0e86fb789726bf4e692a500e5eb08e164b7ff16cdbbf54447b8459a41

mismatch:
source_running_server_build_hash

restart_required: true
connector_refresh_required: false
operation_contract_repair_required: false
```

This mismatch is expected evidence that F1 has not been live-activated. It is not an F1 source defect.

No restart or connector refresh is authorized or performed by this acceptance record.

---

# 14. Development notes retained transparently

During implementation one accidental harmless durable command was launched while switching between apply/run evidence tools:

```text
20260815T114030Z_executable_profile_a24730d3
```

Its command was only:

```text
Write-Output noop
```

It made no repository or service mutation beyond creating its normal durable Run record.

An early hard-crash focused test also initially asserted the staged stdin at the wrong filesystem location. The canonical staging manifest uses:

```text
inputs/stdin.bin
```

The recovery itself had succeeded; the assertion was corrected and the focused final gate then passed 5/5.

These development events do not alter the acceptance verdict.

---

# 15. Unrelated owner/concurrent work preserved

The implementation deliberately excluded and preserved unrelated untracked owner/concurrent work.

At F1 closeout this includes the separately protected:

```text
docs/CANONICAL_PROJECT_MEMORY_CONTRACT.md
```

and the concurrently appearing:

```text
docs/soma-improvement-research/iteration-01-reliability-ergonomics-portfolio-scan-2026-08-15.md
docs/soma-improvement-research/iteration-02-reproducible-core-runtime-dependency-provenance-2026-08-15.md
docs/soma-improvement-research/iteration-03-terminal-output-evidence-cold-archive-2026-08-15.md
docs/soma-improvement-research/iteration-04-durability-conformance-proof-harness-2026-08-15.md
docs/soma-improvement-research/iteration-05-mcp-tasks-extension-transport-adapter-feasibility-2026-08-15.md
docs/soma-improvement-research/iteration-06-runtime-source-drift-candidate-rejected-existing-capability-2026-08-15.md
docs/soma-improvement-research/iteration-07-public-surface-documentation-conformance-2026-08-15.md
```

None is part of the F1 implementation commit.

---

# 16. Commit state

Implementation commit created:

```text
yes
d6f51f01875660eb2593df50db8a76dd34f85bef
```

This acceptance document is intended to be committed separately so implementation source/tests and acceptance evidence remain independently auditable.

Push:

```text
no
```

---

# 17. Next authorized stage

The dependency sequence allows:

```text
C1 - continuation persistence foundation
```

only after F1 is accepted.

F1 source is now accepted, but this record does not authorize C1 and does not activate F1 into the running Soma service.

---

# Final verdict

**F1 SINGLE-RUN LOGICAL REQUEST IDEMPOTENCY: SOURCE ACCEPTED, NOT LIVE ACTIVATED.**

The three participating direct single-Run operations now have mechanically proven durable logical request replay, conflict detection, concurrency convergence, crash recovery, and backward compatibility without changing the semantics of groups, Hermes service, canonical Task, or ordinary unkeyed Run starts.
