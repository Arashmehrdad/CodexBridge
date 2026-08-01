from __future__ import annotations

import re
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Iterator


_REPO_NAME_SEPARATOR_RE = re.compile(r"[^a-z0-9]+")


@dataclass(frozen=True)
class DiscoveredRepo:
    repo_name: str
    folder_name: str
    path: Path


def canonical_repo_name(value: str) -> str:
    """Convert a folder or user-supplied name into a stable MCP repo_name."""
    return _REPO_NAME_SEPARATOR_RE.sub("_", value.strip().lower()).strip("_")


def _separator_insensitive_repo_name(value: str) -> str:
    """Normalize aliases while preserving the established canonical identity."""
    return _REPO_NAME_SEPARATOR_RE.sub("", value.strip().lower())


def iter_discovered_repositories(
    *,
    roots: Iterable[Path],
    max_depth: int = 1,
    require_git: bool = True,
    exclude_names: Iterable[str] = (),
) -> Iterator[DiscoveredRepo]:
    """Yield eligible repositories beneath trusted roots in deterministic order."""
    excluded = {name.casefold() for name in exclude_names}

    for configured_root in roots:
        try:
            root = Path(configured_root).expanduser().resolve()
        except OSError:
            continue
        if not root.exists() or not root.is_dir() or root.is_symlink():
            continue

        queue: deque[tuple[Path, int]] = deque([(root, 0)])
        while queue:
            parent, depth = queue.popleft()
            if depth >= max_depth:
                continue

            try:
                children = sorted(
                    parent.iterdir(),
                    key=lambda child: (child.name.casefold(), child.name),
                )
            except OSError:
                continue

            for child in children:
                if child.name.casefold() in excluded:
                    continue
                try:
                    if child.is_symlink() or not child.is_dir():
                        continue
                except OSError:
                    continue

                child_depth = depth + 1
                git_marker = child / ".git"
                try:
                    is_git_repo = git_marker.exists()
                except OSError:
                    is_git_repo = False

                if is_git_repo or not require_git:
                    repo_name = canonical_repo_name(child.name)
                    if repo_name:
                        yield DiscoveredRepo(
                            repo_name=repo_name,
                            folder_name=child.name,
                            path=child.resolve(),
                        )

                # Do not scan inside an already discovered Git repository.
                if is_git_repo:
                    continue
                if child_depth < max_depth:
                    queue.append((child, child_depth))


def discover_repository(
    *,
    roots: Iterable[Path],
    requested_name: str,
    max_depth: int = 1,
    require_git: bool = True,
    exclude_names: Iterable[str] = (),
) -> DiscoveredRepo | None:
    """Resolve one unambiguous trusted repository, preferring exact names."""
    requested_folder = requested_name.strip().casefold()
    requested_canonical = canonical_repo_name(requested_name)
    requested_separator_insensitive = _separator_insensitive_repo_name(requested_name)
    repositories = list(
        iter_discovered_repositories(
            roots=roots,
            max_depth=max_depth,
            require_git=require_git,
            exclude_names=exclude_names,
        )
    )

    def unique_match(
        matches: list[DiscoveredRepo], match_kind: str
    ) -> DiscoveredRepo | None:
        if not matches:
            return None
        if len(matches) == 1:
            return matches[0]
        candidates = ", ".join(
            repr(repository.folder_name)
            for repository in sorted(
                matches,
                key=lambda repository: (
                    repository.folder_name.casefold(),
                    repository.folder_name,
                ),
            )
        )
        raise ValueError(
            f"Ambiguous repo_name {requested_name!r}: {match_kind} matches "
            f"multiple trusted repositories: {candidates}. Use an exact folder name."
        )

    exact_match = unique_match(
        [
            repository
            for repository in repositories
            if repository.folder_name.casefold() == requested_folder
        ],
        "exact folder name",
    )
    if exact_match is not None:
        return exact_match

    canonical_match = unique_match(
        [
            repository
            for repository in repositories
            if repository.repo_name == requested_canonical
        ],
        "canonical alias",
    )
    if canonical_match is not None:
        return canonical_match

    return unique_match(
        [
            repository
            for repository in repositories
            if _separator_insensitive_repo_name(repository.folder_name)
            == requested_separator_insensitive
        ],
        "separator-insensitive alias",
    )


def discover_repositories(
    *,
    roots: Iterable[Path],
    max_depth: int = 1,
    require_git: bool = True,
    exclude_names: Iterable[str] = (),
) -> dict[str, DiscoveredRepo]:
    """
    Discover repository directories beneath approved roots.

    Discovery is deterministic, skips symlinks, stops descending once a Git
    repository is found, and keeps the first repository when normalized names
    collide.
    """
    discovered: dict[str, DiscoveredRepo] = {}
    for repository in iter_discovered_repositories(
        roots=roots,
        max_depth=max_depth,
        require_git=require_git,
        exclude_names=exclude_names,
    ):
        discovered.setdefault(repository.repo_name, repository)
    return discovered


def diagnose_repository_miss(
    *,
    roots: Iterable[Path],
    requested_name: str,
    max_depth: int = 1,
    exclude_names: Iterable[str] = (),
) -> str:
    """Explain why a matching trusted-root path was not eligible for discovery."""
    requested_folder = requested_name.strip().casefold()
    requested_canonical = canonical_repo_name(requested_name)
    requested_separator_insensitive = _separator_insensitive_repo_name(requested_name)
    excluded = {name.casefold() for name in exclude_names}

    for configured_root in roots:
        try:
            root = Path(configured_root).expanduser().resolve()
        except OSError:
            continue
        if not root.exists() or not root.is_dir() or root.is_symlink():
            continue

        queue: deque[tuple[Path, int]] = deque([(root, 0)])
        while queue:
            parent, depth = queue.popleft()
            if depth >= max_depth:
                continue
            try:
                children = sorted(
                    parent.iterdir(),
                    key=lambda child: (child.name.casefold(), child.name),
                )
            except OSError:
                continue

            for child in children:
                name_matches = (
                    child.name.casefold() == requested_folder
                    or canonical_repo_name(child.name) == requested_canonical
                    or _separator_insensitive_repo_name(child.name)
                    == requested_separator_insensitive
                )
                if child.name.casefold() in excluded:
                    if name_matches:
                        return (
                            f"matching folder {child.name!r} is excluded from discovery"
                        )
                    continue
                try:
                    if child.is_symlink():
                        if name_matches:
                            return f"matching folder {child.name!r} is a symlink"
                        continue
                    is_directory = child.is_dir()
                except OSError:
                    if name_matches:
                        return f"matching path {child.name!r} could not be inspected"
                    continue
                if not is_directory:
                    if name_matches:
                        return f"matching path {child.name!r} is not a directory"
                    continue

                child_depth = depth + 1
                try:
                    has_git_marker = (child / ".git").exists()
                except OSError:
                    has_git_marker = False
                if name_matches:
                    if not has_git_marker:
                        return (
                            f"matching folder {child.name!r} is not a Git repository root "
                            "because .git is missing"
                        )
                    return (
                        f"matching Git repository {child.name!r} was found but could not "
                        "be resolved"
                    )
                if has_git_marker:
                    continue
                if child_depth < max_depth:
                    queue.append((child, child_depth))

    return ""
