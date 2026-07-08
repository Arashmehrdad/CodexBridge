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
from .run_guards import derive_requirement_manifest
from .run_store import RunStore, validate_run_id
from .safety import (
    reject_destructive_command,
    validate_repo_relative_path,
    validate_repo_relative_paths,
)
from .ssh_commands import resolve_ssh_command_profile, resolve_ssh_host
from .ssh_tools import build_ssh_action, validate_remote_path


def make_run_id(tool: str) -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    safe_tool = "".join(char if char.isalnum() else "_" for char in tool.lower())
    return f"{timestamp}_{safe_tool}_{uuid4().hex[:8]}"


class JobManager:
    def __init__(self, config: AppConfig, config_path: Path | None):
        self.config = config
        self.config_path = config_path
        self.store = RunStore(config.resolve_runs_dir())
        self.locks = OperationLockStore(config.resolve_runs_dir())

    def reconcile_startup(self) -> int:
        stale = self.store.mark_stale_running()
        self.locks.recover_stale()
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
        acquisition = self.locks.acquire(
            repo_name=repo_name,
            tool=tool,
            normalized_input=input_data,
            run_id=run_id,
            owner_pid=os.getpid(),
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
        self.locks.heartbeat(repo_name, run_id)
        event = self.store.append_event(
            run_id,
            level="info",
            stage="worker",
            message="Worker process started",
            data={"worker_pid": process.pid},
        )
        artifacts.append_event(event)
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
        canonical_repo_name = None
        if repo_name:
            canonical_repo_name, _ = resolve_repo_config(self.config, repo_name)
        return redact_and_truncate(
            self.store.list_runs(
                repo_name=canonical_repo_name or repo_name or None,
                status=status or None,
                limit=limit,
            )
        )

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
        self.locks.release(run["repo_name"], run_id)
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
