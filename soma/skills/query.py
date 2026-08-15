"""Read-only progressive-disclosure service over the portable Skill library.

The service retrieves mechanical metadata and exact immutable package bytes. It
never selects a Skill for the model, interprets Skill semantics, grants tool
authority, or executes package resources.
"""

from __future__ import annotations

import base64
import json
from base64 import urlsafe_b64decode, urlsafe_b64encode
from hashlib import sha256
from pathlib import Path
from typing import Any, Final

from .library import SkillLibrary, SkillNotFound, normalize_package_path


SKILL_QUERY_CURSOR_VERSION: Final[str] = "skill.query.cursor.v1"
SKILL_QUERY_DEFAULT_LIMIT: Final[int] = 20
SKILL_QUERY_MAX_LIMIT: Final[int] = 100
SKILL_RESOURCE_DEFAULT_BYTES: Final[int] = 64 * 1024
SKILL_RESOURCE_MAX_BYTES: Final[int] = 256 * 1024
SKILL_GET_INLINE_TEXT_BYTES: Final[int] = 48 * 1024
SKILL_GET_MANIFEST_MAX_ITEMS: Final[int] = 100
SKILL_GET_MANIFEST_MAX_BYTES: Final[int] = 16 * 1024


def _bounded_limit(limit: int) -> int:
    if isinstance(limit, bool) or not isinstance(limit, int):
        raise ValueError("limit must be an integer")
    if limit < 1 or limit > SKILL_QUERY_MAX_LIMIT:
        raise ValueError(f"limit must be between 1 and {SKILL_QUERY_MAX_LIMIT}")
    return limit


def _encode_cursor(*, collection: str, position: dict[str, Any]) -> str:
    payload = {
        "version": SKILL_QUERY_CURSOR_VERSION,
        "collection": collection,
        "position": position,
    }
    encoded = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")
    body = urlsafe_b64encode(encoded).decode("ascii").rstrip("=")
    return f"{body}.{sha256(encoded).hexdigest()}"


def _decode_cursor(cursor: str, *, collection: str) -> dict[str, Any]:
    if not isinstance(cursor, str) or not cursor or cursor.count(".") != 1:
        raise ValueError("Invalid Skill query cursor")
    body, checksum = cursor.split(".", 1)
    if not body or len(checksum) != 64:
        raise ValueError("Invalid Skill query cursor")
    try:
        encoded = urlsafe_b64decode(body + ("=" * (-len(body) % 4)))
        if urlsafe_b64encode(encoded).decode("ascii").rstrip("=") != body:
            raise ValueError("Invalid Skill query cursor")
        if sha256(encoded).hexdigest() != checksum:
            raise ValueError("Skill query cursor checksum mismatch")
        payload = json.loads(encoded.decode("utf-8"))
        canonical = json.dumps(
            payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True
        ).encode("utf-8")
    except ValueError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError):
        raise ValueError("Invalid Skill query cursor") from None
    if canonical != encoded or not isinstance(payload, dict):
        raise ValueError("Invalid Skill query cursor")
    if set(payload) != {"version", "collection", "position"}:
        raise ValueError("Invalid Skill query cursor")
    if payload["version"] != SKILL_QUERY_CURSOR_VERSION:
        raise ValueError("Skill query cursor version mismatch")
    if payload["collection"] != collection:
        raise ValueError("Skill query cursor collection mismatch")
    position = payload["position"]
    if not isinstance(position, dict):
        raise ValueError("Invalid Skill query cursor position")
    return position


def _utf8_prefix(data: bytes, max_bytes: int) -> tuple[str, bool]:
    if len(data) <= max_bytes:
        return data.decode("utf-8"), True
    prefix = data[:max_bytes]
    while prefix:
        try:
            return prefix.decode("utf-8"), False
        except UnicodeDecodeError as exc:
            prefix = prefix[: exc.start]
    return "", False


class SkillQueryService:
    """Deterministic read surface over one canonical SkillLibrary."""

    def __init__(self, library: SkillLibrary | None) -> None:
        self._library = library

    @property
    def library(self) -> SkillLibrary:
        if self._library is None:
            raise SkillNotFound("Skill library is not initialized")
        return self._library

    def capabilities(self) -> dict[str, Any]:
        return {
            "ok": True,
            "capability": "portable_agent_skills_query",
            "model_version": "skill.query.v1",
            "cursor_version": SKILL_QUERY_CURSOR_VERSION,
            "query_operations": [
                "capabilities",
                "list",
                "search",
                "get",
                "history",
                "resource",
            ],
            "default_limit": SKILL_QUERY_DEFAULT_LIMIT,
            "maximum_limit": SKILL_QUERY_MAX_LIMIT,
            "resource_default_chunk_bytes": SKILL_RESOURCE_DEFAULT_BYTES,
            "resource_max_chunk_bytes": SKILL_RESOURCE_MAX_BYTES,
            "default_discovery_scope": "current_enabled_only",
            "exact_historical_ref_retrieval": True,
            "executes_resources": False,
            "grants_permissions": False,
            "chooses_skill": False,
            "runs_reasoning": False,
            "library_initialized": self._library is not None,
        }

    def _current_enabled_rows(self) -> list[dict[str, Any]]:
        with self.library.connect() as conn:
            rows = conn.execute(
                """
                SELECT r.skill_name, r.skill_ref, r.package_hash, r.description,
                       r.created_at, s.state_version
                FROM skill_state AS s
                JOIN skill_revisions AS r
                  ON r.skill_name = s.skill_name
                 AND r.package_hash = s.current_package_hash
                WHERE s.enabled = 1 AND s.current_package_hash <> ''
                ORDER BY r.skill_name
                """
            ).fetchall()
        return [dict(row) for row in rows]

    @staticmethod
    def _provenance_summary(revision: dict[str, Any]) -> dict[str, Any]:
        sources = list(revision.get("sources") or [])
        kinds = sorted({str(source.get("source_kind") or "") for source in sources})
        return {
            "source_count": len(sources),
            "source_kinds": [kind for kind in kinds if kind],
        }

    def _source_summary(self, skill_ref: str) -> dict[str, Any]:
        return self._provenance_summary(self.library.get_revision(skill_ref))

    @staticmethod
    def _bounded_manifest(manifest: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int]:
        page: list[dict[str, Any]] = []
        encoded_bytes = 2  # []
        for raw_entry in manifest[:SKILL_GET_MANIFEST_MAX_ITEMS]:
            entry = dict(raw_entry)
            encoded = json.dumps(
                entry,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=True,
            ).encode("utf-8")
            next_bytes = encoded_bytes + len(encoded) + (1 if page else 0)
            if next_bytes > SKILL_GET_MANIFEST_MAX_BYTES:
                break
            page.append(entry)
            encoded_bytes = next_bytes
        return page, encoded_bytes

    def _discovery_projection(self, row: dict[str, Any]) -> dict[str, Any]:
        skill_ref = str(row["skill_ref"])
        return {
            "skill_ref": skill_ref,
            "name": str(row["skill_name"]),
            "description": str(row["description"]),
            "package_hash": str(row["package_hash"]),
            "current": True,
            "historical": False,
            "enabled": True,
            "state_version": int(row["state_version"]),
            "provenance": self._source_summary(skill_ref),
        }

    def list_skills(
        self,
        *,
        limit: int = SKILL_QUERY_DEFAULT_LIMIT,
        cursor: str = "",
    ) -> dict[str, Any]:
        bounded = _bounded_limit(limit)
        if self._library is None:
            if cursor:
                raise ValueError("Skill list cursor cannot target an uninitialized library")
            return {
                "ok": True,
                "items": [],
                "count": 0,
                "has_more": False,
                "next_cursor": "",
                "scope": "current_enabled_only",
            }
        after_name = ""
        if cursor:
            position = _decode_cursor(cursor, collection="list")
            if set(position) != {"after_name"}:
                raise ValueError("Invalid Skill list cursor position")
            after_name = position["after_name"]
            if not isinstance(after_name, str) or not after_name:
                raise ValueError("Invalid Skill list cursor position")
        rows = [
            row for row in self._current_enabled_rows()
            if str(row["skill_name"]) > after_name
        ]
        page = rows[:bounded]
        has_more = len(rows) > bounded
        next_cursor = ""
        if has_more and page:
            next_cursor = _encode_cursor(
                collection="list",
                position={"after_name": str(page[-1]["skill_name"])},
            )
        return {
            "ok": True,
            "items": [self._discovery_projection(row) for row in page],
            "count": len(page),
            "has_more": has_more,
            "next_cursor": next_cursor,
            "scope": "current_enabled_only",
        }

    @staticmethod
    def _search_rank(query: str, *, name: str, description: str) -> int | None:
        needle = query.casefold()
        folded_name = name.casefold()
        folded_description = description.casefold()
        if folded_name == needle:
            return 0
        if folded_name.startswith(needle):
            return 1
        if needle in folded_name:
            return 2
        if needle in folded_description:
            return 3
        return None

    def search(
        self,
        query: str,
        *,
        limit: int = SKILL_QUERY_DEFAULT_LIMIT,
        cursor: str = "",
    ) -> dict[str, Any]:
        text = str(query or "").strip()
        if not text or len(text) > 512:
            raise ValueError("query must be 1..512 characters")
        bounded = _bounded_limit(limit)
        if self._library is None:
            if cursor:
                raise ValueError("Skill search cursor cannot target an uninitialized library")
            return {
                "ok": True,
                "query": text,
                "items": [],
                "count": 0,
                "has_more": False,
                "next_cursor": "",
                "scope": "current_enabled_only",
                "ranking": "deterministic_name_description_v1",
            }
        query_hash = sha256(text.casefold().encode("utf-8")).hexdigest()
        after_rank = -1
        after_name = ""
        if cursor:
            position = _decode_cursor(cursor, collection="search")
            if set(position) != {"query_hash", "after_rank", "after_name"}:
                raise ValueError("Invalid Skill search cursor position")
            if position["query_hash"] != query_hash:
                raise ValueError("Skill search cursor query mismatch")
            after_rank = position["after_rank"]
            after_name = position["after_name"]
            if isinstance(after_rank, bool) or not isinstance(after_rank, int):
                raise ValueError("Invalid Skill search cursor position")
            if not isinstance(after_name, str):
                raise ValueError("Invalid Skill search cursor position")

        ranked: list[tuple[int, str, dict[str, Any]]] = []
        for row in self._current_enabled_rows():
            name = str(row["skill_name"])
            rank = self._search_rank(
                text, name=name, description=str(row["description"])
            )
            if rank is None:
                continue
            if after_rank >= 0 and (rank, name) <= (after_rank, after_name):
                continue
            ranked.append((rank, name, row))
        ranked.sort(key=lambda item: (item[0], item[1]))
        page = ranked[:bounded]
        has_more = len(ranked) > bounded
        next_cursor = ""
        if has_more and page:
            last_rank, last_name, _ = page[-1]
            next_cursor = _encode_cursor(
                collection="search",
                position={
                    "query_hash": query_hash,
                    "after_rank": last_rank,
                    "after_name": last_name,
                },
            )
        return {
            "ok": True,
            "query": text,
            "items": [self._discovery_projection(item[2]) for item in page],
            "count": len(page),
            "has_more": has_more,
            "next_cursor": next_cursor,
            "scope": "current_enabled_only",
            "ranking": "deterministic_name_description_v1",
        }

    def _resolve_get_ref(self, *, skill_ref: str = "", name: str = "") -> str:
        ref = str(skill_ref or "").strip()
        skill_name = str(name or "").strip()
        if bool(ref) == bool(skill_name):
            raise ValueError("Specify exactly one of skill_ref or name")
        if ref:
            return ref
        state = self.library.get_state(skill_name)
        current_ref = str(state.get("current_skill_ref") or "")
        if not current_ref or not bool(state.get("enabled")):
            raise SkillNotFound(skill_name)
        return current_ref

    def get(
        self,
        *,
        skill_ref: str = "",
        name: str = "",
    ) -> dict[str, Any]:
        resolved_ref = self._resolve_get_ref(skill_ref=skill_ref, name=name)
        revision = self.library.get_revision(resolved_ref)
        package_root = Path(str(revision["package_root"]))
        skill_md_bytes = (package_root / "SKILL.md").read_bytes()
        skill_md, complete = _utf8_prefix(skill_md_bytes, SKILL_GET_INLINE_TEXT_BYTES)
        manifest = list(revision.get("manifest") or [])
        manifest_page, manifest_projection_bytes = self._bounded_manifest(manifest)
        return {
            "ok": True,
            "skill_ref": str(revision["skill_ref"]),
            "name": str(revision["skill_name"]),
            "description": str(revision["description"]),
            "package_hash": str(revision["package_hash"]),
            "current": bool(revision["current"]),
            "historical": not bool(revision["current"]),
            "enabled": bool(revision["enabled"]),
            "state_version": int(revision["state_version"]),
            "created_at": str(revision["created_at"]),
            "parent_skill_ref": str(revision["parent_skill_ref"]),
            "provenance": self._provenance_summary(revision),
            "skill_md": skill_md,
            "skill_md_complete": complete,
            "skill_md_size_bytes": len(skill_md_bytes),
            "skill_md_sha256": sha256(skill_md_bytes).hexdigest(),
            "manifest": manifest_page,
            "manifest_count": len(manifest),
            "manifest_truncated": len(manifest_page) < len(manifest),
            "manifest_projection_bytes": manifest_projection_bytes,
            "manifest_projection_max_bytes": SKILL_GET_MANIFEST_MAX_BYTES,
            "package_root": str(package_root),
            "locator_is_execution_authority": False,
            "resource_retrieval": {
                "gateway": "skill_query",
                "operation": "resource",
                "skill_ref": str(revision["skill_ref"]),
            },
        }

    def history(
        self,
        skill_name: str,
        *,
        limit: int = SKILL_QUERY_DEFAULT_LIMIT,
        cursor: str = "",
    ) -> dict[str, Any]:
        name = str(skill_name or "").strip()
        if not name or len(name) > 64:
            raise ValueError("skill_name must be 1..64 characters")
        bounded = _bounded_limit(limit)
        after_created_at = ""
        after_hash = ""
        if cursor:
            position = _decode_cursor(cursor, collection="history")
            if set(position) != {"skill_name", "after_created_at", "after_hash"}:
                raise ValueError("Invalid Skill history cursor position")
            if position["skill_name"] != name:
                raise ValueError("Skill history cursor name mismatch")
            after_created_at = position["after_created_at"]
            after_hash = position["after_hash"]
            if not isinstance(after_created_at, str) or not isinstance(after_hash, str):
                raise ValueError("Invalid Skill history cursor position")
        rows = self.library.history(name)
        if not rows:
            raise SkillNotFound(name)
        filtered = [
            row for row in rows
            if not after_created_at
            or (str(row["created_at"]), str(row["package_hash"]))
            > (after_created_at, after_hash)
        ]
        page = filtered[:bounded]
        has_more = len(filtered) > bounded
        next_cursor = ""
        if has_more and page:
            last = page[-1]
            next_cursor = _encode_cursor(
                collection="history",
                position={
                    "skill_name": name,
                    "after_created_at": str(last["created_at"]),
                    "after_hash": str(last["package_hash"]),
                },
            )
        current_ref = str(self.library.get_state(name).get("current_skill_ref") or "")
        items = []
        for row in page:
            ref = str(row["skill_ref"])
            revision = self.library.get_revision(ref)
            items.append(
                {
                    "skill_ref": ref,
                    "name": name,
                    "description": str(row["description"]),
                    "package_hash": str(row["package_hash"]),
                    "parent_skill_ref": str(row["parent_skill_ref"]),
                    "created_at": str(row["created_at"]),
                    "current": ref == current_ref,
                    "historical": ref != current_ref,
                    "provenance": {
                        "source_count": len(revision.get("sources") or []),
                        "source_kinds": sorted(
                            {
                                str(source.get("source_kind") or "")
                                for source in revision.get("sources") or []
                                if str(source.get("source_kind") or "")
                            }
                        ),
                    },
                }
            )
        return {
            "ok": True,
            "skill_name": name,
            "items": items,
            "count": len(items),
            "total_count": len(rows),
            "has_more": has_more,
            "next_cursor": next_cursor,
        }

    def resource(
        self,
        skill_ref: str,
        relative_path: str,
        *,
        max_bytes: int = SKILL_RESOURCE_DEFAULT_BYTES,
        cursor: str = "",
    ) -> dict[str, Any]:
        if isinstance(max_bytes, bool) or not isinstance(max_bytes, int):
            raise ValueError("max_bytes must be an integer")
        if max_bytes < 1 or max_bytes > SKILL_RESOURCE_MAX_BYTES:
            raise ValueError(
                f"max_bytes must be between 1 and {SKILL_RESOURCE_MAX_BYTES}"
            )
        path = normalize_package_path(relative_path)
        revision = self.library.get_revision(skill_ref)
        manifest = {
            str(entry["path"]): entry for entry in revision.get("manifest") or []
        }
        entry = manifest.get(path)
        if entry is None:
            raise SkillNotFound(f"{skill_ref}:{path}")
        offset = 0
        if cursor:
            position = _decode_cursor(cursor, collection="resource")
            if set(position) != {"skill_ref", "relative_path", "offset"}:
                raise ValueError("Invalid Skill resource cursor position")
            if position["skill_ref"] != skill_ref:
                raise ValueError("Skill resource cursor revision mismatch")
            if position["relative_path"] != path:
                raise ValueError("Skill resource cursor path mismatch")
            offset = position["offset"]
            if isinstance(offset, bool) or not isinstance(offset, int) or offset < 0:
                raise ValueError("Invalid Skill resource cursor position")
        package_root = Path(str(revision["package_root"]))
        resource_path = package_root.joinpath(*Path(path).parts)
        data = resource_path.read_bytes()
        expected_size = int(entry["size_bytes"])
        expected_sha = str(entry["sha256"])
        if len(data) != expected_size or sha256(data).hexdigest() != expected_sha:
            raise ValueError("package_integrity_mismatch")
        if offset > len(data):
            raise ValueError("Skill resource cursor offset is beyond end of resource")
        chunk = data[offset : offset + max_bytes]
        next_offset = offset + len(chunk)
        complete = next_offset >= len(data)
        next_cursor = ""
        if not complete:
            next_cursor = _encode_cursor(
                collection="resource",
                position={
                    "skill_ref": skill_ref,
                    "relative_path": path,
                    "offset": next_offset,
                },
            )
        result: dict[str, Any] = {
            "ok": True,
            "skill_ref": skill_ref,
            "name": str(revision["skill_name"]),
            "package_hash": str(revision["package_hash"]),
            "relative_path": path,
            "size_bytes": len(data),
            "sha256": expected_sha,
            "offset": offset,
            "chunk_size_bytes": len(chunk),
            "complete": complete,
            "has_more": not complete,
            "next_cursor": next_cursor,
            "package_root": str(package_root),
            "resource_path": str(resource_path),
            "locator_is_execution_authority": False,
            "executes_resource": False,
        }
        try:
            text = chunk.decode("utf-8")
        except UnicodeDecodeError:
            result["encoding"] = "base64"
            result["content_base64"] = base64.b64encode(chunk).decode("ascii")
        else:
            result["encoding"] = "utf-8"
            result["content_text"] = text
        return result
