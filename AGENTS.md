# CodexBridge Agent Instructions

## Project Purpose

CodexBridge is evolving from a ChatGPT-to-Codex bridge into a local engineering control plane.

Target operating model:
- ChatGPT decides strategy and normal engineering actions.
- CodexBridge MCP receives requests.
- The local agent handles cheap, repetitive, operational, and long-running work.
- Codex CLI is reserved for real coding/editing tasks.
- PulseSender, when integrated later, returns completed reports back to the ChatGPT conversation.
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
- Do not auto-commit.
- Do not push.
- Use PowerShell snippets in docs.

## Local Agent Direction

The local agent should eventually handle:
- repo inspection
- task classification
- command/test running through allowlisted profiles
- audit events
- structured run artifacts
- local model summaries
- Codex escalation packets
- project memory
- long-running jobs
- supervisor recovery
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

Codex should be used for:
- source code edits
- bug fixes
- creating modules
- refactors
- fixing failing tests after local diagnosis
- architecture-sensitive changes
- multi-file implementation work
- durable workflow orchestration when a complete multi-step sequence is already known

When a full multi-step sequence is already known, prefer starting one durable workflow instead of manually chaining child runs from ChatGPT turn by turn. Never start duplicate child runs for the same durable workflow state, and do not emit repetitive "still running" monitoring turns when the workflow worker can advance internally.

Before a future Codex escalation, the local agent should prepare a compact packet containing:
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
- starting and monitoring long-running local jobs

Never expose secrets in logs, prompts, summaries, or run artifacts.

## Command Execution Rules

Future command execution must:
- use allowlisted command profiles
- use argv lists, not shell strings
- run with `shell=False`
- reject arbitrary user-provided shell commands
- reject unknown command IDs
- capture stdout, stderr, exit code, duration, timeout status, working directory, command profile ID, and audit event ID
- write structured run artifacts under `runs/`
- enforce timeouts
- avoid write-capable behavior by default

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

If a batch cannot run one of these, report why.

All new behavior should include tests. Tests should prefer fakes/monkeypatching for subprocess, HTTP, model calls, browser calls, and long-running jobs. Prefer tests before claiming success.

## Artifact and Audit Expectations

Future local-agent work should prefer structured outputs:
- result JSON
- stdout/stderr files where relevant
- audit event IDs
- `created_at` timestamps
- run IDs
- stable status fields

Avoid relying only on human-readable logs.

## Roadmap Order

This list is directional, not proof that a feature exists:

1. Local Agent Core
2. Universal Tool Runner
3. Local Model Adapter
4. Codex Escalation Router
5. Project Memory Store
6. Autonomy Policy Engine
7. Supervisor Upgrade
8. Long-Run Job Manager
9. Workflow Orchestrator
10. PulseSender Return Loop
11. Optional Local Coding
12. Minimal Dashboard

## Reporting Format

At the end of each Codex task, report:
- files changed
- behavior added
- tests added
- validation commands and results
- assumptions
- known limitations
- recommended next batch

## Maintenance Rule

When the user corrects a recurring project rule, update `AGENTS.md` so future Codex sessions inherit the correction.
