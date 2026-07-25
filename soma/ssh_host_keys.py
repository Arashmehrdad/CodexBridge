from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterable, Sequence
from uuid import uuid4

from .return_loop.atomic_writer import atomic_write_json, atomic_write_text

SSH_KNOWN_HOSTS_DIR = "ssh_known_hosts"
SSH_STAGED_HOST_KEYS_DIR = "staged"
HOST_KEY_SCHEMA_VERSION = "ssh-host-key-verification.v1"

_HOST_ID_RE = re.compile(r"^[A-Za-z0-9_-]+$")
_HOSTNAME_RE = re.compile(r"^[A-Za-z0-9.-]+$")
_KEY_TYPE_RE = re.compile(r"^[A-Za-z0-9@._+-]+$")
_KEY_DATA_RE = re.compile(r"^[A-Za-z0-9+/]+={0,2}$")
_FINGERPRINT_RE = re.compile(r"^SHA256:[A-Za-z0-9+/]+={0,2}$")
_VERIFICATION_ID_RE = re.compile(
    r"^\d{8}T\d{6}Z_sshkey_[0-9a-f]{8}$"
)

HostKeyScanner = Callable[[str, int, int], str]


@dataclass(frozen=True)
class HostKeyObservation:
    key_type: str
    key_data: str
    fingerprint: str
    known_hosts_line: str


@dataclass(frozen=True)
class HostKeyVerification:
    verification_id: str
    host_id: str
    policy: str
    selected_fingerprints: tuple[str, ...]
    observed_fingerprints: tuple[str, ...]
    previous_fingerprints: tuple[str, ...]
    staged_known_hosts_path: Path
    manifest_path: Path


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _verification_id() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{stamp}_sshkey_{uuid4().hex[:8]}"


def _normalize_host_id(host_id: str) -> str:
    value = str(host_id or "").strip()
    if not _HOST_ID_RE.fullmatch(value):
        raise ValueError("SSH host-key host_id must use letters, numbers, _ or -")
    return value


def _normalize_hostname(hostname: str) -> str:
    value = str(hostname or "").strip()
    if not _HOSTNAME_RE.fullmatch(value):
        raise ValueError("SSH host-key hostname is invalid")
    return value


def _normalize_port(port: int) -> int:
    value = int(port)
    if not 1 <= value <= 65535:
        raise ValueError("SSH host-key port must be between 1 and 65535")
    return value


def _normalize_fingerprint(value: str, *, required: bool = False) -> str:
    fingerprint = str(value or "").strip().rstrip("=")
    if not fingerprint:
        if required:
            raise ValueError("SSH host-key policy requires an expected fingerprint")
        return ""
    if not _FINGERPRINT_RE.fullmatch(fingerprint):
        raise ValueError("SSH host-key fingerprint is invalid")
    return fingerprint


def _normalize_fingerprints(values: Iterable[str]) -> tuple[str, ...]:
    normalized = {
        _normalize_fingerprint(value, required=True)
        for value in values
        if str(value or "").strip()
    }
    return tuple(sorted(normalized))


def managed_known_hosts_path(runs_dir: Path) -> Path:
    return (Path(runs_dir).resolve() / SSH_KNOWN_HOSTS_DIR / "known_hosts").resolve()


def _staged_directory(runs_dir: Path, verification_id: str) -> Path:
    if not _VERIFICATION_ID_RE.fullmatch(verification_id):
        raise ValueError("Invalid SSH host-key verification_id")
    root = (
        Path(runs_dir).resolve()
        / SSH_KNOWN_HOSTS_DIR
        / SSH_STAGED_HOST_KEYS_DIR
    ).resolve()
    candidate = (root / verification_id).resolve()
    candidate.relative_to(root)
    return candidate


def known_hosts_host_token(hostname: str, port: int) -> str:
    normalized_host = _normalize_hostname(hostname)
    normalized_port = _normalize_port(port)
    return (
        normalized_host
        if normalized_port == 22
        else f"[{normalized_host}]:{normalized_port}"
    )


def _fingerprint_key_data(key_data: str) -> str:
    try:
        decoded = base64.b64decode(key_data.encode("ascii"), validate=True)
    except (ValueError, UnicodeError) as exc:
        raise ValueError("SSH host-key data is not valid base64") from exc
    if not decoded:
        raise ValueError("SSH host-key data is empty")
    digest = hashlib.sha256(decoded).digest()
    encoded = base64.b64encode(digest).decode("ascii").rstrip("=")
    return f"SHA256:{encoded}"


def parse_host_key_scan(
    text: str,
    *,
    hostname: str,
    port: int,
) -> tuple[HostKeyObservation, ...]:
    """Parse ssh-keyscan output into canonical known-host observations."""

    if "\x00" in text:
        raise ValueError("SSH host-key scan contains a NUL byte")
    host_token = known_hosts_host_token(hostname, port)
    observations: dict[tuple[str, str], HostKeyObservation] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        fields = line.split()
        if len(fields) < 3:
            raise ValueError("SSH host-key scan contains a malformed line")
        key_type = fields[1]
        key_data = fields[2]
        if not _KEY_TYPE_RE.fullmatch(key_type):
            raise ValueError("SSH host-key scan contains an invalid key type")
        if not _KEY_DATA_RE.fullmatch(key_data):
            raise ValueError("SSH host-key scan contains invalid key data")
        fingerprint = _fingerprint_key_data(key_data)
        observation = HostKeyObservation(
            key_type=key_type,
            key_data=key_data,
            fingerprint=fingerprint,
            known_hosts_line=f"{host_token} {key_type} {key_data}",
        )
        observations[(key_type, fingerprint)] = observation
    if not observations:
        raise ValueError("SSH host-key scan returned no usable host keys")
    return tuple(
        observations[key]
        for key in sorted(observations, key=lambda item: (item[0], item[1]))
    )


def _default_scanner(hostname: str, port: int, timeout_seconds: int) -> str:
    executable = shutil.which("ssh-keyscan")
    if not executable:
        raise ValueError("ssh-keyscan was not found on PATH")
    try:
        completed = subprocess.run(
            [
                executable,
                "-T",
                str(timeout_seconds),
                "-p",
                str(port),
                hostname,
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            shell=False,
            timeout=timeout_seconds + 3,
            check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except subprocess.TimeoutExpired as exc:
        raise ValueError("SSH host-key scan timed out") from exc
    except (OSError, PermissionError) as exc:
        raise ValueError("SSH host-key scan could not start") from exc
    if completed.returncode != 0 and not completed.stdout.strip():
        raise ValueError("SSH host-key scan failed")
    return completed.stdout


def scan_stable_host_keys(
    hostname: str,
    port: int,
    *,
    attempts: int = 2,
    timeout_seconds: int = 5,
    scanner: HostKeyScanner | None = None,
) -> tuple[HostKeyObservation, ...]:
    """Require repeated scans to produce exactly one stable host-key set."""

    normalized_host = _normalize_hostname(hostname)
    normalized_port = _normalize_port(port)
    if not 2 <= int(attempts) <= 5:
        raise ValueError("SSH host-key scan attempts must be between 2 and 5")
    if not 1 <= int(timeout_seconds) <= 30:
        raise ValueError("SSH host-key scan timeout must be between 1 and 30 seconds")
    scan = scanner or _default_scanner
    observations: list[tuple[HostKeyObservation, ...]] = []
    errors: list[str] = []
    for _index in range(int(attempts)):
        try:
            text = scan(normalized_host, normalized_port, int(timeout_seconds))
            observations.append(
                parse_host_key_scan(
                    text,
                    hostname=normalized_host,
                    port=normalized_port,
                )
            )
        except ValueError as exc:
            errors.append(str(exc))
    if len(observations) != int(attempts):
        raise ValueError(
            "SSH host-key identity could not be observed consistently: "
            + (errors[-1] if errors else "scan failed")
        )
    reference = tuple(
        (item.key_type, item.fingerprint) for item in observations[0]
    )
    for candidate in observations[1:]:
        identity = tuple((item.key_type, item.fingerprint) for item in candidate)
        if identity != reference:
            raise ValueError("SSH host-key scans did not converge on one identity")
    return observations[0]


def _select_host_keys(
    observations: Sequence[HostKeyObservation],
    *,
    policy: str,
    expected_fingerprint: str,
    intent: str,
) -> tuple[HostKeyObservation, ...]:
    normalized_policy = str(policy or "").strip().lower()
    normalized_intent = str(intent or "").strip().lower()
    if normalized_policy not in {"pinned", "tofu", "rotation"}:
        raise ValueError("SSH host-key policy must be pinned, tofu, or rotation")

    expected = _normalize_fingerprint(
        expected_fingerprint,
        required=normalized_policy in {"pinned", "rotation"},
    )
    observed = {item.fingerprint for item in observations}
    if normalized_policy == "tofu":
        if normalized_intent != "new_host":
            raise ValueError("SSH TOFU policy is allowed only for explicit new-host onboarding")
        if expected and expected not in observed:
            raise ValueError("SSH host-key fingerprint did not match the expected identity")
        selected = (
            tuple(item for item in observations if item.fingerprint == expected)
            if expected
            else tuple(observations)
        )
    elif normalized_policy == "rotation":
        if normalized_intent != "rotation":
            raise ValueError("SSH rotation policy requires explicit rotation intent")
        selected = tuple(
            item for item in observations if item.fingerprint == expected
        )
    else:
        if normalized_intent not in {"existing_host", "new_host"}:
            raise ValueError("SSH pinned policy requires explicit host intent")
        selected = tuple(
            item for item in observations if item.fingerprint == expected
        )

    if not selected:
        raise ValueError("SSH host-key fingerprint did not match the expected identity")
    return selected


def stage_host_key_verification(
    runs_dir: Path,
    *,
    host_id: str,
    hostname: str,
    port: int,
    policy: str,
    expected_fingerprint: str = "",
    intent: str,
    previous_fingerprints: Sequence[str] = (),
    attempts: int = 2,
    timeout_seconds: int = 5,
    scanner: HostKeyScanner | None = None,
) -> dict[str, object]:
    """Verify a candidate host identity and write a staged known_hosts artifact.

    This function never changes the active managed known_hosts file. Promotion is
    owned by the later transactional activation worker.
    """

    normalized_host_id = _normalize_host_id(host_id)
    normalized_hostname = _normalize_hostname(hostname)
    normalized_port = _normalize_port(port)
    normalized_policy = str(policy or "").strip().lower()
    previous = _normalize_fingerprints(previous_fingerprints)
    observations = scan_stable_host_keys(
        normalized_hostname,
        normalized_port,
        attempts=attempts,
        timeout_seconds=timeout_seconds,
        scanner=scanner,
    )
    selected = _select_host_keys(
        observations,
        policy=normalized_policy,
        expected_fingerprint=expected_fingerprint,
        intent=intent,
    )
    if normalized_policy == "rotation" and not previous:
        raise ValueError("SSH host-key rotation requires the previous fingerprint identity")

    verification_id = _verification_id()
    stage_dir = _staged_directory(Path(runs_dir), verification_id)
    staged_path = stage_dir / "known_hosts"
    manifest_path = stage_dir / "manifest.json"
    staged_text = "".join(f"{item.known_hosts_line}\n" for item in selected)
    atomic_write_text(staged_path, staged_text)

    selected_fingerprints = tuple(sorted({item.fingerprint for item in selected}))
    observed_fingerprints = tuple(
        sorted({item.fingerprint for item in observations})
    )
    host_identity_sha256 = hashlib.sha256(
        f"{os.path.normcase(normalized_hostname)}:{normalized_port}".encode("utf-8")
    ).hexdigest()
    relative_stage = (
        f"{SSH_KNOWN_HOSTS_DIR}/{SSH_STAGED_HOST_KEYS_DIR}/"
        f"{verification_id}/known_hosts"
    )
    manifest = {
        "schema_version": HOST_KEY_SCHEMA_VERSION,
        "verification_id": verification_id,
        "host_id": normalized_host_id,
        "policy": normalized_policy,
        "intent": str(intent or "").strip().lower(),
        "host_identity_sha256": host_identity_sha256,
        "selected_fingerprints": list(selected_fingerprints),
        "observed_fingerprints": list(observed_fingerprints),
        "previous_fingerprints": list(previous),
        "scan_attempts": int(attempts),
        "staged_known_hosts_relative_path": relative_stage,
        "staged_known_hosts_sha256": hashlib.sha256(
            staged_text.encode("utf-8")
        ).hexdigest(),
        "created_at": _utc_now(),
        "status": "verified",
    }
    atomic_write_json(manifest_path, manifest)
    return {
        "ok": True,
        "verification_id": verification_id,
        "status": "verified",
        "host_id": normalized_host_id,
        "policy": normalized_policy,
        "intent": manifest["intent"],
        "host_identity_sha256": host_identity_sha256,
        "selected_fingerprints": list(selected_fingerprints),
        "observed_fingerprints": list(observed_fingerprints),
        "previous_fingerprints": list(previous),
        "scan_attempts": int(attempts),
        "staged_known_hosts_relative_path": relative_stage,
        "staged_known_hosts_sha256": manifest["staged_known_hosts_sha256"],
        "created_at": manifest["created_at"],
        "error": "",
    }


def read_host_key_verification(
    runs_dir: Path,
    verification_id: str,
) -> HostKeyVerification:
    stage_dir = _staged_directory(Path(runs_dir), verification_id)
    manifest_path = stage_dir / "manifest.json"
    staged_path = stage_dir / "known_hosts"
    if (
        manifest_path.is_symlink()
        or staged_path.is_symlink()
        or not manifest_path.is_file()
        or not staged_path.is_file()
    ):
        raise ValueError("Unknown SSH host-key verification_id")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("SSH host-key verification manifest is invalid") from exc
    if manifest.get("verification_id") != verification_id:
        raise ValueError("SSH host-key verification manifest ID mismatch")
    staged_bytes = staged_path.read_bytes()
    if hashlib.sha256(staged_bytes).hexdigest() != manifest.get(
        "staged_known_hosts_sha256"
    ):
        raise ValueError("SSH staged known_hosts hash mismatch")
    return HostKeyVerification(
        verification_id=verification_id,
        host_id=str(manifest.get("host_id") or ""),
        policy=str(manifest.get("policy") or ""),
        selected_fingerprints=tuple(manifest.get("selected_fingerprints") or ()),
        observed_fingerprints=tuple(manifest.get("observed_fingerprints") or ()),
        previous_fingerprints=tuple(manifest.get("previous_fingerprints") or ()),
        staged_known_hosts_path=staged_path,
        manifest_path=manifest_path,
    )
