"""V3-1A provider adapter contract and frozen protocol fixtures.

This package is pure and inert. It builds command specifications without running
them, and parses recorded provider output without contacting a provider. It
registers no MCP gateway, imports no canonical task or run state, and decides
no outcome.

The one thing it exists to do is turn provider protocol drift from a runtime
surprise into a failing test, before Soma launches its first provider process.
"""

from __future__ import annotations

from .claude_code import ClaudeCodeAdapter
from .codex import CodexAdapter
from .contract import (
    AdapterIdentity,
    Capability,
    CapabilityDeclaration,
    CapabilitySupport,
    EventClass,
    ParsedEvent,
    ProtocolDriftError,
    ProviderCapabilities,
    ProviderCommandSpec,
    SessionIdentityOutcome,
    SessionIdentityUnavailable,
    SpecKind,
    StdinMode,
    StreamParseResult,
    UNINFORMATIVE_EVENT_CLASSES,
    UsageExtraction,
    WorkerAdapter,
)
from .fixtures import (
    FixtureIntegrityError,
    FixtureRecord,
    fixture_hash,
    fixtures_for,
    load_manifest,
    read_fixture_lines,
)

#: Adapters are looked up by the same opaque provider identifier the worker
#: substrate stores, so a binding row and an adapter always agree on the name.
ADAPTERS: dict[str, WorkerAdapter] = {
    ClaudeCodeAdapter.identity.provider: ClaudeCodeAdapter(),
    CodexAdapter.identity.provider: CodexAdapter(),
}


def get_adapter(provider: str) -> WorkerAdapter:
    """Return the adapter for a provider, or refuse.

    There is no default adapter. An unrecognised provider is an error, not a
    reason to guess at a protocol.
    """
    try:
        return ADAPTERS[provider]
    except KeyError:
        raise KeyError(
            f"no adapter for provider {provider!r}; known providers: "
            f"{sorted(ADAPTERS)}"
        ) from None


__all__ = [
    "ADAPTERS",
    "AdapterIdentity",
    "Capability",
    "CapabilityDeclaration",
    "CapabilitySupport",
    "ClaudeCodeAdapter",
    "CodexAdapter",
    "EventClass",
    "FixtureIntegrityError",
    "FixtureRecord",
    "ParsedEvent",
    "ProtocolDriftError",
    "ProviderCapabilities",
    "ProviderCommandSpec",
    "SessionIdentityOutcome",
    "SessionIdentityUnavailable",
    "SpecKind",
    "StdinMode",
    "StreamParseResult",
    "UNINFORMATIVE_EVENT_CLASSES",
    "UsageExtraction",
    "WorkerAdapter",
    "fixture_hash",
    "fixtures_for",
    "get_adapter",
    "load_manifest",
    "read_fixture_lines",
]
