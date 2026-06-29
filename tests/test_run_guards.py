from __future__ import annotations

from pathlib import Path

from codexbridge.run_guards import (
    allowed_write_directories,
    assess_implementation_output,
    assess_plan_output,
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
    assert drifted.blocked is True
    assert drifted.plan_conformance is False
