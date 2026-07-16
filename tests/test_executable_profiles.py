from __future__ import annotations

from hashlib import sha256
from pathlib import Path

import pytest

from codexbridge.config import AppConfig, ExecutableProfileConfig, RepoConfig
from codexbridge.executable_profiles import (
    inspect_executable_identity,
    resolve_executable_profile,
    resolve_verified_local_executable,
)


def make_config(
    tmp_path: Path,
    profile: ExecutableProfileConfig,
) -> AppConfig:
    return AppConfig(
        repos={"sample": RepoConfig(path=str(tmp_path))},
        executable_profiles={profile.profile_id: profile},
        config_dir=tmp_path,
    )


def test_resolve_verified_local_executable_records_exact_identity(
    tmp_path: Path,
) -> None:
    executable = tmp_path / "pwsh.exe"
    payload = b"fake-powershell-binary\x00\xff"
    executable.write_bytes(payload)
    expected = sha256(payload).hexdigest()
    profile = ExecutableProfileConfig(
        profile_id="powershell",
        enabled=True,
        executable_path=str(executable),
        expected_sha256=expected.upper(),
        expected_signer="Example Signer",
        expected_version="7.6.0",
        unrestricted_argv=True,
    )

    resolved, identity = resolve_verified_local_executable(
        make_config(tmp_path, profile),
        "powershell",
    )

    assert resolved is profile
    assert identity["profile_id"] == "powershell"
    assert identity["executable_path"] == str(executable.resolve())
    assert identity["observed_sha256"] == expected
    assert identity["expected_sha256"] == expected
    assert identity["expected_signer"] == "Example Signer"
    assert identity["expected_version"] == "7.6.0"
    assert identity["size_bytes"] == len(payload)
    assert identity["target"] == "local"


def test_executable_resolution_rejects_before_process_creation(
    tmp_path: Path,
) -> None:
    executable = tmp_path / "pwsh.exe"
    executable.write_bytes(b"binary")
    disabled = ExecutableProfileConfig(
        profile_id="powershell",
        enabled=False,
        executable_path=str(executable),
    )
    config = make_config(tmp_path, disabled)

    with pytest.raises(ValueError, match="must not be empty"):
        resolve_executable_profile(config, "")
    with pytest.raises(ValueError, match="Unknown executable profile"):
        resolve_executable_profile(config, "missing")
    with pytest.raises(ValueError, match="is disabled"):
        resolve_executable_profile(config, "powershell")

    remote = disabled.model_copy(update={"enabled": True, "target": "remote"})
    remote_config = make_config(tmp_path, remote)
    with pytest.raises(ValueError, match="not a local target"):
        resolve_executable_profile(remote_config, "powershell")


def test_executable_identity_rejects_missing_non_file_symlink_and_hash_mismatch(
    tmp_path: Path,
) -> None:
    missing = ExecutableProfileConfig(
        profile_id="missing",
        enabled=True,
        executable_path=str(tmp_path / "missing.exe"),
    )
    with pytest.raises(ValueError, match="does not exist"):
        inspect_executable_identity(missing)

    directory = tmp_path / "directory.exe"
    directory.mkdir()
    non_file = ExecutableProfileConfig(
        profile_id="directory",
        enabled=True,
        executable_path=str(directory),
    )
    with pytest.raises(ValueError, match="regular non-symlink file"):
        inspect_executable_identity(non_file)

    executable = tmp_path / "pwsh.exe"
    executable.write_bytes(b"binary")
    mismatch = ExecutableProfileConfig(
        profile_id="powershell",
        enabled=True,
        executable_path=str(executable),
        expected_sha256="0" * 64,
    )
    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        inspect_executable_identity(mismatch)

    symlink = tmp_path / "pwsh-link.exe"
    try:
        symlink.symlink_to(executable)
    except OSError:
        pytest.skip("Symlink creation is unavailable for this account")
    linked = ExecutableProfileConfig(
        profile_id="powershell_link",
        enabled=True,
        executable_path=str(symlink),
    )
    with pytest.raises(ValueError, match="regular non-symlink file"):
        inspect_executable_identity(linked)
