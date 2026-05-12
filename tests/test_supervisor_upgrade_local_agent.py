from __future__ import annotations

from codexbridge.local_agent import LocalAgentOrchestrator, LocalAgentTaskType
from codexbridge.supervisor import SupervisorStatus, SupervisorTaskRequest


class FakeSupervisorManager:
    def __init__(self):
        self.started = []

    def start_supervised_task(self, request: SupervisorTaskRequest):
        self.started.append(request)
        return _Dumpable({"run": {"supervisor_id": request.supervisor_id, "status": SupervisorStatus.COMPLETED.value}})

    def get_status(self, supervisor_id: str):
        return _Dumpable({"run": {"supervisor_id": supervisor_id, "status": SupervisorStatus.COMPLETED.value}, "events": []})

    def list_runs(self):
        return [_Dumpable({"supervisor_id": "supervisor_1", "status": SupervisorStatus.COMPLETED.value})]

    def cancel(self, supervisor_id: str):
        return _Dumpable({"run": {"supervisor_id": supervisor_id, "status": SupervisorStatus.CANCELLED.value}})

    def resume(self, supervisor_id: str):
        return self.get_status(supervisor_id)

    def generate_report(self, supervisor_id: str):
        return _Dumpable({"run": {"supervisor_id": supervisor_id, "status": SupervisorStatus.REPORTED.value}})


class _Dumpable:
    def __init__(self, data):
        self.data = data

    def model_dump(self, *args, **kwargs):
        return self.data


def test_local_agent_routes_explicit_supervisor_task() -> None:
    manager = FakeSupervisorManager()
    orchestrator = LocalAgentOrchestrator(supervisor_manager=manager)

    result = orchestrator.handle_task("start supervised task: inspect repo")

    assert result.task_type == LocalAgentTaskType.SUPERVISOR
    assert result.supervisor_result["run"]["status"] == "completed"
    assert manager.started[0].objective == "inspect repo"


def test_local_agent_does_not_route_ordinary_edit_to_supervisor() -> None:
    manager = FakeSupervisorManager()
    orchestrator = LocalAgentOrchestrator(supervisor_manager=manager)

    result = orchestrator.handle_task("fix this bug")

    assert result.task_type == LocalAgentTaskType.SOURCE_EDIT
    assert result.supervisor_result is None
    assert manager.started == []


def test_local_agent_lists_supervisors_read_only() -> None:
    orchestrator = LocalAgentOrchestrator(supervisor_manager=FakeSupervisorManager())

    result = orchestrator.handle_task("list supervisors")

    assert result.task_type == LocalAgentTaskType.SUPERVISOR
    assert result.supervisor_result == [{"supervisor_id": "supervisor_1", "status": "completed"}]
