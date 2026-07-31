# V3-1A-LAUNCH-FAILURE-CONTAINMENT-1 — Completion Evidence

**Date:** 2026-07-31
**Status:** implemented locally; awaiting independent acceptance.
**Baseline:** `bb9b292b72b6cbeeb24b22a7010d2899f644bc1d`
**Push:** none.

## Outcome

Fresh local launch cleanup no longer acts on a numeric PID after start-identity capture fails. The runtime records a structured containment disposition, uses only the exact creator-held process handle or an already-established Job Object without identity, and retains mutation ownership whenever exact-process exit cannot be proved.

The existing canonical run plane remains authoritative. No lifecycle manager, public state, task command, gateway, provider execution, interaction command, or production activation was added.

## Containment contract

`LaunchContainment` distinguishes:

- `identity_captured`;
- `stop_confirmed`;
- `stop_unconfirmed`;
- `cleanup_error`.

Evidence is bounded to PID, method, identity presence, creator-handle kill attempt, exact-handle exit confirmation, and a bounded error. `LaunchIdentityUnavailable` carries this evidence and no longer implies successful containment by exception type.

`ProcessContainmentUncertain` carries post-identity cleanup evidence when identity-scoped termination cannot re-prove the recorded process absent.

## Lifecycle behavior

- Confirmed creator-handle stop retains the existing infrastructure-failure, publication, and lock-release behavior.
- Unconfirmed initial launch containment moves the run to `recovery_pending`, publishes no terminal result, and retains the repository lock.
- Unconfirmed recovery relaunch containment remains `recovery_pending` under the current lease and retains ownership.
- Parallel initial and refill uncertainty remain active `recovery_pending` children, do not count as terminal failures, and do not free concurrency as though the process were absent.
- Executable-child identity capture, attachment exception, attachment refusal, and timeout propagate unconfirmed containment into worker-level `recovery_pending`; the worker retains the repository lock.

## Identity-proven cleanup

The seven bounded cleanup paths now use the captured launcher or child identity and re-verify absence:

1. JobManager initial launch lease loss;
2. JobManager recovery relaunch lease loss;
3. parallel initial child launch lease loss;
4. parallel refill lease loss;
5. executable-child attachment exception;
6. executable-child attachment refusal;
7. executable-child timeout.

No touched path calls `terminate_process_tree(process.pid)` directly.

## Behavioral evidence

Executed regressions cover:

- creator-handle confirmed stop;
- creator-handle kill failure, wait timeout, and poll failure;
- simulated PID reuse with zero raw-PID queries or termination calls;
- initial and recovery JobManager uncertainty with lock retention;
- parallel initial and refill identity persistence and uncertainty;
- executable attachment exception, refusal, timeout, and unconfirmed cleanup;
- identity-scoped termination refusal on unreadable or mismatched identities;
- real `atomic_write_json` publication failure, durable failed-publication state, retry through `publish_run_result`, stable authoritative result/source hash, and idempotent success.

## CF1 classification

The inventory classification is intentionally unchanged and reported accurately:

- `launcher_identity` and `child_identity` remain in `RUN_SCALAR_SUMMARY_COLUMNS`;
- they are not in `RUN_INTERNAL_ONLY_COLUMNS`;
- their values remain absent from the governed public summary/control projections and gateway inventories.

This classification is distinct from exposure. The pre-existing `worker_identity` behavior through `get_status` remains outside this subgate and is not silently changed.

## Authority and exclusions

Generic authority delta is zero. Interaction commands and real providers remain inactive. The correction does not touch SSH/workflow/supervisor cleanup, add a handle keeper, start V3-1B, or authorise production use.

## Validation

- Changed-file Ruff format check: passed.
- Changed-file Ruff lint check: passed.
- Focused process, launcher, child, publication, CF1, and cancellation selection: `212 passed, 1 xfailed`.
- Dedicated parallel-group selection after refill coverage was added: `13 passed`.
- Full repository suite: `2551 passed, 35 skipped, 1 xfailed`.
- `python -m pip check`: passed with no broken requirements.
- `git diff --check`: passed; Git reported line-ending conversion warnings only.
- Mypy, Pyright, and pre-commit are not configured or available.

Repository-wide Ruff is not a clean baseline: its check reports 189 pre-existing formatting differences and 10 unrelated lint findings outside this package. Those files were not changed. Ruff passes on every Python file changed by this correction.

## Acceptance disposition

The implementation is ready for independent acceptance review after all validation commands listed in the final implementation report pass. This record does not itself accept `V3-1A-PROCESS-IDENTITY-1` and does not advance the roadmap.
