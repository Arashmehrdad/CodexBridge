"""Strict non-secret contracts for the isolated V3-2 worker MCP source boundary."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class WorkerInvokeRequestV1(_StrictModel):
    grant_id: str = Field(min_length=1, max_length=128)
    parameters: dict[str, Any] = Field(default_factory=dict)
    expected_task_state_version: int = Field(ge=0)
    controller_request_id: str = Field(min_length=1, max_length=128)


class WorkerGatewayErrorV1(_StrictModel):
    code: str = Field(min_length=1, max_length=128)
    detail: str = Field(min_length=1, max_length=512)


class WorkerCapabilityProjectionV1(_StrictModel):
    grant_id: str
    intent_ref: str
    intent_hash: str
    operation_ref: str
    operation_hash: str
    operation_kind: Literal["query", "action", "protected_mutation"]
    parameter_contract: dict[str, Any]
    parameter_contract_hash: str
    task_state: str
    task_state_version: int
    expires_at: datetime


class WorkerCapabilitiesSuccessV1(_StrictModel):
    ok: Literal[True] = True
    principal_id: str
    capabilities: tuple[WorkerCapabilityProjectionV1, ...]


class WorkerInvokeSuccessV1(_StrictModel):
    ok: Literal[True] = True
    principal_id: str
    grant_id: str
    operation_ref: str
    controller_request_id: str
    result: Any


class WorkerGatewayFailureV1(_StrictModel):
    ok: Literal[False] = False
    error: WorkerGatewayErrorV1
