from __future__ import annotations

import re
from pathlib import Path, PureWindowsPath
from typing import Iterable


DESTRUCTIVE_PATTERNS = [
    re.compile(r"\bdocker\s+system\s+prune\b", re.IGNORECASE),
    re.compile(r"\bdocker\s+volume\s+rm\b", re.IGNORECASE),
    re.compile(r"\bdocker\s+compose\s+down\s+-v\b", re.IGNORECASE),
    re.compile(r"\bRemove-Item\b.*-Recurse\b.*-Force\b", re.IGNORECASE),
    re.compile(r"\brm\s+-rf\b", re.IGNORECASE),
    re.compile(r"\bdel\s+/s\b", re.IGNORECASE),
    re.compile(r"\brmdir\s+/s\b", re.IGNORECASE),
    re.compile(r"\bformat\b", re.IGNORECASE),
    re.compile(r"\bdiskpart\b", re.IGNORECASE),
]

SECRET_FILE_PATTERNS = [
    re.compile(r"(^|[\\/])\.env(\.|$|[\\/])?", re.IGNORECASE),
    re.compile(
        r"(secret|secrets|credential|credentials|token|apikey|api_key|private[_-]?key)",
        re.IGNORECASE,
    ),
    re.compile(r"\.(pem|key|p12|pfx)$", re.IGNORECASE),
]

SECRET_VALUE_PATTERNS = [
    re.compile(
        r"(?i)(api[_-]?key|token|secret|password|credential)\s*[:=]\s*['\"]?[^'\"\s]+"
    ),
    re.compile(r"(?i)(bearer)\s+[a-z0-9._\-]+"),
]


def reject_destructive_command(command: str) -> None:
    for pattern in DESTRUCTIVE_PATTERNS:
        if pattern.search(command):
            raise ValueError(f"Destructive command is not allowed: {command}")


def contains_wildcard(path: str) -> bool:
    return any(char in path for char in "*?[]")


def validate_repo_relative_path(repo_root: Path, relative_path: str) -> Path:
    if not relative_path or not relative_path.strip():
        raise ValueError("Path must not be empty")

    raw = relative_path.replace("\\", "/")
    win = PureWindowsPath(relative_path)
    if win.is_absolute() or win.drive or raw.startswith("//"):
        raise ValueError(
            f"Absolute, drive, and UNC paths are not allowed: {relative_path}"
        )
    if Path(relative_path).is_absolute():
        raise ValueError(f"Absolute paths are not allowed: {relative_path}")
    if contains_wildcard(relative_path):
        raise ValueError(f"Wildcard paths are not allowed: {relative_path}")

    parts = PureWindowsPath(relative_path).parts
    if any(part == ".." for part in parts):
        raise ValueError(f"Parent traversal is not allowed: {relative_path}")

    root = repo_root.resolve()
    candidate = (root / relative_path).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"Path escapes repo: {relative_path}") from exc
    return candidate


def validate_repo_relative_paths(repo_root: Path, paths: Iterable[str]) -> list[Path]:
    return [validate_repo_relative_path(repo_root, path) for path in paths]


def is_secret_like_file(path: str) -> bool:
    normalized = path.replace("\\", "/")
    return any(pattern.search(normalized) for pattern in SECRET_FILE_PATTERNS)


def reject_secret_like_file(path: str) -> None:
    if is_secret_like_file(path):
        raise ValueError(f"Secret-like files are not allowed for summarization: {path}")


def redact_secret_values(text: str) -> str:
    redacted = text
    for pattern in SECRET_VALUE_PATTERNS:
        redacted = pattern.sub(
            lambda match: (
                match.group(0).split(match.group(1), 1)[0]
                + match.group(1)
                + "=[REDACTED]"
            ),
            redacted,
        )
    return redacted
