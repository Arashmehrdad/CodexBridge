from __future__ import annotations

import json
from typing import Any

from soma.gateway_models import RunListQuery, RunResultQuery, RunStatusQuery
from soma.job_manager import JobManager
from soma.run_query_chunks import RUN_QUERY_CHUNK_CHARACTERS


RUN_ID = "20260714T000000Z_project_command_12345678"


class FakeRunStore:
    def __init__(self, run: dict[str, Any]) -> None:
        self.run = run

    def get_run(self, run_id: str) -> dict[str, Any]:
        if run_id != self.run["run_id"]:
            raise KeyError(run_id)
        return dict(self.run)

    def list_runs(
        self,
        repo_name: str | None = None,
        status: str | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        del repo_name, status
        return [dict(self.run)][:limit]


def make_run(detail: str) -> dict[str, Any]:
    return {
        "run_id": RUN_ID,
        "repo_name": "soma",
        "tool": "project_command",
        "status": "completed",
        "current_phase": "result",
        "created_at": "2026-07-14T00:00:00+00:00",
        "started_at": "2026-07-14T00:00:01+00:00",
        "ended_at": "2026-07-14T00:01:00+00:00",
        "duration_seconds": 59.0,
        "exit_code": 0,
        "summary": "done",
        "error": "",
        "safety_failure": False,
        "input": {
            "detail": detail,
            "api_token": "secret-token-value",
            "message": "token: another-secret-value",
        },
        "result": {
            "run_id": RUN_ID,
            "status": "completed",
            "detail": detail,
        },
        "progress": {},
        "worker_lease_token": "must-never-be-public",
    }


def make_manager(run: dict[str, Any]) -> JobManager:
    manager = object.__new__(JobManager)
    manager.store = FakeRunStore(run)
    return manager


def collect_status(manager: JobManager) -> dict[str, Any]:
    cursor = ""
    chunks: list[str] = []
    while True:
        request = RunStatusQuery(
            operation="status",
            run_id=RUN_ID,
            cursor=cursor,
        )
        response = manager.get_status(request.run_id)
        assert response["transport"] == "chunked_json"
        chunks.append(response["chunk"])
        if response["complete"]:
            break
        cursor = response["next_cursor"]
        assert cursor
    return json.loads("".join(chunks))


def test_large_status_round_trips_without_total_data_loss() -> None:
    detail = "x" * (RUN_QUERY_CHUNK_CHARACTERS * 2 + 73)
    payload = collect_status(make_manager(make_run(detail)))

    assert payload["input"]["detail"] == detail
    assert payload["input"]["api_token"] == "[REDACTED]"
    assert payload["input"]["message"] == "token=[REDACTED]"
    assert "worker_lease_token" not in payload


def test_status_cursor_uses_frozen_snapshot_when_run_changes() -> None:
    original_detail = "x" * (RUN_QUERY_CHUNK_CHARACTERS + 50)
    run = make_run(original_detail)
    manager = make_manager(run)
    first_request = RunStatusQuery(operation="status", run_id=RUN_ID)
    first = manager.get_status(first_request.run_id)
    assert first["complete"] is False

    run["input"]["detail"] = "y" * (RUN_QUERY_CHUNK_CHARACTERS + 50)
    chunks = [first["chunk"]]
    cursor = first["next_cursor"]
    while cursor:
        next_request = RunStatusQuery(
            operation="status",
            run_id=RUN_ID,
            cursor=cursor,
        )
        response = manager.get_status(next_request.run_id)
        chunks.append(response["chunk"])
        cursor = response["next_cursor"]

    reconstructed = json.loads("".join(chunks))
    assert reconstructed["input"]["detail"] == original_detail


def test_small_public_status_stays_inline_and_redacted() -> None:
    manager = make_manager(make_run("small"))
    request = RunStatusQuery(operation="status", run_id=RUN_ID)

    response = manager.get_status(request.run_id)

    assert response["run_id"] == RUN_ID
    assert response["input"]["api_token"] == "[REDACTED]"
    assert response["_transport"]["mode"] == "inline"
    assert response["_transport"]["complete"] is True


def test_large_result_uses_same_cursor_contract() -> None:
    detail = "r" * (RUN_QUERY_CHUNK_CHARACTERS + 91)
    manager = make_manager(make_run(detail))
    cursor = ""
    chunks: list[str] = []

    while True:
        request = RunResultQuery(
            operation="result",
            run_id=RUN_ID,
            cursor=cursor,
        )
        response = manager.get_result(request.run_id)
        chunks.append(response["chunk"])
        if response["complete"]:
            break
        cursor = response["next_cursor"]

    assert json.loads("".join(chunks))["detail"] == detail


def test_large_list_returns_one_bounded_transport_item_per_call() -> None:
    detail = "z" * (RUN_QUERY_CHUNK_CHARACTERS + 200)
    manager = make_manager(make_run(detail))
    cursor = ""
    chunks: list[str] = []

    while True:
        request = RunListQuery(operation="list", limit=1, cursor=cursor)
        response = manager.list_runs(
            request.repo_name,
            request.status,
            request.limit,
        )
        assert len(response) == 1
        transport = response[0]
        assert transport["transport"] == "chunked_json"
        chunks.append(transport["chunk"])
        if transport["complete"]:
            break
        cursor = transport["next_cursor"]

    reconstructed = json.loads("".join(chunks))
    assert reconstructed[0]["input"]["detail"] == detail
    assert reconstructed[0]["input"]["api_token"] == "[REDACTED]"


def test_internal_status_reader_keeps_legacy_shape() -> None:
    manager = make_manager(make_run("small"))

    response = manager.get_status(RUN_ID)

    assert response["run_id"] == RUN_ID
    assert "_transport" not in response
