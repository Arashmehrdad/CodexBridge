from __future__ import annotations

import asyncio
import json
import sqlite3
import threading
from hashlib import sha256
from pathlib import Path

import pytest

import soma.server as server
from soma.config import AppConfig, load_config
from soma.gateway_models import (
    RunEventsQuery,
    RunInputQuery,
    RunOutputQuery,
    RunResultQuery,
    RunStatusQuery,
    RunTerminalQuery,
    TaskDurableCommandStart,
)
from soma.project_scope import ProjectScopeError, ProjectScopeStore
from soma.project_scope.schema import (
    PROJECT_SCOPE_MIGRATIONS,
    PROJECT_SCOPE_TABLE_NAMES,
    apply_project_scope_migrations,
)
from soma.run_store import RunStore
from soma.tasks.backends import BackendObservation
from soma.tasks.manager import TaskManager
from soma.tasks.models import (
    BackendKind,
    TaskKind,
    make_task_id,
    normalize_durable_command_request,
    normalized_request_hash,
    run_input_reference,
)
from soma.tasks.store import TaskStore


PROJECT_ALPHA = "Project_Alpha"
PROJECT_BETA = "Project_Beta"
RESOURCE_REPOSITORY = "Resource_Soma"


def _make_config(tmp_path: Path) -> tuple[AppConfig, Path, Path]:
    repo = tmp_path / "repo"
    repo.mkdir(parents=True)
    (repo / ".git").mkdir()
    executable = tmp_path / "fake-pwsh.exe"
    executable.write_bytes(b"scope-fixture")
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


def _bootstrap(
    scope: ProjectScopeStore,
    repo: Path,
    *,
    project_id: str = PROJECT_ALPHA,
    project_key: str = "alpha",
    resource_id: str = RESOURCE_REPOSITORY,
    access_mode: str = "exclusive",
) -> None:
    result = scope.apply_bootstrap(
        project_id=project_id,
        project_key=project_key,
        resource_id=resource_id,
        repo_name="sample",
        repository_root=repo,
        access_mode=access_mode,
    )
    assert result["applied"] is True


class StoredRunBackend:
    kind = BackendKind.SOMA_DURABLE_RUN.value
    executor = "executable_profile"

    def __init__(self, runs_dir: Path):
        self.store = RunStore(runs_dir)
        self.counter = 0
        self.started: list[str] = []
        self.queried: list[str] = []
        self.cancelled: list[str] = []

    def reserve(self) -> str:
        self.counter += 1
        return f"20260727T050000Z_executable_profile_{self.counter:08x}"

    def start(self, spec, backend_ref: str) -> dict:
        self.started.append(backend_ref)
        run_dir = self.store.runs_dir / backend_ref
        run_dir.mkdir(parents=True)
        self.store.create_run(
            run_id=backend_ref,
            repo_name=spec.repo_name,
            tool=self.executor,
            run_dir=run_dir,
            input_data={"repo_name": spec.repo_name},
            status="queued",
        )
        return {"accepted": True, "run_id": backend_ref, "status": "queued"}

    def query(self, backend_ref: str) -> BackendObservation:
        self.queried.append(backend_ref)
        try:
            run = self.store.get_run(backend_ref)
        except KeyError:
            return BackendObservation(exists=False, error_code="not_found")
        return BackendObservation(
            exists=True,
            status=str(run["status"]),
            executor=str(run["tool"]),
            repo_name=str(run["repo_name"]),
            state_version=int(run["state_version"]),
        )

    def cancel(self, backend_ref: str) -> dict:
        self.cancelled.append(backend_ref)
        return {"ok": False, "run_id": backend_ref, "status": "queued"}

    def result_reference(self, backend_ref: str) -> dict:
        return {"available": False, "authority": "durable_run", "run_id": backend_ref}


def test_schema_is_additive_idempotent_empty_and_foreign_key_clean(
    tmp_path: Path,
) -> None:
    runs_dir = tmp_path / "runs"
    run_store = RunStore(runs_dir)
    task_store = TaskStore(runs_dir)
    legacy_run_id = "20260727T040000Z_fixture_aaaaaaaa"
    run_dir = runs_dir / legacy_run_id
    run_dir.mkdir()
    run_store.create_run(
        run_id=legacy_run_id,
        repo_name="sample",
        tool="fixture",
        run_dir=run_dir,
        input_data={"legacy": True},
    )
    legacy_task_id = make_task_id()
    task_store.reserve_task(
        task_id=legacy_task_id,
        task_kind=TaskKind.DURABLE_COMMAND.value,
        controller_request_id="legacy-request",
        request_hash="a" * 64,
        backend_kind=BackendKind.SOMA_DURABLE_RUN.value,
        backend_executor="fixture",
        backend_ref=legacy_run_id,
        backend_identity={},
    )
    with sqlite3.connect(runs_dir / "soma.sqlite3") as scope_connect:
        incumbent_schema_before = {
            row[0]: row[1]
            for row in scope_connect.execute(
                "SELECT name, sql FROM sqlite_master "
                "WHERE type = 'table' AND name IN ('runs', 'tasks')"
            )
        }
    before = sha256(f"{legacy_run_id}\0{legacy_task_id}".encode("utf-8")).hexdigest()

    scope = ProjectScopeStore(runs_dir)
    assert scope.is_installed() is False
    # Every declared version applies in order on a fresh store, and a second
    # call is a no-op. Asserted against the migration list rather than a fixed
    # number so adding an ordered version does not silently weaken this test.
    assert scope.init_db() == [version for version, _name, _sql in PROJECT_SCOPE_MIGRATIONS]
    assert scope.init_db() == []
    assert scope.schema_state()["up_to_date"] is True
    assert set(scope.schema_state()["tables"]) == set(PROJECT_SCOPE_TABLE_NAMES)
    assert all(count == 0 for count in scope.table_counts().values())
    with scope.connect() as conn:
        assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
        run_ids = [row[0] for row in conn.execute("SELECT run_id FROM runs")]
        task_ids = [row[0] for row in conn.execute("SELECT task_id FROM tasks")]
        incumbent_schema_after = {
            row[0]: row[1]
            for row in conn.execute(
                "SELECT name, sql FROM sqlite_master "
                "WHERE type = 'table' AND name IN ('runs', 'tasks')"
            )
        }
    after = sha256(f"{run_ids[0]}\0{task_ids[0]}".encode("utf-8")).hexdigest()
    assert after == before
    assert incumbent_schema_after == incumbent_schema_before
    assert run_store.get_run(legacy_run_id)["run_id"] == legacy_run_id
    assert task_store.get_task(legacy_task_id).task_id == legacy_task_id
    assert scope.scoped_writes_enabled() is False


def test_forced_migration_failure_rolls_back_all_v1_objects(tmp_path: Path) -> None:
    runs_dir = tmp_path / "runs"
    TaskStore(runs_dir)
    scope = ProjectScopeStore(runs_dir)
    version, name, statements = PROJECT_SCOPE_MIGRATIONS[0]
    broken = ((version, name, (*statements, "SELECT * FROM missing_scope_table")),)

    with pytest.raises(sqlite3.OperationalError):
        apply_project_scope_migrations(scope.connect, migrations=broken)

    with scope.connect() as conn:
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' "
            "AND name LIKE 'project_%'"
        ).fetchall()
        marker = conn.execute(
            "SELECT 1 FROM soma_schema_migrations WHERE component = 'project_scope'"
        ).fetchone()
    assert tables == []
    assert marker is None


def test_bootstrap_resolution_is_explicit_exact_and_ambiguity_fails_closed(
    tmp_path: Path,
) -> None:
    config, _config_path, repo = _make_config(tmp_path)
    scope = ProjectScopeStore(config.resolve_runs_dir())
    TaskStore(config.resolve_runs_dir())
    scope.init_db()
    _bootstrap(scope, repo, access_mode="shared")

    explicit = scope.resolve_repository(
        project_id=PROJECT_ALPHA,
        repo_name="SAMPLE",
        repository_root=repo,
    )
    assert explicit.project_id == PROJECT_ALPHA
    assert explicit.resource_id == RESOURCE_REPOSITORY
    with pytest.raises(ProjectScopeError, match="No active repository binding"):
        scope.resolve_repository(
            project_id=PROJECT_ALPHA.lower(),
            repo_name="sample",
            repository_root=repo,
        )

    _bootstrap(
        scope,
        repo,
        project_id=PROJECT_BETA,
        project_key="beta",
        resource_id=RESOURCE_REPOSITORY,
        access_mode="shared",
    )
    with pytest.raises(ProjectScopeError, match="ambiguous"):
        scope.resolve_repository(repo_name="sample", repository_root=repo)
    beta = scope.resolve_repository(
        project_id=PROJECT_BETA,
        repo_name="sample",
        repository_root=repo,
    )
    assert beta.project_id == PROJECT_BETA


def test_exclusive_repository_binding_cannot_be_shared_implicitly(
    tmp_path: Path,
) -> None:
    config, _config_path, repo = _make_config(tmp_path)
    TaskStore(config.resolve_runs_dir())
    scope = ProjectScopeStore(config.resolve_runs_dir())
    scope.init_db()
    _bootstrap(scope, repo)

    preview = scope.preview_bootstrap(
        project_id=PROJECT_BETA,
        project_key="beta",
        resource_id=RESOURCE_REPOSITORY,
        repo_name="sample",
        repository_root=repo,
        access_mode="shared",
    )

    assert preview["ok"] is False
    assert preview["conflicts"] == ["resource_exclusivity_conflict"]


def test_scoped_task_start_replay_and_exact_assertions_are_isolated(
    tmp_path: Path,
) -> None:
    config, config_path, repo = _make_config(tmp_path)
    TaskStore(config.resolve_runs_dir())
    scope = ProjectScopeStore(config.resolve_runs_dir())
    scope.init_db()
    _bootstrap(scope, repo, access_mode="shared")
    scope.set_scoped_writes_enabled(True)
    backend = StoredRunBackend(config.resolve_runs_dir())
    manager = TaskManager(config, config_path, backend=backend, scope_store=scope)
    payload = {
        "controller_request_id": "Scoped-Request",
        "project_id": PROJECT_ALPHA,
        "repo_name": "sample",
        "argv": ["-NoProfile", "-Command", "Write-Output scoped"],
        "working_directory": str(repo),
    }

    first = manager.start_durable_command(**payload)
    replay = manager.start_durable_command(**payload)

    assert first["ok"] is True
    assert first["project_id"] == PROJECT_ALPHA
    assert first["project_attempt_status"] == "attached"
    assert replay["task_id"] == first["task_id"]
    assert replay["idempotent_replay"] is True
    assert backend.started == [first["backend_reference"]]
    assert (
        scope.require_task(PROJECT_ALPHA, first["task_id"]).project_id == PROJECT_ALPHA
    )
    assert (
        scope.require_run(PROJECT_ALPHA, first["backend_reference"]).project_id
        == PROJECT_ALPHA
    )
    denied = manager.get_status(first["task_id"], project_id=PROJECT_BETA)
    assert denied["ok"] is False
    assert denied["error_code"] == "project_scope_mismatch"
    for operation in (
        manager.get_result,
        manager.get_events,
        manager.get_links,
    ):
        denied_read = operation(first["task_id"], project_id=PROJECT_BETA)
        assert denied_read["error_code"] == "project_scope_mismatch"
    denied_cancel = manager.cancel_task(
        first["task_id"],
        project_id=PROJECT_BETA,
        if_state_version=first["state_version"],
    )
    assert denied_cancel["error_code"] == "project_scope_mismatch"
    assert backend.cancelled == []
    assert first["response_bytes"] <= first["response_budget_bytes"]


def test_omitted_project_requires_exactly_one_active_repository_binding(
    tmp_path: Path,
) -> None:
    config, config_path, repo = _make_config(tmp_path)
    TaskStore(config.resolve_runs_dir())
    scope = ProjectScopeStore(config.resolve_runs_dir())
    scope.init_db()
    _bootstrap(scope, repo)
    scope.set_scoped_writes_enabled(True)
    backend = StoredRunBackend(config.resolve_runs_dir())
    manager = TaskManager(config, config_path, backend=backend, scope_store=scope)

    unique = manager.start_durable_command(
        controller_request_id="omitted-unique",
        repo_name="sample",
    )
    assert unique["ok"] is True
    assert unique["project_id"] == PROJECT_ALPHA

    with scope.transaction() as conn:
        conn.execute(
            "UPDATE projects SET lifecycle_state = 'suspended' WHERE project_id = ?",
            (PROJECT_ALPHA,),
        )
    missing = manager.start_durable_command(
        controller_request_id="omitted-missing",
        repo_name="sample",
    )
    assert missing["error_code"] == "project_scope_resolution_failed"


def test_concurrent_scoped_replay_reserves_one_task_attempt_and_run(
    tmp_path: Path,
) -> None:
    config, config_path, repo = _make_config(tmp_path)
    TaskStore(config.resolve_runs_dir())
    scope = ProjectScopeStore(config.resolve_runs_dir())
    scope.init_db()
    _bootstrap(scope, repo)
    scope.set_scoped_writes_enabled(True)
    backend = StoredRunBackend(config.resolve_runs_dir())
    manager = TaskManager(config, config_path, backend=backend, scope_store=scope)
    responses: list[dict] = []

    def start() -> None:
        responses.append(
            manager.start_durable_command(
                controller_request_id="concurrent-scoped",
                project_id=PROJECT_ALPHA,
                repo_name="sample",
                argv=["Write-Output", "same"],
            )
        )

    threads = [threading.Thread(target=start) for _ in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert len(responses) == 4
    assert len({response["task_id"] for response in responses}) == 1
    assert len(backend.started) == 1
    counts = scope.table_counts()
    assert counts["project_task_reservations"] == 1
    assert counts["project_run_attempts"] == 1


def test_scope_and_incumbent_task_are_committed_before_backend_handoff(
    tmp_path: Path,
) -> None:
    config, config_path, repo = _make_config(tmp_path)
    task_store = TaskStore(config.resolve_runs_dir())
    scope = ProjectScopeStore(config.resolve_runs_dir())
    scope.init_db()
    _bootstrap(scope, repo)
    scope.set_scoped_writes_enabled(True)

    class InspectingBackend(StoredRunBackend):
        def start(self, spec, backend_ref: str) -> dict:
            task = task_store.find_by_backend_ref(self.kind, backend_ref)
            assert task is not None
            binding = scope.require_task_attempt(
                PROJECT_ALPHA,
                task.task_id,
                backend_ref,
            )
            assert binding.binding_status == "attached"
            assert binding.attempt_status == "reserved"
            return super().start(spec, backend_ref)

    backend = InspectingBackend(config.resolve_runs_dir())
    manager = TaskManager(
        config,
        config_path,
        backend=backend,
        store=task_store,
        scope_store=scope,
    )
    result = manager.start_durable_command(
        controller_request_id="persist-before-handoff",
        project_id=PROJECT_ALPHA,
        repo_name="sample",
    )

    assert result["ok"] is True, result["backend_launch_error"]
    assert backend.started == [result["backend_reference"]]


def test_active_scope_rejects_unknown_ambiguous_parent_and_external_path(
    tmp_path: Path,
) -> None:
    config, config_path, repo = _make_config(tmp_path)
    TaskStore(config.resolve_runs_dir())
    scope = ProjectScopeStore(config.resolve_runs_dir())
    scope.init_db()
    _bootstrap(scope, repo, access_mode="shared")
    _bootstrap(
        scope,
        repo,
        project_id=PROJECT_BETA,
        project_key="beta",
        resource_id=RESOURCE_REPOSITORY,
        access_mode="shared",
    )
    scope.set_scoped_writes_enabled(True)
    manager = TaskManager(
        config,
        config_path,
        backend=StoredRunBackend(config.resolve_runs_dir()),
        scope_store=scope,
    )

    ambiguous = manager.start_durable_command(
        controller_request_id="ambiguous",
        repo_name="sample",
    )
    assert ambiguous["error_code"] == "project_scope_resolution_failed"
    unknown = manager.start_durable_command(
        controller_request_id="unknown",
        project_id="Project_Missing",
        repo_name="sample",
    )
    assert unknown["error_code"] == "project_scope_resolution_failed"
    external = manager.start_durable_command(
        controller_request_id="external",
        project_id=PROJECT_ALPHA,
        repo_name="sample",
        working_directory=str(tmp_path / "outside"),
    )
    assert external["error_code"] == "project_scope_resolution_failed"

    alpha = manager.start_durable_command(
        controller_request_id="alpha-parent",
        project_id=PROJECT_ALPHA,
        repo_name="sample",
    )
    cross_parent = manager.start_durable_command(
        controller_request_id="beta-child",
        project_id=PROJECT_BETA,
        repo_name="sample",
        parent_task_id=alpha["task_id"],
    )
    assert cross_parent["error_code"] == "project_scope_reservation_failed"


def test_reconciliation_is_deterministic_and_concurrent_safe(tmp_path: Path) -> None:
    config, _config_path, repo = _make_config(tmp_path)
    run_store = RunStore(config.resolve_runs_dir())
    task_store = TaskStore(config.resolve_runs_dir())
    scope = ProjectScopeStore(config.resolve_runs_dir())
    scope.init_db()
    _bootstrap(scope, repo)
    binding = scope.resolve_repository(
        project_id=PROJECT_ALPHA,
        repo_name="sample",
        repository_root=repo,
    )
    task_id = make_task_id()
    run_id = "20260727T060000Z_executable_profile_aaaaaaaa"
    with task_store.transaction() as conn:
        scope.reserve_task_attempt(
            conn,
            binding=binding,
            task_id=task_id,
            run_id=run_id,
        )
        task_store.reserve_task_in_connection(
            conn,
            task_id=task_id,
            task_kind=TaskKind.DURABLE_COMMAND.value,
            controller_request_id="recovery",
            request_hash="b" * 64,
            backend_kind=BackendKind.SOMA_DURABLE_RUN.value,
            backend_executor="executable_profile",
            backend_ref=run_id,
            backend_identity={},
            objective_ref=run_input_reference(run_id),
        )
        scope.attach_task(conn, task_id)

    attach_task_id = make_task_id()
    attach_run_id = "20260727T060001Z_executable_profile_bbbbbbbb"
    attach_run_dir = config.resolve_runs_dir() / attach_run_id
    attach_run_dir.mkdir()
    run_store.create_run(
        run_id=attach_run_id,
        repo_name="sample",
        tool="executable_profile",
        run_dir=attach_run_dir,
        input_data={"recovery": "attach"},
    )
    with task_store.transaction() as conn:
        scope.reserve_task_attempt(
            conn,
            binding=binding,
            task_id=attach_task_id,
            run_id=attach_run_id,
        )
        task_store.reserve_task_in_connection(
            conn,
            task_id=attach_task_id,
            task_kind=TaskKind.DURABLE_COMMAND.value,
            controller_request_id="recovery-attach",
            request_hash="e" * 64,
            backend_kind=BackendKind.SOMA_DURABLE_RUN.value,
            backend_executor="executable_profile",
            backend_ref=attach_run_id,
            backend_identity={},
            objective_ref=run_input_reference(attach_run_id),
        )
        scope.attach_task(conn, attach_task_id)

    results: list[dict] = []
    threads = [
        threading.Thread(target=lambda: results.append(scope.reconcile_startup()))
        for _ in range(2)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert scope.scope_for_run(run_id).attempt_status == "recovery_pending"
    assert scope.scope_for_run(attach_run_id).attempt_status == "attached"
    assert sum(item["changed"] for item in results) == 2


def test_reconciliation_quarantines_orphan_and_contradictory_attachment(
    tmp_path: Path,
) -> None:
    config, _config_path, repo = _make_config(tmp_path)
    RunStore(config.resolve_runs_dir())
    task_store = TaskStore(config.resolve_runs_dir())
    scope = ProjectScopeStore(config.resolve_runs_dir())
    scope.init_db()
    _bootstrap(scope, repo)
    binding = scope.resolve_repository(
        project_id=PROJECT_ALPHA,
        repo_name="sample",
        repository_root=repo,
    )
    orphan_task_id = make_task_id()
    orphan_run_id = "20260727T061000Z_executable_profile_bbbbbbbb"
    with scope.transaction() as conn:
        scope.reserve_task_attempt(
            conn,
            binding=binding,
            task_id=orphan_task_id,
            run_id=orphan_run_id,
        )

    attached_task_id = make_task_id()
    attached_run_id = "20260727T061001Z_executable_profile_cccccccc"
    with task_store.transaction() as conn:
        scope.reserve_task_attempt(
            conn,
            binding=binding,
            task_id=attached_task_id,
            run_id=attached_run_id,
        )
        task_store.reserve_task_in_connection(
            conn,
            task_id=attached_task_id,
            task_kind=TaskKind.DURABLE_COMMAND.value,
            controller_request_id="contradictory",
            request_hash="c" * 64,
            backend_kind=BackendKind.SOMA_DURABLE_RUN.value,
            backend_executor="executable_profile",
            backend_ref=attached_run_id,
            backend_identity={},
        )
        scope.attach_task(conn, attached_task_id)
        conn.execute(
            "UPDATE project_run_attempts SET status = 'attached' WHERE run_id = ?",
            (attached_run_id,),
        )

    result = scope.reconcile_startup()

    assert result["counts"]["task_quarantined"] == 1
    assert result["counts"]["attempt_quarantined"] == 1
    assert scope.scope_for_task(orphan_task_id).binding_status == "quarantined"
    assert scope.scope_for_run(attached_run_id).attempt_status == "quarantined"
    counts = scope.table_counts()
    assert counts["project_scope_quarantine"] == 2


def test_legacy_hash_and_replay_survive_installed_active_scope(tmp_path: Path) -> None:
    config, config_path, repo = _make_config(tmp_path)
    backend = StoredRunBackend(config.resolve_runs_dir())
    manager = TaskManager(config, config_path, backend=backend)
    payload = {
        "controller_request_id": "legacy-before-scope",
        "repo_name": "sample",
        "argv": ["-NoProfile", "-Command", "Write-Output legacy"],
    }
    normalized = normalize_durable_command_request(
        repo_name="sample",
        profile_id="powershell",
        argv=payload["argv"],
    )
    assert normalized_request_hash(normalized) == (
        "10b08e12169fe7a657dca393215f441a51e458c73055423b366f39240b7cca32"
    )
    first = manager.start_durable_command(**payload)

    scope = ProjectScopeStore(config.resolve_runs_dir())
    scope.init_db()
    _bootstrap(scope, repo)
    scope.set_scoped_writes_enabled(True)
    restarted = TaskManager(config, config_path, backend=backend, scope_store=scope)
    replay = restarted.start_durable_command(**payload)

    assert replay["task_id"] == first["task_id"]
    assert replay["idempotent_replay"] is True
    assert replay["project_binding_status"] == "legacy_unassigned"


def test_mcp_models_are_strict_additive_and_run_guard_checks_base_reference(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    start_schema = TaskDurableCommandStart.model_json_schema()
    assert "project_id" in start_schema["properties"]
    assert "project_id" not in start_schema["required"]
    assert start_schema["additionalProperties"] is False
    incumbent = TaskDurableCommandStart.model_validate(
        {
            "operation": "start",
            "controller_request_id": "incumbent",
            "repo_name": "sample",
        }
    )
    assert incumbent.project_id == ""

    config, config_path, repo = _make_config(tmp_path)
    TaskStore(config.resolve_runs_dir())
    scope = ProjectScopeStore(config.resolve_runs_dir())
    scope.init_db()
    _bootstrap(scope, repo)
    scope.set_scoped_writes_enabled(True)
    backend = StoredRunBackend(config.resolve_runs_dir())
    manager = TaskManager(config, config_path, backend=backend, scope_store=scope)
    started = manager.start_durable_command(
        controller_request_id="run-guard",
        project_id=PROJECT_ALPHA,
        repo_name="sample",
    )
    monkeypatch.setattr(server, "_config", config)
    monkeypatch.setattr(server, "_config_path", config_path)

    allowed = server.run_query(
        RunStatusQuery(
            operation="status",
            run_id=started["backend_reference"],
            project_id=PROJECT_ALPHA,
        )
    )
    denied = server.run_query(
        RunStatusQuery(
            operation="status",
            run_id=started["backend_reference"],
            project_id=PROJECT_BETA,
        )
    )
    denied_input = server.run_query(
        RunInputQuery(
            operation="input",
            run_id=started["backend_reference"],
            project_id=PROJECT_BETA,
        )
    )
    denied_output = server.run_query(
        RunOutputQuery(
            operation="output",
            run_id=started["backend_reference"],
            project_id=PROJECT_BETA,
        )
    )

    assert allowed["project_id"] == PROJECT_ALPHA
    assert allowed["project_attempt_status"] == "attached"
    assert denied["error_code"] == "project_scope_mismatch"
    assert denied_input["error_code"] == "project_scope_mismatch"
    assert denied_output["error_code"] == "project_scope_mismatch"

    encoded = RunResultQuery(
        operation="result",
        run_id=started["backend_reference"],
        project_id=PROJECT_ALPHA,
        cursor="next-page",
    )
    guard_error, encoded_scope = server._run_scope_guard(encoded)
    assert guard_error is None
    assert encoded_scope["project_id"] == PROJECT_ALPHA


def test_cross_project_replays_do_not_disclose_task_or_run_identity(
    tmp_path: Path,
) -> None:
    config, config_path, repo = _make_config(tmp_path)
    TaskStore(config.resolve_runs_dir())
    scope = ProjectScopeStore(config.resolve_runs_dir())
    scope.init_db()
    _bootstrap(scope, repo, access_mode="shared")
    scope.set_scoped_writes_enabled(True)
    backend = StoredRunBackend(config.resolve_runs_dir())
    manager = TaskManager(config, config_path, backend=backend, scope_store=scope)
    alpha = manager.start_durable_command(
        controller_request_id="shared-controller-request",
        project_id=PROJECT_ALPHA,
        repo_name="sample",
        argv=["Write-Output", "alpha"],
    )

    _bootstrap(
        scope,
        repo,
        project_id=PROJECT_BETA,
        project_key="beta",
        resource_id=RESOURCE_REPOSITORY,
        access_mode="shared",
    )
    omitted_replay = manager.start_durable_command(
        controller_request_id="shared-controller-request",
        repo_name="sample",
        argv=["Write-Output", "alpha"],
    )
    denied = manager.start_durable_command(
        controller_request_id="shared-controller-request",
        project_id=PROJECT_BETA,
        repo_name="sample",
        argv=["Write-Output", "different"],
    )

    assert omitted_replay["task_id"] == alpha["task_id"]
    assert omitted_replay["project_id"] == PROJECT_ALPHA
    assert denied["error_code"] == "controller_request_scope_conflict"
    assert {
        "task_id",
        "backend_reference",
        "existing_request_hash",
        "submitted_request_hash",
    }.isdisjoint(denied)


def test_concurrent_cross_project_request_has_one_winner_and_no_identity_leak(
    tmp_path: Path,
) -> None:
    config, config_path, repo = _make_config(tmp_path)
    TaskStore(config.resolve_runs_dir())
    scope = ProjectScopeStore(config.resolve_runs_dir())
    scope.init_db()
    _bootstrap(scope, repo, access_mode="shared")
    _bootstrap(
        scope,
        repo,
        project_id=PROJECT_BETA,
        project_key="beta",
        resource_id=RESOURCE_REPOSITORY,
        access_mode="shared",
    )
    scope.set_scoped_writes_enabled(True)
    backend = StoredRunBackend(config.resolve_runs_dir())
    manager = TaskManager(config, config_path, backend=backend, scope_store=scope)
    barrier = threading.Barrier(2)
    responses: list[dict] = []

    def start(project_id: str) -> None:
        barrier.wait()
        responses.append(
            manager.start_durable_command(
                controller_request_id="cross-project-race",
                project_id=project_id,
                repo_name="sample",
            )
        )

    threads = [
        threading.Thread(target=start, args=(PROJECT_ALPHA,)),
        threading.Thread(target=start, args=(PROJECT_BETA,)),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    successes = [response for response in responses if response.get("ok")]
    conflicts = [
        response
        for response in responses
        if response.get("error_code") == "controller_request_scope_conflict"
    ]
    assert len(successes) == 1
    assert len(conflicts) == 1
    assert len(backend.started) == 1
    assert {"task_id", "backend_reference", "existing_request_hash"}.isdisjoint(
        conflicts[0]
    )


def test_pause_is_irreversible_to_legacy_and_launch_is_revalidated(
    tmp_path: Path,
) -> None:
    config, config_path, repo = _make_config(tmp_path)
    scope = ProjectScopeStore(config.resolve_runs_dir())
    task_store = TaskStore(config.resolve_runs_dir())
    scope.init_db()
    _bootstrap(scope, repo)
    assert scope.schema_state()["enforcement_state"] == "inactive"
    scope.set_scoped_writes_enabled(True)
    assert scope.schema_state()["enforcement_state"] == "enforced"
    scope.set_scoped_writes_enabled(False)
    assert scope.schema_state()["enforcement_state"] == "paused"

    backend = StoredRunBackend(config.resolve_runs_dir())
    manager = TaskManager(
        config,
        config_path,
        backend=backend,
        store=task_store,
        scope_store=scope,
    )
    for project_id in ("", PROJECT_ALPHA):
        denied = manager.start_durable_command(
            controller_request_id=f"paused-{project_id}",
            project_id=project_id,
            repo_name="sample",
        )
        assert denied["error_code"] == "project_scope_paused"
    assert backend.started == []

    class PausingTaskStore(TaskStore):
        def __init__(self, runs_dir: Path, scope_store: ProjectScopeStore):
            super().__init__(runs_dir)
            self.scope_store = scope_store
            self.paused = False

        def append_event(self, task_id: str, **kwargs):
            result = super().append_event(task_id, **kwargs)
            if kwargs.get("stage") == "reserved" and not self.paused:
                self.paused = True
                self.scope_store.set_scoped_writes_enabled(False)
            return result

    scope.set_scoped_writes_enabled(True)
    pausing_store = PausingTaskStore(config.resolve_runs_dir(), scope)
    pausing_backend = StoredRunBackend(config.resolve_runs_dir())
    pausing_manager = TaskManager(
        config,
        config_path,
        backend=pausing_backend,
        store=pausing_store,
        scope_store=scope,
    )
    rejected_launch = pausing_manager.start_durable_command(
        controller_request_id="pause-before-launch",
        project_id=PROJECT_ALPHA,
        repo_name="sample",
    )

    assert rejected_launch["ok"] is False
    assert "paused before launch" in rejected_launch["backend_launch_error"]
    assert pausing_backend.started == []


def test_task_backend_reference_mismatch_fails_closed_and_is_quarantined(
    tmp_path: Path,
) -> None:
    config, config_path, repo = _make_config(tmp_path)
    task_store = TaskStore(config.resolve_runs_dir())
    scope = ProjectScopeStore(config.resolve_runs_dir())
    scope.init_db()
    _bootstrap(scope, repo)
    scope.set_scoped_writes_enabled(True)
    backend = StoredRunBackend(config.resolve_runs_dir())
    manager = TaskManager(
        config,
        config_path,
        backend=backend,
        store=task_store,
        scope_store=scope,
    )
    started = manager.start_durable_command(
        controller_request_id="backend-ref-integrity",
        project_id=PROJECT_ALPHA,
        repo_name="sample",
    )
    backend.queried.clear()
    with task_store.transaction() as conn:
        conn.execute(
            "UPDATE tasks SET backend_ref = ? WHERE task_id = ?",
            ("20260727T070000Z_executable_profile_ffffffff", started["task_id"]),
        )

    denied = manager.get_status(started["task_id"], project_id=PROJECT_ALPHA)
    assert denied["error_code"] == "project_scope_mismatch"
    assert backend.queried == []

    reconciled = scope.reconcile_startup()
    assert reconciled["counts"]["attempt_quarantined"] == 1
    assert scope.scope_for_task(started["task_id"]).binding_status == "quarantined"
    assert scope.scope_for_run(started["backend_reference"]).attempt_status == (
        "quarantined"
    )


def test_scoped_projection_authority_budgets_and_task_matrix(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config, config_path, repo = _make_config(tmp_path)
    TaskStore(config.resolve_runs_dir())
    scope = ProjectScopeStore(config.resolve_runs_dir())
    scope.init_db()
    _bootstrap(scope, repo)
    scope.set_scoped_writes_enabled(True)
    backend = StoredRunBackend(config.resolve_runs_dir())
    manager = TaskManager(config, config_path, backend=backend, scope_store=scope)
    started = manager.start_durable_command(
        controller_request_id="projection-matrix",
        project_id=PROJECT_ALPHA,
        repo_name="sample",
    )
    task_responses = [
        started,
        manager.capabilities(),
        manager.get_status(started["task_id"], project_id=PROJECT_ALPHA),
        manager.get_result(started["task_id"], project_id=PROJECT_ALPHA),
        manager.get_events(started["task_id"], project_id=PROJECT_ALPHA),
        manager.get_links(started["task_id"], project_id=PROJECT_ALPHA),
        manager.cancel_task(
            started["task_id"],
            project_id=PROJECT_ALPHA,
            if_state_version=started["state_version"],
        ),
    ]
    for response in task_responses:
        assert response["response_bytes"] == len(
            json.dumps(response, ensure_ascii=False).encode("utf-8")
        )
        assert response["response_bytes"] <= response["response_budget_bytes"]

    monkeypatch.setattr(server, "_config", config)
    monkeypatch.setattr(server, "_config_path", config_path)
    run_id = started["backend_reference"]
    run_requests = [
        RunStatusQuery(operation="status", run_id=run_id, project_id=PROJECT_ALPHA),
        RunInputQuery(operation="input", run_id=run_id, project_id=PROJECT_ALPHA),
        RunOutputQuery(operation="output", run_id=run_id, project_id=PROJECT_ALPHA),
        RunEventsQuery(operation="events", run_id=run_id, project_id=PROJECT_ALPHA),
        RunTerminalQuery(operation="terminal", run_id=run_id, project_id=PROJECT_ALPHA),
        RunResultQuery(operation="result", run_id=run_id, project_id=PROJECT_ALPHA),
    ]
    for request in run_requests:
        response = server.run_query(request)
        assert response["project_id"] == PROJECT_ALPHA
        if "byte_budget" in response:
            # `public_schema_hash` is stamped by the response wrapper after
            # byte accounting has already run, unlike the three legacy
            # capability tags which are counted. Excluding only that field
            # keeps this assertion exactly as strict as it was.
            encoded = json.dumps(
                {
                    key: value
                    for key, value in response.items()
                    if key != "public_schema_hash"
                },
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            ).encode("utf-8")
            assert response["payload_bytes"] == len(encoded)
            assert response["payload_bytes"] <= response["byte_budget"]
        if "response_budget_bytes" in response:
            encoded = json.dumps(
                {
                    key: value
                    for key, value in response.items()
                    if key != "public_schema_hash"
                },
                ensure_ascii=False,
            ).encode("utf-8")
            assert response["response_bytes"] == len(encoded)
            assert response["response_bytes"] <= response["response_budget_bytes"]

    protected_hash = "d" * 64
    authoritative = server._add_run_scope_projection(
        RunStatusQuery(operation="status", run_id=run_id),
        {
            "project_id": PROJECT_ALPHA,
            "resource_id": RESOURCE_REPOSITORY,
            "project_binding_status": "attached",
        },
        {
            "ok": True,
            "project_id": "Spoofed_Project",
            "source_result_sha256": protected_hash,
            "byte_budget": 4096,
            "payload_bytes": 0,
        },
    )
    assert authoritative["project_id"] == PROJECT_ALPHA
    assert authoritative["source_result_sha256"] == protected_hash


def test_actual_mcp_schema_is_strict_additive_stable_and_wrapper_compatible(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config, config_path, _repo = _make_config(tmp_path)
    monkeypatch.setattr(server, "_config", config)
    monkeypatch.setattr(server, "_config_path", config_path)

    async def discover():
        return {tool.name: tool for tool in await server.mcp.list_tools()}

    tools = asyncio.run(discover())
    snapshots: list[str] = []
    exact_operations = {
        "run_query": {
            "status",
            "input",
            "control",
            "output",
            "events",
            "terminal",
            "result",
            "summary",
        },
        "task_query": {"status", "result", "events", "links"},
        "task_action": {"start", "cancel"},
    }
    for tool_name, operations in exact_operations.items():
        schema = tools[tool_name].parameters
        snapshots.append(json.dumps(schema, sort_keys=True, separators=(",", ":")))
        branches = schema["oneOf"]
        for branch in branches:
            operation = branch["properties"]["operation"].get("const")
            if operation not in operations:
                continue
            assert "project_id" in branch["properties"]
            assert "project_id" not in branch["required"]
            assert branch["additionalProperties"] is False
            assert "default" not in branch["properties"]["project_id"]

    rediscovered = asyncio.run(discover())
    assert [
        json.dumps(
            rediscovered[name].parameters,
            sort_keys=True,
            separators=(",", ":"),
        )
        for name in exact_operations
    ] == snapshots

    flat = asyncio.run(tools["task_query"].run({"operation": "capabilities"}))
    wrapped = asyncio.run(
        tools["task_query"].run({"request": {"operation": "capabilities"}})
    )
    assert flat.structured_content == wrapped.structured_content
