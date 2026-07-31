# V3-1A-CANCELLATION-CLOSURE-1 — Independent Acceptance Audit

**Date:** 2026-07-31
**Verdict:** not accepted; one bounded launch-failure-containment correction remains.
**Implementation commit audited:** `89fb199c4a1a62fc464eed38d6b2836b3094941b`
**Parent gate:** `V3-1A-PROCESS-IDENTITY-1`
**Push:** not authorised.

## 1. Summary

The closure package fixes nearly every blocker from the prior cancellation-authority audit. It closes contradictory empty-row publication, covers the missing canonical launcher identity paths, replaces inherited environment extras with a positive policy, reports publication failure honestly, proves exact publication retry independently, enables Windows `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`, restores deterministic cancellation ordering, and keeps launcher/child identity values out of the public projections governed by this gate.

The package does not yet close `V3-1A-PROCESS-IDENTITY-1`. Fresh-launch failure handling still performs raw-PID process-tree termination when no process identity exists, and callers cannot distinguish a proven stop from uncontained uncertainty. Independent adversarial evidence shows that this uncertainty is currently converted into terminal infrastructure failure with repository-lock release.

No interaction-command work is active.

## 2. Evidence that passed

- focused worker/process/adapter/foundation suites: **286 passed, 1 xfailed**;
- adjacent audit selection: **272 passed**;
- no process or cancellation test was deselected;
- `NOTHING_RECORDED` plus non-empty kernel membership cannot publish and becomes contradictory uncertainty;
- all four canonical launcher callers and the executable-child caller invoke fresh identity capture;
- arbitrary inherited environment extras are refused and reviewed values remain credential-checked;
- cancellation publication failure returns an explicit partial outcome;
- independent real-publication evidence proved durable `failed` state, lock release after zero-process proof, identical result JSON and source hash on retry, no repeated termination, and idempotent publication success;
- Windows `KILL_ON_JOB_CLOSE` crash simulation passes inside the focused suite;
- deterministic child → worker → launcher termination ordering passes without touching host processes;
- launcher and child identities are absent from `get_status`, control projections, summary projections, and gateway inventories;
- authority delta remains zero;
- worktree was clean at the audited commit.

Durable validation references:

- focused suites: `20260731T033958Z_executable_profile_66dda70a`;
- adjacent suites: `20260731T033958Z_executable_profile_9263a7f3`;
- real publication failure/retry probe: `20260731T034049Z_executable_profile_b626710b`.

## 3. Acceptance blockers

### 3.1 Fresh identity failure still invokes raw-PID termination

`process_control.capture_launch_identity` correctly tries the exact creator-held `Popen` handle first. But after `kill()` and `wait()`, it does this when the numeric PID appears live:

```python
if pid > 0 and process_is_running(pid):
    terminate_process_tree(pid, grace_seconds=timeout_seconds)
```

At that point no start identity exists. The live PID may be:

- the original process whose exact handle did not stop it;
- a reused PID occupied by another process;
- an unreadable process for which ownership cannot be proven.

The owner-approved contract forbids all three from being acted on by number alone.

The audit supplied an identity-less creator handle, simulated a live numeric PID after handle wait, and recorded the raw termination call:

```text
{'killed': 1, 'waited': 1, 'raw_pid_calls': [4242]}
```

Durable probe: `20260731T033806Z_executable_profile_76000fa9`.

This is an acceptance blocker and a direct violation of the gate's binding no-raw-PID decision.

### 3.2 The exception contract claims proof it does not possess

`LaunchIdentityUnavailable` states that it is raised only after the process has been stopped, so callers may assume nothing remains. The implementation does not verify that claim:

- exceptions from `process.kill()` are ignored;
- exceptions or timeout from `process.wait()` are ignored;
- the raw tree terminator's result is ignored;
- no exact-handle terminal observation is returned;
- no uncertain disposition exists.

Consequently the same exception represents both confirmed containment and unconfirmed containment.

### 3.3 JobManager terminalises and releases ownership on unconfirmed containment

The initial JobManager launch catch path treats every identity-capture exception as ordinary infrastructure failure. It transitions the run to terminal `failed`, publishes a result, and releases the repository lock.

The audit injected `LaunchIdentityUnavailable("termination unconfirmed")`. The durable result was:

```text
accepted=False
response_status=failed
durable_status=failed
lock_present=False
```

Durable probe: `20260731T034423Z_executable_profile_f1c4e082`.

When a newly created process may still be alive and ownership cannot be proven, terminal failure and lock release are forbidden. The run must remain durably uncertain/recovery-pending and retain or quarantine mutation ownership.

### 3.4 Identity-proven cleanup paths still discard their proof

After identity capture succeeds, several touched paths still call `terminate_process_tree(process.pid)` directly instead of using the captured identity:

- JobManager recovery relaunch lease loss;
- JobManager initial launch lease loss;
- parallel-group refill lease loss;
- parallel-group initial child lease loss;
- executable-child attachment exception;
- executable-child attachment returning false;
- executable-child timeout.

These paths possess `launcher_identity` or `child_identity` and should use identity-scoped termination with post-action absence verification. A process can exit and its PID can be reused between the triggering condition and raw termination.

### 3.5 Required behavioral tests are weaker than reported

The implementation source is directionally correct, but several gate claims are not pinned by the committed tests:

- `test_child_identity_capture_failure_stops_the_child` inspects source strings rather than executing the failure path;
- `test_every_canonical_launcher_path_persists_a_non_empty_identity` exercises JobManager only, and its recovery assertion is conditional;
- parallel initial/refill tests do not directly assert non-empty stored identity;
- the committed publication test replaces the entire publisher with lambdas, so it does not prove durable failed-publication metadata, exact result/source hash, or the real retry implementation.

The real publication behavior passed the independent probe, so this is an evidence-regression gap rather than a current runtime defect. It must nevertheless be pinned before acceptance.

## 4. Reporting correction

The completion report says `launcher_identity` and `child_identity` are classified in `RUN_INTERNAL_ONLY_COLUMNS`. At `89fb199`, that is false.

They remain in `RUN_SCALAR_SUMMARY_COLUMNS`, beside `worker_identity`; `RUN_INTERNAL_ONLY_COLUMNS` contains only `worker_lease_token` and `run_dir`.

The actual public summary/control projections still exclude launcher and child identity values, so this is a classification/reporting error rather than a demonstrated public leak. The pre-existing `worker_identity` exposure through `get_status` remains explicitly deferred and is not introduced by this gate.

Durable classification probe: `20260731T033806Z_executable_profile_9d33cf5a`.

## 5. Accepted portions of the package

The following corrections do not need redesign:

- contradictory empty-row cancellation proof;
- reviewed inherited-extra policy;
- honest cancellation/publication response fields;
- lock release after proven zero-process termination despite publication failure;
- real publication retry implementation;
- Windows `KILL_ON_JOB_CLOSE` policy and crash proof;
- deterministic cancellation ordering;
- launcher/child public projection exclusion;
- additive migration behavior;
- zero authority delta.

The next correction must preserve these results.

## 6. Authority disposition

`RunStore` and `JobManager` remain canonical for run state, terminal transition, lock ownership and ResultPublication. `process_control` may construct process proof but may not convert uncertainty into terminal state. No new lifecycle manager, supervisor, handle-keeper, task command, gateway or result publisher is authorised.

Generic authority delta must remain **zero**.

## 7. Disposition

- `V3-1A-CANCELLATION-CLOSURE-1`: implemented but not accepted;
- active bounded corrective subgate: [`V3_1A_LAUNCH_FAILURE_CONTAINMENT_1_GATE_2026-07-31.md`](V3_1A_LAUNCH_FAILURE_CONTAINMENT_1_GATE_2026-07-31.md);
- `V3-1A-PROCESS-IDENTITY-1`: remains unaccepted;
- `V3-1A-INTERACTION-COMMANDS-1`: inactive;
- real Claude/Codex launch, provider accounts, live prompts, public worker access, V3-1B, production activation and push: forbidden.
