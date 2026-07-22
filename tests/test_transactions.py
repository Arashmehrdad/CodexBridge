from __future__ import annotations

from pathlib import Path

from codexbridge.transactions import (
    TransactionContext,
    build_transaction_result,
    rollback_transaction,
)


def test_transaction_context_does_not_scan_unrelated_workspace(
    monkeypatch, tmp_path: Path
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".git").mkdir()
    target = repo / "sample.txt"
    target.write_text("before\n", encoding="utf-8")
    unrelated = repo / "runs" / "large-artifact.bin"
    unrelated.parent.mkdir()
    unrelated.write_bytes(b"artifact")
    original_stat = Path.stat

    def guarded_stat(path: Path, *args, **kwargs):
        if path == unrelated:
            raise AssertionError("transaction scanned an unrelated workspace file")
        return original_stat(path, *args, **kwargs)

    monkeypatch.setattr(Path, "stat", guarded_stat)

    context = TransactionContext(repo, ["sample.txt"])

    assert context.file_snapshots["sample.txt"].content == b"before\n"


def test_transaction_context_tracks_baseline_and_rollback(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".git").mkdir()
    target = repo / "sample.txt"
    target.write_text("before\n", encoding="utf-8")
    context = TransactionContext(repo, ["sample.txt"])
    target.write_text("after\n", encoding="utf-8")

    rollback_transaction(
        context,
        write_bytes=lambda path, data: path.write_bytes(data),
        unlink_path=lambda path: path.unlink(),
    )

    result = build_transaction_result(context)
    assert result["rollback"]["attempted"] is True
    assert target.read_text(encoding="utf-8") == "before\n"


def test_transaction_context_reports_introduced_changes(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".git").mkdir()
    target = repo / "sample.txt"
    target.write_text("before\n", encoding="utf-8")
    context = TransactionContext(repo, ["sample.txt"])
    target.write_text("after\n", encoding="utf-8")

    result = build_transaction_result(context)

    assert result["introduced_changes"] == ["sample.txt"]


def test_transaction_context_preserves_preexisting_changes(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".git").mkdir()
    existing = repo / "preexisting.txt"
    target = repo / "sample.txt"
    existing.write_text("dirty\n", encoding="utf-8")
    target.write_text("before\n", encoding="utf-8")
    context = TransactionContext(repo, ["sample.txt"])
    context.baseline_dirty_files = ["preexisting.txt"]
    existing.write_text("still dirty\n", encoding="utf-8")
    target.write_text("after\n", encoding="utf-8")

    result = build_transaction_result(context)

    assert result["introduced_changes"] == ["sample.txt"]
    assert result["preserved_preexisting_changes"] == ["preexisting.txt"]
