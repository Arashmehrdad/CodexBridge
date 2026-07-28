from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
import unicodedata
from pathlib import Path, PurePosixPath
from typing import Any

import yaml

from .models import KnowledgeRecord

_FRONTMATTER = re.compile(r"\A---\r?\n(.*?)\r?\n---\r?\n?", re.DOTALL)


class UnadoptedNote(Exception):
    """A Markdown file in the vault that Soma does not own.

    Deliberately not a `ValueError`: an owner's hand-written Obsidian note is
    preserved and reported, never counted as a malformed Soma record and never
    silently dropped.
    """


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
        """Read a Soma-owned canonical record, or raise.

        Raises `UnadoptedNote` when the file is not Soma-owned at all, and
        `ValueError` only when a file that *claims* to be Soma-owned cannot be
        parsed. Callers must keep those apart: the first is the owner writing in
        their own workspace, the second is corruption.
        """
        resolved = path.resolve()
        try:
            relative = resolved.relative_to(self.root).as_posix()
        except ValueError as exc:
            raise ValueError("knowledge note is outside the vault") from exc
        text = resolved.read_text(encoding="utf-8")
        match = _FRONTMATTER.match(text)
        if match is None:
            raise UnadoptedNote(
                f"{relative} has no YAML frontmatter, so it is an owner-authored "
                "note Soma does not manage"
            )
        try:
            metadata: Any = yaml.safe_load(match.group(1))
        except yaml.YAMLError as exc:
            raise ValueError("knowledge note has invalid YAML frontmatter") from exc
        if not isinstance(metadata, dict):
            raise ValueError("knowledge note frontmatter must be a mapping")
        # A note with frontmatter but no Soma identity is the owner's own file
        # -- an Obsidian template, a daily note, anything. Soma preserves it and
        # keeps it out of authoritative context; it is not corruption.
        if not metadata.get("knowledge_id") or not metadata.get("project_id"):
            raise UnadoptedNote(
                f"{relative} carries no Soma record identity, so it is an "
                "owner-authored note Soma does not manage"
            )
        metadata["vault_path"] = relative
        metadata["body"] = text[match.end() :].rstrip("\n")
        validate_project_id(str(metadata.get("project_id") or ""))
        record = KnowledgeRecord.model_validate(metadata)
        record.content_sha256 = content_hash(record)
        return record

    def markdown_files(self) -> list[Path]:
        return sorted(path for path in self.root.rglob("*.md") if path.is_file())


#: Domain separator so a body can never be crafted to collide with a field list.
_INTEGRITY_DOMAIN = "soma.knowledge.integrity.v2"


def content_hash(record: KnowledgeRecord) -> str:
    """Integrity hash over every authoritative field, not just the content.

    The v1 hash covered `project_id`, `kind`, `title`, `summary` and `body`
    only. Lifecycle and provenance were therefore unprotected: editing `status`,
    `supersedes_ids` or `sources` in a canonical file left the hash unchanged,
    so a rebuild adopted the altered lifecycle with no drift signal at all.

    Scope, lifecycle, temporal validity, supersession links and provenance are
    authoritative, so they are hashed. `updated_at`, `revision` and
    `content_sha256` are not: they are bookkeeping about the record rather than
    claims the record makes, and including them would make the hash
    self-referential.
    """
    payload = json.dumps(
        {
            "domain": _INTEGRITY_DOMAIN,
            "project_id": record.project_id,
            "vault_path": record.vault_path,
            "kind": record.kind,
            "title": record.title,
            "summary": record.summary,
            "body": record.body,
            "tags": sorted(record.tags),
            "status": record.status,
            "review_state": record.review_state,
            "created_at": record.created_at,
            "valid_from": record.valid_from,
            "valid_until": record.valid_until,
            "supersedes_ids": sorted(record.supersedes_ids),
            "sources": sorted(
                (item.source_id, item.uri, item.title, item.version, item.content_hash)
                for item in record.sources
            ),
            "locators": sorted(
                (item.source_id, item.locator, item.relationship)
                for item in record.locators
            ),
            "idempotency_key": record.idempotency_key,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
