"""One definition of the repository paths that tools own rather than the owner.

These paths hold scratch produced by test runs, benchmarks, and coding-agent
worktrees. They are not authored source, they are not repository knowledge, and
they must not be treated as owner work.

This lives in its own module because the definition was previously duplicated:
``git_tools`` classified tool-owned paths for commit manifests while
``repo_wiki`` kept a separate blocked-directory set for indexing. The two lists
drifted, so ``.codex-tmp/`` was correctly excluded from one and silently indexed
by the other — which is how 17,456 scratch files reached repository knowledge
and every managed-change result.

Both consumers now import from here so the classification cannot diverge again.
"""

from __future__ import annotations

from pathlib import Path

#: Repository-relative prefixes owned by tooling. Trailing slashes are
#: significant: a prefix matches the directory itself and anything beneath it,
#: never a sibling that merely shares a name prefix.
TOOL_OWNED_PREFIXES: tuple[str, ...] = (
    ".soma/",
    ".claude/worktrees/",
    ".codex-pytest-temp/",
    ".codex-tmp/",
    ".pytest_cache/",
    ".ruff_cache/",
    "_pytest-cf1-temp/",
    "tests/pytest_tmp_probe/",
)


def is_tool_owned_path(path: str | Path) -> bool:
    """Return whether a repository-relative path is tool-owned."""
    normalized = Path(str(path)).as_posix().strip("/")
    if not normalized:
        return False
    return any(
        normalized == prefix.rstrip("/") or normalized.startswith(prefix)
        for prefix in TOOL_OWNED_PREFIXES
    )
