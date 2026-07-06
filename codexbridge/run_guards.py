from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from .safety import validate_repo_relative_paths

_IGNORED_WORKSPACE_PARTS = frozenset(
    {
        ".git",
        ".mypy_cache",
        ".pytest_cache",
        ".pytest_tmp",
        ".ruff_cache",
        ".tox",
        ".venv",
        "__pycache__",
        "node_modules",
        "venv",
    }
)

_EXPLICIT_STATUS_RE = re.compile(
    r"(?im)^FINAL_STATUS:\s*(completed|blocked|failed)\s*$"
)
_PLAN_CONFORMANCE_RE = re.compile(r"(?im)^PLAN_CONFORMANCE:\s*(yes|no)\s*$")
_PLAN_STATUS_RE = re.compile(r"(?im)^PLAN_STATUS:\s*(ready|blocked)\s*$")
_PLAN_PLACEHOLDER_PATTERNS = (
    re.compile(r"\bsend\s+(?:me\s+)?the\s+actual\s+task\b", re.IGNORECASE),
    re.compile(r"\bprovide\s+(?:me\s+)?the\s+(?:actual\s+)?task\b", re.IGNORECASE),
)
_BLOCKER_PATTERNS = (
    re.compile(r"\bcould(?:\s+not|n't)\s+complete\b", re.IGNORECASE),
    re.compile(
        r"\bimplementation\s+(?:could(?:\s+not|n't)|was\s+not)\s+completed?\b",
        re.IGNORECASE,
    ),
    re.compile(r"\bwrite[- ]blocked\b", re.IGNORECASE),
    re.compile(r"\baccess\s+(?:to\s+the\s+path\s+.+?\s+)?is\s+denied\b", re.IGNORECASE),
    re.compile(r"\bpermission\s+denied\b", re.IGNORECASE),
    re.compile(r"\bfailed\s+to\s+(?:write|create|edit|apply)\b", re.IGNORECASE),
    re.compile(
        r"\bno\s+(?:repository\s+)?edit\s+(?:was|could\s+be)\s+applied\b", re.IGNORECASE
    ),
)


@dataclass(frozen=True)
class ImplementationOutcome:
    blocked: bool
    blockers: list[str]
    plan_conformance: bool | None


WorkspaceSnapshot = dict[str, tuple[int, int]]


def allowed_write_directories(
    repo_root: Path, allowed_files: Iterable[str]
) -> list[Path]:
    """Return unique non-root parent directories for the exact write allowlist."""
    root = repo_root.resolve()
    targets = validate_repo_relative_paths(root, allowed_files)
    directories: list[Path] = []
    seen: set[Path] = set()
    for target in targets:
        parent = target.parent
        while parent != root and not parent.exists():
            parent = parent.parent
        if parent == root or parent in seen:
            continue
        seen.add(parent)
        directories.append(parent)
    return directories


def snapshot_workspace(
    repo_root: Path, ignored_roots: Iterable[Path] = ()
) -> WorkspaceSnapshot:
    """Capture persistent files outside known caches and bridge artifact roots."""
    root = repo_root.resolve()
    ignored: list[Path] = []
    for candidate in ignored_roots:
        resolved = candidate.resolve()
        try:
            resolved.relative_to(root)
        except ValueError:
            continue
        ignored.append(resolved)
    snapshot: WorkspaceSnapshot = {}
    for path in root.rglob("*"):
        try:
            relative = path.relative_to(root)
        except ValueError:
            continue
        if any(
            path == ignored_root or ignored_root in path.parents
            for ignored_root in ignored
        ):
            continue
        if any(part.lower() in _IGNORED_WORKSPACE_PARTS for part in relative.parts):
            continue
        try:
            if not path.is_file():
                continue
            stat = path.stat()
        except OSError:
            continue
        snapshot[relative.as_posix()] = (stat.st_size, stat.st_mtime_ns)
    return snapshot


def changed_workspace_paths(
    before: WorkspaceSnapshot, after: WorkspaceSnapshot
) -> list[str]:
    return sorted(
        path
        for path in before.keys() | after.keys()
        if before.get(path) != after.get(path)
    )


def out_of_scope_workspace_changes(
    before: WorkspaceSnapshot,
    after: WorkspaceSnapshot,
    allowed_files: Iterable[str],
) -> list[str]:
    allowed = {Path(path).as_posix() for path in allowed_files}
    return [
        path
        for path in changed_workspace_paths(before, after)
        if path not in allowed and not _is_allowed_temporary_sibling(path, allowed)
    ]


def classify_git_attribution(
    changed_after: Iterable[str],
    workspace_before: WorkspaceSnapshot,
    workspace_after: WorkspaceSnapshot,
    dirty_before: Iterable[str],
) -> tuple[list[str], list[str]]:
    changed_set = {Path(path).as_posix() for path in changed_after}
    dirty_before_set = {Path(path).as_posix() for path in dirty_before}
    workspace_delta = set(changed_workspace_paths(workspace_before, workspace_after))
    introduced = sorted(path for path in workspace_delta if path in changed_set)
    preserved = sorted(
        path
        for path in dirty_before_set
        if path in changed_set and path not in introduced
    )
    return introduced, preserved


def _is_allowed_temporary_sibling(path: str, allowed: set[str]) -> bool:
    candidate = Path(path)
    if candidate.suffix.lower() != ".tmp":
        return False
    name = candidate.name
    for allowed_path in allowed:
        allowed_name = Path(allowed_path).name
        if name.startswith(f".{allowed_name}.") or name == f".{allowed_name}.tmp":
            if candidate.parent.as_posix() == Path(allowed_path).parent.as_posix():
                return True
    return False


def assess_plan_output(summary: str) -> ImplementationOutcome:
    """Reject placeholder or explicitly blocked plan responses."""
    text = summary or ""
    statuses = _PLAN_STATUS_RE.findall(text)
    blockers: list[str] = []
    if statuses and statuses[-1].lower() == "blocked":
        blockers.append("Codex reported PLAN_STATUS: blocked")
    if not statuses:
        for pattern in _PLAN_PLACEHOLDER_PATTERNS:
            if pattern.search(text):
                blockers.append("Codex returned a placeholder instead of a plan")
                break
    if not text.strip():
        blockers.append("Codex returned an empty plan")
    return ImplementationOutcome(
        blocked=bool(blockers), blockers=blockers, plan_conformance=None
    )


def assess_implementation_output(summary: str) -> ImplementationOutcome:
    """Classify explicit/fallback blocker signals from Codex's final response."""
    explicit_statuses = _EXPLICIT_STATUS_RE.findall(summary or "")
    conformance_matches = _PLAN_CONFORMANCE_RE.findall(summary or "")
    plan_conformance = None
    if conformance_matches:
        plan_conformance = conformance_matches[-1].lower() == "yes"

    blockers: list[str] = []
    if explicit_statuses and explicit_statuses[-1].lower() in {"blocked", "failed"}:
        blockers.append(f"Codex reported FINAL_STATUS: {explicit_statuses[-1].lower()}")
    if plan_conformance is False:
        blockers.append("Codex reported PLAN_CONFORMANCE: no")

    if not explicit_statuses:
        for pattern in _BLOCKER_PATTERNS:
            if pattern.search(summary or ""):
                blockers.append(
                    "Codex final response reports an implementation blocker"
                )
                break

    return ImplementationOutcome(
        blocked=bool(blockers),
        blockers=blockers,
        plan_conformance=plan_conformance,
    )
