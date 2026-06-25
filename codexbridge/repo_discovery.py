from __future__ import annotations

import re
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


_REPO_NAME_SEPARATOR_RE = re.compile(r"[^a-z0-9]+")


@dataclass(frozen=True)
class DiscoveredRepo:
    repo_name: str
    folder_name: str
    path: Path


def canonical_repo_name(value: str) -> str:
    """Convert a folder or user-supplied name into a stable MCP repo_name."""
    return _REPO_NAME_SEPARATOR_RE.sub("_", value.strip().lower()).strip("_")


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
    excluded = {name.casefold() for name in exclude_names}
    discovered: dict[str, DiscoveredRepo] = {}

    for configured_root in roots:
        root = Path(configured_root).expanduser().resolve()
        if not root.exists() or not root.is_dir() or root.is_symlink():
            continue

        queue: deque[tuple[Path, int]] = deque([(root, 0)])
        while queue:
            parent, depth = queue.popleft()
            if depth >= max_depth:
                continue

            try:
                children = sorted(
                    (
                        child
                        for child in parent.iterdir()
                        if child.is_dir() and not child.is_symlink()
                    ),
                    key=lambda child: (child.name.casefold(), child.name),
                )
            except OSError:
                continue

            for child in children:
                if child.name.casefold() in excluded:
                    continue

                child_depth = depth + 1
                git_marker = child / ".git"
                is_git_repo = git_marker.exists()

                if is_git_repo or not require_git:
                    repo_name = canonical_repo_name(child.name)
                    if repo_name and repo_name not in discovered:
                        discovered[repo_name] = DiscoveredRepo(
                            repo_name=repo_name,
                            folder_name=child.name,
                            path=child.resolve(),
                        )

                # Do not scan inside an already discovered Git repository.
                if is_git_repo:
                    continue
                if child_depth < max_depth:
                    queue.append((child, child_depth))

    return discovered
