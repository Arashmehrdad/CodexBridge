from __future__ import annotations

import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from .cloudflare_tools import authorize_cloudflare_profile, build_cloudflare_action
from .command_profiles import (
    BASH_N_PATH_COMMAND_ID,
    GIT_READONLY_COMMAND_ID,
    JSON_VALIDATE_PATH_COMMAND_ID,
    PYTEST_PATH_COMMAND_ID,
    PY_COMPILE_PATH_COMMAND_ID,
    build_bash_n_path_profile,
    build_git_readonly_profile,
    build_json_validate_path_profile,
    build_py_compile_path_profile,
    build_pytest_path_profile,
    resolve_command_profile,
)
from .config import AppConfig, resolve_repo, resolve_repo_config
from .docker_tools import build_docker_action
from .events import ArtifactWriter, redact_and_truncate
from .external_fixtures import validate_fixture_request
from .operation_locks import OperationLockStore
from .policy import PolicyDecision, decide_implementation_task, decide_plan_task
from .process_control import (
    process_group_popen_kwargs,
    process_is_running,
    process_matches_identity,
    terminate_process_tree,
)
from .run_guards import derive_requirement_manifest
from .run_store import TERMINAL_STATUSES, RunStore, validate_run_id
from .safety import (
    reject_destructive_command,
    validate_repo_relative_path,
    validate_repo_relative_paths,
)
from .ssh_commands import resolve_ssh_command_profile, resolve_ssh_host
from .ssh_watchdog import (
    terminate_remote_process_group,
    validate_monitored_command_start,
)
from .ssh_tools import build_ssh_action, validate_remote_path


def make_run_id(tool: str) -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    safe_tool = "".join(char if char.isalnum() else "_" for char in tool.lower())
    return f"{timestamp}_{safe_tool}_{uuid4().hex[:8]}"


def _read_output_tail(path: Path, tail_bytes: int) -> dict:
    if not path.exists():
        return {"text": "", "size_bytes": 0, "truncated": False, "available": False}
    if not path.is_file() or path.is_symlink():
        raise ValueError(f"Run output is not a regular file: {path.name}")
    size = path.stat().st_size
    offset = max(0, size - tail_bytes)
    with path.open("rb") as handle:
        handle.seek(offset)
        data = handle.read(tail_bytes)
    text = data.decode("utf-8", errors="replace")
    return {
        "text": redact_and_truncate(text, tail_bytes),
        "size_bytes": size,
        "truncated": offset > 0,
        "available": True,
    }


class JobManager:
    def __init__(self, config: AppConfig, config_path: Path | None):
        self.config = config
        self.config_path = config_path
        self.store = RunStore(config.resolve_runs_dir())
        self.locks = OperationLockStore(config.resolve_runs_dir())

    def reconcile_startup(self) -> int:
        reconciled = 0
        for run in self.store.list_recoverable_runs():
            try:
                self._reconcile_run(run)
            except Exception as exc:
                reason = f"Startup reconciliation failed: {exc}"
                self.store.mark_recovery_pending(run["run_id"], reason)
                self._append_recovery_event(
                    run,
                    level="error",
                    message=reason,
                    data={"exception_type": type(exc).__name__},
                )
            reconciled += 1
        self.locks.recover_stale()
        return reconciled

    def _worker_command(self, run_id: str, lease_token: str) -> list[str]:
        return [
            sys.executable,
            "-m",
            "codexbridge.job_worker",
            "--config",
            str(self.config_path),
            "--run-id",
            run_id,
            "--lease-token",
            lease_token,
        ]

    def _spawn_worker(self, run_id: str, lease_token: str):
        return subprocess.Popen(
            self._worker_command(run_id, lease_token),
            cwd=Path.cwd(),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            close_fds=os.name != "nt",
            **process_group_popen_kwargs(),
        )

    def _append_recovery_event(
        self,
        run: dict,
        *,
        level: str,
        message: str,
        data: dict | None = None,
    ) -> None:
        event = self.store.append_event(
            run["run_id"],
            level=level,
            stage="reconcile",
            message=message,
            data=data or {},
        )
        ArtifactWriter(Path(run["run_dir"])).append_event(event)

    def _fail_recovery(self, run: dict, reason: str) -> None:
        self.store.fail_infrastructure(run["run_id"], reason)
        self.locks.release(
            run["repo_name"],
            run["run_id"],
            str(run.get("worker_lease_token") or ""),
        )
        self._append_recovery_event(run, level="error", message=reason)

    def _reconcile_run(self, run: dict) -> None:
        run_id = run["run_id"]
        status = str(run.get("status") or "")
        lease_token = str(run.get("worker_lease_token") or "")
        worker_pid = int(run.get("worker_pid") or 0)
        worker_identity = str(run.get("worker_identity") or "")
        launcher_pid = int(run.get("launcher_pid") or 0)
        child_pid = int(run.get("pid") or 0)
        worker_verified = process_matches_identity(worker_pid, worker_identity)
        launcher_running = process_is_running(launcher_pid)
        child_running = process_is_running(child_pid)

        if worker_verified:
            self.locks.claim_owner(
                run["repo_name"],
                run_id,
                owner_pid=worker_pid,
                owner_token=lease_token,
            )
            self._append_recovery_event(
                run,
                level="info",
                message="Active worker identity verified after server restart",
                data={"worker_pid": worker_pid},
            )
            return

        if run["tool"] == "ssh_monitored_command":
            reason = (
                "Server restarted while monitored remote execution may still be active"
            )
            self.store.update_run(
                run_id,
                status="cancellation_pending",
                current_phase="cancellation_pending",
                ended_at=None,
                error=reason,
                recovery_reason=reason,
                safety_failure=True,
            )
            self._append_recovery_event(run, level="warning", message=reason)
            return

        if child_running:
            reason = "Worker ownership is unavailable while a child process remains active"
            self.store.mark_recovery_pending(run_id, reason)
            self._append_recovery_event(
                run,
                level="warning",
                message=reason,
                data={"child_pid": child_pid},
            )
            return

        if status in {"launch_pending", "queued"}:
            if launcher_running:
                self._append_recovery_event(
                    run,
                    level="warning",
                    message="Launcher remains active; awaiting canonical worker claim",
                    data={"launcher_pid": launcher_pid},
                )
                return
            if int(run.get("launch_attempts") or 0) < 2:
                try:
                    process = self._spawn_worker(run_id, lease_token)
                    self.store.record_worker_launch(run_id, process.pid)
                    self.locks.heartbeat(run["repo_name"], run_id, lease_token)
                    self._append_recovery_event(
                        run,
                        level="warning",
                        message="Stranded queued worker relaunched once",
                        data={"launcher_pid": process.pid},
                    )
                except Exception as exc:
                    self._fail_recovery(
                        run, f"Worker relaunch failed during startup recovery: {exc}"
                    )
                return
            self._fail_recovery(
                run, "Queued run exhausted its bounded worker launch attempts"
            )
            return

        if status == "running":
            if worker_pid and worker_identity:
                self._fail_recovery(
                    run, "Verified worker process is no longer active after restart"
                )
                return
            reason = "Running legacy record has no verifiable worker identity"
            self.store.mark_recovery_pending(run_id, reason)
            self._append_recovery_event(run, level="warning", message=reason)
            return

        if status in {"cancellation_pending", "recovery_pending"}:
            self._append_recovery_event(
                run,
                level="warning",
                message="Conservative recovery state retained pending operator action",
            )

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
        requirement_manifest = derive_requirement_manifest(approved_plan)
        input_data = {
            "repo_name": repo_name,
            "approved_plan": approved_plan,
            "allowed_files": allowed_files,
            "tests": tests,
            "requirement_manifest": requirement_manifest,
        }
        return self._create_and_launch(
            "codex_implement_task", repo_name, input_data, decision
        )

    def start_project_command(self, repo_name: str, command_id: str) -> dict:
        resolve_repo(self.config, repo_name)
        _, repo_config = resolve_repo_config(self.config, repo_name)
        repo_profiles = list(repo_config.command_profiles or [])
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
        response.setdefault("repo_name", repo_name)
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
        response.setdefault("repo_name", repo_name)
        response["command_id"] = PYTEST_PATH_COMMAND_ID
        response["path"] = normalized_target
        return response

    def start_py_compile_path(self, repo_name: str, path: str) -> dict:
        repo_root = resolve_repo(self.config, repo_name)
        profile = build_py_compile_path_profile(repo_root, path)
        return self._start_validated_path_command(
            repo_name,
            command_id=PY_COMPILE_PATH_COMMAND_ID,
            normalized_target=profile.argv[-1],
            timeout_seconds=profile.timeout_seconds,
            reason="Allowlisted py_compile path validation is approved for durable async execution",
        )

    def start_bash_n_path(self, repo_name: str, path: str) -> dict:
        repo_root = resolve_repo(self.config, repo_name)
        profile = build_bash_n_path_profile(repo_root, path)
        return self._start_validated_path_command(
            repo_name,
            command_id=BASH_N_PATH_COMMAND_ID,
            normalized_target=profile.argv[-1],
            timeout_seconds=profile.timeout_seconds,
            reason="Allowlisted bash -n path validation is approved for durable async execution",
        )

    def start_json_validation_path(self, repo_name: str, path: str) -> dict:
        repo_root = resolve_repo(self.config, repo_name)
        profile = build_json_validate_path_profile(repo_root, path)
        return self._start_validated_path_command(
            repo_name,
            command_id=JSON_VALIDATE_PATH_COMMAND_ID,
            normalized_target=profile.argv[-1],
            timeout_seconds=profile.timeout_seconds,
            reason="Allowlisted JSON validation path is approved for durable async execution",
        )

    def start_git_readonly(self, repo_name: str, operation: str) -> dict:
        resolve_repo(self.config, repo_name)
        profile = build_git_readonly_profile(operation)
        decision = PolicyDecision(
            accepted=True,
            tier=1,
            risk_level="low",
            requires_human=False,
            reason="Allowlisted read-only git operation is approved for durable async execution",
            estimated_duration_minutes=max(1, (profile.timeout_seconds + 59) // 60),
            recommended_check_after_minutes=1,
        )
        response = self._create_and_launch(
            "project_command",
            repo_name,
            {
                "repo_name": repo_name,
                "command_id": GIT_READONLY_COMMAND_ID,
                "operation": operation,
            },
            decision,
        )
        response.setdefault("repo_name", repo_name)
        response["command_id"] = GIT_READONLY_COMMAND_ID
        response["operation"] = operation
        return response

    def start_docker_action(
        self,
        repo_name: str,
        action: str,
        *,
        target: str = "",
        destination: str = "",
        services: list[str] | None = None,
        command_id: str = "",
        context: str = ".",
        dockerfile: str = "",
        build: bool = False,
        force: bool = False,
        confirmation: str = "",
    ) -> dict:
        repo_root = resolve_repo(self.config, repo_name)
        _, repo_config = resolve_repo_config(self.config, repo_name)
        normalized_services = list(services or [])
        spec = build_docker_action(
            self.config,
            repo_root,
            repo_config,
            action,
            target=target,
            destination=destination,
            services=normalized_services,
            command_id=command_id,
            context=context,
            dockerfile=dockerfile,
            build=build,
            force=force,
            confirmation=confirmation,
        )
        estimated_minutes = max(1, (spec.timeout_seconds + 59) // 60)
        decision = PolicyDecision(
            accepted=True,
            tier=3 if spec.high_risk else 2,
            risk_level="high" if spec.high_risk else "medium",
            requires_human=False,
            reason=(
                "Explicitly confirmed high-risk Docker action is approved"
                if spec.high_risk
                else "Bounded Docker action is approved for durable async execution"
            ),
            estimated_duration_minutes=estimated_minutes,
            recommended_check_after_minutes=min(2, estimated_minutes),
        )
        input_data = {
            "repo_name": repo_name,
            "action": action,
            "target": target,
            "destination": destination,
            "services": normalized_services,
            "command_id": command_id,
            "context": context,
            "dockerfile": dockerfile,
            "build": build,
            "force": force,
            "confirmation": confirmation,
        }
        response = self._create_and_launch(
            "docker_action", repo_name, input_data, decision
        )
        response.setdefault("repo_name", repo_name)
        response["action"] = action
        response["high_risk"] = spec.high_risk
        return response

    def start_external_fixture_validation(
        self,
        repo_name: str,
        url: str,
        expected_sha256: str,
        validation: str = "none",
    ) -> dict:
        resolve_repo(self.config, repo_name)
        validate_fixture_request(
            self.config.external_fixtures,
            url,
            expected_sha256,
            validation,
        )
        estimated_minutes = max(
            1, (self.config.external_fixtures.timeout_seconds + 59) // 60
        )
        decision = PolicyDecision(
            accepted=True,
            tier=2,
            risk_level="medium",
            requires_human=False,
            reason=(
                "Hash-pinned fixture from an allowlisted HTTPS host is approved "
                "for isolated durable validation"
            ),
            estimated_duration_minutes=estimated_minutes,
            recommended_check_after_minutes=min(2, estimated_minutes),
        )
        return self._create_and_launch(
            "external_fixture_validation",
            repo_name,
            {
                "repo_name": repo_name,
                "url": url,
                "expected_sha256": expected_sha256.lower(),
                "validation": validation,
            },
            decision,
        )

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

    def start_ssh_monitored_command(self, host_id: str, command_id: str) -> dict:
        host, profile = validate_monitored_command_start(
            self.config, host_id, command_id
        )
        estimated_minutes = max(1, (profile.timeout_seconds + 59) // 60)
        decision = PolicyDecision(
            accepted=True,
            tier=2 if profile.writes_remote else 1,
            risk_level="medium" if profile.writes_remote else "low",
            requires_human=False,
            reason="Opt-in monitored SSH command is approved for durable async execution",
            estimated_duration_minutes=estimated_minutes,
            recommended_check_after_minutes=min(2, estimated_minutes),
        )
        response = self._create_and_launch(
            "ssh_monitored_command",
            f"ssh:{host_id}",
            {"host_id": host_id, "command_id": command_id},
            decision,
        )
        response["host_id"] = host_id
        response["command_id"] = command_id
        response["writes_remote"] = profile.writes_remote
        response["watchdog_mode"] = host.watchdog.enforcement_mode
        response["automatic_termination_active"] = bool(
            host.watchdog.enabled
            and host.watchdog.enforcement_mode == "terminate"
            and host.watchdog.allow_automatic_termination
            and profile.watchdog_eligible
        )
        return response

    def start_ssh_action(
        self,
        host_id: str,
        action: str,
        *,
        target: str = "",
        source: str = "",
        destination: str = "",
        path: str = "",
        deployment_id: str = "",
        command_id: str = "",
        packages: list[str] | None = None,
        executable: str = "",
        args: list[str] | None = None,
        force: bool = False,
        confirmation: str = "",
    ) -> dict:
        normalized_packages = list(packages or [])
        normalized_args = list(args or [])
        spec = build_ssh_action(
            self.config,
            host_id,
            action,
            target=target,
            source=source,
            destination=destination,
            path=path,
            deployment_id=deployment_id,
            command_id=command_id,
            packages=normalized_packages,
            executable=executable,
            args=normalized_args,
            force=force,
            confirmation=confirmation,
        )
        estimated_minutes = max(1, (spec.timeout_seconds + 59) // 60)
        decision = PolicyDecision(
            accepted=True,
            tier=3 if spec.high_risk else 2,
            risk_level="high" if spec.high_risk else "medium",
            requires_human=False,
            reason=(
                "Explicitly confirmed high-risk SSH action is approved"
                if spec.high_risk
                else "Bounded SSH action is approved for durable execution"
            ),
            estimated_duration_minutes=estimated_minutes,
            recommended_check_after_minutes=min(2, estimated_minutes),
        )
        input_data = {
            "host_id": host_id,
            "action": action,
            "target": target,
            "source": source,
            "destination": destination,
            "path": path,
            "deployment_id": deployment_id,
            "command_id": command_id,
            "packages": normalized_packages,
            "executable": executable,
            "args": normalized_args,
            "force": force,
            "confirmation": confirmation,
        }
        response = self._create_and_launch(
            "ssh_action", f"ssh:{host_id}", input_data, decision
        )
        response["host_id"] = host_id
        response["action"] = action
        response["high_risk"] = spec.high_risk
        return response

    def start_ssh_transfer(
        self,
        host_id: str,
        direction: str,
        *,
        repo_name: str,
        local_path: str,
        remote_path: str,
        recursive: bool = False,
        overwrite: bool = False,
        confirmation: str = "",
    ) -> dict:
        if not self.config.ssh.allow_transfer:
            raise ValueError("SSH transfer capability is disabled by allow_transfer")
        direction = str(direction or "").strip().lower()
        if direction not in {"upload", "download"}:
            raise ValueError("direction must be 'upload' or 'download'")
        if overwrite and confirmation != self.config.ssh.confirmation_token:
            raise ValueError(
                "Overwrite transfer requires the configured SSH confirmation token"
            )
        host = resolve_ssh_host(self.config, host_id)
        validate_remote_path(host, remote_path, sensitive=True)
        repo_root = resolve_repo(self.config, repo_name)
        if direction == "upload":
            local = validate_repo_relative_path(repo_root, local_path)
            if not local.exists():
                raise ValueError(f"Local upload path does not exist: {local_path}")
            if local.is_dir() and not recursive:
                raise ValueError("Directory upload requires recursive=true")
        decision = PolicyDecision(
            accepted=True,
            tier=3 if overwrite else 2,
            risk_level="high" if overwrite else "medium",
            requires_human=False,
            reason="Bounded SCP transfer is approved for durable execution",
            estimated_duration_minutes=max(
                1, (self.config.ssh.transfer_timeout_seconds + 59) // 60
            ),
            recommended_check_after_minutes=2,
        )
        input_data = {
            "host_id": host_id,
            "direction": direction,
            "local_repo_name": repo_name,
            "local_path": local_path,
            "remote_path": remote_path,
            "recursive": recursive,
            "overwrite": overwrite,
            "confirmation": confirmation,
        }
        response = self._create_and_launch(
            "ssh_transfer", f"ssh:{host_id}", input_data, decision
        )
        response["host_id"] = host_id
        response["direction"] = direction
        return response

    def start_ssh_deployment(
        self,
        host_id: str,
        deployment_id: str,
        *,
        confirmation: str,
    ) -> dict:
        if not self.config.ssh.allow_deploy:
            raise ValueError("SSH deployment capability is disabled by allow_deploy")
        if confirmation != self.config.ssh.confirmation_token:
            raise ValueError(
                "SSH deployment requires the configured confirmation token"
            )
        host = resolve_ssh_host(self.config, host_id)
        deployment = host.deployment_profiles.get(deployment_id)
        if deployment is None:
            raise ValueError(
                f"Unknown deployment_id: {deployment_id!r}. "
                f"Allowed: {sorted(host.deployment_profiles)}"
            )
        resolve_repo(self.config, deployment.repo_name)
        validate_remote_path(host, deployment.remote_root, sensitive=True)
        decision = PolicyDecision(
            accepted=True,
            tier=3,
            risk_level="high",
            requires_human=False,
            reason="Confirmed archive-based SSH deployment is approved",
            estimated_duration_minutes=max(
                5, (self.config.ssh.transfer_timeout_seconds + 59) // 60
            ),
            recommended_check_after_minutes=2,
        )
        input_data = {
            "host_id": host_id,
            "deployment_id": deployment_id,
            "confirmation": confirmation,
        }
        response = self._create_and_launch(
            "ssh_deployment", f"ssh:{host_id}", input_data, decision
        )
        response["host_id"] = host_id
        response["deployment_id"] = deployment_id
        return response

    def start_cloudflare_action(
        self,
        repo_name: str,
        profile_id: str,
        action: str,
        *,
        resource_id: str = "",
        payload: dict | None = None,
        confirmation: str = "",
    ) -> dict:
        canonical_repo_name, _ = authorize_cloudflare_profile(
            self.config, repo_name, profile_id
        )
        normalized_payload = dict(payload or {})
        spec = build_cloudflare_action(
            self.config,
            profile_id,
            action,
            resource_id=resource_id,
            payload=normalized_payload,
            confirmation=confirmation,
        )
        estimated_minutes = max(1, (spec.timeout_seconds + 59) // 60)
        decision = PolicyDecision(
            accepted=True,
            tier=3 if spec.high_risk else 2,
            risk_level="high" if spec.high_risk else "medium",
            requires_human=False,
            reason=(
                "Explicitly confirmed high-risk Cloudflare action is approved"
                if spec.high_risk
                else "Bounded Cloudflare action is approved for durable execution"
            ),
            estimated_duration_minutes=estimated_minutes,
            recommended_check_after_minutes=min(2, estimated_minutes),
        )
        input_data = {
            "repo_name": canonical_repo_name,
            "profile_id": profile_id,
            "action": action,
            "resource_id": resource_id,
            "payload": normalized_payload,
            "confirmation": confirmation,
        }
        response = self._create_and_launch(
            "cloudflare_action",
            f"cloudflare:{canonical_repo_name}:{profile_id}",
            input_data,
            decision,
        )
        response["repo_name"] = canonical_repo_name
        response["profile_id"] = profile_id
        response["action"] = action
        response["high_risk"] = spec.high_risk
        return response

    def _create_and_launch(
        self, tool: str, repo_name: str, input_data: dict, decision
    ) -> dict:
        requested_repo_name = repo_name
        input_data = dict(input_data)
        if not repo_name.startswith(("ssh:", "cloudflare:")):
            resolve_repo(self.config, repo_name)
            canonical_repo_name, _ = resolve_repo_config(self.config, repo_name)
            repo_name = canonical_repo_name
            if "repo_name" in input_data:
                input_data["repo_name"] = canonical_repo_name
            input_data["requested_repo_name"] = requested_repo_name

        if self.config_path is None:
            return {
                "run_id": "",
                "accepted": False,
                "status": "refused",
                "estimated_duration_minutes": 0,
                "recommended_check_after_minutes": 0,
                "risk_level": "high",
                "requires_human": False,
                "reason": "Async jobs require a config file path",
            }

        run_id = make_run_id(tool)
        lease_token = uuid4().hex
        acquisition = self.locks.acquire(
            repo_name=repo_name,
            tool=tool,
            normalized_input=input_data,
            run_id=run_id,
            owner_pid=os.getpid(),
            owner_token=lease_token,
        )
        if not acquisition.acquired:
            return {
                "run_id": "",
                "accepted": False,
                "status": "refused",
                "estimated_duration_minutes": 0,
                "recommended_check_after_minutes": 0,
                "risk_level": decision.risk_level,
                "requires_human": False,
                "reason": acquisition.reason,
                "duplicate": acquisition.duplicate,
            }
        run_dir = self.config.resolve_runs_dir() / run_id
        run_created = False
        try:
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
                status="launch_pending",
                worker_lease_token=lease_token,
            )
            run_created = True
            event = self.store.append_event(
                run_id,
                level="info",
                stage="launch_pending",
                message="Durable worker launch intent recorded",
                data={"tool": tool},
            )
            artifacts.append_event(event)
            process = self._spawn_worker(run_id, lease_token)
            self.store.record_worker_launch(run_id, process.pid)
            self.locks.heartbeat(repo_name, run_id, lease_token)
            event = self.store.append_event(
                run_id,
                level="info",
                stage="worker",
                message="Worker launcher process started",
                data={"launcher_pid": process.pid},
            )
            artifacts.append_event(event)
        except Exception as exc:
            reason = f"Worker launch failed after durable acceptance: {exc}"
            if run_created:
                self.store.fail_infrastructure(run_id, reason)
                event = self.store.append_event(
                    run_id,
                    level="error",
                    stage="launch_failed",
                    message=reason,
                    data={},
                )
                ArtifactWriter(run_dir).append_event(event)
            self.locks.release(repo_name, run_id, lease_token)
            return {
                "run_id": run_id if run_created else "",
                "accepted": False,
                "status": "failed",
                "estimated_duration_minutes": 0,
                "recommended_check_after_minutes": 0,
                "risk_level": decision.risk_level,
                "requires_human": False,
                "reason": reason,
            }
        response = decision.to_start_response(run_id=run_id, status="queued")
        response["repo_name"] = repo_name
        if requested_repo_name != repo_name:
            response["requested_repo_name"] = requested_repo_name
        return response

    def _start_validated_path_command(
        self,
        repo_name: str,
        *,
        command_id: str,
        normalized_target: str,
        timeout_seconds: int,
        reason: str,
    ) -> dict:
        decision = PolicyDecision(
            accepted=True,
            tier=1,
            risk_level="low",
            requires_human=False,
            reason=reason,
            estimated_duration_minutes=max(1, (timeout_seconds + 59) // 60),
            recommended_check_after_minutes=min(
                2, max(1, (timeout_seconds + 59) // 60)
            ),
        )
        response = self._create_and_launch(
            "project_command",
            repo_name,
            {
                "repo_name": repo_name,
                "command_id": command_id,
                "path": normalized_target,
            },
            decision,
        )
        response.setdefault("repo_name", repo_name)
        response["command_id"] = command_id
        response["path"] = normalized_target
        return response

    @staticmethod
    def _public_run(run: dict) -> dict:
        public = dict(run)
        public.pop("worker_lease_token", None)
        return public

    def get_status(self, run_id: str) -> dict:
        try:
            run = self.store.get_run(run_id)
        except (ValueError, KeyError) as exc:
            return self._run_lookup_error(run_id, exc)
        return redact_and_truncate(self._public_run(run))

    def get_events(
        self, run_id: str, limit: int = 50, after_id: int | None = None
    ) -> list[dict]:
        return redact_and_truncate(self.store.get_events(run_id, limit, after_id))

    def get_control_status(self, run_id: str) -> dict:
        run = self.store.get_run(run_id)
        launcher_pid = int(run.get("launcher_pid") or 0)
        worker_pid = int(run.get("worker_pid") or 0)
        worker_identity = str(run.get("worker_identity") or "")
        child_pid = int(run.get("pid") or 0)
        progress = dict(run.get("progress") or {})
        return redact_and_truncate(
            {
                "ok": True,
                "run_id": run_id,
                "repo_name": run["repo_name"],
                "tool": run["tool"],
                "status": run["status"],
                "current_phase": run.get("current_phase") or "",
                "elapsed_seconds": run.get("elapsed_seconds") or 0.0,
                "heartbeat_at": run.get("heartbeat_at"),
                "heartbeat_age_seconds": run.get("heartbeat_age_seconds"),
                "worker_stale": bool(run.get("worker_stale")),
                "launcher_pid": launcher_pid,
                "launcher_running": process_is_running(launcher_pid),
                "worker_pid": worker_pid,
                "worker_identity_present": bool(worker_identity),
                "worker_running": process_matches_identity(
                    worker_pid, worker_identity
                ),
                "child_pid": child_pid,
                "child_running": process_is_running(child_pid),
                "last_output_at": progress.get("last_output_at", ""),
                "cancellation_requested_at": progress.get(
                    "cancellation_requested_at", ""
                ),
                "lock": self.locks.find_lock(run["repo_name"], run_id) or {},
                "error": run.get("error") or "",
            }
        )

    def get_output(
        self, run_id: str, stream: str = "combined", tail_bytes: int = 20000
    ) -> dict:
        validate_run_id(run_id)
        normalized_stream = str(stream or "combined").strip().lower()
        if normalized_stream not in {"stdout", "stderr", "combined"}:
            raise ValueError("stream must be stdout, stderr, or combined")
        bounded_tail = max(1, min(int(tail_bytes), 200000))
        run = self.store.get_run(run_id)
        raw_run_dir = Path(run["run_dir"])
        if raw_run_dir.is_symlink():
            raise ValueError("Run directory must not be a symlink")
        run_dir = raw_run_dir.resolve()
        run_dir.relative_to(self.config.resolve_runs_dir())
        selected = (
            [normalized_stream]
            if normalized_stream in {"stdout", "stderr"}
            else ["stdout", "stderr"]
        )
        streams = {
            name: _read_output_tail(run_dir / f"{name}.txt", bounded_tail)
            for name in selected
        }
        return {
            "ok": True,
            "run_id": run_id,
            "status": run["status"],
            "stream": normalized_stream,
            "tail_bytes": bounded_tail,
            "streams": streams,
            "error": "",
        }

    def list_operation_locks(
        self, repo_name: str | None = None, *, include_stale: bool = True
    ) -> list[dict]:
        normalized_name = repo_name or None
        if normalized_name and not normalized_name.startswith(
            ("ssh:", "cloudflare:", "__")
        ):
            normalized_name, _ = resolve_repo_config(self.config, normalized_name)
        return redact_and_truncate(
            self.locks.list_locks(normalized_name, include_stale=include_stale)
        )

    def get_result(self, run_id: str) -> dict:
        try:
            run = self.store.get_run(run_id)
        except (ValueError, KeyError) as exc:
            return self._run_lookup_error(run_id, exc)
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
                "stdout": "",
                "stderr": "",
                "process_success": None,
                "classification": "pending",
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
                "cancelled": False,
                "timed_out": False,
            }
        )

    @staticmethod
    def _run_lookup_error(run_id: str, exc: Exception) -> dict:
        malformed = isinstance(exc, ValueError)
        return {
            "ok": False,
            "run_id": run_id,
            "status": "invalid" if malformed else "not_found",
            "classification": "lookup_error",
            "error_code": "invalid_run_id" if malformed else "run_not_found",
            "error": str(exc),
            "result_available": False,
            "exit_code": None,
            "stdout": "",
            "stderr": "",
        }

    @staticmethod
    def _cancellation_result(
        run: dict, ended_at: str, error: str, progress: dict
    ) -> dict:
        return {
            "run_id": run["run_id"],
            "repo_name": run["repo_name"],
            "tool": run["tool"],
            "status": "cancelled",
            "classification": "cancelled",
            "process_success": None,
            "exit_code": run.get("exit_code"),
            "stdout": "",
            "stderr": "",
            "started_at": run.get("started_at"),
            "ended_at": ended_at,
            "duration_seconds": run.get("duration_seconds"),
            "summary": error,
            "error": error,
            "cancelled": True,
            "cancellation": progress,
            "timed_out": False,
            "safety_failure": False,
            "changed_files": [],
            "tests_run": [],
            "remaining_risks": [],
        }

    def list_runs(
        self, repo_name: str | None = None, status: str | None = None, limit: int = 20
    ) -> list[dict]:
        canonical_repo_name = None
        if repo_name:
            canonical_repo_name, _ = resolve_repo_config(self.config, repo_name)
        runs = self.store.list_runs(
            repo_name=canonical_repo_name or repo_name or None,
            status=status or None,
            limit=limit,
        )
        return redact_and_truncate([self._public_run(run) for run in runs])

    def latest_result(
        self, repo_name: str | None = None, tool: str | None = None
    ) -> dict:
        canonical_repo_name = None
        if repo_name:
            canonical_repo_name, _ = resolve_repo_config(self.config, repo_name)
        run = self.store.latest_run(
            repo_name=canonical_repo_name or repo_name or None,
            tool=tool or None,
        )
        return self.get_result(run["run_id"])

    def cancel_run(self, run_id: str) -> dict:
        try:
            validate_run_id(run_id)
            run = self.store.get_run(run_id)
        except (ValueError, KeyError) as exc:
            return self._run_lookup_error(run_id, exc)
        if run["status"] in TERMINAL_STATUSES:
            return {
                "ok": True,
                "run_id": run_id,
                "status": run["status"],
                "cancelled": False,
                "termination_confirmed": True,
                "reason": "Run is already terminal",
            }

        requested_at = datetime.now(timezone.utc).isoformat()
        progress = dict(run.get("progress") or {})
        progress["cancellation_requested_at"] = requested_at
        child_pid = int(run.get("pid") or 0)
        worker_pid = int(run.get("worker_pid") or 0)
        launcher_pid = int(run.get("launcher_pid") or 0)

        if run["tool"] == "ssh_monitored_command":
            if (
                run["status"] == "queued"
                and not launcher_pid
                and not worker_pid
                and not child_pid
            ):
                ended_at = datetime.now(timezone.utc).isoformat()
                error = "Run cancelled before monitored SSH launch"
                result = self._cancellation_result(run, ended_at, error, progress)
                self.store.update_run(
                    run_id,
                    status="cancelled",
                    ended_at=ended_at,
                    error=error,
                    progress_json=progress,
                    result_json=result,
                )
                self.locks.release(run["repo_name"], run_id)
                return {
                    "ok": True,
                    "run_id": run_id,
                    "status": "cancelled",
                    "cancelled": True,
                    "terminated": False,
                    "termination_confirmed": True,
                    "termination_reports": [],
                }

            self.store.update_run(
                run_id,
                status="cancellation_pending",
                current_phase="cancellation_pending",
                progress_json=progress,
            )
            if worker_pid > 0 and process_is_running(worker_pid):
                return {
                    "ok": False,
                    "run_id": run_id,
                    "status": "cancellation_pending",
                    "cancelled": False,
                    "terminated": False,
                    "termination_confirmed": False,
                    "reason": "Cancellation recorded; attached worker owns remote termination",
                }

            remote_process = dict(progress.get("remote_process") or {})
            if not remote_process:
                return {
                    "ok": False,
                    "run_id": run_id,
                    "status": "cancellation_pending",
                    "cancelled": False,
                    "terminated": False,
                    "termination_confirmed": False,
                    "reason": "Worker is unavailable and remote process identity is unknown; lock retained",
                }
            termination = terminate_remote_process_group(
                self.config,
                str(run["input"]["host_id"]),
                {
                    **remote_process,
                    "command_id": str(run["input"]["command_id"]),
                },
                grace_seconds=int(progress.get("termination_grace_seconds") or 5),
            )
            progress["remote_termination"] = termination
            if not termination.get("terminated"):
                self.store.set_progress(
                    run_id,
                    phase="cancellation_pending",
                    progress=progress,
                    elapsed_seconds=float(run.get("elapsed_seconds") or 0.0),
                )
                return {
                    "ok": False,
                    "run_id": run_id,
                    "status": "cancellation_pending",
                    "cancelled": False,
                    "terminated": False,
                    "termination_confirmed": False,
                    "termination_reports": [termination],
                    "reason": "Remote termination could not be confirmed; lock retained",
                }

            reports = []
            if child_pid > 0 and process_is_running(child_pid):
                report = terminate_process_tree(child_pid)
                report["role"] = "child"
                reports.append(report)
            local_confirmed = all(bool(report.get("terminated")) for report in reports)
            progress["termination_reports"] = reports
            if not local_confirmed:
                self.store.set_progress(
                    run_id,
                    phase="cancellation_pending",
                    progress=progress,
                    elapsed_seconds=float(run.get("elapsed_seconds") or 0.0),
                )
                return {
                    "ok": False,
                    "run_id": run_id,
                    "status": "cancellation_pending",
                    "cancelled": False,
                    "terminated": True,
                    "termination_confirmed": False,
                    "termination_reports": [termination, *reports],
                    "reason": "Remote exit confirmed but local SSH termination is unconfirmed; lock retained",
                }

            ended_at = datetime.now(timezone.utc).isoformat()
            error = "Run cancelled after verified remote termination"
            result = self._cancellation_result(run, ended_at, error, progress)
            self.store.update_run(
                run_id,
                status="cancelled",
                ended_at=ended_at,
                error=error,
                progress_json=progress,
                result_json=result,
            )
            self.locks.release(run["repo_name"], run_id)
            event = self.store.append_event(
                run_id,
                level="warning",
                stage="cancel",
                message="Monitored SSH run cancelled after verified remote termination",
                data={"termination_reports": [termination, *reports]},
            )
            ArtifactWriter(Path(run["run_dir"])).append_event(event)
            return {
                "ok": True,
                "run_id": run_id,
                "status": "cancelled",
                "cancelled": True,
                "terminated": True,
                "termination_confirmed": True,
                "termination_reports": [termination, *reports],
            }

        self.store.set_progress(
            run_id,
            phase=run.get("current_phase") or "cancellation_pending",
            progress=progress,
            elapsed_seconds=float(run.get("elapsed_seconds") or 0.0),
        )
        pids: list[tuple[str, int]] = []
        if child_pid > 0:
            pids.append(("child", child_pid))
        if worker_pid > 0 and worker_pid != child_pid:
            pids.append(("worker", worker_pid))
        if (
            launcher_pid > 0
            and launcher_pid != child_pid
            and launcher_pid != worker_pid
        ):
            pids.append(("launcher", launcher_pid))
        reports = []
        for role, pid in pids:
            report = terminate_process_tree(pid)
            report["role"] = role
            reports.append(report)
        if run["status"] == "queued" and not pids:
            termination_confirmed = True
        else:
            termination_confirmed = bool(reports) and all(
                bool(report.get("terminated")) for report in reports
            )
        progress["termination_reports"] = reports

        if not termination_confirmed:
            self.store.set_progress(
                run_id,
                phase="cancellation_pending",
                progress=progress,
                elapsed_seconds=float(run.get("elapsed_seconds") or 0.0),
            )
            event = self.store.append_event(
                run_id,
                level="error",
                stage="cancellation_pending",
                message="Cancellation requested but process termination is unconfirmed",
                data={"termination_reports": reports},
            )
            ArtifactWriter(Path(run["run_dir"])).append_event(event)
            return {
                "ok": False,
                "run_id": run_id,
                "status": run["status"],
                "cancelled": False,
                "terminated": False,
                "termination_confirmed": False,
                "termination_reports": reports,
                "reason": "Process termination could not be confirmed; lock retained",
            }

        ended_at = datetime.now(timezone.utc).isoformat()
        error = "Run cancelled by request"
        result = self._cancellation_result(run, ended_at, error, progress)
        self.store.update_run(
            run_id,
            status="cancelled",
            ended_at=ended_at,
            error=error,
            progress_json=progress,
            result_json=result,
        )
        self.locks.release(run["repo_name"], run_id)
        event = self.store.append_event(
            run_id,
            level="warning",
            stage="cancel",
            message="Run cancelled after process-tree termination was confirmed",
            data={"termination_reports": reports},
        )
        ArtifactWriter(Path(run["run_dir"])).append_event(event)
        return {
            "ok": True,
            "run_id": run_id,
            "status": "cancelled",
            "cancelled": True,
            "terminated": bool(reports),
            "termination_confirmed": True,
            "termination_reports": reports,
        }
