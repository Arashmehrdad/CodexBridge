from __future__ import annotations

import base64
import binascii
import json
from pathlib import Path, PurePosixPath
from typing import Any

from .canonical import (
    canonical_json_bytes,
    canonical_json_sha256,
    normalize_repo_relative_path,
)
from .canonical import (
    relation_id as canonical_relation_id,
)
from .generation import ResearchMapGenerationError, load_current_generation
from .graphiti_backend import graphiti_projection_contract_sha256
from .manifest import ManifestState, load_project_manifest
from .models import (
    PREDICATE_REGISTRY_VERSION,
    RESEARCH_MAP_SCHEMA_VERSION,
    Predicate,
    ProjectManifest,
    ResearchMapSidecar,
)
from .search import BackendFactory as SearchBackendFactory
from .search import ResearchMapSearchError, search_published_generation
from .service import ResearchMapHealthState, ResearchMapScan, scan_research_map
from .sidecars import SidecarState, expected_sidecar_path

RESEARCH_MAP_QUERY_GATEWAY_VERSION = "soma.research-map.query.v2"


class ResearchMapQueryError(ValueError):
    pass


def _json_bytes(value: Any) -> int:
    return len(json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))


def _encode_cursor(offset: int, desired_state: str) -> str:
    payload = {
        "version": 1,
        "offset": offset,
        "semantic_desired_state_sha256": desired_state,
    }
    encoded = base64.urlsafe_b64encode(canonical_json_bytes(payload)).decode("ascii")
    return encoded.rstrip("=")


def _decode_cursor(cursor: str, desired_state: str) -> int:
    if not cursor:
        return 0
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        raw = base64.urlsafe_b64decode(padded.encode("ascii"))
        payload = json.loads(raw.decode("utf-8", errors="strict"))
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError, binascii.Error) as exc:
        raise ResearchMapQueryError("invalid_cursor") from exc
    if not isinstance(payload, dict) or payload.get("version") != 1:
        raise ResearchMapQueryError("invalid_cursor")
    offset = payload.get("offset")
    if isinstance(offset, bool) or not isinstance(offset, int) or offset < 0:
        raise ResearchMapQueryError("invalid_cursor")
    if payload.get("semantic_desired_state_sha256") != desired_state:
        raise ResearchMapQueryError("stale_cursor")
    return offset


def _adoption_state(scan: ResearchMapScan) -> str:
    if scan.health_state is ResearchMapHealthState.NOT_ADOPTED:
        return "not_adopted"
    if scan.manifest_state.value == "valid":
        return "adopted"
    return "unknown"


def _coverage_state(scan: ResearchMapScan) -> str:
    if scan.health_state is ResearchMapHealthState.NOT_ADOPTED:
        return "not_adopted"
    if scan.health_state is ResearchMapHealthState.DISABLED:
        return "disabled"
    if scan.manifest_state.value != "valid":
        return "degraded"
    if scan.coverage.complete:
        return "complete"
    if scan.coverage.total_count == 0:
        return "empty"
    return "incomplete"


def _publication_state(
    repository_root: str | Path,
    scan: ResearchMapScan,
) -> tuple[str, str, str | None, str | None]:
    if scan.health_state is ResearchMapHealthState.NOT_ADOPTED:
        return "not_applicable", "unavailable", None, None
    if scan.manifest_state.value != "valid":
        return "unknown", "unavailable", None, None
    try:
        current = load_current_generation(repository_root)
    except ResearchMapGenerationError:
        return "degraded", "not_checked", None, None
    if current is None:
        return "missing", "unavailable", None, None

    expected_projection = graphiti_projection_contract_sha256()
    stale = (
        current.repository_uid != scan.repository_uid
        or current.semantic_desired_state_sha256 != scan.semantic_desired_state_sha256
        or current.projection_contract_sha256 != expected_projection
    )
    return (
        "stale" if stale else "published_verified",
        "not_checked",
        current.generation,
        current.projection_contract_sha256,
    )


def _health_payload(
    repository_root: str | Path,
    scan: ResearchMapScan,
    *,
    project_id: str,
    repo_name: str,
) -> dict[str, Any]:
    counts = scan.coverage.counts
    issue_codes = sorted({issue.code for issue in scan.issues})
    sync_state, backend_state, published_generation, projection_contract = _publication_state(
        repository_root,
        scan,
    )
    return {
        "ok": True,
        "operation": "health",
        "status": scan.health_state.value,
        "project_id": project_id,
        "repo_name": repo_name,
        "adoption_state": _adoption_state(scan),
        "manifest_state": scan.manifest_state.value,
        "coverage_state": _coverage_state(scan),
        "sync_state": sync_state,
        "backend_state": backend_state,
        "repository_uid": scan.repository_uid,
        "semantic_desired_state_sha256": scan.semantic_desired_state_sha256,
        "published_generation": published_generation,
        "projection_contract_sha256": projection_contract,
        "coverage_counts": counts,
        "stale_sidecar_count": counts.get("stale", 0),
        "unreviewed_count": counts.get("unreviewed", 0),
        "deferred_count": counts.get("deferred", 0),
        "missing_source_count": counts.get("missing_source", 0),
        "issue_count": len(scan.issues),
        "issue_codes": issue_codes[:32],
        "issue_codes_truncated": len(issue_codes) > 32,
        "gateway_version": RESEARCH_MAP_QUERY_GATEWAY_VERSION,
        "error": "",
    }


def query_health(
    repository_root: str | Path,
    *,
    project_id: str,
    repo_name: str,
) -> dict[str, Any]:
    return _health_payload(
        repository_root,
        scan_research_map(repository_root),
        project_id=project_id,
        repo_name=repo_name,
    )


def query_coverage(
    repository_root: str | Path,
    *,
    project_id: str,
    repo_name: str,
    limit: int,
    cursor: str,
    response_budget_bytes: int,
) -> dict[str, Any]:
    scan = scan_research_map(repository_root)
    health = _health_payload(
        repository_root,
        scan,
        project_id=project_id,
        repo_name=repo_name,
    )
    desired_state = scan.semantic_desired_state_sha256 or ""
    if scan.manifest_state.value != "valid" or scan.health_state in {
        ResearchMapHealthState.NOT_ADOPTED,
        ResearchMapHealthState.DISABLED,
    }:
        return {
            **health,
            "operation": "coverage",
            "items": [],
            "count": 0,
            "total_count": scan.coverage.total_count,
            "has_more": False,
            "next_cursor": "",
            "response_budget_bytes": response_budget_bytes,
        }

    try:
        offset = _decode_cursor(cursor, desired_state)
    except ResearchMapQueryError as exc:
        return {
            **health,
            "ok": False,
            "operation": "coverage",
            "status": str(exc),
            "items": [],
            "count": 0,
            "total_count": scan.coverage.total_count,
            "has_more": False,
            "next_cursor": "",
            "response_budget_bytes": response_budget_bytes,
            "error": str(exc),
        }

    entries = list(scan.coverage.entries)
    page = entries[offset : offset + limit]
    items = [
        {
            "source_path": entry.source_path,
            "logical_record_id": entry.logical_record_id,
            "expected_sidecar_path": entry.expected_sidecar_path,
            "coverage_state": entry.state.value,
            "sidecar_state": entry.sidecar_state.value,
            "canonical_text_sha256": entry.canonical_text_sha256,
            "canonical_sidecar_sha256": entry.canonical_sidecar_sha256,
        }
        for entry in page
    ]
    next_offset = offset + len(items)
    has_more = next_offset < len(entries)
    result = {
        **health,
        "operation": "coverage",
        "items": items,
        "count": len(items),
        "total_count": len(entries),
        "has_more": has_more,
        "next_cursor": _encode_cursor(next_offset, desired_state) if has_more else "",
        "response_budget_bytes": response_budget_bytes,
        "truncated": False,
    }
    while _json_bytes(result) > response_budget_bytes and result["items"]:
        result["items"].pop()
        result["count"] = len(result["items"])
        next_offset = offset + len(result["items"])
        result["has_more"] = next_offset < len(entries)
        result["next_cursor"] = (
            _encode_cursor(next_offset, desired_state) if result["has_more"] else ""
        )
        result["truncated"] = True
    result["response_bytes"] = _json_bytes(result)
    return result


def _truncate_relation_payload(
    relation: dict[str, Any],
    *,
    compact: bool,
) -> tuple[dict[str, Any], list[str]]:
    if not compact:
        return relation, []
    projected = dict(relation)
    truncated: list[str] = []
    statement = str(projected.get("statement") or "")
    if len(statement) > 8_000:
        projected["statement"] = statement[:8_000]
        truncated.append("statement")
    locator = dict(projected.get("locator") or {})
    anchor = str(locator.get("anchor") or "")
    if len(anchor) > 4_000:
        locator["anchor"] = anchor[:4_000]
        projected["locator"] = locator
        truncated.append("locator.anchor")
    return projected, truncated


def query_relation(
    repository_root: str | Path,
    *,
    project_id: str,
    repo_name: str,
    relation_id: str,
    view: str,
    response_budget_bytes: int,
) -> dict[str, Any]:
    scan = scan_research_map(repository_root)
    health = _health_payload(
        repository_root,
        scan,
        project_id=project_id,
        repo_name=repo_name,
    )
    if scan.manifest_state.value != "valid" or scan.health_state in {
        ResearchMapHealthState.NOT_ADOPTED,
        ResearchMapHealthState.DISABLED,
    }:
        return {
            **health,
            "operation": "relation",
            "relation_id": relation_id,
            "relation": None,
            "error": "",
        }

    matches = []
    for record in scan.sidecar_scan.records:
        if record.sidecar_state is not SidecarState.VALID or record.sidecar is None:
            continue
        for relation in record.sidecar.relations:
            if relation.relation_id == relation_id:
                matches.append((record, relation))
    if not matches:
        return {
            **health,
            "ok": False,
            "operation": "relation",
            "status": "not_found",
            "relation_id": relation_id,
            "relation": None,
            "error": "relation_not_found",
        }
    if len(matches) != 1:
        return {
            **health,
            "ok": False,
            "operation": "relation",
            "status": "ambiguous",
            "relation_id": relation_id,
            "source_paths": sorted(record.source_path for record, _ in matches),
            "relation": None,
            "error": "duplicate_relation_id",
        }

    record, relation = matches[0]
    governance = {
        item.relation_id: item
        for item in (scan.governance.relations if scan.governance is not None else ())
    }.get(relation_id)
    full_relation = relation.model_dump(mode="json", exclude_none=True)
    projected_relation, truncated_fields = _truncate_relation_payload(
        full_relation,
        compact=view == "compact",
    )
    result = {
        **health,
        "operation": "relation",
        "status": "found",
        "relation_id": relation_id,
        "source_path": record.source_path,
        "record_facets": dict(record.sidecar.facets),
        "declared_lifecycle": relation.lifecycle.value,
        "effective_lifecycle": (
            governance.effective_lifecycle.value if governance is not None else relation.lifecycle.value
        ),
        "superseded_by": list(governance.superseded_by) if governance is not None else [],
        "relation_content_sha256": canonical_json_sha256(full_relation),
        "relation": projected_relation,
        "truncated": bool(truncated_fields),
        "truncated_fields": truncated_fields,
        "response_budget_bytes": response_budget_bytes,
    }
    if _json_bytes(result) > response_budget_bytes:
        projected_relation, truncated_fields = _truncate_relation_payload(
            full_relation,
            compact=True,
        )
        result["relation"] = projected_relation
        result["truncated"] = True
        result["truncated_fields"] = sorted(set(truncated_fields + ["response_budget"]))
        while _json_bytes(result) > response_budget_bytes:
            relation_payload = result.get("relation")
            if not isinstance(relation_payload, dict):
                break
            statement = str(relation_payload.get("statement") or "")
            locator = dict(relation_payload.get("locator") or {})
            anchor = str(locator.get("anchor") or "")
            if len(statement) > 512:
                relation_payload["statement"] = statement[: max(512, len(statement) // 2)]
                continue
            if len(anchor) > 256:
                locator["anchor"] = anchor[: max(256, len(anchor) // 2)]
                relation_payload["locator"] = locator
                continue
            subject = dict(relation_payload.get("subject") or {})
            object_node = dict(relation_payload.get("object") or {})
            result["relation"] = {
                "relation_id": relation_payload.get("relation_id"),
                "subject": {
                    "key": str(subject.get("key") or "")[:512],
                    "label": str(subject.get("label") or "")[:512],
                },
                "predicate": relation_payload.get("predicate"),
                "object": {
                    "key": str(object_node.get("key") or "")[:512],
                    "label": str(object_node.get("label") or "")[:512],
                },
                "statement": statement[:512],
                "locator": {"anchor": anchor[:256]},
                "epistemic_class": relation_payload.get("epistemic_class"),
                "lifecycle": relation_payload.get("lifecycle"),
                "supersedes": list(relation_payload.get("supersedes") or [])[:16],
                "facets": {},
                "qualifiers": {},
            }
            result["record_facets"] = {}
            result["truncated_fields"] = sorted(
                set(
                    list(result.get("truncated_fields") or [])
                    + ["facets", "qualifiers", "record_facets"]
                )
            )
            break
    result["response_bytes"] = _json_bytes(result)
    return result


def _search_candidate_payload(candidate: Any) -> tuple[dict[str, Any], bool]:
    payload = candidate.as_dict()
    truncated_fields: list[str] = []
    statement = str(payload.get("statement") or "")
    anchor = str(payload.get("source_anchor") or "")
    if len(statement) > 2_000:
        payload["statement"] = statement[:2_000]
        truncated_fields.append("statement")
    if len(anchor) > 1_000:
        payload["source_anchor"] = anchor[:1_000]
        truncated_fields.append("source_anchor")
    payload["truncated_fields"] = truncated_fields
    return payload, bool(truncated_fields)


def query_search(
    repository_root: str | Path,
    *,
    project_id: str,
    repo_name: str,
    query: str,
    limit: int,
    include_noncurrent: bool,
    response_budget_bytes: int,
    backend_factory: SearchBackendFactory | None = None,
) -> dict[str, Any]:
    scan = scan_research_map(repository_root)
    health = _health_payload(
        repository_root,
        scan,
        project_id=project_id,
        repo_name=repo_name,
    )
    query_preview = query[:512]
    query_hash = canonical_json_sha256({"query": query})
    try:
        current, candidates = search_published_generation(
            repository_root,
            scan,
            query=query,
            limit=limit,
            include_noncurrent=include_noncurrent,
            backend_factory=backend_factory,
        )
    except ResearchMapSearchError as exc:
        if exc.code == "backend_drift":
            backend_state = "drifted"
        elif exc.code == "source_verification_failed":
            backend_state = "verified"
        elif exc.code.startswith("backend"):
            backend_state = "unavailable"
        else:
            backend_state = "not_checked"
        error_text = str(exc)
        public_error = error_text[:1_000]
        result = {
            **health,
            "ok": False,
            "operation": "search",
            "status": exc.code,
            "query_preview": query_preview,
            "query_sha256": query_hash,
            "query_truncated": len(query) > len(query_preview),
            "limit": limit,
            "include_noncurrent": include_noncurrent,
            "results": [],
            "count": 0,
            "matched_count": 0,
            "backend_state": backend_state,
            "response_budget_bytes": response_budget_bytes,
            "truncated": len(public_error) < len(error_text),
            "error": public_error,
        }
        while _json_bytes(result) > response_budget_bytes and result["error"]:
            result["error"] = result["error"][: max(0, len(result["error"]) // 2)]
            result["truncated"] = True
        result["response_bytes"] = _json_bytes(result)
        return result

    results: list[dict[str, Any]] = []
    field_truncated = False
    for candidate in candidates:
        payload, was_truncated = _search_candidate_payload(candidate)
        results.append(payload)
        field_truncated = field_truncated or was_truncated
    matched_count = len(results)
    result = {
        **health,
        "ok": True,
        "operation": "search",
        "status": "found" if results else "empty",
        "query_preview": query_preview,
        "query_sha256": query_hash,
        "query_truncated": len(query) > len(query_preview),
        "limit": limit,
        "include_noncurrent": include_noncurrent,
        "results": results,
        "count": len(results),
        "matched_count": matched_count,
        "backend_state": "verified",
        "published_generation": current.generation,
        "database": current.database,
        "response_budget_bytes": response_budget_bytes,
        "truncated": field_truncated,
        "error": "",
    }
    while _json_bytes(result) > response_budget_bytes and result["results"]:
        result["results"].pop()
        result["count"] = len(result["results"])
        result["truncated"] = True
    result["response_bytes"] = _json_bytes(result)
    return result


def _load_authoring_manifest(
    repository_root: str | Path,
    *,
    project_id: str,
    repo_name: str,
    operation: str,
) -> tuple[ProjectManifest | None, dict[str, Any] | None]:
    manifest_result = load_project_manifest(repository_root)
    if manifest_result.state is ManifestState.MISSING:
        return None, {
            "ok": False,
            "operation": operation,
            "project_id": project_id,
            "repo_name": repo_name,
            "status": "not_adopted",
            "error": "research map is not adopted for this repository",
        }
    if not manifest_result.valid or manifest_result.manifest is None:
        return None, {
            "ok": False,
            "operation": operation,
            "project_id": project_id,
            "repo_name": repo_name,
            "status": "manifest_malformed",
            "error": manifest_result.error_code or "manifest_malformed",
        }
    if not manifest_result.manifest.research_map.enabled:
        return None, {
            "ok": False,
            "operation": operation,
            "project_id": project_id,
            "repo_name": repo_name,
            "status": "disabled",
            "error": "research map is disabled for this repository",
        }
    return manifest_result.manifest, None


def query_authoring_contract(
    repository_root: str | Path,
    *,
    project_id: str,
    repo_name: str,
    response_budget_bytes: int,
) -> dict[str, Any]:
    manifest, error = _load_authoring_manifest(
        repository_root,
        project_id=project_id,
        repo_name=repo_name,
        operation="authoring_contract",
    )
    if error is not None or manifest is None:
        return error or {}

    sidecar_schema = ResearchMapSidecar.model_json_schema()
    result = {
        "ok": True,
        "operation": "authoring_contract",
        "status": "available",
        "project_id": project_id,
        "repo_name": repo_name,
        "schema_version": RESEARCH_MAP_SCHEMA_VERSION,
        "predicate_registry_version": PREDICATE_REGISTRY_VERSION,
        "sidecar_json_schema": sidecar_schema,
        "sidecar_json_schema_sha256": canonical_json_sha256(sidecar_schema),
        "roots": [
            item.model_dump(mode="json", exclude_none=True)
            for item in sorted(manifest.research_map.roots, key=lambda root: root.path)
        ],
        "source_hash_contract": {
            "algorithm": "sha256",
            "encoding": "strict UTF-8",
            "line_endings": "normalize CRLF and CR to LF before hashing",
            "field": "source.canonical_text_sha256",
        },
        "sidecar_placement": {
            "rule": "<root.path>/<root.sidecar_dir>/<source-relative-stem>.json",
            "tracked": True,
            "source_must_be_owned_by_configured_root": True,
        },
        "relation_identity": {
            "helper_operation": "relation_id",
            "identity_fields": ["source_path", "subject_key", "predicate", "object_key"],
            "normalization": {
                "source_path": "normalized repository-relative POSIX path",
                "subject_key": "strip surrounding whitespace",
                "predicate": "registered predicate value",
                "object_key": "strip surrounding whitespace",
            },
            "digest": "SHA-256 of NUL-separated UTF-8 identity fields, prefixed with rel_",
            "statement_in_identity": False,
            "labels_in_identity": False,
            "anchor_in_identity": False,
        },
        "authoring_boundary": {
            "materiality_owner": "project scientific/research controller",
            "semantic_relation_selection": "project-owned",
            "soma_role": "mechanical schema, identity, validation, sync, rebuild, and search",
            "auto_generate_semantics": False,
        },
        "response_budget_bytes": response_budget_bytes,
        "error": "",
    }
    required_bytes = _json_bytes(result)
    if required_bytes > response_budget_bytes:
        return {
            "ok": False,
            "operation": "authoring_contract",
            "project_id": project_id,
            "repo_name": repo_name,
            "status": "response_budget_too_small",
            "required_response_bytes": required_bytes,
            "response_budget_bytes": response_budget_bytes,
            "error": "authoring contract does not fit the requested response budget",
        }
    result["response_bytes"] = required_bytes
    return result


def _owned_research_root(manifest: ProjectManifest, source_path: str):
    candidate = PurePosixPath(source_path)
    for root in sorted(manifest.research_map.roots, key=lambda item: item.path):
        root_path = PurePosixPath(root.path)
        try:
            relative = candidate.relative_to(root_path)
        except ValueError:
            continue
        if not relative.parts:
            continue
        sidecar_parts = PurePosixPath(root.sidecar_dir).parts
        if relative.parts[: len(sidecar_parts)] == sidecar_parts:
            continue
        if any(relative.match(pattern) for pattern in root.include):
            return root
    return None


def query_relation_id(
    repository_root: str | Path,
    *,
    project_id: str,
    repo_name: str,
    source_path: str,
    subject_key: str,
    predicate: str,
    object_key: str,
) -> dict[str, Any]:
    manifest, error = _load_authoring_manifest(
        repository_root,
        project_id=project_id,
        repo_name=repo_name,
        operation="relation_id",
    )
    if error is not None or manifest is None:
        return error or {}
    try:
        normalized_source = normalize_repo_relative_path(source_path)
        predicate_value = Predicate(str(predicate)).value
    except (TypeError, ValueError) as exc:
        return {
            "ok": False,
            "operation": "relation_id",
            "project_id": project_id,
            "repo_name": repo_name,
            "status": "invalid_identity",
            "error": str(exc),
        }

    owner = _owned_research_root(manifest, normalized_source)
    if owner is None:
        return {
            "ok": False,
            "operation": "relation_id",
            "project_id": project_id,
            "repo_name": repo_name,
            "status": "source_not_owned",
            "source_path": normalized_source,
            "error": "source path is not owned by an adopted research root/include rule",
        }

    generated = canonical_relation_id(
        normalized_source,
        subject_key,
        predicate_value,
        object_key,
    )
    return {
        "ok": True,
        "operation": "relation_id",
        "status": "generated",
        "project_id": project_id,
        "repo_name": repo_name,
        "source_path": normalized_source,
        "expected_sidecar_path": expected_sidecar_path(owner, normalized_source),
        "relation_id": generated,
        "identity": {
            "subject_key": subject_key.strip(),
            "predicate": predicate_value,
            "object_key": object_key.strip(),
        },
        "statement_in_identity": False,
        "error": "",
    }


def research_map_query_gateway(
    repository_root: str | Path,
    *,
    project_id: str,
    repo_name: str,
    operation: str,
    relation_id: str = "",
    query: str = "",
    source_path: str = "",
    subject_key: str = "",
    predicate: str = "",
    object_key: str = "",
    limit: int = 50,
    cursor: str = "",
    include_noncurrent: bool = False,
    view: str = "compact",
    response_budget_bytes: int = 12 * 1024,
    search_backend_factory: SearchBackendFactory | None = None,
) -> dict[str, Any]:
    if operation == "health":
        return query_health(repository_root, project_id=project_id, repo_name=repo_name)
    if operation == "coverage":
        return query_coverage(
            repository_root,
            project_id=project_id,
            repo_name=repo_name,
            limit=limit,
            cursor=cursor,
            response_budget_bytes=response_budget_bytes,
        )
    if operation == "relation":
        return query_relation(
            repository_root,
            project_id=project_id,
            repo_name=repo_name,
            relation_id=relation_id,
            view=view,
            response_budget_bytes=response_budget_bytes,
        )
    if operation == "search":
        return query_search(
            repository_root,
            project_id=project_id,
            repo_name=repo_name,
            query=query,
            limit=limit,
            include_noncurrent=include_noncurrent,
            response_budget_bytes=response_budget_bytes,
            backend_factory=search_backend_factory,
        )
    if operation == "authoring_contract":
        return query_authoring_contract(
            repository_root,
            project_id=project_id,
            repo_name=repo_name,
            response_budget_bytes=response_budget_bytes,
        )
    if operation == "relation_id":
        return query_relation_id(
            repository_root,
            project_id=project_id,
            repo_name=repo_name,
            source_path=source_path,
            subject_key=subject_key,
            predicate=predicate,
            object_key=object_key,
        )
    raise ResearchMapQueryError(f"unsupported_operation:{operation}")
