from __future__ import annotations

import argparse
import subprocess
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

from . import git_tools
from .config import load_config, resolve_repo
from .events import ArtifactWriter, redact_and_truncate
from .policy import decide_implementation_task, decide_plan_task
from .prompts import build_implementation_prompt, build_plan_prompt
from .run_store import RunStore
from .run_guards import (
    allowed_write_directories,
    assess_implementation_output,
    assess_plan_output,
    changed_workspace_paths,
    out_of_scope_workspace_changes,
    snapshot_workspace,
)
from .runner import CodexRunner, _safe_command_args
from .safety import reject_destructive_command, validate_repo_relative_paths


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _duration(started_at: str, ended_at: str) -> float:
    started = datetime.fromisoformat(started_at)
    ended = datetime.fromisoformat(ended_at)
    return round((ended - started).total_seconds(), 3)


def _stream_pipe(pipe, output_path: Path, sink: list[str], limit: int = 40000) -> None:
    with output_path.open("a", encoding="utf-8", errors="replace") as handle:
        for line in iter(pipe.readline, ""):
            handle.write(line)
            handle.flush()
            if sum(len(item) for item in sink) < limit:
                sink.append(line)
    pipe.close()


class JobWorker:
    def __init__(self, config_path: Path, run_id: str):
        self.config_path = config_path
        self.config = load_config(config_path)
        self.store = RunStore(self.config.resolve_runs_dir())
        self.run = self.store.get_run(run_id)
        self.run_id = run_id
        self.artifacts = ArtifactWriter(Path(self.run["run_dir"]))

    def event(
        self, level: str, stage: str, message: str, data: dict | None = None
    ) -> None:
        event = self.store.append_event(
            self.run_id,
            level=level,
            stage=stage,
            message=message,
            data=redact_and_truncate(data or {}),
        )
        self.artifacts.append_event(event)

    def execute(self) -> int:
        started_at = _utc_now()
        self.store.update_run(self.run_id, status="running", started_at=started_at)
        self.event("info", "worker", "Worker started")
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
            self.event(
                "info" if status == "completed" else "error",
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

    def _execute_inner(self, started_at: str) -> dict:
        input_data = self.run["input"]
        repo_name = input_data["repo_name"]
        repo_root = resolve_repo(self.config, repo_name)
        tool = self.run["tool"]

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
        ignored_run_roots = [Path(self.run["run_dir"])]
        workspace_before = snapshot_workspace(repo_root, ignored_run_roots)
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
        process = subprocess.Popen(
            args,
            cwd=repo_root,
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
                Path(self.run["run_dir"]) / "stdout.txt",
                stdout_parts,
            ),
        )
        stderr_thread = threading.Thread(
            target=_stream_pipe,
            args=(
                process.stderr,
                Path(self.run["run_dir"]) / "stderr.txt",
                stderr_parts,
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
        changed = git_tools.changed_files(repo_root)
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
                {path for path in changed if path not in set(allowed_files)}
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

        ended_at = _utc_now()
        return {
            "run_id": self.run_id,
            "repo_name": repo_name,
            "tool": tool,
            "status": "failed"
            if safety_failure or blocked or exit_code != 0
            else "completed",
            "exit_code": exit_code,
            "started_at": started_at,
            "ended_at": ended_at,
            "duration_seconds": _duration(started_at, ended_at),
            "changed_files": changed,
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
            "error": "; ".join(blockers),
            "safety_failure": safety_failure,
            "codex_exit_code": exit_code,
            "codex_command_args": _safe_command_args(args),
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
