# CodexBridge Roadmap Status

## Completed Foundations

- Repository-scoped MCP read/write controls with capability metadata.
- Durable async child runs through `JobManager` and `RunStore`.
- Supervisor recovery flow with return-loop report artifacts.
- Read-only local dashboard for runs, jobs, supervisors, approvals, escalations, and return-loop state.

## Current Batch: Durable Workflow Orchestrator

Status: implemented in this batch.

Scope delivered:

- Durable workflow models, validation, SQLite-backed persistence, manager, worker, and reporter under `codexbridge/workflows/`.
- Structured workflow steps for `codex_implement`, `project_command`, `pytest_path`, `git_readonly`, and `local_summary`.
- Detached workflow worker execution with restart reconciliation and active-child cancellation handling.
- Workflow result snapshots, event logs, resume/report artifacts, PulseSender manifest discovery, MCP tools, and read-only dashboard visibility.

## Acceptance Criteria

- Validate the full workflow graph before launch:
  - reject duplicate step IDs
  - reject unknown step types
  - reject malformed parameters
  - reject missing dependencies
  - reject dependency cycles / invalid forward dependencies
  - reject excessive step counts
- Persist workflow and step state durably in SQLite plus `runs/workflows/<workflow_id>/result.json` and `events.jsonl`.
- Advance eligible child runs internally without ChatGPT polling each child run.
- Generate `workflow_report.md`, `resume_prompt.txt`, and `pulse_manifest.json` when the workflow reaches a terminal/reportable state.
- Expose MCP tools:
  - `start_workflow`
  - `get_workflow_status`
  - `get_workflow_events`
  - `get_workflow_result`
  - `cancel_workflow`
- Show workflow state in the local dashboard without adding write routes or browser/PulseSender imports.

## Implementation Notes

- The dashboard task box implemented here is the existing local read-only dashboard surface.
- This is not the later native ChatGPT Apps SDK live-status component.
- Workflow reporting reuses the return-loop manifest contract so external PulseSender can discover workflow artifacts alongside jobs and supervisors.
- Workflow workers launch child runs through existing `JobManager` APIs and keep advancement inside the worker loop.

## Validation Evidence

- Targeted workflow/server/dashboard/return-loop tests: pending final run result.
- Full repository pytest: pending final run result.
- `pip check`: pending final run result.

## Known Limitations

- Supported workflow step types are intentionally limited to the approved batch.
- The read-only dashboard shows workflow state from durable artifacts; it does not provide workflow mutation.
- The local dashboard workflow section is a local operator surface, not the future ChatGPT-native live component.

## Next Batch

- Optional ChatGPT Apps SDK live status component for native workflow visibility.
- Keep it distinct from the already-implemented local dashboard task box.
