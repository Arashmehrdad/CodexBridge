# Soma Agent Instructions

## Project Purpose

Soma is a local engineering control plane and the future durable organisation around intelligent agents. The current accepted runtime also includes durable semantic continuation/re-entry and a portable Skill layer; these remain mechanical support for the connected controller rather than a second semantic planner. The Autonomous Company roadmap is frozen. `PLANS.md` is the sole concise source of current lane activation truth.

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

## Architectural Conformance Gate

Owner-approved architecture, explicit owner constraints, and accepted architecture/acceptance records are hard implementation requirements, not advisory context.

For every implementation batch:
- Identify the exact architectural seam being changed and preserve all surrounding accepted boundaries.
- Treat passing unit/integration tests as necessary but not sufficient; acceptance also requires proving that the resulting runtime architecture still matches the owner-approved design.
- Do not convert a temporary test, conformance, migration, benchmark, or debugging dependency into a normal runtime dependency unless the owner explicitly authorizes that architectural change.
- Do not let implementation convenience, an already-running service, or an available dependency silently redefine the accepted operating model.
- When a roadmap item can be implemented in multiple ways, choose only an approach consistent with existing owner constraints and accepted architecture records. If those sources conflict or the compliant path is unclear, stop and surface the conflict before implementation.
- Cross-cutting runtime, storage, lifecycle, dependency, authority, or serving changes require an explicit before/after architecture check covering component ownership, persistent dependencies, startup/restart behavior, failure/rollback behavior, and which subsystem is authoritative.
- A batch that starts requiring unrelated architectural changes must be split or re-authorized rather than expanded opportunistically.
- After the owner corrects a recurring architectural or operational rule, update `AGENTS.md` in the same workstream before continuing implementation so later sessions cannot lose the correction.
- Never declare a roadmap or acceptance milestone closed while a known implementation detail contradicts an accepted owner boundary, even if its functional tests pass.

### Docker Runtime Boundary

- Docker Desktop and Docker containers are disposable conformance/test infrastructure for Soma unless the owner explicitly authorizes a different use.
- Normal Soma operation must remain functional with Docker Desktop stopped.
- No normal Soma or Research Map runtime path may acquire Docker as a persistent service, storage, startup, or availability dependency without explicit owner authorization and a dedicated architecture acceptance step.
- Research Map conformance may use a pinned disposable FalkorDB container, but that container must not become the accepted normal backend merely because it is already available.
- Conformance work that starts Docker must tear down its disposable containers and leave Docker stopped when the proof is complete, unless another explicitly authorized task still owns Docker.
- Docker-specific cleanup, prune, volume deletion, and other destructive operations remain subject to the Safety and Autonomy Policy below.

## Current Plan Authority

`PLANS.md` is the sole concise source of active plan truth. No Company package is currently activated. The semantic-continuation + portable-Skill programme is completed/accepted; Patch Auto-Repair remains the next intended lane but still requires its own owner opening instruction. Historical V3/Agent-Worker material below remains compatibility and architecture history, not permission to resume a frozen lane.

The preserved `V3-1A-INTERACTION-FOUNDATION-ARCH-REVIEW-1` package is parked until RELIABILITY-1 closes. Repository editing now supports corrected handoff states, anchored line ranges, hash-bound whole-file replacement, explicit manual commit mode, exact pending-file reporting, and commit metadata for creation and reversal paths. Markdown section intelligence, typed operation unions, scratch branches, and broader editing ergonomics remain future work unless a reproduced reliability defect makes one necessary.

`V3-1A-FOUNDATION-1`, `V3-1A-ADAPTER-CONTRACT-1`, and the complete `V3-1A-PROCESS-IDENTITY-1` corrective chain are accepted and closed after independent audits. The accepted process boundary forbids raw-PID ownership inference, distinguishes root exit from owned-tree absence, retains ownership on uncertainty, requires zero-descendant proof before terminal publication, and preserves `KILL_ON_JOB_CLOSE`, environment, publication, cancellation-ordering, and public-projection protections. The historical bounded subgate was `V3-1A-INTERACTION-COMMANDS-1`: canonical `STEER` and `SUPPLY_INPUT` task commands, persisted-before-send interaction evidence, genuinely non-terminal `AWAITING_CONTROLLER`, exact checkpoint/session identity, bounded deadlines, cancellation-wins race handling, and fail-closed delivery uncertainty through deterministic stand-in transport only. It may not launch Claude Code or Codex, use provider accounts, send live provider prompts or streams, expose Soma MCP to workers, begin V3-1B, or activate production behavior.

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

11. **Machine-global CUDA arbitration**
   - Every local Soma-launched workload that can initialize or execute CUDA must use `run_start(operation="powershell", resource_class="cuda_exclusive", ...)`.
   - Checking `nvidia-smi`, GPU utilization, free VRAM, or `torch.cuda.is_available()` is diagnostic only and never grants launch permission.
   - The CUDA reservation must be acquired before the child process is spawned and held until the canonical CUDA child is terminal or safely contained. CUDA commands must not detach GPU subprocesses outside canonical Run ownership.
   - Unrelated repositories and Chats share the same FIFO CUDA queue; do not create per-repository GPU locks or bypass the queue because the device appears idle.
   - Queue leases require heartbeat, worker process identity, stale/dead-owner recovery, cancellation-safe release, and a short post-release cooldown before the next grant.
   - Default GPU jobs are exclusive. Shared/VRAM-packed GPU scheduling requires a separately accepted design and must not be inferred automatically.

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

## Legacy Local Agent Direction - Inactive Routing Path

This section describes retained legacy/source-history behavior. It is not the current public semantic-routing architecture and must not be used to resurrect objective classification or automatic next-action selection. The connected controller remains the semantic decision maker.

The legacy local agent was designed to handle:
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

Soma uses **tiered validation by default**. The full pytest suite is not the normal inner-loop validation command for ordinary fixes or small implementation batches.

1. **Tier 0 — smoke / exact reproduction**
   - Run the exact failing test or smallest deterministic reproduction first.
   - Use fast import/config/contract checks when they directly cover the changed surface.

2. **Tier 1 — touched subsystem**
   - Run the test file(s), marker(s), or narrowly related subsystem tests that own the changed behavior.
   - Use `python -m pytest -n 12 -q ...` by default whenever those tests are safe under xdist.
   - If a specific test genuinely requires serialization, serialize only that test or smallest necessary scope; do not drop the project-wide 12-worker default.

3. **Tier 2 — related integration slice**
   - For durability, lifecycle, gateway, storage, or cross-module changes, run the directly related integration/acceptance slice after Tier 1.
   - Examples include the relevant restart, cancellation, lock, workflow, supervisor, process-control, Research Map, or service tests.
   - Run `python -m pip check` and the relevant Ruff/static checks before commit.

4. **Tier 3 — full suite**
   - `python -m pytest -n 12 -q` is reserved for explicit full-suite stabilization, release/release-candidate validation, major cross-cutting core changes, or when the user specifically asks for it.
   - Do **not** automatically run the full suite after an ordinary bug fix merely because the targeted and related integration gates passed.
   - A failure discovered only by a Tier 3 run must be classified separately; do not silently expand the current fix into unrelated cleanup.

Default normal-fix sequence:

```text
exact failing test
→ touched subsystem tests (-n 12 when compatible)
→ related integration slice when warranted
→ pip check + relevant Ruff/static checks
→ commit
```

For durability batches, include the exact crash/restart/lease boundary being changed in the targeted or related integration slice. If a validation command cannot run, report why.

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
1. V3-1A Interactive Worker Substrate — accepted and closed
2. V3-1B Kernel of One — active; schema and Agent/Worker mechanics accepted, product authority closure in progress
3. V3-2 Role-Scoped Capability Broker — planned, inactive
4. Interactive collaboration and temporary organisation — planned, inactive
5. Cortana/dashboard, business bindings, autonomous company trial, and genuine learning — later outcomes

Only the exact V3-1B package named by `PLANS.md` may change product behavior. Do not skip into V3-2 or later outcomes.

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

Current owner-specific hard boundaries:
- Any Codex CLI, App Server, API, model generation, or Codex subagent usage requires a fresh explicit owner request. Never infer authorization from roadmap work.
- `docs/CANONICAL_PROJECT_MEMORY_CONTRACT.md` is owner work and must not be modified, staged, deleted, renamed, or committed without explicit future authorization.
- Preserve unrelated concurrent owner files and never include them in a roadmap commit.
