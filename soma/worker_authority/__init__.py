"""V3-2 role-scoped worker authority foundation."""

from .authority import (
    WorkerAuthorityService,
    WorkerOperationRegistry,
    WorkerProtectedAuthorityResolver,
)
from .models import (
    WORKER_AUTHORITY_MODEL_VERSION,
    WORKER_AUTHORITY_SCHEMA_COMPONENT,
    WORKER_AUTHORITY_SCHEMA_VERSION,
    WorkerAuthorizationDecisionV1,
    WorkerAuthorizationDenied,
    WorkerAuthorizationRequestV1,
    WorkerAuthorityConflict,
    WorkerAuthorityRevocationV1,
    WorkerCapabilityGrantIssueV1,
    WorkerCapabilityGrantV1,
    WorkerOperationSpecV1,
    WorkerPrincipalIssueResultV1,
    WorkerPrincipalIssueV1,
    WorkerPrincipalV1,
)
from .store import WorkerAuthorityStore

__all__ = [
    "WORKER_AUTHORITY_MODEL_VERSION",
    "WORKER_AUTHORITY_SCHEMA_COMPONENT",
    "WORKER_AUTHORITY_SCHEMA_VERSION",
    "WorkerAuthorityService",
    "WorkerAuthorityStore",
    "WorkerAuthorizationDecisionV1",
    "WorkerAuthorizationDenied",
    "WorkerAuthorizationRequestV1",
    "WorkerAuthorityConflict",
    "WorkerAuthorityRevocationV1",
    "WorkerCapabilityGrantIssueV1",
    "WorkerCapabilityGrantV1",
    "WorkerOperationRegistry",
    "WorkerOperationSpecV1",
    "WorkerPrincipalIssueResultV1",
    "WorkerPrincipalIssueV1",
    "WorkerPrincipalV1",
    "WorkerProtectedAuthorityResolver",
]
