"""Minimal Sol semantic continuation persistence package."""

from .models import (
    CONTINUATION_MODEL_VERSION,
    CONTINUATION_SCHEMA_COMPONENT,
    CONTINUATION_SCHEMA_VERSION,
    ContinuationEffectKind,
    ContinuationEffectLinkRecord,
    ContinuationHandoffRecord,
    ContinuationLifecycle,
    ContinuationRecord,
    ContractRevisionRecord,
)
from .service import (
    CONTINUATION_HISTORY_CURSOR_VERSION,
    CONTINUATION_HISTORY_DEFAULT_LIMIT,
    CONTINUATION_HISTORY_MAX_LIMIT,
    CONTINUATION_RESUME_PROJECTION_VERSION,
    ContinuationService,
)
from .store import (
    ContinuationClosed,
    ContinuationLifecycleConflict,
    ContinuationRequestConflict,
    ContinuationStore,
    EffectOriginConflict,
    StaleContinuationContract,
)

__all__ = [
    "CONTINUATION_HISTORY_CURSOR_VERSION",
    "CONTINUATION_HISTORY_DEFAULT_LIMIT",
    "CONTINUATION_HISTORY_MAX_LIMIT",
    "CONTINUATION_RESUME_PROJECTION_VERSION",
    "CONTINUATION_MODEL_VERSION",
    "CONTINUATION_SCHEMA_COMPONENT",
    "CONTINUATION_SCHEMA_VERSION",
    "ContinuationClosed",
    "ContinuationEffectKind",
    "ContinuationEffectLinkRecord",
    "ContinuationHandoffRecord",
    "ContinuationLifecycle",
    "ContinuationLifecycleConflict",
    "ContinuationRecord",
    "ContinuationRequestConflict",
    "ContinuationService",
    "ContinuationStore",
    "ContractRevisionRecord",
    "EffectOriginConflict",
    "StaleContinuationContract",
]
