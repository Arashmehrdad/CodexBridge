# RELIABILITY-1 Operator Runbook

**Scope:** ordinary Soma operation, safe recovery, and restart activation.  
**Repository:** `D:/Github/Soma`  
**Safety rule:** never stop, restart, refresh, reconfigure, or mutate shared state while another project is using Soma. Never push without explicit owner instruction.

## 1. Before any service action

From `D:/Github/Soma`, establish a quiet boundary first:

```powershell
pwsh -NoProfile -File .\scripts\manage_soma_service.ps1 status
pwsh -NoProfile -File .\scripts\manage_soma_service.ps1 validate-config
```

The status command reports the verified process that owns the configured listening port as the primary PID and labels it `listener`. It also lists every related verified Soma PID used by the coordinated stop path. Use the listener PID for port and request-path correlation; preserve the full verified set when investigating process ownership.

Then use Soma's public checks:

1. `repo_query(status, repo_name="Soma")` — require the expected branch and understood worktree state.
2. `run_query(preflight, repo_name="Soma", include_stale=true)` — require no unexplained running, queued, launch-pending, or stale runs and no unexplained repository locks.
3. `system_query(capability_identity)` — distinguish `restart_required`, `connector_refresh_required`, and `operation_contract_repair_required`; do not substitute one action for another.
4. `system_query(self_check)` — require configuration, store, integrity, and reconciliation paths to be available or explicitly degraded with a reason.

If another project is actively using Soma, stop here and preserve the current process.

## 2. Start, stop, and restart

Use the identity-checking service controller rather than killing a PID manually:

```powershell
pwsh -NoProfile -File .\scripts\manage_soma_service.ps1 start
pwsh -NoProfile -File .\scripts\manage_soma_service.ps1 stop
pwsh -NoProfile -File .\scripts\manage_soma_service.ps1 restart
```

The tunnel is intentionally separate. Do not change it during an ordinary server restart unless the diagnosed action explicitly requires tunnel work.

After a restart:

1. wait for the service controller's readiness result;
2. run `system_query(capability_identity)` and require source/running build convergence;
3. run `system_query(self_check)` and inspect every startup reconciliation path and duration;
4. run `run_query(preflight, include_stale=true)` and require no unexplained active work or locks;
5. probe each newly activated public operation before relying on it;
6. refresh the ChatGPT connector only when capability identity says `connector_refresh_required` or a public schema is demonstrably stale.

A source/running build mismatch requires a Soma restart, not a connector refresh. A connector-only mismatch requires a connector refresh, not another server restart.

## 3. Logs and diagnostics

```powershell
pwsh -NoProfile -File .\scripts\manage_soma_service.ps1 diagnostics
pwsh -NoProfile -File .\scripts\manage_soma_service.ps1 logs -Tail 120
pwsh -NoProfile -File .\scripts\manage_soma_service.ps1 follow-logs
```

Preserve exact run, task, workflow, supervisor, project, repository, and request IDs in incident notes. Never replace an opaque identifier with a guessed name.

After `REL-021` activation, new Uvicorn default and HTTP access lines begin with a local ISO timestamp and UTC offset. Historical untimestamped access lines are not rewritten and cannot support exact wall-clock correlation. Cloudflared may label an ordinary client-aborted MCP stream as `ERR ... canceled by remote with error code 0`; do not infer a tunnel outage from that line alone. Compare its rate with adjacent minutes and require connection-loss, reconnect, registration, or HA-connection evidence before assigning the tunnel as the cause.

Managed server and tunnel stdout/stderr use stable active files. Before each managed start, the controller rolls over a stream only when it is already at or above 25 MB, retains the four newest timestamped archives for that stream, and prunes older archives. It never moves or truncates a file owned by an active service. `diagnostics` reports the configured threshold, retention count, and current size of every existing stream; an over-limit active file is left untouched and warned for rollover at the next managed start. `-MaxLogBytes` and `-MaxArchivedLogs` exist for bounded testing or explicit operator adjustment.

## 4. Repository changes

Use the bounded transaction sequence:

1. `repo_preview` with exact source hashes and anchored edits;
2. `repo_apply(..., commit_mode="manual")`;
3. inspect `repo_query(diff)` and `repo_query(status)`;
4. run focused tests with a repository-owned pytest temp directory, for example:

```powershell
.\.venv\Scripts\python.exe -m pytest -q --basetemp runs/reliability-1/pytest-<unique-id> <focused tests>
```

5. run `git diff --check` through an approved project command;
6. commit only the selected validated files;
7. verify the worktree is clean;
8. do not push.

After `REL-024` activation, `repo_commit` may return `status: repository_busy` with `retryable: true`, the verified owner lock/run, and a polling request. This is successful serialization, not a failed Soma service. Require `commit_attempted: false` and `repository_changed: false`, poll the supplied owner until terminal, confirm `run_query(preflight, include_stale=true)` shows no active lock, and retry the identical selected-file commit. Do not cancel or stop a healthy owning run solely to acquire the repository lock.

The repository-owned `--basetemp` avoids the observed Windows `%TEMP%\pytest-current` permission failure that can obscure the real pytest result.

## 5. Fresh-project onboarding

1. Discover or resolve the exact repository under an approved root.
2. If aliases collide, use the exact folder name; ambiguous normalized aliases must fail closed.
3. Call `memory_bind_repository` explicitly. Reads must not create ProjectScope authority silently.
4. Preserve the returned project ID, resource ID, project key, canonical repository name, root, scope generation, and exact `memory_scope`.
5. Repeat the bind and require the same identities with `binding_applied: false`.
6. Prove save/search/get and wrong-project isolation before treating onboarding as complete.
7. Use `memory_archive_repository` only after confirming zero task/run scope history and the exact current generation.

## 6. Task and run recovery

1. Read the canonical task first, then its durable backend observation.
2. Treat replay as replay: it must not imply a new launch attempt.
3. Do not infer backend existence from a reserved backend reference string.
4. Use compare-and-swap state versions for cancellation and recovery actions.
5. Before terminal publication or cancellation closure, require owned launcher, worker, and child process-tree absence where the lifecycle contract demands it.
6. If ownership is uncertain, keep the task/run in an explicit recovery state; never fabricate a backend run, result, or evidence reference.
7. Retrieve exact events and terminal evidence before resolving or superseding recovery.

## 7. Evidence retrieval

For a durable run, use:

- `run_query(control)` or `run_query(status)` for lifecycle and ownership;
- `run_query(events)` for the immutable event sequence;
- `run_query(output)` for bounded stdout/stderr evidence;
- `run_query(terminal)` for the public terminal projection;
- the authoritative result/evidence operation referenced by the terminal projection when exact bytes are required.

Top-level query success is separate from run business outcome. A healthy query may report a failed, cancelled, blocked, or pending run.

After `REL-020` activation, an exact pre-database Codex run ID may be served from its preserved filesystem evidence with `legacy_filesystem_only: true` and `database_record_present: false`. This compatibility path is exact-read only: it does not import rows, participate in run listing or reconciliation, expose an event stream, permit cancellation, or re-enable legacy execution. Incomplete, malformed, conflicting, oversized, symlinked, or nonlegacy directories continue to fail closed.

## 8. Storage and integrity

Use read-only SQLite diagnostics while Soma is live. The minimum checks are:

- `PRAGMA integrity_check` returns `ok`;
- `PRAGMA foreign_key_check` returns zero rows;
- journal mode is `wal`;
- no unexplained recoverable runs or operation locks remain after test work;
- terminal publication metadata is complete or explicitly queued for restart repair.

Do not edit `runs/soma.sqlite3` manually. Repair through the owning store/publication path so state version, projection source hash, events, and artifacts remain coherent.

Startup now selects incomplete terminal publication identities in SQL and performs a full artifact check only for the newest 100 terminal runs. A comprehensive historical artifact audit is an explicit maintenance action, not part of the availability-critical startup path.

Canonical-memory catalog rebuild and semantic-provider index rebuild are different operations. The canonical catalog can be reconstructed from Markdown and must preserve identity, hashes, drift reporting, malformed-content exclusion, and tool-owned-path exclusion. `memory_rebuild_index` concerns the optional semantic provider; when semantic retrieval is disabled or provider coverage cannot be proven, it must refuse before launching work. Do not treat that refusal as canonical-memory unavailability, and do not repeatedly retry it.

## 9. Current restart activation checklist

The source sequence has already passed against an isolated backup of the live store; see [`RELIABILITY_1_ISOLATED_PRE_RESTART_REHEARSAL_2026-08-01.md`](RELIABILITY_1_ISOLATED_PRE_RESTART_REHEARSAL_2026-08-01.md). That rehearsal predicts the historical outcomes and proves idempotency, but it does not replace live activation.

The activation-batch checklist is:

1. `REL-012` ambiguous repository aliases fail closed live;
2. `REL-013` repository archival is visible through the refreshed connector and disposable bindings can be archived/deleted safely;
3. `REL-014` discovered folder aliases apply through one canonical repository identity;
4. `REL-015` stale managed-artifact conflicts classify as validation/safety failures rather than infrastructure failures;
5. `REL-016` missing-backend task replay reports no accepted launch;
6. `REL-017` historical supervisors reconcile and readiness records the supervisor path;
7. `REL-018` the five currently pending Hermes terminal results are repaired, and new shared-service runs publish immediately;
8. `REL-019` `job_runs` startup reconciliation completes near the measured bounded path rather than the prior 46–101 second range;
9. `REL-020` an actual filesystem-only Codex run is readable through exact status/input/output/result/terminal operations with no SQLite insertion, while the four empty directories remain unavailable;
10. `REL-021` new Uvicorn default and access log lines carry an ISO timestamp with UTC offset, while stdio operation remains unchanged;
11. `REL-024` a selected-file commit attempted during a disposable repository-owned run returns structured retryable `repository_busy` ownership and polling metadata, then succeeds only after the owner is terminal and preflight is lock-free;
12. capability identity converges, self-check passes, preflight is quiet, and the worktree remains clean.

**Activation result on 2026-08-01:** items 6–12 passed after the owner-approved restart and connector refresh. Historical supervisors reconciled, all five pending Hermes results published, `job_runs` startup reconciliation completed in 1.281 seconds, the filesystem-only Codex probe succeeded, timestamped access lines were observed, the structured repository-busy refusal passed under a controlled healthy lock, capability identity converged, all ten self-check paths passed, and preflight returned to zero locks. The live controller also reported the `REL-023` rollover threshold, archive count, and all four current stream sizes. Items 1–5 remain targeted disposable scenario probes and must not be claimed complete from build convergence alone.

Do not perform a future activation while shared users are active.
