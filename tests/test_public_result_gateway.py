from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import TypeAdapter, ValidationError

import codexbridge.server as server
from codexbridge.config import AppConfig, RepoConfig
from codexbridge.gateway_models import RunQueryRequest
from codexbridge.job_manager import JobManager
from codexbridge.public_projection_contract import DEFAULT_PUBLIC_BYTE_BUDGETS
from codexbridge.run_public_result import (
    PUBLIC_RESULT_STATUS_READY,
    canonical_public_json_bytes,
)
from codexbridge.run_publication import publish_run_result
from codexbridge.run_store import utc_now


RUN_ID = "20260722T043000Z_project_command_facefeed"


def _manager(tmp_path: Path) -> JobManager:
    config = AppConfig(
        repos={"sample": RepoConfig(path=str(tmp_path))},
        runs_dir=str(tmp_path / "runs"),
        config_dir=tmp_path,
    )
    return JobManager(config, None)


def _create_run(manager: JobManager, tmp_path: Path) -> str:
    run_dir = tmp_path / "runs" / RUN_ID
    run_dir.mkdir(parents=True)
    manager.store.create_run(
        run_id=RUN_ID,
        repo_name="sample",
        tool="project_command",
        run_dir=run_dir,
        input_data={"repo_name": "sample", "command_id": "pytest"},
    )
    return RUN_ID


def _complete(manager: JobManager, run_id: str) -> None:
    current = manager.store.get_run(run_id)
    transitioned = manager.store.transition_terminal(
        run_id,
        status="completed",
        result={
            "status": "completed",
            "classification": "success",
            "process_success": True,
            "summary": "gateway complete",
            "stdout": "archive-only output",
            "changed_files": ["codexbridge/server.py"],
        },
        expected_statuses=("queued",),
        expected_state_version=current["state_version"],
        ended_at=utc_now(),
        summary="gateway complete",
    )
    assert transitioned is not None


def _assert_bounded(response: dict) -> None:
    serialized = canonical_public_json_bytes(response)
    assert response["payload_bytes"] == len(serialized)
    assert len(serialized) <= DEFAULT_PUBLIC_BYTE_BUDGETS.terminal_result


def test_nonterminal_gateway_returns_bounded_pending_envelope(tmp_path: Path) -> None:
    manager = _manager(tmp_path)
    run_id = _create_run(manager, tmp_path)

    response = manager.get_terminal_result(run_id)

    assert response["operation"] == "terminal"
    assert response["result_available"] is False
    assert response["projection_status"] == "pending"
    assert response["result"]["outcome"] == "pending"
    assert response["evidence"]["authoritative_operation"] == "control"
    _assert_bounded(response)


def test_current_projection_uses_bounded_snapshot_without_source_json(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manager = _manager(tmp_path)
    run_id = _create_run(manager, tmp_path)
    _complete(manager, run_id)
    assert publish_run_result(manager.store, run_id)["ok"] is True
    expected = manager.store.get_run(run_id)["public_result"]

    def forbidden_source_read(_run_id: str) -> dict:
        raise AssertionError("authoritative result_json must not be selected")

    monkeypatch.setattr(
        manager.store, "get_result_source_snapshot", forbidden_source_read
    )
    response = manager.get_terminal_result(run_id)

    assert response == expected
    assert response["projection_status"] == PUBLIC_RESULT_STATUS_READY
    assert b"archive-only output" not in canonical_public_json_bytes(response)
    _assert_bounded(response)


def test_legacy_terminal_projection_materializes_once_then_reuses(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manager = _manager(tmp_path)
    run_id = _create_run(manager, tmp_path)
    _complete(manager, run_id)
    before = manager.store.get_run(run_id)

    first = manager.get_terminal_result(run_id)
    after_first = manager.store.get_run(run_id)

    def forbidden_source_read(_run_id: str) -> dict:
        raise AssertionError("second compact read must reuse public_result_json")

    monkeypatch.setattr(
        manager.store, "get_result_source_snapshot", forbidden_source_read
    )
    second = manager.get_terminal_result(run_id)
    after_second = manager.store.get_run(run_id)

    assert first == second
    assert first["projection_status"] == PUBLIC_RESULT_STATUS_READY
    assert after_first["state_version"] == before["state_version"] + 1
    assert after_second["state_version"] == after_first["state_version"]
    _assert_bounded(first)


def test_terminal_model_and_gateway_are_additive_and_strict(monkeypatch) -> None:
    calls: list[str] = []

    class FakeJobs:
        def get_terminal_result(self, run_id: str) -> dict:
            calls.append(run_id)
            return {"ok": True, "operation": "terminal", "run_id": run_id}

    monkeypatch.setattr(server, "get_job_manager", lambda: FakeJobs())
    adapter = TypeAdapter(RunQueryRequest)
    terminal = adapter.validate_python(
        {"operation": "terminal", "run_id": "run_1"}
    )
    legacy = adapter.validate_python(
        {"operation": "result", "run_id": "run_1", "cursor": "opaque"}
    )

    assert server.run_query(terminal)["operation"] == "terminal"
    assert calls == ["run_1"]
    assert legacy.operation == "result"
    with pytest.raises(ValidationError):
        adapter.validate_python(
            {"operation": "terminal", "run_id": "run_1", "cursor": "not-allowed"}
        )


def test_result_defaults_to_bounded_projection_and_full_view_is_explicit(monkeypatch) -> None:
    calls: list[tuple[str, str]] = []

    class FakeJobs:
        def get_terminal_result(self, run_id: str) -> dict:
            calls.append(("terminal", run_id))
            return {"operation": "terminal", "run_id": run_id}

        def get_result(self, run_id: str) -> dict:
            calls.append(("result", run_id))
            return {"operation": "result", "run_id": run_id, "detail": "full"}

    monkeypatch.setattr(server, "get_job_manager", lambda: FakeJobs())
    adapter = TypeAdapter(RunQueryRequest)
    compact = adapter.validate_python({"operation": "result", "run_id": "run_1"})
    full = adapter.validate_python(
        {"operation": "result", "run_id": "run_1", "view": "full"}
    )

    assert server.run_query(compact)["operation"] == "terminal"
    assert server.run_query(full)["operation"] == "result"
    assert [kind for kind, _run_id in calls] == ["terminal", "result"]
