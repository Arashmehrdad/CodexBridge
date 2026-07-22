from __future__ import annotations


def like_pattern(query: str) -> str:
    escaped = query.replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"
