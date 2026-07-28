from __future__ import annotations

import hashlib
import os
import re
import tempfile
import unicodedata
from pathlib import Path, PurePosixPath
from typing import Any

import yaml

from .models import KnowledgeRecord

_FRONTMATTER = re.compile(r"\A---\r?\n(.*?)\r?\n---\r?\n?", re.DOTALL)


def normalize_text(value: str) -> str:
    value = unicodedata.normalize("NFKC", value).replace("ي", "ی").replace("ك", "ک")
    return " ".join(value.casefold().split())


def validate_project_id(project_id: str) -> str:
    if (
        not project_id
        or len(project_id) > 128
        or "\x00" in project_id
        or "/" in project_id
        or "\\" in project_id
    ):
        raise ValueError("project_id must be a non-empty opaque identifier")
    return project_id


class MarkdownVault:
    def __init__(self, root: Path):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def resolve_path(self, relative: str) -> Path:
        pure = PurePosixPath(relative.replace("\\", "/"))
        if (
            pure.is_absolute()
            or not pure.parts
            or ".." in pure.parts
            or pure.suffix.casefold() != ".md"
        ):
            raise ValueError("vault_path must be a contained relative Markdown path")
        target = (self.root / Path(*pure.parts)).resolve()
        try:
            target.relative_to(self.root)
        except ValueError as exc:
            raise ValueError("vault_path escapes the knowledge vault") from exc
        return target

    def write(self, record: KnowledgeRecord) -> Path:
        path = self.resolve_path(record.vault_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        metadata = record.model_dump(mode="json", exclude={"body"})
        payload = (
            "---\n"
            + yaml.safe_dump(
                metadata, allow_unicode=True, sort_keys=True, default_flow_style=False
            )
            + "---\n"
            + record.body
        )
        if record.body and not payload.endswith("\n"):
            payload += "\n"
        descriptor, temp_name = tempfile.mkstemp(
            dir=path.parent, prefix=f".{path.name}.", suffix=".tmp"
        )
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_name, path)
        finally:
            Path(temp_name).unlink(missing_ok=True)
        return path

    def read(self, path: Path) -> KnowledgeRecord:
        resolved = path.resolve()
        try:
            relative = resolved.relative_to(self.root).as_posix()
        except ValueError as exc:
            raise ValueError("knowledge note is outside the vault") from exc
        text = resolved.read_text(encoding="utf-8")
        match = _FRONTMATTER.match(text)
        if match is None:
            raise ValueError("knowledge note has no valid YAML frontmatter")
        try:
            metadata: Any = yaml.safe_load(match.group(1))
        except yaml.YAMLError as exc:
            raise ValueError("knowledge note has invalid YAML frontmatter") from exc
        if not isinstance(metadata, dict):
            raise ValueError("knowledge note frontmatter must be a mapping")
        metadata["vault_path"] = relative
        metadata["body"] = text[match.end() :].rstrip("\n")
        validate_project_id(str(metadata.get("project_id") or ""))
        record = KnowledgeRecord.model_validate(metadata)
        record.content_sha256 = content_hash(record)
        return record

    def markdown_files(self) -> list[Path]:
        return sorted(path for path in self.root.rglob("*.md") if path.is_file())


def content_hash(record: KnowledgeRecord) -> str:
    payload = "\n".join(
        (
            record.project_id,
            record.kind,
            record.title,
            record.summary,
            record.body,
        )
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
