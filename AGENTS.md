# Soma Agent Instructions

## Project Purpose

Soma is a local engineering control plane. The production runtime does not yet launch or supervise coding-agent sessions. `V3-1A — INTERACTIVE-WORKER-SUBSTRATE-1` is the active implementation lane that may add one bounded provider-native interactive worker path beneath the existing canonical Task → Run authority.

Target operating model:
- ChatGPT/Cortana decides strategy, creates bounded work packages, reviews results, and resolves normal engineering decisions.
- Soma MCP receives requests and owns durable project, task, run, evidence, recovery, and later outcome-acceptance state.
- Provider-native coding workers are short-lived, interactive, replaceable execution sessions; they never become a second task, plan, result, or recovery authority.
- Until V3-1A is implemented and accepted, real coding/editing tasks continue through manual external-coder handoff.
- V3-1A workers receive no direct Soma MCP access. A later role-scoped positive-allowlist broker is required before worker tool access.
- PulseSender remains separate and returns prepared reports to the ChatGPT conversation.
- The human only approves genuinely risky boundaries.

Future coding-agent sessions must inspect the repository before assuming any roadmap feature exists.

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

## Immediate Priority: V3-1A Interactive Worker Substrate

CF1 and the Pre-Roadmap V3 bridge are complete. `PLANS.md` is the sole concise source of active plan truth. The autonomous-company architecture, Claude red-team, Codex repository feasibility audit, owner reconciliation, and final consistency audit are complete.

Only `V3-1A — INTERACTIVE-WORKER-SUBSTRATE-1` is active. It must extend the existing canonical Task → Run authority with one bounded provider-native interactive worker path. It may add subordinate session bindings, interaction delivery records, checkpoints, provider-child identity, and raw usage evidence. It may not create a second worker lifecycle manager, expose the current broad Soma MCP surface to workers, implement the Company Kernel, create departments, enable scheduled autonomy, or add generic external mutations.

`V3-1A-FOUNDATION-1`, `V3-1A-ADAPTER-CONTRACT-1`, and the complete `V3-1A-PROCESS-IDENTITY-1` corrective chain are accepted and closed after independent audits. The accepted process boundary forbids raw-PID ownership inference, distinguishes root exit from owned-tree absence, retains ownership on uncertainty, requires zero-descendant proof before terminal publication, and preserves `KILL_ON_JOB_CLOSE`, environment, publication, cancellation-ordering, and public-projection protections. The active bounded subgate is `V3-1A-INTERACTION-COMMANDS-1`: canonical `STEER` and `SUPPLY_INPUT` task commands, persisted-before-send interaction evidence, genuinely non-terminal `AWAITING_CONTROLLER`, exact checkpoint/session identity, bounded deadlines, cancellation-wins race handling, and fail-closed delivery uncertainty through deterministic stand-in transport only. It may not launch Claude Code or Codex, use provider accounts, send live provider prompts or streams, expose Soma MCP to workers, begin V3-1B, or activate production behavior.

The lane uses progressive lifecycle convergence:

1. task admission, running, waiting, cancellation, recovery, and result publication remain canonical Task → Run responsibilities;
2. provider-native session IDs and protocol cursors remain subordinate binding facts, not lifecycle authority;
3. workflows and supervisors are legacy generic lifecycle managers, not business domains; V3 must project or retire their overlapping generic responsibilities when later lanes touch them;
4. SSH activation, Trading Lab, memory, research, and future business systems retain irreducible domain facts while work execution converges on canonical tasks and runs;
5. every compatibility bridge must name its canonical side, retirement condition, and owning future lane;
6. the lane must close with no unexplained increase in canonical authority.

Do not implement V3-1B, the capability broker, collaboration, temporary organisations, dashboard product work, provider subscriptions, or unrelated cleanup until V3-1A is accepted and `PLANS.md` explicitly advances the sequence.

Remote PowerShell remains available for registered hosts that already provide `pwsh` or `powershell`. Soma does not require installing or staging PowerShell on Linux hosts merely to satisfy acceptance.

Local `JobManager`/`RunStore` execution and R4 monitored remote SSH execution may be described as restart-safe where their acceptance tests apply. New remote execution surfaces must reuse the authoritative controller, reattachment, identity-scoped cancellation, and exactly-once publication protocol rather than creating parallel ownership models.

The following execution invariants are permanent requirements for every new local or remote execution path:

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
- external-coder handoff generation (manual use only; nothing is invoked)
- project memory
- durable local long-running jobs through `JobManager`/`RunStore`
- supervisor/workflow recovery through the shared durable lifecycle
- remote transfer and controller work only after the relevant R3/R4 invariants are implemented
- report/resume prompt generation

The local agent must not perform risky writes, commits, pushes, deployments, or secret handling without the policy layer and proper approval.

## External-Coder Handoff Rules

The accepted production runtime does not yet execute a coding agent. Manual external-coder handoff remains the incumbent path while V3-1A is under construction. The unfinished V3-1A path must never be used for production repository work or treated as accepted merely because a provider process can be launched. An external-coder handoff should usually not be generated for:
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

An external-coder handoff should be generated for:
- source code edits
- bug fixes
- creating modules
- refactors
- fixing failing tests after local diagnosis
- architecture-sensitive changes
- multi-file implementation work

When a full multi-step sequence is already known, use one durable workflow only after its launch/lease/recovery invariants are satisfied. Never start duplicate child runs for the same durable state, and do not emit repetitive monitoring turns when the worker can safely advance internally.

The generated handoff is a bounded packet containing:
- objective
- current branch, HEAD, and worktree state
- relevant files
- exact evidence and failures
- approved scope (allowed/forbidden files)
- constraints and repository safety rules
- tests and validation commands
- the expected completion report

The user supplies it manually to the coding agent of their choice; Soma records the artifact and parks in `needs_external_coder`.

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

0. V3-0 Architecture reconciliation — complete
1. V3-1A Interactive Worker Substrate — active
2. V3-1B Kernel of One — planned, inactive
3. V3-2 Role-Scoped Capability Broker — planned, inactive
4. Interactive collaboration and temporary organisation — planned, inactive
5. Cortana/dashboard, business bindings, autonomous company trial, and genuine learning — later outcomes

Only V3-1A is active. Do not implement or validate later roadmap outcomes until V3-1A passes its session identity, interaction delivery, non-terminal waiting, explicit recovery, zero-orphan cancellation, raw usage, protocol-drift, compatibility, and authority-delta gates and the owner explicitly advances the plan.

## Roadmap Documentation Discipline

- `PLANS.md` is the concise active decision and execution-order document.
- Completed narratives, commit lists, test counts, and checkpoints belong in `docs/roadmap-v2-achievements.md` or a later achievement record.
- Pilot observations belong in a separate evidence log, not chronologically in `PLANS.md`.
- When a milestone completes, leave only its outcome and still-relevant invariants in `PLANS.md`, then preserve detailed evidence in the achievement record.
- Do not delete historical evidence merely to shorten the active roadmap.

## Reporting Format

At the end of each coding-agent task, report:
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

When the user corrects a recurring project rule, update `AGENTS.md` so future coding-agent sessions inherit the correction.
