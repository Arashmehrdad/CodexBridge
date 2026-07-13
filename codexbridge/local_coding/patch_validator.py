from __future__ import annotations

from pathlib import Path
from fnmatch import fnmatch

from codexbridge.config import LocalCodingConfig

from .classifier import SOURCE_EXTENSIONS
from .models import LocalPatchValidationResult
from .redaction import detect_sensitivity


def validate_patch(
    *,
    repo_path: Path,
    target_file: Path,
    original: str,
    updated: str,
    diff: str,
    config: LocalCodingConfig | None = None,
) -> LocalPatchValidationResult:
    settings = config or LocalCodingConfig()
    blocked: list[str] = []
    repo = Path(repo_path).resolve()
    target = (
        (repo / target_file).resolve()
        if not Path(target_file).is_absolute()
        else Path(target_file).resolve()
    )
    try:
        target.relative_to(repo)
    except ValueError:
        blocked.append("path_outside_repo")
    relative = (
        target.relative_to(repo).as_posix()
        if not blocked
        else Path(target_file).as_posix()
    )
    if ".." in Path(target_file).parts:
        blocked.append("path_traversal_blocked")
    if target.exists() and target.is_symlink():
        try:
            target.resolve().relative_to(repo)
        except ValueError:
            blocked.append("symlink_outside_repo_blocked")
    if not target.exists():
        blocked.append("target_file_missing")
    elif not target.is_file():
        blocked.append("target_not_file")
    elif target.stat().st_size > settings.local_coding_max_file_bytes:
        blocked.append("file_too_large")
    if settings.local_coding_allowed_path_globs and not _path_allowed(
        relative, settings.local_coding_allowed_path_globs
    ):
        blocked.append("path_not_allowlisted")
    if (
        settings.local_coding_allowed_extensions
        and target.suffix.lower() not in settings.local_coding_allowed_extensions
    ):
        blocked.append("extension_not_allowlisted")
    if (
        settings.local_coding_block_source_code
        and target.suffix.lower() in SOURCE_EXTENSIONS
    ):
        blocked.append("source_code_blocked")
    if settings.local_coding_block_tests and _looks_like_test_path(relative):
        blocked.append("test_file_blocked")
    if "\x00" in original:
        blocked.append("binary_file_blocked")
    changed_bytes = abs(
        len(updated.encode("utf-8")) - len(original.encode("utf-8"))
    ) + len(diff.encode("utf-8"))
    changed_lines = sum(
        1
        for line in diff.splitlines()
        if line.startswith(("+", "-")) and not line.startswith(("+++", "---"))
    )
    if changed_bytes > settings.local_coding_max_patch_bytes:
        blocked.append("patch_too_large")
    if changed_lines > settings.local_coding_max_changed_lines:
        blocked.append("too_many_changed_lines")
    sensitivity = detect_sensitivity(updated)
    if sensitivity and settings.local_coding_block_sensitive:
        blocked.append("secret_like_content")
    return LocalPatchValidationResult(
        valid=not blocked,
        blocked_reasons=sorted(set(blocked)),
        changed_lines=changed_lines,
        changed_bytes=changed_bytes,
        sensitivity_flags=sensitivity,
    )


def _path_allowed(relative: str, globs: list[str]) -> bool:
    return any(
        fnmatch(relative, pattern)
        or Path(relative).match(pattern)
        or _double_star_one_level(relative, pattern)
        for pattern in globs
    )


def _double_star_one_level(relative: str, pattern: str) -> bool:
    if "/**/" not in pattern:
        return False
    return fnmatch(relative, pattern.replace("**/", ""))


def _looks_like_test_path(relative: str) -> bool:
    path = Path(relative)
    parts = [part.lower() for part in path.parts]
    name = path.name.lower()
    return "tests" in parts or name.startswith("test_") or name.endswith("_test.py")
