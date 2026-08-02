"""V3-1A interactive worker substrate: subordinate persistence foundation.

Nothing here owns task admission, task state, leases, cancellation, terminal
results, or result publication. Those remain with ``soma.tasks`` (canonical task
plane) and ``soma.run_store``/``soma.job_manager`` (canonical run plane). This
package records the *subordinate facts* an interactive provider worker needs and
that no existing authority represents:

- exact provider-session binding for one canonical task/run;
- crash-safe interaction delivery and acknowledgement evidence;
- controller-checkpoint deadlines and explicit expiry evidence;
- raw provider-native usage events;
- provider-child PID plus process-start identity.

The package has an internal atomic reservation coordinator but no public gateway
or provider transport. Importing it does not migrate the live database; only
constructing :class:`WorkerSubstrateStore` does.
"""

from __future__ import annotations

from .coordinator import (
    InteractionCoordinator,
    InteractionReservation,
    InteractionStateConflict,
)
from .models import (
    CheckpointDeadlinePolicy,
    CheckpointExpiryDisposition,
    InteractionDelivery,
    InteractionKind,
    MessageClass,
    MessageDisposition,
    ProviderChildRole,
    ProviderChildProcessRecord,
    ProviderSessionBinding,
    SessionBindingDisposition,
    TransportAttemptRecord,
    TransportAttemptState,
    WORKER_SUBSTRATE_SCHEMA_COMPONENT,
    WORKER_SUBSTRATE_SCHEMA_VERSION,
    CheckpointDeadline,
    CheckpointExpiryEvent,
    InteractionRecord,
    UsageEvent,
    WorkerMessageRecord,
    message_contract_hash,
    normalize_message_contract,
    usage_dedupe_key,
)
from .schema import WORKER_SUBSTRATE_TABLE_NAMES
from .transitions import (
    InteractionTransitionPolicy,
    WaitTransitionConflict,
    WaitTransitionResult,
)
from .store import (
    AttemptClaimBlocked,
    CanonicalBindingMismatch,
    EvidenceConflict,
    InteractionConflict,
    MessageConflict,
    PayloadReference,
    SessionBindingConflict,
    WorkerSubstrateStore,
)

__all__ = [
    "AttemptClaimBlocked",
    "CanonicalBindingMismatch",
    "CheckpointDeadline",
    "CheckpointDeadlinePolicy",
    "CheckpointExpiryDisposition",
    "CheckpointExpiryEvent",
    "EvidenceConflict",
    "InteractionConflict",
    "InteractionCoordinator",
    "InteractionDelivery",
    "InteractionKind",
    "InteractionReservation",
    "InteractionStateConflict",
    "InteractionTransitionPolicy",
    "InteractionRecord",
    "MessageClass",
    "MessageConflict",
    "MessageDisposition",
    "PayloadReference",
    "ProviderChildProcessRecord",
    "ProviderChildRole",
    "ProviderSessionBinding",
    "SessionBindingConflict",
    "SessionBindingDisposition",
    "TransportAttemptRecord",
    "TransportAttemptState",
    "UsageEvent",
    "WorkerMessageRecord",
    "WORKER_SUBSTRATE_SCHEMA_COMPONENT",
    "WORKER_SUBSTRATE_SCHEMA_VERSION",
    "WORKER_SUBSTRATE_TABLE_NAMES",
    "WaitTransitionConflict",
    "WaitTransitionResult",
    "WorkerSubstrateStore",
    "message_contract_hash",
    "normalize_message_contract",
    "usage_dedupe_key",
]
