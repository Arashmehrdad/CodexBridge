from __future__ import annotations

from pathlib import Path
from typing import Any

from .config import AppConfig, resolve_repo
from .events import redact_and_truncate
from .run_store import RunStore, validate_run_id
from .supervisor_engine import JobManagerChildBackend, SupervisorEngine
from .supervisor_resume_prompt import supervisor_prompt_path
from .supervisor_store import SupervisorStore, validate_supervisor_id


DELIVERY_STATUSES = {"pending", "delivered", "failed", "partial", "suppressed"}


class SupervisorService:
    def __init__(self, config: AppConfig, config_path: Path | None):
        self.config = config
        self.config_path = config_path
        self.store = SupervisorStore(config.resolve_runs_dir())
        self.run_store = RunStore(config.resolve_runs_dir())

    def child_backend(self) -> JobManagerChildBackend:
        return JobManagerChildBackend(self.config, self.config_path)

    def start_supervised_recovery_task(
        self,
        repo_name: str,
        objective: str,
        task: str,
        constraints: str = "",
        source_run_id: str | None = None,
        autonomy_profile: str = "balanced",
    ) -> dict[str, Any]:
        resolve_repo(self.config, repo_name)
        self._validate_autonomy_profile(autonomy_profile)
        if source_run_id:
            validate_run_id(source_run_id)
            source = self.run_store.get_run(source_run_id)
            if source["repo_name"] != repo_name:
                raise ValueError("source_run_id must belong to repo_name")
        engine = self._engine(autonomy_profile)
        supervisor = engine.create_plan_supervisor(
            repo_name=repo_name, objective=objective, task=task, constraints=constraints
        )
        if source_run_id:
            self.store.add_run_link(
                supervisor["supervisor_id"], source_run_id, "source"
            )
        return self.enrich_supervisor(engine.tick(supervisor["supervisor_id"]))

    def get_status(self, supervisor_id: str) -> dict[str, Any]:
        return self.enrich_supervisor(self._get(supervisor_id))

    def get_events(self, supervisor_id: str, limit: int = 50) -> list[dict[str, Any]]:
        validate_supervisor_id(supervisor_id)
        return redact_and_truncate(
            self.store.get_events(supervisor_id, self._limit(limit))
        )

    def get_result(self, supervisor_id: str) -> dict[str, Any]:
        supervisor = self.enrich_supervisor(self._get(supervisor_id))
        metadata = supervisor.get("metadata") or {}
        return redact_and_truncate(
            {
                "supervisor_id": supervisor["supervisor_id"],
                "repo_name": supervisor["repo_name"],
                "status": supervisor["status"],
                "summary": supervisor["summary"],
                "error": supervisor["error"],
                "plan_result": metadata.get("plan_result"),
                "implementation_result": metadata.get("implementation_result"),
                "run_links": supervisor["run_links"],
                "resume_prompt_path": supervisor["resume_prompt_path"],
                "resume_prompt_exists": supervisor["resume_prompt_exists"],
            }
        )

    def resume(self, supervisor_id: str) -> dict[str, Any]:
        supervisor = self._get(supervisor_id)
        metadata = dict(supervisor.get("metadata") or {})
        status = supervisor["status"]
        if status == "paused":
            previous = metadata.get("paused_from")
            if previous not in {"queued", "needs_input"}:
                raise ValueError(
                    "Paused supervisor is missing a valid paused_from state"
                )
            metadata["paused_from"] = None
            supervisor = self.store.update_supervisor(
                supervisor_id, status=previous, metadata_json=metadata
            )
            status = supervisor["status"]
        if status in {"queued", "planning", "implementing"}:
            return self.enrich_supervisor(
                self._engine_from_supervisor(supervisor).tick(supervisor_id)
            )
        return self.enrich_supervisor(supervisor)

    def pause(self, supervisor_id: str) -> dict[str, Any]:
        supervisor = self._get(supervisor_id)
        if supervisor["status"] not in {"queued", "needs_input"}:
            raise ValueError(
                "pause_supervisor is only supported from queued or needs_input"
            )
        metadata = dict(supervisor.get("metadata") or {})
        metadata["paused_from"] = supervisor["status"]
        paused = self.store.update_supervisor(
            supervisor_id, status="paused", metadata_json=metadata
        )
        self.store.append_event(
            supervisor_id,
            level="info",
            stage="paused",
            message="Supervisor paused",
            data={"from": metadata["paused_from"]},
        )
        return self.enrich_supervisor(paused)

    def cancel(self, supervisor_id: str) -> dict[str, Any]:
        supervisor = self._get(supervisor_id)
        return self.enrich_supervisor(
            self._engine_from_supervisor(supervisor).cancel(supervisor_id)
        )

    def get_notifications(
        self, supervisor_id: str, delivery_status: str | None = None, limit: int = 50
    ) -> list[dict[str, Any]]:
        validate_supervisor_id(supervisor_id)
        if delivery_status and delivery_status not in DELIVERY_STATUSES:
            raise ValueError(f"Invalid delivery_status: {delivery_status}")
        return redact_and_truncate(
            self.store.list_notifications(
                supervisor_id, delivery_status, self._limit(limit)
            )
        )

    def get_resume_prompt(self, supervisor_id: str) -> dict[str, Any]:
        validate_supervisor_id(supervisor_id)
        path = supervisor_prompt_path(self.config.resolve_runs_dir(), supervisor_id)
        if not path.exists():
            return {
                "supervisor_id": supervisor_id,
                "exists": False,
                "path": str(path),
                "content": "",
            }
        return redact_and_truncate(
            {
                "supervisor_id": supervisor_id,
                "exists": True,
                "path": str(path),
                "content": path.read_text(encoding="utf-8"),
            }
        )

    def enrich_supervisor(self, supervisor: dict[str, Any]) -> dict[str, Any]:
        enriched = dict(supervisor)
        run_links = self.store.list_run_links(supervisor["supervisor_id"])
        enriched["run_links"] = run_links
        active_child = (supervisor.get("metadata") or {}).get("active_child") or {}
        run_id = active_child.get("run_id")
        enriched["active_child_status"] = self._active_child_status(run_id)
        path = supervisor_prompt_path(
            self.config.resolve_runs_dir(), supervisor["supervisor_id"]
        )
        enriched["resume_prompt_path"] = str(path)
        enriched["resume_prompt_exists"] = path.exists()
        enriched["pending_notifications"] = len(
            self.store.list_notifications(
                supervisor["supervisor_id"], delivery_status="pending", limit=500
            )
        )
        return redact_and_truncate(enriched)

    def _get(self, supervisor_id: str) -> dict[str, Any]:
        validate_supervisor_id(supervisor_id)
        return self.store.get_supervisor(supervisor_id)

    def _engine(self, autonomy_profile: str) -> SupervisorEngine:
        profile = self.config.supervisors.autonomy_profiles[autonomy_profile]
        return SupervisorEngine(
            self.store,
            self.child_backend(),
            autonomy_profile=profile,
            profile_name=autonomy_profile,
        )

    def _engine_from_supervisor(self, supervisor: dict[str, Any]) -> SupervisorEngine:
        profile_name = (supervisor.get("metadata") or {}).get("policy", {}).get(
            "profile", {}
        ).get("name") or self.config.supervisors.default_autonomy_profile
        self._validate_autonomy_profile(profile_name)
        return self._engine(profile_name)

    def _validate_autonomy_profile(self, autonomy_profile: str) -> None:
        if autonomy_profile not in self.config.supervisors.autonomy_profiles:
            raise ValueError(f"Unknown autonomy_profile: {autonomy_profile}")

    def _limit(self, limit: int) -> int:
        return max(1, min(int(limit), 500))

    def _active_child_status(self, run_id: str | None) -> dict[str, Any] | None:
        if not run_id:
            return None
        try:
            return self.run_store.get_run(run_id)
        except Exception:
            return {"run_id": run_id, "status": "unknown"}
