from __future__ import annotations

from uuid import uuid4

from codexbridge.run_store import utc_now


def policy_audit_event(action: str, message: str, metadata: dict | None = None) -> dict:
    return {
        "audit_event_id": f"policy_{uuid4().hex}",
        "timestamp": utc_now(),
        "action": action,
        "message": message,
        "metadata": metadata or {},
    }
