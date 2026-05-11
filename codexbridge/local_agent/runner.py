from __future__ import annotations

import subprocess
import time
from pathlib import Path
from uuid import uuid4

from codexbridge.config import AppConfig, resolve_repo
from codexbridge.events import append_jsonl
from codexbridge.run_store import utc_now

from .audit import create_audit_event
from .command_profiles import get_command_profile
from .models import CommandRunResult, CommandRunStatus, PermissionTier


class LocalAgentCommandRunner:
    def __init__(self, config: AppConfig | None = None, runs_dir: Path | None = None):
        self.config = config
        self.runs_dir = (runs_dir or (config.resolve_runs_dir() if config else Path.cwd() / "runs")).resolve()

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
        run_id = f"{created_at.replace('-', '').replace(':', '').split('.')[0]}_local_agent_command_{uuid4().hex[:8]}"
        run_dir = self.runs_dir / "local_agent" / "commands" / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        audit_requested = create_audit_event(
            task_id=run_id,
            action="command_requested",
            message=f"Command requested: {command_id}",
            metadata={"command_id": command_id, "repo_name": repo_name, "repo_path": str(repo_path) if repo_path else None},
        )
        self._append_audit(run_dir, audit_requested.model_dump(mode="json"))

        profile = get_command_profile(command_id)
        if profile is None:
            return self._blocked_result(
                run_dir=run_dir,
                run_id=run_id,
                command_id=command_id,
                repo_name=repo_name,
                repo_path=repo_path,
                status=CommandRunStatus.PROFILE_MISSING,
                permission_tier=PermissionTier.HUMAN_ONLY_RISKY_ACTION,
                timeout_seconds=timeout_seconds or 0,
                created_at=created_at,
                error=f"Unknown command_id: {command_id}",
            )

        if args:
            return self._blocked_result(
                run_dir=run_dir,
                run_id=run_id,
                command_id=command_id,
                repo_name=repo_name,
                repo_path=repo_path,
                status=CommandRunStatus.BLOCKED,
                permission_tier=profile.permission_tier,
                timeout_seconds=profile.default_timeout_seconds,
                created_at=created_at,
                argv=profile.argv,
                error="Command profile arguments are not supported yet.",
            )

        requested_tier = PermissionTier(permission_tier) if permission_tier is not None else profile.permission_tier
        if requested_tier != profile.permission_tier:
            return self._blocked_result(
                run_dir=run_dir,
                run_id=run_id,
                command_id=command_id,
                repo_name=repo_name,
                repo_path=repo_path,
                status=CommandRunStatus.PERMISSION_DENIED,
                permission_tier=profile.permission_tier,
                timeout_seconds=profile.default_timeout_seconds,
                created_at=created_at,
                argv=profile.argv,
                error=f"Permission tier mismatch: requested {requested_tier.value}, profile requires {profile.permission_tier.value}",
            )

        effective_timeout = timeout_seconds if timeout_seconds is not None else profile.default_timeout_seconds
        if effective_timeout > profile.default_timeout_seconds:
            return self._blocked_result(
                run_dir=run_dir,
                run_id=run_id,
                command_id=command_id,
                repo_name=repo_name,
                repo_path=repo_path,
                status=CommandRunStatus.PERMISSION_DENIED,
                permission_tier=profile.permission_tier,
                timeout_seconds=profile.default_timeout_seconds,
                created_at=created_at,
                argv=profile.argv,
                error="Requested timeout exceeds command profile maximum.",
            )

        working_directory, repo_error = self._resolve_working_directory(repo_name, repo_path)
        if repo_error:
            return self._blocked_result(
                run_dir=run_dir,
                run_id=run_id,
                command_id=command_id,
                repo_name=repo_name,
                repo_path=repo_path,
                status=CommandRunStatus.REPO_MISSING,
                permission_tier=profile.permission_tier,
                timeout_seconds=effective_timeout,
                created_at=created_at,
                argv=profile.argv,
                error=repo_error,
            )

        self._append_audit(
            run_dir,
            create_audit_event(
                task_id=run_id,
                action="command_allowed",
                message=f"Command allowed: {command_id}",
                metadata={"command_id": command_id, "permission_tier": profile.permission_tier.value},
            ).model_dump(mode="json"),
        )
        started = time.monotonic()
        stdout = ""
        stderr = ""
        exit_code: int | None = None
        timed_out = False
        status = CommandRunStatus.SUCCESS
        try:
            completed = subprocess.run(
                profile.argv,
                cwd=working_directory,
                shell=False,
                capture_output=True,
                text=True,
                timeout=effective_timeout,
                check=False,
            )
            stdout = completed.stdout or ""
            stderr = completed.stderr or ""
            exit_code = completed.returncode
            if completed.returncode != 0:
                status = CommandRunStatus.FAILED
        except subprocess.TimeoutExpired as exc:
            stdout = _coerce_output(exc.stdout)
            stderr = _coerce_output(exc.stderr)
            status = CommandRunStatus.TIMEOUT
            timed_out = True
        duration = time.monotonic() - started

        result = CommandRunResult(
            run_id=run_id,
            command_id=command_id,
            repo_name=repo_name,
            repo_path=Path(repo_path).resolve() if repo_path else None,
            working_directory=working_directory,
            argv=list(profile.argv),
            permission_tier=profile.permission_tier,
            status=status,
            exit_code=exit_code,
            duration_seconds=duration,
            timeout_seconds=effective_timeout,
            timed_out=timed_out,
            stdout_path=run_dir / "stdout.txt",
            stderr_path=run_dir / "stderr.txt",
            result_path=run_dir / "result.json",
            audit_event_id=f"local_agent_{uuid4().hex}",
            created_at=created_at,
        )
        self._write_artifacts(result, stdout, stderr)
        self._append_audit(
            run_dir,
            create_audit_event(
                task_id=run_id,
                action="command_completed",
                message=f"Command completed with status: {status.value}",
                metadata={"command_id": command_id, "status": status.value, "exit_code": exit_code, "timed_out": timed_out},
            ).model_dump(mode="json"),
        )
        return result

    def _resolve_working_directory(self, repo_name: str | None, repo_path: str | Path | None) -> tuple[Path | None, str]:
        if repo_name:
            if self.config is None:
                return None, "repo_name requires an AppConfig for resolution."
            try:
                return resolve_repo(self.config, repo_name), ""
            except Exception as exc:
                return None, str(exc)
        if repo_path:
            path = Path(repo_path).resolve()
            if not path.exists() or not path.is_dir():
                return None, f"Repo path does not exist or is not a directory: {path}"
            return path, ""
        return Path.cwd().resolve(), ""

    def _blocked_result(
        self,
        *,
        run_dir: Path,
        run_id: str,
        command_id: str,
        repo_name: str | None,
        repo_path: str | Path | None,
        status: CommandRunStatus,
        permission_tier: PermissionTier,
        timeout_seconds: int,
        created_at: str,
        error: str,
        argv: list[str] | None = None,
    ) -> CommandRunResult:
        result = CommandRunResult(
            run_id=run_id,
            command_id=command_id,
            repo_name=repo_name,
            repo_path=Path(repo_path).resolve() if repo_path else None,
            working_directory=None,
            argv=argv or [],
            permission_tier=permission_tier,
            status=status,
            exit_code=None,
            duration_seconds=0.0,
            timeout_seconds=timeout_seconds,
            timed_out=False,
            stdout_path=run_dir / "stdout.txt",
            stderr_path=run_dir / "stderr.txt",
            result_path=run_dir / "result.json",
            audit_event_id=f"local_agent_{uuid4().hex}",
            created_at=created_at,
            error=error,
        )
        self._write_artifacts(result, "", error)
        self._append_audit(
            run_dir,
            create_audit_event(
                task_id=run_id,
                action="command_blocked",
                message=error,
                metadata={"command_id": command_id, "status": status.value},
            ).model_dump(mode="json"),
        )
        return result

    def _write_artifacts(self, result: CommandRunResult, stdout: str, stderr: str) -> None:
        assert result.stdout_path is not None
        assert result.stderr_path is not None
        assert result.result_path is not None
        result.stdout_path.write_text(stdout, encoding="utf-8")
        result.stderr_path.write_text(stderr, encoding="utf-8")
        result.result_path.write_text(result.model_dump_json(indent=2), encoding="utf-8")

    def _append_audit(self, run_dir: Path, event: dict) -> None:
        append_jsonl(run_dir / "events.jsonl", event)


def run_project_command(
    *,
    command_id: str,
    repo_name: str | None = None,
    repo_path: str | Path | None = None,
    args: dict | None = None,
    permission_tier: str | PermissionTier | None = None,
    timeout_seconds: int | None = None,
    config: AppConfig | None = None,
    runs_dir: Path | None = None,
) -> CommandRunResult:
    return LocalAgentCommandRunner(config=config, runs_dir=runs_dir).run_project_command(
        command_id=command_id,
        repo_name=repo_name,
        repo_path=repo_path,
        args=args,
        permission_tier=permission_tier,
        timeout_seconds=timeout_seconds,
    )


def _coerce_output(value: str | bytes | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value
