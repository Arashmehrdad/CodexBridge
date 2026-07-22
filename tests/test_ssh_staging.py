from __future__ import annotations

from pathlib import Path

from soma.ssh_staging import (
    build_ssh_staging_manifest,
    stage_ssh_inputs,
    validate_ssh_staging_manifest,
)


def test_reviewed_script_staging_revalidation_is_repeatable(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    run_id = "reviewed-run"
    script = "printf '%s\\n' repeatable\n"
    manifest = build_ssh_staging_manifest(
        tool="ssh_reviewed_script",
        run_id=run_id,
        lease_generation=3,
        script=script,
    )
    stage_ssh_inputs(run_dir, script=script, manifest=manifest)

    first = validate_ssh_staging_manifest(
        run_dir,
        manifest,
        tool="ssh_reviewed_script",
        run_id=run_id,
        lease_generation=3,
    )
    second = validate_ssh_staging_manifest(
        run_dir,
        manifest,
        tool="ssh_reviewed_script",
        run_id=run_id,
        lease_generation=3,
    )

    assert first == second
    assert first[0] == script
    assert first[1] == {
        "stdout": run_dir / "stdout.txt",
        "stderr": run_dir / "stderr.txt",
    }
    assert (run_dir / "inputs" / "reviewed-script.bin").read_bytes() == script.encode(
        "utf-8"
    )


def test_remote_controller_staging_revalidation_is_repeatable(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    run_id = "controller-run"
    manifest = build_ssh_staging_manifest(
        tool="ssh_monitored_command",
        run_id=run_id,
        lease_generation=7,
    )

    first = validate_ssh_staging_manifest(
        run_dir,
        manifest,
        tool="ssh_monitored_command",
        run_id=run_id,
        lease_generation=7,
    )
    second = validate_ssh_staging_manifest(
        run_dir,
        manifest,
        tool="ssh_monitored_command",
        run_id=run_id,
        lease_generation=7,
    )

    assert first == second
    assert first[0] is None
    assert first[1] == {
        "stdout": run_dir / "stdout.txt",
        "stderr": run_dir / "stderr.txt",
    }
    assert first[2] == [
        {
            "stream": "stdout",
            "relative_path": "stdout.txt",
            "classification": "protected_evidence",
        },
        {
            "stream": "stderr",
            "relative_path": "stderr.txt",
            "classification": "protected_evidence",
        },
    ]
