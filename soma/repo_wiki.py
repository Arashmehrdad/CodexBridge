from __future__ import annotations

import ast
import hashlib
import json
import os
import re
import subprocess
from collections import Counter
from contextlib import suppress
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Iterable
from uuid import uuid4

from .return_loop.atomic_writer import atomic_write_text
from .tool_owned_paths import is_tool_owned_path

WIKI_VERSION = 2
WIKI_SCHEMA_VERSION = 1
MAX_SOURCE_FILES = 2_000
MAX_SOURCE_FILE_BYTES = 250_000
MAX_WIKI_READ_BYTES = 150_000
AI_WIKI_PAGES = (
    "index.md",
    "overview.md",
    "architecture.md",
    "modules.md",
    "validation.md",
)
GENERATION_MACHINE_FILES = (
    "machine/manifest.json",
    "machine/source-index.json",
)
_GENERATION_ID_RE = re.compile(r"^\d{8}T\d{12}Z-[0-9a-f]{7}-[0-9a-f]{7}$")

_BLOCKED_DIRS = {
    ".git",
    ".pulse-chrome-profile",
    ".venv",
    "venv",
    "node_modules",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".tox",
    ".nox",
    ".idea",
    ".vscode",
    "dist",
    "build",
    "coverage",
    "htmlcov",
    "runs",
    ".codex-pytest-temp",
    "generated",
    "media",
    "artifacts",
    "models",
    "secrets",
    "credentials",
}
_BLOCKED_FILES = {
    ".env",
    ".env.local",
    ".env.production",
    "id_rsa",
    "id_ed25519",
}
_BLOCKED_SUFFIXES = {
    ".pem",
    ".key",
    ".p12",
    ".pfx",
    ".pyc",
    ".pyo",
    ".db",
    ".sqlite",
    ".sqlite3",
}
_TEXT_SUFFIXES = {
    ".py",
    ".pyi",
    ".js",
    ".jsx",
    ".ts",
    ".tsx",
    ".json",
    ".toml",
    ".yaml",
    ".yml",
    ".md",
    ".rst",
    ".txt",
    ".ini",
    ".cfg",
    ".conf",
    ".sh",
    ".ps1",
    ".bat",
    ".cmd",
    ".sql",
    ".html",
    ".css",
    ".scss",
    ".go",
    ".rs",
    ".java",
    ".kt",
    ".cs",
    ".cpp",
    ".c",
    ".h",
}
_IMPORT_RE = re.compile(
    r"^\s*(?:from\s+([\w.]+)\s+import|import\s+([\w.]+))", re.MULTILINE
)
_JS_IMPORT_RE = re.compile(r"(?:from\s+|require\s*\(\s*)['\"]([^'\"]+)['\"]")
_JS_SYMBOL_RE = re.compile(
    r"^\s*(?:export\s+)?(?:default\s+)?(?:async\s+)?(?:function|class)\s+([A-Za-z_$][\w$]*)",
    re.MULTILINE,
)


def _normalize_search_text(value: str) -> str:
    """Normalize punctuation and spacing for deterministic wiki search."""
    return " ".join(re.findall(r"[^\W_]+", value.casefold(), flags=re.UNICODE))


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _safe_relative_page(page: str) -> PurePosixPath:
    normalized = page.replace("\\", "/").strip()
    candidate = PurePosixPath(normalized)
    if not normalized or candidate.is_absolute() or ".." in candidate.parts:
        raise ValueError(f"Invalid wiki page: {page!r}")
    if candidate.suffix.lower() not in {".md", ".json"}:
        raise ValueError("Wiki pages must be Markdown or JSON")
    return candidate


def mark_repo_wiki_stale(
    repo_root: Path, repo_name: str, *, reason: str
) -> dict[str, Any]:
    """Mark a repository wiki stale without performing a refresh."""
    return RepoWikiService(repo_root, repo_name).mark_stale(reason=reason)


class RepoWikiService:
    """Generate and query a deterministic, repository-local knowledge wiki."""

    def __init__(
        self,
        repo_root: Path,
        repo_name: str,
        *,
        wiki_exclusions: Iterable[str] = (),
    ):
        self.repo_root = Path(repo_root).resolve()
        self.repo_name = repo_name
        self.wiki_root = self.repo_root / ".soma" / "wiki"
        self.generations_root = self.wiki_root / "generations"
        self.current_path = self.wiki_root / "CURRENT.json"
        # Kept as a public compatibility path for callers that inspect the
        # legacy layout. New generations never write to this path.
        self.manifest_path = self.wiki_root / "manifest.json"
        self.refresh_lock_path = self.wiki_root / ".refresh.lock"
        self.wiki_exclusions = {
            item.replace("\\", "/").strip("/") for item in wiki_exclusions
        }

    def refresh(self, *, force: bool = False) -> dict[str, Any]:
        operation_id = f"wiki_{uuid4().hex}"
        lock_result = self._try_acquire_refresh_lock(operation_id)
        if lock_result is not None:
            return lock_result
        try:
            return self._refresh_locked(operation_id=operation_id, force=force)
        except Exception as exc:
            return self._refresh_failure(str(exc), operation_id=operation_id)
        finally:
            with suppress(OSError):
                self.refresh_lock_path.unlink()

    def _refresh_locked(self, *, operation_id: str, force: bool) -> dict[str, Any]:
        current_before = self._read_current_json()
        previous, legacy = self._load_previous_snapshot(current_before)
        captured_source_generation = self._source_generation(current_before)
        captured_head = self._git_value(["rev-parse", "HEAD"])
        captured_branch = self._git_value(["branch", "--show-current"])
        captured_tree = self._git_working_tree_fingerprint()
        current_candidates = self._git_list_source_candidates()
        config_fingerprint = self._index_configuration_fingerprint()
        previous_fingerprint = self._manifest_fingerprint(previous)
        incremental = False
        changed_candidates: set[str] = set()

        if not force and self._incremental_manifest_is_usable(
            previous, captured_head, config_fingerprint
        ) and current_candidates is not None:
            previous_candidates = set(previous.get("candidate_files", []))
            changed_candidates.update(previous_candidates ^ set(current_candidates))
            if captured_head != previous.get("indexed_head"):
                history_changes = self._git_changed_paths(previous["indexed_head"])
                if history_changes is None:
                    current_candidates = None
                else:
                    changed_candidates.update(history_changes)
            if current_candidates is not None:
                working_changes = self._git_working_tree_changed_paths()
                if working_changes is None:
                    current_candidates = None
                else:
                    changed_candidates.update(working_changes)

        if (
            not force
            and current_candidates is not None
            and self._incremental_manifest_is_usable(
                previous, captured_head, config_fingerprint
            )
        ):
            source_files, truncated = self._scan_source_files_incremental(
                current_candidates, previous, changed_candidates
            )
            incremental = True
        else:
            source_files, truncated = self._scan_source_files()

        fingerprint = {item["path"]: item["sha256"] for item in source_files}
        changed = sorted(
            path
            for path in set(fingerprint) | set(previous_fingerprint)
            if fingerprint.get(path) != previous_fingerprint.get(path)
        )
        if (
            not force
            and current_before
            and current_before.get("generation_id")
            and not current_before.get("stale", False)
            and fingerprint == previous_fingerprint
            and not truncated
            and self._source_snapshot_is_current(captured_tree, source_files)
        ):
            return self._result(
                ok=True,
                status="unchanged",
                current=current_before,
                source_file_count=len(source_files),
                changed_source_files=[],
                scan_truncated=False,
                incremental=incremental,
                operation_id=operation_id,
            )

        analysis = self._analyse(
            source_files,
            previous_analysis=previous.get("analysis"),
            changed_paths=set(changed),
        )
        snapshot_hash = self._snapshot_hash(source_files)
        generation_id = self._generation_id(captured_head, snapshot_hash)
        source_index = self._build_source_index(source_files, analysis)

        def freshness_state() -> tuple[dict[str, Any], bool, str, str | None, int]:
            current_after = self._read_current_json()
            source_snapshot_current = self._source_snapshot_is_current(
                captured_tree, source_files
            )
            source_generation_current = self._source_generation(current_after)
            state_changed = source_generation_current != captured_source_generation
            stale = state_changed or not source_snapshot_current
            stale_reason = ""
            stale_since = None
            if stale:
                stale_reason = (
                    str(current_after.get("stale_reason", ""))
                    if state_changed
                    else "source changed during wiki refresh"
                ) or "source changed during wiki refresh"
                stale_since = current_after.get("stale_since") or _utc_now()
            return (
                current_after,
                stale,
                stale_reason,
                stale_since,
                max(captured_source_generation, source_generation_current),
            )

        _, stale, stale_reason, stale_since, published_source_generation = (
            freshness_state()
        )
        pages = {
            "overview.md": self._render_overview(
                source_files,
                analysis,
                truncated,
                generation_id=generation_id,
                indexed_branch=captured_branch,
                indexed_head=captured_head,
                source_generation=published_source_generation,
                indexed_source_generation=captured_source_generation,
                stale=stale,
                stale_reason=stale_reason,
            ),
            "architecture.md": self._render_architecture(analysis),
            "modules.md": self._render_modules(analysis),
            "validation.md": self._render_validation(source_files, analysis),
        }
        pages["index.md"] = self._render_index(
            generation_id=generation_id,
            indexed_branch=captured_branch,
            indexed_head=captured_head,
            source_file_count=len(source_files),
            analysis=analysis,
            stale=stale,
            stale_reason=stale_reason,
        )

        # Rendering itself can be long enough for a source write to happen.
        # Re-check before publication and update the freshness fields in the
        # immutable pages if the captured snapshot is no longer current.
        _, final_stale, final_stale_reason, final_stale_since, final_source_generation = (
            freshness_state()
        )
        if (
            final_stale != stale
            or final_stale_reason != stale_reason
            or final_source_generation != published_source_generation
        ):
            stale = final_stale
            stale_reason = final_stale_reason
            stale_since = final_stale_since
            published_source_generation = final_source_generation
            pages["overview.md"] = self._render_overview(
                source_files,
                analysis,
                truncated,
                generation_id=generation_id,
                indexed_branch=captured_branch,
                indexed_head=captured_head,
                source_generation=published_source_generation,
                indexed_source_generation=captured_source_generation,
                stale=stale,
                stale_reason=stale_reason,
            )
            pages["index.md"] = self._render_index(
                generation_id=generation_id,
                indexed_branch=captured_branch,
                indexed_head=captured_head,
                source_file_count=len(source_files),
                analysis=analysis,
                stale=stale,
                stale_reason=stale_reason,
            )

        generation_dir = self.generations_root / generation_id
        generation_dir.mkdir(parents=True, exist_ok=False)
        for relative, content in pages.items():
            atomic_write_text(generation_dir / relative, content)
        atomic_write_text(
            generation_dir / "machine" / "source-index.json",
            json.dumps(source_index, indent=2, sort_keys=True) + "\n",
        )

        manifest = {
            "schema_version": WIKI_SCHEMA_VERSION,
            "version": WIKI_VERSION,
            "repo_name": self.repo_name,
            "generation_id": generation_id,
            "indexed_head": captured_head,
            "indexed_branch": captured_branch,
            "working_tree_fingerprint": snapshot_hash,
            "generated_at": _utc_now(),
            "source_file_count": len(source_files),
            "scan_truncated": truncated,
            "stale": stale,
            "stale_reason": stale_reason,
            "stale_since": stale_since,
            "source_generation": published_source_generation,
            "indexed_source_generation": captured_source_generation,
            "index_configuration_fingerprint": config_fingerprint,
            "candidate_files": sorted(
                current_candidates or [item["path"] for item in source_files]
            ),
            "pages": self._file_metadata_map(
                generation_dir, tuple(pages), include_machine=False
            ),
            "source_index_path": "machine/source-index.json",
            # These fields retain the prior incremental analyser cache in the
            # generation manifest while the AI-facing contract stays Markdown.
            "analysis": analysis,
            "source_files": source_files,
        }
        manifest_path = generation_dir / "machine" / "manifest.json"
        atomic_write_text(
            manifest_path, json.dumps(manifest, indent=2, sort_keys=True) + "\n"
        )
        self._verify_generation(generation_dir, manifest)
        manifest_bytes = manifest_path.read_bytes()
        current = {
            "schema_version": WIKI_SCHEMA_VERSION,
            "generation_id": generation_id,
            "manifest_sha256": _sha256_bytes(manifest_bytes),
            "source_generation": published_source_generation,
            "indexed_source_generation": captured_source_generation,
            "stale": stale,
            "stale_reason": stale_reason,
            "stale_since": stale_since,
            "updated_at": _utc_now(),
            "repo_name": self.repo_name,
            "indexed_head": captured_head,
            "indexed_branch": captured_branch,
            "working_tree_fingerprint": snapshot_hash,
        }
        self._publish_current(current)
        return self._result(
            ok=True,
            status="migrated" if legacy else ("generated" if not previous else "refreshed"),
            current=current,
            source_file_count=len(source_files),
            changed_source_files=changed,
            scan_truncated=truncated,
            incremental=incremental,
            operation_id=operation_id,
        )

    def mark_stale(self, *, reason: str) -> dict[str, Any]:
        """Mark indexed knowledge stale without scanning or regenerating pages."""
        current = self._read_current_json()
        if not current.get("generation_id"):
            return {
                "ok": True,
                "repo_name": self.repo_name,
                "status": "no_generation",
                "generation_id": "",
                "stale": True,
                "source_generation": 0,
                "error": "",
            }
        now = _utc_now()
        current["source_generation"] = self._source_generation(current) + 1
        current["stale"] = True
        current["stale_since"] = current.get("stale_since") or now
        current["stale_reason"] = reason[:200]
        current["updated_at"] = now
        self._publish_current(current)
        return {
            "ok": True,
            "repo_name": self.repo_name,
            "status": "stale",
            "generation_id": current.get("generation_id", ""),
            "stale": True,
            "stale_since": current["stale_since"],
            "stale_reason": current["stale_reason"],
            "source_generation": current["source_generation"],
            "error": "",
        }

    def read_page(self, page: str = "overview.md") -> dict[str, Any]:
        relative = _safe_relative_page(page)
        snapshot = self._resolve_snapshot()
        path = snapshot["root"] / Path(*relative.parts)
        try:
            path.relative_to(snapshot["root"])
        except ValueError as exc:
            raise ValueError("Wiki page resolves outside the selected wiki snapshot") from exc
        if not path.is_file():
            raise FileNotFoundError(f"Wiki page not found: {relative.as_posix()}")
        data = path.read_bytes()
        truncated = len(data) > MAX_WIKI_READ_BYTES
        content = data[:MAX_WIKI_READ_BYTES].decode("utf-8", errors="replace")
        if truncated:
            content += "\n[truncated]\n"
        return {
            "ok": True,
            "repo_name": self.repo_name,
            "page": relative.as_posix(),
            "content": content,
            "size_bytes": len(data),
            "truncated": truncated,
            "generation_id": snapshot.get("generation_id", ""),
            "stale": snapshot.get("stale", False),
            "indexed_head": snapshot.get("indexed_head", ""),
            "indexed_branch": snapshot.get("indexed_branch", ""),
            "source_generation": snapshot.get("source_generation", 0),
            "indexed_source_generation": snapshot.get("indexed_source_generation", 0),
            "error": "",
        }

    def search(self, query: str, *, limit: int = 20) -> list[dict[str, Any]]:
        return self.search_with_metadata(query, limit=limit)["hits"]

    def search_with_metadata(self, query: str, *, limit: int = 20) -> dict[str, Any]:
        raw_query = query.strip()
        needle = _normalize_search_text(raw_query)
        if not needle:
            raise ValueError("query must not be empty")
        hits: list[dict[str, Any]] = []
        maximum = max(1, min(limit, 100))
        try:
            snapshot = self._resolve_snapshot()
        except FileNotFoundError:
            return {
                "hits": hits,
                "generation_id": "",
                "stale": False,
                "indexed_head": "",
                "indexed_branch": "",
                "source_generation": 0,
                "indexed_source_generation": 0,
            }
        if not snapshot:
            return {
                "hits": hits,
                "generation_id": "",
                "stale": False,
                "indexed_head": "",
                "indexed_branch": "",
                "source_generation": 0,
                "indexed_source_generation": 0,
            }
        for page in AI_WIKI_PAGES:
            path = snapshot["root"] / page
            if not path.is_file():
                continue
            for line_number, line in enumerate(
                path.read_text(encoding="utf-8", errors="replace").splitlines(), 1
            ):
                if needle in _normalize_search_text(line):
                    hits.append(
                        {
                            "source": "wiki",
                            "page": page,
                            "line": line_number,
                            "snippet": line.strip()[:500],
                        }
                    )
                    if len(hits) >= maximum:
                        return {
                            "hits": hits,
                            "generation_id": snapshot.get("generation_id", ""),
                            "stale": snapshot.get("stale", False),
                            "indexed_head": snapshot.get("indexed_head", ""),
                            "indexed_branch": snapshot.get("indexed_branch", ""),
                            "source_generation": snapshot.get("source_generation", 0),
                            "indexed_source_generation": snapshot.get(
                                "indexed_source_generation", 0
                            ),
                        }
        return {
            "hits": hits,
            "generation_id": snapshot.get("generation_id", ""),
            "stale": snapshot.get("stale", False),
            "indexed_head": snapshot.get("indexed_head", ""),
            "indexed_branch": snapshot.get("indexed_branch", ""),
            "source_generation": snapshot.get("source_generation", 0),
            "indexed_source_generation": snapshot.get("indexed_source_generation", 0),
        }

    def _try_acquire_refresh_lock(self, operation_id: str) -> dict[str, Any] | None:
        self.wiki_root.mkdir(parents=True, exist_ok=True)
        payload = {
            "operation_id": operation_id,
            "pid": os.getpid(),
            "started_at": _utc_now(),
        }
        try:
            fd = os.open(
                self.refresh_lock_path,
                os.O_CREAT | os.O_EXCL | os.O_WRONLY,
            )
        except FileExistsError:
            active = {}
            with suppress(OSError, json.JSONDecodeError):
                active = json.loads(self.refresh_lock_path.read_text(encoding="utf-8"))
            return self._result(
                ok=False,
                status="wiki_refresh_in_progress",
                current=self._read_current_json(),
                operation_id=str(active.get("operation_id", "")),
                error="A wiki refresh is already running for this repository.",
            )
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, sort_keys=True)
            handle.flush()
            os.fsync(handle.fileno())
        return None

    def _refresh_failure(self, error: str, *, operation_id: str) -> dict[str, Any]:
        return self._result(
            ok=False,
            status="failed",
            current=self._read_current_json(),
            operation_id=operation_id,
            error=error[:1000],
        )

    def _result(self, *, ok: bool, status: str, current: dict[str, Any], **kwargs) -> dict[str, Any]:
        result = {
            "ok": ok,
            "repo_name": self.repo_name,
            "status": status,
            "wiki_root": ".soma/wiki",
            "pages": list(AI_WIKI_PAGES),
            "source_file_count": int(kwargs.pop("source_file_count", 0)),
            "changed_source_files": list(kwargs.pop("changed_source_files", [])),
            "scan_truncated": bool(kwargs.pop("scan_truncated", False)),
            "stale": bool(current.get("stale", False)),
            "generation_id": str(current.get("generation_id", "")),
            "indexed_head": str(current.get("indexed_head", "")),
            "indexed_branch": str(current.get("indexed_branch", "")),
            "source_generation": int(current.get("source_generation", 0) or 0),
            "indexed_source_generation": int(
                current.get("indexed_source_generation", 0) or 0
            ),
            "incremental": bool(kwargs.pop("incremental", False)),
            "refresh_operation_id": str(kwargs.pop("operation_id", "")),
            "error": str(kwargs.pop("error", "")),
        }
        result.update(kwargs)
        return result

    def _read_current_json(self) -> dict[str, Any]:
        if not self.current_path.is_file():
            return {}
        try:
            raw = json.loads(self.current_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        return raw if isinstance(raw, dict) else {}

    @staticmethod
    def _source_generation(current: dict[str, Any]) -> int:
        try:
            return max(0, int(current.get("source_generation", 0)))
        except (TypeError, ValueError):
            return 0

    def _load_previous_snapshot(
        self, current: dict[str, Any]
    ) -> tuple[dict[str, Any], bool]:
        generation_id = str(current.get("generation_id", ""))
        if generation_id:
            try:
                snapshot = self._resolve_current_snapshot(current)
            except ValueError:
                snapshot = None
            if snapshot:
                manifest = dict(snapshot["manifest"])
                source_index_path = snapshot["root"] / "machine" / "source-index.json"
                if source_index_path.is_file():
                    with suppress(OSError, json.JSONDecodeError):
                        source_index = json.loads(
                            source_index_path.read_text(encoding="utf-8")
                        )
                        if isinstance(source_index, dict):
                            manifest = self._merge_source_index_cache(
                                manifest, source_index
                            )
                return manifest, False
        legacy = self._load_legacy_manifest()
        return legacy, bool(legacy)

    def _load_legacy_manifest(self) -> dict[str, Any]:
        if not self.manifest_path.is_file():
            return {}
        try:
            raw = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        return raw if isinstance(raw, dict) else {}

    def _load_manifest(self) -> dict[str, Any]:
        """Compatibility accessor for callers that used the old flat manifest."""
        return self._load_previous_snapshot(self._read_current_json())[0]

    def _resolve_snapshot(self) -> dict[str, Any]:
        current_exists = self.current_path.is_file()
        current = self._read_current_json()
        if current_exists:
            try:
                return self._resolve_current_snapshot(current)
            except ValueError:
                raise
        legacy = self._legacy_snapshot()
        if legacy:
            return legacy
        raise FileNotFoundError("Repository wiki has not been generated")

    def _resolve_current_snapshot(self, current: dict[str, Any]) -> dict[str, Any]:
        generation_id = str(current.get("generation_id", ""))
        if not _GENERATION_ID_RE.fullmatch(generation_id):
            raise ValueError("Invalid CURRENT.json generation_id")
        generation_root = (self.generations_root / generation_id).resolve()
        try:
            generation_root.relative_to(self.generations_root.resolve())
        except ValueError as exc:
            raise ValueError("CURRENT.json generation escapes the wiki root") from exc
        manifest_path = generation_root / "machine" / "manifest.json"
        source_index_path = generation_root / "machine" / "source-index.json"
        if not manifest_path.is_file() or not source_index_path.is_file():
            raise ValueError("CURRENT.json references a missing generation")
        try:
            manifest_bytes = manifest_path.read_bytes()
            manifest = json.loads(manifest_bytes.decode("utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("Selected wiki generation manifest is invalid") from exc
        if not isinstance(manifest, dict) or manifest.get("generation_id") != generation_id:
            raise ValueError("Selected wiki generation manifest does not match CURRENT.json")
        if current.get("manifest_sha256") != _sha256_bytes(manifest_bytes):
            raise ValueError("CURRENT.json manifest_sha256 does not match the generation")
        pages = manifest.get("pages")
        if not isinstance(pages, dict):
            raise ValueError("Selected wiki generation has invalid page metadata")
        for page in AI_WIKI_PAGES:
            path = generation_root / page
            metadata = pages.get(page)
            if not path.is_file() or not isinstance(metadata, dict):
                raise ValueError(f"Selected wiki generation is missing {page}")
            data = path.read_bytes()
            if metadata.get("sha256") != _sha256_bytes(data) or metadata.get(
                "size_bytes"
            ) != len(data):
                raise ValueError(f"Selected wiki generation has invalid {page}")
        return {
            "root": generation_root,
            "manifest": manifest,
            "generation_id": generation_id,
            "stale": bool(current.get("stale", False)),
            "source_generation": self._source_generation(current),
            "indexed_source_generation": int(
                current.get("indexed_source_generation", 0) or 0
            ),
            "indexed_head": str(current.get("indexed_head", manifest.get("indexed_head", ""))),
            "indexed_branch": str(
                current.get("indexed_branch", manifest.get("indexed_branch", ""))
            ),
        }

    def _legacy_snapshot(self) -> dict[str, Any] | None:
        if not all((self.wiki_root / page).is_file() for page in AI_WIKI_PAGES[1:]):
            return None
        manifest = self._load_legacy_manifest()
        return {
            "root": self.wiki_root,
            "manifest": manifest,
            "generation_id": "",
            "stale": bool(manifest.get("stale", False)),
            "source_generation": int(manifest.get("source_generation", 0) or 0),
            "indexed_source_generation": int(
                manifest.get("indexed_source_generation", 0) or 0
            ),
            "indexed_head": str(manifest.get("indexed_head", "")),
            "indexed_branch": str(manifest.get("indexed_branch", "")),
        }

    @staticmethod
    def _merge_source_index_cache(
        manifest: dict[str, Any], source_index: dict[str, Any]
    ) -> dict[str, Any]:
        source_files = []
        modules = []
        for path, item in source_index.items():
            if not isinstance(item, dict):
                continue
            record = {"path": path}
            for key in ("sha256", "size_bytes"):
                if key in item:
                    record[key] = item[key]
            source_files.append(record)
            if item.get("module"):
                modules.append(
                    {
                        "path": path,
                        **{
                            key: item[key]
                        for key in (
                            "module",
                            "kind",
                            "summary",
                            "classes",
                            "functions",
                            "imports",
                        )
                        if key in item
                        },
                    }
                )
        merged = dict(manifest)
        if source_files:
            merged["source_files"] = sorted(source_files, key=lambda item: item["path"])
        if modules:
            analysis = dict(merged.get("analysis") or {})
            analysis["modules"] = sorted(modules, key=lambda item: item["path"])
            merged["analysis"] = analysis
        return merged

    def _publish_current(self, current: dict[str, Any]) -> None:
        self.wiki_root.mkdir(parents=True, exist_ok=True)
        data = (json.dumps(current, indent=2, sort_keys=True) + "\n").encode("utf-8")
        temp_path = self.wiki_root / "CURRENT.json.tmp"
        with temp_path.open("wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, self.current_path)

    @staticmethod
    def _file_metadata_map(
        root: Path, pages: Iterable[str], *, include_machine: bool
    ) -> dict[str, dict[str, Any]]:
        names = list(pages)
        if include_machine:
            names.extend(GENERATION_MACHINE_FILES)
        result = {}
        for relative in names:
            data = (root / relative).read_bytes()
            result[relative] = {
                "sha256": _sha256_bytes(data),
                "size_bytes": len(data),
            }
        return result

    def _verify_generation(self, root: Path, manifest: dict[str, Any]) -> None:
        required = [*AI_WIKI_PAGES, *GENERATION_MACHINE_FILES]
        if not all((root / path).is_file() for path in required):
            raise ValueError("Wiki generation is incomplete")
        for page, metadata in manifest["pages"].items():
            data = (root / page).read_bytes()
            if metadata["sha256"] != _sha256_bytes(data) or metadata["size_bytes"] != len(data):
                raise ValueError(f"Wiki generation hash verification failed for {page}")

    @staticmethod
    def _snapshot_hash(source_files: list[dict[str, Any]]) -> str:
        payload = "\n".join(
            f"{item['path']}\0{item['sha256']}\0{item['size_bytes']}"
            for item in sorted(source_files, key=lambda value: value["path"])
        )
        return _sha256_bytes(payload.encode("utf-8"))

    @staticmethod
    def _generation_id(head: str, snapshot_hash: str) -> str:
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        return f"{timestamp}-{(head or '0000000')[:7]}-{snapshot_hash[:7]}"

    def _build_source_index(
        self, source_files: list[dict[str, Any]], analysis: dict[str, Any]
    ) -> dict[str, dict[str, Any]]:
        modules = {
            item.get("path"): item
            for item in analysis.get("modules", [])
            if isinstance(item, dict) and item.get("path")
        }
        result = {}
        for record in source_files:
            path = record["path"]
            entry = {
                "sha256": record["sha256"],
                "size_bytes": record["size_bytes"],
                "language": self._language_for_path(path),
            }
            module = modules.get(path)
            if module:
                entry.update(
                    {
                        "module": module.get("module", ""),
                        "kind": module.get("kind", ""),
                        "summary": module.get("summary", ""),
                        "classes": module.get("classes", []),
                        "functions": module.get("functions", []),
                        "symbols": [
                            *module.get("classes", []),
                            *module.get("functions", []),
                        ],
                        "imports": module.get("imports", []),
                    }
                )
            result[path] = entry
        return result

    def _git_working_tree_fingerprint(self) -> str:
        try:
            result = subprocess.run(
                ["git", "status", "--porcelain=v1", "-z", "--untracked-files=all"],
                cwd=self.repo_root,
                capture_output=True,
                text=False,
                timeout=5.0,
            )
        except (OSError, subprocess.TimeoutExpired):
            return ""
        if result.returncode != 0:
            return ""
        entries = []
        for raw in result.stdout.split(b"\0"):
            if not raw:
                continue
            value = raw.decode("utf-8", errors="replace")
            path = value[3:] if len(value) >= 3 else ""
            if path.startswith(".soma/wiki/"):
                continue
            entries.append(value)
        return _sha256_bytes("\0".join(sorted(entries)).encode("utf-8"))

    def _source_snapshot_is_current(
        self, captured_tree: str, source_files: list[dict[str, Any]]
    ) -> bool:
        if self._git_working_tree_fingerprint() != captured_tree:
            return False
        current_files, truncated = self._scan_source_files()
        return not truncated and self._snapshot_hash(current_files) == self._snapshot_hash(
            source_files
        )

    def _git_value(self, args: list[str]) -> str:
        try:
            result = subprocess.run(
                ["git", *args],
                cwd=self.repo_root,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=5.0,
            )
        except (OSError, subprocess.TimeoutExpired):
            return ""
        return result.stdout.strip() if result.returncode == 0 else ""

    def _index_configuration_fingerprint(self) -> str:
        payload = {
            "blocked_dirs": sorted(_BLOCKED_DIRS),
            "blocked_files": sorted(_BLOCKED_FILES),
            "blocked_suffixes": sorted(_BLOCKED_SUFFIXES),
            "text_suffixes": sorted(_TEXT_SUFFIXES),
            "wiki_exclusions": sorted(self.wiki_exclusions),
            "max_source_files": MAX_SOURCE_FILES,
            "max_source_file_bytes": MAX_SOURCE_FILE_BYTES,
        }
        return _sha256_bytes(json.dumps(payload, sort_keys=True).encode("utf-8"))

    @staticmethod
    def _manifest_fingerprint(manifest: dict[str, Any]) -> dict[str, str]:
        return {
            item.get("path", ""): item.get("sha256", "")
            for item in manifest.get("source_files", [])
            if isinstance(item, dict) and item.get("path")
        }

    def _incremental_manifest_is_usable(
        self,
        manifest: dict[str, Any],
        current_head: str,
        config_fingerprint: str,
    ) -> bool:
        return bool(
            manifest
            and manifest.get("version") == WIKI_VERSION
            and (
                (current_head and manifest.get("indexed_head"))
                or (not current_head and not manifest.get("indexed_head"))
            )
            and manifest.get("index_configuration_fingerprint")
            == config_fingerprint
            and not manifest.get("scan_truncated", False)
            and isinstance(manifest.get("candidate_files"), list)
        )

    def _git_changed_paths(self, indexed_head: str) -> set[str] | None:
        if not indexed_head:
            return None
        try:
            result = subprocess.run(
                ["git", "diff", "--name-only", "--no-renames", "-z", f"{indexed_head}..HEAD"],
                cwd=self.repo_root,
                capture_output=True,
                text=False,
                timeout=5.0,
            )
        except (OSError, subprocess.TimeoutExpired):
            return None
        if result.returncode != 0:
            return None
        return {
            item.decode("utf-8", errors="replace").replace("\\", "/")
            for item in result.stdout.split(b"\0")
            if item
        }

    def _git_working_tree_changed_paths(self) -> set[str] | None:
        changed: set[str] = set()
        commands = [
            ["git", "diff", "--name-only", "--no-renames", "-z"],
            ["git", "diff", "--cached", "--name-only", "--no-renames", "-z"],
            ["git", "ls-files", "--others", "--exclude-standard", "-z"],
        ]
        try:
            for command in commands:
                result = subprocess.run(
                    command,
                    cwd=self.repo_root,
                    capture_output=True,
                    text=False,
                    timeout=5.0,
                )
                if result.returncode != 0:
                    return None
                changed.update(
                    item.decode("utf-8", errors="replace").replace("\\", "/")
                    for item in result.stdout.split(b"\0")
                    if item
                )
        except (OSError, subprocess.TimeoutExpired):
            return None
        return changed

    def _scan_source_files_incremental(
        self,
        candidates: list[str],
        previous: dict[str, Any],
        changed_candidates: set[str],
    ) -> tuple[list[dict[str, Any]], bool]:
        previous_records = {
            item.get("path"): item
            for item in previous.get("source_files", [])
            if isinstance(item, dict) and item.get("path")
        }
        records: list[dict[str, Any]] = []
        for relative in sorted(candidates):
            if len(records) >= MAX_SOURCE_FILES:
                return records, True
            path = self.repo_root / relative
            if not self._is_source_candidate(path):
                continue
            if relative in previous_records and relative not in changed_candidates:
                records.append(dict(previous_records[relative]))
                continue
            record = self._read_source_record(relative, path)
            if record is not None:
                records.append(record)
        return records, False

    def _scan_source_files(self) -> tuple[list[dict[str, Any]], bool]:
        records: list[dict[str, Any]] = []
        truncated = False
        for relative in self._list_source_candidates():
            if len(records) >= MAX_SOURCE_FILES:
                truncated = True
                return records, truncated
            path = self.repo_root / relative
            if not self._is_source_candidate(path):
                continue
            record = self._read_source_record(relative, path)
            if record is not None:
                records.append(record)
        return records, truncated

    def _read_source_record(self, relative: str, path: Path) -> dict[str, Any] | None:
        try:
            data = path.read_bytes()
        except OSError:
            return None
        if len(data) > MAX_SOURCE_FILE_BYTES or b"\x00" in data[:8192]:
            return None
        return {
            "path": relative,
            "sha256": _sha256_bytes(data),
            "size_bytes": len(data),
        }

    def _list_source_candidates(self) -> list[str]:
        candidates = self._git_list_source_candidates()
        if candidates is not None:
            return candidates
        return self._filesystem_list_source_candidates()

    def _git_list_source_candidates(self) -> list[str] | None:
        try:
            result = subprocess.run(
                [
                    "git",
                    "ls-files",
                    "--cached",
                    "--others",
                    "--exclude-standard",
                ],
                cwd=self.repo_root,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=5.0,
            )
        except (OSError, subprocess.TimeoutExpired):
            return None
        if result.returncode != 0:
            return None
        seen: set[str] = set()
        paths: list[str] = []
        for raw in result.stdout.splitlines():
            normalized = raw.strip().replace("\\", "/")
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            if self._is_excluded_relative_path(normalized):
                continue
            paths.append(normalized)
        return sorted(paths)

    def _filesystem_list_source_candidates(self) -> list[str]:
        seen: set[str] = set()
        paths: list[str] = []
        for current_root, dirnames, filenames in os.walk(self.repo_root, topdown=True):
            current_path = Path(current_root)
            relative_dir = current_path.relative_to(self.repo_root)
            relative_dir_str = relative_dir.as_posix() if relative_dir.parts else ""
            dirnames[:] = [
                name
                for name in dirnames
                if not self._should_skip_walk_dir(relative_dir_str, name)
            ]
            for filename in filenames:
                relative = (
                    f"{relative_dir_str}/{filename}" if relative_dir_str else filename
                ).replace("\\", "/")
                if relative in seen or self._is_excluded_relative_path(relative):
                    continue
                seen.add(relative)
                paths.append(relative)
        return sorted(paths)

    def _should_skip_walk_dir(self, relative_dir: str, name: str) -> bool:
        candidate = f"{relative_dir}/{name}" if relative_dir else name
        lowered = name.lower()
        if lowered in _BLOCKED_DIRS:
            return True
        if lowered.endswith(".egg-info"):
            return True
        return self._is_excluded_relative_path(candidate)

    def _is_excluded_relative_path(self, relative: str) -> bool:
        parts = relative.split("/")
        lowered_parts = {part.lower() for part in parts}
        if lowered_parts & _BLOCKED_DIRS:
            return True
        if any(part.lower().endswith(".egg-info") for part in parts):
            return True
        if relative.startswith(".soma/wiki/"):
            return True
        # Tool-owned scratch is never repository knowledge. This is a prefix
        # match rather than a segment match so a nested path such as
        # ``.claude/worktrees/...`` is excluded without excluding ``.claude``
        # itself, which holds real project configuration.
        if is_tool_owned_path(relative):
            return True
        if relative in self.wiki_exclusions:
            return True
        return any(
            relative == prefix or relative.startswith(f"{prefix}/")
            for prefix in self.wiki_exclusions
        )

    def _is_source_candidate(self, path: Path) -> bool:
        if path.is_symlink() or not path.is_file():
            return False
        lowered_name = path.name.lower()
        if lowered_name in _BLOCKED_FILES or path.suffix.lower() in _BLOCKED_SUFFIXES:
            return False
        relative = path.relative_to(self.repo_root)
        lowered_parts = {part.lower() for part in relative.parts}
        if lowered_parts & _BLOCKED_DIRS:
            return False
        if is_tool_owned_path(relative):
            return False
        if any(part in {"secrets", "credentials"} for part in lowered_parts):
            return False
        return path.suffix.lower() in _TEXT_SUFFIXES or lowered_name in {
            "dockerfile",
            "makefile",
            "justfile",
            "procfile",
            "license",
            "readme",
        }

    def _analyse(
        self,
        source_files: list[dict[str, Any]],
        *,
        previous_analysis: dict[str, Any] | None = None,
        changed_paths: set[str] | None = None,
    ) -> dict[str, Any]:
        paths = [item["path"] for item in source_files]
        path_set = set(paths)
        language_counts = Counter(self._language_for_path(path) for path in paths)
        top_level = Counter(path.split("/", 1)[0] for path in paths if "/" in path)
        important = [path for path in paths if self._is_important_file(path)]
        project_types = self._project_types(path_set)
        modules: list[dict[str, Any]] = []
        dependency_edges: set[tuple[str, str]] = set()
        local_python_modules = {
            self._python_module_name(path): path
            for path in paths
            if Path(path).suffix.lower() in {".py", ".pyi"}
        }
        local_roots = {name.split(".", 1)[0] for name in local_python_modules}
        previous_modules = {
            item.get("path"): item
            for item in (previous_analysis or {}).get("modules", [])
            if isinstance(item, dict) and item.get("path")
        }
        changed_paths = changed_paths or set(paths)

        for path in paths:
            suffix = Path(path).suffix.lower()
            if suffix not in {".py", ".pyi", ".js", ".jsx", ".ts", ".tsx"}:
                continue
            if path in previous_modules and path not in changed_paths:
                modules.append(dict(previous_modules[path]))
                continue
            absolute = self.repo_root / path
            try:
                text = absolute.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            if suffix in {".py", ".pyi"}:
                module = self._analyse_python(path, text)
                source_name = module["module"]
                for imported in module.get("imports", []):
                    root = imported.split(".", 1)[0]
                    if root in local_roots and root != source_name.split(".", 1)[0]:
                        dependency_edges.add((source_name.split(".", 1)[0], root))
                modules.append(module)
            else:
                modules.append(self._analyse_javascript(path, text))

        return {
            "language_counts": dict(
                sorted(language_counts.items(), key=lambda item: (-item[1], item[0]))
            ),
            "top_level": dict(
                sorted(top_level.items(), key=lambda item: (-item[1], item[0]))
            ),
            "important_files": important,
            "project_types": project_types,
            "modules": sorted(modules, key=lambda item: item["path"]),
            "dependency_edges": sorted(dependency_edges),
            "entry_points": self._entry_points(path_set),
        }

    def _analyse_python(self, path: str, text: str) -> dict[str, Any]:
        classes: list[str] = []
        functions: list[str] = []
        imports: list[str] = []
        summary = ""
        try:
            tree = ast.parse(text)
            summary = (ast.get_docstring(tree) or "").strip().split("\n", 1)[0][:240]
            for node in tree.body:
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    functions.append(node.name)
                elif isinstance(node, ast.ClassDef):
                    classes.append(node.name)
                elif isinstance(node, ast.Import):
                    imports.extend(alias.name for alias in node.names)
                elif isinstance(node, ast.ImportFrom):
                    if node.module:
                        imports.append(node.module)
        except SyntaxError:
            for left, right in _IMPORT_RE.findall(text):
                imports.append(left or right)
        return {
            "path": path,
            "module": self._python_module_name(path),
            "kind": "python",
            "summary": summary,
            "classes": classes[:50],
            "functions": functions[:80],
            "imports": imports,
        }

    def _analyse_javascript(self, path: str, text: str) -> dict[str, Any]:
        imports = [match for match in _JS_IMPORT_RE.findall(text) if match]
        symbols = _JS_SYMBOL_RE.findall(text)
        return {
            "path": path,
            "module": path,
            "kind": "javascript"
            if Path(path).suffix.lower() in {".js", ".jsx"}
            else "typescript",
            "summary": "",
            "classes": [],
            "functions": symbols[:80],
            "imports": imports[:100],
        }

    def _render_overview(
        self,
        source_files: list[dict[str, Any]],
        analysis: dict[str, Any],
        truncated: bool,
        *,
        generation_id: str = "",
        indexed_branch: str = "",
        indexed_head: str = "",
        source_generation: int = 0,
        indexed_source_generation: int = 0,
        stale: bool = False,
        stale_reason: str = "",
    ) -> str:
        lines = [
            f"# {self.repo_name} repository wiki",
            "",
            "> Generated from the live repository by Soma. Verify critical details against source code before editing.",
            "",
            "## Snapshot",
            "",
            f"- generation_id: `{generation_id}`",
            f"- indexed_branch: `{indexed_branch or '(detached or unavailable)'}`",
            f"- indexed_head: `{indexed_head or '(unavailable)'}`",
            f"- source_generation: {source_generation}",
            f"- indexed_source_generation: {indexed_source_generation}",
            f"- stale: {'true' if stale else 'false'}",
            *([f"- stale_reason: {stale_reason}"] if stale_reason else []),
            "",
            f"- Source files indexed: **{len(source_files)}**",
            f"- Scan truncated: **{'yes' if truncated else 'no'}**",
            f"- Project types: **{', '.join(analysis['project_types']) or 'unclassified'}**",
            "",
            "## Languages and formats",
            "",
        ]
        for language, count in analysis["language_counts"].items():
            lines.append(f"- {language}: {count}")
        lines.extend(["", "## Top-level areas", ""])
        for name, count in list(analysis["top_level"].items())[:30]:
            lines.append(f"- `{name}/`: {count} indexed files")
        lines.extend(["", "## Important files", ""])
        for path in analysis["important_files"][:80]:
            lines.append(f"- `{path}`")
        lines.extend(
            [
                "",
                "## Wiki pages",
                "",
                "- [Architecture](architecture.md)",
                "- [Modules](modules.md)",
                "- [Validation](validation.md)",
                "",
            ]
        )
        return "\n".join(lines)

    def _render_index(
        self,
        *,
        generation_id: str,
        indexed_branch: str,
        indexed_head: str,
        source_file_count: int,
        analysis: dict[str, Any],
        stale: bool = False,
        stale_reason: str = "",
    ) -> str:
        top_level = list(analysis.get("top_level", {}))[:30]
        important = analysis.get("important_files", [])[:30]
        project_type = ", ".join(analysis.get("project_types", [])) or "unclassified"
        lines = [
            f"# {self.repo_name} repository wiki",
            "",
            "> This wiki is a structural cache generated from one repository snapshot.",
            "> Exact implementation claims and edits must be verified against live source",
            "> with Git or targeted ripgrep before action.",
            "",
            "## Snapshot",
            "",
            f"- Generation: `{generation_id}`",
            f"- Indexed branch: `{indexed_branch or '(detached or unavailable)'}`",
            f"- Indexed Git commit: `{indexed_head or '(unavailable)'}`",
            f"- Project type: **{project_type}**",
            f"- Indexed source-file count: **{source_file_count}**",
            f"- stale: {'true' if stale else 'false'}",
            *([f"- stale_reason: {stale_reason}"] if stale_reason else []),
            "",
            "## Important files",
            "",
        ]
        lines.extend(f"- `{path}`" for path in important or ["No conventional project files detected."])
        lines.extend(["", "## Top-level directories", ""])
        lines.extend(f"- `{name}/`" for name in top_level or ["No top-level directories detected."])
        lines.extend(
            [
                "",
                "## Pages",
                "",
                "- [Overview](overview.md) — repository shape, languages, and important files.",
                "- [Architecture](architecture.md) — entry points and dependency relationships.",
                "- [Modules](modules.md) — module-level symbols and summaries.",
                "- [Validation](validation.md) — inferred checks and relevant configuration.",
                "",
                "## Verification guidance",
                "",
                "Use Overview for orientation, Architecture for system relationships, Modules for implementation navigation, and Validation for checks. Use live Git status/history and targeted `rg` searches before relying on exact names, behavior, or edit locations.",
                "",
            ]
        )
        return "\n".join(lines)

    def _render_architecture(self, analysis: dict[str, Any]) -> str:
        lines = [
            f"# {self.repo_name} architecture",
            "",
            "## Detected entry points",
            "",
        ]
        if analysis["entry_points"]:
            lines.extend(f"- `{path}`" for path in analysis["entry_points"])
        else:
            lines.append("- No conventional entry point was detected.")
        lines.extend(["", "## Local dependency map", "", "```mermaid", "graph LR"])
        edges = analysis["dependency_edges"][:120]
        if edges:
            for source, target in edges:
                lines.append(
                    f"    {self._mermaid_id(source)}[{source}] --> {self._mermaid_id(target)}[{target}]"
                )
        else:
            lines.append("    repo[Repository] --> modules[Modules]")
        lines.extend(["```", "", "## Architectural module summary", ""])
        for module in analysis["modules"][:120]:
            parts = []
            if module["classes"]:
                parts.append(f"classes: {', '.join(module['classes'][:8])}")
            if module["functions"]:
                parts.append(f"functions: {', '.join(module['functions'][:10])}")
            detail = "; ".join(parts) or module["summary"] or module["kind"]
            lines.append(f"- `{module['path']}` — {detail}")
        lines.append("")
        return "\n".join(lines)

    def _render_modules(self, analysis: dict[str, Any]) -> str:
        lines = [f"# {self.repo_name} modules", ""]
        for module in analysis["modules"][:400]:
            lines.extend([f"## `{module['path']}`", ""])
            if module["summary"]:
                lines.extend([module["summary"], ""])
            lines.append(f"- Kind: {module['kind']}")
            if module["classes"]:
                lines.append(f"- Classes: {', '.join(module['classes'])}")
            if module["functions"]:
                lines.append(f"- Functions/symbols: {', '.join(module['functions'])}")
            lines.append("")
        if len(analysis["modules"]) > 400:
            lines.extend(
                [
                    f"_Module list truncated: {len(analysis['modules']) - 400} additional modules._",
                    "",
                ]
            )
        return "\n".join(lines)

    def _render_validation(
        self, source_files: list[dict[str, Any]], analysis: dict[str, Any]
    ) -> str:
        path_set = {item["path"] for item in source_files}
        commands: list[str] = []
        if (
            "pyproject.toml" in path_set
            or "pytest.ini" in path_set
            or "tox.ini" in path_set
        ):
            commands.append("python -m pytest -q")
        if (
            "pyproject.toml" in path_set
            or "ruff.toml" in path_set
            or ".ruff.toml" in path_set
        ):
            commands.extend(
                ["python -m ruff format --check .", "python -m ruff check ."]
            )
        if "mypy.ini" in path_set or "pyproject.toml" in path_set:
            commands.append("python -m mypy .")
        if "package.json" in path_set:
            commands.extend(["npm test", "npm run lint"])
        if "Cargo.toml" in path_set:
            commands.extend(["cargo test", "cargo clippy --all-targets --all-features"])
        if "go.mod" in path_set:
            commands.extend(["go test ./...", "go vet ./..."])
        commands.append("git diff --check")
        unique_commands = list(dict.fromkeys(commands))
        lines = [
            f"# {self.repo_name} validation",
            "",
            "> These commands are inferred from repository configuration. Prefer project documentation and configured scripts when they differ.",
            "",
            "## Detected project types",
            "",
        ]
        lines.extend(
            f"- {item}" for item in analysis["project_types"] or ["unclassified"]
        )
        lines.extend(["", "## Suggested checks", ""])
        lines.extend(f"- `{command}`" for command in unique_commands)
        lines.extend(["", "## Relevant configuration", ""])
        validation_names = {
            "pyproject.toml",
            "pytest.ini",
            "tox.ini",
            "noxfile.py",
            "ruff.toml",
            ".ruff.toml",
            "mypy.ini",
            "package.json",
            "tsconfig.json",
            "eslint.config.js",
            "biome.json",
            "Cargo.toml",
            "go.mod",
            "Makefile",
            "justfile",
        }
        for path in sorted(path_set):
            if Path(path).name in validation_names:
                lines.append(f"- `{path}`")
        lines.append("")
        return "\n".join(lines)

    @staticmethod
    def _language_for_path(path: str) -> str:
        suffix = Path(path).suffix.lower()
        names = {
            ".py": "Python",
            ".pyi": "Python",
            ".js": "JavaScript",
            ".jsx": "JavaScript",
            ".ts": "TypeScript",
            ".tsx": "TypeScript",
            ".md": "Markdown",
            ".json": "JSON",
            ".toml": "TOML",
            ".yaml": "YAML",
            ".yml": "YAML",
            ".ps1": "PowerShell",
            ".sh": "Shell",
            ".go": "Go",
            ".rs": "Rust",
            ".java": "Java",
            ".cs": "C#",
        }
        return names.get(suffix, suffix.lstrip(".").upper() or "Text")

    @staticmethod
    def _python_module_name(path: str) -> str:
        value = path
        if value.endswith("/__init__.py"):
            value = value[: -len("/__init__.py")]
        elif value.endswith(".py"):
            value = value[:-3]
        elif value.endswith(".pyi"):
            value = value[:-4]
        return value.replace("/", ".") or "root"

    @staticmethod
    def _project_types(paths: set[str]) -> list[str]:
        types: list[str] = []
        if (
            "pyproject.toml" in paths
            or "requirements.txt" in paths
            or any(path.endswith(".py") for path in paths)
        ):
            types.append("Python")
        if "package.json" in paths:
            types.append("Node.js")
        if "Cargo.toml" in paths:
            types.append("Rust")
        if "go.mod" in paths:
            types.append("Go")
        if (
            any(Path(path).name == "Dockerfile" for path in paths)
            or "docker-compose.yml" in paths
            or "compose.yaml" in paths
        ):
            types.append("Containerized")
        return types

    @staticmethod
    def _entry_points(paths: set[str]) -> list[str]:
        conventional = {
            "main.py",
            "app.py",
            "server.py",
            "manage.py",
            "cli.py",
            "index.js",
            "index.ts",
            "src/index.js",
            "src/index.ts",
            "src/main.py",
            "src/main.rs",
            "cmd/main.go",
        }
        result = [
            path
            for path in sorted(paths)
            if path in conventional or Path(path).name in {"__main__.py", "main.go"}
        ]
        return result[:50]

    @staticmethod
    def _is_important_file(path: str) -> bool:
        name = Path(path).name.lower()
        return name in {
            "readme.md",
            "pyproject.toml",
            "package.json",
            "dockerfile",
            "docker-compose.yml",
            "compose.yaml",
            "makefile",
            "justfile",
            "agents.md",
            "contributing.md",
            "architecture.md",
            "cargo.toml",
            "go.mod",
        }

    @staticmethod
    def _mermaid_id(value: str) -> str:
        return "n_" + re.sub(r"[^A-Za-z0-9_]", "_", value)
