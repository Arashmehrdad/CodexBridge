from __future__ import annotations

import json
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from . import git_tools
from .config import AppConfig
from .prompts import build_implementation_prompt, build_plan_prompt
from .safety import reject_destructive_command, validate_repo_relative_paths


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class CodexRunner:
    def __init__(self, config: AppConfig):
        self.config = config

    def create_run_dir(self, tool: str) -> Path:
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        run_dir = self.config.resolve_runs_dir() / f"{timestamp}_{tool}_{uuid4().hex[:8]}"
        run_dir.mkdir(parents=True, exist_ok=False)
        return run_dir

    def _codex_supports_required_flags(self) -> tuple[bool, str]:
        executable = self.config.codex.executable
        if shutil.which(executable) is None:
            return False, f"Codex executable not found: {executable}"
        result = subprocess.run(
            [executable, "exec", "--help"],
            text=True,
            capture_output=True,
        )
        help_text = f"{result.stdout}\n{result.stderr}"
        required = ["--sandbox", "--approval-policy"]
        missing = [flag for flag in required if flag not in help_text]
        if missing:
            return False, f"Codex exec missing required flags: {', '.join(missing)}"
        return True, ""

    def _write_artifacts(
        self,
        run_dir: Path,
        *,
        input_data: dict,
        prompt: str,
        stdout: str,
        stderr: str,
        result: dict,
    ) -> None:
        (run_dir / "input.json").write_text(json.dumps(input_data, indent=2), encoding="utf-8")
        (run_dir / "prompt.txt").write_text(prompt, encoding="utf-8")
        (run_dir / "stdout.txt").write_text(stdout, encoding="utf-8")
        (run_dir / "stderr.txt").write_text(stderr, encoding="utf-8")
        (run_dir / "result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")

    def _run_codex(self, repo_root: Path, sandbox: str, prompt: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                self.config.codex.executable,
                "exec",
                "--sandbox",
                sandbox,
                "--approval-policy",
                "never",
                prompt,
            ],
            cwd=repo_root,
            text=True,
            capture_output=True,
            timeout=self.config.codex.default_timeout_seconds,
        )

    def plan_task(self, repo_name: str, repo_root: Path, task: str, constraints: str | None = None) -> dict:
        prompt = build_plan_prompt(repo_name, task, constraints)
        run_dir = self.create_run_dir("codex_plan_task")
        started_at = _utc_now()
        input_data = {"repo_name": repo_name, "task": task, "constraints": constraints}
        before_status = git_tools.git_status(repo_root)
        supported, mismatch = self._codex_supports_required_flags()
        if not supported:
            result = self._base_result(run_dir, "codex_plan_task", repo_name, started_at, 1)
            result.update({"summary": mismatch, "remaining_risks": ["Codex CLI flags were not validated"], "safety_failure": True})
            self._write_artifacts(run_dir, input_data=input_data, prompt=prompt, stdout="", stderr=mismatch, result=result)
            return result

        try:
            completed = self._run_codex(repo_root, "read-only", prompt)
            stdout, stderr, exit_code = completed.stdout, completed.stderr, completed.returncode
        except subprocess.TimeoutExpired as exc:
            stdout, stderr, exit_code = exc.stdout or "", exc.stderr or "Codex run timed out", 124

        after_status = git_tools.git_status(repo_root)
        safety_failure = before_status != after_status
        result = self._base_result(run_dir, "codex_plan_task", repo_name, started_at, exit_code)
        result.update(
            {
                "summary": stdout.strip() or stderr.strip(),
                "remaining_risks": ["Plan mode changed git status"] if safety_failure else [],
                "safety_failure": safety_failure,
                "changed_files": git_tools.changed_files(repo_root),
                "git_status": after_status,
                "diff_stat": git_tools.diff_stat(repo_root),
            }
        )
        self._write_artifacts(run_dir, input_data=input_data, prompt=prompt, stdout=stdout, stderr=stderr, result=result)
        return result

    def implement_task(
        self,
        repo_name: str,
        repo_root: Path,
        approved_plan: str,
        allowed_files: list[str],
        tests: list[str],
    ) -> dict:
        validate_repo_relative_paths(repo_root, allowed_files)
        for test in tests:
            reject_destructive_command(test)

        prompt = build_implementation_prompt(repo_name, approved_plan, allowed_files, tests)
        run_dir = self.create_run_dir("codex_implement_task")
        started_at = _utc_now()
        input_data = {
            "repo_name": repo_name,
            "approved_plan": approved_plan,
            "allowed_files": allowed_files,
            "tests": tests,
        }
        supported, mismatch = self._codex_supports_required_flags()
        if not supported:
            result = self._base_result(run_dir, "codex_implement_task", repo_name, started_at, 1)
            result.update({"summary": mismatch, "remaining_risks": ["Codex CLI flags were not validated"], "safety_failure": True})
            self._write_artifacts(run_dir, input_data=input_data, prompt=prompt, stdout="", stderr=mismatch, result=result)
            return result

        try:
            completed = self._run_codex(repo_root, "workspace-write", prompt)
            stdout, stderr, exit_code = completed.stdout, completed.stderr, completed.returncode
        except subprocess.TimeoutExpired as exc:
            stdout, stderr, exit_code = exc.stdout or "", exc.stderr or "Codex run timed out", 124

        changed = git_tools.changed_files(repo_root)
        allowed = set(allowed_files)
        violations = [path for path in changed if path not in allowed]
        safety_failure = bool(violations)
        risks = []
        if violations:
            risks.append(f"Changed files outside allowed_files: {violations}")
        if exit_code != 0:
            risks.append("Codex exited nonzero")

        result = self._base_result(run_dir, "codex_implement_task", repo_name, started_at, exit_code)
        result.update(
            {
                "summary": stdout.strip() or stderr.strip(),
                "remaining_risks": risks,
                "safety_failure": safety_failure,
                "changed_files": changed,
                "git_status": git_tools.git_status(repo_root),
                "diff_stat": git_tools.diff_stat(repo_root),
                "tests_run": tests,
            }
        )
        self._write_artifacts(run_dir, input_data=input_data, prompt=prompt, stdout=stdout, stderr=stderr, result=result)
        return result

    def _base_result(self, run_dir: Path, tool: str, repo_name: str, started_at: str, exit_code: int) -> dict:
        return {
            "run_id": run_dir.name,
            "run_dir": str(run_dir),
            "tool": tool,
            "repo_name": repo_name,
            "started_at": started_at,
            "ended_at": _utc_now(),
            "exit_code": exit_code,
            "changed_files": [],
            "git_status": "",
            "diff_stat": "",
            "tests_run": [],
            "test_results": "",
            "summary": "",
            "remaining_risks": [],
            "safety_failure": False,
        }


def latest_run_result(runs_dir: Path) -> dict:
    candidates = sorted(runs_dir.glob("*/result.json"), key=lambda path: path.stat().st_mtime, reverse=True)
    if not candidates:
        raise FileNotFoundError("No run results found")
    return json.loads(candidates[0].read_text(encoding="utf-8"))

