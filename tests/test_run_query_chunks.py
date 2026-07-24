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

    def get_run_input_snapshot(self, run_id: str) -> dict[str, Any]:
        run = self.get_run(run_id)
        raw = json.dumps(run["input"], sort_keys=True)
        return {
            "run_id": run_id,
            "repo_name": run["repo_name"],
            "tool": run["tool"],
            "status": run["status"],
            "state_version": 7,
            "input_json": raw,
            "input": dict(run["input"]),
        }

    def get_run_control_observation(self, run_id: str):
        return self.get_run(run_id), None

    def get_run_control_snapshot(self, run_id: str):
        return self.get_run(run_id)

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
        "state_version": 7,
        "risk_level": "high",
        "requires_human": False,
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


class FakeLocks:
    def find_lock(self, repo_name: str, run_id: str) -> dict[str, Any]:
        del repo_name, run_id
        return {}


def make_manager(run: dict[str, Any]) -> JobManager:
    manager = object.__new__(JobManager)
    manager.store = FakeRunStore(run)
    manager.locks = FakeLocks()
    return manager


def test_compact_lifecycle_status_omits_submitted_and_result_payloads() -> None:
    detail = "x" * (RUN_QUERY_CHUNK_CHARACTERS * 2 + 73)
    manager = make_manager(make_run(detail))
    request = RunStatusQuery(operation="status", run_id=RUN_ID)

    response = manager.get_lifecycle_status(request.run_id)
    serialized = json.dumps(response)

    assert response["operation"] == "status"
    assert response["run_id"] == RUN_ID
    assert response["state_version"] == 7
    assert response["details_available"]["input"] is True
    assert response["payload_bytes"] <= 8192
    assert "input" not in response
    assert "result" not in response
    assert detail[:100] not in serialized
    assert "secret-token-value" not in serialized


def test_internal_full_status_reader_remains_redacted_for_compatibility() -> None:
    manager = make_manager(make_run("small"))
    response = manager.get_status(RUN_ID)
    assert response["run_id"] == RUN_ID
    assert response["input"]["api_token"] == "[REDACTED]"
    assert "worker_lease_token" not in response


def test_explicit_input_round_trips_large_payload_and_redacts_secrets() -> None:
    detail = "i" * (RUN_QUERY_CHUNK_CHARACTERS * 2 + 99)
    manager = make_manager(make_run(detail))
    cursor = ""
    chunks: list[str] = []
    while True:
        response = manager.get_input(RUN_ID, view="full", cursor=cursor)
        chunks.append(response["chunk"])
        if response["complete"]:
            break
        cursor = response["next_cursor"]
    payload = json.loads("".join(chunks))
    assert payload["input"]["detail"] == detail
    assert payload["input"]["api_token"] == "[REDACTED]"
    assert payload["complete_authoritative_input_preserved"] is True


def test_compact_input_returns_hashes_not_values() -> None:
    manager = make_manager(make_run("submitted-secret-marker"))
    response = manager.get_input(RUN_ID)
    serialized = json.dumps(response)
    assert response["operation"] == "input"
    assert response["authoritative_input_bytes"] > 0
    assert len(response["authoritative_input_sha256"]) == 64
    assert "submitted-secret-marker" not in serialized
    assert "secret-token-value" not in serialized
    assert response["has_more"] is True


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
