# Domain Tool Gateway Migration Plan

Status: approved end-to-end implementation plan; implementation has not started.

Baseline:

- Repository: `CodexBridge`
- Working branch at plan creation: `feature/automatic-repo-discovery`
- Clean baseline commit: `17207ed` (`Complete workflow orchestration and stabilize MCP tool surface`)
- Local recovery branch: `checkpoint/pre-domain-gateway-migration-20260711`
- Baseline public MCP action count: 80
- Baseline validation: 805 passed, 1 skipped; `python -m pip check` reported no broken requirements

## Mandatory execution rule

This document may be implemented in one end-to-end Codex run. The run must execute Phases 0 through 8 sequentially, treat each phase as an internal transaction, run that phase's focused validation before advancing, and stop immediately if any phase gate fails. It must not skip or reorder phases, conceal failures, or continue after a failed gate.

For every phase:

1. Inspect the current repository and this document before editing.
2. Confirm the working tree is clean before Phase 0. During later phases, confirm that all dirty files belong to the cumulative migration scope and that no unrelated files appeared.
3. Do not modify unrelated files.
4. Do not commit, push, rebase, reset, clean, stash, or switch branches.
5. Preserve all existing run IDs, workflow IDs, supervisor IDs, durable artifacts, locks, audit records, safety checks, and internal implementations.
6. Never introduce arbitrary shell-command execution.
7. Keep read-only and write-capable public tools separate.
8. Stop immediately on an unexpected test failure, schema incompatibility, missing prerequisite, quota/rate-limit/context-limit error, or uncertainty about destructive behavior.
9. Leave the repository syntactically valid and report the exact partial state if interrupted.
10. Run the validation commands listed for the current phase before advancing. Run the required common validation after each phase when practical and always after Phase 8.
11. After a phase passes, record an internal checkpoint summary containing files changed, public action count, retired names, focused test results, and the next phase, then continue without committing.
12. If a phase cannot be completed safely, stop the entire implementation run. Do not attempt later phases or broad repairs.

## Objective

Reduce the public MCP surface from 80 narrowly named tools to a smaller set of domain gateways while preserving behavior and safety. The migration should improve tool-selection reliability, reduce connector/schema overhead, avoid the 80-tool exposure boundary, and keep the current specialised Python implementations as internal functions.

The target is approximately 24-30 public tools. The final count is not a hard requirement; correctness, safety, typed schemas, and benchmark results take priority.

## Non-goals

- Do not rewrite `JobManager`, workflow persistence, supervisor persistence, SSH execution, Docker execution, Cloudflare execution, repository readers/writers, or audit storage.
- Do not replace all tools with one universal executor.
- Do not accept arbitrary command strings, arbitrary shell fragments, or generic unvalidated dictionaries.
- Do not change durable artifact formats unless a phase explicitly requires an additive compatibility field.
- Do not change run/workflow/supervisor identifier formats.
- Do not add deployment, push, release, or production behavior.
- Do not perform broad formatting or unrelated cleanup.

## Architecture rules

### 1. Domain gateways, not a universal command tool

Public tools should remain grouped by domain, for example:

- `ssh_inspect` / `ssh_action`
- `run_query` / `run_cancel`
- `workflow_query` / `workflow_action`
- `supervisor_query` / `supervisor_action`
- `repo_query` / `repo_preview` / `repo_apply` / `repo_commit`
- `docker_query` / `docker_action`
- `cloudflare_query` / `cloudflare_action`
- `system_query` / `system_action`
- `knowledge_query` / `knowledge_action`
- `codex_plan` / `codex_implement`

Names may differ only when existing names already provide the correct gateway semantics and retaining them avoids a needless breaking change.

### 2. Typed discriminated requests

Each gateway must use a typed discriminated request model or equivalent JSON Schema `oneOf` structure keyed by a literal `operation` or `action` field.

Do not build gateways with a large flat list of unrelated optional parameters.

Good shape:

```python
class RunOutputQuery(BaseModel):
    operation: Literal["output"]
    run_id: str
    stream: Literal["combined", "stdout", "stderr"] = "combined"
    tail_bytes: int = Field(default=20_000, ge=1, le=200_000)

class RunEventsQuery(BaseModel):
    operation: Literal["events"]
    run_id: str
    limit: int = Field(default=50, ge=1, le=500)
    after_id: int | None = Field(default=None, ge=0)

RunQuery = Annotated[
    RunOutputQuery | RunEventsQuery | ...,
    Field(discriminator="operation"),
]
```

Bad shape:

```python
def run_query(operation: str, run_id: str = "", stream: str = "", limit: int = 0, ...):
    ...
```

### 3. Preserve internal implementations

The current specialised functions remain the source of behavior. Gateways dispatch to those functions or manager methods. Retiring a public wrapper means changing its decorator/registration, not deleting proven implementation logic.

### 4. Preserve tool annotations

- Query/inspection gateways: read-only, idempotent, non-destructive.
- Action/apply/cancel gateways: write-capable with current risk and open-world annotations preserved.
- A gateway must not mix read-only operations and write operations under one public tool.

### 5. Preserve or strengthen validation

Operation-specific required fields, enums, bounds, path validation, hash checks, confirmations, repository locks, SSH host allowlists, command profiles, and timeout rules must remain enforced.

### 6. Stable structured outputs

A gateway may return operation-specific structured results. It must keep stable top-level fields where applicable:

- `ok`
- domain identifier such as `repo_name`, `run_id`, `workflow_id`, `supervisor_id`, or `host_id`
- `status`
- `error`
- build/schema metadata already added by the server

Avoid degrading all outputs to an opaque string or untyped blob.

## Public compatibility policy

Compatibility is handled per phase:

1. Add or extend the gateway and its tests.
2. In the same phase, retire only the wrappers replaced by that gateway so the public action count never rises above 80.
3. Keep retired wrappers callable internally where tests or internal code still need them.
4. Update exact action-discovery expectations in the same patch.
5. Do not leave duplicate public tools with overlapping descriptions.
6. Record every retired public name and its replacement operation in the phase report.

The migration does not promise indefinite public aliases. Existing chats may need connector refresh after each surface change.

## Benchmark requirements

Before broad consolidation, establish a deterministic local benchmark suite using direct tool invocation/schema validation rather than relying on live model calls.

The benchmark must cover:

- correct gateway and operation selection fixtures
- schema acceptance of valid calls
- schema rejection of invalid field combinations
- annotation parity
- result parity with the replaced wrapper
- public action count
- absence of retired duplicate public names
- unchanged durable identifiers and artifact reads

Optional live-model comparison can be documented separately, but it is not required for repository tests and must not block deterministic validation.

## Common validation for every implementation phase

Run after the phase-specific tests pass:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m pip check
git diff --check
git status --short
```

A phase is incomplete if any command fails. Do not conceal pre-existing versus new failures; report both precisely.

## Phase 0 - Migration harness and schema inventory

Purpose: create the testing and typed-model foundation without changing the public tool surface.

Allowed files:

- new focused gateway model/module files under `codexbridge/`
- new focused tests under `tests/`
- `docs/domain-tool-gateway-migration.md` only if implementation findings require a factual correction

Required work:

1. Generate a machine-readable inventory from the live server registration containing public name, annotations, input schema, output schema, and domain classification.
2. Add reusable test helpers for:
   - public action count
   - exact public-name sets by domain
   - annotation assertions
   - valid/invalid discriminated-union payload checks
   - result-parity checks
3. Add typed request models only for Phase 1 SSH inspection operations; do not register a new public tool yet.
4. Add tests proving the models reject cross-operation fields and missing required fields.
5. Do not edit existing runtime dispatch behavior.

Phase-specific validation:

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests\test_mcp_action_discovery.py tests\test_tool_gateway_models.py
```

Exit gate:

- Public action count remains exactly 80.
- Existing action names are unchanged.
- Full suite passes.

## Phase 1 - Consolidate SSH read-only inspection

Purpose: use the existing `ssh_inspect` gateway for environment and GPU inspection.

Allowed files:

- SSH gateway model module created in Phase 0
- `codexbridge/server.py`
- existing SSH implementation modules only if a minimal dispatch adapter is required
- `tests/test_mcp_action_discovery.py`
- focused SSH tests
- relevant README section

Required work:

1. Extend `ssh_inspect` with typed operations for:
   - `host_health`
   - `environment_probe`
   - `gpu_telemetry`
   - all currently supported bounded inspection operations
2. Dispatch to the current `_ssh_host_health`, `_run_ssh_environment_probe`, `_run_ssh_gpu_telemetry`, and `_run_ssh_inspection` implementations.
3. Retire these public wrappers while keeping their implementations internal:
   - `ssh_environment_probe`
   - `ssh_gpu_telemetry`
   - `ssh_host_health` if it is still public in the current baseline
4. Preserve the current output content and read-only annotations.
5. Add parity tests comparing gateway results to internal implementation results.

Exit gate:

- Public count decreases by the number of retired wrappers minus any genuinely new public gateway.
- No SSH write tool changes.
- Full suite passes.

## Phase 2 - Consolidate run queries

Purpose: replace overlapping read-only run retrieval tools with `run_query`.

Allowed files:

- gateway model/dispatch modules
- `codexbridge/server.py`
- job manager/store only for additive `after_id` event-cursor support
- run-focused tests
- action-discovery tests
- relevant README section

Required `run_query` operations:

- `status`
- `control`
- `output`
- `events`
- `result`
- `list`
- `locks`

Required behavior:

- Preserve all current manager calls and outputs.
- Add optional `after_id` to the `events` operation only, with deterministic ascending event order and no duplicates.
- Keep `cancel_run` as a separate write tool.
- Retire the corresponding read-only public wrappers only after parity tests pass.

Exit gate:

- Existing run IDs remain readable.
- Existing event calls without `after_id` retain current behavior.
- Event cursor tests cover empty, exact-boundary, stale, and multi-page cases.
- Full suite passes.

## Phase 3 - Consolidate workflow and supervisor lifecycle tools

Purpose: reduce repetitive lifecycle wrappers while preserving read/write separation.

Required public shape:

- `workflow_query`: status, events, result
- `workflow_action`: start, cancel
- `supervisor_query`: status, events, result, notifications, resume_prompt
- `supervisor_action`: start, resume, pause, cancel

Rules:

- Use discriminated request types.
- Preserve existing workflow/supervisor managers and artifact formats.
- Do not combine workflow and supervisor domains.
- Preserve cancellation behavior and active-child handling.

Exit gate:

- Existing workflow and supervisor identifiers remain valid.
- Restart reconciliation tests remain unchanged and passing.
- Full suite passes.

## Phase 4 - Consolidate repository inspection and managed changes

Purpose: reduce repository tools while retaining preview/apply safety boundaries.

Required public shape:

- `repo_query`: status, compact_status, list_files, read_files, search_text, recent_files, diff, log, commit_range
- `repo_preview`: patch, create_file, remove_file, cleanup
- `repo_apply`: previewed_change, cleanup, revert, move_file
- `repo_commit`: create_branch, commit_selected

Rules:

- Do not merge preview and apply into one tool.
- Do not remove hash verification, opaque preview bundles, rollback data, path checks, protected-branch rules, repository locks, or selected-file commit validation.
- Prefer the existing batch read path over restoring duplicate single-file public wrappers.
- Do not expose `stage_all`, `commit_all_changes`, or arbitrary command execution.

Exit gate:

- Every write operation still requires its current preview/hash/confirmation boundary.
- No operation can address files outside the whitelisted repository.
- Full suite passes.

## Phase 5 - Consolidate validation and project-run starters

Purpose: replace the separate pytest, compile, shell-syntax, JSON, Git-readonly, fixture-validation, and project-command starters with one typed `run_start` gateway.

Required operations:

- `project_command`
- `pytest_path`
- `py_compile_path`
- `bash_syntax_path`
- `json_validation_path`
- `git_readonly`
- `external_fixture_validation`

Rules:

- Continue to use allowlisted profiles and validated paths.
- Do not accept raw argv or shell text.
- Keep durable async behavior and result storage.
- Do not merge Codex plan/implementation into this gateway.

Exit gate:

- Each old starter has result-parity coverage.
- Unknown operations and invalid paths are rejected before job creation.
- Full suite passes.

## Phase 6 - Consolidate Docker, Cloudflare, and remaining SSH actions

Required public shape:

- `docker_query`: capabilities, health, inspect
- `docker_action`: existing bounded actions
- `cloudflare_query`: capabilities, health, inspect
- `cloudflare_action`: existing bounded actions
- `ssh_query`: capabilities, profile-change status, and read-only profile preview if not covered by `ssh_inspect`
- `ssh_action`: profile apply, configured command, monitored command, bounded administration, transfer, deployment

Rules:

- Domain boundaries remain separate.
- Preserve confirmation requirements and high-risk gates.
- Transfers and deployments may remain separate public tools if combining them makes schemas or approval semantics less clear.
- Never expose unrestricted remote command text.

Exit gate:

- Risk annotations and confirmation tests are at least as strict as baseline.
- Full suite passes.

## Phase 7 - Consolidate system and knowledge tools

Required public shape:

- `system_query`: capabilities, self_check, local_model_health, validate_config, reload_status
- `system_action`: reload, rollback
- `knowledge_query`: read_wiki, search
- `knowledge_action`: refresh_wiki, remember_decision

Rules:

- Keep repository-scoped memory as the default.
- Do not mix global memory unless explicitly requested and already permitted.
- Preserve service reload/rollback validation and last-known-good behavior.

Exit gate:

- Repository knowledge isolation tests pass.
- Service lifecycle rollback tests pass.
- Full suite passes.

## Phase 8 - Codex endpoints and final surface review

Codex planning and implementation remain separate public tools because they have materially different permissions and risk:

- `codex_plan`
- `codex_implement`

Work:

1. Remove obsolete compatibility aliases only when their replacement is tested and documented.
2. Review every remaining public tool for a unique responsibility.
3. Verify no tool is hidden by connector action limits.
4. Update README and exact action-discovery tests.
5. Record the final public count and retired-name mapping.
6. Run the complete benchmark and full suite.

Final acceptance criteria:

- Approximately 24-30 public tools, unless evidence justifies a different number.
- No universal executor.
- No arbitrary shell or remote command input.
- Read/write separation preserved.
- Existing durable IDs and artifacts remain valid.
- Public schemas use typed discriminated operations.
- Exact action discovery, annotations, and outputs are tested.
- Full repository tests and dependency checks pass.
- Connector refresh instructions are documented.

## Interruption and recovery procedure

If Codex is interrupted or reaches a usage limit:

1. Do not start another implementation run immediately.
2. Inspect `git status --short` and `git diff --check`.
3. Run only the focused tests for the current phase.
4. Compare against this phase's allowed-file list.
5. Revert only files proven to belong exclusively to the failed phase, or restore the whole baseline using the recovery branch after preserving any wanted diff.
6. Never use `git clean -fd` against an unreviewed tree.

Baseline recovery reference:

```powershell
git branch --show-current
git status --short
git diff > ..\domain-gateway-interrupted.patch
git reset --hard checkpoint/pre-domain-gateway-migration-20260711
git status --short
```

The `git reset --hard` line is destructive to uncommitted work and must only be used after exporting or intentionally discarding the interrupted migration diff.

## Required implementation report

During a single end-to-end run, keep a concise internal checkpoint after every completed phase. In the final response, report:

- phases completed and any phase where execution stopped
- files changed, grouped by phase or domain
- public tools added, extended, retired, and final count
- complete retired-name to gateway-operation mapping
- operation-to-internal-function mapping
- schema and annotation changes
- tests added
- focused validation results for every phase
- final full-suite and dependency-check results
- benchmark results and comparison with the 80-tool baseline
- compatibility impact on existing chats and connector refresh requirements
- assumptions and known limitations
- exact `git status --short`
- confirmation that no commit or push occurred
