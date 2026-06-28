from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .safety import redact_secret_values


MAX_TEXT_LENGTH = 20000


def truncate_text(text: str, limit: int = MAX_TEXT_LENGTH) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n[truncated {len(text) - limit} characters]"


def redact_and_truncate(value: Any, limit: int = MAX_TEXT_LENGTH) -> Any:
    if isinstance(value, str):
        return truncate_text(redact_secret_values(value), limit)
    if isinstance(value, list):
        return [redact_and_truncate(item, limit) for item in value]
    if isinstance(value, dict):
        return {
            str(key): redact_and_truncate(item, limit) for key, item in value.items()
        }
    return value


def append_jsonl(path: Path, event: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    safe_event = redact_and_truncate(event)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(safe_event, sort_keys=True) + "\n")


def read_jsonl(path: Path, limit: int = 50) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8").splitlines()
    selected = lines[-max(1, min(limit, 500)) :]
    return [json.loads(line) for line in selected if line.strip()]


class ArtifactWriter:
    def __init__(self, run_dir: Path):
        self.run_dir = run_dir
        self.run_dir.mkdir(parents=True, exist_ok=True)

    def write_json(self, name: str, data: dict[str, Any]) -> None:
        (self.run_dir / name).write_text(
            json.dumps(redact_and_truncate(data), indent=2), encoding="utf-8"
        )

    def write_text(self, name: str, text: str) -> None:
        (self.run_dir / name).write_text(redact_and_truncate(text), encoding="utf-8")

    def append_event(self, event: dict[str, Any]) -> None:
        append_jsonl(self.run_dir / "events.jsonl", event)
