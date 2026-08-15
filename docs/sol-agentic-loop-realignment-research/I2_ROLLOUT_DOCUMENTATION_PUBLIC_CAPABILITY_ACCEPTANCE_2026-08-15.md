# I2 Rollout, Documentation, and Public Capability Reconciliation - Acceptance

Date: 2026-08-15  
Stage: I2 - rollout/docs/public capability reconciliation  
Status: ACCEPTED  
Branch: `lane/memory-integration-foundation-1`  
I2 source/docs HEAD before this acceptance record: `b28e7858419cd908b9e969463f1c4de172019875`

## 1. Scope and owner direction

I2 closes the mandatory Sol semantic-continuation + Soma portable-Skill programme after the owner explicitly removed the earlier desire for an additional normal-Chat reasoning add-on. The accepted end state remains the architecture already specified by the implementation plan:

```text
Sol / ChatGPT = single semantic reasoning head
Soma continuation = durable semantic re-entry
Soma Skills = portable reusable guidance
Task / Run / repo / SSH / other providers = canonical mechanical authorities
```

No semantic planner, next-step engine, persisted reasoning state, Skill router brain, LocalAgent/Supervisor brain, or secondary reasoning model was added.

Optional A1/A2 adapters are not activated by this gate because the mandatory programme does not have measured evidence that they are required.

## 2. I2 implementation and reconciliation commits

I2 uses two implementation/reconciliation commits after I1:

```text
c93315f50bd5eb398e7193293f20ee58897741ee
  Reconcile I2 F1 and public-surface baselines

b28e7858419cd908b9e969463f1c4de172019875
  Reconcile continuation and Skill rollout docs
```

The first commit advances stale CF1 measurement/transport fixtures to the accepted F1 single-Run identity and final 38-gateway public surface, and fixes the compact preflight status adapter so it accepts the current structured `files` contract without requiring the removed legacy `changed_files` field.

The second commit reconciles active human-facing architecture/runbook/config documentation, including README, PLANS, AGENTS, the example Skill-library configuration, and the continuation/Skill runbook.

Historical research was not rewritten.

## 3. Public capability reconciliation

After the managed service restart and connector recovery, live capability identity converged.

Observed live identity:

```text
server_build_hash:
51a21dd4aab48529f9fe2de368192610d19cd664f9f580269237fbdd6906ec25

schema_hash:
42bdb69d96fb0a4cd66c3d023ce95decfbaa9b4907781041e49f0495248f9888

capability_epoch:
51a21dd4aab4-42bdb69d96fb

public gateway count:
38

operation schema count:
286

public input schema hash:
5ef04e36efed1496ede40ffe3c51c8f8fe3de06255f0b9ecfda15905c4df8ebd

public descriptor hash:
e53780fa49bc31702e89601bd8f9b8db3844b15aeac5b77c0659a0e2171ebd60

operation inventory hash:
ffdcc0d5f7bb2d93316c3ce0b67de86b1d8f1dc35162316005b95a117417165b
```

Live `system_query(capability_identity)` reported:

```text
converged = true
discovery_passes_converged = true
operation_schema_error = ""
mismatches = []
restart_required = false
connector_refresh_required = false
operation_contract_repair_required = false
```

The final public identity therefore matches the accepted S3/S4 topology and hashes; I2 changed reconciliation/documentation and compatibility behavior without introducing another public gateway or operation.

## 4. Live preflight proof after restart

After the owner brought the managed Soma server back up, live `run_query(preflight)` returned:

```text
ok = true
source = live
repo = soma
branch = lane/memory-integration-foundation-1
head_commit = b28e7858419cd908b9e969463f1c4de172019875
running = []
queued = []
launch_pending = []
locks = []
```

The worktree is intentionally not globally clean because unrelated concurrent research/audit documents remain untracked. These files were preserved and are not part of this programme.

This live result specifically proves the I2 compact-preflight compatibility repair is active in the restarted runtime.

## 5. Test and compatibility evidence

### 5.1 Full repository diagnostic sweep

Durable run:

```text
20260815T173342Z_executable_profile_84216753
```

Result:

```text
3513 passed
34 skipped
1 xfailed
17 failed
```

This diagnostic sweep exposed stale programme-owned contracts plus unrelated existing/environmental failures. It was not accepted as the I2 seal.

Programme-owned failures found by that sweep and corrected before closeout:

```text
CF1 Run query baseline still expected pre-F1 planner index
CF1 Run-store baseline omitted F1 logical identity columns
transport representative map omitted continuation/Skill gateways
worker-isolation test hard-coded 36 public gateways
compact preflight required removed changed_files field
```

The remaining full-suite failures were outside this programme: TradingLab/MT5 environment or package provenance, legacy pytest-launcher environment behavior, Windows process-enumeration timing, and existing Worker Gateway/FastMCP authentication behavior. They were not silently modified in this lane.

### 5.2 Programme-owned stale-contract reconciliation

Durable run:

```text
20260815T175357Z_executable_profile_a22578f5
```

Result:

```text
60 passed
26 skipped
Ruff: PASS
git diff --check: PASS
```

### 5.3 Compact preflight compatibility fix

Durable run:

```text
20260815T180332Z_executable_profile_dd6150e3
```

Result:

```text
4 passed
Ruff: PASS
git diff --check: PASS
```

### 5.4 Final mandatory programme superset

Durable run:

```text
20260815T180353Z_executable_profile_9ed17b75
```

Behavioral result:

```text
775 passed
26 skipped
```

This is the final mandatory programme behavioral seal. The process exit was non-zero only because a repository-wide Ruff invocation then found ten pre-existing lint findings in unrelated memory-pilot/basic-memory/worker-cancellation files.

Targeted Ruff over every I2-touched source/test file plus `git diff --check` was then run separately:

```text
20260815T180815Z_executable_profile_758d66a1
```

Result:

```text
All checks passed!
exit code = 0
```

No programme-owned lint or diff-check failure remains.

## 6. Migration compatibility

I2 retains the plan's required compatibility contract:

```text
historical Runs without F1 logical identity remain readable
existing Task API still works without continuation context
ordinary Soma effect tools still work without continuation
Skill library has a safe runs-internal development fallback when no external root is configured
repository-local .agents/skills packages are not silently ingested or activated
continuation context remains optional for ordinary work
powershell_group and hermes_service remain outside F1 single-Run identity semantics
```

The accepted F1/C1-C5/S1-S4 test corpus and the final 775-test programme superset cover these compatibility boundaries.

## 7. Architecture invariants checked

```text
PASS  Sol remains the only semantic reasoning head
PASS  continuation stores re-entry facts, not reasoning state
PASS  resume does not choose a next action
PASS  Skill search/retrieval is mechanical; no semantic router was introduced
PASS  Skill scripts remain inert until existing Soma execution authority is used
PASS  Company remains separate
PASS  ordinary work does not require continuation or Skill ceremony
PASS  Task/Run continuation origins remain immutable under replay
PASS  single-Run F1 scope remains powershell / remote_powershell / hermes_companion only
PASS  powershell_group semantics remain unchanged
PASS  hermes_service semantics remain unchanged
PASS  no project-local Skill auto-ingestion
PASS  no hidden ChatGPT/session-state claim
```

## 8. Rollout incident and recovery

The first managed restart was initiated from a durable Soma Run. Stopping the server interrupted the same control path before it could finish bringing the service back up, leaving the connector temporarily unavailable. No repository state was lost.

The owner manually started the managed Soma service. The new process then exposed the final source generation and passed live preflight/capability convergence.

This incident is recorded as rollout evidence; it does not alter the continuation/Skill architecture. A future service-control improvement should avoid self-hosting a restart lifecycle through the process being stopped.

## 9. Contamination / concurrent-work audit

Preserved and excluded from this programme:

```text
docs/OWNER_INTENT_INTEGRITY_ROOT_CAUSE_AUDIT_2026-08-15.md
docs/soma-improvement-research/*
```

The improvement-research lane expanded while this programme was active. Those untracked documents remain owner/concurrent work and were not committed by I2.

Protected file remains untouched:

```text
docs/CANONICAL_PROJECT_MEMORY_CONTRACT.md
```

No Codex or provider-native subagent was used. No push was performed.

## 10. Final verdict

```text
F0  ACCEPTED
F1  ACCEPTED
C1  ACCEPTED
C2  ACCEPTED
C3  ACCEPTED
C4  ACCEPTED
C5  ACCEPTED
S1  ACCEPTED
S2  ACCEPTED
S3  ACCEPTED
S4  ACCEPTED
I1  ACCEPTED
I2  ACCEPTED
```

Mandatory roadmap completion:

```text
13 / 13 = 100%
```

The owner-visible end state is now the intended one:

```text
owner: continue
Sol -> continuation_query.resume -> independently re-check live state -> optionally load Skills -> reason -> use ordinary Soma tools

owner: check repo status
Sol -> repo_query -> answer
```

No continuation ceremony for simple work.  
No Skill ceremony for simple work.  
No second brain.

**I2 ROLLOUT / DOCUMENTATION / PUBLIC CAPABILITY RECONCILIATION: ACCEPTED.**
