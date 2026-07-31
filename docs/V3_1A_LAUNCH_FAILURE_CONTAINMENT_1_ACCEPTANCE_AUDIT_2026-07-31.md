# V3-1A-LAUNCH-FAILURE-CONTAINMENT-1 — Independent Acceptance Audit

**Date:** 2026-07-31
**Verdict:** not accepted; bounded descendant-containment correction required.
**Implementation commit audited:** `b6adcae3267607e26d471163153b2cbec92b41b5`
**Parent gate:** `V3-1A-PROCESS-IDENTITY-1`
**Push:** not authorised.

## 1. Summary

The package closes the raw-PID and lifecycle uncertainty defects reproduced against `89fb199`. After process-start identity capture fails, the new fresh-launch path does not query the numeric PID again, enumerate descendants from it, or invoke a PID-based terminator. Structured containment evidence distinguishes identity capture, root-stop confirmation, unconfirmed stop, and cleanup error. Unconfirmed cleanup moves canonical runs to `recovery_pending`, suppresses terminal publication, retains repository locks, and remains active in parallel-group accounting. The seven touched post-identity cleanup paths now use the captured identity and re-verify exact-process absence. CF1 classification is reported accurately.

The package does not close `V3-1A-PROCESS-IDENTITY-1`. It treats creator-handle confirmation that the root process exited as sufficient terminal containment even though its own `LaunchContainment` contract explicitly says this does not prove descendants are gone. Independent adversarial execution produced a root that spawned a child before identity capture failed. The creator handle killed and reaped the root, `stop_confirmed` became true, and the child remained alive. The canonical JobManager path then transitioned the run to terminal `failed`, published the result, and released the repository lock while that descendant was still running.

Root exit is not owned-tree exit. Terminal failure and lock release require proof that no process from the launch can remain active, not merely proof that the original `Popen` root returned.

## 2. Repository state audited

- Repository: `D:\Github\Soma`
- Branch: `lane/memory-integration-foundation-1`
- Candidate HEAD: `b6adcae3267607e26d471163153b2cbec92b41b5`
- Worktree at audit start: clean
- Branch state: ahead of origin by 30 commits
- Push: none

The candidate changed eleven files with 1,178 insertions and 234 deletions. No public gateway/schema change or new lifecycle authority was introduced.

## 3. Evidence that passed

### 3.1 Identity-less PID action is removed

The audit verified that `contain_fresh_launch` uses `process_identity(pid)` only for the initial identity-capture attempt. After that attempt fails, cleanup is limited to the exact creator-held handle or an already-established Job Object. The PID-reuse regression makes `process_is_running` fail if called after identity failure and records any `terminate_process_tree` call; neither is invoked.

### 3.2 Unconfirmed containment remains non-terminal

The initial JobManager uncertainty path stores `recovery_pending`, leaves `result` empty, avoids ResultPublication, and retains the repository lock. Recovery relaunch uncertainty also remains `recovery_pending` under the current lease and lock. The worker outer exception path publishes only terminal statuses and excludes both `recovery_pending` and `cancellation_pending` from lock release.

### 3.3 Parallel accounting is honest

`recovery_pending` is included in active parallel statuses, does not increment terminal-child count, and prevents refill from treating the uncertain slot as free. Initial and refill launch regressions execute the relevant behavior.

### 3.4 Post-identity cleanup is scoped

The touched JobManager, parallel-group, attachment-failure, attachment-refusal, and timeout paths use `require_identity_scoped_cleanup` with the captured launcher or child identity. The helper delegates to identity-scoped termination and raises `ProcessContainmentUncertain` when exact-process absence cannot be re-proven.

### 3.5 CF1 reporting is accurate

`launcher_identity` and `child_identity` remain in `RUN_SCALAR_SUMMARY_COLUMNS`, not `RUN_INTERNAL_ONLY_COLUMNS`. Their values remain excluded from the governed public summary/control projections. The pre-existing `worker_identity` exposure remains explicitly deferred.

### 3.6 Independent focused validation

The independently selected process, launcher, child, publication, parallel, cancellation, JobManager, and job-worker suites passed:

- **203 passed, 1 xfailed**;
- durable run: `20260731T052128Z_executable_profile_a96f4888`.

The submitted completion report additionally records **2551 passed, 35 skipped, 1 xfailed** for the full repository suite. The full suite was not rerun after the decisive containment contradiction was reproduced.

## 4. Acceptance blocker — root exit is incorrectly treated as tree containment

`LaunchContainment` states that creator-handle evidence reports only the root process and never claims descendants are gone unless a Job Object or another ownership primitive proves it. Despite that, `LaunchContainment.stop_confirmed` becomes true whenever `process.wait(...)` or `process.poll()` proves the root exited, with method `creator_handle`.

JobManager and the other launch callers interpret that root-only value as terminal-safe containment:

- the run becomes infrastructure `failed`;
- the canonical terminal result is published;
- the repository lock is released;
- parallel failure/refill behavior may proceed.

There is no enforced invariant preventing the launched worker or executable child from spawning a descendant before identity capture completes. The canonical launchers are ordinary running `subprocess.Popen` processes; they are not started suspended and none passes a pre-established Job Object into `capture_launch_identity`.

### 4.1 Direct escaped-descendant probe

The audit launched a root process that immediately spawned a sleeping child and wrote its PID. Identity capture was then forced to fail. Creator-handle kill and wait successfully reaped the root.

The implementation returned:

```text
{
  'disposition': 'stop_confirmed',
  'root_exit_confirmed': True,
  'stop_confirmed': True,
  'child_alive_after_root_stop': True
}
```

Durable run: `20260731T052128Z_executable_profile_061e12e8`.

The child was deliberately short-lived and exited naturally after the proof. No unrelated process was touched.

### 4.2 Canonical lifecycle probe

The same race was exercised through `JobManager.start_git_readonly`, not only the helper function. The launch root spawned a child before identity capture failed; creator-handle cleanup reaped the root; the child remained alive.

The canonical result was:

```text
{
  'response_status': 'failed',
  'durable_status': 'failed',
  'publication_status': 'published',
  'lock_present': False,
  'descendant_alive': True
}
```

Durable run: `20260731T052343Z_executable_profile_da5d64cb`.

This violates gate sections 3.1, 3.4, 3.5, 3.6 and the final acceptance condition. Soma published terminal failure and released mutation ownership while work created by that launch remained active.

## 5. Why the committed tests missed it

The confirmed-stop tests use fake handles that cannot create descendants. `test_confirmed_identity_capture_failure_remains_terminal_and_releases_lock` therefore encodes the unsafe assumption that creator-handle root exit is equivalent to launch-tree containment.

The PID-reuse test correctly proves that Soma does not act on a reused numeric PID, but it does not test a descendant that escaped before the root was reaped.

The real publication retry test exercises `publish_run_result` directly. Together with the existing cancellation test it covers the components, but it does not pin the complete real cancellation → atomic write failure → lock release → retry → no-retermination path in one repository regression as section 3.8 requested. Runtime behavior previously passed an independent integrated probe; the closing correction should pin that integrated path while touching the tests again.

## 6. Required correction

The next package must separate **root-exit confirmation** from **owned-tree absence proof**.

A safe minimal disposition is:

- identity captured: normal healthy attachment;
- identity unavailable, root exit confirmed, but no pre-established tree containment: durable `recovery_pending`, no publication, lock retained;
- identity unavailable and a pre-established Job Object proves empty: terminal infrastructure failure may publish and release the lock;
- cleanup error or root exit unconfirmed: durable `recovery_pending`, no publication, lock retained.

Equivalent designs are acceptable only if they prove no descendant from the launch can remain active. Parent-table enumeration or PID inference after identity failure is forbidden.

Required behavioral evidence:

1. real root → child escape attempt where root exit alone remains non-terminal and retains the lock;
2. canonical JobManager lifecycle proof with no terminal publication while the child is alive;
3. parallel initial and refill equivalents remain active and do not free slots;
4. executable-child identity-capture failure follows the same tree-safe rule;
5. a pre-established Job Object empty proof, if used, permits the confirmed terminal path;
6. the unsafe fake-handle terminal test is replaced with tree-aware evidence;
7. the integrated real publication-retry regression required by the prior gate is pinned;
8. all retained `b6adcae` results remain green.

## 7. Authority disposition

Authority delta remains zero. `RunStore` and `JobManager` remain canonical for lifecycle, publication, and lock ownership. Process control and Job Objects remain subordinate proof mechanisms. No supervisor, handle keeper, public state, task command, provider execution, interaction command, or gateway is required.

## 8. Disposition

- `V3-1A-LAUNCH-FAILURE-CONTAINMENT-1`: implemented but not accepted;
- `V3-1A-PROCESS-IDENTITY-1`: remains unaccepted;
- active bounded corrective gate: [`V3_1A_DESCENDANT_CONTAINMENT_1_GATE_2026-07-31.md`](V3_1A_DESCENDANT_CONTAINMENT_1_GATE_2026-07-31.md);
- `V3-1A-INTERACTION-COMMANDS-1`: inactive;
- real providers, V3-1B, production activation and push remain forbidden.
