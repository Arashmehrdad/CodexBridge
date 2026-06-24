"""
command_profiles.py — allowlisted command profiles for run_project_command.

Rules:
- Only command_id is accepted; no arbitrary command text.
- All profiles use argv arrays with shell=False.
- No package installation, network commands, deployment, deletion,
  PowerShell command strings, cmd.exe, Invoke-Expression, or shell=True.
- Per-repo overrides may be supplied in config.yaml under repos.<name>.command_profiles.
"""
from __future__ import annotations

import re
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Limits
# ---------------------------------------------------------------------------
MAX_OUTPUT_BYTES = 100_000   # cap combined stdout+stderr
DEFAULT_TIMEOUT = 120        # seconds

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
    re.compile(r";|&&|\|\||\|", re.IGNORECASE),   # shell chaining / piping
    re.compile(r"`"),                               # backtick execution
    re.compile(r"\$\("),                            # command substitution
]

# Valid command_id format
_COMMAND_ID_RE = re.compile(r"^[A-Za-z0-9_\-]+$")


@dataclass
class CommandProfileSpec:
    command_id: str
    argv: list[str]
    timeout_seconds: int = DEFAULT_TIMEOUT
    description: str = ""

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
        timeout_seconds=120,
        description="Run pytest in quiet mode",
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
    "git_diff_check": CommandProfileSpec(
        command_id="git_diff_check",
        argv=["git", "diff", "--check"],
        timeout_seconds=30,
        description="Check for whitespace errors in git diff",
    ),
}


def _parse_repo_profile(raw: dict[str, Any]) -> CommandProfileSpec:
    """Parse a repo-level command profile override from config.yaml."""
    command_id = str(raw.get("command_id", ""))
    argv = raw.get("argv")
    if not isinstance(argv, list) or not argv:
        raise ValueError(f"Repo command profile '{command_id}' must have a non-empty argv list")
    timeout = int(raw.get("timeout_seconds", DEFAULT_TIMEOUT))
    description = str(raw.get("description", ""))
    spec = CommandProfileSpec(
        command_id=command_id,
        argv=[str(a) for a in argv],
        timeout_seconds=timeout,
        description=description,
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
            f"Unknown command_id: {command_id!r}. "
            f"Allowed built-ins: {allowed}"
        )
    return profile


# ---------------------------------------------------------------------------
# Execution
# ---------------------------------------------------------------------------

def run_command_profile(
    profile: CommandProfileSpec,
    cwd: Path,
) -> dict:
    """
    Execute *profile* in *cwd* with shell=False.
    Returns a structured result with stdout, stderr, exit_code, duration, and truncation flag.
    """
    started = time.monotonic()
    timed_out = False
    try:
        completed = subprocess.run(
            profile.argv,
            cwd=cwd,
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
        stdout = (exc.stdout or b"").decode("utf-8", errors="replace") if isinstance(exc.stdout, bytes) else (exc.stdout or "")
        stderr = (exc.stderr or b"").decode("utf-8", errors="replace") if isinstance(exc.stderr, bytes) else (exc.stderr or "")
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
        "argv": profile.argv,
        "exit_code": exit_code,
        "timed_out": timed_out,
        "duration_seconds": round(duration, 3),
        "stdout": stdout,
        "stderr": stderr,
        "output_truncated": output_truncated,
        "error": f"Timed out after {profile.timeout_seconds}s" if timed_out else (
            stderr.strip()[:300] if exit_code != 0 else ""
        ),
    }
