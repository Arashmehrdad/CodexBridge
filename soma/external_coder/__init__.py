"""Provider-neutral external-coder handoff generation (no invocation)."""

from .context_builder import ExternalCoderContextBuilder
from .handoff_generator import (
    ExternalCoderHandoffGenerator,
    build_handoff_prompt,
    capture_repository_state,
)
from .models import (
    ExternalCoderConstraint,
    ExternalCoderContextFile,
    ExternalCoderContextSnippet,
    ExternalCoderHandoff,
    ExternalCoderHandoffArtifact,
    ExternalCoderHandoffRequest,
    ExternalCoderHandoffResult,
    ExternalCoderHandoffStatus,
    RepositoryStateSnapshot,
)

__all__ = [
    "ExternalCoderConstraint",
    "ExternalCoderContextBuilder",
    "ExternalCoderContextFile",
    "ExternalCoderContextSnippet",
    "ExternalCoderHandoff",
    "ExternalCoderHandoffArtifact",
    "ExternalCoderHandoffGenerator",
    "ExternalCoderHandoffRequest",
    "ExternalCoderHandoffResult",
    "ExternalCoderHandoffStatus",
    "RepositoryStateSnapshot",
    "build_handoff_prompt",
    "capture_repository_state",
]
