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

The package is inert until a later V3-1A package wires it. Importing it does not
migrate the live database; only constructing :class:`WorkerSubstrateStore` does.
"""

from __future__ import annotations

from .models import (
    CheckpointDeadlinePolicy,
    CheckpointExpiryDisposition,
    InteractionDelivery,
    InteractionKind,
    ProviderChildRole,
    ProviderChildProcessRecord,
    ProviderSessionBinding,
    SessionBindingDisposition,
    WORKER_SUBSTRATE_SCHEMA_COMPONENT,
    WORKER_SUBSTRATE_SCHEMA_VERSION,
    CheckpointDeadline,
    CheckpointExpiryEvent,
    InteractionRecord,
    UsageEvent,
    usage_dedupe_key,
)
from .schema import WORKER_SUBSTRATE_TABLE_NAMES
from .store import (
    CanonicalBindingMismatch,
    EvidenceConflict,
    InteractionConflict,
    PayloadReference,
    SessionBindingConflict,
    WorkerSubstrateStore,
)

__all__ = [
    "CanonicalBindingMismatch",
    "CheckpointDeadline",
    "CheckpointDeadlinePolicy",
    "CheckpointExpiryDisposition",
    "CheckpointExpiryEvent",
    "EvidenceConflict",
    "InteractionConflict",
    "InteractionDelivery",
    "InteractionKind",
    "InteractionRecord",
    "PayloadReference",
    "ProviderChildProcessRecord",
    "ProviderChildRole",
    "ProviderSessionBinding",
    "SessionBindingConflict",
    "SessionBindingDisposition",
    "UsageEvent",
    "WORKER_SUBSTRATE_SCHEMA_COMPONENT",
    "WORKER_SUBSTRATE_SCHEMA_VERSION",
    "WORKER_SUBSTRATE_TABLE_NAMES",
    "WorkerSubstrateStore",
    "usage_dedupe_key",
]
