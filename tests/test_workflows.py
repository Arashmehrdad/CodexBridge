from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

import pytest

from codexbridge.config import AppConfig, RepoConfig
from codexbridge.return_loop.pulse_contract import discover_ready_reports
from codexbridge.workflows.manager import WorkflowManager
from codexbridge.workflows.worker import WorkflowWorker
from codexbridge.workflows.models import WorkflowEvent, WorkflowRecord, WorkflowStatus


class FakeWorkflowStore:
    state: dict[str, dict] = {}

    def __init__(self, runs_dir: Path):
        self.runs_dir = str(Path(runs_dir))
        bucket = self.state.setdefault(
            self.runs_dir, {"workflows": {}, "events": {}}
        )
        self.workflows = bucket["workflows"]
        self.events = bucket["events"]

    @classmethod
    def reset(cls) -> None:
        cls.state = {}

    def create_workflow(self, *, workflow_id, repo_name, objective, steps, status):
        self.workflows[workflow_id] = {
            "workflow_id": workflow_id,
            "repo_name": repo_name,
            "objective": objective,
            "status": status.value if hasattr(status, "value") else str(status),
            "terminal_status": None,
            "created_at": "2026-07-11T20:00:00+00:00",
            "updated_at": "2026-07-11T20:00:00+00:00",
            "started_at": None,
            "ended_at": None,
            "worker_pid": None,
            "heartbeat_at": None,
            "active_child_run_id": None,
            "failure_summary": "",
            "recommended_next_action": "",
            "artifact_paths": [],
            "result": {},
            "steps": [
                {
                    "id": step["id"],
                    "type": step["type"],
                    "order_index": step["order_index"],
                    "parameters": step["parameters"],
                    "depends_on": step["depends_on"],
                    "on_failure": step["on_failure"],
                    "status": "pending",
                    "child_run_id": None,
                    "started_at": None,
                    "ended_at": None,
                    "summary": "",
                    "error": "",
                    "artifact_paths": [],
                    "result": {},
                }
                for step in steps
            ],
        }
        self.events[workflow_id] = []
        return self.get_workflow(workflow_id)

    def get_workflow(self, workflow_id: str) -> WorkflowRecord:
        data = self.workflows[workflow_id]
        return WorkflowRecord.model_validate(data)

    def update_workflow(self, workflow_id: str, **fields):
        workflow = self.workflows[workflow_id]
        workflow["updated_at"] = "2026-07-11T20:00:01+00:00"
        for key, value in fields.items():
            if key == "artifact_paths_json":
                workflow["artifact_paths"] = list(value)
            elif key == "result_json":
                workflow["result"] = value
            elif key in {"status", "terminal_status"} and hasattr(value, "value"):
                workflow[key] = value.value
            else:
                workflow[key] = value
        return self.get_workflow(workflow_id)

    def update_step(self, workflow_id: str, step_id: str, **fields):
        step = next(
            item for item in self.workflows[workflow_id]["steps"] if item["id"] == step_id
        )
        for key, value in fields.items():
            if key == "artifact_paths_json":
                step["artifact_paths"] = list(value)
            elif key == "result_json":
                step["result"] = value
            elif key == "status" and hasattr(value, "value"):
                step["status"] = value.value
            else:
                step[key] = value
        self.workflows[workflow_id]["updated_at"] = "2026-07-11T20:00:01+00:00"
        return self.get_workflow(workflow_id)

    def append_event(self, workflow_id: str, *, level, stage, message, data=None, timestamp=None):
        event = WorkflowEvent(
            timestamp=timestamp or "2026-07-11T20:00:01+00:00",
            workflow_id=workflow_id,
            level=level,
            stage=stage,
            message=message,
            data=data or {},
        )
        self.events.setdefault(workflow_id, []).append(event)
        workflow = self.workflows[workflow_id]
        workflow["heartbeat_at"] = event.timestamp
        workflow["updated_at"] = event.timestamp
        return event

    def get_events(self, workflow_id: str, limit: int = 100):
        return self.events.get(workflow_id, [])[-limit:]

    def iter_recoverable_workflows(self):
        return [
            self.get_workflow(workflow_id)
            for workflow_id, workflow in self.workflows.items()
            if workflow["status"] in {"queued", "running"}
        ]


@pytest.fixture
def tmp_path() -> Path:
    path = (Path("runs") / "pytest_tmp" / uuid4().hex).resolve()
    path.mkdir(parents=True, exist_ok=False)
    return path


@pytest.fixture(autouse=True)
def patch_atomic_writes(monkeypatch):
    FakeWorkflowStore.reset()

    def write_text(path: Path, text: str):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return {"path": str(path)}

    def write_json(path: Path, data: dict):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        return {"path": str(path)}

    monkeypatch.setattr(
        "codexbridge.workflows.reporter.atomic_write_text", write_text
    )
    monkeypatch.setattr(
        "codexbridge.workflows.reporter.atomic_write_json", write_json
    )
    monkeypatch.setattr(
        "codexbridge.return_loop.pulse_contract.atomic_write_json", write_json
    )
    monkeypatch.setattr(
        "codexbridge.return_loop.atomic_writer.atomic_write_text", write_text
    )
    monkeypatch.setattr(
        "codexbridge.return_loop.atomic_writer.atomic_write_json", write_json
    )


class FakeJobManager:
    counter = 0
    launches: list[dict] = []
    statuses: dict[str, str] = {}
    results: dict[str, dict] = {}
    cancelled: list[str] = []

    def __init__(self, *_args, **_kwargs):
        pass

    @classmethod
    def reset(cls) -> None:
        cls.counter = 0
        cls.launches = []
        cls.statuses = {}
        cls.results = {}
        cls.cancelled = []

    @classmethod
    def _start(cls, kind: str, payload: dict) -> dict:
        cls.counter += 1
        run_id = f"20260711T2033{cls.counter:02d}Z_{kind}_{cls.counter:08x}"
        cls.launches.append({"kind": kind, "payload": payload, "run_id": run_id})
        status = "completed"
        summary = f"{kind} completed"
        error = ""
        if payload.get("command_id") == "fail_stop":
            status = "failed"
            summary = "step failed hard"
            error = "step failed hard"
        elif payload.get("command_id") == "fail_continue":
            status = "failed"
            summary = "step failed but continue"
            error = "API key=super-secret"
        elif payload.get("command_id") == "needs_input":
            status = "needs_input"
            summary = "waiting for input"
            error = "approval token required"
        elif payload.get("command_id") == "hang":
            status = "running"
            summary = "still running"
        cls.statuses[run_id] = status
        cls.results[run_id] = {
            "run_id": run_id,
            "status": status,
            "summary": summary,
            "error": error,
            "artifacts": [],
        }
        return {
            "ok": True,
            "accepted": True,
            "run_id": run_id,
            "status": "queued",
            "requires_human": False,
        }

    def start_implementation(
        self, repo_name: str, approved_plan: str, allowed_files: list[str], tests: list[str]
    ) -> dict:
        return self._start(
            "codex_implement",
            {
                "repo_name": repo_name,
                "approved_plan": approved_plan,
                "allowed_files": allowed_files,
                "tests": tests,
            },
        )

    def start_project_command(self, repo_name: str, command_id: str) -> dict:
        return self._start(
            "project_command", {"repo_name": repo_name, "command_id": command_id}
        )

    def start_pytest_path(self, repo_name: str, path: str) -> dict:
        return self._start("pytest_path", {"repo_name": repo_name, "path": path})

    def start_git_readonly(self, repo_name: str, operation: str) -> dict:
        return self._start(
            "git_readonly", {"repo_name": repo_name, "operation": operation}
        )

    def get_status(self, run_id: str) -> dict:
        return {
            "run_id": run_id,
            "status": self.statuses[run_id],
            "summary": self.results[run_id]["summary"],
            "error": self.results[run_id]["error"],
        }

    def get_result(self, run_id: str) -> dict:
        return dict(self.results[run_id])

    def cancel_run(self, run_id: str) -> dict:
        self.statuses[run_id] = "cancelled"
        self.results[run_id]["status"] = "cancelled"
        self.results[run_id]["summary"] = "cancelled"
        self.cancelled.append(run_id)
        return {"ok": True, "run_id": run_id, "status": "cancelled"}


def make_config(tmp_path: Path) -> tuple[AppConfig, Path]:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    (repo_root / ".git").mkdir()
    config_path = tmp_path / "config.yaml"
    config_path.write_text("repos: {}\n", encoding="utf-8")
    config = AppConfig(
        repos={"repo": RepoConfig(path=str(repo_root))},
        runs_dir=str(tmp_path / "runs"),
        config_dir=tmp_path,
    )
    return config, config_path


def test_workflow_validation_rejects_duplicate_unknown_dependency_cycle_and_unsafe_fields(
    tmp_path: Path,
) -> None:
    config, config_path = make_config(tmp_path)
    manager = WorkflowManager(config, config_path, worker_launcher=lambda *_args: 1)

    with pytest.raises(ValueError, match="Duplicate workflow step ID"):
        manager.start_workflow(
            "repo",
            "duplicate ids",
            [
                {"id": "a", "type": "project_command", "parameters": {"command_id": "x"}},
                {"id": "a", "type": "project_command", "parameters": {"command_id": "y"}},
            ],
        )
    with pytest.raises(ValueError, match="missing step"):
        manager.start_workflow(
            "repo",
            "missing dep",
            [
                {
                    "id": "a",
                    "type": "project_command",
                    "parameters": {"command_id": "x"},
                    "depends_on": ["missing"],
                }
            ],
        )
    with pytest.raises(ValueError, match="earlier steps"):
        manager.start_workflow(
            "repo",
            "future dep",
            [
                {
                    "id": "a",
                    "type": "project_command",
                    "parameters": {"command_id": "x"},
                    "depends_on": ["b"],
                },
                {"id": "b", "type": "project_command", "parameters": {"command_id": "y"}},
            ],
        )
    with pytest.raises(Exception):
        manager.start_workflow(
            "repo",
            "unsafe",
            [
                {
                    "id": "a",
                    "type": "project_command",
                    "parameters": {"command_id": "x", "command": "rm -rf ."},
                }
            ],
        )


def test_workflow_worker_advances_ordered_steps_dependencies_continue_and_local_summary(
    tmp_path: Path, monkeypatch
) -> None:
    FakeJobManager.reset()
    config, config_path = make_config(tmp_path)
    manager = WorkflowManager(config, config_path, worker_launcher=lambda *_args: 1234)
    started = manager.start_workflow(
        "repo",
        "execute durable workflow",
        [
            {"id": "one", "type": "project_command", "parameters": {"command_id": "ok"}},
            {
                "id": "two",
                "type": "project_command",
                "parameters": {"command_id": "fail_continue"},
                "on_failure": "continue",
            },
            {
                "id": "three",
                "type": "pytest_path",
                "parameters": {"path": "tests/test_sample.py"},
                "depends_on": ["one"],
            },
            {
                "id": "summary",
                "type": "local_summary",
                "parameters": {},
                "depends_on": ["one", "three"],
            },
        ],
    )
    monkeypatch.setattr("codexbridge.workflows.worker.JobManager", FakeJobManager)
    worker = WorkflowWorker(config_path, started["workflow_id"], sleep_fn=lambda *_args: None)
    assert worker.execute() == 0

    workflow = manager.get_result(started["workflow_id"])
    assert workflow["status"] == "reported"
    assert workflow["terminal_status"] == "completed"
    step_states = {step["id"]: step["status"] for step in workflow["steps"]}
    assert step_states == {
        "one": "passed",
        "two": "failed",
        "three": "passed",
        "summary": "passed",
    }
    summary_step = next(step for step in workflow["steps"] if step["id"] == "summary")
    summary_path = Path(summary_step["artifact_paths"][0])
    assert summary_path.exists()
    manifest_path = Path(config.runs_dir) / "workflows" / started["workflow_id"] / "pulse_manifest.json"
    assert manifest_path.exists()
    resume_prompt = (
        Path(config.runs_dir)
        / "workflows"
        / started["workflow_id"]
        / "resume_prompt.txt"
    ).read_text(encoding="utf-8")
    assert "super-secret" not in resume_prompt
    assert "[REDACTED]" in resume_prompt
    ready = discover_ready_reports(Path(config.runs_dir))
    assert [item.artifact_id for item in ready] == [started["workflow_id"]]


def test_workflow_worker_stops_on_failure_and_skips_remaining_steps(
    tmp_path: Path, monkeypatch
) -> None:
    FakeJobManager.reset()
    config, config_path = make_config(tmp_path)
    manager = WorkflowManager(config, config_path, worker_launcher=lambda *_args: 10)
    started = manager.start_workflow(
        "repo",
        "stop on failure",
        [
            {"id": "one", "type": "project_command", "parameters": {"command_id": "fail_stop"}},
            {"id": "two", "type": "project_command", "parameters": {"command_id": "ok"}},
        ],
    )
    monkeypatch.setattr("codexbridge.workflows.worker.JobManager", FakeJobManager)
    worker = WorkflowWorker(config_path, started["workflow_id"], sleep_fn=lambda *_args: None)
    assert worker.execute() == 0

    workflow = manager.get_result(started["workflow_id"])
    assert workflow["terminal_status"] == "failed"
    assert [step["status"] for step in workflow["steps"]] == ["failed", "pending"]


def test_workflow_cancel_requests_active_child_cancellation(tmp_path: Path) -> None:
    FakeJobManager.reset()
    config, config_path = make_config(tmp_path)
    manager = WorkflowManager(config, config_path, worker_launcher=lambda *_args: 11)
    started = manager.start_workflow(
        "repo",
        "cancel workflow",
        [{"id": "one", "type": "project_command", "parameters": {"command_id": "hang"}}],
    )
    store = FakeWorkflowStore(Path(config.runs_dir))
    store.update_step(
        started["workflow_id"],
        "one",
        status="running",
        child_run_id="20260711T203301Z_hang_00000001",
    )
    store.update_workflow(
        started["workflow_id"],
        status="running",
        active_child_run_id="20260711T203301Z_hang_00000001",
    )
    FakeJobManager.statuses["20260711T203301Z_hang_00000001"] = "running"
    FakeJobManager.results["20260711T203301Z_hang_00000001"] = {
        "run_id": "20260711T203301Z_hang_00000001",
        "status": "running",
        "summary": "still running",
        "error": "",
    }
    import codexbridge.job_manager as job_manager_module

    job_manager_module.JobManager = FakeJobManager  # type: ignore[assignment]
    cancelled = manager.cancel_workflow(started["workflow_id"])
    assert cancelled["cancelled"] is True
    assert FakeJobManager.cancelled == ["20260711T203301Z_hang_00000001"]
    workflow = manager.get_result(started["workflow_id"])
    assert workflow["terminal_status"] == "cancelled"


def test_workflow_reconcile_startup_relaunches_stale_worker_once(tmp_path: Path) -> None:
    config, config_path = make_config(tmp_path)
    launches: list[str] = []
    manager = WorkflowManager(
        config,
        config_path,
        worker_launcher=lambda _config_path, workflow_id: launches.append(workflow_id) or 55,
        process_checker=lambda pid: pid == 999,
    )
    started = manager.start_workflow(
        "repo",
        "reconcile",
        [{"id": "one", "type": "project_command", "parameters": {"command_id": "ok"}}],
    )
    store = FakeWorkflowStore(Path(config.runs_dir))
    store.update_workflow(
        started["workflow_id"],
        status="running",
        worker_pid=44,
        heartbeat_at="2026-01-01T00:00:00+00:00",
    )
    relaunched = manager.reconcile_startup()
    assert relaunched == 1
    assert launches.count(started["workflow_id"]) == 2


def test_workflow_result_and_events_snapshots_are_written(tmp_path: Path, monkeypatch) -> None:
    FakeJobManager.reset()
    config, config_path = make_config(tmp_path)
    manager = WorkflowManager(config, config_path, worker_launcher=lambda *_args: 42)
    started = manager.start_workflow(
        "repo",
        "write snapshots",
        [
            {"id": "one", "type": "git_readonly", "parameters": {"operation": "status"}},
            {"id": "two", "type": "local_summary", "parameters": {}, "depends_on": ["one"]},
        ],
    )
    monkeypatch.setattr("codexbridge.workflows.worker.JobManager", FakeJobManager)
    worker = WorkflowWorker(config_path, started["workflow_id"], sleep_fn=lambda *_args: None)
    worker.execute()

    root = Path(config.runs_dir) / "workflows" / started["workflow_id"]
    result_payload = json.loads((root / "result.json").read_text(encoding="utf-8"))
    events_lines = (root / "events.jsonl").read_text(encoding="utf-8").splitlines()
    assert result_payload["workflow_id"] == started["workflow_id"]
    assert any("Workflow report artifacts written" in line for line in events_lines)
