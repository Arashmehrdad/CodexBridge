"""Claude Code native stream-JSON adapter.

Every capability declaration below cites the measurement that justifies it, all
from the accepted pilot record in ``docs/pilot-acp-1-evidence-2026-07-26.md``.
Where the pilot did not measure something, the declaration says ``UNMEASURED``
rather than guessing in either direction.
"""

from __future__ import annotations

from typing import Any, Final, Mapping

from .contract import (
    AdapterIdentity,
    Capability,
    CapabilityDeclaration,
    CapabilitySupport,
    EventClass,
    ParsedEvent,
    ProviderCapabilities,
    ProviderCommandSpec,
    SpecKind,
    StdinMode,
    UsageExtraction,
    WorkerAdapter,
    coerce_optional_cost,
    coerce_optional_int,
)


PROVIDER: Final[str] = "claude_code"
PROTOCOL_ID: Final[str] = "claude_code.stream_json"
PROTOCOL_VERSION: Final[str] = "2026-07-26"

#: Measured in pilot Finding 8: Claude Code refuses to start inside another
#: Claude Code session, so a supervising agent's markers must be removed. These
#: are declared here and applied by a later process/security package.
ENVIRONMENT_REMOVE: Final[tuple[str, ...]] = (
    "CLAUDECODE",
    "CLAUDE_CODE_ENTRYPOINT",
    "CLAUDE_CODE_SSE_PORT",
    "CLAUDE_CODE_MAX_OUTPUT_TOKENS",
    "CODEX_HOME",
    "CODEX_SANDBOX",
    "CODEX_SANDBOX_NETWORK_DISABLED",
)


class ClaudeCodeAdapter(WorkerAdapter):
    identity = AdapterIdentity(
        adapter_id="soma.adapter.claude_code",
        adapter_version="0.1.0",
        provider=PROVIDER,
        protocol_id=PROTOCOL_ID,
        protocol_version=PROTOCOL_VERSION,
    )
    supported_protocol_versions = frozenset({PROTOCOL_VERSION})
    capabilities = ProviderCapabilities(
        {
            Capability.STRUCTURED_STREAM: CapabilityDeclaration(
                CapabilitySupport.SUPPORTED,
                "pilot Finding 2: system/assistant/user/result/rate_limit_event",
            ),
            Capability.SESSION_IDENTITY: CapabilityDeclaration(
                CapabilitySupport.SUPPORTED,
                "pilot Finding 2: stable session_id, emitted even on a failed run",
            ),
            Capability.EXPLICIT_RESUME: CapabilityDeclaration(
                CapabilitySupport.SUPPORTED,
                "pilot Finding 3: --resume <session_id> returned the same id and "
                "recalled prior context",
            ),
            Capability.MID_TURN_STEERING: CapabilityDeclaration(
                CapabilitySupport.SUPPORTED,
                "pilot Finding 10: a message injected mid-turn over "
                "--input-format stream-json halted the running task",
            ),
            Capability.STDIN_PROMPT: CapabilityDeclaration(
                CapabilitySupport.SUPPORTED,
                "pilot Finding 10: --input-format stream-json is a genuine "
                "bidirectional stdin channel",
            ),
            Capability.PROVIDER_REPORTED_COST: CapabilityDeclaration(
                CapabilitySupport.SUPPORTED,
                "pilot Finding 2: result.total_cost_usd reported $0.1094",
            ),
            Capability.TOKEN_BREAKDOWN: CapabilityDeclaration(
                CapabilitySupport.NOT_SUPPORTED,
                "pilot Finding 2 recorded cost only; no token counts observed, so "
                "token fields stay None rather than being derived from cost",
            ),
            Capability.FAILURE_EVENT_MAPPING: CapabilityDeclaration(
                CapabilitySupport.SUPPORTED,
                "pilot Finding 2: a not-logged-in run returned is_error true "
                "alongside a session_id",
            ),
            Capability.ORPHAN_FREE_ROOT_CANCELLATION: CapabilityDeclaration(
                CapabilitySupport.NOT_SUPPORTED,
                "pilot Finding 4: killing the root left 5 of 6 processes alive, "
                "so Soma owned-tree cancellation is mandatory",
            ),
        }
    )

    # -- command construction ------------------------------------------------

    def _base_argv(self) -> tuple[str, ...]:
        # --verbose is required for stream-json output to include every event.
        return (
            "--print",
            "--output-format",
            "stream-json",
            "--input-format",
            "stream-json",
            "--verbose",
        )

    def build_start_spec(
        self,
        *,
        executable_path: str,
        prompt_payload_ref: str,
        working_directory: str = "",
    ) -> ProviderCommandSpec:
        return ProviderCommandSpec(
            spec_kind=SpecKind.START,
            executable_path=executable_path,
            argv=self._base_argv(),
            stdin_mode=StdinMode.STREAM_JSON,
            prompt_payload_ref=prompt_payload_ref,
            working_directory=working_directory,
            environment_remove=ENVIRONMENT_REMOVE,
            notes=(
                "pilot Finding 10: the npm package ships a native bin/claude.exe, "
                "so the executable must be addressed by full resolved path"
            ),
        )

    def build_resume_spec(
        self,
        *,
        executable_path: str,
        native_session_id: str,
        prompt_payload_ref: str,
        working_directory: str = "",
    ) -> ProviderCommandSpec:
        # Explicit id only. --continue / "resume last" is never constructed,
        # because Soma may supervise several concurrent sessions.
        return ProviderCommandSpec(
            spec_kind=SpecKind.RESUME,
            executable_path=executable_path,
            argv=self._base_argv() + ("--resume", native_session_id),
            stdin_mode=StdinMode.STREAM_JSON,
            prompt_payload_ref=prompt_payload_ref,
            working_directory=working_directory,
            native_session_id=native_session_id,
            environment_remove=ENVIRONMENT_REMOVE,
        )

    # -- parsing -------------------------------------------------------------

    @staticmethod
    def _session_id(event: Mapping[str, Any]) -> str:
        value = event.get("session_id")
        return value if isinstance(value, str) and value else ""

    @staticmethod
    def _has_tool_use(event: Mapping[str, Any]) -> bool:
        message = event.get("message")
        if not isinstance(message, dict):
            return False
        content = message.get("content")
        if not isinstance(content, list):
            return False
        return any(
            isinstance(block, dict) and block.get("type") in {"tool_use", "tool_result"}
            for block in content
        )

    def classify(self, index: int, event: Mapping[str, Any]) -> ParsedEvent:
        event_type = event.get("type")
        if not isinstance(event_type, str):
            return ParsedEvent(
                index=index,
                event_class=EventClass.UNKNOWN,
                provider_event_type="",
                native_session_id=self._session_id(event),
                raw=event,
                detail="event has no string type field",
            )
        session_id = self._session_id(event)

        if event_type == "system":
            return ParsedEvent(
                index=index,
                event_class=EventClass.SESSION_STARTED,
                provider_event_type=event_type,
                native_session_id=session_id,
                raw=event,
                detail=str(event.get("subtype") or ""),
            )
        if event_type == "assistant":
            return ParsedEvent(
                index=index,
                event_class=(
                    EventClass.TOOL_ACTIVITY
                    if self._has_tool_use(event)
                    else EventClass.ASSISTANT_MESSAGE
                ),
                provider_event_type=event_type,
                native_session_id=session_id,
                raw=event,
            )
        if event_type == "user":
            return ParsedEvent(
                index=index,
                event_class=EventClass.TOOL_ACTIVITY,
                provider_event_type=event_type,
                native_session_id=session_id,
                raw=event,
            )
        if event_type == "rate_limit_event":
            return ParsedEvent(
                index=index,
                event_class=EventClass.RATE_LIMIT,
                provider_event_type=event_type,
                native_session_id=session_id,
                raw=event,
            )
        if event_type == "result":
            return self._classify_result(index, event, session_id)

        return ParsedEvent(
            index=index,
            event_class=EventClass.UNKNOWN,
            provider_event_type=event_type,
            native_session_id=session_id,
            raw=event,
            detail=f"unrecognised event type {event_type!r} for protocol "
            f"{PROTOCOL_VERSION}",
        )

    def _classify_result(
        self, index: int, event: Mapping[str, Any], session_id: str
    ) -> ParsedEvent:
        """Classify a terminal result event.

        Completion is asserted only by an explicit ``is_error: false``. A result
        event that omits the marker, or carries a non-boolean, is *not* read as
        success: it becomes an unknown event, because a missing marker is exactly
        the drift this gate exists to catch.
        """
        is_error = event.get("is_error")
        if is_error not in (True, False):
            # The outcome marker is missing or not a boolean. A drifted result is
            # an unknown event and carries no usage: an event Soma cannot read
            # must not contribute a figure either.
            return ParsedEvent(
                index=index,
                event_class=EventClass.UNKNOWN,
                provider_event_type="result",
                native_session_id=session_id,
                raw=event,
                detail=(
                    "result event carried no boolean is_error marker; refusing "
                    "to infer an outcome or accept its usage"
                ),
            )
        usage = UsageExtraction(
            event_kind=f"result.{event.get('subtype') or 'unknown'}",
            sequence=index,
            raw_event=dict(event),
            provider_event_id=session_id,
            # Claude reports money and no token breakdown. Leaving these None is
            # the honest representation; deriving tokens from cost would invent
            # a figure the provider never sent.
            input_tokens=coerce_optional_int(event.get("input_tokens")),
            cached_input_tokens=coerce_optional_int(event.get("cached_input_tokens")),
            output_tokens=coerce_optional_int(event.get("output_tokens")),
            total_tokens=coerce_optional_int(event.get("total_tokens")),
            provider_reported_cost_usd=coerce_optional_cost(
                event.get("total_cost_usd")
            ),
        )
        if is_error is False:
            event_class = EventClass.PROVIDER_REPORTED_COMPLETION
            detail = ""
        else:
            event_class = EventClass.PROVIDER_REPORTED_FAILURE
            detail = str(event.get("subtype") or "")
        return ParsedEvent(
            index=index,
            event_class=event_class,
            provider_event_type="result",
            native_session_id=session_id,
            usage=usage,
            raw=event,
            detail=detail,
        )
