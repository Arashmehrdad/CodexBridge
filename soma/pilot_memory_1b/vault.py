"""Canonical vault: Markdown files on disk, nothing else.

Frontmatter is written and parsed by a small strict reader rather than a
general YAML library. The benchmark needs malformed metadata to be a
first-class, deterministic observation, and a permissive parser would quietly
repair exactly the defect being measured.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

from .corpus import NoteSpec

_WIKILINK = re.compile(r"\[\[([^\]|]+)\]\]")
_TYPED_LINK = re.compile(r"^-\s+(\w+)::\s*\[\[([^\]|]+)\]\]\s*$")


@dataclass
class ParsedNote:
    note_id: str
    project_id: str
    kind: str
    title: str
    created: str
    source: str
    supersedes: list[str]
    supersedes_claims: list[tuple[str, str]]
    claims: dict[str, str]
    relations: list[tuple[str, str]]
    body: str
    path: Path
    frontmatter_ok: bool
    parse_error: str = ""

    @property
    def wikilink_targets(self) -> list[str]:
        return [m.group(1).strip() for m in _WIKILINK.finditer(self.body)]


def _render_frontmatter(spec: NoteSpec) -> str:
    lines = [
        "---",
        f"id: {spec.note_id}",
        f"project: {spec.project_id}",
        f"kind: {spec.kind}",
        f"title: {spec.title}",
        f"created: {spec.created}",
        f"source: {spec.source}",
    ]
    if spec.supersedes:
        lines.append("supersedes: " + ", ".join(spec.supersedes))
    if spec.supersedes_claims:
        joined = ", ".join(f"{note}#{claim}" for note, claim in spec.supersedes_claims)
        lines.append("supersedes_claims: " + joined)
    if spec.claims:
        lines.append("claims:")
        for key, value in spec.claims:
            lines.append(f"  {key}: {value}")
    lines.append("---")
    return "\n".join(lines)


def render_note(spec: NoteSpec) -> str:
    """Render one canonical Markdown file."""
    if spec.malformed_frontmatter:
        # Unterminated block, a tab-indented line, and a field with no
        # separator. This is the shape a hand-edited note actually breaks in.
        head = (
            "---\n"
            f"id: {spec.note_id}\n"
            f"project: {spec.project_id}\n"
            f"\tkind {spec.kind}\n"
            f"created: {spec.created}\n"
        )
        return f"{head}\n# {spec.title}\n\n{spec.body}\n"

    parts = [_render_frontmatter(spec), "", f"# {spec.title}", "", spec.body, ""]
    if spec.relations:
        parts.append("## Relations")
        parts.append("")
        for relation_type, target in spec.relations:
            parts.append(f"- {relation_type}:: [[{target}]]")
        parts.append("")
    return "\n".join(parts)


def write_vault(root: Path, specs: tuple[NoteSpec, ...]) -> None:
    """Materialize the canonical corpus. The directory becomes the authority."""
    root.mkdir(parents=True, exist_ok=True)
    for spec in specs:
        (root / f"{spec.note_id}.md").write_text(render_note(spec), encoding="utf-8")


def _split_frontmatter(text: str) -> tuple[list[str], str, str]:
    """Return (frontmatter_lines, body, error)."""
    if not text.startswith("---"):
        return [], text, "missing_frontmatter_open"
    rest = text.split("\n", 1)[1] if "\n" in text else ""
    end = rest.find("\n---")
    if end == -1:
        return [], rest, "unterminated_frontmatter"
    block = rest[:end]
    body = rest[end + 4:]
    return block.split("\n"), body.lstrip("\n"), ""


def parse_note(path: Path) -> ParsedNote:
    """Parse one canonical file. Never raises on malformed metadata."""
    text = path.read_text(encoding="utf-8")
    lines, body, error = _split_frontmatter(text)

    fields: dict[str, str] = {}
    claims: dict[str, str] = {}
    in_claims = False
    for raw in lines:
        if not raw.strip():
            continue
        if raw.startswith("\t"):
            error = error or "indentation_defect"
            continue
        if in_claims and raw.startswith("  "):
            if ":" not in raw:
                error = error or "malformed_claim"
                continue
            key, _, value = raw.strip().partition(":")
            claims[key.strip()] = value.strip()
            continue
        in_claims = False
        if raw.rstrip() == "claims:":
            in_claims = True
            continue
        if ":" not in raw:
            error = error or "malformed_field"
            continue
        key, _, value = raw.partition(":")
        fields[key.strip()] = value.strip()

    relations: list[tuple[str, str]] = []
    for raw in body.split("\n"):
        match = _TYPED_LINK.match(raw.strip())
        if match:
            relations.append((match.group(1), match.group(2).strip()))

    supersedes = [
        part.strip()
        for part in fields.get("supersedes", "").split(",")
        if part.strip()
    ]
    superseded_claims: list[tuple[str, str]] = []
    for part in fields.get("supersedes_claims", "").split(","):
        part = part.strip()
        if not part:
            continue
        if "#" not in part:
            error = error or "malformed_supersedes_claims"
            continue
        note, _, claim = part.partition("#")
        superseded_claims.append((note.strip(), claim.strip()))

    note_id = fields.get("id", path.stem)
    project_id = fields.get("project", "")
    frontmatter_ok = not error and bool(project_id) and bool(fields.get("kind"))

    return ParsedNote(
        note_id=note_id,
        project_id=project_id,
        kind=fields.get("kind", ""),
        title=fields.get("title", ""),
        created=fields.get("created", ""),
        source=fields.get("source", ""),
        supersedes=supersedes,
        supersedes_claims=superseded_claims,
        claims=claims,
        relations=relations,
        body=body,
        path=path,
        frontmatter_ok=frontmatter_ok,
        parse_error=error or ("" if frontmatter_ok else "incomplete_frontmatter"),
    )


def read_vault(root: Path) -> list[ParsedNote]:
    """Read every canonical file, in deterministic order."""
    return [parse_note(p) for p in sorted(root.glob("*.md"))]


def corpus_hash(root: Path) -> str:
    """Digest of canonical bytes only. Independent of any derived structure."""
    digest = hashlib.sha256()
    for path in sorted(root.glob("*.md")):
        digest.update(path.name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()
