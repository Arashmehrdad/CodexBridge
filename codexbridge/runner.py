from __future__ import annotations

import json
import os
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


def _is_windowsapps_path(path: str | Path | None) -> bool:
    return bool(path) and "windowsapps" in str(path).lower()


def _path_info(path: str | Path | None) -> dict:
    if not path:
        return {"path": None, "exists": False, "is_file": False, "is_dir": False}
    candidate = Path(path)
    return {
        "path": str(candidate),
        "exists": candidate.exists(),
        "is_file": candidate.is_file(),
        "is_dir": candidate.is_dir(),
    }


def _safe_command_args(args: list[str]) -> list[str]:
    if not args:
        return []
    return [*args[:-1], "<prompt>"]


class CodexRunner:
    def __init__(self, config: AppConfig):
        self.config = config

    def create_run_dir(self, tool: str) -> Path:
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        run_dir = self.config.resolve_runs_dir() / f"{timestamp}_{tool}_{uuid4().hex[:8]}"
        run_dir.mkdir(parents=True, exist_ok=False)
        return run_dir

    def _resolve_codex_executable(self) -> str:
        executable = self.config.codex.executable
        configured = Path(executable)
        if configured.is_absolute() or configured.parent != Path("."):
            if not configured.exists() or configured.is_dir():
                raise FileNotFoundError(f"Configured Codex executable is not a file: {configured}")
            return str(configured)

        candidates: list[str] = []
        if os.name == "nt":
            for name in (executable, f"{executable}.cmd", f"{executable}.exe"):
                resolved = shutil.which(name)
                if resolved and not _is_windowsapps_path(resolved):
                    candidates.append(resolved)
            sandbox_bin = Path.home() / ".codex" / ".sandbox-bin" / f"{executable}.exe"
            if sandbox_bin.exists():
                candidates.append(str(sandbox_bin))

        resolved = shutil.which(executable)
        if resolved:
            if _is_windowsapps_path(resolved):
                raise PermissionError(f"Refusing WindowsApps Codex executable; configure a launchable codex.exe or codex.cmd: {resolved}")
            candidates.append(resolved)

        if candidates:
            return candidates[0]
        raise FileNotFoundError(f"Codex executable not found: {executable}")

    def _subprocess_diagnostics(self, args: list[str], cwd: Path, exc: BaseException) -> str:
        attempted = args[0] if args else self.config.codex.executable
        resolved = attempted if Path(attempted).is_absolute() else shutil.which(attempted)
        details = {
            "executable_attempted": attempted,
            "resolved_path": resolved,
            "cwd": str(cwd),
            "path_info": _path_info(resolved or attempted),
            "path_excerpt": os.environ.get("PATH", "")[:1000],
            "command_args": args,
            "original_exception": repr(exc),
        }
        return json.dumps(details, indent=2)

    def _run_subprocess(self, args: list[str], cwd: Path, *, timeout: int | None = None) -> subprocess.CompletedProcess[str]:
        try:
            return subprocess.run(
                args,
                cwd=cwd,
                text=True,
                encoding="utf-8",
                errors="replace",
                capture_output=True,
                timeout=timeout,
            )
        except (OSError, PermissionError) as exc:
            raise RuntimeError(self._subprocess_diagnostics(args, cwd, exc)) from exc

    def _codex_exec_help(self, executable: str) -> str:
        result = self._run_subprocess([executable, "exec", "--help"], Path.cwd())
        return f"{result.stdout}\n{result.stderr}"

    def _codex_exec_args(self, executable: str, sandbox: str, help_text: str, prompt: str) -> list[str]:
        args = [executable, "exec"]
        if "--sandbox" in help_text:
            args.extend(["--sandbox", sandbox])
        else:
            raise ValueError("Codex exec missing required --sandbox support")

        windows_sandbox = self.config.codex.windows_sandbox.strip()
        if windows_sandbox:
            args.extend(["-c", f'windows.sandbox="{windows_sandbox}"'])

        if self.config.codex.sandbox_private_desktop is not None:
            private_desktop = "true" if self.config.codex.sandbox_private_desktop else "false"
            args.extend(["-c", f"windows.sandbox_private_desktop={private_desktop}"])

        model = self.config.codex.model.strip()
        if model:
            args.extend(["-m", model])

        if "--approval-policy" in help_text:
            args.extend(["--approval-policy", "never"])
        elif "--ask-for-approval" in help_text:
            args.extend(["--ask-for-approval", "never"])

        args.append(prompt)
        return args

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

    def _run_codex(self, repo_root: Path, sandbox: str, prompt: str) -> tuple[subprocess.CompletedProcess[str], list[str]]:
        executable = self._resolve_codex_executable()
        help_text = self._codex_exec_help(executable)
        args = self._codex_exec_args(executable, sandbox, help_text, prompt)
        return self._run_subprocess(args, repo_root, timeout=self.config.codex.default_timeout_seconds), args

    def plan_task(self, repo_name: str, repo_root: Path, task: str, constraints: str | None = None) -> dict:
        prompt = build_plan_prompt(repo_name, task, constraints)
        run_dir = self.create_run_dir("codex_plan_task")
        started_at = _utc_now()
        input_data = {"repo_name": repo_name, "task": task, "constraints": constraints}
        before_status = git_tools.git_status(repo_root)
        try:
            completed, _codex_args = self._run_codex(repo_root, "read-only", prompt)
            stdout, stderr, exit_code = completed.stdout, completed.stderr, completed.returncode
        except subprocess.TimeoutExpired as exc:
            stdout, stderr, exit_code = exc.stdout or "", exc.stderr or "Codex run timed out", 124
        except Exception as exc:
            mismatch = str(exc)
            result = self._base_result(run_dir, "codex_plan_task", repo_name, started_at, 1)
            result.update({"summary": mismatch, "remaining_risks": ["Codex CLI launch failed"], "safety_failure": True})
            self._write_artifacts(run_dir, input_data=input_data, prompt=prompt, stdout="", stderr=mismatch, result=result)
            return result

        after_status = git_tools.git_status(repo_root)
        safety_failure = before_status != after_status
        result = self._base_result(run_dir, "codex_plan_task", repo_name, started_at, exit_code)
        result.update(
            {
                "summary": (stdout or "").strip() or (stderr or "").strip(),
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
        codex_args: list[str] = []
        try:
            completed, codex_args = self._run_codex(repo_root, "workspace-write", prompt)
            stdout, stderr, exit_code = completed.stdout, completed.stderr, completed.returncode
        except subprocess.TimeoutExpired as exc:
            stdout, stderr, exit_code = exc.stdout or "", exc.stderr or "Codex run timed out", 124
        except Exception as exc:
            mismatch = str(exc)
            result = self._base_result(run_dir, "codex_implement_task", repo_name, started_at, 1)
            result.update({"summary": mismatch, "remaining_risks": ["Codex CLI launch failed"], "safety_failure": True})
            self._write_artifacts(run_dir, input_data=input_data, prompt=prompt, stdout="", stderr=mismatch, result=result)
            return result

        changed = git_tools.changed_files(repo_root)
        allowed = set(allowed_files)
        violations = [path for path in changed if path not in allowed]
        safety_failure = bool(violations)
        risks = []
        if violations:
            risks.append(f"Changed files outside allowed_files: {violations}")
        if exit_code != 0:
            risks.append("Codex exited nonzero")
        combined_output = f"{stdout or ''}\n{stderr or ''}"
        shell_spawn_failure = "windows sandbox: spawn setup refresh" in combined_output
        if shell_spawn_failure:
            risks.append("Codex shell spawn failed during Windows sandbox setup")

        result = self._base_result(run_dir, "codex_implement_task", repo_name, started_at, exit_code)
        result.update(
            {
                "summary": (stdout or "").strip() or (stderr or "").strip(),
                "remaining_risks": risks,
                "safety_failure": safety_failure,
                "changed_files": changed,
                "git_status": git_tools.git_status(repo_root),
                "diff_stat": git_tools.diff_stat(repo_root),
                "tests_run": tests,
                "codex_command_args": _safe_command_args(codex_args),
                "codex_sandbox": "workspace-write",
                "codex_windows_sandbox": self.config.codex.windows_sandbox,
                "codex_sandbox_private_desktop": self.config.codex.sandbox_private_desktop,
                "codex_cwd": str(repo_root),
                "codex_exit_code": exit_code,
                "codex_stdout_excerpt": (stdout or "")[:4000],
                "codex_stderr_excerpt": (stderr or "")[:4000],
                "shell_spawn_failure": shell_spawn_failure,
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
