from __future__ import annotations

from uuid import uuid4

from codexbridge.run_store import utc_now

from .models import AuditEvent


def create_audit_event(
    *,
    task_id: str,
    action: str,
    message: str,
    metadata: dict[str, object] | None = None,
) -> AuditEvent:
    return AuditEvent(
        event_id=f"local_agent_{uuid4().hex}",
        task_id=task_id,
        timestamp=utc_now(),
        action=action,
        message=message,
        metadata=metadata or {},
    )
