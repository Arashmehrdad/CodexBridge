from __future__ import annotations

import importlib
import sys
import time
from pathlib import Path
from typing import Iterable

from .capabilities import PATCH_OPERATION_SCHEMA, capability_metadata
from .config import AppConfig, load_config
from .repo_discovery_integration import install_repo_discovery


_CONFIG_LIFECYCLE_STATE: dict[str, object] = {
    "active_config_path": None,
    "active_config": None,
    "active_loaded_at": None,
    "last_known_good_config": None,
    "last_known_good_loaded_at": None,
    "previous_config": None,
    "previous_loaded_at": None,
    "last_validated_config": None,
    "last_validated_at": None,
    "last_candidate_path": None,
    "last_error": "",
    "last_operation": "",
    "last_status": "uninitialized",
}


def _utc_timestamp() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _lifecycle_metadata() -> dict[str, object]:
    return {
        "config_lifecycle": {
            "active_config_path": _CONFIG_LIFECYCLE_STATE["active_config_path"],
            "active_loaded_at": _CONFIG_LIFECYCLE_STATE["active_loaded_at"],
            "last_known_good_loaded_at": _CONFIG_LIFECYCLE_STATE[
                "last_known_good_loaded_at"
            ],
            "previous_loaded_at": _CONFIG_LIFECYCLE_STATE["previous_loaded_at"],
            "last_validated_at": _CONFIG_LIFECYCLE_STATE["last_validated_at"],
            "last_candidate_path": _CONFIG_LIFECYCLE_STATE["last_candidate_path"],
            "last_operation": _CONFIG_LIFECYCLE_STATE["last_operation"],
            "last_status": _CONFIG_LIFECYCLE_STATE["last_status"],
            "last_error": _CONFIG_LIFECYCLE_STATE["last_error"],
            "has_active_config": _CONFIG_LIFECYCLE_STATE["active_config"] is not None,
            "has_last_known_good_config": (
                _CONFIG_LIFECYCLE_STATE["last_known_good_config"] is not None
            ),
            "has_previous_config": _CONFIG_LIFECYCLE_STATE["previous_config"] is not None,
        }
    }


def register_active_config(config: AppConfig, config_path: Path | None) -> None:
    timestamp = _utc_timestamp()
    _CONFIG_LIFECYCLE_STATE["active_config"] = config
    _CONFIG_LIFECYCLE_STATE["last_known_good_config"] = config
    _CONFIG_LIFECYCLE_STATE["active_loaded_at"] = timestamp
    _CONFIG_LIFECYCLE_STATE["last_known_good_loaded_at"] = timestamp
    _CONFIG_LIFECYCLE_STATE["active_config_path"] = (
        str(config_path.resolve()) if config_path is not None else None
    )
    _CONFIG_LIFECYCLE_STATE["last_candidate_path"] = (
        str(config_path.resolve()) if config_path is not None else None
    )
    _CONFIG_LIFECYCLE_STATE["last_validated_config"] = config
    _CONFIG_LIFECYCLE_STATE["last_validated_at"] = timestamp
    _CONFIG_LIFECYCLE_STATE["last_error"] = ""
    _CONFIG_LIFECYCLE_STATE["last_operation"] = "register"
    _CONFIG_LIFECYCLE_STATE["last_status"] = "active"


def validate_config_candidate(config_path: Path | None) -> dict[str, object]:
    if config_path is None:
        raise ValueError("validate_config_candidate requires a config path")
    resolved = config_path.resolve()
    config = load_config(resolved)
    timestamp = _utc_timestamp()
    _CONFIG_LIFECYCLE_STATE["last_validated_config"] = config
    _CONFIG_LIFECYCLE_STATE["last_validated_at"] = timestamp
    _CONFIG_LIFECYCLE_STATE["last_candidate_path"] = str(resolved)
    _CONFIG_LIFECYCLE_STATE["last_error"] = ""
    _CONFIG_LIFECYCLE_STATE["last_operation"] = "validate"
    _CONFIG_LIFECYCLE_STATE["last_status"] = "validated"
    result = {
        "ok": True,
        "validated": True,
        "candidate_config_path": str(resolved),
        "validated_at": timestamp,
        "message": "Configuration candidate validated successfully.",
        "error": "",
    }
    result.update(_lifecycle_metadata())
    result.update(capability_metadata(PATCH_OPERATION_SCHEMA))
    return result


def get_reload_status() -> dict[str, object]:
    result = {
        "ok": True,
        "status": _CONFIG_LIFECYCLE_STATE["last_status"],
        "message": "",
        "error": "",
    }
    result.update(_lifecycle_metadata())
    result.update(capability_metadata(PATCH_OPERATION_SCHEMA))
    return result


def rollback_service() -> dict[str, object]:
    previous = _CONFIG_LIFECYCLE_STATE["previous_config"]
    if previous is None:
        result = {
            "ok": False,
            "rolled_back": False,
            "message": "",
            "error": "No previous last-known-good configuration is available for rollback.",
        }
        _CONFIG_LIFECYCLE_STATE["last_error"] = str(result["error"])
        _CONFIG_LIFECYCLE_STATE["last_operation"] = "rollback"
        _CONFIG_LIFECYCLE_STATE["last_status"] = "rollback_unavailable"
        result.update(_lifecycle_metadata())
        result.update(capability_metadata(PATCH_OPERATION_SCHEMA))
        return result

    _CONFIG_LIFECYCLE_STATE["active_config"] = previous
    _CONFIG_LIFECYCLE_STATE["last_known_good_config"] = previous
    _CONFIG_LIFECYCLE_STATE["active_loaded_at"] = _utc_timestamp()
    _CONFIG_LIFECYCLE_STATE["last_known_good_loaded_at"] = (
        _CONFIG_LIFECYCLE_STATE["previous_loaded_at"]
        or _CONFIG_LIFECYCLE_STATE["active_loaded_at"]
    )
    _CONFIG_LIFECYCLE_STATE["last_error"] = ""
    _CONFIG_LIFECYCLE_STATE["last_operation"] = "rollback"
    _CONFIG_LIFECYCLE_STATE["last_status"] = "rolled_back"
    result = {
        "ok": True,
        "rolled_back": True,
        "config": previous,
        "message": "Rolled back to the previous last-known-good configuration.",
        "error": "",
    }
    result.update(_lifecycle_metadata())
    result.update(capability_metadata(PATCH_OPERATION_SCHEMA))
    return result

def _rebind_server_ssh_helpers() -> None:
    server_module = sys.modules.get("codexbridge.server")
    commands_module = sys.modules.get("codexbridge.ssh_commands")
    manager_module = sys.modules.get("codexbridge.ssh_profile_manager")
    tools_module = sys.modules.get("codexbridge.ssh_tools")
    if server_module is None or commands_module is None or tools_module is None:
        return
    server_module._list_ssh_capabilities = commands_module.list_ssh_capabilities
    server_module._ssh_host_health = commands_module.ssh_host_health
    server_module._enrich_ssh_capabilities = tools_module.enrich_ssh_capabilities
    server_module._run_ssh_environment_probe = tools_module.run_ssh_environment_probe
    server_module._run_ssh_gpu_telemetry = tools_module.run_ssh_gpu_telemetry
    server_module._run_ssh_inspection = tools_module.run_ssh_inspection
    if manager_module is not None:
        server_module._preview_ssh_profile_change = (
            manager_module.preview_ssh_profile_change
        )
        server_module._get_ssh_profile_change_status = (
            manager_module.get_ssh_profile_change_status
        )
        server_module._apply_ssh_profile_change = manager_module.apply_ssh_profile_change


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
    "codexbridge.ssh_profile_manager",
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

    validated_config: AppConfig | None = None
    resolved_config_path: str | None = None
    if "config" in requested:
        if config_path is None:
            raise ValueError("reload_service requires a config path")
        validated = validate_config_candidate(config_path)
        validated_config = _CONFIG_LIFECYCLE_STATE["last_validated_config"]  # type: ignore[assignment]
        resolved_config_path = str(Path(config_path).resolve())
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
        if qualified in {
            "codexbridge.ssh_commands",
            "codexbridge.ssh_profile_manager",
            "codexbridge.ssh_tools",
        }:
            _rebind_server_ssh_helpers()
        reloaded.append(qualified)

    if validated_config is not None:
        _CONFIG_LIFECYCLE_STATE["previous_config"] = _CONFIG_LIFECYCLE_STATE["active_config"]
        _CONFIG_LIFECYCLE_STATE["previous_loaded_at"] = _CONFIG_LIFECYCLE_STATE[
            "active_loaded_at"
        ]
        _CONFIG_LIFECYCLE_STATE["active_config"] = validated_config
        _CONFIG_LIFECYCLE_STATE["last_known_good_config"] = validated_config
        _CONFIG_LIFECYCLE_STATE["active_loaded_at"] = _utc_timestamp()
        _CONFIG_LIFECYCLE_STATE["last_known_good_loaded_at"] = _CONFIG_LIFECYCLE_STATE[
            "active_loaded_at"
        ]
        _CONFIG_LIFECYCLE_STATE["active_config_path"] = resolved_config_path
        _CONFIG_LIFECYCLE_STATE["last_candidate_path"] = resolved_config_path
        _CONFIG_LIFECYCLE_STATE["last_error"] = ""
        _CONFIG_LIFECYCLE_STATE["last_status"] = (
            "active" if not restart_required else "restart_required"
        )
    else:
        _CONFIG_LIFECYCLE_STATE["last_status"] = (
            "active" if not restart_required else "restart_required"
        )
    _CONFIG_LIFECYCLE_STATE["last_operation"] = "reload"

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
    result.update(_lifecycle_metadata())
    return result


def apply_reloaded_config(config_path: Path) -> AppConfig:
    config = load_config(config_path)
    register_active_config(config, config_path)
    install_repo_discovery()
    return config
