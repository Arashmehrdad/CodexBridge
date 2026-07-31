# V3-1A-DESCENDANT-CONTAINMENT-1 — Completion Evidence

**Date:** 2026-07-31
**Status:** implemented locally; awaiting independent acceptance.
**Baseline:** `b86d541d8df380b5a1cb0f65bdf294a8f722c086`
**Push:** none.

## Outcome

Fresh-launch containment now records root exit separately from owned-tree absence.
Creator-handle kill and wait can prove only `root_exit_confirmed`; terminal failure,
result publication, repository-lock release, and parallel-slot refill require
`terminal_containment_proven`, backed by exact empty-tree proof.

The existing canonical RunStore and JobManager plane remains authoritative. No
new lifecycle manager, public state, gateway, provider execution, interaction
command, handle keeper, or production activation was added.

## Containment contract

`LaunchContainment` now distinguishes:

- `identity_captured`;
- `root_exit_confirmed`;
- `tree_empty_confirmed`;
- `stop_unconfirmed`;
- `cleanup_error`.

The evidence records `root_exit_confirmed` and `owned_tree_empty` independently.
`terminal_containment_proven` is true only for `tree_empty_confirmed` with
positive empty-tree evidence. A creator-held `Popen` handle never sets it.

When a pre-established Job Object is supplied, cleanup checks it even after the
root has exited, terminates the owned tree, and waits boundedly for exact empty
membership. Any query error or failure to become empty remains uncertainty.

## Canonical caller behavior

All five fresh identity-capture callers now branch on terminal tree proof:

1. JobManager initial launcher;
2. JobManager recovery relaunch;
3. parallel initial launcher;
4. parallel refill launcher;
5. executable child.

Root-only evidence causes or preserves `recovery_pending`, suppresses terminal
publication, retains mutation ownership, and remains active in parallel
accounting. Identity-less creator-handle cleanup also no longer reports
`terminated=True` from root exit alone.

## Behavioral evidence

The regressions prove:

- a real root can exit while its short-lived descendant remains active;
- no raw-PID termination is attempted after identity capture fails;
- the canonical JobManager path remains `recovery_pending`, keeps an empty
  result unpublished, and retains its repository lock while the descendant is
  alive;
- recovery relaunch, parallel initial launch, and parallel refill treat
  root-only evidence as active uncertainty;
- executable-child root-only evidence propagates to worker-level
  `recovery_pending`;
- a pre-established Windows Job Object can terminate the owned tree and prove
  exact empty membership;
- the real zero-process cancellation path preserves its terminal winner and
  source hash through one `atomic_write_json` failure, lock release, retry via
  `cancel_run`, and idempotent success without repeated termination.

## Retained invariants

- No numeric PID is queried, enumerated, or terminated after fresh identity
  capture fails.
- Post-identity cleanup remains identity-scoped.
- Unproven cleanup retains or quarantines mutation ownership.
- Parallel uncertain children consume their slots.
- Windows `KILL_ON_JOB_CLOSE` behavior remains intact.
- Public gateway and schema files are unchanged.
- Authority delta remains zero.

## Validation

- Changed-file Ruff format: passed.
- Changed-file Ruff check: passed.
- Focused descendant/cancellation/JobManager selection:
  `171 passed, 1 xfailed`.
- Prior process/adapter/foundation floor:
  `292 passed, 1 xfailed` (previous floor: `286 passed, 1 xfailed`).
- Prior adjacent floor:
  `277 passed` (previous floor: `272 passed`).
- Exact post-audit containment selection:
  `208 passed, 1 xfailed`.
- Isolated chat-footprint performance benchmark: passed.
- Clean full repository rerun:
  `2556 passed, 35 skipped, 1 xfailed`.
- `python -m pip check`: passed with no broken requirements.
- `git diff --check`: passed; Git reported only the repository's existing
  line-ending conversion warning.
- Mypy, Pyright, Pylint, pre-commit, and security scanning are not configured.

The first full-suite attempt ran concurrently with repository inspection and
failed only the existing chat-footprint microbenchmark at its 0.5 ms batch
threshold. The benchmark passed alone, and the uncontended full-suite rerun
passed completely. No product change was made for that environmental timing
result.

## Acceptance disposition

The corrective package is ready for independent acceptance review.
`V3-1A-PROCESS-IDENTITY-1` remains unaccepted until that audit is recorded.
This completion does not activate interaction commands, real providers, V3-1B,
production behavior, or push.
