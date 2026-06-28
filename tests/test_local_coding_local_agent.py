from __future__ import annotations

from codexbridge.local_agent import LocalAgentOrchestrator, LocalAgentTaskType
from codexbridge.local_coding import LocalCodingStatus


class FakeLocalCodingManager:
    def __init__(self):
        self.prepared = []

    def prepare_local_edit(self, request):
        self.prepared.append(request)
        return _Dumpable(
            {
                "edit_id": request.edit_id,
                "status": LocalCodingStatus.APPROVAL_REQUIRED.value,
            }
        )

    def get(self, edit_id):
        return _Dumpable(
            {
                "edit_id": edit_id,
                "status": LocalCodingStatus.APPROVAL_REQUIRED.value,
                "approval_request_id": "approval_1",
            }
        )

    def apply_local_edit(self, edit_id, approval_request_id):
        return _Dumpable(
            {
                "edit_id": edit_id,
                "status": LocalCodingStatus.BLOCKED.value,
                "error": "local_coding_apply_disabled",
            }
        )

    def rollback_local_edit(self, edit_id):
        return _Dumpable(
            {"edit_id": edit_id, "status": LocalCodingStatus.ROLLED_BACK.value}
        )

    def list(self):
        return [
            _Dumpable(
                {
                    "edit_id": "local_edit_1",
                    "status": LocalCodingStatus.APPROVAL_REQUIRED.value,
                }
            )
        ]

    def cancel(self, edit_id):
        return _Dumpable(
            {"edit_id": edit_id, "status": LocalCodingStatus.CANCELLED.value}
        )


class _Dumpable:
    def __init__(self, data):
        self.data = data

    def model_dump(self, *args, **kwargs):
        return self.data


def test_local_agent_routes_explicit_local_coding_prepare() -> None:
    manager = FakeLocalCodingManager()
    orchestrator = LocalAgentOrchestrator(local_coding_manager=manager)

    result = orchestrator.handle_task(
        "prepare local edit: replace README.md :: helo => hello"
    )

    assert result.task_type == LocalAgentTaskType.LOCAL_CODING
    assert result.local_coding_result["status"] == "approval_required"
    assert manager.prepared[0].objective == "replace README.md :: helo => hello"


def test_local_agent_does_not_route_ordinary_edit_to_local_coding() -> None:
    manager = FakeLocalCodingManager()
    orchestrator = LocalAgentOrchestrator(local_coding_manager=manager)

    result = orchestrator.handle_task("fix this bug")

    assert result.task_type == LocalAgentTaskType.SOURCE_EDIT
    assert result.local_coding_result is None
    assert manager.prepared == []


def test_local_agent_routes_local_coding_apply_and_rollback() -> None:
    orchestrator = LocalAgentOrchestrator(local_coding_manager=FakeLocalCodingManager())

    apply_result = orchestrator.handle_task("apply local edit local_edit_1")
    rollback_result = orchestrator.handle_task("rollback local edit local_edit_1")
    list_result = orchestrator.handle_task("list local edits")

    assert apply_result.local_coding_result["error"] == "local_coding_apply_disabled"
    assert rollback_result.local_coding_result["status"] == "rolled_back"
    assert list_result.local_coding_result == [
        {"edit_id": "local_edit_1", "status": "approval_required"}
    ]
