from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path, PurePosixPath

from pydantic import ValidationError

from .canonical import (
    canonical_json_sha256,
    canonical_text_sha256,
    logical_record_id,
    normalize_canonical_text,
    normalize_repo_relative_path,
)
from .models import ProjectManifest, ResearchMapSidecar, ResearchRootConfig

MAX_SOURCE_BYTES = 32 * 1024 * 1024
MAX_SIDECAR_BYTES = 8 * 1024 * 1024


class SidecarState(StrEnum):
    VALID = "valid"
    MISSING = "missing"
    MALFORMED = "malformed"
    SOURCE_PATH_MISMATCH = "source_path_mismatch"
    STALE_HASH = "stale_hash"
    INVALID_ANCHOR = "invalid_anchor"
    SOURCE_INVALID = "source_invalid"
    PATH_COLLISION = "path_collision"
    MISSING_SOURCE = "missing_source"


@dataclass(frozen=True, slots=True)
class ResearchMapIssue:
    code: str
    source_path: str = ""
    sidecar_path: str = ""
    relation_id: str = ""

    def sort_key(self) -> tuple[str, str, str, str]:
        return (self.code, self.source_path, self.sidecar_path, self.relation_id)


@dataclass(frozen=True, slots=True)
class ScannedResearchRecord:
    root_path: str
    source_path: str
    logical_record_id: str
    source_exists: bool
    canonical_text_sha256: str | None
    expected_sidecar_path: str
    sidecar_state: SidecarState
    sidecar: ResearchMapSidecar | None = None
    canonical_sidecar_sha256: str | None = None
    malformed_sidecar_raw_sha256: str | None = None


@dataclass(frozen=True, slots=True)
class SidecarScanResult:
    records: tuple[ScannedResearchRecord, ...]
    issues: tuple[ResearchMapIssue, ...]


def expected_sidecar_path(root: ResearchRootConfig, source_path: str) -> str:
    normalized_source = normalize_repo_relative_path(source_path)
    source = PurePosixPath(normalized_source)
    root_path = PurePosixPath(root.path)
    try:
        relative = source.relative_to(root_path)
    except ValueError as exc:
        raise ValueError("source path is not owned by the configured research root") from exc
    if not relative.parts:
        raise ValueError("source path must identify a file below the research root")
    sidecar = root_path / root.sidecar_dir / f"{relative.stem}.json"
    return normalize_repo_relative_path(sidecar.as_posix())


def _is_within(child: Path, parent: Path) -> bool:
    try:
        child.relative_to(parent)
    except ValueError:
        return False
    return True


def _safe_read_bytes(
    repository_root: Path,
    path: Path,
    *,
    max_bytes: int,
) -> tuple[bytes | None, str]:
    try:
        resolved = path.resolve(strict=True)
        if not _is_within(resolved, repository_root):
            return None, "path_escapes_repository"
        if not resolved.is_file():
            return None, "not_a_file"
        size = resolved.stat().st_size
        if size > max_bytes:
            return None, "file_too_large"
        return resolved.read_bytes(), ""
    except OSError:
        return None, "read_error"


def _sidecar_dir_relative(root: ResearchRootConfig) -> PurePosixPath:
    return PurePosixPath(root.sidecar_dir)


def _is_inside_sidecar_dir(relative_path: PurePosixPath, root: ResearchRootConfig) -> bool:
    sidecar_parts = _sidecar_dir_relative(root).parts
    return relative_path.parts[: len(sidecar_parts)] == sidecar_parts


def _matches_include(relative_path: PurePosixPath, root: ResearchRootConfig) -> bool:
    return any(relative_path.match(pattern) for pattern in root.include)


def _owner_for_source_path(
    manifest: ProjectManifest,
    source_path: str,
) -> ResearchRootConfig | None:
    candidate = PurePosixPath(source_path)
    for root in sorted(manifest.research_map.roots, key=lambda item: item.path):
        root_path = PurePosixPath(root.path)
        try:
            relative = candidate.relative_to(root_path)
        except ValueError:
            continue
        if relative.parts:
            return root
    return None


def _load_sidecar(
    repository_root: Path,
    sidecar_path: Path,
) -> tuple[ResearchMapSidecar | None, str | None, str | None, str]:
    raw, read_error = _safe_read_bytes(
        repository_root,
        sidecar_path,
        max_bytes=MAX_SIDECAR_BYTES,
    )
    if raw is None:
        return None, None, None, read_error or "sidecar_read_error"
    raw_sha = hashlib.sha256(raw).hexdigest()
    try:
        payload = json.loads(raw.decode("utf-8", errors="strict"))
        sidecar = ResearchMapSidecar.model_validate(payload)
    except UnicodeDecodeError:
        return None, None, raw_sha, "sidecar_not_utf8"
    except json.JSONDecodeError:
        return None, None, raw_sha, "sidecar_invalid_json"
    except ValidationError:
        return None, None, raw_sha, "sidecar_schema_invalid"
    return sidecar, canonical_json_sha256(sidecar), raw_sha, ""


def _source_document(
    repository_root: Path,
    source_path: Path,
) -> tuple[str | None, str | None, str]:
    raw, read_error = _safe_read_bytes(
        repository_root,
        source_path,
        max_bytes=MAX_SOURCE_BYTES,
    )
    if raw is None:
        return None, None, read_error or "source_read_error"
    try:
        text = normalize_canonical_text(raw)
    except UnicodeDecodeError:
        return None, None, "source_not_utf8"
    return text, canonical_text_sha256(text), ""


def _record_for_existing_source(
    repository_root: Path,
    root: ResearchRootConfig,
    source_repo_path: str,
    *,
    sidecar_collision: bool,
) -> tuple[ScannedResearchRecord, list[ResearchMapIssue]]:
    issues: list[ResearchMapIssue] = []
    logical_id = logical_record_id(source_repo_path)
    expected = expected_sidecar_path(root, source_repo_path)
    source_abs = repository_root / Path(source_repo_path)
    sidecar_abs = repository_root / Path(expected)

    source_text, source_hash, source_error = _source_document(repository_root, source_abs)
    sidecar: ResearchMapSidecar | None = None
    sidecar_hash: str | None = None
    raw_sidecar_hash: str | None = None
    sidecar_error = ""
    if sidecar_abs.exists():
        sidecar, sidecar_hash, raw_sidecar_hash, sidecar_error = _load_sidecar(
            repository_root,
            sidecar_abs,
        )

    if source_error:
        state = SidecarState.SOURCE_INVALID
        issues.append(
            ResearchMapIssue(
                code="source_invalid",
                source_path=source_repo_path,
                sidecar_path=expected,
            )
        )
    elif sidecar_collision:
        state = SidecarState.PATH_COLLISION
        issues.append(
            ResearchMapIssue(
                code="sidecar_path_collision",
                source_path=source_repo_path,
                sidecar_path=expected,
            )
        )
    elif not sidecar_abs.exists():
        state = SidecarState.MISSING
    elif sidecar is None:
        state = SidecarState.MALFORMED
        issues.append(
            ResearchMapIssue(
                code=sidecar_error or "malformed_sidecar",
                source_path=source_repo_path,
                sidecar_path=expected,
            )
        )
    elif sidecar.source.path != source_repo_path:
        state = SidecarState.SOURCE_PATH_MISMATCH
        issues.append(
            ResearchMapIssue(
                code="sidecar_source_path_mismatch",
                source_path=source_repo_path,
                sidecar_path=expected,
            )
        )
    elif sidecar.source.canonical_text_sha256 != source_hash:
        state = SidecarState.STALE_HASH
        issues.append(
            ResearchMapIssue(
                code="stale_source_hash",
                source_path=source_repo_path,
                sidecar_path=expected,
            )
        )
    else:
        missing_anchor = False
        assert source_text is not None
        for relation in sidecar.relations:
            anchor = normalize_canonical_text(relation.locator.anchor)
            if anchor not in source_text:
                missing_anchor = True
                issues.append(
                    ResearchMapIssue(
                        code="locator_anchor_missing",
                        source_path=source_repo_path,
                        sidecar_path=expected,
                        relation_id=relation.relation_id,
                    )
                )
        state = SidecarState.INVALID_ANCHOR if missing_anchor else SidecarState.VALID

    malformed_hash = raw_sidecar_hash if sidecar is None else None
    return (
        ScannedResearchRecord(
            root_path=root.path,
            source_path=source_repo_path,
            logical_record_id=logical_id,
            source_exists=True,
            canonical_text_sha256=source_hash,
            expected_sidecar_path=expected,
            sidecar_state=state,
            sidecar=sidecar,
            canonical_sidecar_sha256=sidecar_hash,
            malformed_sidecar_raw_sha256=malformed_hash,
        ),
        issues,
    )


def scan_research_sidecars(
    repository_root: str | Path,
    manifest: ProjectManifest,
) -> SidecarScanResult:
    """Discover configured sources and validate tracked sidecars deterministically."""
    try:
        root_path = Path(repository_root).resolve(strict=True)
    except OSError:
        return SidecarScanResult(
            records=(),
            issues=(ResearchMapIssue(code="repository_root_invalid"),),
        )

    issues: list[ResearchMapIssue] = []
    source_specs: list[tuple[ResearchRootConfig, str]] = []
    all_sidecar_files: set[str] = set()

    for root in sorted(manifest.research_map.roots, key=lambda item: item.path):
        research_root = root_path / Path(root.path)
        if not research_root.exists() or not research_root.is_dir():
            issues.append(ResearchMapIssue(code="research_root_missing", source_path=root.path))
            continue

        for candidate in research_root.rglob("*"):
            if not candidate.is_file():
                continue
            try:
                relative = PurePosixPath(candidate.relative_to(research_root).as_posix())
            except ValueError:
                continue
            if _is_inside_sidecar_dir(relative, root):
                continue
            if candidate.suffix.casefold() != ".md":
                continue
            if not _matches_include(relative, root):
                continue
            source_specs.append((root, (PurePosixPath(root.path) / relative).as_posix()))

        sidecar_root = research_root / Path(root.sidecar_dir)
        if sidecar_root.exists() and sidecar_root.is_dir():
            for candidate in sidecar_root.rglob("*.json"):
                if candidate.is_file():
                    try:
                        all_sidecar_files.add(candidate.relative_to(root_path).as_posix())
                    except ValueError:
                        issues.append(ResearchMapIssue(code="sidecar_path_escapes_repository"))

    source_specs.sort(key=lambda item: item[1])
    expected_owners: dict[str, list[str]] = {}
    for root, source_path in source_specs:
        expected_owners.setdefault(expected_sidecar_path(root, source_path), []).append(source_path)

    records: list[ScannedResearchRecord] = []
    consumed_sidecars: set[str] = set()
    parsed_sidecars: list[tuple[str, ResearchMapSidecar]] = []
    discovered_sources = {source_path for _, source_path in source_specs}

    for root, source_path in source_specs:
        expected = expected_sidecar_path(root, source_path)
        record, record_issues = _record_for_existing_source(
            root_path,
            root,
            source_path,
            sidecar_collision=len(expected_owners.get(expected, ())) > 1,
        )
        records.append(record)
        issues.extend(record_issues)
        if (root_path / Path(expected)).exists():
            consumed_sidecars.add(expected)
        if record.sidecar is not None:
            parsed_sidecars.append((expected, record.sidecar))

    for sidecar_repo_path in sorted(all_sidecar_files - consumed_sidecars):
        sidecar_abs = root_path / Path(sidecar_repo_path)
        sidecar, sidecar_hash, raw_hash, error_code = _load_sidecar(root_path, sidecar_abs)
        if sidecar is None:
            issues.append(
                ResearchMapIssue(
                    code=error_code or "malformed_orphan_sidecar",
                    sidecar_path=sidecar_repo_path,
                )
            )
            continue

        parsed_sidecars.append((sidecar_repo_path, sidecar))
        owner = _owner_for_source_path(manifest, sidecar.source.path)
        if owner is None:
            issues.append(
                ResearchMapIssue(
                    code="sidecar_source_outside_roots",
                    source_path=sidecar.source.path,
                    sidecar_path=sidecar_repo_path,
                )
            )
            continue
        declared_expected = expected_sidecar_path(owner, sidecar.source.path)
        if declared_expected != sidecar_repo_path:
            issues.append(
                ResearchMapIssue(
                    code="unexpected_sidecar_path",
                    source_path=sidecar.source.path,
                    sidecar_path=sidecar_repo_path,
                )
            )
            continue
        if sidecar.source.path in discovered_sources:
            issues.append(
                ResearchMapIssue(
                    code="duplicate_sidecar_for_source",
                    source_path=sidecar.source.path,
                    sidecar_path=sidecar_repo_path,
                )
            )
            continue

        declared_source_abs = root_path / Path(sidecar.source.path)
        if declared_source_abs.exists():
            issues.append(
                ResearchMapIssue(
                    code="sidecar_for_ineligible_source",
                    source_path=sidecar.source.path,
                    sidecar_path=sidecar_repo_path,
                )
            )
            continue

        records.append(
            ScannedResearchRecord(
                root_path=owner.path,
                source_path=sidecar.source.path,
                logical_record_id=logical_record_id(sidecar.source.path),
                source_exists=False,
                canonical_text_sha256=None,
                expected_sidecar_path=declared_expected,
                sidecar_state=SidecarState.MISSING_SOURCE,
                sidecar=sidecar,
                canonical_sidecar_sha256=sidecar_hash,
                malformed_sidecar_raw_sha256=None if sidecar is not None else raw_hash,
            )
        )
        issues.append(
            ResearchMapIssue(
                code="missing_source",
                source_path=sidecar.source.path,
                sidecar_path=sidecar_repo_path,
            )
        )

    relation_owner: dict[str, tuple[str, str]] = {}
    for sidecar_path, sidecar in sorted(parsed_sidecars, key=lambda item: item[0]):
        for relation in sidecar.relations:
            previous = relation_owner.get(relation.relation_id)
            if previous is None:
                relation_owner[relation.relation_id] = (sidecar.source.path, sidecar_path)
                continue
            issues.append(
                ResearchMapIssue(
                    code="duplicate_relation_id",
                    source_path=sidecar.source.path,
                    sidecar_path=sidecar_path,
                    relation_id=relation.relation_id,
                )
            )

    unique_issues = tuple(sorted(set(issues), key=ResearchMapIssue.sort_key))
    records.sort(key=lambda item: (item.source_path, item.expected_sidecar_path))
    return SidecarScanResult(records=tuple(records), issues=unique_issues)
