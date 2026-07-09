from __future__ import annotations

import importlib
import sys
from pathlib import Path
from typing import Iterable

from .capabilities import PATCH_OPERATION_SCHEMA, capability_metadata
from .config import AppConfig, load_config
from .repo_discovery_integration import install_repo_discovery

def _rebind_server_ssh_helpers() -> None:
    server_module = sys.modules.get("codexbridge.server")
    commands_module = sys.modules.get("codexbridge.ssh_commands")
    tools_module = sys.modules.get("codexbridge.ssh_tools")
    if server_module is None or commands_module is None or tools_module is None:
        return
    server_module._list_ssh_capabilities = commands_module.list_ssh_capabilities
    server_module._ssh_host_health = commands_module.ssh_host_health
    server_module._enrich_ssh_capabilities = tools_module.enrich_ssh_capabilities
    server_module._run_ssh_inspection = tools_module.run_ssh_inspection


RELOADABLE_MODULES = {
    "codexbridge.capabilities",
    "codexbridge.command_profiles",
    "codexbridge.config",
    "codexbridge.git_tools",
    "codexbridge.external_fixtures",
    "codexbridge.managed_artifacts",
    "codexbridge.operation_locks",
    "codexbridge.prompts",
    "codexbridge.repo_wiki",
    "codexbridge.repo_writer",
    "codexbridge.run_guards",
    "codexbridge.run_store",
    "codexbridge.ssh_commands",
    "codexbridge.ssh_tools",
    "codexbridge.transactions",
    "codexbridge.return_loop.atomic_writer",
}


def reload_service(
    config_path: Path | None,
    *,
    modules: Iterable[str] | None = None,
) -> dict:
    requested = list(modules or [])
    if not requested:
        requested = ["config"]
    resolved_modules: list[str] = []
    reloaded: list[str] = []
    restart_required: list[str] = []

    if "config" in requested:
        if config_path is None:
            raise ValueError("reload_service requires a config path")
        load_config(config_path)
        reloaded.append("config")

    for module_name in requested:
        if module_name == "config":
            continue
        qualified = (
            module_name
            if module_name.startswith("codexbridge.")
            else f"codexbridge.{module_name}"
        )
        resolved_modules.append(qualified)
        if qualified not in RELOADABLE_MODULES:
            restart_required.append(qualified)
            continue
        if qualified in sys.modules:
            importlib.reload(sys.modules[qualified])
        else:
            importlib.import_module(qualified)
        if qualified == "codexbridge.ssh_tools":
            _rebind_server_ssh_helpers()
        reloaded.append(qualified)

    result = {
        "ok": not restart_required,
        "reloaded": reloaded,
        "requested_modules": requested,
        "resolved_modules": resolved_modules,
        "restart_required": restart_required,
        "message": ""
        if not restart_required
        else "One or more modules require process restart for safe activation.",
    }
    install_repo_discovery()
    result.update(capability_metadata(PATCH_OPERATION_SCHEMA))
    return result


def apply_reloaded_config(config_path: Path) -> AppConfig:
    config = load_config(config_path)
    install_repo_discovery()
    return config
