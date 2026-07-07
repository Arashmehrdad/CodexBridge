from __future__ import annotations

import argparse
import os
import subprocess
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Sequence

from . import git_tools
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
    run_command_profile,
)
from .config import load_config, resolve_repo, resolve_repo_config
from .events import ArtifactWriter, redact_and_truncate
from .external_fixtures import fetch_validate_and_discard
from .managed_artifacts import (
    cleanup_new_managed_artifacts,
    snapshot_managed_artifacts,
)
from .operation_locks import OperationLockStore
from .policy import decide_implementation_task, decide_plan_task
from .prompts import build_implementation_prompt, build_plan_prompt
from .run_store import RunStore
from .run_guards import (
    allowed_write_directories,
    assess_implementation_output,
    assess_plan_output,
    changed_workspace_paths,
    classify_git_attribution,
    out_of_scope_workspace_changes,
    snapshot_workspace,
)
from .runner import CodexRunner, _safe_command_args
from .safety import reject_destructive_command, validate_repo_relative_paths
from .ssh_commands import run_ssh_command


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _duration(started_at: str, ended_at: str) -> float:
    started = datetime.fromisoformat(started_at)
    ended = datetime.fromisoformat(ended_at)
    return round((ended - started).total_seconds(), 3)


def _stream_pipe(
    pipe,
    output_path: Path,
    sink: list[str],
    limit: int = 40000,
    on_output: Callable[[], None] | None = None,
) -> None:
    with output_path.open("a", encoding="utf-8", errors="replace") as handle:
        for line in iter(pipe.readline, ""):
            handle.write(line)
            handle.flush()
            if sum(len(item) for item in sink) < limit:
                sink.append(line)
            if on_output is not None:
                on_output()
    pipe.close()


class JobWorker:
    def __init__(self, config_path: Path, run_id: str):
        self.config_path = config_path
        self.config = load_config(config_path)
        self.store = RunStore(self.config.resolve_runs_dir())
        self.locks = OperationLockStore(self.config.resolve_runs_dir())
        self.run = self.store.get_run(run_id)
        self.run_id = run_id
        self.artifacts = ArtifactWriter(Path(self.run["run_dir"]))
        self._started_monotonic = 0.0
        self._heartbeat_stop = threading.Event()
        self._heartbeat_thread: threading.Thread | None = None
        self._last_output_heartbeat = 0.0

    def event(
        self, level: str, stage: str, message: str, data: dict | None = None
    ) -> None:
        self.store.set_progress(
            self.run_id,
            phase=stage,
            progress=data or {},
            elapsed_seconds=self._elapsed_seconds(),
        )
        self.locks.heartbeat(self.run["repo_name"], self.run_id)
        event = self.store.append_event(
            self.run_id,
            level=level,
            stage=stage,
            message=message,
            data=redact_and_truncate(data or {}),
        )
        self.artifacts.append_event(event)

    def _elapsed_seconds(self) -> float:
        if not self._started_monotonic:
            return 0.0
        return round(max(0.0, time.monotonic() - self._started_monotonic), 3)

    def _heartbeat_loop(self) -> None:
        while not self._heartbeat_stop.wait(5.0):
            try:
                self.store.heartbeat(
                    self.run_id,
                    elapsed_seconds=self._elapsed_seconds(),
                    progress_updates={"worker_pid": os.getpid()},
                )
                self.locks.heartbeat(self.run["repo_name"], self.run_id)
            except Exception:
                continue

    def _note_output(self) -> None:
        now = time.monotonic()
        if now - self._last_output_heartbeat < 1.0:
            return
        self._last_output_heartbeat = now
        self.store.heartbeat(
            self.run_id,
            elapsed_seconds=self._elapsed_seconds(),
            progress_updates={"last_output_at": _utc_now()},
        )

    def execute(self) -> int:
        started_at = _utc_now()
        self._started_monotonic = time.monotonic()
        self.store.update_run(self.run_id, status="running", started_at=started_at)
        self.event("info", "worker", "Worker started")
        self._heartbeat_thread = threading.Thread(
            target=self._heartbeat_loop,
            name=f"codexbridge-heartbeat-{self.run_id}",
            daemon=True,
        )
        self._heartbeat_thread.start()
        try:
            result = self._execute_inner(started_at)
            status = str(
                result.get("status")
                or (
                    "failed"
                    if result.get("safety_failure")
                    or result.get("blocked")
                    or result.get("exit_code", 1) != 0
                    else "completed"
                )
            )
            ended_at = result["ended_at"]
            self.artifacts.write_json("result.json", result)
            current = self.store.get_run(self.run_id)
            if current["status"] == "cancelled":
                self.event(
                    "warning",
                    "cancel",
                    "Worker finished after cancellation; preserving cancelled status",
                )
                return int(result.get("exit_code") or 0)
            self.store.update_run(
                self.run_id,
                status=status,
                ended_at=ended_at,
                duration_seconds=result["duration_seconds"],
                exit_code=result.get("exit_code"),
                summary=result.get("summary", ""),
                error=result.get("error", ""),
                safety_failure=result.get("safety_failure", False),
                result_json=result,
            )
            level = (
                "info"
                if status == "completed"
                else "warning"
                if status == "partial"
                else "error"
            )
            self.event(
                level,
                "result",
                f"Run {status}",
                {"exit_code": result.get("exit_code")},
            )
            worker_exit_code = int(result.get("exit_code") or 0)
            return (
                1 if status == "failed" and worker_exit_code == 0 else worker_exit_code
            )
        except Exception as exc:
            ended_at = _utc_now()
            result = self._error_result(started_at, ended_at, exc)
            self.artifacts.write_json("result.json", result)
            self.store.update_run(
                self.run_id,
                status="failed",
                ended_at=ended_at,
                duration_seconds=result["duration_seconds"],
                exit_code=1,
                summary=result["summary"],
                error=result["error"],
                safety_failure=True,
                result_json=result,
            )
            self.event("error", "result", "Run failed", {"error": str(exc)})
            return 1
        finally:
            self._heartbeat_stop.set()
            if self._heartbeat_thread is not None:
                self._heartbeat_thread.join(timeout=2)
            self.locks.release(self.run["repo_name"], self.run_id)

    def _execute_inner(self, started_at: str) -> dict:
        input_data = self.run["input"]
        tool = self.run["tool"]

        if tool == "ssh_command":
            return self._execute_ssh_command(started_at, input_data)

        repo_name = input_data["repo_name"]
        repo_root = resolve_repo(self.config, repo_name)

        if tool == "project_command":
            return self._execute_project_command(
                started_at, repo_name, repo_root, input_data
            )
        if tool == "external_fixture_validation":
            return self._execute_external_fixture_validation(
                started_at, repo_name, input_data
            )

        if tool == "codex_plan_task":
            decision = decide_plan_task(
                input_data["task"], input_data.get("constraints")
            )
            if not decision.accepted:
                raise ValueError(decision.reason)
            prompt = build_plan_prompt(
                repo_name, input_data["task"], input_data.get("constraints", "")
            )
            sandbox = "read-only"
            tests: list[str] = []
            allowed_files: list[str] = []
        elif tool == "codex_implement_task":
            allowed_files = list(input_data.get("allowed_files") or [])
            tests = list(input_data.get("tests") or [])
            validate_repo_relative_paths(repo_root, allowed_files)
            for test in tests:
                reject_destructive_command(test)
            decision = decide_implementation_task(
                input_data["approved_plan"], allowed_files, tests
            )
            if not decision.accepted:
                raise ValueError(decision.reason)
            prompt = build_implementation_prompt(
                repo_name, input_data["approved_plan"], allowed_files, tests
            )
            sandbox = "workspace-write"
        else:
            raise ValueError(f"Unsupported async tool: {tool}")

        writable_dirs = (
            allowed_write_directories(repo_root, allowed_files)
            if tool == "codex_implement_task"
            else []
        )
        run_dir = Path(self.run["run_dir"])
        ignored_run_roots = [self.config.resolve_runs_dir()]
        managed_artifacts_before = snapshot_managed_artifacts(repo_root)
        workspace_before = snapshot_workspace(repo_root, ignored_run_roots)
        dirty_before = git_tools.changed_files(repo_root)
        git_before = git_tools.git_status(repo_root)
        self.artifacts.write_text("git_before.txt", git_before)
        self.artifacts.write_text("prompt.txt", prompt)
        self.event("info", "codex", "Starting Codex process", {"sandbox": sandbox})

        runner = CodexRunner(self.config)
        executable = runner._resolve_codex_executable()
        help_text = runner._codex_exec_help(executable)
        args = runner._codex_exec_args(
            executable, sandbox, help_text, prompt, writable_dirs=writable_dirs
        )
        temp_root = run_dir / "tmp"
        temp_root.mkdir(parents=True, exist_ok=True)
        process_env = os.environ.copy()
        process_env.update(
            {"TMP": str(temp_root), "TEMP": str(temp_root), "TMPDIR": str(temp_root)}
        )
        process = subprocess.Popen(
            args,
            cwd=repo_root,
            env=process_env,
            text=True,
            encoding="utf-8",
            errors="replace",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        self.store.update_run(self.run_id, pid=process.pid)
        self.event(
            "info",
            "codex",
            "Codex process spawned",
            {"pid": process.pid, "command": _safe_command_args(args)},
        )

        stdout_parts: list[str] = []
        stderr_parts: list[str] = []
        stdout_thread = threading.Thread(
            target=_stream_pipe,
            args=(
                process.stdout,
                run_dir / "stdout.txt",
                stdout_parts,
                40000,
                self._note_output,
            ),
        )
        stderr_thread = threading.Thread(
            target=_stream_pipe,
            args=(
                process.stderr,
                run_dir / "stderr.txt",
                stderr_parts,
                40000,
                self._note_output,
            ),
        )
        stdout_thread.start()
        stderr_thread.start()
        try:
            exit_code = process.wait(timeout=self.config.codex.default_timeout_seconds)
        except subprocess.TimeoutExpired:
            process.kill()
            exit_code = 124
            self.event(
                "error",
                "codex",
                "Codex process timed out and was killed",
                {"pid": process.pid},
            )
        stdout_thread.join(timeout=5)
        stderr_thread.join(timeout=5)

        stdout = "".join(stdout_parts)
        stderr = "".join(stderr_parts)
        summary = (stdout or "").strip() or (stderr or "").strip()
        outcome = (
            assess_implementation_output(summary)
            if tool == "codex_implement_task"
            else assess_plan_output(summary)
        )
        managed_artifacts_cleaned = cleanup_new_managed_artifacts(
            repo_root, managed_artifacts_before
        )
        workspace_after = snapshot_workspace(repo_root, ignored_run_roots)
        workspace_changes = changed_workspace_paths(workspace_before, workspace_after)
        workspace_violations = (
            out_of_scope_workspace_changes(
                workspace_before, workspace_after, allowed_files
            )
            if tool == "codex_implement_task"
            else []
        )
        git_after = git_tools.git_status(repo_root)
        diff_stat = git_tools.diff_stat(repo_root)
        changed_after = git_tools.changed_files(repo_root)
        introduced_changes, preserved_preexisting_changes = classify_git_attribution(
            changed_after, workspace_before, workspace_after, dirty_before
        )
        self.artifacts.write_text("git_after.txt", git_after)
        self.artifacts.write_text("diff_stat.txt", diff_stat)

        risks: list[str] = []
        safety_failure = False
        if tool == "codex_plan_task":
            risks.extend(outcome.blockers)
            if git_before != git_after:
                safety_failure = True
                risks.append("Plan mode changed git status")
        if tool == "codex_implement_task":
            assert outcome is not None
            risks.extend(outcome.blockers)
            violations = sorted(
                {path for path in introduced_changes if path not in set(allowed_files)}
                | set(workspace_violations)
            )
            if violations:
                safety_failure = True
                risks.append(f"Changed files outside allowed_files: {violations}")
        if exit_code != 0:
            risks.append("Codex exited nonzero")
        combined_output = f"{stdout}\n{stderr}"
        if "windows sandbox: spawn setup refresh" in combined_output:
            risks.append("Codex shell spawn failed during Windows sandbox setup")

        blocked = bool(outcome and outcome.blocked)
        blockers = outcome.blockers if outcome else []
        plan_conformance = outcome.plan_conformance if outcome else None
        completed_requirements = outcome.completed_requirements if outcome else []
        skipped_requirements = outcome.skipped_requirements if outcome else []
        validation_status = outcome.validation_status if outcome else None
        validation_confirmed = not tests or validation_status in {
            "passed",
            "not_required",
        }
        implementation_complete = bool(
            tool != "codex_implement_task"
            or (
                plan_conformance is True
                and not skipped_requirements
                and validation_confirmed
            )
        )
        if exit_code == 124:
            terminal_status = "timed_out"
        elif safety_failure or blocked or exit_code != 0:
            terminal_status = "failed"
        elif not implementation_complete:
            terminal_status = "partial"
        else:
            terminal_status = "completed"

        ended_at = _utc_now()
        return {
            "run_id": self.run_id,
            "repo_name": repo_name,
            "tool": tool,
            "status": terminal_status,
            "exit_code": exit_code,
            "started_at": started_at,
            "ended_at": ended_at,
            "duration_seconds": _duration(started_at, ended_at),
            "changed_files": introduced_changes,
            "introduced_changes": introduced_changes,
            "preserved_preexisting_changes": preserved_preexisting_changes,
            "workspace_changes": workspace_changes,
            "out_of_scope_workspace_changes": workspace_violations,
            "writable_directories": [str(path) for path in writable_dirs],
            "git_status": git_after,
            "diff_stat": diff_stat,
            "tests_run": tests,
            "test_results": "",
            "summary": summary,
            "remaining_risks": risks,
            "blocked": blocked,
            "blockers": blockers,
            "plan_conformance": plan_conformance,
            "requested_files": allowed_files,
            "completed_requirements": completed_requirements,
            "skipped_requirements": skipped_requirements,
            "validation_status": validation_status,
            "managed_artifacts_cleaned": managed_artifacts_cleaned,
            "temporary_directory": str(temp_root),
            "error": "; ".join(blockers)
            or (
                "Approved plan was only partially verified"
                if terminal_status == "partial"
                else ""
            ),
            "safety_failure": safety_failure,
            "codex_exit_code": exit_code,
            "codex_command_args": _safe_command_args(args),
        }

    def _execute_ssh_command(self, started_at: str, input_data: dict) -> dict:
        host_id = str(input_data["host_id"])
        command_id = str(input_data["command_id"])
        self.event(
            "info",
            "ssh",
            "Starting allowlisted SSH command",
            {"host_id": host_id, "command_id": command_id},
        )
        command_result = run_ssh_command(self.config, host_id, command_id)
        safe_command_result = dict(redact_and_truncate(command_result))
        command_result = safe_command_result
        stdout = str(safe_command_result.get("stdout", ""))
        stderr = str(safe_command_result.get("stderr", ""))
        self.artifacts.write_text("stdout.txt", stdout)
        self.artifacts.write_text("stderr.txt", stderr)

        risks: list[str] = []
        if command_result.get("timed_out"):
            risks.append("SSH command timed out; inspect saved output before retrying")
        if command_result.get("writes_remote"):
            risks.append(
                "CodexBridge cannot independently verify the resulting remote state"
            )
        output_summary = (stdout or stderr).strip()
        summary = (
            output_summary[-4000:]
            if output_summary
            else (
                f"SSH command {command_id} completed with exit code "
                f"{command_result.get('exit_code')}"
            )
        )
        ended_at = _utc_now()
        return {
            "run_id": self.run_id,
            "repo_name": f"ssh:{host_id}",
            "tool": "ssh_command",
            "host_id": host_id,
            "ssh_alias": str(command_result.get("ssh_alias", "")),
            "command_id": command_id,
            "writes_remote": bool(command_result.get("writes_remote")),
            "remote_state_verified": False,
            "status": "completed" if command_result.get("ok") else "failed",
            "exit_code": int(command_result.get("exit_code", 1)),
            "started_at": started_at,
            "ended_at": ended_at,
            "duration_seconds": _duration(started_at, ended_at),
            "changed_files": [],
            "git_status": "",
            "diff_stat": "",
            "tests_run": [],
            "test_results": output_summary,
            "summary": summary,
            "remaining_risks": risks,
            "error": str(command_result.get("error", "")),
            "safety_failure": False,
            "timed_out": bool(command_result.get("timed_out")),
            "output_truncated": bool(command_result.get("output_truncated")),
            "argv": list(command_result.get("argv", [])),
            "command_result": command_result,
        }

    def _execute_external_fixture_validation(
        self,
        started_at: str,
        repo_name: str,
        input_data: dict,
    ) -> dict:
        run_dir = Path(self.run["run_dir"])
        self.event(
            "info",
            "external_fixture",
            "Fetching hash-pinned external fixture",
            {"validation": str(input_data.get("validation", "none"))},
        )
        fixture_result = fetch_validate_and_discard(
            self.config.external_fixtures,
            url=str(input_data["url"]),
            expected_sha256=str(input_data["expected_sha256"]),
            validation=str(input_data.get("validation", "none")),
            run_dir=run_dir,
        )
        self.artifacts.write_json("external_fixture_result.json", fixture_result)
        ended_at = _utc_now()
        ok = bool(fixture_result.get("ok"))
        return {
            "run_id": self.run_id,
            "repo_name": repo_name,
            "tool": "external_fixture_validation",
            "status": "completed" if ok else "failed",
            "exit_code": 0 if ok else 1,
            "started_at": started_at,
            "ended_at": ended_at,
            "duration_seconds": _duration(started_at, ended_at),
            "changed_files": [],
            "git_status": "",
            "diff_stat": "",
            "tests_run": [str(input_data.get("validation", "none"))],
            "test_results": fixture_result,
            "summary": (
                "External fixture hash verified, validated, and discarded"
                if ok
                else "External fixture validation failed and the fixture was discarded"
            ),
            "remaining_risks": [],
            "error": str(fixture_result.get("error", "")),
            "safety_failure": False,
            "fixture": fixture_result,
        }

    def _execute_project_command(
        self,
        started_at: str,
        repo_name: str,
        repo_root: Path,
        input_data: dict,
    ) -> dict:
        command_id = str(input_data["command_id"])
        normalized_target = ""
        if command_id == PYTEST_PATH_COMMAND_ID:
            normalized_target = build_pytest_path_profile(
                repo_root, str(input_data["path"])
            ).argv[-1]
            profile = build_pytest_path_profile(repo_root, normalized_target)
        elif command_id == PY_COMPILE_PATH_COMMAND_ID:
            normalized_target = build_py_compile_path_profile(
                repo_root, str(input_data["path"])
            ).argv[-1]
            profile = build_py_compile_path_profile(repo_root, normalized_target)
        elif command_id == BASH_N_PATH_COMMAND_ID:
            normalized_target = build_bash_n_path_profile(
                repo_root, str(input_data["path"])
            ).argv[-1]
            profile = build_bash_n_path_profile(repo_root, normalized_target)
        elif command_id == JSON_VALIDATE_PATH_COMMAND_ID:
            normalized_target = build_json_validate_path_profile(
                repo_root, str(input_data["path"])
            ).argv[-1]
            profile = build_json_validate_path_profile(repo_root, normalized_target)
        elif command_id == GIT_READONLY_COMMAND_ID:
            normalized_target = str(input_data.get("operation", ""))
            profile = build_git_readonly_profile(normalized_target)
        else:
            _, repo_config = resolve_repo_config(self.config, repo_name)
            repo_profiles = list(repo_config.command_profiles or [])
            profile = resolve_command_profile(command_id, repo_profiles)
        run_dir = Path(self.run["run_dir"])
        temp_root = run_dir / "tmp"
        temp_root.mkdir(parents=True, exist_ok=True)
        extra_env = {
            "TMP": str(temp_root),
            "TEMP": str(temp_root),
            "TMPDIR": str(temp_root),
        }
        pytest_temp = run_dir / "pytest-tmp"
        if command_id in {"pytest", PYTEST_PATH_COMMAND_ID} or "pytest" in profile.argv:
            pytest_temp.mkdir(parents=True, exist_ok=True)
            existing_addopts = os.environ.get("PYTEST_ADDOPTS", "").strip()
            basetemp = f'--basetemp="{pytest_temp.as_posix()}"'
            extra_env["PYTEST_ADDOPTS"] = " ".join(
                value for value in (existing_addopts, basetemp) if value
            )

        git_before = git_tools.git_status(repo_root)
        diff_before = git_tools.diff_stat(repo_root)
        dirty_before = git_tools.changed_files(repo_root)
        workspace_before = snapshot_workspace(
            repo_root, [self.config.resolve_runs_dir()]
        )
        self.artifacts.write_text("git_before.txt", git_before)
        self.event(
            "info",
            "command",
            "Starting allowlisted project command",
            {
                "command_id": command_id,
                "timeout_seconds": profile.timeout_seconds,
                "temporary_directory": str(temp_root),
                "path": normalized_target,
            },
        )
        command_result = run_command_profile(profile, repo_root, extra_env=extra_env)
        stdout = str(command_result.get("stdout", ""))
        stderr = str(command_result.get("stderr", ""))
        self.artifacts.write_text("stdout.txt", stdout)
        self.artifacts.write_text("stderr.txt", stderr)

        git_after = git_tools.git_status(repo_root)
        diff_after = git_tools.diff_stat(repo_root)
        changed_after = git_tools.changed_files(repo_root)
        workspace_after = snapshot_workspace(
            repo_root, [self.config.resolve_runs_dir()]
        )
        introduced_changes, preserved_preexisting_changes = classify_git_attribution(
            changed_after, workspace_before, workspace_after, dirty_before
        )
        self.artifacts.write_text("git_after.txt", git_after)
        self.artifacts.write_text("diff_stat.txt", diff_after)

        safety_failure = bool(
            not profile.writes_files
            and (git_before != git_after or diff_before != diff_after)
        )
        risks: list[str] = []
        if safety_failure:
            risks.append("Read-only command changed repository state")
        if command_result.get("timed_out"):
            risks.append(
                "Project command timed out; inspect saved output before retrying"
            )

        output_summary = (stdout or stderr).strip()
        summary = (
            output_summary[-4000:]
            if output_summary
            else (
                f"Project command {command_id} completed with exit code "
                f"{command_result.get('exit_code')}"
            )
        )
        errors = [str(command_result.get("error", "")).strip()]
        if safety_failure:
            errors.append("Read-only command changed repository state")
        error = "; ".join(item for item in errors if item)
        ended_at = _utc_now()
        tests_run = (
            [f"{command_id}:{normalized_target}"] if normalized_target else [command_id]
        )
        return {
            "run_id": self.run_id,
            "repo_name": repo_name,
            "tool": "project_command",
            "command_id": command_id,
            "path": normalized_target,
            "status": "completed"
            if command_result.get("ok") and not safety_failure
            else "failed",
            "exit_code": int(command_result.get("exit_code", 1)),
            "started_at": started_at,
            "ended_at": ended_at,
            "duration_seconds": _duration(started_at, ended_at),
            "changed_files": introduced_changes,
            "introduced_changes": introduced_changes,
            "preserved_preexisting_changes": preserved_preexisting_changes,
            "git_status": git_after,
            "diff_stat": diff_after,
            "tests_run": tests_run,
            "test_results": output_summary,
            "summary": summary,
            "remaining_risks": risks,
            "error": error,
            "safety_failure": safety_failure,
            "timed_out": bool(command_result.get("timed_out")),
            "output_truncated": bool(command_result.get("output_truncated")),
            "argv": list(command_result.get("argv", [])),
            "temporary_directory": str(temp_root),
            "pytest_basetemp": str(pytest_temp) if pytest_temp.exists() else "",
            "command_result": command_result,
        }

    def _error_result(self, started_at: str, ended_at: str, exc: Exception) -> dict:
        return {
            "run_id": self.run_id,
            "repo_name": self.run.get("repo_name", ""),
            "tool": self.run.get("tool", ""),
            "status": "failed",
            "exit_code": 1,
            "started_at": started_at,
            "ended_at": ended_at,
            "duration_seconds": _duration(started_at, ended_at),
            "changed_files": [],
            "git_status": "",
            "diff_stat": "",
            "tests_run": [],
            "test_results": "",
            "summary": str(exc),
            "remaining_risks": ["Async worker failed"],
            "error": str(exc),
            "safety_failure": True,
        }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run a queued CodexBridge job.")
    parser.add_argument("--config", required=True)
    parser.add_argument("--run-id", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    worker = JobWorker(Path(args.config).resolve(), args.run_id)
    raise SystemExit(worker.execute())


if __name__ == "__main__":
    main()
