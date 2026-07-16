from __future__ import annotations

import time
from pathlib import Path
from typing import Protocol
from uuid import uuid4

from codexbridge.command_profiles import resolve_command_profile
from codexbridge.config import AppConfig, resolve_repo, resolve_repo_config
from codexbridge.job_manager import JobManager
from codexbridge.run_store import TERMINAL_STATUSES, utc_now

from .command_profiles import get_command_profile
from .models import CommandRunResult, CommandRunStatus, PermissionTier


class ProjectCommandRunner(Protocol):
    def run_project_command(
        self,
        *,
        command_id: str,
        repo_name: str | None = None,
        repo_path: str | Path | None = None,
        args: dict | None = None,
        permission_tier: str | PermissionTier | None = None,
        timeout_seconds: int | None = None,
    ) -> CommandRunResult: ...


_STATUS_MAP = {
    "completed": CommandRunStatus.SUCCESS,
    "failed": CommandRunStatus.FAILED,
    "cancelled": CommandRunStatus.FAILED,
    "timed_out": CommandRunStatus.TIMEOUT,
    "needs_input": CommandRunStatus.BLOCKED,
    "partial": CommandRunStatus.FAILED,
}


class DurableProjectCommandRunner:
    """Run a durable project command while preserving the legacy immediate-result API."""

    def __init__(
        self,
        *,
        config: AppConfig,
        config_path: Path | None = None,
        job_manager: JobManager | None = None,
        poll_interval_seconds: float = 0.05,
        wait_grace_seconds: float = 5.0,
    ) -> None:
        self.config = config
        self.job_manager = job_manager or JobManager(config, config_path)
        self.poll_interval_seconds = poll_interval_seconds
        self.wait_grace_seconds = wait_grace_seconds

    def run_project_command(
        self,
        *,
        command_id: str,
        repo_name: str | None = None,
        repo_path: str | Path | None = None,
        args: dict | None = None,
        permission_tier: str | PermissionTier | None = None,
        timeout_seconds: int | None = None,
    ) -> CommandRunResult:
        created_at = utc_now()
        if args:
            return self._blocked(
                command_id,
                repo_name,
                repo_path,
                created_at,
                "Command profile arguments are not supported yet.",
            )
        if not repo_name:
            return self._blocked(
                command_id,
                repo_name,
                repo_path,
                created_at,
                "Durable project commands require repo_name.",
            )

        canonical_name, repo_config = resolve_repo_config(self.config, repo_name)
        repo_root = resolve_repo(self.config, canonical_name)
        if repo_path and Path(repo_path).resolve() != repo_root:
            return self._blocked(
                command_id,
                canonical_name,
                repo_path,
                created_at,
                "repo_path does not match the configured repository path.",
            )
        local_profile = get_command_profile(command_id)
        if local_profile is None:
            return self._blocked(
                command_id,
                canonical_name,
                repo_root,
                created_at,
                f"Unknown command_id: {command_id}",
            )
        profile = resolve_command_profile(
            command_id, list(repo_config.command_profiles or [])
        )
        requested_tier = (
            PermissionTier(permission_tier)
            if permission_tier is not None
            else local_profile.permission_tier
        )
        expected_tier = local_profile.permission_tier
        if requested_tier != expected_tier:
            return self._blocked(
                command_id,
                canonical_name,
                repo_root,
                created_at,
                f"Permission tier mismatch: requested {requested_tier.value}, profile requires {expected_tier.value}",
                permission_tier=expected_tier,
                timeout_seconds=local_profile.default_timeout_seconds,
                argv=list(profile.argv),
            )

        wait_seconds = timeout_seconds or local_profile.default_timeout_seconds
        if wait_seconds > local_profile.default_timeout_seconds:
            return self._blocked(
                command_id,
                canonical_name,
                repo_root,
                created_at,
                "Requested timeout exceeds command profile maximum.",
                permission_tier=expected_tier,
                timeout_seconds=local_profile.default_timeout_seconds,
                argv=list(profile.argv),
            )

        launch = self.job_manager.start_project_command(canonical_name, command_id)
        run_id = str(launch["run_id"])
        deadline = time.monotonic() + wait_seconds + self.wait_grace_seconds
        while True:
            run = self.job_manager.store.get_run(run_id)
            if str(run["status"]) in TERMINAL_STATUSES:
                return self._from_run(
                    run,
                    command_id=command_id,
                    repo_name=canonical_name,
                    repo_root=repo_root,
                    argv=list(profile.argv),
                    permission_tier=expected_tier,
                    timeout_seconds=wait_seconds,
                    created_at=created_at,
                )
            if time.monotonic() >= deadline:
                self.job_manager.cancel_run(run_id)
                run = self.job_manager.store.get_run(run_id)
                return self._from_run(
                    run,
                    command_id=command_id,
                    repo_name=canonical_name,
                    repo_root=repo_root,
                    argv=list(profile.argv),
                    permission_tier=expected_tier,
                    timeout_seconds=wait_seconds,
                    created_at=created_at,
                    forced_timeout=True,
                )
            time.sleep(self.poll_interval_seconds)

    def _from_run(
        self,
        run: dict,
        *,
        command_id: str,
        repo_name: str,
        repo_root: Path,
        argv: list[str],
        permission_tier: PermissionTier,
        timeout_seconds: int,
        created_at: str,
        forced_timeout: bool = False,
    ) -> CommandRunResult:
        run_dir = Path(run["run_dir"])
        durable_status = str(run["status"])
        status = (
            CommandRunStatus.TIMEOUT
            if forced_timeout
            else _STATUS_MAP.get(durable_status, CommandRunStatus.FAILED)
        )
        return CommandRunResult(
            run_id=str(run["run_id"]),
            command_id=command_id,
            repo_name=repo_name,
            repo_path=repo_root,
            working_directory=repo_root,
            argv=argv,
            permission_tier=permission_tier,
            status=status,
            exit_code=run.get("exit_code"),
            duration_seconds=float(run.get("duration_seconds") or 0.0),
            timeout_seconds=timeout_seconds,
            timed_out=forced_timeout or durable_status == "timed_out",
            stdout_path=run_dir / "stdout.txt",
            stderr_path=run_dir / "stderr.txt",
            result_path=run_dir / "result.json",
            audit_event_id=f"durable_project_command_{uuid4().hex}",
            created_at=created_at,
            error=str(run.get("error") or ""),
        )

    def _blocked(
        self,
        command_id: str,
        repo_name: str | None,
        repo_path: str | Path | None,
        created_at: str,
        error: str,
        *,
        permission_tier: PermissionTier = PermissionTier.HUMAN_ONLY_RISKY_ACTION,
        timeout_seconds: int = 0,
        argv: list[str] | None = None,
    ) -> CommandRunResult:
        return CommandRunResult(
            run_id=f"{created_at.replace('-', '').replace(':', '').split('.')[0]}_durable_adapter_{uuid4().hex[:8]}",
            command_id=command_id,
            repo_name=repo_name,
            repo_path=Path(repo_path).resolve() if repo_path else None,
            argv=argv or [],
            permission_tier=permission_tier,
            status=CommandRunStatus.BLOCKED,
            timeout_seconds=timeout_seconds,
            audit_event_id=f"durable_project_command_{uuid4().hex}",
            created_at=created_at,
            error=error,
        )
