"""V3-1A process and security boundary.

Sanitised environment construction, exact executable identity, bounded stand-in
launch with persist-before-attach, and owned-tree cancellation with
zero-descendant proof.

No provider is launched from here and no provider credential is held. Canonical
lifecycle stays with ``RunStore``/``JobManager``; process-start identity and
tree termination stay with ``soma.process_control``; the observations this
module writes are subordinate rows in ``worker_child_processes``.
"""

from __future__ import annotations

from .cancellation import (
    CancellationDisposition,
    CancellationProof,
    TerminationRecord,
    cancel_owned_tree,
    contain_tree,
)
from .environment import (
    BASE_ALLOWLIST,
    EnvironmentEvidence,
    RemovalReason,
    SanitisedEnvironment,
    build_child_environment,
    find_secret_shaped_names,
)
from .executable import (
    ExecutableIdentity,
    ExecutableRejected,
    require_unchanged,
    verify_executable,
)
from .launch import (
    AttachmentDisposition,
    AttachmentResult,
    StandInLaunchRequest,
    launch_stand_in,
    record_descendants,
)

__all__ = [
    "AttachmentDisposition",
    "AttachmentResult",
    "BASE_ALLOWLIST",
    "CancellationDisposition",
    "CancellationProof",
    "EnvironmentEvidence",
    "ExecutableIdentity",
    "ExecutableRejected",
    "RemovalReason",
    "SanitisedEnvironment",
    "StandInLaunchRequest",
    "TerminationRecord",
    "build_child_environment",
    "cancel_owned_tree",
    "contain_tree",
    "find_secret_shaped_names",
    "launch_stand_in",
    "record_descendants",
    "require_unchanged",
    "verify_executable",
]
