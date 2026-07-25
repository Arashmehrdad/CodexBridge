from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path

import pytest

from soma import ssh_commands, ssh_tools
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
    SSHConnection,
    build_ssh_argv,
    build_ssh_host_key_options,
    build_ssh_payload_argv,
)
from soma.ssh_host_keys import (
    known_hosts_host_token,
    managed_known_hosts_path,
    parse_host_key_scan,
    read_host_key_verification,
    scan_stable_host_keys,
    stage_host_key_verification,
)


def _key_data(label: str) -> str:
    return base64.b64encode(label.encode("utf-8")).decode("ascii")


def _fingerprint(key_data: str) -> str:
    digest = hashlib.sha256(base64.b64decode(key_data)).digest()
    return "SHA256:" + base64.b64encode(digest).decode("ascii").rstrip("=")


KEY_A = _key_data("ssh-host-key-a")
KEY_B = _key_data("ssh-host-key-b")
FINGERPRINT_A = _fingerprint(KEY_A)
FINGERPRINT_B = _fingerprint(KEY_B)
HOSTNAME = "candidate.example"


def _scan_text(key_data: str = KEY_A, key_type: str = "ssh-ed25519") -> str:
    return f"# scanner comment\n{HOSTNAME} {key_type} {key_data}\n"


def test_known_hosts_token_and_parser_are_canonical() -> None:
    assert known_hosts_host_token(HOSTNAME, 22) == HOSTNAME
    assert known_hosts_host_token(HOSTNAME, 2222) == f"[{HOSTNAME}]:2222"

    observations = parse_host_key_scan(
        _scan_text(), hostname=HOSTNAME, port=2222
    )
    assert len(observations) == 1
    assert observations[0].fingerprint == FINGERPRINT_A
    assert observations[0].known_hosts_line == (
        f"[{HOSTNAME}]:2222 ssh-ed25519 {KEY_A}"
    )


@pytest.mark.parametrize(
    "text",
    [
        "not-enough-fields\n",
        f"{HOSTNAME} bad$type {KEY_A}\n",
        f"{HOSTNAME} ssh-ed25519 not_base64!\n",
        "\x00bad\n",
        "# comments only\n",
    ],
)
def test_host_key_parser_fails_closed(text: str) -> None:
    with pytest.raises(ValueError):
        parse_host_key_scan(text, hostname=HOSTNAME, port=22)


def test_stable_scan_requires_two_identical_observations() -> None:
    calls: list[int] = []

    def stable_scanner(hostname: str, port: int, timeout_seconds: int) -> str:
        assert hostname == HOSTNAME
        assert port == 22
        assert timeout_seconds == 3
        calls.append(1)
        return _scan_text()

    observations = scan_stable_host_keys(
        HOSTNAME,
        22,
        attempts=2,
        timeout_seconds=3,
        scanner=stable_scanner,
    )
    assert len(calls) == 2
    assert observations[0].fingerprint == FINGERPRINT_A

    sequence = iter((_scan_text(KEY_A), _scan_text(KEY_B)))
    with pytest.raises(ValueError, match="did not converge"):
        scan_stable_host_keys(
            HOSTNAME,
            22,
            attempts=2,
            scanner=lambda _host, _port, _timeout: next(sequence),
        )


def test_pinned_verification_stages_only_matching_identity(tmp_path: Path) -> None:
    multi_key_scan = (
        f"{HOSTNAME} ssh-ed25519 {KEY_A}\n"
        f"{HOSTNAME} ssh-rsa {KEY_B}\n"
    )
    result = stage_host_key_verification(
        tmp_path / "runs",
        host_id="production_vps",
        hostname=HOSTNAME,
        port=2222,
        policy="pinned",
        expected_fingerprint=FINGERPRINT_A,
        intent="existing_host",
        scanner=lambda _host, _port, _timeout: multi_key_scan,
    )

    assert result["ok"] is True
    assert result["policy"] == "pinned"
    assert result["selected_fingerprints"] == [FINGERPRINT_A]
    assert sorted(result["observed_fingerprints"]) == sorted(
        [FINGERPRINT_A, FINGERPRINT_B]
    )
    verification = read_host_key_verification(
        tmp_path / "runs", str(result["verification_id"])
    )
    staged = verification.staged_known_hosts_path.read_text(encoding="utf-8")
    assert staged == f"[{HOSTNAME}]:2222 ssh-ed25519 {KEY_A}\n"
    assert KEY_B not in staged

    public_and_manifest = json.dumps(result, sort_keys=True) + (
        verification.manifest_path.read_text(encoding="utf-8")
    )
    assert HOSTNAME not in public_and_manifest


def test_pinned_mismatch_and_missing_fingerprint_fail_without_staging(
    tmp_path: Path,
) -> None:
    def scanner(_host: str, _port: int, _timeout: int) -> str:
        return _scan_text()
    with pytest.raises(ValueError, match="requires an expected fingerprint"):
        stage_host_key_verification(
            tmp_path / "runs",
            host_id="production_vps",
            hostname=HOSTNAME,
            port=22,
            policy="pinned",
            intent="existing_host",
            scanner=scanner,
        )
    with pytest.raises(ValueError, match="did not match"):
        stage_host_key_verification(
            tmp_path / "runs",
            host_id="production_vps",
            hostname=HOSTNAME,
            port=22,
            policy="pinned",
            expected_fingerprint=FINGERPRINT_B,
            intent="existing_host",
            scanner=scanner,
        )
    assert not (tmp_path / "runs" / "ssh_known_hosts" / "staged").exists()


def test_tofu_requires_explicit_new_host_intent(tmp_path: Path) -> None:
    def scanner(_host: str, _port: int, _timeout: int) -> str:
        return _scan_text()
    with pytest.raises(ValueError, match="new-host onboarding"):
        stage_host_key_verification(
            tmp_path / "runs",
            host_id="new_vps",
            hostname=HOSTNAME,
            port=22,
            policy="tofu",
            intent="existing_host",
            scanner=scanner,
        )

    result = stage_host_key_verification(
        tmp_path / "runs",
        host_id="new_vps",
        hostname=HOSTNAME,
        port=22,
        policy="tofu",
        intent="new_host",
        scanner=scanner,
    )
    assert result["selected_fingerprints"] == [FINGERPRINT_A]


def test_rotation_requires_explicit_intent_and_previous_identity(
    tmp_path: Path,
) -> None:
    def scanner(_host: str, _port: int, _timeout: int) -> str:
        return _scan_text(KEY_B)
    with pytest.raises(ValueError, match="rotation intent"):
        stage_host_key_verification(
            tmp_path / "runs",
            host_id="production_vps",
            hostname=HOSTNAME,
            port=22,
            policy="rotation",
            expected_fingerprint=FINGERPRINT_B,
            intent="existing_host",
            previous_fingerprints=[FINGERPRINT_A],
            scanner=scanner,
        )
    with pytest.raises(ValueError, match="previous fingerprint"):
        stage_host_key_verification(
            tmp_path / "runs",
            host_id="production_vps",
            hostname=HOSTNAME,
            port=22,
            policy="rotation",
            expected_fingerprint=FINGERPRINT_B,
            intent="rotation",
            scanner=scanner,
        )

    result = stage_host_key_verification(
        tmp_path / "runs",
        host_id="production_vps",
        hostname=HOSTNAME,
        port=22,
        policy="rotation",
        expected_fingerprint=FINGERPRINT_B,
        intent="rotation",
        previous_fingerprints=[FINGERPRINT_A],
        scanner=scanner,
    )
    assert result["selected_fingerprints"] == [FINGERPRINT_B]
    assert result["previous_fingerprints"] == [FINGERPRINT_A]


def test_verification_reader_detects_staged_file_tampering(tmp_path: Path) -> None:
    result = stage_host_key_verification(
        tmp_path / "runs",
        host_id="candidate",
        hostname=HOSTNAME,
        port=22,
        policy="pinned",
        expected_fingerprint=FINGERPRINT_A,
        intent="new_host",
        scanner=lambda _host, _port, _timeout: _scan_text(),
    )
    verification = read_host_key_verification(
        tmp_path / "runs", str(result["verification_id"])
    )
    verification.staged_known_hosts_path.write_text(
        f"{HOSTNAME} ssh-ed25519 {KEY_B}\n", encoding="utf-8"
    )
    with pytest.raises(ValueError, match="hash mismatch"):
        read_host_key_verification(
            tmp_path / "runs", str(result["verification_id"])
        )


def _write_private_key(path: Path) -> Path:
    path.write_text(
        "-----BEGIN OPENSSH PRIVATE KEY-----\n"
        "host-key-options-test\n"
        "-----END OPENSSH PRIVATE KEY-----\n",
        encoding="utf-8",
    )
    path.chmod(0o600)
    return path.resolve()


def _credential_config(tmp_path: Path, key: Path) -> AppConfig:
    return AppConfig(
        repos={"sample": RepoConfig(path=str(tmp_path))},
        runs_dir="runs",
        config_dir=tmp_path,
        ssh=SSHConfig(
            enabled=True,
            credential_sources={
                "production": SSHCredentialSourceConfig(
                    type="process_environment"
                )
            },
            hosts={
                "production_vps": SSHHostConfig(
                    credential_binding=SSHCredentialBindingConfig(
                        source_id="production",
                        host_key_policy="pinned",
                        hostname="PROD_SSH_HOST",
                        user="PROD_SSH_USER",
                        port="PROD_SSH_PORT",
                        identity_file="PROD_SSH_KEY_PATH",
                        expected_host_key="PROD_SSH_HOST_KEY",
                    ),
                    command_profiles=[
                        SSHCommandProfileConfig(
                            command_id="health", argv=["true"]
                        )
                    ],
                )
            },
        ),
    )


def test_credential_ssh_payload_and_scp_use_only_managed_known_hosts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    key = _write_private_key(tmp_path / "id_ed25519")
    config = _credential_config(tmp_path, key)
    monkeypatch.setenv("PROD_SSH_HOST", HOSTNAME)
    monkeypatch.setenv("PROD_SSH_USER", "root")
    monkeypatch.setenv("PROD_SSH_PORT", "2222")
    monkeypatch.setenv("PROD_SSH_KEY_PATH", str(key))
    monkeypatch.setenv("PROD_SSH_HOST_KEY", FINGERPRINT_A)
    monkeypatch.setattr(ssh_commands.shutil, "which", lambda _name: "ssh.exe")
    monkeypatch.setattr(ssh_tools.shutil, "which", lambda _name: "scp.exe")

    expected_known_hosts = managed_known_hosts_path(config.resolve_runs_dir())
    expected_options = {
        "StrictHostKeyChecking=yes",
        f"UserKnownHostsFile={expected_known_hosts}",
        f"GlobalKnownHostsFile={__import__('os').devnull}",
    }

    profile = config.ssh.hosts["production_vps"].command_profiles[0]
    normal = build_ssh_argv(config, "production_vps", profile)
    payload = build_ssh_payload_argv(
        config, "production_vps", "exec bash -s --"
    )
    scp, _host, _destination = ssh_tools._scp_base(
        config, "production_vps", recursive=False
    )
    for argv in (normal, payload, scp):
        assert expected_options.issubset(set(argv))
        assert "StrictHostKeyChecking=accept-new" not in argv


def test_legacy_host_key_options_remain_unchanged(tmp_path: Path) -> None:
    config = AppConfig(
        repos={"sample": RepoConfig(path=str(tmp_path))},
        config_dir=tmp_path,
    )
    assert build_ssh_host_key_options(
        config, SSHConnection(destination="alias", mode="alias")
    ) == ["-o", "StrictHostKeyChecking=yes"]
    assert build_ssh_host_key_options(
        config,
        SSHConnection(
            destination="root@example.test", mode="connection_file"
        ),
    ) == ["-o", "StrictHostKeyChecking=accept-new"]
