from __future__ import annotations

from pathlib import Path

import pytest

from codexbridge.run_artifacts import resolve_output_artifacts


def _run(run_dir: Path, manifest: object | None) -> dict:
    input_data = {} if manifest is None else {"staging_manifest": manifest}
    return {
        "run_id": "20260722T060000Z_executable_profile_deadbeef",
        "run_dir": str(run_dir),
        "input": input_data,
    }


def test_resolver_uses_manifest_listed_binary_outputs(tmp_path: Path) -> None:
    run_dir = tmp_path / "runs" / "run"
    run_dir.mkdir(parents=True)
    run = _run(
        run_dir,
        {
            "version": 1,
            "invoking_run_id": "20260722T060000Z_executable_profile_deadbeef",
            "outputs": [
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
            ],
        },
    )

    artifacts = resolve_output_artifacts(run, tmp_path / "runs")

    assert artifacts["stdout"].path == (run_dir / "stdout.bin").resolve()
    assert artifacts["stdout"].classification == "protected_evidence"
    assert artifacts["stderr"].classification == "staged_output"
    assert artifacts["stdout"].manifest_source == "staging_manifest"


def test_resolver_uses_fixed_legacy_text_adapter_without_manifest(
    tmp_path: Path,
) -> None:
    run_dir = tmp_path / "runs" / "run"
    run_dir.mkdir(parents=True)

    artifacts = resolve_output_artifacts(_run(run_dir, None), tmp_path / "runs")

    assert artifacts["stdout"].path == (run_dir / "stdout.txt").resolve()
    assert artifacts["stderr"].path == (run_dir / "stderr.txt").resolve()
    assert artifacts["stdout"].manifest_source == "legacy_output_adapter_v1"


def test_resolver_rejects_manifest_escape_instead_of_guessing_output(
    tmp_path: Path,
) -> None:
    run_dir = tmp_path / "runs" / "run"
    run_dir.mkdir(parents=True)
    run = _run(
        run_dir,
        {
            "version": 1,
            "invoking_run_id": "20260722T060000Z_executable_profile_deadbeef",
            "outputs": [
                {
                    "stream": "stdout",
                    "relative_path": "../stdout.bin",
                    "classification": "protected_evidence",
                },
                {
                    "stream": "stderr",
                    "relative_path": "stderr.bin",
                    "classification": "protected_evidence",
                },
            ],
        },
    )

    with pytest.raises(ValueError, match="escapes the run directory"):
        resolve_output_artifacts(run, tmp_path / "runs")
