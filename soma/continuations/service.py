"""Bounded domain service for Sol semantic continuation re-entry.

The service composes durable continuation records with current canonical Task/Run
readers. It never interprets handoff meaning, decides objective completion, or
recommends what Sol should do next.
"""

from __future__ import annotations

import json
from base64 import urlsafe_b64decode, urlsafe_b64encode
from hashlib import sha256
from pathlib import Path
from typing import Any, Final

from soma.run_store import RunStore
from soma.tasks.store import TaskStore

from .models import (
    ContinuationEffectKind,
    ContinuationEffectLinkRecord,
    ContinuationHandoffRecord,
)
from .store import ContinuationStore


CONTINUATION_RESUME_PROJECTION_VERSION: Final[str] = "continuation.resume.v1"
CONTINUATION_HISTORY_CURSOR_VERSION: Final[str] = "continuation.history.cursor.v1"
CONTINUATION_HISTORY_DEFAULT_LIMIT: Final[int] = 20
CONTINUATION_HISTORY_MAX_LIMIT: Final[int] = 100


def _bounded_limit(limit: int) -> int:
    if isinstance(limit, bool) or not isinstance(limit, int):
        raise ValueError("limit must be an integer")
    if limit < 1 or limit > CONTINUATION_HISTORY_MAX_LIMIT:
        raise ValueError(
            f"limit must be between 1 and {CONTINUATION_HISTORY_MAX_LIMIT}"
        )
    return limit


def _encode_cursor(
    *, continuation_id: str, collection: str, position: dict[str, Any]
) -> str:
    payload = {
        "version": CONTINUATION_HISTORY_CURSOR_VERSION,
        "continuation_id": continuation_id,
        "collection": collection,
        "position": position,
    }
    encoded = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")
    body = urlsafe_b64encode(encoded).decode("ascii").rstrip("=")
    return f"{body}.{sha256(encoded).hexdigest()}"


def _decode_cursor(
    cursor: str, *, continuation_id: str, collection: str
) -> dict[str, Any]:
    if not isinstance(cursor, str) or not cursor or cursor.count(".") != 1:
        raise ValueError("Invalid continuation history cursor")
    body, checksum = cursor.split(".", 1)
    if not body or len(checksum) != 64:
        raise ValueError("Invalid continuation history cursor")
    try:
        encoded = urlsafe_b64decode(body + ("=" * (-len(body) % 4)))
        if urlsafe_b64encode(encoded).decode("ascii").rstrip("=") != body:
            raise ValueError("Invalid continuation history cursor")
        if sha256(encoded).hexdigest() != checksum:
            raise ValueError("Continuation history cursor checksum mismatch")
        payload = json.loads(encoded.decode("utf-8"))
        canonical = json.dumps(
            payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True
        ).encode("utf-8")
    except ValueError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError):
        raise ValueError("Invalid continuation history cursor") from None
    if canonical != encoded or not isinstance(payload, dict):
        raise ValueError("Invalid continuation history cursor")
    if set(payload) != {"version", "continuation_id", "collection", "position"}:
        raise ValueError("Invalid continuation history cursor")
    if payload["version"] != CONTINUATION_HISTORY_CURSOR_VERSION:
        raise ValueError("Continuation history cursor version mismatch")
    if payload["continuation_id"] != continuation_id:
        raise ValueError("Continuation history cursor continuation mismatch")
    if payload["collection"] != collection:
        raise ValueError("Continuation history cursor collection mismatch")
    position = payload["position"]
    if not isinstance(position, dict):
        raise ValueError("Invalid continuation history cursor position")
    return position


def _history_ref(continuation_id: str, collection: str) -> str:
    return f"continuation:{continuation_id}:{collection}"


class ContinuationService:
    """Small mechanical composition layer over continuation, Task, and Run truth."""

    def __init__(
        self,
        runs_dir: Path,
        *,
        continuation_store: ContinuationStore | None = None,
        task_store: TaskStore | None = None,
        run_store: RunStore | None = None,
    ) -> None:
        root = Path(runs_dir)
        self.continuation_store = continuation_store or ContinuationStore(root)
        self.task_store = task_store or TaskStore(root)
        self.run_store = run_store or RunStore(root)
        db_paths = {
            Path(self.continuation_store.db_path).resolve(),
            Path(self.task_store.db_path).resolve(),
            Path(self.run_store.db_path).resolve(),
        }
        if len(db_paths) != 1:
            raise ValueError("Continuation, Task, and Run readers must share soma.sqlite3")

    def capabilities(self) -> dict[str, Any]:
        return {
            "ok": True,
            "capability": "sol_semantic_continuation",
            "model_version": "continuation.v1",
            "resume_projection_version": CONTINUATION_RESUME_PROJECTION_VERSION,
            "history_cursor_version": CONTINUATION_HISTORY_CURSOR_VERSION,
            "query_operations": [
                "capabilities",
                "list",
                "status",
                "resume",
                "handoffs",
                "effects",
            ],
            "action_operations": [
                "open",
                "update_contract",
                "checkpoint",
                "complete",
                "cancel",
            ],
            "semantic_reentry_only": True,
            "runs_reasoning": False,
            "chooses_next_action": False,
            "continuation_context_ref_is_authorization": False,
            "default_history_limit": CONTINUATION_HISTORY_DEFAULT_LIMIT,
            "maximum_history_limit": CONTINUATION_HISTORY_MAX_LIMIT,
        }

    def status(self, continuation_id: str) -> dict[str, Any]:
        continuation = self.continuation_store.get_continuation(continuation_id)
        current_revision = self.continuation_store.get_contract_revision(
            continuation.current_contract_revision_id
        )
        latest = self.continuation_store.latest_handoff(continuation_id)
        return {
            "ok": True,
            "continuation": self._continuation_projection(continuation),
            "continuation_context_ref": current_revision.contract_revision_id,
            "current_contract": {
                "contract_revision_id": current_revision.contract_revision_id,
                "revision_number": current_revision.revision_number,
                "content_hash": current_revision.content_hash,
                "provenance_class": current_revision.provenance_class,
                "provenance_ref": current_revision.provenance_ref,
                "created_at": current_revision.created_at,
            },
            "latest_handoff": (
                None
                if latest is None
                else {
                    "handoff_id": latest.handoff_id,
                    "contract_revision_id": latest.contract_revision_id,
                    "sequence_number": latest.sequence_number,
                    "content_hash": latest.content_hash,
                    "created_at": latest.created_at,
                }
            ),
            "handoff_count": self.continuation_store.count_handoffs(continuation_id),
            "effect_count": self.continuation_store.count_effect_links(continuation_id),
        }

    def list_continuations(
        self,
        *,
        limit: int = CONTINUATION_HISTORY_DEFAULT_LIMIT,
        cursor: str = "",
    ) -> dict[str, Any]:
        bounded = _bounded_limit(limit)
        before_updated_at = ""
        before_continuation_id = ""
        if cursor:
            position = _decode_cursor(
                cursor, continuation_id="*", collection="continuations"
            )
            if set(position) != {"before_updated_at", "before_continuation_id"}:
                raise ValueError("Invalid continuation list cursor position")
            before_updated_at = position["before_updated_at"]
            before_continuation_id = position["before_continuation_id"]
            if not isinstance(before_updated_at, str) or not before_updated_at:
                raise ValueError("Invalid continuation list cursor position")
            if not isinstance(before_continuation_id, str) or not before_continuation_id:
                raise ValueError("Invalid continuation list cursor position")

        items, has_more = self.continuation_store.page_continuations(
            before_updated_at=before_updated_at,
            before_continuation_id=before_continuation_id,
            limit=bounded,
        )
        next_cursor = ""
        if has_more and items:
            last = items[-1]
            next_cursor = _encode_cursor(
                continuation_id="*",
                collection="continuations",
                position={
                    "before_updated_at": last.updated_at,
                    "before_continuation_id": last.continuation_id,
                },
            )
        return {
            "items": [self._continuation_projection(item) for item in items],
            "count": len(items),
            "total_count": self.continuation_store.count_continuations(),
            "has_more": has_more,
            "next_cursor": next_cursor,
        }

    @staticmethod
    def _continuation_projection(continuation: Any) -> dict[str, Any]:
        return {
            "continuation_id": continuation.continuation_id,
            "label": continuation.label,
            "lifecycle": continuation.lifecycle.value,
            "continuation_context_ref": continuation.current_contract_revision_id,
            "created_at": continuation.created_at,
            "updated_at": continuation.updated_at,
            "closed_at": continuation.closed_at,
        }

    def resume(
        self,
        continuation_id: str,
        *,
        effect_limit: int = CONTINUATION_HISTORY_DEFAULT_LIMIT,
    ) -> dict[str, Any]:
        """Return bounded semantic re-entry material plus current effect truth."""
        limit = _bounded_limit(effect_limit)
        continuation = self.continuation_store.get_continuation(continuation_id)
        current_revision = self.continuation_store.get_contract_revision(
            continuation.current_contract_revision_id
        )
        handoff = self.continuation_store.latest_handoff(continuation_id)
        effect_page = self.effect_history(continuation_id, limit=limit)
        handoff_count = self.continuation_store.count_handoffs(continuation_id)
        effect_count = self.continuation_store.count_effect_links(continuation_id)

        sol_handoff: dict[str, Any] | None = None
        if handoff is not None:
            sol_handoff = self._handoff_projection(handoff)

        return {
            "projection_version": CONTINUATION_RESUME_PROJECTION_VERSION,
            "continuation": {
                "continuation_id": continuation.continuation_id,
                "label": continuation.label,
                "lifecycle": continuation.lifecycle.value,
                "created_at": continuation.created_at,
                "updated_at": continuation.updated_at,
                "closed_at": continuation.closed_at,
            },
            "continuation_context_ref": current_revision.contract_revision_id,
            "controller_instruction": {
                "contract_revision_id": current_revision.contract_revision_id,
                "revision_number": current_revision.revision_number,
                "instruction_text": current_revision.instruction_text,
                "instruction_ref": current_revision.instruction_ref,
                "content_hash": current_revision.content_hash,
                "provenance_class": current_revision.provenance_class,
                "provenance_ref": current_revision.provenance_ref,
                "created_at": current_revision.created_at,
            },
            "sol_handoff": sol_handoff,
            "contract_changed_since_handoff": bool(
                handoff is not None
                and handoff.contract_revision_id
                != current_revision.contract_revision_id
            ),
            "associated_effects": effect_page,
            "retrieval": {
                "handoffs": {
                    "history_ref": _history_ref(continuation_id, "handoffs"),
                    "total_count": handoff_count,
                    "default_limit": CONTINUATION_HISTORY_DEFAULT_LIMIT,
                    "max_limit": CONTINUATION_HISTORY_MAX_LIMIT,
                },
                "effects": {
                    "history_ref": _history_ref(continuation_id, "effects"),
                    "total_count": effect_count,
                    "default_limit": CONTINUATION_HISTORY_DEFAULT_LIMIT,
                    "max_limit": CONTINUATION_HISTORY_MAX_LIMIT,
                    "has_more": effect_page["has_more"],
                    "next_cursor": effect_page["next_cursor"],
                },
            },
        }

    def handoff_history(
        self,
        continuation_id: str,
        *,
        limit: int = CONTINUATION_HISTORY_DEFAULT_LIMIT,
        cursor: str = "",
    ) -> dict[str, Any]:
        """Return one newest-first immutable handoff history page."""
        self.continuation_store.get_continuation(continuation_id)
        bounded = _bounded_limit(limit)
        before_sequence: int | None = None
        if cursor:
            position = _decode_cursor(
                cursor, continuation_id=continuation_id, collection="handoffs"
            )
            if set(position) != {"before_sequence"}:
                raise ValueError("Invalid handoff history cursor position")
            raw = position["before_sequence"]
            if isinstance(raw, bool) or not isinstance(raw, int) or raw < 1:
                raise ValueError("Invalid handoff history cursor position")
            before_sequence = raw

        items, has_more = self.continuation_store.page_handoffs(
            continuation_id,
            before_sequence=before_sequence,
            limit=bounded,
        )
        next_cursor = ""
        if has_more and items:
            next_cursor = _encode_cursor(
                continuation_id=continuation_id,
                collection="handoffs",
                position={"before_sequence": items[-1].sequence_number},
            )
        return {
            "history_ref": _history_ref(continuation_id, "handoffs"),
            "items": [self._handoff_projection(item) for item in items],
            "count": len(items),
            "total_count": self.continuation_store.count_handoffs(continuation_id),
            "has_more": has_more,
            "next_cursor": next_cursor,
        }

    def effect_history(
        self,
        continuation_id: str,
        *,
        limit: int = CONTINUATION_HISTORY_DEFAULT_LIMIT,
        cursor: str = "",
    ) -> dict[str, Any]:
        """Return one bounded origin-link page with current canonical projections."""
        self.continuation_store.get_continuation(continuation_id)
        bounded = _bounded_limit(limit)
        before_created_at = ""
        before_link_id = ""
        if cursor:
            position = _decode_cursor(
                cursor, continuation_id=continuation_id, collection="effects"
            )
            if set(position) != {"before_created_at", "before_link_id"}:
                raise ValueError("Invalid effect history cursor position")
            before_created_at = position["before_created_at"]
            before_link_id = position["before_link_id"]
            if not isinstance(before_created_at, str) or not before_created_at:
                raise ValueError("Invalid effect history cursor position")
            if not isinstance(before_link_id, str) or not before_link_id:
                raise ValueError("Invalid effect history cursor position")

        links, has_more = self.continuation_store.page_effect_links(
            continuation_id,
            before_created_at=before_created_at,
            before_link_id=before_link_id,
            limit=bounded,
        )
        next_cursor = ""
        if has_more and links:
            last = links[-1]
            next_cursor = _encode_cursor(
                continuation_id=continuation_id,
                collection="effects",
                position={
                    "before_created_at": last.created_at,
                    "before_link_id": last.link_id,
                },
            )
        return {
            "history_ref": _history_ref(continuation_id, "effects"),
            "items": [self._effect_projection(link) for link in links],
            "count": len(links),
            "total_count": self.continuation_store.count_effect_links(
                continuation_id
            ),
            "has_more": has_more,
            "next_cursor": next_cursor,
        }

    @staticmethod
    def _handoff_projection(handoff: ContinuationHandoffRecord) -> dict[str, Any]:
        return {
            "handoff_id": handoff.handoff_id,
            "contract_revision_id": handoff.contract_revision_id,
            "sequence_number": handoff.sequence_number,
            "handoff_text": handoff.handoff_text,
            "content_hash": handoff.content_hash,
            "created_at": handoff.created_at,
        }

    def _effect_projection(
        self, link: ContinuationEffectLinkRecord
    ) -> dict[str, Any]:
        base = {
            "link_id": link.link_id,
            "effect_kind": link.effect_kind.value,
            "effect_id": link.effect_id,
            "origin_contract_revision_id": link.contract_revision_id,
            "linked_at": link.created_at,
        }
        if link.effect_kind == ContinuationEffectKind.TASK:
            base["canonical"] = self._task_projection(link.effect_id)
        else:
            base["canonical"] = self._run_projection(link.effect_id)
        return base

    def _task_projection(self, task_id: str) -> dict[str, Any]:
        try:
            task = self.task_store.get_task(task_id)
        except KeyError:
            return {"projection_status": "missing"}
        except Exception as exc:
            return {
                "projection_status": "unavailable",
                "error_type": type(exc).__name__,
            }
        return {
            "projection_status": "available",
            "state": task.state.value,
            "phase": task.phase.value,
            "state_version": task.state_version,
            "result": {
                "result_ref": task.result_ref,
                "result_hash": task.result_hash,
                "evidence_ref": task.evidence_ref,
            },
            "recovery": {
                "state": task.recovery_state.value,
                "reason": task.recovery_reason,
                "reconciled_at": task.reconciled_at,
            },
            "updated_at": task.updated_at,
            "started_at": task.started_at,
            "ended_at": task.ended_at,
        }

    def _run_projection(self, run_id: str) -> dict[str, Any]:
        try:
            summary = self.run_store.get_run_summary(run_id)
        except KeyError:
            return {"projection_status": "missing"}
        except Exception as exc:
            return {
                "projection_status": "unavailable",
                "error_type": type(exc).__name__,
            }

        result: dict[str, Any]
        try:
            public_result = self.run_store.get_public_result_snapshot(run_id)
            result = {
                "projection_status": "available",
                "publication_status": summary["result_publication_status"],
                "published_hash": summary["result_published_hash"],
                "public_result_status": public_result["public_result_status"],
                "public_result": public_result["public_result"],
                "public_result_source_sha256": public_result[
                    "public_result_source_sha256"
                ],
                "public_result_error": public_result["public_result_error"],
            }
        except Exception as exc:
            result = {
                "projection_status": "unavailable",
                "error_type": type(exc).__name__,
            }

        return {
            "projection_status": "available",
            "status": summary["status"],
            "current_phase": summary["current_phase"],
            "state_version": summary["state_version"],
            "summary": summary["summary"],
            "error": summary["error"],
            "safety_failure": summary["safety_failure"],
            "recovery_reason": summary["recovery_reason"],
            "exit_code": summary["exit_code"],
            "started_at": summary["started_at"],
            "ended_at": summary["ended_at"],
            "result": result,
        }
