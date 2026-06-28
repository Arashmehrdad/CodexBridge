from __future__ import annotations

import os
from pathlib import Path

from . import config as config_module
from .repo_discovery import canonical_repo_name, discover_repositories


_ORIGINAL_RESOLVE_REPO = config_module.resolve_repo
_INSTALLED = False
_TRUTHY = {"1", "true", "yes", "on"}
_FALSEY = {"0", "false", "no", "off"}
_DEFAULT_EXCLUDES = (".fallow", "secrets")


def _discovery_enabled() -> bool:
    raw = os.getenv("CODEXBRIDGE_AUTO_DISCOVER_REPOS", "1").strip().lower()
    if raw in _FALSEY:
        return False
    return raw in _TRUTHY or raw == ""


def _configured_roots(config: config_module.AppConfig) -> list[Path]:
    roots: list[Path] = []
    raw_roots = os.getenv("CODEXBRIDGE_REPO_ROOTS", "")
    for item in raw_roots.replace("\n", ";").split(";"):
        item = item.strip()
        if item:
            roots.append(Path(item).expanduser().resolve())

    # Existing explicit repositories define trusted parent directories. This
    # makes D:/Github automatic when at least one configured repo lives there.
    for repo in config.repos.values():
        roots.append(Path(repo.path).expanduser().resolve().parent)

    deduplicated: list[Path] = []
    seen: set[str] = set()
    for root in roots:
        key = str(root).casefold()
        if key not in seen:
            seen.add(key)
            deduplicated.append(root)
    return deduplicated


def _excluded_names() -> tuple[str, ...]:
    raw = os.getenv("CODEXBRIDGE_REPO_EXCLUDES", "")
    if not raw.strip():
        return _DEFAULT_EXCLUDES
    return tuple(item.strip() for item in raw.split(",") if item.strip())


def _max_depth() -> int:
    raw = os.getenv("CODEXBRIDGE_REPO_MAX_DEPTH", "1").strip()
    try:
        value = int(raw)
    except ValueError:
        return 1
    return min(max(value, 1), 8)


def resolve_repo_with_discovery(
    config: config_module.AppConfig, repo_name: str
) -> Path:
    """Resolve explicit repositories first, then rescan trusted parent roots."""
    try:
        return _ORIGINAL_RESOLVE_REPO(config, repo_name)
    except ValueError as original_error:
        if not str(original_error).startswith("Unknown repo_name:"):
            raise
        if not _discovery_enabled():
            raise

    discovered = discover_repositories(
        roots=_configured_roots(config),
        max_depth=_max_depth(),
        require_git=True,
        exclude_names=_excluded_names(),
    )
    canonical_name = canonical_repo_name(repo_name)
    match = discovered.get(repo_name) or discovered.get(canonical_name)
    if match is None:
        raise ValueError(f"Unknown repo_name: {repo_name}")

    config.repos[match.repo_name] = config_module.RepoConfig(path=str(match.path))
    return _ORIGINAL_RESOLVE_REPO(config, match.repo_name)


def install_repo_discovery() -> None:
    """Install automatic discovery without changing the public config API."""
    global _INSTALLED
    if _INSTALLED:
        return
    config_module.resolve_repo = resolve_repo_with_discovery
    _INSTALLED = True
