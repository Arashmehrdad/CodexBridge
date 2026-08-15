"""Portable, content-addressed Agent Skills library.

Soma owns only mechanical package identity, provenance, immutable revision bytes,
and current/enabled registry state.  The free-form Skill body is never parsed
into plans, steps, routes, or reasoning state.
"""

from __future__ import annotations

import json
import os
import shutil
import sqlite3
import tempfile
from contextlib import contextmanager
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path, PurePosixPath
from typing import Iterable, Iterator, Mapping

import yaml


SKILL_SCHEMA_VERSION = 1
SKILL_NAME_MAX_CHARS = 64
SKILL_DESCRIPTION_MAX_CHARS = 1024
SKILL_NAME_PATTERN = r"^[a-z0-9]+(?:-[a-z0-9]+)*$"
SOURCE_KINDS = {
    "owner_local_import",
    "repo_builtin_seed",
    "native_exported_copy",
    "imported_source",
}


class SkillLibraryError(ValueError):
    """Base error for mechanical Skill-library contract violations."""


class SkillPackageInvalid(SkillLibraryError):
    """The submitted package is not a valid bounded v1 Agent Skill package."""


class SkillRequestConflict(SkillLibraryError):
    """A stable mutation request identity was reused with different semantics."""


class StaleSkillState(SkillLibraryError):
    """A current/enabled mutation supplied a stale expected state version."""


class PackageIntegrityMismatch(SkillLibraryError):
    """Canonical immutable revision bytes changed out of band."""


class SkillNotFound(KeyError):
    """Requested Skill or immutable revision is absent."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def make_skill_ref(name: str, package_hash: str) -> str:
    return f"skill:{name}@sha256:{package_hash}"


def parse_skill_ref(skill_ref: str) -> tuple[str, str]:
    prefix = "skill:"
    marker = "@sha256:"
    if not skill_ref.startswith(prefix) or marker not in skill_ref:
        raise SkillPackageInvalid("invalid skill_ref")
    body = skill_ref[len(prefix) :]
    name, package_hash = body.rsplit(marker, 1)
    if not name or len(package_hash) != 64:
        raise SkillPackageInvalid("invalid skill_ref")
    try:
        int(package_hash, 16)
    except ValueError as exc:
        raise SkillPackageInvalid("invalid skill_ref") from exc
    return name, package_hash.lower()


def _canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _canonical_hash(value: object) -> str:
    return sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def normalize_package_path(value: str) -> str:
    raw = str(value or "")
    if not raw or "\\" in raw or "\x00" in raw:
        raise SkillPackageInvalid(f"invalid package-relative path: {raw!r}")
    parts = raw.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise SkillPackageInvalid(f"invalid package-relative path: {raw!r}")
    path = PurePosixPath(raw)
    if path.is_absolute() or raw.startswith("/"):
        raise SkillPackageInvalid(f"absolute package path is not allowed: {raw!r}")
    for part in parts:
        if ":" in part or part.endswith(".") or part.endswith(" "):
            raise SkillPackageInvalid(f"non-portable package path component: {part!r}")
    return path.as_posix()


def _validate_unique_paths(paths: Iterable[str]) -> list[str]:
    normalized: list[str] = []
    casefolded: dict[str, str] = {}
    for raw in paths:
        path = normalize_package_path(raw)
        folded = path.casefold()
        prior = casefolded.get(folded)
        if prior is not None:
            raise SkillPackageInvalid(
                f"duplicate/case-colliding package paths: {prior!r} and {path!r}"
            )
        casefolded[folded] = path
        normalized.append(path)
    return normalized


def parse_skill_metadata(skill_md: bytes) -> dict[str, str]:
    try:
        text = skill_md.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise SkillPackageInvalid("SKILL.md must be valid UTF-8") from exc
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        raise SkillPackageInvalid("SKILL.md must start with YAML frontmatter")
    closing = next((index for index in range(1, len(lines)) if lines[index].strip() == "---"), None)
    if closing is None:
        raise SkillPackageInvalid("SKILL.md YAML frontmatter is not terminated")
    try:
        metadata = yaml.safe_load("\n".join(lines[1:closing])) or {}
    except yaml.YAMLError as exc:
        raise SkillPackageInvalid("SKILL.md YAML frontmatter is invalid") from exc
    if not isinstance(metadata, dict):
        raise SkillPackageInvalid("SKILL.md frontmatter must be a mapping")
    name = metadata.get("name")
    description = metadata.get("description")
    if not isinstance(name, str) or not name:
        raise SkillPackageInvalid("SKILL.md frontmatter requires a non-empty name")
    if len(name) > SKILL_NAME_MAX_CHARS:
        raise SkillPackageInvalid("Skill name exceeds 64 characters")
    import re

    if re.fullmatch(SKILL_NAME_PATTERN, name) is None:
        raise SkillPackageInvalid(
            "Skill name must contain lowercase letters/numbers separated by single hyphens"
        )
    if not isinstance(description, str) or not description.strip():
        raise SkillPackageInvalid("SKILL.md frontmatter requires a non-empty description")
    if len(description) > SKILL_DESCRIPTION_MAX_CHARS:
        raise SkillPackageInvalid("Skill description exceeds 1024 characters")
    return {"name": name, "description": description}


def build_manifest(files: Mapping[str, bytes]) -> tuple[list[dict[str, object]], str]:
    normalized = _validate_unique_paths(files.keys())
    manifest: list[dict[str, object]] = []
    by_normalized = {normalize_package_path(path): bytes(content) for path, content in files.items()}
    for relative_path in sorted(normalized):
        content = by_normalized[relative_path]
        manifest.append(
            {
                "path": relative_path,
                "sha256": sha256(content).hexdigest(),
                "size_bytes": len(content),
            }
        )
    package_hash = sha256(_canonical_json(manifest).encode("utf-8")).hexdigest()
    return manifest, package_hash


class SkillLibrary:
    def __init__(
        self,
        root: Path,
        *,
        max_files: int = 256,
        max_total_bytes: int = 16 * 1024 * 1024,
        max_file_bytes: int = 4 * 1024 * 1024,
        read_only: bool = False,
    ) -> None:
        self.root = Path(root).resolve()
        self.max_files = int(max_files)
        self.max_total_bytes = int(max_total_bytes)
        self.max_file_bytes = int(max_file_bytes)
        self.read_only = bool(read_only)
        self.revisions_root = self.root / "revisions"
        self.staging_root = self.root / ".staging"
        self.db_path = self.root / "registry.sqlite3"
        if self.read_only:
            if not self.root.is_dir() or not self.db_path.is_file():
                raise SkillNotFound("Skill library is not initialized")
            return
        self.root.mkdir(parents=True, exist_ok=True)
        self.revisions_root.mkdir(parents=True, exist_ok=True)
        self.staging_root.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def connect(self) -> sqlite3.Connection:
        if self.read_only:
            uri = f"file:{self.db_path.as_posix()}?mode=ro"
            conn = sqlite3.connect(uri, timeout=5, uri=True)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys = ON")
            return conn
        conn = sqlite3.connect(self.db_path, timeout=5)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        return conn

    def _init_db(self) -> None:
        with self.connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS skill_library_schema (
                    version INTEGER PRIMARY KEY,
                    applied_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS skill_revisions (
                    skill_name TEXT NOT NULL,
                    package_hash TEXT NOT NULL,
                    skill_ref TEXT NOT NULL UNIQUE,
                    description TEXT NOT NULL,
                    manifest_json TEXT NOT NULL,
                    file_count INTEGER NOT NULL,
                    total_bytes INTEGER NOT NULL,
                    parent_skill_ref TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    PRIMARY KEY(skill_name, package_hash)
                );
                CREATE TABLE IF NOT EXISTS skill_revision_sources (
                    skill_name TEXT NOT NULL,
                    package_hash TEXT NOT NULL,
                    source_kind TEXT NOT NULL,
                    source_ref TEXT NOT NULL DEFAULT '',
                    first_seen_at TEXT NOT NULL,
                    PRIMARY KEY(skill_name, package_hash, source_kind, source_ref),
                    FOREIGN KEY(skill_name, package_hash)
                      REFERENCES skill_revisions(skill_name, package_hash)
                );
                CREATE TABLE IF NOT EXISTS skill_state (
                    skill_name TEXT PRIMARY KEY,
                    current_package_hash TEXT NOT NULL DEFAULT '',
                    enabled INTEGER NOT NULL DEFAULT 1 CHECK(enabled IN (0, 1)),
                    state_version INTEGER NOT NULL DEFAULT 0,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS skill_mutation_requests (
                    controller_request_id TEXT PRIMARY KEY,
                    operation TEXT NOT NULL,
                    request_hash TEXT NOT NULL,
                    result_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                """
            )
            conn.execute(
                "INSERT OR IGNORE INTO skill_library_schema(version, applied_at) VALUES (?, ?)",
                (SKILL_SCHEMA_VERSION, utc_now()),
            )

    @contextmanager
    def _transaction(self) -> Iterator[sqlite3.Connection]:
        if self.read_only:
            raise SkillLibraryError("Skill library was opened read-only")
        conn = self.connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            try:
                yield conn
            except BaseException:
                conn.rollback()
                raise
            conn.commit()
        finally:
            conn.close()

    def _bounded_files(self, files: Mapping[str, bytes]) -> dict[str, bytes]:
        if not files or "SKILL.md" not in files:
            raise SkillPackageInvalid("canonical Skill package requires SKILL.md")
        if len(files) > self.max_files:
            raise SkillPackageInvalid("Skill package exceeds max_files")
        normalized = _validate_unique_paths(files.keys())
        result: dict[str, bytes] = {}
        total = 0
        for raw, normalized_path in zip(files.keys(), normalized, strict=True):
            content = bytes(files[raw])
            if len(content) > self.max_file_bytes:
                raise SkillPackageInvalid(f"Skill file exceeds max_file_bytes: {normalized_path}")
            total += len(content)
            if total > self.max_total_bytes:
                raise SkillPackageInvalid("Skill package exceeds max_total_bytes")
            result[normalized_path] = content
        return result

    def _source(self, source_kind: str, source_ref: str) -> tuple[str, str]:
        kind = str(source_kind or "").strip()
        if kind not in SOURCE_KINDS:
            raise SkillPackageInvalid(f"unsupported Skill source_kind: {kind!r}")
        ref = str(source_ref or "")
        if len(ref) > 32_768:
            raise SkillPackageInvalid("Skill source_ref is too long")
        return kind, ref

    def _require_writable(self) -> None:
        if self.read_only:
            raise SkillLibraryError("Skill library was opened read-only")

    def _request_id(self, controller_request_id: str) -> str:
        value = str(controller_request_id or "").strip()
        if not value or len(value) > 128:
            raise SkillPackageInvalid("controller_request_id must be 1..128 characters")
        return value

    def _revision_path(self, name: str, package_hash: str) -> Path:
        return self.revisions_root / package_hash / name

    def _read_request(
        self, conn: sqlite3.Connection, controller_request_id: str, operation: str, request_hash: str
    ) -> dict[str, object] | None:
        row = conn.execute(
            "SELECT operation, request_hash, result_json FROM skill_mutation_requests WHERE controller_request_id = ?",
            (controller_request_id,),
        ).fetchone()
        if row is None:
            return None
        if row["operation"] != operation or row["request_hash"] != request_hash:
            raise SkillRequestConflict(
                f"controller_request_id {controller_request_id!r} is already bound to a different Skill mutation"
            )
        return json.loads(row["result_json"])

    def _record_request(
        self,
        conn: sqlite3.Connection,
        *,
        controller_request_id: str,
        operation: str,
        request_hash: str,
        result: dict[str, object],
    ) -> None:
        conn.execute(
            "INSERT INTO skill_mutation_requests(controller_request_id, operation, request_hash, result_json, created_at) VALUES (?, ?, ?, ?, ?)",
            (controller_request_id, operation, request_hash, _canonical_json(result), utc_now()),
        )

    def _materialize(self, name: str, files: Mapping[str, bytes], package_hash: str) -> Path:
        self._require_writable()
        destination = self._revision_path(name, package_hash)
        if destination.exists():
            self._verify_path(name, package_hash, destination)
            return destination
        temp_parent = Path(tempfile.mkdtemp(prefix="skill-", dir=self.staging_root))
        package_root = temp_parent / name
        try:
            package_root.mkdir()
            for relative_path, content in files.items():
                target = package_root.joinpath(*PurePosixPath(relative_path).parts)
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(content)
            destination.parent.mkdir(parents=True, exist_ok=True)
            try:
                os.replace(package_root, destination)
            except OSError:
                if not destination.exists():
                    raise
                self._verify_path(name, package_hash, destination)
            return destination
        finally:
            shutil.rmtree(temp_parent, ignore_errors=True)

    def import_revision(
        self,
        files: Mapping[str, bytes],
        *,
        controller_request_id: str,
        source_kind: str = "owner_local_import",
        source_ref: str = "",
        make_current: bool = False,
        expected_state_version: int | None = None,
    ) -> dict[str, object]:
        self._require_writable()
        request_id = self._request_id(controller_request_id)
        source_kind, source_ref = self._source(source_kind, source_ref)
        bounded = self._bounded_files(files)
        metadata = parse_skill_metadata(bounded["SKILL.md"])
        name = metadata["name"]
        manifest, package_hash = build_manifest(bounded)
        total_bytes = sum(int(entry["size_bytes"]) for entry in manifest)
        request_hash = _canonical_hash(
            {
                "name": name,
                "package_hash": package_hash,
                "source_kind": source_kind,
                "source_ref": source_ref,
                "make_current": bool(make_current),
                "expected_state_version": expected_state_version,
            }
        )
        with self.connect() as conn:
            replay = self._read_request(conn, request_id, "import_revision", request_hash)
        if replay is not None:
            self.get_revision(str(replay["skill_ref"]))
            return {**replay, "replayed": True}

        package_root = self._materialize(name, bounded, package_hash)
        skill_ref = make_skill_ref(name, package_hash)
        with self._transaction() as conn:
            replay = self._read_request(conn, request_id, "import_revision", request_hash)
            if replay is not None:
                return {**replay, "replayed": True}
            state = conn.execute(
                "SELECT current_package_hash, enabled, state_version FROM skill_state WHERE skill_name = ?",
                (name,),
            ).fetchone()
            parent_ref = ""
            if state is not None and state["current_package_hash"]:
                parent_ref = make_skill_ref(name, state["current_package_hash"])
            created = conn.execute(
                "SELECT 1 FROM skill_revisions WHERE skill_name = ? AND package_hash = ?",
                (name, package_hash),
            ).fetchone() is None
            conn.execute(
                "INSERT OR IGNORE INTO skill_revisions(skill_name, package_hash, skill_ref, description, manifest_json, file_count, total_bytes, parent_skill_ref, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    name,
                    package_hash,
                    skill_ref,
                    metadata["description"],
                    _canonical_json(manifest),
                    len(manifest),
                    total_bytes,
                    parent_ref,
                    utc_now(),
                ),
            )
            conn.execute(
                "INSERT OR IGNORE INTO skill_revision_sources(skill_name, package_hash, source_kind, source_ref, first_seen_at) VALUES (?, ?, ?, ?, ?)",
                (name, package_hash, source_kind, source_ref, utc_now()),
            )
            if state is None:
                conn.execute(
                    "INSERT INTO skill_state(skill_name, current_package_hash, enabled, state_version, updated_at) VALUES (?, '', 1, 0, ?)",
                    (name, utc_now()),
                )
                state_version = 0
            else:
                state_version = int(state["state_version"])
            if make_current:
                if state_version != 0 and expected_state_version is None:
                    raise StaleSkillState(
                        "expected_state_version is required when replacing an existing current Skill state"
                    )
                expected = state_version if expected_state_version is None else int(expected_state_version)
                changed = conn.execute(
                    "UPDATE skill_state SET current_package_hash = ?, state_version = state_version + 1, updated_at = ? WHERE skill_name = ? AND state_version = ?",
                    (package_hash, utc_now(), name, expected),
                ).rowcount
                if changed != 1:
                    raise StaleSkillState("stale Skill state version")
                state_version = expected + 1
            result: dict[str, object] = {
                "skill_ref": skill_ref,
                "name": name,
                "description": metadata["description"],
                "package_hash": package_hash,
                "package_root": str(package_root),
                "created": created,
                "current": bool(make_current),
                "state_version": state_version,
                "replayed": False,
            }
            self._record_request(
                conn,
                controller_request_id=request_id,
                operation="import_revision",
                request_hash=request_hash,
                result=result,
            )
            return result

    def import_directory(
        self,
        package_root: Path,
        *,
        controller_request_id: str,
        source_kind: str = "owner_local_import",
        source_ref: str = "",
        make_current: bool = False,
        expected_state_version: int | None = None,
    ) -> dict[str, object]:
        self._require_writable()
        package_root = Path(package_root)
        if package_root.is_symlink():
            raise SkillPackageInvalid("symlinks are not allowed in canonical v1 Skill packages")
        if not package_root.is_dir():
            raise SkillPackageInvalid("Skill package root must be a directory")
        files: dict[str, bytes] = {}
        for current, dirnames, filenames in os.walk(package_root, followlinks=False):
            current_path = Path(current)
            for dirname in list(dirnames):
                candidate = current_path / dirname
                if candidate.is_symlink():
                    raise SkillPackageInvalid("symlinks are not allowed in canonical v1 Skill packages")
            for filename in filenames:
                candidate = current_path / filename
                if candidate.is_symlink():
                    raise SkillPackageInvalid("symlinks are not allowed in canonical v1 Skill packages")
                relative = candidate.relative_to(package_root).as_posix()
                files[relative] = candidate.read_bytes()
        bounded = self._bounded_files(files)
        metadata = parse_skill_metadata(bounded["SKILL.md"])
        if package_root.name != metadata["name"]:
            raise SkillPackageInvalid(
                "Skill frontmatter name must match the immediate package-root directory"
            )
        return self.import_revision(
            bounded,
            controller_request_id=controller_request_id,
            source_kind=source_kind,
            source_ref=source_ref or str(package_root.resolve()),
            make_current=make_current,
            expected_state_version=expected_state_version,
        )

    def _scan_revision_path(self, package_root: Path) -> dict[str, bytes]:
        if package_root.is_symlink():
            raise PackageIntegrityMismatch("package_integrity_mismatch")
        files: dict[str, bytes] = {}
        for current, dirnames, filenames in os.walk(package_root, followlinks=False):
            current_path = Path(current)
            for dirname in list(dirnames):
                if (current_path / dirname).is_symlink():
                    raise PackageIntegrityMismatch("package_integrity_mismatch")
            for filename in filenames:
                candidate = current_path / filename
                if candidate.is_symlink():
                    raise PackageIntegrityMismatch("package_integrity_mismatch")
                files[candidate.relative_to(package_root).as_posix()] = candidate.read_bytes()
        return files

    def _verify_path(self, name: str, package_hash: str, package_root: Path) -> None:
        try:
            files = self._bounded_files(self._scan_revision_path(package_root))
            metadata = parse_skill_metadata(files["SKILL.md"])
            if metadata["name"] != name or package_root.name != name:
                raise PackageIntegrityMismatch("package_integrity_mismatch")
            _manifest, observed_hash = build_manifest(files)
        except SkillLibraryError as exc:
            if isinstance(exc, PackageIntegrityMismatch):
                raise
            raise PackageIntegrityMismatch("package_integrity_mismatch") from exc
        if observed_hash != package_hash:
            raise PackageIntegrityMismatch("package_integrity_mismatch")

    def get_revision(self, skill_ref: str) -> dict[str, object]:
        name, package_hash = parse_skill_ref(skill_ref)
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM skill_revisions WHERE skill_name = ? AND package_hash = ?",
                (name, package_hash),
            ).fetchone()
            if row is None:
                raise SkillNotFound(skill_ref)
            sources = [
                dict(source)
                for source in conn.execute(
                    "SELECT source_kind, source_ref, first_seen_at FROM skill_revision_sources WHERE skill_name = ? AND package_hash = ? ORDER BY source_kind, source_ref",
                    (name, package_hash),
                ).fetchall()
            ]
            state = conn.execute(
                "SELECT current_package_hash, enabled, state_version FROM skill_state WHERE skill_name = ?",
                (name,),
            ).fetchone()
        package_root = self._revision_path(name, package_hash)
        self._verify_path(name, package_hash, package_root)
        result = dict(row)
        result["manifest"] = json.loads(result.pop("manifest_json"))
        result["sources"] = sources
        result["package_root"] = str(package_root)
        result["current"] = bool(state and state["current_package_hash"] == package_hash)
        result["enabled"] = bool(state and state["enabled"])
        result["state_version"] = int(state["state_version"]) if state else 0
        return result

    def get_state(self, skill_name: str) -> dict[str, object]:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT skill_name, current_package_hash, enabled, state_version, updated_at FROM skill_state WHERE skill_name = ?",
                (skill_name,),
            ).fetchone()
        if row is None:
            raise SkillNotFound(skill_name)
        result = dict(row)
        current_hash = str(result["current_package_hash"])
        result["current_skill_ref"] = make_skill_ref(skill_name, current_hash) if current_hash else ""
        result["enabled"] = bool(result["enabled"])
        return result

    def set_current(
        self,
        skill_ref: str,
        *,
        expected_state_version: int,
        controller_request_id: str,
    ) -> dict[str, object]:
        self._require_writable()
        name, package_hash = parse_skill_ref(skill_ref)
        # A mutable pointer may never bless bytes that fail the immutable
        # revision's stored identity.  This keeps drift detection in front of
        # future discovery rather than only on exact historical reads.
        self.get_revision(skill_ref)
        request_id = self._request_id(controller_request_id)
        request_hash = _canonical_hash(
            {"skill_ref": skill_ref, "expected_state_version": int(expected_state_version)}
        )
        with self._transaction() as conn:
            replay = self._read_request(conn, request_id, "set_current", request_hash)
            if replay is not None:
                return {**replay, "replayed": True}
            if conn.execute(
                "SELECT 1 FROM skill_revisions WHERE skill_name = ? AND package_hash = ?",
                (name, package_hash),
            ).fetchone() is None:
                raise SkillNotFound(skill_ref)
            changed = conn.execute(
                "UPDATE skill_state SET current_package_hash = ?, state_version = state_version + 1, updated_at = ? WHERE skill_name = ? AND state_version = ?",
                (package_hash, utc_now(), name, int(expected_state_version)),
            ).rowcount
            if changed != 1:
                raise StaleSkillState("stale Skill state version")
            result = {
                "skill_ref": skill_ref,
                "name": name,
                "current_package_hash": package_hash,
                "state_version": int(expected_state_version) + 1,
                "replayed": False,
            }
            self._record_request(
                conn,
                controller_request_id=request_id,
                operation="set_current",
                request_hash=request_hash,
                result=result,
            )
            return result

    def set_enabled(
        self,
        skill_name: str,
        enabled: bool,
        *,
        expected_state_version: int,
        controller_request_id: str,
    ) -> dict[str, object]:
        self._require_writable()
        request_id = self._request_id(controller_request_id)
        request_hash = _canonical_hash(
            {
                "skill_name": skill_name,
                "enabled": bool(enabled),
                "expected_state_version": int(expected_state_version),
            }
        )
        with self._transaction() as conn:
            replay = self._read_request(conn, request_id, "set_enabled", request_hash)
            if replay is not None:
                return {**replay, "replayed": True}
            changed = conn.execute(
                "UPDATE skill_state SET enabled = ?, state_version = state_version + 1, updated_at = ? WHERE skill_name = ? AND state_version = ?",
                (1 if enabled else 0, utc_now(), skill_name, int(expected_state_version)),
            ).rowcount
            if changed != 1:
                if conn.execute(
                    "SELECT 1 FROM skill_state WHERE skill_name = ?", (skill_name,)
                ).fetchone() is None:
                    raise SkillNotFound(skill_name)
                raise StaleSkillState("stale Skill state version")
            result = {
                "name": skill_name,
                "enabled": bool(enabled),
                "state_version": int(expected_state_version) + 1,
                "replayed": False,
            }
            self._record_request(
                conn,
                controller_request_id=request_id,
                operation="set_enabled",
                request_hash=request_hash,
                result=result,
            )
            return result

    def history(self, skill_name: str) -> list[dict[str, object]]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT skill_ref, package_hash, description, parent_skill_ref, created_at FROM skill_revisions WHERE skill_name = ? ORDER BY created_at, package_hash",
                (skill_name,),
            ).fetchall()
        return [dict(row) for row in rows]
