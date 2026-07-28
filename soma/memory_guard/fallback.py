"""Bounded direct Markdown access, used only when semantic health is unavailable.

Deliberately primitive. This is a literal substring reader over canonical files,
not a retrieval engine: no scoring model, no ranking heuristics, no embeddings,
no index. Results are returned in stable path order so nothing here can be
mistaken for relevance ordering.
"""

from __future__ import annotations

from pathlib import Path

from .health import os_manifest
from .models import PathRefused, RefusalReason


#: Hard caps so the fallback can never become an expensive search path.
MAX_FILES_SCANNED: int = 2000
MAX_FILE_BYTES: int = 512_000
MAX_RESULTS: int = 50


def resolve_within_root(root: str | Path, candidate: str | Path) -> Path:
    """Return the absolute path, or refuse if it escapes the bound root."""
    base = Path(root).expanduser().resolve()
    target = Path(candidate)
    resolved = (base / target if not target.is_absolute() else target).resolve()
    try:
        resolved.relative_to(base)
    except ValueError:
        raise PathRefused(
            f"path {str(candidate)!r} resolves outside the bound canonical root "
            f"({RefusalReason.PATH_OUTSIDE_ROOT.value})"
        ) from None
    return resolved


def literal_search(
    root: str | Path,
    query: str,
    *,
    max_results: int = MAX_RESULTS,
    case_sensitive: bool = False,
) -> list[dict[str, object]]:
    """Plain substring match over canonical Markdown, in stable path order."""
    if not query or not query.strip():
        return []
    needle = query if case_sensitive else query.casefold()
    base = Path(root).expanduser().resolve()
    results: list[dict[str, object]] = []

    for index, relative in enumerate(os_manifest(base)):
        if index >= MAX_FILES_SCANNED:
            break
        path = base / relative
        try:
            if path.stat().st_size > MAX_FILE_BYTES:
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        haystack = text if case_sensitive else text.casefold()
        if needle not in haystack:
            continue
        line_number = 0
        excerpt = ""
        for number, line in enumerate(text.splitlines(), start=1):
            probe = line if case_sensitive else line.casefold()
            if needle in probe:
                line_number = number
                excerpt = line.strip()[:300]
                break
        results.append(
            {
                "file_path": relative,
                "line": line_number,
                "excerpt": excerpt,
                "source": "canonical_markdown_fallback",
            }
        )
        if len(results) >= max_results:
            break
    return results


def read_note(root: str | Path, relative_path: str) -> dict[str, object]:
    """Read one canonical file, refusing any path outside the bound root."""
    resolved = resolve_within_root(root, relative_path)
    if not resolved.is_file():
        raise PathRefused(f"no canonical file at {relative_path!r}")
    text = resolved.read_text(encoding="utf-8", errors="replace")
    base = Path(root).expanduser().resolve()
    return {
        "file_path": resolved.relative_to(base).as_posix(),
        "content": text,
        "bytes": len(text.encode("utf-8")),
        "source": "canonical_markdown_fallback",
    }
