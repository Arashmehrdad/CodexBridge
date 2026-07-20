from __future__ import annotations

from dataclasses import dataclass
from typing import Final


@dataclass(frozen=True)
class PublicGatewayInventoryEntry:
    name: str
    family: str
    source: str
    response_path: str
    cf1_risk: str


PUBLIC_GATEWAY_INVENTORY_VERSION: Final[str] = "cf1.0.v1"


def _entry(name: str, family: str, source: str, response_path: str, cf1_risk: str) -> PublicGatewayInventoryEntry:
    return PublicGatewayInventoryEntry(name, family, source, response_path, cf1_risk)


PUBLIC_GATEWAY_INVENTORY: Final[tuple[PublicGatewayInventoryEntry, ...]] = (
    _entry("ssh_inspect", "ssh", "codexbridge.server", "direct bounded object", "provider payload and diagnostic growth"),
    _entry("codex_plan", "codex", "codexbridge.server", "durable run launch", "request echo through run records"),
    _entry("codex_implement", "codex", "codexbridge.server", "durable run launch", "request echo through run records"),
    _entry("docker_query", "docker", "codexbridge.server", "direct object", "inspection and log growth"),
    _entry("docker_action", "docker", "codexbridge.server", "durable run launch", "terminal provider payload growth"),
    _entry("cloudflare_query", "cloudflare", "codexbridge.server", "direct object", "provider response and pagination growth"),
    _entry("cloudflare_action", "cloudflare", "codexbridge.server", "durable run launch", "request and provider payload growth"),
    _entry("ssh_query", "ssh", "codexbridge.server", "direct object", "profile preview payload growth"),
    _entry("ssh_action", "ssh", "codexbridge.server", "durable run launch", "script, argv, and evidence growth"),
    _entry("run_start", "runs", "codexbridge.server", "durable run launch", "input echo and launch metadata growth"),
    _entry("workflow_query", "workflows", "codexbridge.server", "direct durable snapshot", "nested child and event growth"),
    _entry("workflow_action", "workflows", "codexbridge.server", "durable workflow mutation", "objective and step echo growth"),
    _entry("cancel_run", "runs", "codexbridge.server", "direct mutation result", "process-tree diagnostic growth"),
    _entry("run_query", "runs", "codexbridge.server", "full row or bounded output", "JSON decoding, request echo, and oversized lists"),
    _entry("system_query", "system", "codexbridge.server", "direct object", "capability and self-check growth"),
    _entry("system_action", "system", "codexbridge.server", "direct mutation result", "reload diagnostic growth"),
    _entry("supervisor_query", "supervisors", "codexbridge.server", "direct durable snapshot", "linked run and notification growth"),
    _entry("supervisor_action", "supervisors", "codexbridge.server", "durable supervisor mutation", "objective, task, and child echo growth"),
    _entry("trading_query", "trading", "codexbridge.server", "direct provider object", "market series growth"),
    _entry("trading_signal_submit", "trading", "codexbridge.server", "direct journal object", "reason and news-context growth"),
    _entry("trading_signal_get", "trading", "codexbridge.server", "direct journal object", "signal payload growth"),
    _entry("trading_signal_list", "trading", "codexbridge.server", "direct journal list", "list growth and repeated payloads"),
    _entry("trading_signal_cancel_before_entry", "trading", "codexbridge.server", "direct journal object", "signal payload repetition"),
    _entry("repo_query", "repository", "codexbridge.server", "direct repository object", "file, search, and diff payload growth"),
    _entry("repo_preview", "repository", "codexbridge.server", "opaque preview object", "patch and file-content echo growth"),
    _entry("repo_apply", "repository", "codexbridge.server", "direct mutation result", "patch lifecycle diagnostic growth"),
    _entry("repo_commit", "repository", "codexbridge.server", "direct mutation result", "commit diagnostic growth"),
    _entry("knowledge_query", "knowledge", "codexbridge.knowledge_tools_integration", "direct knowledge object", "wiki and search result growth"),
    _entry("knowledge_action", "knowledge", "codexbridge.knowledge_tools_integration", "direct mutation result", "decision and wiki payload growth"),
)

PUBLIC_GATEWAY_NAMES: Final[frozenset[str]] = frozenset(entry.name for entry in PUBLIC_GATEWAY_INVENTORY)

if len(PUBLIC_GATEWAY_NAMES) != len(PUBLIC_GATEWAY_INVENTORY):
    raise RuntimeError("public gateway inventory contains duplicate names")
