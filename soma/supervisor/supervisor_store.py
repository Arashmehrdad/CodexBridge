from __future__ import annotations

import json
from pathlib import Path

from soma.return_loop.atomic_writer import atomic_write_json
from soma.run_store import utc_now

from .models import SupervisorEvent, SupervisorRun


class LocalSupervisorStore:
    def __init__(self, supervisors_dir: Path):
        self.supervisors_dir = Path(supervisors_dir).resolve()
        self.supervisors_dir.mkdir(parents=True, exist_ok=True)

    def run_dir(self, supervisor_id: str) -> Path:
        return self.supervisors_dir / supervisor_id

    def create(self, run: SupervisorRun) -> SupervisorRun:
        self.run_dir(run.supervisor_id).mkdir(parents=True, exist_ok=True)
        self.write(run)
        self.append_event(
            run.supervisor_id, stage="created", message="Supervisor created"
        )
        return run

    def write(self, run: SupervisorRun) -> SupervisorRun:
        atomic_write_json(
            self.run_dir(run.supervisor_id) / "result.json", run.to_dict()
        )
        return run

    def get(self, supervisor_id: str) -> SupervisorRun:
        path = self.run_dir(supervisor_id) / "result.json"
        if not path.exists():
            raise KeyError(f"Supervisor not found: {supervisor_id}")
        return SupervisorRun.model_validate_json(path.read_text(encoding="utf-8"))

    def list(self, limit: int = 20) -> list[SupervisorRun]:
        runs = []
        for path in self.supervisors_dir.glob("*/result.json"):
            try:
                runs.append(
                    SupervisorRun.model_validate_json(path.read_text(encoding="utf-8"))
                )
            except Exception:
                continue
        runs.sort(key=lambda item: item.created_at, reverse=True)
        return runs[: max(1, min(limit, 100))]

    def update(self, supervisor_id: str, **fields) -> SupervisorRun:
        run = self.get(supervisor_id)
        for key, value in fields.items():
            setattr(run, key, value)
        self.write(run)
        if "status" in fields:
            self.append_event(
                supervisor_id,
                stage=str(run.status.value),
                message=f"Supervisor status: {run.status.value}",
            )
        return run

    def append_event(
        self,
        supervisor_id: str,
        *,
        stage: str,
        message: str,
        level: str = "info",
        data: dict | None = None,
    ) -> SupervisorEvent:
        event = SupervisorEvent(
            timestamp=utc_now(),
            supervisor_id=supervisor_id,
            level=level,
            stage=stage,
            message=message,
            data=data or {},
        )
        path = self.run_dir(supervisor_id) / "events.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(
                json.dumps(event.model_dump(mode="json"), sort_keys=True) + "\n"
            )
        return event

    def events(self, supervisor_id: str, limit: int = 50) -> list[SupervisorEvent]:
        path = self.run_dir(supervisor_id) / "events.jsonl"
        if not path.exists():
            return []
        lines = path.read_text(encoding="utf-8").splitlines()[-limit:]
        return [
            SupervisorEvent.model_validate_json(line) for line in lines if line.strip()
        ]
