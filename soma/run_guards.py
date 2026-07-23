from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
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
_COMPLETED_REQUIREMENT_RE = re.compile(r"(?im)^COMPLETED_REQUIREMENT:\s*(.+?)\s*$")
_SKIPPED_REQUIREMENT_RE = re.compile(r"(?im)^SKIPPED_REQUIREMENT:\s*(.+?)\s*$")
_VALIDATION_STATUS_RE = re.compile(
    r"(?im)^VALIDATION_STATUS:\s*(passed|failed|not_run|not_required)\s*$"
)
_FAILED_REQUIREMENT_RE = re.compile(r"(?im)^FAILED_REQUIREMENT:\s*(.+?)\s*$")
_REQUIREMENT_ID_RE = re.compile(r"\bREQ-\d{3}\b")
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
    completed_requirements: list[str] = field(default_factory=list)
    skipped_requirements: list[str] = field(default_factory=list)
    failed_requirements: list[str] = field(default_factory=list)
    missing_requirements: list[str] = field(default_factory=list)
    mandatory_incomplete: list[str] = field(default_factory=list)
    validation_status: str | None = None


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
    """Capture persistent files while pruning ignored trees before traversal."""
    root = repo_root.resolve()
    ignored: set[Path] = set()
    for candidate in ignored_roots:
        resolved = candidate.resolve()
        try:
            resolved.relative_to(root)
        except ValueError:
            continue
        ignored.add(resolved)

    snapshot: WorkspaceSnapshot = {}
    for current_dir, directory_names, file_names in os.walk(root, topdown=True):
        current = Path(current_dir).resolve()
        if current in ignored:
            directory_names[:] = []
            continue

        kept_directories: list[str] = []
        for name in directory_names:
            child = (current / name).resolve()
            if name.lower() in _IGNORED_WORKSPACE_PARTS:
                continue
            if any(
                child == ignored_root or ignored_root in child.parents
                for ignored_root in ignored
            ):
                continue
            kept_directories.append(name)
        directory_names[:] = kept_directories

        for name in file_names:
            path = current / name
            try:
                relative = path.relative_to(root)
                stat = path.stat()
            except (OSError, ValueError):
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
        blockers.append("External coder reported PLAN_STATUS: blocked")
    if not statuses:
        for pattern in _PLAN_PLACEHOLDER_PATTERNS:
            if pattern.search(text):
                blockers.append("External coder returned a placeholder instead of a plan")
                break
    if not text.strip():
        blockers.append("External coder returned an empty plan")
    return ImplementationOutcome(
        blocked=bool(blockers), blockers=blockers, plan_conformance=None
    )


def assess_implementation_output(summary: str) -> ImplementationOutcome:
    """Classify blocker, conformance, requirement, and validation signals."""
    return assess_implementation_output_against(summary, ())


def assess_implementation_output_against(
    summary: str, required_requirement_ids: Iterable[str]
) -> ImplementationOutcome:
    """Classify blocker, conformance, requirement, and validation signals."""
    text = summary or ""
    explicit_statuses = _EXPLICIT_STATUS_RE.findall(text)
    conformance_matches = _PLAN_CONFORMANCE_RE.findall(text)
    plan_conformance = None
    if conformance_matches:
        plan_conformance = conformance_matches[-1].lower() == "yes"
    completed_requirements = [
        item.strip() for item in _COMPLETED_REQUIREMENT_RE.findall(text)
    ]
    skipped_requirements = [
        item.strip() for item in _SKIPPED_REQUIREMENT_RE.findall(text)
    ]
    failed_requirements = [
        item.strip() for item in _FAILED_REQUIREMENT_RE.findall(text)
    ]
    validation_matches = _VALIDATION_STATUS_RE.findall(text)
    validation_status = validation_matches[-1].lower() if validation_matches else None

    completed_ids = _extract_requirement_ids(completed_requirements)
    skipped_ids = _extract_requirement_ids(skipped_requirements)
    failed_ids = _extract_requirement_ids(failed_requirements)
    required_ids = _stable_requirement_ids(required_requirement_ids)
    resolved_ids = completed_ids | skipped_ids | failed_ids
    missing_requirements = [
        req_id for req_id in required_ids if req_id not in resolved_ids
    ]
    mandatory_incomplete = _stable_requirement_ids(
        [*skipped_ids, *failed_ids, *missing_requirements]
    )

    blockers: list[str] = []
    if explicit_statuses and explicit_statuses[-1].lower() in {"blocked", "failed"}:
        blockers.append(f"External coder reported FINAL_STATUS: {explicit_statuses[-1].lower()}")
    if validation_status == "failed":
        blockers.append("External coder reported VALIDATION_STATUS: failed")

    if not explicit_statuses:
        for pattern in _BLOCKER_PATTERNS:
            if pattern.search(text):
                blockers.append(
                    "External coder response reports an implementation blocker"
                )
                break

    return ImplementationOutcome(
        blocked=bool(blockers),
        blockers=blockers,
        plan_conformance=plan_conformance,
        completed_requirements=completed_requirements,
        skipped_requirements=skipped_requirements,
        failed_requirements=failed_requirements,
        missing_requirements=missing_requirements,
        mandatory_incomplete=mandatory_incomplete,
        validation_status=validation_status,
    )


def derive_requirement_manifest(approved_plan: str) -> list[dict[str, object]]:
    manifest: list[dict[str, object]] = []
    seen: set[str] = set()
    for raw_line in approved_plan.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        match = _REQUIREMENT_ID_RE.search(line)
        if not match:
            continue
        requirement_id = match.group(0)
        if requirement_id in seen:
            continue
        seen.add(requirement_id)
        manifest.append(
            {
                "requirement_id": requirement_id,
                "text": line,
                "mandatory": True,
            }
        )
    return manifest


def _extract_requirement_ids(items: Iterable[str]) -> set[str]:
    found: set[str] = set()
    for item in items:
        for match in _REQUIREMENT_ID_RE.findall(item):
            found.add(match)
    return found


def _stable_requirement_ids(items: Iterable[str]) -> list[str]:
    return sorted({item for item in items if item})
