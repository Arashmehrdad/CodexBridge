from __future__ import annotations

import base64
import binascii
import json
from pathlib import Path
from typing import Any

from .canonical import canonical_json_bytes, canonical_json_sha256
from .generation import ResearchMapGenerationError, load_current_generation
from .graphiti_backend import graphiti_projection_contract_sha256
from .service import ResearchMapHealthState, ResearchMapScan, scan_research_map
from .sidecars import SidecarState

RESEARCH_MAP_QUERY_GATEWAY_VERSION = "soma.research-map.query.v1"


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


def query_search_unavailable(
    repository_root: str | Path,
    *,
    project_id: str,
    repo_name: str,
    query: str,
    limit: int,
    include_noncurrent: bool,
    response_budget_bytes: int,
) -> dict[str, Any]:
    scan = scan_research_map(repository_root)
    health = _health_payload(
        repository_root,
        scan,
        project_id=project_id,
        repo_name=repo_name,
    )
    return {
        **health,
        "ok": False,
        "operation": "search",
        "status": "backend_unavailable",
        "query": query,
        "limit": limit,
        "include_noncurrent": include_noncurrent,
        "results": [],
        "count": 0,
        "backend_state": "unavailable",
        "response_budget_bytes": response_budget_bytes,
        "error": "semantic_search_backend_unavailable_until_rm7",
    }


def research_map_query_gateway(
    repository_root: str | Path,
    *,
    project_id: str,
    repo_name: str,
    operation: str,
    relation_id: str = "",
    query: str = "",
    limit: int = 50,
    cursor: str = "",
    include_noncurrent: bool = False,
    view: str = "compact",
    response_budget_bytes: int = 12 * 1024,
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
        return query_search_unavailable(
            repository_root,
            project_id=project_id,
            repo_name=repo_name,
            query=query,
            limit=limit,
            include_noncurrent=include_noncurrent,
            response_budget_bytes=response_budget_bytes,
        )
    raise ResearchMapQueryError(f"unsupported_operation:{operation}")
