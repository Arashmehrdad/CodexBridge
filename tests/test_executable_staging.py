from __future__ import annotations

from base64 import b64encode
from pathlib import Path

import pytest

from codexbridge.executable_staging import (
    build_executable_staging_manifest,
    stage_executable_input,
    validate_executable_staging_manifest,
)


def test_executable_staging_manifest_round_trips_binary_input_and_classifies_outputs(
    tmp_path: Path,
) -> None:
    payload = b"\x00\xffbinary\r\ntext"
    input_data = {
        "stdin_mode": "bytes",
        "stdin_base64": b64encode(payload).decode("ascii"),
        "stdout_mode": "protected_artifact",
        "stderr_mode": "bytes",
        "preserve_protected_artifacts": True,
    }
    run_id = "20260717T000000Z_executable_profile_deadbeef"
    manifest = build_executable_staging_manifest(
        input_data,
        run_id=run_id,
        lease_generation=3,
    )

    stage_executable_input(tmp_path, input_data, manifest)
    staged_input, output_paths, outputs = validate_executable_staging_manifest(
        tmp_path,
        manifest,
        run_id=run_id,
        lease_generation=3,
    )

    assert staged_input == payload
    assert output_paths == {
        "stdout": (tmp_path / "stdout.bin").resolve(),
        "stderr": (tmp_path / "stderr.bin").resolve(),
    }
    assert outputs == [
        {
            "stream": "stdout",
            "relative_path": "stdout.bin",
            "classification": "protected_evidence",
        },
        {
            "stream": "stderr",
            "relative_path": "stderr.bin",
            "classification": "staged_output",
        },
    ]


def test_executable_staging_manifest_rejects_identity_drift_and_input_changes(
    tmp_path: Path,
) -> None:
    input_data = {
        "stdin_mode": "text",
        "stdin_text": "Write-Output ok",
        "stdout_mode": "protected_artifact",
        "stderr_mode": "protected_artifact",
        "preserve_protected_artifacts": True,
    }
    run_id = "20260717T000000Z_executable_profile_deadbeef"
    manifest = build_executable_staging_manifest(
        input_data,
        run_id=run_id,
        lease_generation=1,
    )
    stage_executable_input(tmp_path, input_data, manifest)

    with pytest.raises(ValueError, match="run identity"):
        validate_executable_staging_manifest(
            tmp_path,
            manifest,
            run_id="20260717T000001Z_executable_profile_feedface",
            lease_generation=1,
        )
    with pytest.raises(ValueError, match="lease generation"):
        validate_executable_staging_manifest(
            tmp_path,
            manifest,
            run_id=run_id,
            lease_generation=2,
        )

    (tmp_path / "inputs" / "stdin.bin").write_bytes(b"changed")
    with pytest.raises(ValueError, match="size changed|SHA-256 changed"):
        validate_executable_staging_manifest(
            tmp_path,
            manifest,
            run_id=run_id,
            lease_generation=1,
        )


def test_executable_staging_manifest_rejects_escaping_output_path(tmp_path: Path) -> None:
    manifest = build_executable_staging_manifest(
        {
            "stdin_mode": "none",
            "stdout_mode": "protected_artifact",
            "stderr_mode": "protected_artifact",
        },
        run_id="20260717T000000Z_executable_profile_deadbeef",
        lease_generation=1,
    )
    manifest["outputs"][0]["relative_path"] = "../stdout.bin"

    with pytest.raises(ValueError, match="escapes the run directory"):
        validate_executable_staging_manifest(
            tmp_path,
            manifest,
            run_id="20260717T000000Z_executable_profile_deadbeef",
            lease_generation=1,
        )
