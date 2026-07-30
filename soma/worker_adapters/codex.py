"""Codex ``exec --json`` native adapter.

Codex is the provider the pilot measured *less* thoroughly, and this adapter says
so. Steering, stdin prompt delivery, and the failure-event shape are all declared
``UNMEASURED``. The pilot's own correction log is the reason for that caution:
two favourable Codex readings turned out to be artifacts of the test, not
properties of the agent.
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
    coerce_optional_int,
)


PROVIDER: Final[str] = "codex"
PROTOCOL_ID: Final[str] = "codex.exec_json"
PROTOCOL_VERSION: Final[str] = "2026-07-26"

ENVIRONMENT_REMOVE: Final[tuple[str, ...]] = (
    "CODEX_HOME",
    "CODEX_SANDBOX",
    "CODEX_SANDBOX_NETWORK_DISABLED",
    "CLAUDECODE",
    "CLAUDE_CODE_ENTRYPOINT",
)


class CodexAdapter(WorkerAdapter):
    identity = AdapterIdentity(
        adapter_id="soma.adapter.codex",
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
                "pilot Finding 2: thread.started/turn.started/item.started/"
                "item.completed/turn.completed",
            ),
            Capability.SESSION_IDENTITY: CapabilityDeclaration(
                CapabilitySupport.SUPPORTED,
                "pilot Finding 2: stable thread_id",
            ),
            Capability.EXPLICIT_RESUME: CapabilityDeclaration(
                CapabilitySupport.SUPPORTED,
                "pilot Finding 3: exec resume <SESSION_ID> returned a matching "
                "thread_id and recalled prior context",
            ),
            Capability.MID_TURN_STEERING: CapabilityDeclaration(
                CapabilitySupport.UNMEASURED,
                "pilot Finding 10 measured steering on Claude only; no Codex "
                "mid-turn injection was attempted, so this is untested rather "
                "than unsupported",
            ),
            Capability.STDIN_PROMPT: CapabilityDeclaration(
                CapabilitySupport.UNMEASURED,
                "the pilot passed prompts as arguments; the '-' stdin form used "
                "by build_start_spec is documented but was never exercised",
            ),
            Capability.PROVIDER_REPORTED_COST: CapabilityDeclaration(
                CapabilitySupport.NOT_SUPPORTED,
                "pilot Finding 2: Codex reports token counts and no USD; a "
                "conversion needs a pricing authority that does not exist",
            ),
            Capability.TOKEN_BREAKDOWN: CapabilityDeclaration(
                CapabilitySupport.SUPPORTED,
                "pilot Finding 2: turn.completed.usage carries input, cached "
                "input and output token counts",
            ),
            Capability.FAILURE_EVENT_MAPPING: CapabilityDeclaration(
                CapabilitySupport.UNMEASURED,
                "no Codex failure stream was captured; turn.failed is mapped "
                "from documentation and its fixture is labelled "
                "inferred_unverified",
            ),
            Capability.ORPHAN_FREE_ROOT_CANCELLATION: CapabilityDeclaration(
                CapabilitySupport.NOT_SUPPORTED,
                "pilot Finding 4: killing the root left 2 of 5 processes alive, "
                "including the python child doing the work",
            ),
        }
    )

    # -- command construction ------------------------------------------------

    def build_start_spec(
        self,
        *,
        executable_path: str,
        prompt_payload_ref: str,
        working_directory: str = "",
    ) -> ProviderCommandSpec:
        # The trailing '-' asks Codex to read the prompt from stdin. This keeps
        # the prompt out of argv, which is non-negotiable, but the form itself is
        # declared UNMEASURED under Capability.STDIN_PROMPT and must be verified
        # by the first real-launch package before it is trusted.
        return ProviderCommandSpec(
            spec_kind=SpecKind.START,
            executable_path=executable_path,
            argv=("exec", "--json", "-"),
            stdin_mode=StdinMode.TEXT,
            prompt_payload_ref=prompt_payload_ref,
            working_directory=working_directory,
            environment_remove=ENVIRONMENT_REMOVE,
            notes="stdin prompt delivery is unmeasured; verify before first launch",
        )

    def build_resume_spec(
        self,
        *,
        executable_path: str,
        native_session_id: str,
        prompt_payload_ref: str,
        working_directory: str = "",
    ) -> ProviderCommandSpec:
        return ProviderCommandSpec(
            spec_kind=SpecKind.RESUME,
            executable_path=executable_path,
            argv=("exec", "resume", native_session_id, "--json", "-"),
            stdin_mode=StdinMode.TEXT,
            prompt_payload_ref=prompt_payload_ref,
            working_directory=working_directory,
            native_session_id=native_session_id,
            environment_remove=ENVIRONMENT_REMOVE,
        )

    # -- parsing -------------------------------------------------------------

    @staticmethod
    def _thread_id(event: Mapping[str, Any]) -> str:
        value = event.get("thread_id")
        return value if isinstance(value, str) and value else ""

    def classify(self, index: int, event: Mapping[str, Any]) -> ParsedEvent:
        event_type = event.get("type")
        if not isinstance(event_type, str):
            return ParsedEvent(
                index=index,
                event_class=EventClass.UNKNOWN,
                provider_event_type="",
                native_session_id=self._thread_id(event),
                raw=event,
                detail="event has no string type field",
            )
        thread_id = self._thread_id(event)

        if event_type == "thread.started":
            return ParsedEvent(
                index=index,
                event_class=EventClass.SESSION_STARTED,
                provider_event_type=event_type,
                native_session_id=thread_id,
                raw=event,
            )
        if event_type == "turn.started":
            return ParsedEvent(
                index=index,
                event_class=EventClass.PROGRESS,
                provider_event_type=event_type,
                native_session_id=thread_id,
                raw=event,
            )
        if event_type in {"item.started", "item.completed", "item.updated"}:
            return ParsedEvent(
                index=index,
                event_class=EventClass.TOOL_ACTIVITY,
                provider_event_type=event_type,
                native_session_id=thread_id,
                raw=event,
            )
        if event_type == "turn.completed":
            return self._classify_turn_completed(index, event, thread_id)
        if event_type == "turn.failed":
            # This shape was never observed in the accepted pilot. Preserve the
            # event as protocol uncertainty until a genuine capture is reviewed;
            # documentation alone cannot authorise a trusted failure mapping.
            return ParsedEvent(
                index=index,
                event_class=EventClass.UNKNOWN,
                provider_event_type=event_type,
                native_session_id=thread_id,
                raw=event,
                detail="unverified turn.failed shape; failure mapping is unmeasured",
            )

        return ParsedEvent(
            index=index,
            event_class=EventClass.UNKNOWN,
            provider_event_type=event_type,
            native_session_id=thread_id,
            raw=event,
            detail=f"unrecognised event type {event_type!r} for protocol "
            f"{PROTOCOL_VERSION}",
        )

    def _classify_turn_completed(
        self, index: int, event: Mapping[str, Any], thread_id: str
    ) -> ParsedEvent:
        usage_block = event.get("usage")
        usage: UsageExtraction | None = None
        if isinstance(usage_block, dict):
            usage = UsageExtraction(
                event_kind="turn.completed",
                sequence=index,
                raw_event=dict(event),
                # Codex does not identify usage events, so the substrate's dedupe
                # key falls back to sequence plus exact raw-event hash.
                provider_event_id="",
                input_tokens=coerce_optional_int(usage_block.get("input_tokens")),
                cached_input_tokens=coerce_optional_int(
                    usage_block.get("cached_input_tokens")
                ),
                output_tokens=coerce_optional_int(usage_block.get("output_tokens")),
                total_tokens=coerce_optional_int(usage_block.get("total_tokens")),
                # Never derived. Codex reports no money, and inventing a dollar
                # figure from tokens would need a pricing authority Soma lacks.
                provider_reported_cost_usd=None,
            )
        return ParsedEvent(
            index=index,
            event_class=EventClass.PROVIDER_REPORTED_COMPLETION,
            provider_event_type="turn.completed",
            native_session_id=thread_id,
            usage=usage,
            raw=event,
            detail="" if usage is not None else "turn.completed carried no usage block",
        )
