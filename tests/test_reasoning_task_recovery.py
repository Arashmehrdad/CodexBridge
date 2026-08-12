"""G2.4 restart/fault matrix for canonical reasoning Tasks.

Every provider is deterministic fake infrastructure. These tests exercise new
TaskManager/ReasoningBackendStore instances over the same durable SQLite state.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from soma.config import AppConfig, load_config
from soma.project_scope import ProjectScopeStore
from soma.reasoning.fake import FakeReasoningBackend
from soma.reasoning.models import ReasoningBudgetsV1, ReasoningSpecV1
from soma.reasoning.store import ReasoningBackendStore
from soma.tasks.manager import TaskManager


PROJECT_ID = "Project_Reasoning_Recovery"
RESOURCE_ID = "Resource_Reasoning_Recovery"


def _hash(character: str) -> str:
    return character * 64


def _config(tmp_path: Path) -> tuple[AppConfig, Path, Path]:
    repo = tmp_path / "repo"
    repo.mkdir(parents=True)
    (repo / ".git").mkdir()
    executable = tmp_path / "fake-pwsh.exe"
    executable.write_bytes(b"g2-recovery-fixture")
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


def _bootstrap_scope(config: AppConfig, repo: Path) -> ProjectScopeStore:
    # TaskManager/TaskStore will install Task schema in the same DB. ProjectScope
    # bootstrap is intentionally separate so restart fixtures can recreate stores.
    from soma.tasks.store import TaskStore

    TaskStore(config.resolve_runs_dir())
    scope = ProjectScopeStore(config.resolve_runs_dir())
    scope.init_db()
    scope.apply_bootstrap(
        project_id=PROJECT_ID,
        project_key="reasoning-recovery",
        resource_id=RESOURCE_ID,
        repo_name="sample",
        repository_root=repo,
        access_mode="exclusive",
    )
    scope.set_scoped_writes_enabled(True)
    return scope


def _spec(*, route_marker: str = "7") -> ReasoningSpecV1:
    return ReasoningSpecV1(
        assignment_ref="assignment:reasoning-recovery",
        assignment_hash=_hash("1"),
        output_contract_ref="contract:evidence-submission-v1",
        output_contract_hash=_hash("2"),
        tool_policy_ref="tool-policy:read-only",
        tool_policy_hash=_hash("3"),
        authority_ref="authority:reasoning-recovery",
        authority_hash=_hash("4"),
        provider_route_ref="route:fake-recovery",
        provider_route_hash=_hash(route_marker),
        budgets=ReasoningBudgetsV1(
            wall_time_seconds=60,
            output_bytes=32 * 1024,
            provider_internal_concurrency_limit=1,
        ),
        continuation_policy="none",
        mutation_policy="read_only",
    )


def _fresh(
    tmp_path: Path,
    *,
    case: str,
) -> tuple[TaskManager, FakeReasoningBackend, ReasoningBackendStore, AppConfig, Path]:
    config, config_path, repo = _config(tmp_path)
    scope = _bootstrap_scope(config, repo)
    reasoning_store = ReasoningBackendStore(config.resolve_runs_dir())
    fake = FakeReasoningBackend(reasoning_store, case=case)
    manager = TaskManager(
        config,
        config_path,
        reasoning_backend=fake,
        scope_store=scope,
    )
    return manager, fake, reasoning_store, config, config_path


def _restart(
    config: AppConfig,
    config_path: Path,
    *,
    case: str,
) -> tuple[TaskManager, FakeReasoningBackend, ReasoningBackendStore, ProjectScopeStore]:
    reasoning_store = ReasoningBackendStore(config.resolve_runs_dir())
    fake = FakeReasoningBackend(reasoning_store, case=case)
    scope = ProjectScopeStore(config.resolve_runs_dir())
    manager = TaskManager(
        config,
        config_path,
        reasoning_backend=fake,
        scope_store=scope,
    )
    return manager, fake, reasoning_store, scope


def _start(manager: TaskManager, *, spec: ReasoningSpecV1 | None = None, fault=None):
    return manager.start_reasoning_task(
        controller_request_id="g2-recovery-request",
        repo_name="sample",
        project_id=PROJECT_ID,
        spec=spec or _spec(),
        work_package_attempt_ref="wpattempt:g2-recovery",
        work_package_attempt_hash=_hash("8"),
        _fault_injector=fault,
    )


def test_crash_after_backend_ref_reserve_before_task_commit_leaves_no_canonical_split(
    tmp_path: Path,
) -> None:
    manager, fake, reasoning_store, _config_value, _config_path = _fresh(
        tmp_path, case="success"
    )

    def crash(phase: str) -> None:
        if phase == "after_backend_reserve":
            raise RuntimeError("crash-after-backend-reserve")

    with pytest.raises(RuntimeError, match="backend-reserve"):
        _start(manager, fault=crash)

    assert manager.store.find_by_controller_request("g2-recovery-request") is None
    assert reasoning_store.table_counts() == {
        "reasoning_backend_runs": 0,
        "reasoning_backend_start_attempts": 0,
    }
    assert fake.provider_create_calls == 0

    recovered = _start(manager)
    assert recovered["state"] == "completed"
    assert fake.provider_create_calls == 1


def test_restart_after_task_commit_before_backend_claim_resumes_same_task(
    tmp_path: Path,
) -> None:
    manager, fake, _store, config, config_path = _fresh(tmp_path, case="success")

    def crash(phase: str) -> None:
        if phase == "after_task_commit":
            raise RuntimeError("crash-after-task-commit")

    with pytest.raises(RuntimeError, match="task-commit"):
        _start(manager, fault=crash)
    persisted = manager.store.find_by_controller_request("g2-recovery-request")
    assert persisted is not None
    assert fake.provider_create_calls == 0

    restarted, restarted_fake, store, _scope = _restart(
        config, config_path, case="success"
    )
    replay = _start(restarted)

    assert replay["task_id"] == persisted.task_id
    assert replay["state"] == "completed"
    assert restarted_fake.provider_create_calls == 1
    assert store.table_counts()["reasoning_backend_start_attempts"] == 1


def test_restart_after_start_claim_before_provider_send_uses_same_start_attempt(
    tmp_path: Path,
) -> None:
    manager, fake, store, config, config_path = _fresh(
        tmp_path, case="crash_before_send"
    )
    first = _start(manager)
    task = manager.store.find_by_controller_request("g2-recovery-request")
    assert task is not None
    attempt_before = store.start_attempt(task.backend_ref)

    assert first["ok"] is False
    assert fake.provider_create_calls == 0
    assert attempt_before["disposition"] == "claimed_not_sent"

    restarted, restarted_fake, restarted_store, _scope = _restart(
        config, config_path, case="success"
    )
    replay = _start(restarted)
    attempt_after = restarted_store.start_attempt(task.backend_ref)

    assert replay["task_id"] == task.task_id
    assert replay["state"] == "completed"
    assert restarted_fake.provider_create_calls == 1
    assert attempt_after["start_attempt_id"] == attempt_before["start_attempt_id"]


def test_accepted_provider_response_loss_then_restart_never_duplicates_create(
    tmp_path: Path,
) -> None:
    manager, fake, _store, config, config_path = _fresh(tmp_path, case="success")

    def crash(phase: str) -> None:
        if phase == "after_backend_start":
            raise RuntimeError("response-lost")

    with pytest.raises(RuntimeError, match="response-lost"):
        _start(manager, fault=crash)
    task = manager.store.find_by_controller_request("g2-recovery-request")
    assert task is not None
    assert fake.provider_create_calls == 1

    restarted, restarted_fake, _restarted_store, _scope = _restart(
        config, config_path, case="provider_rejection"
    )
    replay = _start(restarted)

    assert replay["task_id"] == task.task_id
    assert replay["state"] == "completed"
    assert restarted_fake.provider_create_calls == 0
    assert (
        restarted.get_result(task.task_id, project_id=PROJECT_ID)["result_available"]
        is True
    )


def test_backend_restart_can_publish_result_before_task_observes_terminal_state(
    tmp_path: Path,
) -> None:
    manager, fake, _store, config, config_path = _fresh(
        tmp_path, case="result_publication"
    )
    running = _start(manager)
    assert running["state"] == "running"
    assert fake.provider_create_calls == 1

    restarted, restarted_fake, _store2, _scope = _restart(
        config, config_path, case="provider_rejection"
    )
    before = restarted.get_status(running["task_id"], project_id=PROJECT_ID)
    assert before["state"] == "running"
    assert restarted_fake.provider_create_calls == 0

    published = restarted_fake.publish_scripted_result(running["backend_reference"])
    assert published.provider_terminal_claim == "success"
    after = restarted.get_status(running["task_id"], project_id=PROJECT_ID)

    assert after["state"] == "completed"
    assert after["result_available"] is True
    assert restarted_fake.provider_create_calls == 0


def test_cancellation_during_reconnect_delegates_once_to_recovered_backend(
    tmp_path: Path,
) -> None:
    manager, fake, _store, config, config_path = _fresh(tmp_path, case="long_running")
    running = _start(manager)
    assert running["state"] == "running"
    assert fake.provider_create_calls == 1

    restarted, restarted_fake, _store2, _scope = _restart(
        config, config_path, case="provider_rejection"
    )
    status = restarted.get_status(running["task_id"], project_id=PROJECT_ID)
    cancelled = restarted.cancel_task(
        running["task_id"],
        if_state_version=status["state_version"],
        project_id=PROJECT_ID,
        reason="cancel after reconnect",
    )

    assert cancelled["state"] == "cancelled"
    assert restarted_fake.provider_cancel_calls == 1
    assert restarted_fake.provider_create_calls == 0


def test_ambiguous_create_restart_never_resubmits_and_cancel_stays_uncertain(
    tmp_path: Path,
) -> None:
    manager, fake, _store, config, config_path = _fresh(tmp_path, case="ambiguous_ack")
    first = _start(manager)
    assert first["state"] == "recovery_pending"
    assert fake.provider_create_calls == 1

    restarted, restarted_fake, _store2, _scope = _restart(
        config, config_path, case="success"
    )
    replay = _start(restarted)
    assert replay["state"] == "recovery_pending"
    assert restarted_fake.provider_create_calls == 0

    status = restarted.get_status(replay["task_id"], project_id=PROJECT_ID)
    cancelled = restarted.cancel_task(
        replay["task_id"],
        if_state_version=status["state_version"],
        project_id=PROJECT_ID,
        reason="cancel uncertain provider create",
    )
    assert cancelled["state"] == "recovery_pending"
    assert restarted_fake.provider_cancel_calls == 0


def test_duplicate_and_conflicting_controller_requests_remain_deterministic(
    tmp_path: Path,
) -> None:
    manager, fake, _store, _config_value, _config_path = _fresh(
        tmp_path, case="success"
    )
    first = _start(manager)
    replay = _start(manager)
    conflict = _start(manager, spec=_spec(route_marker="9"))

    assert replay["task_id"] == first["task_id"]
    assert replay["idempotent_replay"] is True
    assert conflict["ok"] is False
    assert conflict["error_code"] == "controller_request_hash_conflict"
    assert fake.provider_create_calls == 1


def test_invalid_result_contract_survives_restart_as_failure_not_success(
    tmp_path: Path,
) -> None:
    manager, _fake, _store, config, config_path = _fresh(
        tmp_path, case="malformed_output"
    )
    failed = _start(manager)
    assert failed["state"] == "failed"
    assert failed["result_available"] is False

    restarted, restarted_fake, _store2, _scope = _restart(
        config, config_path, case="success"
    )
    recovered = restarted.get_status(failed["task_id"], project_id=PROJECT_ID)
    result = restarted.get_result(failed["task_id"], project_id=PROJECT_ID)

    assert recovered["state"] == "failed"
    assert result["result_available"] is False
    assert restarted_fake.provider_create_calls == 0


def test_bounded_result_reference_is_stable_across_restart_and_retry(
    tmp_path: Path,
) -> None:
    manager, _fake, _store, config, config_path = _fresh(tmp_path, case="success")
    completed = _start(manager)
    first = manager.get_result(completed["task_id"], project_id=PROJECT_ID)

    restarted, restarted_fake, _store2, _scope = _restart(
        config, config_path, case="provider_rejection"
    )
    second = restarted.get_result(completed["task_id"], project_id=PROJECT_ID)
    third = restarted.get_result(completed["task_id"], project_id=PROJECT_ID)

    assert second["result_source"] == first["result_source"]
    assert third["result_source"] == first["result_source"]
    assert "transcript" not in second["result_source"]
    assert restarted_fake.provider_create_calls == 0
