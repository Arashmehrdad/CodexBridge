# CodexBridge Agent Instructions

## Project Purpose

CodexBridge is evolving from a ChatGPT-to-Codex bridge into a local engineering control plane.

Target operating model:
- ChatGPT decides strategy and normal engineering actions.
- CodexBridge MCP receives requests and owns durable execution state.
- The local agent handles cheap, repetitive, operational, and long-running work.
- Codex CLI is reserved for real coding/editing tasks.
- PulseSender remains separate and returns prepared reports to the ChatGPT conversation.
- The human only approves genuinely risky boundaries.

Future Codex sessions must inspect the repository before assuming any roadmap feature exists.

## Current Development Discipline

- Work in small milestone batches only.
- Never implement the whole roadmap in one pass.
- Implement only the batch explicitly requested by the user.
- Do not skip ahead to later milestones.
- Use minimal, focused edits.
- Do not introduce broad refactors unless the user explicitly asks.
- Preserve existing MCP behavior unless the batch specifically requires a change.
- Keep read-only tools and write tools separate.
- Prefer minimal, tested, extensible implementations.
- Existing tests must continue to pass.
- Do not touch unrelated dirty files.
- Commit completed repository work locally.
- Never push unless the user explicitly asks.
- Never reset, clean, discard, amend, rebase, or rewrite existing work/history.
- Use PowerShell snippets in docs.

## Immediate Priority: Durable Execution Recovery

Feature expansion is paused behind the durable-execution gate in `PLANS.md`.

The current execution layer has persistence, but accepted work is not yet fully safe across process crashes, service restarts, launcher PID mismatches, or partial child-launch transitions. Until the gate is complete, do not describe workflows, supervisors, or long-running jobs as production-safe or fully restart-safe.

Required execution invariants:

1. **Persist before launch**
   - Record the normalized request, stable run ID, launch intent, repository identity, policy decision, and ownership token before starting a worker or child process.
   - If process creation fails, transition the record to a terminal infrastructure failure and release only the lock owned by that failed launch.

2. **Canonical process identity**
   - The executing worker must register its real PID in the canonical database field.
   - Persist a process-start identity or lease token in addition to the PID so PID reuse cannot make an unrelated process appear valid.
   - Do not treat a launcher, wrapper, or stale Popen PID as the authoritative worker without verification.

3. **Process-aware restart reconciliation**
   - Reconcile `queued`, `launch_pending`, `running`, and `cancellation_pending` records.
   - Do not mark a run failed merely because the MCP server restarted.
   - Adopt a verifiably active worker, relaunch an idempotently claimable queued run, or move the run to a conservative recovery state when identity is uncertain.

4. **Conservative lock release**
   - Never release a repository lock solely because a database status was changed to terminal during startup.
   - Release only after verified worker/child exit, successful ownership transfer, or an explicit terminal transition performed by the current lease owner.
   - Retain the lock when remote or local execution may still be active.

5. **Idempotent launch and attachment**
   - Workflow and supervisor child launches require a durable launch-intent/checkpoint before process creation.
   - Persist child attachment with an idempotency key so a crash cannot create an orphan child followed by a duplicate child.
   - A `running` step with no child ID must have a deterministic recovery path; it must never spin forever.

6. **Conditional state transitions**
   - Use compare-and-swap or versioned updates for ownership-sensitive transitions.
   - Completion, cancellation, timeout, restart recovery, and worker adoption must not overwrite one another unconditionally.

7. **Single authoritative repository lock system**
   - Do not add a third lock implementation.
   - Migrate supervisor/workflow write ownership toward the same durable lock and lease model used by direct runs.

8. **Durable result and event consistency**
   - Database terminal state and structured result must become visible atomically.
   - Human-readable artifacts should use atomic replacement and must not be treated as the sole source of truth.
   - Startup reconciliation failures must produce durable events; never silently swallow them.

9. **Legacy job containment**
   - `LongRunJobManager` is not a production execution path and is disabled by default.
   - Its in-memory execution mode is compatibility/test-only and requires explicit `allow_legacy_execution=True` opt-in.
   - Recreated managers must move unowned nonterminal legacy jobs to `needs_input`; never report them as ordinarily running or falsely cancelled.
   - Route every new unattended workload through the durable `JobManager`/`RunStore` lease and reconciliation path.

10. **Opaque identifier preservation**
   - Parsers may match command prefixes case-insensitively, but must preserve run, job, workflow, supervisor, host, and profile identifiers exactly as supplied.
   - Never lowercase an opaque identifier before process ownership, lock, database, or artifact lookup.

## Required Crash-Window Tests

Durability changes must add tests for the exact failure boundaries they close. At minimum cover:

- server restart while a detached worker remains active
- worker death while a child process remains active
- process-launch failure after durable run creation
- worker death before changing `queued` to `running`
- workflow crash after step claim but before child launch
- workflow crash after child launch but before child-ID attachment
- concurrent startup reconcilers attempting the same workflow/run
- cancellation racing with normal completion
- supervisor crash after plan or implementation child launch
- PID reuse or mismatched launcher/worker PID
- recreation of the legacy long-job manager while work is active
- regeneration of a previously delivered return-loop manifest

Prefer deterministic fakes for most cases, plus at least one Windows subprocess integration test for real PID/lease behavior.

## Local Agent Direction

The local agent should handle:
- repo inspection
- task classification
- command/test running through allowlisted profiles
- audit events
- structured run artifacts
- local model summaries
- Codex escalation packets
- project memory
- durable long-running jobs after the durability gate passes
- supervisor/workflow recovery after the durability gate passes
- report/resume prompt generation

The local agent must not perform risky writes, commits, pushes, deployments, or secret handling without the policy layer and proper approval.

## Codex Routing Rules

Codex should usually not be used for:
- inspecting files
- listing tests
- running tests
- running pip check
- checking git status
- summarising logs
- explaining failures
- preparing plans
- monitoring long-running jobs
- orchestrating already-defined workflow state transitions

Codex should be used for:
- source code edits
- bug fixes
- creating modules
- refactors
- fixing failing tests after local diagnosis
- architecture-sensitive changes
- multi-file implementation work

When a full multi-step sequence is already known, use one durable workflow only after its launch/lease/recovery invariants are satisfied. Never start duplicate child runs for the same durable state, and do not emit repetitive monitoring turns when the worker can safely advance internally.

Before a Codex escalation, the local agent should prepare a compact packet containing:
- objective
- relevant files
- current error or task context
- tests already run
- constraints
- allowed files
- expected output

## Safety and Autonomy Policy

Permission tiers:
- T0 - read only
- T1 - safe local test
- T2 - long-running non-destructive job
- T3 - write preview / dry run
- T4 - write apply under ChatGPT-delegated approval
- T5 - commit / private branch push under ChatGPT-delegated approval
- T6 - human-only risky action

Human approval is required for:
- secrets or credentials
- deleting files outside the project
- system-level deletion
- destructive filesystem actions
- Docker prune, volume deletion, destructive cleanup, or heavy training
- real-money actions
- changing real production infrastructure
- publishing sensitive data
- granting new external access permissions
- pushing to main/master
- release tags
- public repo pushes
- deployment branch pushes
- ChatGPT connector UI approvals that cannot be automated

ChatGPT-delegated approval may cover normal engineering actions inside whitelisted repositories, such as:
- running tests
- running self-checks
- inspecting git status
- inspecting diffs
- creating branches
- staging selected files
- committing selected files
- pushing private personal feature branches
- installing ordinary dev packages
- running documented project commands
- updating non-secret config files
- starting and monitoring long-running local jobs only when the execution layer satisfies the durable-execution gate

Never expose secrets in logs, prompts, summaries, or run artifacts.

## Command Execution Rules

Command execution must:
- use allowlisted command profiles
- use argv lists, not shell strings
- run with `shell=False`
- reject arbitrary user-provided shell commands
- reject unknown command IDs
- capture stdout, stderr, exit code, duration, timeout status, working directory, command profile ID, and audit event ID
- write structured run artifacts under `runs/`
- enforce timeouts
- avoid write-capable behavior by default
- record canonical worker/child identity and lease ownership for durable runs
- pass Codex prompts through a UTF-8 file-backed stdin stream; never launch `codex exec -` without attaching that stream
- use the connector-isolated Codex child environment for both synchronous and durable workers
- keep full prompts out of command-line arguments and preserve multiline content exactly

Current expected command profiles:
- `pytest`: `python -m pytest -q`
- `pip_check`: `python -m pip check`
- `git_status`: `git status --short`

## Testing and Validation

For normal implementation batches, run:

```powershell
python -m pytest -q
python -m pip check
```

For durability batches, also run targeted restart, cancellation, lock, workflow, supervisor, and process-control tests. If a validation command cannot run, report why.

All new behavior should include tests. Tests should prefer fakes/monkeypatching for subprocess, HTTP, model calls, browser calls, and long-running jobs, but process identity and restart adoption require at least one real subprocess integration path. Prefer tests before claiming success.

## Artifact and Audit Expectations

Local-agent work should prefer structured outputs:
- result JSON
- stdout/stderr files where relevant
- audit event IDs
- `created_at`, `started_at`, heartbeat, and terminal timestamps
- stable run IDs
- lease/ownership IDs
- stable status and classification fields
- explicit recovery decisions and reasons

Avoid relying only on human-readable logs.

## Roadmap Order

This list is directional, not proof that a feature exists:

0. Durable Execution Recovery and Ownership Gate
1. Local Agent Core
2. Universal Tool Runner
3. Local Model Adapter
4. Codex Escalation Router
5. Project Memory Store
6. Autonomy Policy Engine
7. Supervisor Upgrade
8. Unified Durable Job Manager
9. Workflow Orchestrator Hardening
10. PulseSender Return Loop Hardening
11. Optional Local Coding
12. Minimal Dashboard
13. Optional ChatGPT-native live status component

Do not begin roadmap items 11-13 until item 0 is complete and validated.

## Reporting Format

At the end of each Codex task, report:
- files changed
- behavior added
- tests added
- validation commands and results
- durability invariants affected
- assumptions
- known limitations
- recommended next batch

## Documentation-Only Validation Rule

For prose-only changes such as `PLANS.md`, `AGENTS.md`, README files, roadmap/status notes, and other documentation that does not directly drive generated or runtime behavior:

- Never run the full test suite, `pip check`, or any other long-running validation unless Arash explicitly requests it.
- Use only proportionate checks: review the scoped diff, run `git diff --check`, verify that only the intended documentation files changed, commit those files, and confirm a clean worktree.
- Prefer the fastest sufficient validation and do not spend minutes validating an ordinary documentation edit.

## Maintenance Rule

When the user corrects a recurring project rule, update `AGENTS.md` so future Codex sessions inherit the correction.
