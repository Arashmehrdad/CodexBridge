from __future__ import annotations

from pathlib import Path

from soma.run_guards import (
    allowed_write_directories,
    assess_implementation_output,
    assess_implementation_output_against,
    assess_plan_output,
    changed_workspace_paths,
    derive_requirement_manifest,
    out_of_scope_workspace_changes,
    snapshot_workspace,
)


def test_allowed_write_directories_use_existing_allowed_file_parents(
    tmp_path: Path,
) -> None:
    docs = tmp_path / "docs"
    source = tmp_path / "src" / "package"
    tests = tmp_path / "tests" / "unit"
    for directory in (docs, source, tests):
        directory.mkdir(parents=True)

    result = allowed_write_directories(
        tmp_path,
        [
            "docs/plan.md",
            "src/package/new_module.py",
            "tests/unit/test_new_module.py",
            "README.md",
        ],
    )

    assert result == [docs.resolve(), source.resolve(), tests.resolve()]


def test_workspace_snapshot_detects_ignored_untracked_root_write(
    tmp_path: Path,
) -> None:
    before = snapshot_workspace(tmp_path)
    (tmp_path / "write_test.tmp").write_text("diagnostic", encoding="utf-8")
    after = snapshot_workspace(tmp_path)

    assert out_of_scope_workspace_changes(before, after, ["docs/allowed.md"]) == [
        "write_test.tmp"
    ]


def test_workspace_snapshot_ignores_tool_cache_files(tmp_path: Path) -> None:
    before = snapshot_workspace(tmp_path)
    cache = tmp_path / ".pytest_cache"
    cache.mkdir()
    (cache / "state").write_text("x", encoding="utf-8")
    after = snapshot_workspace(tmp_path)

    assert out_of_scope_workspace_changes(before, after, []) == []


def test_workspace_snapshot_prunes_nested_git_and_ignored_runs_root(
    tmp_path: Path,
) -> None:
    before = snapshot_workspace(tmp_path, [tmp_path / "runs"])
    nested_git = tmp_path / "nested" / ".git"
    nested_git.mkdir(parents=True)
    (nested_git / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")
    ignored_run_file = tmp_path / "runs" / "job" / "stdout.txt"
    ignored_run_file.parent.mkdir(parents=True)
    ignored_run_file.write_text("ignored\n", encoding="utf-8")
    after = snapshot_workspace(tmp_path, [tmp_path / "runs"])

    assert changed_workspace_paths(before, after) == []


def test_blocked_plan_status_is_not_treated_as_ready() -> None:
    outcome = assess_plan_output("PLAN_STATUS: blocked")

    assert outcome.blocked is True
    assert outcome.blockers


def test_blocked_summary_is_not_treated_as_success() -> None:
    outcome = assess_implementation_output(
        "I couldn't complete a repository edit because this session is write-blocked."
    )

    assert outcome.blocked is True
    assert outcome.blockers


def test_explicit_status_and_plan_conformance_are_parsed() -> None:
    completed = assess_implementation_output(
        "Work complete.\nFINAL_STATUS: completed\nPLAN_CONFORMANCE: yes\nBLOCKERS: none"
    )
    drifted = assess_implementation_output(
        "FINAL_STATUS: completed\nPLAN_CONFORMANCE: no\nBLOCKERS: changed scope"
    )

    assert completed.blocked is False
    assert completed.plan_conformance is True
    assert drifted.blocked is False
    assert drifted.plan_conformance is False


def test_requirement_manifest_is_derived_stably() -> None:
    manifest = derive_requirement_manifest(
        "\n".join(
            [
                "REQ-001 Independent requirement accounting",
                "REQ-002 Canonical repository identity",
                "REQ-001 Independent requirement accounting",
            ]
        )
    )

    assert manifest == [
        {
            "requirement_id": "REQ-001",
            "text": "REQ-001 Independent requirement accounting",
            "mandatory": True,
        },
        {
            "requirement_id": "REQ-002",
            "text": "REQ-002 Canonical repository identity",
            "mandatory": True,
        },
    ]


def test_requirement_reconciliation_tracks_missing_and_incomplete_ids() -> None:
    outcome = assess_implementation_output_against(
        "\n".join(
            [
                "COMPLETED_REQUIREMENT: REQ-001 Independent requirement accounting",
                "SKIPPED_REQUIREMENT: REQ-003 Capability metadata schemas remain pending",
                "VALIDATION_STATUS: passed",
                "FINAL_STATUS: completed",
                "PLAN_CONFORMANCE: yes",
            ]
        ),
        ["REQ-001", "REQ-002", "REQ-003"],
    )

    assert outcome.completed_requirements == [
        "REQ-001 Independent requirement accounting"
    ]
    assert outcome.skipped_requirements == [
        "REQ-003 Capability metadata schemas remain pending"
    ]
    assert outcome.failed_requirements == []
    assert outcome.missing_requirements == ["REQ-002"]
    assert outcome.mandatory_incomplete == ["REQ-002", "REQ-003"]
