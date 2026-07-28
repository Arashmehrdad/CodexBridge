"""The accepted local-only provider profile.

The decision requires that cloud routing, remote sync and hosted embeddings be
*impossible* in the accepted profile -- not merely unavailable because credentials
happen to be absent. The pilot showed an unknown project name falls back toward
cloud routing and refuses only for want of credentials, so absence of credentials
is explicitly not accepted as the control.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

from .models import ProfileRefused, RefusalReason


#: Settings that must hold in the production profile, with the value required.
REQUIRED_SETTINGS: dict[str, object] = {
    # Provider must never rewrite canonical Markdown.
    #
    # `ensure_frontmatter_on_sync: False` alone is NOT sufficient: the live
    # confirmation measured all 6 canonical files still rewritten with it set.
    # `disable_permalinks: True` is the setting that actually stops the injected
    # `permalink:` key, and with it the measured drift is 0/6 across initial
    # index, repeated sync and full delete-and-rebuild. Both are required --
    # the second is the working control, the first is defence in depth.
    "disable_permalinks": True,
    "ensure_frontmatter_on_sync": False,
    # No silent routing when identity is omitted. The guard supplies identity.
    "default_project": None,
    # The release is frozen; the provider must not update itself underneath it.
    "auto_update": False,
    # Telemetry off.
    "logfire_enabled": False,
    "logfire_send_to_logfire": False,
}

#: Config keys that indicate a reachable cloud path. Any truthy value refuses.
CLOUD_SETTINGS: tuple[str, ...] = (
    "cloud_api_key",
    "default_workspace",
)

#: Environment forced on every provider process.
FORCED_ENV: dict[str, str] = {
    "BASIC_MEMORY_FORCE_LOCAL": "1",
    "BASIC_MEMORY_CLOUD_MODE": "0",
    "BASIC_MEMORY_NO_PROMOS": "1",
    # An empty key is not a credential; combined with FORCE_LOCAL this keeps the
    # cloud path unreachable rather than merely unconfigured.
    "BASIC_MEMORY_CLOUD_API_KEY": "",
    "BASIC_MEMORY_API_KEY": "",
}

#: Environment that must never be set for a guarded process.
FORBIDDEN_ENV: tuple[str, ...] = (
    "BASIC_MEMORY_FORCE_CLOUD",
    "BASIC_MEMORY_CLOUD_HOST",
    "BASIC_MEMORY_TENANT_ID",
)

#: The exact ambient variables a provider subprocess inherits, and nothing else.
#:
#: Both extremes here are defects, and both have been observed. Passing only the
#: `BASIC_MEMORY_*` keys left the child with no PATH and no SystemRoot, so every
#: real subprocess failed to start. Passing all of `os.environ` hands the
#: provider every credential that happens to live in Soma's process. This named
#: allowlist is the middle: enough for a Windows process to run, and nothing
#: that carries a secret.
INHERITED_ENV: tuple[str, ...] = (
    "PATH",
    "PATHEXT",
    "SystemRoot",
    "SystemDrive",
    "COMSPEC",
    "TEMP",
    "TMP",
    "USERPROFILE",
    "APPDATA",
    "LOCALAPPDATA",
    "ProgramData",
    "ProgramFiles",
    "NUMBER_OF_PROCESSORS",
    "PROCESSOR_ARCHITECTURE",
    "HOME",
    "LANG",
    "LC_ALL",
    "TZ",
)


@dataclass(frozen=True)
class ProviderProfile:
    """A validated, local-only provider configuration."""

    config_dir: Path
    config: dict[str, object]
    executable: str = ""

    def env(self, extra: dict[str, str] | None = None) -> dict[str, str]:
        """The complete environment for a guarded provider process.

        Built from the named `INHERITED_ENV` allowlist rather than from all of
        `os.environ`: the child gets what a Windows process needs to start and
        nothing that could carry a credential. The guard's own keys are applied
        last so they always win, and `validate_env` still refuses any variable
        that could re-enable a cloud path.
        """
        env: dict[str, str] = {}
        for key in INHERITED_ENV:
            value = os.environ.get(key)
            if value is not None:
                env[key] = value
        env["BASIC_MEMORY_CONFIG_DIR"] = str(self.config_dir)
        env.update(FORCED_ENV)
        for key in FORBIDDEN_ENV:
            env.pop(key, None)
        if extra:
            env.update(extra)
        return env


def load_profile(
    config_dir: str | Path, *, executable: str | Path = ""
) -> ProviderProfile:
    """Load and validate the provider config, or refuse.

    `executable` is the provider binary the guard expects to be invoked. It is
    recorded so `runtime.verify_runtime` can enforce the frozen stack; without
    it the runtime identity cannot be checked and semantic use is refused.
    """
    directory = Path(config_dir).expanduser()
    config_path = directory / "config.json"
    if not config_path.is_file():
        raise ProfileRefused(f"provider config not found at {config_path}")
    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ProfileRefused(f"provider config is not valid JSON: {exc}") from exc
    if not isinstance(config, dict):
        raise ProfileRefused("provider config must be a JSON object")
    validate_profile(config)
    return ProviderProfile(
        config_dir=directory, config=config, executable=str(executable or "")
    )


def validate_profile(config: dict[str, object]) -> None:
    """Refuse any configuration that is not the accepted local-only profile."""
    for key, required in REQUIRED_SETTINGS.items():
        if key not in config:
            raise ProfileRefused(
                f"provider config is missing required setting {key!r}; "
                "the guard refuses rather than assuming a default"
            )
        actual = config[key]
        if actual != required:
            reason = (
                RefusalReason.MUTATING_PROFILE.value
                if key in {"disable_permalinks", "ensure_frontmatter_on_sync"}
                else "profile_mismatch"
            )
            raise ProfileRefused(
                f"provider setting {key!r} must be {required!r}, found {actual!r} "
                f"({reason})"
            )

    for key in CLOUD_SETTINGS:
        if config.get(key):
            raise ProfileRefused(
                f"provider setting {key!r} is configured, so a cloud path is "
                f"reachable ({RefusalReason.CLOUD_REACHABLE.value})"
            )

    projects = config.get("projects")
    if not isinstance(projects, dict) or not projects:
        raise ProfileRefused("provider config declares no projects")


def validate_env(env: dict[str, str]) -> None:
    """Refuse an environment that could re-enable a cloud path."""
    for key in FORBIDDEN_ENV:
        if env.get(key):
            raise ProfileRefused(
                f"environment sets {key!r}, which can re-enable cloud routing "
                f"({RefusalReason.CLOUD_REACHABLE.value})"
            )
    for key, required in FORCED_ENV.items():
        if env.get(key, "") != required:
            raise ProfileRefused(
                f"environment must set {key}={required!r} for the local profile"
            )
