# Permissive-Only Migration Inventory

Status: **C1 complete on 2026-07-17**.

This document is the final C1 capability and retention record. Local unrestricted PowerShell and durable parallel fan-out are the active arbitrary-command substrates. Remote SSH transport, staging, transfer, deployment, reviewed-script, and administration primitives remain intentionally retained for R3, R4, and X4 because equivalent durable remote ownership and staging are not yet available.

## Active installation state

- `config.yaml`, `config.example.yaml`, SSH request models, policy evaluation, manager defaults, worker revalidation, and public capability schemas accept only the `permissive` SSH execution profile.
- Removed SSH profile names are retained only in negative validation tests or historical migration evidence; they have no positive runtime, configuration, or public-schema route.
- `supervisor_action` starts with the permissive profile only.
- Permission-tier names such as `T4_WRITE_APPLY_CHATGPT_DELEGATED` remain part of the general approval model. They are not execution-profile routes and were not removed by C1.
- Repository query, managed patching, durable runs, locks, protected artifacts, workflows, supervisors, cancellation, recovery, return-loop publication, SSH transport, and configuration lifecycle tools remain retained control-plane primitives.

## Final capability matrix

| Surface reviewed | C1 result | Retained replacement or reason |
| --- | --- | --- |
| SSH `conservative`, `balanced`, and `chatgpt_delegated` execution routing | Removed from active configuration, models, policy matrix, manager defaults, workers, and live schemas | Permissive-only SSH execution; deterministic rejection tests preserve migration evidence |
| Public synchronous `run_project_command` compatibility tool | Removed | Durable typed operations and unrestricted PowerShell |
| Public `run_start(operation="project_command")` variant and forwarding helper | Removed | Internal `JobManager.start_project_command` remains for workflows and `DurableProjectCommandRunner` only |
| Direct-subprocess `LocalAgentCommandRunner` and helper | Removed | `DurableProjectCommandRunner` over `JobManager`/`RunStore`; orchestration tests inject structural doubles |
| Duplicate local-agent command-profile registry and artifact tree | Removed | Canonical durable command-profile registry and durable run artifacts |
| Built-in `ruff_check`, `ruff_format_check`, `ruff_format`, `mypy`, and duplicate `git_diff_check` | Removed | Unrestricted PowerShell; retained typed `git_readonly(diff_check)` where a fixed validation operation is useful |
| Ordinary Andia `eslint`, `typecheck`, `vitest`, and `frontend_validate` configured profiles | Removed after live replacement smoke tests | Unrestricted PowerShell with the repository working directory and explicit timeout |
| CodexBridge inspection, rollback repair, and service-restart configured profiles | Retained | These carry reviewed operational semantics and remain internal durable workflow contracts, not public arbitrary-command gateways |
| SSH reviewed-script, administration, transfer, and deployment wrappers | Retained and assigned to R3/R4/X4 | They still provide remote transport, staging, controller, and evidence behavior that local PowerShell cannot replace safely before remote durability parity |
| Durable history and protected evidence from removed routes | Retained | Explicit C1 retention policy below |

## Configuration migration result

- `ssh_active_autonomy_profiles_v1` is deterministic, rollback-capable, and reports no migration requirement for the active permissive-only configuration.
- `ordinary_validation_command_profiles_v1` preserves complete configured profiles as rollback data and emits exact unrestricted-PowerShell replacements while candidates exist.
- After the Andia migration and config reload, configuration validation omits the ordinary-profile migration key entirely because no candidates remain.
- Configuration migration never deletes or mutates historical durable runs.

## Durable evidence retention policy

C1 route removal does not delete durable evidence.

- The configured `runs/` directory, SQLite databases, run directories, protected stdout/stderr artifacts, structured results, events, return-loop reports, and delivered manifests are outside managed cleanup scope.
- Managed cleanup accepts only the explicit `MANAGED_ARTIFACT_ROOTS` allowlist: `.codex-tmp`, `.pytest_cache`, `.ruff_cache`, and `tests/pytest_tmp_probe`.
- Cleanup requires a preview manifest, repository fingerprint, per-file SHA-256 verification, regular-file checks, and an idempotent apply transition.
- Cleanup rejects the `runs` root and every unregistered path.
- Historical evidence remains readable after its originating public route or compatibility implementation is removed. Any future time-based retention feature requires a separate roadmap unit and explicit operator policy.

## Validation and acceptance evidence

Focused closure validation:

- `tests/test_service_reload.py`: 9 passed;
- `tests/test_managed_artifacts.py`: 5 passed;
- `tests/test_powershell_acceptance.py`: 4 passed;
- `tests/test_parallel_powershell_acceptance.py`: 7 passed.

Live unrestricted-PowerShell evidence:

- PowerShell launched Git `2.53.0.windows.2`;
- PowerShell launched OpenSSH for Windows `9.5p2`;
- PowerShell launched Git-for-Windows OpenSSL `3.5.5` by absolute installed path;
- PowerShell launched Python `3.12.10`;
- earlier Andia replacements passed typecheck, 6 Vitest files with 20 tests, frontend validation, and reviewed ESLint validation without changing ACLs or deleting generated data.

C1 exit gate:

- full repository suite: **1103 passed, 1 skipped**;
- `python -m pip check`: no broken requirements;
- `git diff --check`: passed;
- configuration validation and reload: passed;
- durable protected artifacts and run history: preserved.

## Closure decision

C1 removes redundant local execution surfaces and compatibility execution-profile routing. It does not remove remote transport or staging functionality before replacement durability exists. The next roadmap unit is **R3 - Transfer Policy and Managed Staging**, followed by **R4 - Durable Remote Job Protocol** and **X4 - Unrestricted Remote PowerShell**.
