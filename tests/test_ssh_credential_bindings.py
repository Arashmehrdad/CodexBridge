from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from soma import ssh_commands, ssh_credentials
from soma.config import (
    AppConfig,
    RepoConfig,
    SSHCommandProfileConfig,
    SSHConfig,
    SSHCredentialBindingConfig,
    SSHCredentialSourceConfig,
    SSHHostConfig,
)
from soma.ssh_commands import (
    build_ssh_argv,
    list_ssh_capabilities,
    resolve_ssh_connection,
)
from soma.ssh_credentials import resolve_ssh_credential_binding


HOST_VALUE = "binding-host-canary.example"
USER_VALUE = "binding-user-canary"
FINGERPRINT_VALUE = "SHA256:" + "C" * 43


def _write_key(path: Path) -> Path:
    path.write_text(
        "-----BEGIN OPENSSH PRIVATE KEY-----\n"
        "binding-key-canary-41f2\n"
        "-----END OPENSSH PRIVATE KEY-----\n",
        encoding="utf-8",
    )
    path.chmod(0o600)
    return path.resolve()


def _safe_security(_path: Path) -> dict[str, object]:
    return {
        "ok": True,
        "git": {"ok": True},
        "acl": {"ok": True},
        "refusals": [],
        "warnings": [],
    }


def _binding(source_id: str = "production") -> SSHCredentialBindingConfig:
    return SSHCredentialBindingConfig(
        source_id=source_id,
        hostname="PROD_SSH_HOST",
        user="PROD_SSH_USER",
        port="PROD_SSH_PORT",
        identity_file="PROD_SSH_KEY_PATH",
        expected_host_key="PROD_SSH_HOST_KEY",
    )


def _config(
    tmp_path: Path,
    source: SSHCredentialSourceConfig,
    *,
    binding: SSHCredentialBindingConfig | None = None,
) -> AppConfig:
    return AppConfig(
        repos={"sample": RepoConfig(path=str(tmp_path))},
        ssh=SSHConfig(
            enabled=True,
            credential_sources={"production": source},
            hosts={
                "production_vps": SSHHostConfig(
                    credential_binding=binding or _binding(),
                    connect_timeout_seconds=18,
                    command_profiles=[
                        SSHCommandProfileConfig(command_id="health", argv=["true"])
                    ],
                )
            },
        ),
        config_dir=tmp_path,
    )


def test_reference_models_validate_without_resolving_local_values(tmp_path: Path) -> None:
    missing_source = tmp_path / "not-created.env"
    config = _config(
        tmp_path,
        SSHCredentialSourceConfig(type="env_file", path=str(missing_source.resolve())),
    )

    assert config.ssh.hosts["production_vps"].credential_binding is not None
    dumped = json.dumps(config.model_dump(mode="json"), sort_keys=True)
    assert "PROD_SSH_HOST" in dumped
    assert HOST_VALUE not in dumped
    assert USER_VALUE not in dumped


def test_ssh_config_rejects_unknown_source_and_mixed_connection_modes(tmp_path: Path) -> None:
    with pytest.raises(ValidationError, match="unknown credential source"):
        SSHConfig(
            hosts={
                "bad": SSHHostConfig(
                    credential_binding=SSHCredentialBindingConfig(
                        source_id="missing",
                        hostname="SSH_HOST",
                        user="SSH_USER",
                        identity_file="SSH_KEY_PATH",
                    )
                )
            }
        )

    with pytest.raises(ValidationError, match="exactly one"):
        SSHHostConfig(
            ssh_alias="existing-alias",
            credential_binding=SSHCredentialBindingConfig(
                source_id="production",
                hostname="SSH_HOST",
                user="SSH_USER",
                identity_file="SSH_KEY_PATH",
            ),
        )

    with pytest.raises(ValidationError, match="missing references"):
        SSHConfig(
            credential_sources={
                "production": SSHCredentialSourceConfig(
                    type="process_environment"
                )
            },
            hosts={
                "bad": SSHHostConfig(
                    credential_binding=SSHCredentialBindingConfig(
                        source_id="production",
                        hostname="SSH_HOST",
                    )
                )
            },
        )


def test_env_file_binding_resolves_only_at_execution_time(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(ssh_credentials, "_file_security", _safe_security)
    key = _write_key(tmp_path / "id_env")
    source_path = tmp_path / "production.env"
    source_path.write_text(
        f"PROD_SSH_HOST={HOST_VALUE}\n"
        f"PROD_SSH_USER={USER_VALUE}\n"
        "PROD_SSH_PORT=2202\n"
        f"PROD_SSH_KEY_PATH={key}\n"
        f"PROD_SSH_HOST_KEY={FINGERPRINT_VALUE}\n",
        encoding="utf-8",
    )
    config = _config(
        tmp_path,
        SSHCredentialSourceConfig(type="env_file", path=str(source_path.resolve())),
    )

    connection = resolve_ssh_connection(
        config.ssh.hosts["production_vps"], config.ssh
    )
    assert connection.mode == "credential_binding"
    assert connection.destination == f"{USER_VALUE}@{HOST_VALUE}"
    assert connection.port == 2202
    assert connection.identity_file == str(key)
    assert connection.expected_host_key == FINGERPRINT_VALUE
    assert connection.source_id == "production"

    source_path.write_text(
        f"PROD_SSH_HOST=changed.example\n"
        f"PROD_SSH_USER={USER_VALUE}\n"
        f"PROD_SSH_KEY_PATH={key}\n",
        encoding="utf-8",
    )
    changed = resolve_ssh_connection(
        config.ssh.hosts["production_vps"], config.ssh
    )
    assert changed.destination == f"{USER_VALUE}@changed.example"
    assert changed.port == 22


def test_process_environment_binding_is_scoped_and_fail_closed(
    tmp_path: Path,
) -> None:
    key = _write_key(tmp_path / "id_process")
    source = SSHCredentialSourceConfig(type="process_environment")
    binding = _binding()
    values = {
        "PROD_SSH_HOST": HOST_VALUE,
        "PROD_SSH_USER": USER_VALUE,
        "PROD_SSH_PORT": "2222",
        "PROD_SSH_KEY_PATH": str(key),
        "PROD_SSH_HOST_KEY": FINGERPRINT_VALUE,
        "UNRELATED_SECRET": "must-not-be-read",
    }

    resolved = resolve_ssh_credential_binding(
        {"production": source}, binding, environment=values
    )
    assert resolved.destination == f"{USER_VALUE}@{HOST_VALUE}"
    assert resolved.port == 2222

    del values["PROD_SSH_USER"]
    with pytest.raises(ValueError, match="variable referenced for user") as exc_info:
        resolve_ssh_credential_binding(
            {"production": source}, binding, environment=values
        )
    assert HOST_VALUE not in str(exc_info.value)
    assert "must-not-be-read" not in str(exc_info.value)


def test_key_file_source_uses_stored_non_secret_endpoint(tmp_path: Path) -> None:
    key = _write_key(tmp_path / "id_direct")
    source = SSHCredentialSourceConfig(
        type="key_file",
        path=str(key),
        hostname=HOST_VALUE,
        user=USER_VALUE,
        port=2022,
        expected_host_key=FINGERPRINT_VALUE,
    )
    binding = SSHCredentialBindingConfig(source_id="production")

    resolved = resolve_ssh_credential_binding(
        {"production": source}, binding
    )
    assert resolved.destination == f"{USER_VALUE}@{HOST_VALUE}"
    assert resolved.identity_file == str(key)
    assert resolved.port == 2022


def test_connection_file_and_openssh_sources_resolve_canonically(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(ssh_credentials, "_file_security", _safe_security)
    key = _write_key(tmp_path / "id_sources")
    connection_file = tmp_path / "connection.txt"
    connection_file.write_text(
        f"ssh {USER_VALUE}@{HOST_VALUE} -p 2023 -i {key}\n",
        encoding="utf-8",
    )
    connection_source = SSHCredentialSourceConfig(
        type="connection_file", path=str(connection_file.resolve())
    )
    connection = resolve_ssh_credential_binding(
        {"production": connection_source},
        SSHCredentialBindingConfig(source_id="production"),
    )
    assert connection.destination == f"{USER_VALUE}@{HOST_VALUE}"
    assert connection.port == 2023

    openssh_file = tmp_path / "ssh_config"
    openssh_file.write_text(
        "Host production-alias\n"
        f"  HostName {HOST_VALUE}\n"
        f"  User {USER_VALUE}\n"
        "  Port 2024\n"
        f"  IdentityFile {key}\n",
        encoding="utf-8",
    )
    openssh_source = SSHCredentialSourceConfig(
        type="openssh_config",
        path=str(openssh_file.resolve()),
        alias="production-alias",
    )
    openssh = resolve_ssh_credential_binding(
        {"production": openssh_source},
        SSHCredentialBindingConfig(source_id="production"),
    )
    assert openssh.destination == f"{USER_VALUE}@{HOST_VALUE}"
    assert openssh.port == 2024
    assert openssh.identity_file == str(key)


def test_build_ssh_argv_uses_binding_but_capabilities_do_not_resolve_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    key = _write_key(tmp_path / "id_argv")
    config = _config(
        tmp_path,
        SSHCredentialSourceConfig(type="process_environment"),
    )
    monkeypatch.setattr(ssh_commands.shutil, "which", lambda _name: "ssh.exe")
    monkeypatch.setenv("PROD_SSH_HOST", HOST_VALUE)
    monkeypatch.setenv("PROD_SSH_USER", USER_VALUE)
    monkeypatch.setenv("PROD_SSH_PORT", "2205")
    monkeypatch.setenv("PROD_SSH_KEY_PATH", str(key))
    monkeypatch.setenv("PROD_SSH_HOST_KEY", FINGERPRINT_VALUE)

    capabilities = list_ssh_capabilities(config)
    host_summary = capabilities["hosts"][0]
    assert host_summary["connection_mode"] == "credential_binding"
    assert host_summary["credential_source_id"] == "production"
    assert host_summary["ssh_alias"] == "<credential_binding:production>"
    serialized_capabilities = json.dumps(capabilities)
    assert HOST_VALUE not in serialized_capabilities
    assert USER_VALUE not in serialized_capabilities
    assert str(key) not in serialized_capabilities

    argv = build_ssh_argv(
        config,
        "production_vps",
        config.ssh.hosts["production_vps"].command_profiles[0],
    )
    assert argv[-2:] == [f"{USER_VALUE}@{HOST_VALUE}", "true"]
    assert argv[argv.index("-i") + 1] == str(key)
    assert argv[argv.index("-p") + 1] == "2205"
    assert "PasswordAuthentication=no" in argv
    assert "KbdInteractiveAuthentication=no" in argv


def test_credential_binding_requires_global_registry_for_direct_resolution() -> None:
    host = SSHHostConfig(
        credential_binding=SSHCredentialBindingConfig(
            source_id="production",
            hostname="SSH_HOST",
            user="SSH_USER",
            identity_file="SSH_KEY_PATH",
        )
    )
    with pytest.raises(ValueError, match="global SSH configuration"):
        resolve_ssh_connection(host)
