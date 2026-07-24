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
    _entry("ssh_inspect", "ssh", "soma.server", "direct bounded object", "provider payload and diagnostic growth"),
    _entry("docker_query", "docker", "soma.server", "direct object", "inspection and log growth"),
    _entry("docker_action", "docker", "soma.server", "durable run launch", "terminal provider payload growth"),
    _entry("cloudflare_query", "cloudflare", "soma.server", "direct object", "provider response and pagination growth"),
    _entry("cloudflare_action", "cloudflare", "soma.server", "durable run launch", "request and provider payload growth"),
    _entry("ssh_query", "ssh", "soma.server", "direct object", "profile preview payload growth"),
    _entry("ssh_action", "ssh", "soma.server", "durable run launch", "script, argv, and evidence growth"),
    _entry("run_start", "runs", "soma.server", "durable run launch", "input echo and launch metadata growth"),
    _entry("workflow_query", "workflows", "soma.server", "direct durable snapshot", "nested child and event growth"),
    _entry("workflow_action", "workflows", "soma.server", "durable workflow mutation", "objective and step echo growth"),
    _entry("cancel_run", "runs", "soma.server", "direct mutation result", "process-tree diagnostic growth"),
    _entry("run_query", "runs", "soma.server", "full row or bounded output", "JSON decoding, request echo, and oversized lists"),
    _entry("system_query", "system", "soma.server", "direct object", "capability and self-check growth"),
    _entry("system_action", "system", "soma.server", "direct mutation result", "reload diagnostic growth"),
    _entry("supervisor_query", "supervisors", "soma.server", "direct durable snapshot", "linked run and notification growth"),
    _entry("supervisor_action", "supervisors", "soma.server", "durable supervisor mutation", "objective, task, and child echo growth"),
    _entry("trading_query", "trading", "soma.server", "direct provider object", "market series growth"),
    _entry("trading_signal_submit", "trading", "soma.server", "direct journal object", "reason and news-context growth"),
    _entry("trading_signal_get", "trading", "soma.server", "direct journal object", "signal payload growth"),
    _entry("trading_signal_list", "trading", "soma.server", "direct journal list", "list growth and repeated payloads"),
    _entry("trading_signal_cancel_before_entry", "trading", "soma.server", "direct journal object", "signal payload repetition"),
    _entry("trading_companion_action", "trading", "soma.server", "direct companion journal transition", "research, review, signal, and action evidence growth"),
    _entry("trading_action_submit", "trading", "soma.server", "durable action record", "action evidence and reconciliation growth"),
    _entry("trading_runtime_control", "trading", "soma.server", "direct runtime state", "pass report and event growth"),
    _entry("repo_query", "repository", "soma.server", "direct repository object", "file, search, and diff payload growth"),
    _entry("repo_preview", "repository", "soma.server", "opaque preview object", "patch and file-content echo growth"),
    _entry("repo_apply", "repository", "soma.server", "direct mutation result", "patch lifecycle diagnostic growth"),
    _entry("repo_commit", "repository", "soma.server", "direct mutation result", "commit diagnostic growth"),
    _entry("knowledge_query", "knowledge", "soma.knowledge_tools_integration", "direct knowledge object", "wiki and search result growth"),
    _entry("knowledge_action", "knowledge", "soma.knowledge_tools_integration", "direct mutation result", "decision and wiki payload growth"),
)

PUBLIC_GATEWAY_NAMES: Final[frozenset[str]] = frozenset(entry.name for entry in PUBLIC_GATEWAY_INVENTORY)

if len(PUBLIC_GATEWAY_NAMES) != len(PUBLIC_GATEWAY_INVENTORY):
    raise RuntimeError("public gateway inventory contains duplicate names")
