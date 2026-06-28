from __future__ import annotations

import json
from pathlib import Path

from codexbridge.run_store import utc_now

from .models import ApprovalDecision, ApprovalRequest, ApprovalStatus


class ApprovalStore:
    def __init__(self, approvals_dir: Path):
        self.approvals_dir = Path(approvals_dir).resolve()
        self.approvals_dir.mkdir(parents=True, exist_ok=True)

    def create(self, request: ApprovalRequest) -> ApprovalRequest:
        self._path(request.approval_request_id).write_text(
            request.model_dump_json(indent=2), encoding="utf-8"
        )
        return request

    def get(self, approval_request_id: str) -> ApprovalRequest:
        path = self._path(approval_request_id)
        if not path.exists():
            raise KeyError(f"Approval request not found: {approval_request_id}")
        return ApprovalRequest.model_validate_json(path.read_text(encoding="utf-8"))

    def list_pending(self) -> list[ApprovalRequest]:
        return [
            item for item in self.list_all() if item.status == ApprovalStatus.PENDING
        ]

    def list_all(self) -> list[ApprovalRequest]:
        records = []
        for path in self.approvals_dir.glob("*.json"):
            records.append(
                ApprovalRequest.model_validate_json(path.read_text(encoding="utf-8"))
            )
        records.sort(key=lambda item: item.created_at)
        return records

    def record_decision(
        self,
        approval_request_id: str,
        *,
        decided_by: str,
        approved: bool,
        notes: str = "",
    ) -> ApprovalDecision:
        record = self.get(approval_request_id)
        if record.required_approver == "human" and decided_by == "chatgpt" and approved:
            raise PermissionError("ChatGPT cannot approve human-only approval requests")
        record.status = ApprovalStatus.APPROVED if approved else ApprovalStatus.DENIED
        record.decided_at = utc_now()
        record.decided_by = decided_by
        record.decision_notes = notes
        self.create(record)
        return ApprovalDecision(
            approval_request_id=approval_request_id,
            status=record.status,
            decided_by=decided_by,
            decided_at=record.decided_at,
            decision_notes=notes,
        )

    def expire_stale(self) -> int:
        count = 0
        for record in self.list_pending():
            record.status = ApprovalStatus.EXPIRED
            record.decided_at = utc_now()
            record.decision_notes = "Expired by policy store maintenance"
            self.create(record)
            count += 1
        return count

    def _path(self, approval_request_id: str) -> Path:
        safe = approval_request_id.replace("/", "_").replace("\\", "_")
        return self.approvals_dir / f"{safe}.json"
