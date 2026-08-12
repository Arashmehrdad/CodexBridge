"""Authoritative human-facing metadata for Soma's public 32-tool surface."""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Final, Mapping

from soma.public_gateway_inventory import PUBLIC_GATEWAY_NAMES


ANNOTATION_KEYS: Final[frozenset[str]] = frozenset(
    {
        "readOnlyHint",
        "destructiveHint",
        "idempotentHint",
        "openWorldHint",
    }
)


@dataclass(frozen=True)
class PublicToolMetadata:
    """One public tool's ChatGPT/MCP presentation metadata."""

    name: str
    title: str
    description: str
    invoking: str
    invoked: str
    annotations: Mapping[str, bool]

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("public tool metadata name must not be empty")
        if not self.title:
            raise ValueError(f"{self.name}: title must not be empty")
        if not self.description.startswith("Use this when"):
            raise ValueError(f"{self.name}: description must begin 'Use this when'")
        if len(self.invoking) > 64 or len(self.invoked) > 64:
            raise ValueError(f"{self.name}: invocation labels must be <= 64 characters")
        if set(self.annotations) != ANNOTATION_KEYS:
            raise ValueError(
                f"{self.name}: annotations must contain exactly {sorted(ANNOTATION_KEYS)}"
            )
        if any(type(value) is not bool for value in self.annotations.values()):
            raise ValueError(f"{self.name}: annotation values must be booleans")


def _annotations(
    *,
    read_only: bool,
    destructive: bool,
    idempotent: bool,
    open_world: bool,
) -> Mapping[str, bool]:
    return MappingProxyType(
        {
            "readOnlyHint": read_only,
            "destructiveHint": destructive,
            "idempotentHint": idempotent,
            "openWorldHint": open_world,
        }
    )


def _record(
    name: str,
    *,
    title: str,
    description: str,
    invoking: str,
    invoked: str,
    read_only: bool,
    destructive: bool,
    idempotent: bool,
    open_world: bool,
) -> PublicToolMetadata:
    return PublicToolMetadata(
        name=name,
        title=title,
        description=description,
        invoking=invoking,
        invoked=invoked,
        annotations=_annotations(
            read_only=read_only,
            destructive=destructive,
            idempotent=idempotent,
            open_world=open_world,
        ),
    )


PUBLIC_TOOL_METADATA: Final[Mapping[str, PublicToolMetadata]] = MappingProxyType(
    {
        "ssh_inspect": _record(
            "ssh_inspect",
            title="Inspect SSH host",
            description=(
                "Use this when you need to check whether an authorized SSH host, "
                "tunnel, or service is reachable, or inspect live read-only SSH "
                "health, environment, GPU telemetry, logs, files, services, Git, "
                "or Docker state. Do not use it to change the host."
            ),
            invoking="Inspecting SSH host...",
            invoked="SSH inspection ready",
            read_only=True,
            destructive=False,
            idempotent=True,
            open_world=True,
        ),
        "docker_query": _record(
            "docker_query",
            title="Inspect Docker",
            description=(
                "Use this when you need Docker capabilities, health, container or "
                "Compose inspection without changing Docker state. Do not use it "
                "to start, stop, remove, or prune resources."
            ),
            invoking="Inspecting Docker...",
            invoked="Docker inspection ready",
            read_only=True,
            destructive=False,
            idempotent=True,
            open_world=False,
        ),
        "docker_action": _record(
            "docker_action",
            title="Control Docker",
            description=(
                "Use this when the user explicitly wants a bounded Docker build, "
                "pull, create, start, stop, restart, pause, unpause, exec, "
                "removal, kill, or prune action. Use docker_query for inspection; "
                "some actions can discard resources."
            ),
            invoking="Updating Docker...",
            invoked="Docker action submitted",
            read_only=False,
            destructive=True,
            idempotent=False,
            open_world=True,
        ),
        "cloudflare_query": _record(
            "cloudflare_query",
            title="Inspect Cloudflare",
            description=(
                "Use this when you need authorized Cloudflare capabilities, health, "
                "DNS, ruleset, tunnel, cache, or zone information without changing "
                "Cloudflare."
            ),
            invoking="Inspecting Cloudflare...",
            invoked="Cloudflare inspection ready",
            read_only=True,
            destructive=False,
            idempotent=True,
            open_world=True,
        ),
        "cloudflare_action": _record(
            "cloudflare_action",
            title="Change Cloudflare",
            description=(
                "Use this when the user explicitly wants to create, update, delete, "
                "purge, rotate, or otherwise change authorized Cloudflare DNS, "
                "ruleset, Turnstile, tunnel, cache, SSL, or zone state. Use "
                "cloudflare_query for inspection."
            ),
            invoking="Updating Cloudflare...",
            invoked="Cloudflare action submitted",
            read_only=False,
            destructive=True,
            idempotent=False,
            open_world=True,
        ),
        "ssh_query": _record(
            "ssh_query",
            title="Inspect or prepare SSH",
            description=(
                "Use this when you need SSH capabilities, profile status, project "
                "bindings, credential probes, profile previews, or fresh host "
                "capability validation. Some operations persist local evidence or "
                "reach the host; use ssh_action for changes."
            ),
            invoking="Inspecting SSH configuration...",
            invoked="SSH configuration ready",
            read_only=False,
            destructive=False,
            idempotent=False,
            open_world=True,
        ),
        "ssh_action": _record(
            "ssh_action",
            title="Run SSH action",
            description=(
                "Use this when the user explicitly wants an authorized remote SSH "
                "command, reviewed script, root shell, administration change, "
                "transfer, deployment, or profile activation. This surface can "
                "change or remove remote state."
            ),
            invoking="Running SSH action...",
            invoked="SSH action submitted",
            read_only=False,
            destructive=True,
            idempotent=False,
            open_world=True,
        ),
        "run_start": _record(
            "run_start",
            title="Start durable command",
            description=(
                "Use this when the user explicitly wants to run tests, scripts, "
                "PowerShell, or a Hermes operation as durable local or remote "
                "execution. The command surface is unrestricted enough to "
                "overwrite, delete, or reach external systems; do not use it for "
                "inspection."
            ),
            invoking="Starting durable command...",
            invoked="Durable command started",
            read_only=False,
            destructive=True,
            idempotent=False,
            open_world=True,
        ),
        "workflow_query": _record(
            "workflow_query",
            title="Inspect workflow",
            description=(
                "Use this when you need durable workflow status, events, or results "
                "without advancing or cancelling the workflow."
            ),
            invoking="Inspecting workflow...",
            invoked="Workflow status ready",
            read_only=True,
            destructive=False,
            idempotent=True,
            open_world=False,
        ),
        "workflow_action": _record(
            "workflow_action",
            title="Control workflow",
            description=(
                "Use this when the user explicitly wants to start or cancel a "
                "validated durable workflow. Workflow steps can launch allowlisted "
                "project commands that may write files."
            ),
            invoking="Updating workflow...",
            invoked="Workflow action submitted",
            read_only=False,
            destructive=True,
            idempotent=False,
            open_world=True,
        ),
        "cancel_run": _record(
            "cancel_run",
            title="Cancel durable run",
            description=(
                "Use this when the user explicitly wants to cancel one exact known "
                "durable run or PowerShell command group. Do not use it as a broad "
                "process-kill tool."
            ),
            invoking="Cancelling durable run...",
            invoked="Run cancellation complete",
            read_only=False,
            destructive=True,
            idempotent=False,
            open_world=False,
        ),
        "run_query": _record(
            "run_query",
            title="Inspect durable run",
            description=(
                "Use this when you need durable run status, input, output, events, "
                "terminal evidence, results, summaries, locks, or repository "
                "preflight without launching or cancelling work."
            ),
            invoking="Inspecting durable run...",
            invoked="Run evidence ready",
            read_only=True,
            destructive=False,
            idempotent=True,
            open_world=False,
        ),
        "task_query": _record(
            "task_query",
            title="Inspect task",
            description=(
                "Use this when you need canonical task capabilities, status, result, "
                "events, links, or quarantine evidence without changing the task."
            ),
            invoking="Inspecting task...",
            invoked="Task evidence ready",
            read_only=True,
            destructive=False,
            idempotent=True,
            open_world=False,
        ),
        "task_action": _record(
            "task_action",
            title="Control task",
            description=(
                "Use this when the user explicitly wants to start, steer, supply "
                "input to, cancel, or resolve one canonical task. Task start "
                "delegates to the durable execution backend and can have "
                "unrestricted command effects."
            ),
            invoking="Updating task...",
            invoked="Task action submitted",
            read_only=False,
            destructive=True,
            idempotent=False,
            open_world=True,
        ),
        "system_query": _record(
            "system_query",
            title="Inspect Soma service",
            description=(
                "Use this when you need Soma capabilities, self-checks, configuration "
                "validation, local-model health, capability identity, or reload "
                "status without changing the running service."
            ),
            invoking="Inspecting Soma service...",
            invoked="Soma service status ready",
            read_only=True,
            destructive=False,
            idempotent=True,
            open_world=False,
        ),
        "system_action": _record(
            "system_action",
            title="Reload Soma service",
            description=(
                "Use this when the user explicitly wants a validated Soma module "
                "reload or last-known-good rollback. Do not use it for ordinary "
                "health or configuration inspection."
            ),
            invoking="Updating Soma service...",
            invoked="Soma service update complete",
            read_only=False,
            destructive=False,
            idempotent=False,
            open_world=False,
        ),
        "supervisor_query": _record(
            "supervisor_query",
            title="Inspect supervisor",
            description=(
                "Use this when you need durable supervisor status, events, results, "
                "notifications, or a resume prompt without advancing the supervisor."
            ),
            invoking="Inspecting supervisor...",
            invoked="Supervisor evidence ready",
            read_only=True,
            destructive=False,
            idempotent=True,
            open_world=False,
        ),
        "supervisor_action": _record(
            "supervisor_action",
            title="Control supervisor",
            description=(
                "Use this when the user explicitly wants to start, resume, pause, "
                "or cancel a durable supervisor. Start and resume can advance child "
                "execution; cancel can terminate an active child."
            ),
            invoking="Updating supervisor...",
            invoked="Supervisor action complete",
            read_only=False,
            destructive=True,
            idempotent=False,
            open_world=True,
        ),
        "trading_query": _record(
            "trading_query",
            title="Inspect Trading Lab",
            description=(
                "Use this when you need Trading Lab journal, market/provider, runtime, "
                "or companion information. Some operations contact the configured "
                "MT5/provider or synchronize durable journal links; use "
                "trading_runtime_control for explicit runtime actions."
            ),
            invoking="Inspecting Trading Lab...",
            invoked="Trading Lab information ready",
            read_only=False,
            destructive=False,
            idempotent=False,
            open_world=True,
        ),
        "trading_signal_submit": _record(
            "trading_signal_submit",
            title="Record trading signal",
            description=(
                "Use this when you need to store one packet-bound Trading Lab signal "
                "or NO_TRADE decision in the local journal. This tool does not submit "
                "a broker order."
            ),
            invoking="Recording trading signal...",
            invoked="Trading signal recorded",
            read_only=False,
            destructive=False,
            idempotent=False,
            open_world=False,
        ),
        "trading_signal_get": _record(
            "trading_signal_get",
            title="Read trading signal",
            description=(
                "Use this when you need one exact Trading Lab signal record from the "
                "local journal."
            ),
            invoking="Reading trading signal...",
            invoked="Trading signal ready",
            read_only=True,
            destructive=False,
            idempotent=True,
            open_world=False,
        ),
        "trading_signal_list": _record(
            "trading_signal_list",
            title="List trading signals",
            description=(
                "Use this when you need a filtered page of Trading Lab signal records "
                "from the local journal."
            ),
            invoking="Listing trading signals...",
            invoked="Trading signals ready",
            read_only=True,
            destructive=False,
            idempotent=True,
            open_world=False,
        ),
        "trading_signal_cancel_before_entry": _record(
            "trading_signal_cancel_before_entry",
            title="Cancel trading signal",
            description=(
                "Use this when the user explicitly wants to cancel one stored Trading "
                "Lab signal before entry. This changes the signal's durable lifecycle "
                "and does not close an existing broker position."
            ),
            invoking="Cancelling trading signal...",
            invoked="Trading signal cancelled",
            read_only=False,
            destructive=True,
            idempotent=False,
            open_world=False,
        ),
        "trading_companion_action": _record(
            "trading_companion_action",
            title="Advance trading companion",
            description=(
                "Use this when the user explicitly wants to start, decide, review, or "
                "execute a Trading Lab companion cycle. Some stages read the configured "
                "provider and execute can reach broker-demo trading."
            ),
            invoking="Advancing trading companion...",
            invoked="Trading companion updated",
            read_only=False,
            destructive=True,
            idempotent=False,
            open_world=True,
        ),
        "trading_action_submit": _record(
            "trading_action_submit",
            title="Submit trading action",
            description=(
                "Use this when the user explicitly wants one guarded Trading Lab action "
                "such as entry, modification, close, flatten, or emergency close. The "
                "configured mode may be internal paper or broker-demo."
            ),
            invoking="Submitting trading action...",
            invoked="Trading action complete",
            read_only=False,
            destructive=True,
            idempotent=False,
            open_world=True,
        ),
        "trading_runtime_control": _record(
            "trading_runtime_control",
            title="Control trading runtime",
            description=(
                "Use this when the user explicitly wants to start, stop, change the "
                "kill switch, or run a manual trading supervision/analysis pass. Use "
                "Trading Lab record reads for runtime status instead of this mutation "
                "surface."
            ),
            invoking="Updating trading runtime...",
            invoked="Trading runtime updated",
            read_only=False,
            destructive=True,
            idempotent=False,
            open_world=True,
        ),
        "repo_query": _record(
            "repo_query",
            title="Inspect repository",
            description=(
                "Use this when you need to inspect or search a repository (repo) or "
                "repository evidence: current status, files, audit documents, source "
                "text, diffs, history, commit ranges, patch status, or the current state "
                "of an interrupted repository task. Do not use it to preview, apply, or "
                "commit changes."
            ),
            invoking="Inspecting repository...",
            invoked="Repository inspection ready",
            read_only=True,
            destructive=False,
            idempotent=True,
            open_world=False,
        ),
        "repo_preview": _record(
            "repo_preview",
            title="Prepare repository change",
            description=(
                "Use this when the user asks to make, correct, edit, create, remove, "
                "or otherwise change repository source/files and you need a durable "
                "hash-bound preview or cleanup plan before applying it. This creates "
                "Soma preview state but does not modify repository files."
            ),
            invoking="Preparing change preview...",
            invoked="Change preview ready",
            read_only=False,
            destructive=False,
            idempotent=False,
            open_world=False,
        ),
        "repo_apply": _record(
            "repo_apply",
            title="Apply repository change",
            description=(
                "Use this when the user has authorized an established managed preview, "
                "cleanup, revert, or move. This can overwrite, remove, restore, or move "
                "repository content; it does not push."
            ),
            invoking="Applying repository change...",
            invoked="Repository change applied",
            read_only=False,
            destructive=True,
            idempotent=False,
            open_world=False,
        ),
        "repo_commit": _record(
            "repo_commit",
            title="Commit selected files",
            description=(
                "Use this when the user explicitly wants a protected local branch "
                "creation or a commit containing selected validated files. Do not push "
                "or include unrelated work."
            ),
            invoking="Committing selected files...",
            invoked="Selected files committed",
            read_only=False,
            destructive=False,
            idempotent=False,
            open_world=False,
        ),
        "knowledge_query": _record(
            "knowledge_query",
            title="Access project knowledge",
            description=(
                "Use this when you need canonical project memory, repository wiki, "
                "legacy knowledge, or research evidence. This broad surface also "
                "includes stateful context operations; do not treat it as a pure read "
                "or substitute it for a narrower memory surface."
            ),
            invoking="Reading project knowledge...",
            invoked="Project knowledge ready",
            read_only=False,
            destructive=False,
            idempotent=False,
            open_world=False,
        ),
        "knowledge_action": _record(
            "knowledge_action",
            title="Update project knowledge",
            description=(
                "Use this when the user explicitly wants to update canonical project "
                "memory, repository wiki, legacy knowledge, or research knowledge. "
                "Some operations change lifecycle, rebuild indexes, or refresh durable "
                "content."
            ),
            invoking="Updating project knowledge...",
            invoked="Project knowledge updated",
            read_only=False,
            destructive=True,
            idempotent=False,
            open_world=False,
        ),
    }
)


_OPENAI_INVOKING_META_KEY: Final[str] = "openai/toolInvocation/invoking"
_OPENAI_INVOKED_META_KEY: Final[str] = "openai/toolInvocation/invoked"


def fastmcp_registration_kwargs(name: str, **kwargs: Any) -> dict[str, Any]:
    """Merge registry metadata into FastMCP registration keyword arguments.

    Unknown names are returned unchanged so internal registrations retain their
    existing behavior. For a public name, the registry owns the human-facing
    descriptor fields and the two OpenAI invocation metadata keys. Other
    FastMCP metadata remains intact.
    """

    registration = dict(kwargs)
    metadata = PUBLIC_TOOL_METADATA.get(name)
    if metadata is None:
        return registration

    registration.update(
        {
            "title": metadata.title,
            "description": metadata.description,
            "annotations": dict(metadata.annotations),
        }
    )
    merged_meta = dict(registration.get("meta") or {})
    merged_meta.update(
        {
            _OPENAI_INVOKING_META_KEY: metadata.invoking,
            _OPENAI_INVOKED_META_KEY: metadata.invoked,
        }
    )
    registration["meta"] = merged_meta
    return registration


if set(PUBLIC_TOOL_METADATA) != set(PUBLIC_GATEWAY_NAMES):
    missing = sorted(set(PUBLIC_GATEWAY_NAMES) - set(PUBLIC_TOOL_METADATA))
    unknown = sorted(set(PUBLIC_TOOL_METADATA) - set(PUBLIC_GATEWAY_NAMES))
    raise RuntimeError(
        "public tool metadata must match PUBLIC_GATEWAY_NAMES exactly; "
        f"missing={missing}, unknown={unknown}"
    )

if any(name != metadata.name for name, metadata in PUBLIC_TOOL_METADATA.items()):
    raise RuntimeError(
        "public tool metadata record names must match their mapping keys"
    )
