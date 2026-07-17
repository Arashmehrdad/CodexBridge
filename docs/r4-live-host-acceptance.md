# R4 Live-Host Acceptance Evidence

Date: 2026-07-18

## Scope and isolation

The controlled gate used the registered QuoteFollow Oracle host only as an isolated acceptance fixture. Test files were confined to `/var/tmp/codexbridge-r4` and `/home/ubuntu/.codexbridge`. The production `quotefollow.service` unit and `/opt/quotefollow/current` were not modified.

## Durable execution identity

- Local run ID: `20260717T222632Z_ssh_monitored_command_fae9475e`
- Remote execution ID: `5ae97707e6257059c325eb6e4b5ee379`
- Parent PID and PGID: `1567113`
- Child PID: `1567114`
- Grandchild PID: `1567115`
- Process-start identity: `398057789`
- Controller fingerprint: `d3d7875e4d51775855f5c936abcc8914f0104c57a899aea5de5a594197166cab`

Before cancellation, the controller had run for 3,931.55 seconds. Its authoritative state was `running`, its heartbeat age was 2.88 seconds, and the PID/PPID/PGID table showed exactly one parent-child-grandchild tree in process group `1567113`.

The local worker was intentionally lost and the CodexBridge service restarted. Startup reconciliation adopted the existing remote controller with the same execution ID, PID, PGID, and process-start identity. Two additional concurrent reconcilers also completed without launching a duplicate controller. The remote host still contained only the original process tree.

## Identity-scoped cancellation

Cancellation was requested through `JobManager.cancel_run`, the same validated CodexBridge cancellation path used by the gateway. The cancellation report recorded:

- identity verified: true
- cancellation request persisted: true
- TERM sent: true
- KILL required: false
- exact process group terminated: true
- remote completion persisted: true
- identity changed: false

Remote `state.json` and `result.json` both converged to authoritative state `cancelled`. The result retained execution ID, PID, PGID, process-start identity, request ID, cancellation timestamps, and return code `-15`. Independent `kill -0` checks confirmed PIDs `1567113`, `1567114`, and `1567115` were all gone, with no remaining `/var/tmp/codexbridge-r4/r4_*` process.

## Canonical terminal publication

The local run converged to terminal status `cancelled` with summary `Run cancelled after verified remote termination`. The repository lock for `ssh:quotefollow_oracle_r4` was released.

Canonical publication evidence:

- publication status: `published`
- publication hash: `fa0ac0e1e895b1ccf4b71c5988c87f3b7d42a2a65f02a8871757534fa2c48db2`
- publication timestamp: `2026-07-17T23:32:37.226300+00:00`
- terminal state version: `670`

Two subsequent full startup reconciliations left the status, publication hash, publication timestamp, and state version unchanged, proving terminal reconciliation did not republish or mutate the canonical result.

## Validation

- Focused R4 suites: `116 passed in 22.83s`
- Full repository suite with isolated `--basetemp`: `1131 passed, 1 skipped in 175.88s`
- `python -m pip check`: `No broken requirements found.`
- `git diff --check`: passed

## Result

R4 acceptance passed. Durable monitored remote work is restart-safe for the tested protocol: authoritative remote ownership survives local worker and service loss, duplicate reconciliation does not relaunch work, cancellation is bound to exact process identity and process group, descendants are terminated, terminal evidence is durably published once, and repository locking is released only after canonical publication.