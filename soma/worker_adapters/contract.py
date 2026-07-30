"""Provider-neutral internal adapter contract.

This module is pure: it constructs *inert* command specifications and parses
*recorded* provider output. It launches nothing, touches no environment, opens
no socket, and registers no gateway.

Two authority rules shape every type here.

First, nothing in this module may express canonical state. There is no import of
``TaskState``, no ``EventClass`` value that spells a task state, and no method
that returns success. A provider saying "I finished" is a *claim* recorded as
``PROVIDER_REPORTED_COMPLETION``; whether the canonical task completed is decided
by the run plane against the published result, not by a parsed line.

Second, absence never implies capability. :class:`ProviderCapabilities` refuses
construction unless every capability in :class:`Capability` is declared, so a
provider cannot acquire steering support by an adapter author forgetting to
mention it.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from enum import Enum
from hashlib import sha256
from pathlib import PurePosixPath, PureWindowsPath
from typing import Any, Final, Mapping, Sequence


MAX_RAW_EXCERPT_CHARS: Final[int] = 512
PAYLOAD_REFERENCE_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"^worker_payload:[a-f0-9]{64}$"
)


class ProtocolDriftError(ValueError):
    """A stream declared a protocol version this adapter has not been reviewed for."""

    def __init__(self, adapter_id: str, declared: str, supported: frozenset[str]):
        super().__init__(
            f"adapter {adapter_id} supports protocol versions "
            f"{sorted(supported)}; refusing to parse declared version {declared!r}"
        )
        self.adapter_id = adapter_id
        self.declared = declared
        self.supported = frozenset(supported)


class SessionIdentityUnavailable(ValueError):
    """Exact native session identity could not be established from a stream."""

    def __init__(self, outcome: "SessionIdentityOutcome", detail: str):
        super().__init__(f"native session identity {outcome.value}: {detail}")
        self.outcome = outcome
        self.detail = detail


class EventClass(str, Enum):
    """Provider-neutral classification of one recorded protocol event.

    Every value is either an observation or an explicit non-answer. None of them
    is a task state, and a test pins that: an event class must never be
    projectable as canonical state.

    ``PROVIDER_REPORTED_COMPLETION`` and ``PROVIDER_REPORTED_FAILURE`` are named
    for what they are. The provider asserted an outcome; Soma recorded the
    assertion.
    """

    SESSION_STARTED = "session_started"
    PROGRESS = "progress"
    ASSISTANT_MESSAGE = "assistant_message"
    TOOL_ACTIVITY = "tool_activity"
    PROVIDER_REPORTED_COMPLETION = "provider_reported_completion"
    PROVIDER_REPORTED_FAILURE = "provider_reported_failure"
    RATE_LIMIT = "rate_limit"
    UNKNOWN = "unknown"
    MALFORMED = "malformed"


#: Classes that carry no information about progress. A stream made only of these
#: has told Soma nothing, which is the correct reading of provider drift.
UNINFORMATIVE_EVENT_CLASSES: Final[frozenset[EventClass]] = frozenset(
    {EventClass.UNKNOWN, EventClass.MALFORMED}
)


class SessionIdentityOutcome(str, Enum):
    RESOLVED = "resolved"
    MISSING = "missing"
    CONFLICTING = "conflicting"


class Capability(str, Enum):
    """Everything a caller may need to know before choosing a provider."""

    STRUCTURED_STREAM = "structured_stream"
    SESSION_IDENTITY = "session_identity"
    EXPLICIT_RESUME = "explicit_resume"
    MID_TURN_STEERING = "mid_turn_steering"
    STDIN_PROMPT = "stdin_prompt"
    PROVIDER_REPORTED_COST = "provider_reported_cost"
    TOKEN_BREAKDOWN = "token_breakdown"
    FAILURE_EVENT_MAPPING = "failure_event_mapping"
    ORPHAN_FREE_ROOT_CANCELLATION = "orphan_free_root_cancellation"


class CapabilitySupport(str, Enum):
    """Three-valued on purpose.

    ``UNMEASURED`` exists so an adapter can say "nobody has tested this" instead
    of choosing between two lies. The pilot's own correction log is the reason:
    an unmeasured Codex behaviour was twice read as a measured one.
    """

    SUPPORTED = "supported"
    NOT_SUPPORTED = "not_supported"
    UNMEASURED = "unmeasured"


@dataclass(frozen=True)
class CapabilityDeclaration:
    support: CapabilitySupport
    evidence: str

    def __post_init__(self) -> None:
        if not self.evidence.strip():
            raise ValueError("every capability declaration must cite its evidence")


@dataclass(frozen=True)
class ProviderCapabilities:
    """A complete declaration. Partial declarations are refused, not defaulted."""

    declarations: Mapping[Capability, CapabilityDeclaration]

    def __post_init__(self) -> None:
        missing = set(Capability) - set(self.declarations)
        if missing:
            raise ValueError(
                "capability declaration is incomplete; absence is never support. "
                f"Undeclared: {sorted(item.value for item in missing)}"
            )

    def support(self, capability: Capability) -> CapabilitySupport:
        return self.declarations[capability].support

    def is_supported(self, capability: Capability) -> bool:
        """True only for a measured yes. ``UNMEASURED`` is not a yes."""
        return self.support(capability) is CapabilitySupport.SUPPORTED

    def to_dict(self) -> dict[str, dict[str, str]]:
        return {
            capability.value: {
                "support": declaration.support.value,
                "evidence": declaration.evidence,
            }
            for capability, declaration in sorted(
                self.declarations.items(), key=lambda item: item[0].value
            )
        }


@dataclass(frozen=True)
class AdapterIdentity:
    adapter_id: str
    adapter_version: str
    provider: str
    protocol_id: str
    protocol_version: str

    def to_dict(self) -> dict[str, str]:
        return {
            "adapter_id": self.adapter_id,
            "adapter_version": self.adapter_version,
            "provider": self.provider,
            "protocol_id": self.protocol_id,
            "protocol_version": self.protocol_version,
        }


class StdinMode(str, Enum):
    NONE = "none"
    TEXT = "text"
    STREAM_JSON = "stream_json"


class SpecKind(str, Enum):
    START = "start"
    RESUME = "resume"


@dataclass(frozen=True)
class ProviderCommandSpec:
    """An inert description of a command. Nothing here runs it.

    The prompt is carried as ``prompt_payload_ref`` -- a worker-substrate
    content-addressed reference -- and never as an argv element. ``validate``
    enforces that structurally rather than trusting each call site, because the
    pilot's measured requirement is absolute: prompts and secrets must not reach
    a command line.

    ``environment_remove`` and ``environment_allowlist`` are *declarations*. This
    package does not sanitise or apply an environment; a later process/security
    package does, and it reads these.
    """

    spec_kind: SpecKind
    executable_path: str
    argv: tuple[str, ...]
    stdin_mode: StdinMode
    prompt_payload_ref: str = ""
    working_directory: str = ""
    native_session_id: str = ""
    environment_remove: tuple[str, ...] = ()
    environment_allowlist: tuple[str, ...] = ()
    notes: str = ""

    def __post_init__(self) -> None:
        self.validate()

    def validate(self) -> None:
        executable = self.executable_path
        if not isinstance(executable, str) or not executable.strip():
            raise ValueError("executable_path is required and must be fully resolved")
        windows_path = PureWindowsPath(executable)
        posix_path = PurePosixPath(executable)
        is_absolute = windows_path.is_absolute() or posix_path.is_absolute()
        path_parts = windows_path.parts if windows_path.is_absolute() else posix_path.parts
        if "\x00" in executable or not is_absolute or ".." in path_parts:
            raise ValueError(
                "executable_path must be an absolute resolved path, not a PATH lookup"
            )
        if self.spec_kind is SpecKind.RESUME and (
            not isinstance(self.native_session_id, str)
            or not self.native_session_id.strip()
        ):
            raise ValueError(
                "a resume specification requires an exact native session id; "
                "resume-last is forbidden"
            )
        for index, item in enumerate(self.argv):
            if item.startswith("worker_payload:"):
                raise ValueError(
                    f"argv[{index}] carries a payload reference; prompt content "
                    "must travel on stdin"
                )
        if not self.prompt_payload_ref:
            raise ValueError("a content-addressed prompt_payload_ref is required")
        if self.stdin_mode is StdinMode.NONE and self.prompt_payload_ref:
            raise ValueError("a prompt payload reference requires a stdin mode")
        if self.prompt_payload_ref and PAYLOAD_REFERENCE_PATTERN.fullmatch(
            self.prompt_payload_ref
        ) is None:
            raise ValueError(
                "prompt_payload_ref must be worker_payload:<lowercase sha256>"
            )

    def contains_in_argv(self, needle: str) -> bool:
        """Test helper: does any argv element carry this text?"""
        return any(needle in item for item in self.argv)

    def to_dict(self) -> dict[str, Any]:
        return {
            "spec_kind": self.spec_kind.value,
            "executable_path": self.executable_path,
            "argv": list(self.argv),
            "stdin_mode": self.stdin_mode.value,
            "prompt_payload_ref": self.prompt_payload_ref,
            "working_directory": self.working_directory,
            "native_session_id": self.native_session_id,
            "environment_remove": list(self.environment_remove),
            "environment_allowlist": list(self.environment_allowlist),
            "notes": self.notes,
        }


@dataclass(frozen=True)
class UsageExtraction:
    """Raw provider usage in exactly the worker-substrate field names.

    Field names match :class:`soma.worker_substrate.models.UsageEvent` so an
    extraction can be handed straight to ``record_usage_event`` with no
    translation layer that could quietly invent a value. Every count is optional
    and ``None`` means *the provider did not report it*.
    """

    event_kind: str
    sequence: int
    raw_event: Mapping[str, Any]
    provider_event_id: str = ""
    input_tokens: int | None = None
    cached_input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    provider_reported_cost_usd: str | None = None

    def __post_init__(self) -> None:
        if isinstance(self.sequence, bool) or not isinstance(self.sequence, int) or self.sequence < 0:
            raise ValueError("usage sequence must be a non-negative integer")
        for field_name in (
            "input_tokens",
            "cached_input_tokens",
            "output_tokens",
            "total_tokens",
        ):
            value = getattr(self, field_name)
            if value is not None and (
                isinstance(value, bool) or not isinstance(value, int) or value < 0
            ):
                raise ValueError(f"{field_name} must be a non-negative integer or None")
        if self.provider_reported_cost_usd is not None and (
            coerce_optional_cost(self.provider_reported_cost_usd)
            != self.provider_reported_cost_usd
        ):
            raise ValueError(
                "provider_reported_cost_usd must be finite, non-negative provider text"
            )

    def to_record_kwargs(self) -> dict[str, Any]:
        return {
            "event_kind": self.event_kind,
            "sequence": self.sequence,
            "raw_event": dict(self.raw_event),
            "provider_event_id": self.provider_event_id,
            "input_tokens": self.input_tokens,
            "cached_input_tokens": self.cached_input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.total_tokens,
            "provider_reported_cost_usd": self.provider_reported_cost_usd,
        }


@dataclass(frozen=True)
class ParsedEvent:
    index: int
    event_class: EventClass
    provider_event_type: str
    native_session_id: str = ""
    usage: UsageExtraction | None = None
    raw: Mapping[str, Any] | None = None
    raw_excerpt: str = ""
    raw_sha256: str = ""
    raw_bytes: int = 0
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "event_class": self.event_class.value,
            "provider_event_type": self.provider_event_type,
            "native_session_id": self.native_session_id,
            "usage": None if self.usage is None else self.usage.to_record_kwargs(),
            "raw_excerpt": self.raw_excerpt,
            "raw_sha256": self.raw_sha256,
            "raw_bytes": self.raw_bytes,
            "detail": self.detail,
        }


@dataclass(frozen=True)
class StreamParseResult:
    adapter: AdapterIdentity
    events: tuple[ParsedEvent, ...]
    identity_outcome: SessionIdentityOutcome
    native_session_id: str = ""
    observed_identities: tuple[str, ...] = ()
    identity_detail: str = ""

    @property
    def unknown_event_count(self) -> int:
        return sum(1 for e in self.events if e.event_class is EventClass.UNKNOWN)

    @property
    def malformed_line_count(self) -> int:
        return sum(1 for e in self.events if e.event_class is EventClass.MALFORMED)

    @property
    def raw_usage_extractions(self) -> tuple[UsageExtraction, ...]:
        """Every syntactically extracted usage claim, including uncertain streams."""
        return tuple(e.usage for e in self.events if e.usage is not None)

    @property
    def provider_claimed_completion(self) -> bool:
        """Whether any parsed event carried a recognised completion claim."""
        return any(
            e.event_class is EventClass.PROVIDER_REPORTED_COMPLETION
            for e in self.events
        )

    @property
    def provider_claimed_failure(self) -> bool:
        """Whether any parsed event carried a recognised failure claim."""
        return any(
            e.event_class is EventClass.PROVIDER_REPORTED_FAILURE for e in self.events
        )

    @property
    def protocol_uncertain(self) -> bool:
        """True when the whole stream is unsafe for trusted outcome or usage projection.

        One unknown or malformed line may hide a changed outcome, identity, or
        usage contract. A missing/conflicting identity or competing terminal
        claims is equally unsafe. The parsed events remain available as evidence,
        but trusted completion/failure and usage projections fail closed.
        """
        terminal_claims = sum(
            1
            for event in self.events
            if event.event_class
            in {
                EventClass.PROVIDER_REPORTED_COMPLETION,
                EventClass.PROVIDER_REPORTED_FAILURE,
            }
        )
        return (
            self.identity_outcome is not SessionIdentityOutcome.RESOLVED
            or self.unknown_event_count > 0
            or self.malformed_line_count > 0
            or terminal_claims > 1
        )

    @property
    def usage_extractions(self) -> tuple[UsageExtraction, ...]:
        """Usage safe to persist; uncertain streams expose none."""
        return () if self.protocol_uncertain else self.raw_usage_extractions

    @property
    def provider_reported_completion(self) -> bool:
        """A recognised completion claim from a protocol-trusted stream.

        This remains only a provider claim, never canonical task success. Unknown,
        malformed, identity-uncertain, or competing-terminal streams return False
        even when one line resembles a known completion marker.
        """
        return (
            not self.protocol_uncertain
            and self.provider_claimed_completion
            and not self.provider_claimed_failure
        )

    @property
    def provider_reported_failure(self) -> bool:
        """A recognised failure claim from a protocol-trusted stream."""
        return (
            not self.protocol_uncertain
            and self.provider_claimed_failure
            and not self.provider_claimed_completion
        )

    def require_native_session_id(self) -> str:
        """Return the exact identity, or refuse.

        Binding a run to a session Soma cannot pin exactly is the failure this
        raises to prevent. Missing identity refuses; two identities in one stream
        is protocol uncertainty, not a choice between them.
        """
        if self.identity_outcome is not SessionIdentityOutcome.RESOLVED:
            raise SessionIdentityUnavailable(
                self.identity_outcome, self.identity_detail
            )
        return self.native_session_id

    def to_dict(self) -> dict[str, Any]:
        return {
            "adapter": self.adapter.to_dict(),
            "identity_outcome": self.identity_outcome.value,
            "native_session_id": self.native_session_id,
            "observed_identities": list(self.observed_identities),
            "event_classes": [e.event_class.value for e in self.events],
            "unknown_event_count": self.unknown_event_count,
            "malformed_line_count": self.malformed_line_count,
            "protocol_uncertain": self.protocol_uncertain,
            "provider_claimed_completion": self.provider_claimed_completion,
            "provider_claimed_failure": self.provider_claimed_failure,
            "provider_reported_completion": self.provider_reported_completion,
            "provider_reported_failure": self.provider_reported_failure,
        }


class WorkerAdapter:
    """Base class every provider adapter implements.

    Subclasses supply identity, capabilities, command construction, and per-event
    classification. This class owns the parts that must not vary between
    providers: protocol-version gating, malformed-line containment, and session
    identity resolution including the conflict rule.
    """

    identity: AdapterIdentity
    capabilities: ProviderCapabilities
    supported_protocol_versions: frozenset[str]

    # -- command construction ------------------------------------------------

    def build_start_spec(
        self,
        *,
        executable_path: str,
        prompt_payload_ref: str,
        working_directory: str = "",
    ) -> ProviderCommandSpec:
        raise NotImplementedError

    def build_resume_spec(
        self,
        *,
        executable_path: str,
        native_session_id: str,
        prompt_payload_ref: str,
        working_directory: str = "",
    ) -> ProviderCommandSpec:
        raise NotImplementedError

    # -- parsing -------------------------------------------------------------

    def classify(self, index: int, event: Mapping[str, Any]) -> ParsedEvent:
        raise NotImplementedError

    def parse_stream(
        self, lines: Sequence[str], *, declared_protocol_version: str | None = None
    ) -> StreamParseResult:
        version = (
            self.identity.protocol_version
            if declared_protocol_version is None
            else declared_protocol_version
        )
        if version not in self.supported_protocol_versions:
            raise ProtocolDriftError(
                self.identity.adapter_id, version, self.supported_protocol_versions
            )

        events: list[ParsedEvent] = []
        for index, line in enumerate(lines):
            text = line.strip()
            if not text:
                continue
            try:
                decoded = json.loads(text)
            except json.JSONDecodeError as exc:
                # Do not copy malformed provider bytes into ordinary evidence: a
                # truncated line may contain credentials or private prompt text.
                # Preserve an exact fingerprint and byte count plus a bounded
                # non-secret marker. A later protected-evidence layer may retain
                # the original bytes under its own policy.
                raw_bytes = text.encode("utf-8")
                digest = sha256(raw_bytes).hexdigest()
                events.append(
                    ParsedEvent(
                        index=index,
                        event_class=EventClass.MALFORMED,
                        provider_event_type="",
                        raw_excerpt=f"[malformed provider line withheld sha256={digest}]",
                        raw_sha256=digest,
                        raw_bytes=len(raw_bytes),
                        detail=f"json decode error: {exc.msg}",
                    )
                )
                continue
            if not isinstance(decoded, dict):
                raw_bytes = text.encode("utf-8")
                digest = sha256(raw_bytes).hexdigest()
                events.append(
                    ParsedEvent(
                        index=index,
                        event_class=EventClass.MALFORMED,
                        provider_event_type="",
                        raw_excerpt=f"[non-object provider line withheld sha256={digest}]",
                        raw_sha256=digest,
                        raw_bytes=len(raw_bytes),
                        detail="top-level event is not an object",
                    )
                )
                continue
            events.append(self.classify(index, decoded))

        return self._resolve_identity(tuple(events))

    def _resolve_identity(self, events: tuple[ParsedEvent, ...]) -> StreamParseResult:
        # Exact bytes, no case folding: two spellings are two identities.
        observed: list[str] = []
        for event in events:
            if event.native_session_id and event.native_session_id not in observed:
                observed.append(event.native_session_id)

        if not observed:
            return StreamParseResult(
                adapter=self.identity,
                events=events,
                identity_outcome=SessionIdentityOutcome.MISSING,
                identity_detail="no event carried a native session identity",
            )
        if len(observed) > 1:
            return StreamParseResult(
                adapter=self.identity,
                events=events,
                identity_outcome=SessionIdentityOutcome.CONFLICTING,
                observed_identities=tuple(observed),
                identity_detail=(
                    "one stream reported "
                    f"{len(observed)} distinct native session identities"
                ),
            )
        return StreamParseResult(
            adapter=self.identity,
            events=events,
            identity_outcome=SessionIdentityOutcome.RESOLVED,
            native_session_id=observed[0],
            observed_identities=tuple(observed),
        )


def coerce_optional_int(value: Any) -> int | None:
    """Return an int only for a genuine integer figure, otherwise ``None``.

    A provider sending a string, a float, or nothing at all yields ``None``
    rather than a coerced number, because a guessed count is worse than a
    missing one.
    """
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


def coerce_optional_cost(value: Any) -> str | None:
    """Preserve a provider-reported cost exactly, as text.

    ``repr`` of a float would introduce Soma's formatting into provider
    evidence, so an int/float is rendered with ``repr`` only after being
    recognised as a number, and any other type is refused rather than stringified.
    """
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, str):
        if not value.strip():
            return None
        candidate = value.strip()
        preserved = value
    elif isinstance(value, (int, float)):
        candidate = repr(value)
        preserved = candidate
    else:
        return None
    try:
        parsed = Decimal(candidate)
    except (InvalidOperation, ValueError):
        return None
    if not parsed.is_finite() or parsed < 0:
        return None
    return preserved
