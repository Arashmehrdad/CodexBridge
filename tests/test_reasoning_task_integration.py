"""G2.3 canonical Task integration with the provider-neutral fake reasoning backend."""

from __future__ import annotations

from pathlib import Path

import pytest

from soma.config import AppConfig, load_config
from soma.project_scope import ProjectScopeStore
from soma.reasoning.fake import FakeReasoningBackend
from soma.reasoning.models import (
    ReasoningBudgetsV1,
    ReasoningHashedReferenceV1,
    ReasoningSpecV1,
)
from soma.reasoning.store import ReasoningBackendStore
from soma.tasks.manager import TaskManager
from soma.tasks.models import (
    BackendKind,
    TaskKind,
    normalize_durable_command_request,
    normalized_request_hash,
)
from soma.tasks.store import TaskStore


PROJECT_ID = "Project_Reasoning"
RESOURCE_ID = "Resource_Reasoning_Repo"


def _hash(character: str) -> str:
    return character * 64


def _make_config(tmp_path: Path) -> tuple[AppConfig, Path, Path]:
    repo = tmp_path / "repo"
    repo.mkdir(parents=True)
    (repo / ".git").mkdir()
    executable = tmp_path / "fake-pwsh.exe"
    executable.write_bytes(b"reasoning-task-fixture")
    runs_dir = tmp_path / "runs"
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "\n".join(
            [
                "repos:",
                "  sample:",
                f'    path: "{repo.as_posix()}"',
                "executable_profiles:",
                "  powershell:",
                '    profile_id: "powershell"',
                "    enabled: true",
                f'    executable_path: "{executable.as_posix()}"',
                '    target: "local"',
                '    autonomy_profile: "permissive"',
                '    working_directory_policy: "arbitrary"',
                '    environment_policy: "arbitrary"',
                '    stdin_mode: "bytes"',
                '    stdout_mode: "protected_artifact"',
                '    stderr_mode: "protected_artifact"',
                "    allow_no_timeout: true",
                "    unrestricted_argv: true",
                "    unrestricted_paths: true",
                "    unrestricted_environment: true",
                f'runs_dir: "{runs_dir.as_posix()}"',
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return load_config(config_path), config_path, repo


def _scope(config: AppConfig, repo: Path) -> ProjectScopeStore:
    TaskStore(config.resolve_runs_dir())
    scope = ProjectScopeStore(config.resolve_runs_dir())
    scope.init_db()
    applied = scope.apply_bootstrap(
        project_id=PROJECT_ID,
        project_key="reasoning",
        resource_id=RESOURCE_ID,
        repo_name="sample",
        repository_root=repo,
        access_mode="exclusive",
    )
    assert applied["applied"] is True
    scope.set_scoped_writes_enabled(True)
    return scope


def _spec() -> ReasoningSpecV1:
    return ReasoningSpecV1(
        assignment_ref="assignment:reasoning-task",
        assignment_hash=_hash("1"),
        context_refs=(ReasoningHashedReferenceV1(ref="context:repo", hash=_hash("2")),),
        dependency_proof_refs=(
            ReasoningHashedReferenceV1(ref="proof:upstream", hash=_hash("3")),
        ),
        output_contract_ref="contract:evidence-submission-v1",
        output_contract_hash=_hash("4"),
        tool_policy_ref="tool-policy:read-only",
        tool_policy_hash=_hash("5"),
        authority_ref="authority:work-package-attempt",
        authority_hash=_hash("6"),
        provider_route_ref="route:fake-reasoning",
        provider_route_hash=_hash("7"),
        budgets=ReasoningBudgetsV1(
            wall_time_seconds=60,
            output_bytes=32 * 1024,
            provider_internal_concurrency_limit=1,
        ),
        continuation_policy="none",
        mutation_policy="read_only",
    )


def _manager(
    tmp_path: Path,
    *,
    case: str,
) -> tuple[TaskManager, FakeReasoningBackend, ProjectScopeStore]:
    config, config_path, repo = _make_config(tmp_path)
    scope = _scope(config, repo)
    reasoning_store = ReasoningBackendStore(config.resolve_runs_dir())
    fake = FakeReasoningBackend(reasoning_store, case=case)
    manager = TaskManager(
        config,
        config_path,
        reasoning_backend=fake,
        scope_store=scope,
    )
    return manager, fake, scope


def _start(manager: TaskManager, **overrides):
    values = {
        "controller_request_id": "reasoning-request-1",
        "repo_name": "sample",
        "project_id": PROJECT_ID,
        "spec": _spec(),
        "work_package_attempt_ref": "wpattempt:fixture",
        "work_package_attempt_hash": _hash("8"),
    }
    values.update(overrides)
    return manager.start_reasoning_task(**values)


def test_public_task_capabilities_remain_durable_only_before_activation(
    tmp_path: Path,
) -> None:
    manager, _fake, _scope_store = _manager(tmp_path, case="success")
    capabilities = manager.capabilities()

    assert capabilities["task_kinds"] == [TaskKind.DURABLE_COMMAND.value]
    assert [item["backend_kind"] for item in capabilities["backends"]] == [
        BackendKind.SOMA_DURABLE_RUN.value
    ]
    assert "reasoning" not in capabilities["task_kinds"]
    assert "backend" not in capabilities["link_types"]


def test_legacy_durable_request_hash_is_unchanged() -> None:
    normalized = normalize_durable_command_request(
        repo_name="sample",
        profile_id="powershell",
        argv=["-NoProfile", "-Command", "Write-Output legacy"],
    )
    assert normalized_request_hash(normalized) == (
        "10b08e12169fe7a657dca393215f441a51e458c73055423b366f39240b7cca32"
    )


def test_reasoning_task_success_is_idempotent_and_uses_generic_backend_link(
    tmp_path: Path,
) -> None:
    manager, fake, scope = _manager(tmp_path, case="success")

    first = _start(manager)
    replay = _start(manager)

    assert first["ok"] is True
    assert first["task_kind"] == "reasoning"
    assert first["backend_kind"] == "soma_reasoning"
    assert first["state"] == "completed"
    assert first["result_available"] is True
    assert first["project_attempt_status"] == "attached"
    assert replay["task_id"] == first["task_id"]
    assert replay["idempotent_replay"] is True
    assert fake.provider_create_calls == 1
    assert scope.require_task_attempt(
        PROJECT_ID, first["task_id"], first["backend_reference"]
    )

    task = manager.store.get_task(first["task_id"])
    assert task.task_kind is TaskKind.REASONING
    assert task.backend_kind is BackendKind.SOMA_REASONING
    assert "provider_operation_ref" not in task.backend_identity
    assert task.backend_identity["reasoning_spec_hash"]
    links = manager.get_links(first["task_id"], project_id=PROJECT_ID)
    assert any(
        link["link_type"] == "backend" and link["target_kind"] == "backend"
        for link in links["links"]
    )

    result = manager.get_result(first["task_id"], project_id=PROJECT_ID)
    assert result["result_authority"] == "reasoning_backend"
    assert result["result_source"]["authority"] == "reasoning_backend"
    assert result["result_source"]["evidence_submission_ref"]
    assert "transcript" not in result["result_source"]
    assert "authoritative_result_retrieval" not in result
    assert "complete_result_retrieval" not in result


def test_backend_start_response_loss_replays_without_duplicate_provider_create(
    tmp_path: Path,
) -> None:
    manager, fake, scope = _manager(tmp_path, case="success")

    def crash(phase: str) -> None:
        if phase == "after_backend_start":
            raise RuntimeError("response-lost-after-backend-start")

    with pytest.raises(RuntimeError, match="response-lost"):
        _start(manager, _fault_injector=crash)

    task = manager.store.find_by_controller_request("reasoning-request-1")
    assert task is not None
    assert fake.provider_create_calls == 1
    assert scope.scope_for_run(task.backend_ref).attempt_status == "reserved"

    replay = _start(manager)
    assert replay["idempotent_replay"] is True
    assert replay["state"] == "completed"
    assert fake.provider_create_calls == 1
    assert scope.scope_for_run(task.backend_ref).attempt_status == "attached"


def test_crash_after_task_commit_before_backend_claim_recovers_on_replay(
    tmp_path: Path,
) -> None:
    manager, fake, scope = _manager(tmp_path, case="success")

    def crash(phase: str) -> None:
        if phase == "after_task_commit":
            raise RuntimeError("crash-after-task-commit")

    with pytest.raises(RuntimeError, match="crash-after-task-commit"):
        _start(manager, _fault_injector=crash)

    task = manager.store.find_by_controller_request("reasoning-request-1")
    assert task is not None
    assert fake.provider_create_calls == 0
    assert scope.scope_for_run(task.backend_ref).attempt_status == "reserved"

    replay = _start(manager)
    assert replay["state"] == "completed"
    assert fake.provider_create_calls == 1
    assert scope.scope_for_run(task.backend_ref).attempt_status == "attached"


def test_ambiguous_create_ack_enters_recovery_and_never_resubmits(
    tmp_path: Path,
) -> None:
    manager, fake, _scope_store = _manager(tmp_path, case="ambiguous_ack")

    first = _start(manager)
    replay = _start(manager)

    assert first["state"] == "recovery_pending"
    assert first["recovery_state"] == "pending"
    assert first["result_available"] is False
    assert replay["task_id"] == first["task_id"]
    assert replay["state"] == "recovery_pending"
    assert fake.provider_create_calls == 1


def test_long_running_reasoning_cancellation_delegates_to_selected_backend(
    tmp_path: Path,
) -> None:
    manager, fake, _scope_store = _manager(tmp_path, case="long_running")
    started = _start(manager)
    assert started["state"] == "running"

    cancelled = manager.cancel_task(
        started["task_id"],
        if_state_version=started["state_version"],
        project_id=PROJECT_ID,
        reason="operator cancellation",
    )

    assert cancelled["ok"] is True
    assert cancelled["state"] == "cancelled"
    assert fake.provider_cancel_calls == 1


def test_malformed_reasoning_output_never_becomes_completed(tmp_path: Path) -> None:
    manager, _fake, _scope_store = _manager(tmp_path, case="malformed_output")
    started = _start(manager)

    assert started["state"] == "failed"
    assert started["result_available"] is False
    result = manager.get_result(started["task_id"], project_id=PROJECT_ID)
    assert result["result_available"] is False
    assert result["result_source"]["available"] is False


def test_project_scope_startup_understands_reasoning_backend_attachment(
    tmp_path: Path,
) -> None:
    manager, _fake, scope = _manager(tmp_path, case="long_running")
    started = _start(manager)
    assert started["project_attempt_status"] == "attached"

    reconciled = scope.reconcile_startup()
    assert reconciled["counts"]["attempt_quarantined"] == 0
    assert (
        scope.scope_for_run(started["backend_reference"]).attempt_status == "attached"
    )


def test_missing_reasoning_adapter_recovers_without_durable_fallback(
    tmp_path: Path,
) -> None:
    manager, fake, scope = _manager(tmp_path, case="long_running")
    started = _start(manager)
    assert started["state"] == "running"
    assert fake.provider_create_calls == 1

    restarted = TaskManager(
        manager.config,
        manager.config_path,
        scope_store=scope,
    )
    status = restarted.get_status(started["task_id"], project_id=PROJECT_ID)

    assert status["backend_kind"] == "soma_reasoning"
    assert status["state"] == "uncertain"
    assert status["recovery_state"] == "unresolved"
    assert status["recovery_reason"] == "backend_not_configured"
    assert status["backend_status"] == ""
    assert fake.provider_create_calls == 1


def test_reasoning_start_requires_enforced_project_scope(tmp_path: Path) -> None:
    manager, _fake, scope = _manager(tmp_path, case="success")
    scope.set_scoped_writes_enabled(False)

    denied = _start(manager)

    assert denied["ok"] is False
    assert denied["error_code"] == "project_scope_paused"
