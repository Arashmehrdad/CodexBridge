from __future__ import annotations

import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from .command_profiles import (
    PYTEST_PATH_COMMAND_ID,
    build_pytest_path_profile,
    resolve_command_profile,
)
from .config import AppConfig, resolve_repo
from .events import ArtifactWriter, redact_and_truncate
from .policy import PolicyDecision, decide_implementation_task, decide_plan_task
from .run_store import RunStore, validate_run_id
from .safety import reject_destructive_command, validate_repo_relative_paths
from .ssh_commands import resolve_ssh_command_profile


def make_run_id(tool: str) -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    safe_tool = "".join(char if char.isalnum() else "_" for char in tool.lower())
    return f"{timestamp}_{safe_tool}_{uuid4().hex[:8]}"


class JobManager:
    def __init__(self, config: AppConfig, config_path: Path | None):
        self.config = config
        self.config_path = config_path
        self.store = RunStore(config.resolve_runs_dir())

    def reconcile_startup(self) -> int:
        stale = self.store.mark_stale_running()
        return stale

    def start_plan(self, repo_name: str, task: str, constraints: str = "") -> dict:
        resolve_repo(self.config, repo_name)
        decision = decide_plan_task(task, constraints)
        if not decision.accepted:
            return decision.to_start_response(status="refused")
        input_data = {"repo_name": repo_name, "task": task, "constraints": constraints}
        return self._create_and_launch(
            "codex_plan_task", repo_name, input_data, decision
        )

    def start_implementation(
        self,
        repo_name: str,
        approved_plan: str,
        allowed_files: list[str],
        tests: list[str],
    ) -> dict:
        repo_root = resolve_repo(self.config, repo_name)
        validate_repo_relative_paths(repo_root, allowed_files)
        for test in tests:
            reject_destructive_command(test)
        decision = decide_implementation_task(approved_plan, allowed_files, tests)
        if not decision.accepted:
            return decision.to_start_response(status="refused")
        input_data = {
            "repo_name": repo_name,
            "approved_plan": approved_plan,
            "allowed_files": allowed_files,
            "tests": tests,
        }
        return self._create_and_launch(
            "codex_implement_task", repo_name, input_data, decision
        )

    def start_project_command(self, repo_name: str, command_id: str) -> dict:
        resolve_repo(self.config, repo_name)
        repo_profiles = list(self.config.repos[repo_name].command_profiles or [])
        profile = resolve_command_profile(command_id, repo_profiles)
        estimated_minutes = max(1, (profile.timeout_seconds + 59) // 60)
        decision = PolicyDecision(
            accepted=True,
            tier=1,
            risk_level="low" if not profile.writes_files else "medium",
            requires_human=False,
            reason="Allowlisted project command is approved for durable async execution",
            estimated_duration_minutes=estimated_minutes,
            recommended_check_after_minutes=min(2, estimated_minutes),
        )
        response = self._create_and_launch(
            "project_command",
            repo_name,
            {"repo_name": repo_name, "command_id": command_id},
            decision,
        )
        response["repo_name"] = repo_name
        response["command_id"] = command_id
        return response

    def start_pytest_path(self, repo_name: str, path: str) -> dict:
        repo_root = resolve_repo(self.config, repo_name)
        profile = build_pytest_path_profile(repo_root, path)
        decision = PolicyDecision(
            accepted=True,
            tier=1,
            risk_level="low",
            requires_human=False,
            reason="Allowlisted scoped pytest command is approved for durable async execution",
            estimated_duration_minutes=max(1, (profile.timeout_seconds + 59) // 60),
            recommended_check_after_minutes=min(
                2, max(1, (profile.timeout_seconds + 59) // 60)
            ),
        )
        normalized_target = profile.argv[-1]
        response = self._create_and_launch(
            "project_command",
            repo_name,
            {
                "repo_name": repo_name,
                "command_id": PYTEST_PATH_COMMAND_ID,
                "path": normalized_target,
            },
            decision,
        )
        response["repo_name"] = repo_name
        response["command_id"] = PYTEST_PATH_COMMAND_ID
        response["path"] = normalized_target
        return response

    def start_ssh_command(self, host_id: str, command_id: str) -> dict:
        _, profile = resolve_ssh_command_profile(self.config, host_id, command_id)
        estimated_minutes = max(1, (profile.timeout_seconds + 59) // 60)
        decision = PolicyDecision(
            accepted=True,
            tier=2 if profile.writes_remote else 1,
            risk_level="medium" if profile.writes_remote else "low",
            requires_human=False,
            reason="Allowlisted SSH command is approved for durable async execution",
            estimated_duration_minutes=estimated_minutes,
            recommended_check_after_minutes=min(2, estimated_minutes),
        )
        response = self._create_and_launch(
            "ssh_command",
            f"ssh:{host_id}",
            {"host_id": host_id, "command_id": command_id},
            decision,
        )
        response["host_id"] = host_id
        response["command_id"] = command_id
        response["writes_remote"] = profile.writes_remote
        return response

    def _create_and_launch(
        self, tool: str, repo_name: str, input_data: dict, decision
    ) -> dict:
        if self.config_path is None:
            return {
                "run_id": None,
                "accepted": False,
                "status": "refused",
                "estimated_duration_minutes": 0,
                "recommended_check_after_minutes": 0,
                "risk_level": "high",
                "requires_human": False,
                "reason": "Async jobs require a config file path",
            }

        run_id = make_run_id(tool)
        run_dir = self.config.resolve_runs_dir() / run_id
        run_dir.mkdir(parents=True, exist_ok=False)
        artifacts = ArtifactWriter(run_dir)
        artifacts.write_json("input.json", input_data)
        self.store.create_run(
            run_id=run_id,
            repo_name=repo_name,
            tool=tool,
            run_dir=run_dir,
            input_data=input_data,
            risk_level=decision.risk_level,
            requires_human=decision.requires_human,
        )
        event = self.store.append_event(
            run_id,
            level="info",
            stage="queued",
            message="Run queued",
            data={"tool": tool},
        )
        artifacts.append_event(event)
        command = [
            sys.executable,
            "-m",
            "codexbridge.job_worker",
            "--config",
            str(self.config_path),
            "--run-id",
            run_id,
        ]
        process = subprocess.Popen(
            command,
            cwd=Path.cwd(),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            close_fds=os.name != "nt",
        )
        self.store.update_run(run_id, worker_pid=process.pid)
        event = self.store.append_event(
            run_id,
            level="info",
            stage="worker",
            message="Worker process started",
            data={"worker_pid": process.pid},
        )
        artifacts.append_event(event)
        return decision.to_start_response(run_id=run_id, status="queued")

    def get_status(self, run_id: str) -> dict:
        run = self.store.get_run(run_id)
        return redact_and_truncate(run)

    def get_events(self, run_id: str, limit: int = 50) -> list[dict]:
        return redact_and_truncate(self.store.get_events(run_id, limit))

    def get_result(self, run_id: str) -> dict:
        run = self.store.get_run(run_id)
        result = run.get("result") or {}
        if result:
            return redact_and_truncate(result)
        return redact_and_truncate(
            {
                "run_id": run["run_id"],
                "repo_name": run["repo_name"],
                "tool": run["tool"],
                "status": run["status"],
                "exit_code": run["exit_code"],
                "started_at": run["started_at"],
                "ended_at": run["ended_at"],
                "duration_seconds": run["duration_seconds"],
                "changed_files": [],
                "git_status": "",
                "diff_stat": "",
                "tests_run": [],
                "test_results": "",
                "summary": run["summary"],
                "remaining_risks": [],
                "error": run["error"],
                "safety_failure": run["safety_failure"],
            }
        )

    def list_runs(
        self, repo_name: str | None = None, status: str | None = None, limit: int = 20
    ) -> list[dict]:
        return redact_and_truncate(
            self.store.list_runs(
                repo_name=repo_name or None, status=status or None, limit=limit
            )
        )

    def latest_result(
        self, repo_name: str | None = None, tool: str | None = None
    ) -> dict:
        run = self.store.latest_run(repo_name=repo_name or None, tool=tool or None)
        return self.get_result(run["run_id"])

    def cancel_run(self, run_id: str) -> dict:
        validate_run_id(run_id)
        run = self.store.get_run(run_id)
        if run["status"] in {"completed", "failed", "cancelled", "needs_input"}:
            return {
                "run_id": run_id,
                "status": run["status"],
                "cancelled": False,
                "reason": "Run is already terminal",
            }
        worker_pid = run.get("worker_pid")
        terminated = False
        if worker_pid:
            try:
                if os.name == "nt":
                    subprocess.run(
                        ["taskkill", "/PID", str(worker_pid), "/T", "/F"],
                        text=True,
                        capture_output=True,
                        timeout=10,
                    )
                else:
                    os.kill(int(worker_pid), 15)
                terminated = True
            except Exception:
                terminated = False
        ended_at = datetime.now(timezone.utc).isoformat()
        self.store.update_run(
            run_id,
            status="cancelled",
            ended_at=ended_at,
            error="Run cancelled by request",
        )
        event = self.store.append_event(
            run_id,
            level="warning",
            stage="cancel",
            message="Run cancellation requested",
            data={"terminated": terminated},
        )
        ArtifactWriter(Path(run["run_dir"])).append_event(event)
        return {
            "run_id": run_id,
            "status": "cancelled",
            "cancelled": True,
            "terminated": terminated,
        }
