from __future__ import annotations

import importlib
import sys
from pathlib import Path
from typing import Iterable

from .capabilities import PATCH_OPERATION_SCHEMA, capability_metadata
from .config import AppConfig, load_config
from .repo_discovery_integration import install_repo_discovery

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
