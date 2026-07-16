"""
command_profiles.py — allowlisted profiles for durable project-command execution.

Rules:
- Only command_id is accepted; no arbitrary command text.
- All profiles use argv arrays with shell=False.
- No package installation, network commands, deployment, deletion,
  PowerShell command strings, cmd.exe, Invoke-Expression, or shell=True.
- Per-repo overrides may be supplied in config.yaml under repos.<name>.command_profiles.
- Project commands prefer the target repository's local virtual environment.
"""

from __future__ import annotations

import os
import re
import stat
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from pathlib import PurePosixPath
from typing import Any

# ---------------------------------------------------------------------------
# Limits
# ---------------------------------------------------------------------------
MAX_OUTPUT_BYTES = 100_000  # cap combined stdout+stderr
DEFAULT_TIMEOUT = 120  # seconds

# ---------------------------------------------------------------------------
# Blocked patterns that must never appear in any argv element
# ---------------------------------------------------------------------------
_BLOCKED_ARGV_PATTERNS = [
    re.compile(r"\bpip\s+install\b", re.IGNORECASE),
    re.compile(r"\bpip3\s+install\b", re.IGNORECASE),
    re.compile(r"\bnpm\s+install\b", re.IGNORECASE),
    re.compile(r"\byarn\s+add\b", re.IGNORECASE),
    re.compile(r"\bcmd(\.exe)?\b", re.IGNORECASE),
    re.compile(r"\bpowershell(\.exe)?\b", re.IGNORECASE),
    re.compile(r"\bInvoke-Expression\b", re.IGNORECASE),
    re.compile(r"\bInvoke-Command\b", re.IGNORECASE),
    re.compile(r"\brm\s+-rf\b", re.IGNORECASE),
    re.compile(r"\brmdir\b", re.IGNORECASE),
    re.compile(r"\bdel\s*/s\b", re.IGNORECASE),
    re.compile(r"\bdeploy\b", re.IGNORECASE),
    re.compile(r"\bdocker\s+push\b", re.IGNORECASE),
    re.compile(r"\bssh\b", re.IGNORECASE),
    re.compile(r"\bcurl\b", re.IGNORECASE),
    re.compile(r"\bwget\b", re.IGNORECASE),
    re.compile(r";|&&|\|\||\|", re.IGNORECASE),  # shell chaining / piping
    re.compile(r"`"),  # backtick execution
    re.compile(r"\$\("),  # command substitution
]

# Valid command_id format
_COMMAND_ID_RE = re.compile(r"^[A-Za-z0-9_\-]+$")
_PYTHON_LAUNCHERS = frozenset({"python", "python.exe", "python3", "python3.exe"})
PYTEST_PATH_COMMAND_ID = "pytest_path"
PY_COMPILE_PATH_COMMAND_ID = "py_compile_path"
BASH_N_PATH_COMMAND_ID = "bash_n_path"
JSON_VALIDATE_PATH_COMMAND_ID = "json_validate_path"
GIT_READONLY_COMMAND_ID = "git_readonly"
_CONTROL_CHAR_RE = re.compile(r"[\x00-\x1f\x7f]")
_WINDOWS_DRIVE_RE = re.compile(r"^[A-Za-z]:")
_PATH_WILDCARD_RE = re.compile(r"[*?\[\]]")
_JSON_SUFFIXES = frozenset({".json"})
_BASH_SUFFIXES = frozenset({".sh", ".bash"})
_PYTHON_SUFFIXES = frozenset({".py"})
_GIT_READONLY_OPERATIONS: dict[str, list[str]] = {
    "status": ["git", "status", "--short", "--branch"],
    "diff_check": ["git", "diff", "--check"],
    "diff_name_only": ["git", "diff", "--name-only"],
    "ls_files": ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
}


@dataclass
class CommandProfileSpec:
    command_id: str
    argv: list[str]
    timeout_seconds: int = DEFAULT_TIMEOUT
    description: str = ""
    writes_files: bool = False
    async_only: bool = False

    def validate(self) -> None:
        if not self.command_id or not _COMMAND_ID_RE.match(self.command_id):
            raise ValueError(f"Invalid command_id: {self.command_id!r}")
        if not self.argv:
            raise ValueError("argv must not be empty")
        for element in self.argv:
            for pattern in _BLOCKED_ARGV_PATTERNS:
                if pattern.search(element):
                    raise ValueError(
                        f"Blocked pattern in argv element {element!r}: {pattern.pattern}"
                    )


# ---------------------------------------------------------------------------
# Built-in profiles
# ---------------------------------------------------------------------------
BUILTIN_PROFILES: dict[str, CommandProfileSpec] = {
    "pytest": CommandProfileSpec(
        command_id="pytest",
        argv=["python", "-m", "pytest", "-q"],
        timeout_seconds=600,
        description="Run pytest in quiet mode as a durable async command",
        async_only=True,
    ),
    "ruff_check": CommandProfileSpec(
        command_id="ruff_check",
        argv=["python", "-m", "ruff", "check", "."],
        timeout_seconds=60,
        description="Run ruff lint check",
    ),
    "ruff_format_check": CommandProfileSpec(
        command_id="ruff_format_check",
        argv=["python", "-m", "ruff", "format", "--check", "."],
        timeout_seconds=60,
        description="Run ruff format check (no changes written)",
    ),
    "ruff_format": CommandProfileSpec(
        command_id="ruff_format",
        argv=["python", "-m", "ruff", "format", "."],
        timeout_seconds=60,
        description="Apply Ruff formatting",
        writes_files=True,
    ),
    "mypy": CommandProfileSpec(
        command_id="mypy",
        argv=["python", "-m", "mypy", "."],
        timeout_seconds=120,
        description="Run mypy type checking",
    ),
    "pip_check": CommandProfileSpec(
        command_id="pip_check",
        argv=["python", "-m", "pip", "check"],
        timeout_seconds=60,
        description="Verify no broken package requirements",
    ),
    "git_status": CommandProfileSpec(
        command_id="git_status",
        argv=["git", "status", "--short", "--branch"],
        timeout_seconds=30,
        description="Read repository branch and working-tree status",
        writes_files=False,
    ),
    "git_diff_check": CommandProfileSpec(
        command_id="git_diff_check",
        argv=["git", "diff", "--check"],
        timeout_seconds=30,
        description="Check for whitespace errors in git diff",
    ),
    GIT_READONLY_COMMAND_ID: CommandProfileSpec(
        command_id=GIT_READONLY_COMMAND_ID,
        argv=list(_GIT_READONLY_OPERATIONS["status"]),
        timeout_seconds=30,
        description="Run one fixed read-only git operation",
    ),
}


def _is_symlink_or_reparse_point(path: Path) -> bool:
    try:
        if path.is_symlink():
            return True
        file_attributes = getattr(path.lstat(), "st_file_attributes", 0)
    except OSError:
        return False
    return bool(file_attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0))


def validate_and_normalize_pytest_target(repo_root: Path, target: str) -> str:
    """Validate one repo-relative pytest path target and return POSIX form."""
    raw_target = str(target)
    if not raw_target.strip():
        raise ValueError("Pytest path target must not be empty")
    if _CONTROL_CHAR_RE.search(raw_target):
        raise ValueError("Pytest path target contains control characters")

    path_part, separator, selector = raw_target.partition("::")
    normalized_path = path_part.strip().replace("\\", "/")
    if not normalized_path:
        raise ValueError("Pytest path target must include a repository path")
    if normalized_path.startswith("-"):
        raise ValueError("Pytest path target must not start with an option")
    if normalized_path.startswith(("/", "//")) or raw_target.startswith(("\\\\", "//")):
        raise ValueError("Pytest path target must be repository-relative")
    if _WINDOWS_DRIVE_RE.match(normalized_path):
        raise ValueError("Pytest path target must not include a drive prefix")
    if _PATH_WILDCARD_RE.search(normalized_path):
        raise ValueError("Pytest path target must not contain wildcards")

    parts = PurePosixPath(normalized_path).parts
    if not parts:
        raise ValueError("Pytest path target must include a repository path")
    if any(part in {"", ".", ".."} for part in parts):
        raise ValueError("Pytest path target must not contain traversal segments")

    repo_root = repo_root.resolve()
    candidate = repo_root.joinpath(*parts)
    current = repo_root
    for part in parts:
        current = current / part
        if _is_symlink_or_reparse_point(current):
            raise ValueError(
                "Pytest path target must not traverse symlinks or reparse points"
            )

    if not candidate.exists():
        raise ValueError("Pytest path target does not exist")
    if candidate.is_dir():
        normalized = candidate.relative_to(repo_root).as_posix()
    elif candidate.is_file():
        if candidate.suffix != ".py":
            raise ValueError("Pytest path target file must be a .py file")
        normalized = candidate.relative_to(repo_root).as_posix()
    else:
        raise ValueError("Pytest path target must be a file or directory")

    if not normalized:
        raise ValueError("Pytest path target must not resolve to the repository root")
    selector_suffix = f"{separator}{selector}" if separator else ""
    return f"{normalized}{selector_suffix}"


def build_pytest_path_profile(repo_root: Path, target: str) -> CommandProfileSpec:
    normalized_target = validate_and_normalize_pytest_target(repo_root, target)
    profile = CommandProfileSpec(
        command_id=PYTEST_PATH_COMMAND_ID,
        argv=["python", "-m", "pytest", "-q", normalized_target],
        timeout_seconds=600,
        description="Run pytest in quiet mode for one validated repo-relative path",
        async_only=True,
        writes_files=False,
    )
    profile.validate()
    return profile


def validate_repo_relative_command_path(
    repo_root: Path, target: str, *, allowed_suffixes: set[str] | frozenset[str]
) -> str:
    raw_target = str(target)
    if not raw_target.strip():
        raise ValueError("Validated path target must not be empty")
    if _CONTROL_CHAR_RE.search(raw_target):
        raise ValueError("Validated path target contains control characters")
    normalized_path = raw_target.strip().replace("\\", "/")
    if normalized_path.startswith("-"):
        raise ValueError("Validated path target must not start with an option")
    if normalized_path.startswith(("/", "//")) or raw_target.startswith(("\\\\", "//")):
        raise ValueError("Validated path target must be repository-relative")
    if _WINDOWS_DRIVE_RE.match(normalized_path):
        raise ValueError("Validated path target must not include a drive prefix")
    if _PATH_WILDCARD_RE.search(normalized_path):
        raise ValueError("Validated path target must not contain wildcards")
    parts = PurePosixPath(normalized_path).parts
    if not parts or any(part in {"", ".", ".."} for part in parts):
        raise ValueError("Validated path target must not contain traversal segments")
    repo_root = repo_root.resolve()
    candidate = repo_root.joinpath(*parts)
    current = repo_root
    for part in parts:
        current = current / part
        if _is_symlink_or_reparse_point(current):
            raise ValueError(
                "Validated path target must not traverse symlinks or reparse points"
            )
    if not candidate.exists() or not candidate.is_file():
        raise ValueError("Validated path target must be an existing file")
    if candidate.suffix.lower() not in allowed_suffixes:
        allowed_text = ", ".join(sorted(allowed_suffixes))
        raise ValueError(f"Validated path target must use one of: {allowed_text}")
    return candidate.relative_to(repo_root).as_posix()


def build_py_compile_path_profile(repo_root: Path, target: str) -> CommandProfileSpec:
    normalized = validate_repo_relative_command_path(
        repo_root, target, allowed_suffixes=_PYTHON_SUFFIXES
    )
    profile = CommandProfileSpec(
        command_id=PY_COMPILE_PATH_COMMAND_ID,
        argv=["python", "-m", "py_compile", normalized],
        timeout_seconds=120,
        description="Compile one validated Python file without executing it",
    )
    profile.validate()
    return profile


def build_bash_n_path_profile(repo_root: Path, target: str) -> CommandProfileSpec:
    normalized = validate_repo_relative_command_path(
        repo_root, target, allowed_suffixes=_BASH_SUFFIXES
    )
    profile = CommandProfileSpec(
        command_id=BASH_N_PATH_COMMAND_ID,
        argv=["bash", "-n", normalized],
        timeout_seconds=120,
        description="Run bash -n on one validated shell script",
    )
    profile.validate()
    return profile


def build_json_validate_path_profile(
    repo_root: Path, target: str
) -> CommandProfileSpec:
    normalized = validate_repo_relative_command_path(
        repo_root, target, allowed_suffixes=_JSON_SUFFIXES
    )
    profile = CommandProfileSpec(
        command_id=JSON_VALIDATE_PATH_COMMAND_ID,
        argv=["python", "-m", "json.tool", normalized],
        timeout_seconds=120,
        description="Validate one repository JSON file",
    )
    profile.validate()
    return profile


def build_git_readonly_profile(operation: str) -> CommandProfileSpec:
    argv = _GIT_READONLY_OPERATIONS.get(str(operation))
    if argv is None:
        raise ValueError(
            f"Unsupported git read-only operation: {operation!r}. Allowed: {sorted(_GIT_READONLY_OPERATIONS)}"
        )
    profile = CommandProfileSpec(
        command_id=GIT_READONLY_COMMAND_ID,
        argv=list(argv),
        timeout_seconds=30,
        description="Run one fixed read-only git operation",
    )
    profile.validate()
    return profile


def _parse_repo_profile(raw: dict[str, Any]) -> CommandProfileSpec:
    """Parse a repo-level command profile override from config.yaml."""
    command_id = str(raw.get("command_id", ""))
    argv = raw.get("argv")
    if not isinstance(argv, list) or not argv:
        raise ValueError(
            f"Repo command profile '{command_id}' must have a non-empty argv list"
        )
    builtin = BUILTIN_PROFILES.get(command_id)
    timeout = int(
        raw.get(
            "timeout_seconds",
            builtin.timeout_seconds if builtin is not None else DEFAULT_TIMEOUT,
        )
    )
    description = str(
        raw.get("description", builtin.description if builtin is not None else "")
    )
    async_only = bool(
        raw.get("async_only", builtin.async_only if builtin is not None else False)
    )
    spec = CommandProfileSpec(
        command_id=command_id,
        argv=[str(a) for a in argv],
        timeout_seconds=timeout,
        description=description,
        writes_files=bool(
            raw.get(
                "writes_files",
                builtin.writes_files if builtin is not None else False,
            )
        ),
        async_only=async_only,
    )
    spec.validate()
    return spec


def resolve_command_profile(
    command_id: str,
    repo_profiles: list[dict[str, Any]] | None = None,
) -> CommandProfileSpec:
    """
    Return the CommandProfileSpec for *command_id*.

    Repo-level overrides (from config.yaml) shadow built-ins with the same ID.
    Raises ValueError for unknown or invalid command IDs.
    """
    if not command_id or not _COMMAND_ID_RE.match(command_id):
        raise ValueError(f"Invalid command_id: {command_id!r}")

    # Repo-level overrides take precedence
    if repo_profiles:
        for raw in repo_profiles:
            if str(raw.get("command_id", "")) == command_id:
                return _parse_repo_profile(raw)

    profile = BUILTIN_PROFILES.get(command_id)
    if profile is None:
        allowed = sorted(BUILTIN_PROFILES.keys())
        raise ValueError(
            f"Unknown command_id: {command_id!r}. Allowed built-ins: {allowed}"
        )
    return profile


# ---------------------------------------------------------------------------
# Execution
# ---------------------------------------------------------------------------


def _virtualenv_candidates(cwd: Path) -> tuple[tuple[str, ...], ...]:
    """Return platform-preferred repository-local Python candidates."""
    windows = (
        (".venv", "Scripts", "python.exe"),
        ("venv", "Scripts", "python.exe"),
        ("venv312", "Scripts", "python.exe"),
    )
    posix = (
        (".venv", "bin", "python"),
        ("venv", "bin", "python"),
        ("venv312", "bin", "python"),
    )
    return windows + posix if os.name == "nt" else posix + windows


def find_repo_python(cwd: Path) -> tuple[Path | None, Path | None]:
    """
    Find a repository-local virtual-environment interpreter.

    Returns ``(python_executable, virtual_env_root)``. The candidate path is
    kept inside the repository lexically; symlink targets are not resolved so
    normal POSIX virtual environments remain supported.
    """
    repo_root = cwd.resolve()
    for env_name in ("VIRTUAL_ENV", "CONDA_PREFIX"):
        value = os.environ.get(env_name, "").strip()
        if not value:
            continue
        candidate_root = Path(value)
        interpreter = _interpreter_in_env(candidate_root)
        if interpreter is None:
            continue
        if _is_within_repo(candidate_root, repo_root):
            return interpreter.absolute(), candidate_root.absolute()
    for relative_parts in _virtualenv_candidates(repo_root):
        candidate = repo_root.joinpath(*relative_parts)
        try:
            if candidate.is_file():
                return candidate.absolute(), candidate.parent.parent.absolute()
        except OSError:
            continue
    return None, None


def _interpreter_in_env(env_root: Path) -> Path | None:
    candidates = (
        env_root / "Scripts" / "python.exe",
        env_root / "bin" / "python",
    )
    for candidate in candidates:
        try:
            if candidate.is_file():
                return candidate
        except OSError:
            continue
    return None


def _is_within_repo(candidate_root: Path, repo_root: Path) -> bool:
    try:
        candidate_root.resolve().relative_to(repo_root.resolve())
        return True
    except ValueError:
        return False


def prepare_repo_execution(
    profile: CommandProfileSpec,
    cwd: Path,
) -> tuple[list[str], dict[str, str], Path | None, Path | None]:
    """Build argv and environment for a command executed in *cwd*."""
    argv = list(profile.argv)
    env = os.environ.copy()
    python_executable, virtual_env = find_repo_python(cwd)

    if python_executable is not None and virtual_env is not None:
        scripts_dir = python_executable.parent
        current_path = env.get("PATH", "")
        env["PATH"] = (
            str(scripts_dir)
            if not current_path
            else f"{scripts_dir}{os.pathsep}{current_path}"
        )
        env["VIRTUAL_ENV"] = str(virtual_env)
        env.pop("PYTHONHOME", None)

        # Built-ins and normal repo profiles use a bare Python launcher. Replace
        # it directly so the target repository's packages are always selected.
        if argv and argv[0].lower() in _PYTHON_LAUNCHERS:
            argv[0] = str(python_executable)

    return argv, env, python_executable, virtual_env


def run_command_profile(
    profile: CommandProfileSpec,
    cwd: Path,
    *,
    extra_env: dict[str, str] | None = None,
) -> dict:
    """
    Execute *profile* in *cwd* with shell=False.
    Returns a structured result with stdout, stderr, exit_code, duration, and truncation flag.
    """
    argv, env, _, _ = prepare_repo_execution(profile, cwd)
    if extra_env:
        env.update({str(key): str(value) for key, value in extra_env.items()})
    started = time.monotonic()
    timed_out = False
    try:
        completed = subprocess.run(
            argv,
            cwd=cwd,
            env=env,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            shell=False,
            timeout=profile.timeout_seconds,
        )
        stdout = completed.stdout or ""
        stderr = completed.stderr or ""
        exit_code = completed.returncode
    except subprocess.TimeoutExpired as exc:
        stdout = (
            (exc.stdout or b"").decode("utf-8", errors="replace")
            if isinstance(exc.stdout, bytes)
            else (exc.stdout or "")
        )
        stderr = (
            (exc.stderr or b"").decode("utf-8", errors="replace")
            if isinstance(exc.stderr, bytes)
            else (exc.stderr or "")
        )
        exit_code = 124
        timed_out = True
    except (OSError, PermissionError) as exc:
        stdout = ""
        stderr = str(exc)
        exit_code = 1
        timed_out = False

    duration = time.monotonic() - started

    # Cap combined output
    combined = stdout + stderr
    output_truncated = False
    if len(combined.encode("utf-8")) > MAX_OUTPUT_BYTES:
        # Trim stdout first, then stderr
        stdout_bytes = stdout.encode("utf-8")
        stderr_bytes = stderr.encode("utf-8")
        if len(stdout_bytes) > MAX_OUTPUT_BYTES:
            stdout = stdout_bytes[:MAX_OUTPUT_BYTES].decode("utf-8", errors="replace")
            stderr = ""
        else:
            remaining = MAX_OUTPUT_BYTES - len(stdout_bytes)
            stderr = stderr_bytes[:remaining].decode("utf-8", errors="replace")
        output_truncated = True

    return {
        "ok": exit_code == 0 and not timed_out,
        "command_id": profile.command_id,
        "argv": argv,
        "exit_code": exit_code,
        "timed_out": timed_out,
        "duration_seconds": round(duration, 3),
        "stdout": stdout,
        "stderr": stderr,
        "output_truncated": output_truncated,
        "error": f"Timed out after {profile.timeout_seconds}s"
        if timed_out
        else (stderr.strip()[:300] if exit_code != 0 else ""),
    }
