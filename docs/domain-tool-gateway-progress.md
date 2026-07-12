# Domain tool gateway migration progress

## Phase 0 — migration harness and schema inventory (`complete`)

- Files changed so far: `codexbridge/gateway_models.py`, `tests/test_tool_gateway_models.py`, this journal.
- Public actions: 80. Public names introduced/retired: none.
- Gateway operations added: strict Phase-1 SSH request contracts only; runtime dispatch unchanged.
- Focused tests: `tests/test_mcp_action_discovery.py tests/test_tool_gateway_models.py` — 32 passed.
- Full validation: 807 passed, 1 skipped; `pip check` passed; `git diff --check` passed.
- Known limitation: pytest emits an existing `.pytest_cache` access warning; test execution is otherwise successful via the local base directory.
- Next phase: Phase 1 — SSH read-only inspection consolidation.

## Phase 1 — SSH read-only inspection consolidation (`complete`)

- Files changed so far: `codexbridge/gateway_models.py`, `codexbridge/server.py`, discovery/server/model tests, and this journal.
- Public actions: 78. Added/extended: `ssh_inspect`. Retired: `ssh_environment_probe` → `ssh_inspect.environment_probe`; `ssh_gpu_telemetry` → `ssh_inspect.gpu_telemetry`.
- Gateway dispatch: existing `_ssh_host_health`, `_run_ssh_environment_probe`, `_run_ssh_gpu_telemetry`, and `_run_ssh_inspection` remain unchanged.
- Focused tests: SSH, server, discovery, and gateway models — 73 passed.
- Full validation: 808 passed, 1 skipped; `pip check` and `git diff --check` passed.
- Next phase: Phase 2 — run query consolidation and event cursor.

## Phase 2 — run query consolidation and `after_id` (`complete`)

- Files changed so far: Phase 1 files plus `codexbridge/run_store.py`, `codexbridge/job_manager.py`, and `tests/test_run_store.py`.
- Public actions: 72. Added: `run_query`. Retired: `get_run_status`, `get_run_control_status`, `get_run_output`, `get_run_events`, `get_run_result`, `list_runs`, and `list_operation_locks` → corresponding `run_query` operations.
- Cursor implementation: `after_id` is accepted only by `run_query.events`; cursor queries return ascending `id > after_id` pages, expose the event ID additively, and legacy queries retain latest-N ascending behavior.
- Focused tests: run store, job manager, discovery, and gateway models — 72 passed.
- Full validation: 809 passed, 1 skipped; `pip check` and `git diff --check` passed.
- Next phase: Phase 3 — workflow and supervisor consolidation.

## Phase 3 — workflow and supervisor consolidation (`complete`)

- Files changed so far: Phase 2 files plus workflow/supervisor gateway contracts and focused discovery/model coverage.
- Public actions: 64. Added: `workflow_query`, `workflow_action`, `supervisor_query`, and `supervisor_action`. Retired: `start_workflow`, `get_workflow_status`, `get_workflow_events`, `get_workflow_result`, `cancel_workflow`, `start_supervised_recovery_task`, `get_supervisor_status`, `get_supervisor_events`, `get_supervisor_result`, `resume_supervisor`, `pause_supervisor`, and `cancel_supervisor`.
- Gateway dispatch: the established workflow manager and supervisor service calls remain the internal implementations. Durable workflow/supervisor identifiers, cancellation behavior, active-child handling, and artifact formats are unchanged.
- Focused tests: discovery, server, and gateway models — 62 passed. `pip check` and `git diff --check` passed.
- Known limitation: pytest emits the existing `.pytest_cache` access warning; local repository pytest bases continue to isolate test temp data.
- Next phase: Phase 4 — repository query, preview, apply, and commit gateways.

## Phase 4 — repository query, preview, apply, and commit gateways (`complete`)

- Files changed so far: Phase 0–3 files plus `codexbridge/gateway_models.py`, `codexbridge/server.py`, focused discovery/model tests, and this journal.
- Public actions: 48. Added: `repo_query`, `repo_preview`, `repo_apply`, and `repo_commit`. Retired: `inspect_repo_status`, `inspect_repo_status_compact`, `get_patch_status`, `list_repo_files`, `read_repo_files`, `search_repo_text`, `get_recently_modified_files`, `repo_git_diff`, `git_log`, `inspect_commit_range`, `preview_repo_patch`, `preview_repo_file_creation`, `preview_repo_file_removal`, `preview_managed_artifact_cleanup`, `apply_previewed_repo_change`, `apply_managed_artifact_cleanup`, `move_repo_file`, `revert_managed_patch`, `create_git_branch`, and `commit_selected_files`.
- Gateway dispatch: established repository readers/writers and wrappers remain internal. `repo_query.patch_status` preserves the prior managed-patch lifecycle read with a strict opaque patch ID.
- Focused tests: discovery, server, and gateway models — 64 passed. `pip check` and `git diff --check` passed.
- Next phase: Phase 5 — validation and project-run starters.

## Phase 5 — validation and project-run starters (`complete`)

- Files changed so far: Phase 0–4 files plus strict run-start models, `codexbridge/server.py`, focused discovery/model tests, and this journal.
- Public actions: 42. Added: `run_start`. Retired: `start_project_command_async`, `start_pytest_path_async`, `start_py_compile_path_async`, `start_bash_n_path_async`, `start_json_validation_path_async`, `start_git_readonly_async`, and `start_external_fixture_validation_async`.
- Gateway dispatch: existing JobManager allowlisted starters remain internal and preserve durable run IDs, artifacts, locks, path validation, and outputs.
- Focused tests: 66 passed. Phase 5 full suite: 815 passed, 1 skipped. `pip check` and `git diff --check` passed.
- Next phase: Phase 6 — Docker, Cloudflare, and remaining SSH action gateways.

## Phase 6 — Docker, Cloudflare, and remaining SSH action gateways (`complete`)

- Files changed so far: Phase 0–5 files plus strict Docker, Cloudflare, and SSH domain contracts, gateway dispatch, focused discovery/model tests, and this journal.
- Public actions: 31. Added: `docker_query`, `docker_action`, `cloudflare_query`, `cloudflare_action`, `ssh_query`, and `ssh_action`. Retired: the prior Docker, Cloudflare, and remaining SSH query/action starter wrappers; `ssh_inspect` remains separate.
- Gateway dispatch: existing capability, profile, JobManager, authorization, allowlist, confirmation, transfer, and deployment implementations remain internal.
- Focused tests: 67 passed. `pip check` and `git diff --check` passed.
- Next phase: Phase 7 — system and knowledge gateways.

## Phase 7 — system and knowledge gateways (`complete`)

- Files changed so far: Phase 0–6 files plus strict system/knowledge contracts, gateway dispatch, dynamic knowledge registration refactor, focused discovery/model tests, and this journal.
- Public actions: 24. Added: `system_query`, `system_action`, `knowledge_query`, and `knowledge_action`. Retired: the prior system and knowledge wrappers; repository-scoped memory defaults and service reload/rollback internals remain unchanged.
- Focused tests: 68 passed. `pip check` and `git diff --check` passed.
- Next phase: Phase 8 — Codex endpoints and final surface review.

## Phase 8 — Codex endpoints and final surface review (`complete`)

- Files changed so far: Phase 0–7 files plus strict `codex_plan`/`codex_implement` gateway registration, deterministic benchmark coverage, knowledge documentation, updated integration tests, and this journal.
- Final public actions: 24. Added/retained separate `codex_plan` and `codex_implement`; retired `start_codex_plan_task_async` and `start_codex_implement_task_async` public names.
- Deterministic benchmark/final focused gate: 74 passed, including 24-action count, schema generation/validation, valid/invalid discriminated calls, annotation parity, retired-name absence, and knowledge integration.
- Phase 8 full suite: 819 passed, 1 skipped. `pip check` and `git diff --check` passed.
- Connector requirement: restart the CodexBridge server and refresh the connector/action catalog after this MCP surface migration; existing chats using retired names need gateway-operation updates.
