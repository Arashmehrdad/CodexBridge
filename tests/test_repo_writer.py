"""
Tests for codexbridge/repo_writer.py and related server tools.
No CodexRunner, Gemini, Ollama, or local-model calls are made.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path

import pytest

from codexbridge import repo_writer as rw
from codexbridge.repo_writer import (
    preview_repo_patch,
    apply_repo_patch,
    revert_managed_patch,
    create_repo_file,
    delete_repo_file,
    move_repo_file,
    _sha256_file,
    _make_patch_id,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_repo(tmp_path: Path) -> Path:
    (tmp_path / ".git").mkdir()
    return tmp_path


def write_file(path: Path, content: str = "hello\n") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def sha256_of(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_file(path: Path) -> str:
    return _sha256_file(path)


# ---------------------------------------------------------------------------
# preview_repo_patch – success
# ---------------------------------------------------------------------------


def test_preview_returns_patch_id_and_diff(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    runs = tmp_path / "runs"
    write_file(repo / "hello.py", "def greet():\n    return 'hello'\n")
    sha = sha256_file(repo / "hello.py")
    ops = [
        {
            "path": "hello.py",
            "expected_sha256": sha,
            "old_text": "return 'hello'",
            "new_text": "return 'hi'",
        }
    ]
    result = preview_repo_patch(repo, ops, runs)
    assert result["ok"] is True
    assert result["patch_id"]
    assert "hello.py" in result["diff"]
    assert result["changed_files"] == ["hello.py"]
    assert result["changed_lines"] >= 2
    assert result["validation_errors"] == []


def test_preview_makes_no_changes(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    runs = tmp_path / "runs"
    write_file(repo / "src.py", "x = 1\n")
    sha = sha256_file(repo / "src.py")
    original = (repo / "src.py").read_text(encoding="utf-8")
    ops = [
        {
            "path": "src.py",
            "expected_sha256": sha,
            "old_text": "x = 1",
            "new_text": "x = 2",
        }
    ]
    preview_repo_patch(repo, ops, runs)
    assert (repo / "src.py").read_text(encoding="utf-8") == original


def test_preview_stores_manifest(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    runs = tmp_path / "runs"
    write_file(repo / "a.py", "a = 1\n")
    sha = sha256_file(repo / "a.py")
    ops = [
        {
            "path": "a.py",
            "expected_sha256": sha,
            "old_text": "a = 1",
            "new_text": "a = 99",
        }
    ]
    result = preview_repo_patch(repo, ops, runs)
    patch_dir = runs / "managed_patches" / result["patch_id"]
    assert (patch_dir / "manifest.json").exists()


# ---------------------------------------------------------------------------
# preview_repo_patch – rejection cases
# ---------------------------------------------------------------------------


def test_preview_rejects_stale_sha256(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    runs = tmp_path / "runs"
    write_file(repo / "b.py", "b = 1\n")
    ops = [
        {
            "path": "b.py",
            "expected_sha256": "a" * 64,
            "old_text": "b = 1",
            "new_text": "b = 2",
        }
    ]
    result = preview_repo_patch(repo, ops, runs)
    assert result["ok"] is False
    assert result["validation_errors"]


def test_preview_rejects_missing_old_text(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    runs = tmp_path / "runs"
    write_file(repo / "c.py", "c = 1\n")
    sha = sha256_file(repo / "c.py")
    ops = [
        {
            "path": "c.py",
            "expected_sha256": sha,
            "old_text": "DOES_NOT_EXIST",
            "new_text": "c = 2",
        }
    ]
    result = preview_repo_patch(repo, ops, runs)
    assert result["ok"] is False
    assert any("not found" in e for e in result["validation_errors"])


def test_preview_rejects_ambiguous_old_text(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    runs = tmp_path / "runs"
    write_file(repo / "d.py", "x = 1\nx = 1\n")
    sha = sha256_file(repo / "d.py")
    ops = [
        {
            "path": "d.py",
            "expected_sha256": sha,
            "old_text": "x = 1",
            "new_text": "x = 9",
        }
    ]
    result = preview_repo_patch(repo, ops, runs)
    assert result["ok"] is False
    assert any("times" in e for e in result["validation_errors"])


def test_preview_and_apply_compose_non_overlapping_same_file_edits(
    tmp_path: Path,
) -> None:
    repo = make_repo(tmp_path)
    runs = tmp_path / "runs"
    original = "alpha = 1\nmiddle = 2\nomega = 3\n"
    write_file(repo / "composed.py", original)
    sha = sha256_file(repo / "composed.py")
    ops = [
        {
            "path": "composed.py",
            "expected_sha256": sha,
            "old_text": "alpha = 1",
            "new_text": "alpha = 10",
        },
        {
            "path": "composed.py",
            "expected_sha256": sha,
            "old_text": "omega = 3",
            "new_text": "omega = 30",
        },
    ]

    preview = preview_repo_patch(repo, ops, runs)

    assert preview["ok"] is True
    assert preview["changed_files"] == ["composed.py"]
    assert "alpha = 10" in preview["diff"]
    assert "omega = 30" in preview["diff"]

    applied = apply_repo_patch(repo, ops, preview["patch_id"], runs)

    assert applied["changed_files"] == ["composed.py"]
    assert (repo / "composed.py").read_text(encoding="utf-8") == (
        "alpha = 10\nmiddle = 2\nomega = 30\n"
    )


def test_preview_rejects_overlapping_same_file_edits(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    runs = tmp_path / "runs"
    write_file(repo / "e.py", "e = 1\n")
    sha = sha256_file(repo / "e.py")
    ops = [
        {
            "path": "e.py",
            "expected_sha256": sha,
            "old_text": "e = 1",
            "new_text": "e = 2",
        },
        {
            "path": "e.py",
            "expected_sha256": sha,
            "old_text": "e = 1",
            "new_text": "e = 3",
        },
    ]
    result = preview_repo_patch(repo, ops, runs)
    assert result["ok"] is False
    assert any("overlaps" in e.lower() for e in result["validation_errors"])


def test_preview_rejects_absolute_path(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    runs = tmp_path / "runs"
    ops = [
        {
            "path": str(tmp_path / "secret.py"),
            "expected_sha256": "x" * 64,
            "old_text": "a",
            "new_text": "b",
        }
    ]
    result = preview_repo_patch(repo, ops, runs)
    assert result["ok"] is False


def test_preview_rejects_traversal_path(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    runs = tmp_path / "runs"
    ops = [
        {
            "path": "../outside.py",
            "expected_sha256": "x" * 64,
            "old_text": "a",
            "new_text": "b",
        }
    ]
    result = preview_repo_patch(repo, ops, runs)
    assert result["ok"] is False


def test_preview_rejects_blocked_extension(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    runs = tmp_path / "runs"
    write_file(repo / "cert.pem", "-----BEGIN CERTIFICATE-----\n")
    sha = sha256_file(repo / "cert.pem")
    ops = [
        {
            "path": "cert.pem",
            "expected_sha256": sha,
            "old_text": "BEGIN",
            "new_text": "END",
        }
    ]
    result = preview_repo_patch(repo, ops, runs)
    assert result["ok"] is False


def test_preview_rejects_bak_and_tmp(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    runs = tmp_path / "runs"
    for name in ["file.bak", "file.tmp"]:
        write_file(repo / name, "data\n")
        sha = sha256_file(repo / name)
        ops = [
            {"path": name, "expected_sha256": sha, "old_text": "data", "new_text": "x"}
        ]
        result = preview_repo_patch(repo, ops, runs)
        assert result["ok"] is False, f"Expected rejection of {name}"


def test_preview_rejects_venv_path(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    runs = tmp_path / "runs"
    ops = [
        {
            "path": ".venv/lib/site.py",
            "expected_sha256": "x" * 64,
            "old_text": "x",
            "new_text": "y",
        }
    ]
    result = preview_repo_patch(repo, ops, runs)
    assert result["ok"] is False


def test_preview_rejects_git_path(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    runs = tmp_path / "runs"
    ops = [
        {
            "path": ".git/config",
            "expected_sha256": "x" * 64,
            "old_text": "x",
            "new_text": "y",
        }
    ]
    result = preview_repo_patch(repo, ops, runs)
    assert result["ok"] is False


# ---------------------------------------------------------------------------
# apply_repo_patch – success and stale-hash rejection
# ---------------------------------------------------------------------------


def test_apply_writes_file(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    runs = tmp_path / "runs"
    write_file(repo / "apply.py", "x = 1\n")
    sha = sha256_file(repo / "apply.py")
    ops = [
        {
            "path": "apply.py",
            "expected_sha256": sha,
            "old_text": "x = 1",
            "new_text": "x = 99",
        }
    ]
    preview = preview_repo_patch(repo, ops, runs)
    assert preview["ok"] is True
    result = apply_repo_patch(repo, ops, preview["patch_id"], runs)
    assert result["ok"] is True
    assert (repo / "apply.py").read_text(encoding="utf-8") == "x = 99\n"
    assert result["changed_files"] == ["apply.py"]


def test_apply_returns_sha256_of_result(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    runs = tmp_path / "runs"
    write_file(repo / "f.py", "v = 1\n")
    sha = sha256_file(repo / "f.py")
    ops = [
        {
            "path": "f.py",
            "expected_sha256": sha,
            "old_text": "v = 1",
            "new_text": "v = 7",
        }
    ]
    preview = preview_repo_patch(repo, ops, runs)
    result = apply_repo_patch(repo, ops, preview["patch_id"], runs)
    assert result["results"][0]["sha256"] == sha256_file(repo / "f.py")


def test_apply_rejects_unknown_patch_id(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    runs = tmp_path / "runs"
    write_file(repo / "g.py", "g = 1\n")
    sha = sha256_file(repo / "g.py")
    ops = [
        {
            "path": "g.py",
            "expected_sha256": sha,
            "old_text": "g = 1",
            "new_text": "g = 2",
        }
    ]
    with pytest.raises(ValueError, match="Unknown patch_id"):
        apply_repo_patch(repo, ops, "20260624T000000Z_patch_deadbeef", runs)


def test_apply_rejects_stale_file_between_preview_and_apply(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    runs = tmp_path / "runs"
    write_file(repo / "h.py", "h = 1\n")
    sha = sha256_file(repo / "h.py")
    ops = [
        {
            "path": "h.py",
            "expected_sha256": sha,
            "old_text": "h = 1",
            "new_text": "h = 2",
        }
    ]
    preview = preview_repo_patch(repo, ops, runs)
    # Mutate file between preview and apply
    (repo / "h.py").write_text("h = 999\n", encoding="utf-8")
    with pytest.raises(Exception, match="[Hh]ash"):
        apply_repo_patch(repo, ops, preview["patch_id"], runs)


def test_apply_rejects_already_applied(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    runs = tmp_path / "runs"
    write_file(repo / "i.py", "i = 1\n")
    sha = sha256_file(repo / "i.py")
    ops = [
        {
            "path": "i.py",
            "expected_sha256": sha,
            "old_text": "i = 1",
            "new_text": "i = 2",
        }
    ]
    preview = preview_repo_patch(repo, ops, runs)
    apply_repo_patch(repo, ops, preview["patch_id"], runs)
    with pytest.raises(ValueError, match="already been applied"):
        apply_repo_patch(repo, ops, preview["patch_id"], runs)


# ---------------------------------------------------------------------------
# Atomic multi-file rollback after partial failure
# ---------------------------------------------------------------------------


def test_apply_rolls_back_on_partial_failure(tmp_path: Path, monkeypatch) -> None:
    repo = make_repo(tmp_path)
    runs = tmp_path / "runs"
    write_file(repo / "r1.py", "r = 1\n")
    write_file(repo / "r2.py", "s = 1\n")
    sha1 = sha256_file(repo / "r1.py")
    sha2 = sha256_file(repo / "r2.py")
    ops = [
        {
            "path": "r1.py",
            "expected_sha256": sha1,
            "old_text": "r = 1",
            "new_text": "r = 9",
        },
        {
            "path": "r2.py",
            "expected_sha256": sha2,
            "old_text": "s = 1",
            "new_text": "s = 9",
        },
    ]
    preview = preview_repo_patch(repo, ops, runs)

    original_replace = os.replace
    call_count = {"n": 0}

    def fail_on_second(src, dst):
        call_count["n"] += 1
        if call_count["n"] == 2:
            raise OSError("simulated disk failure")
        return original_replace(src, dst)

    monkeypatch.setattr(rw.os, "replace", fail_on_second)
    with pytest.raises(RuntimeError, match="partial rollback"):
        apply_repo_patch(repo, ops, preview["patch_id"], runs)

    # r1.py should be rolled back to original
    assert (repo / "r1.py").read_text(encoding="utf-8") == "r = 1\n"


# ---------------------------------------------------------------------------
# revert_managed_patch
# ---------------------------------------------------------------------------


def test_revert_restores_original(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    runs = tmp_path / "runs"
    write_file(repo / "rev.py", "v = 1\n")
    sha = sha256_file(repo / "rev.py")
    ops = [
        {
            "path": "rev.py",
            "expected_sha256": sha,
            "old_text": "v = 1",
            "new_text": "v = 2",
        }
    ]
    preview = preview_repo_patch(repo, ops, runs)
    apply_repo_patch(repo, ops, preview["patch_id"], runs)
    assert (repo / "rev.py").read_text(encoding="utf-8") == "v = 2\n"
    result = revert_managed_patch(repo, preview["patch_id"], runs)
    assert result["ok"] is True
    assert (repo / "rev.py").read_text(encoding="utf-8") == "v = 1\n"


def test_revert_rejects_non_applied_patch(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    runs = tmp_path / "runs"
    write_file(repo / "nop.py", "n = 1\n")
    sha = sha256_file(repo / "nop.py")
    ops = [
        {
            "path": "nop.py",
            "expected_sha256": sha,
            "old_text": "n = 1",
            "new_text": "n = 2",
        }
    ]
    preview = preview_repo_patch(repo, ops, runs)
    with pytest.raises(ValueError, match="not in 'applied'"):
        revert_managed_patch(repo, preview["patch_id"], runs)


def test_revert_rejects_modified_file(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    runs = tmp_path / "runs"
    write_file(repo / "mod.py", "m = 1\n")
    sha = sha256_file(repo / "mod.py")
    ops = [
        {
            "path": "mod.py",
            "expected_sha256": sha,
            "old_text": "m = 1",
            "new_text": "m = 2",
        }
    ]
    preview = preview_repo_patch(repo, ops, runs)
    apply_repo_patch(repo, ops, preview["patch_id"], runs)
    (repo / "mod.py").write_text("m = 999\n", encoding="utf-8")
    with pytest.raises(ValueError, match="modified"):
        revert_managed_patch(repo, preview["patch_id"], runs)


# ---------------------------------------------------------------------------
# create_repo_file
# ---------------------------------------------------------------------------


def test_create_repo_file_succeeds(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    result = create_repo_file(repo, "new.py", "x = 1\n")
    assert result["ok"] is True
    assert (repo / "new.py").exists()
    assert result["sha256"] == sha256_file(repo / "new.py")


def test_create_repo_file_rejects_existing(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    write_file(repo / "exists.py", "x\n")
    with pytest.raises(ValueError, match="already exists"):
        create_repo_file(repo, "exists.py", "y\n")


def test_create_repo_file_creates_parent_dirs(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    result = create_repo_file(repo, "subdir/deep/new.py", "pass\n")
    assert result["ok"] is True
    assert (repo / "subdir" / "deep" / "new.py").exists()


def test_create_repo_file_rejects_absolute(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    with pytest.raises(ValueError):
        create_repo_file(repo, str(tmp_path / "escape.py"), "x\n")


def test_create_repo_file_rejects_traversal(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    with pytest.raises(ValueError):
        create_repo_file(repo, "../outside.py", "x\n")


def test_create_repo_file_rejects_blocked_extension(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    with pytest.raises(ValueError):
        create_repo_file(repo, "cert.pem", "data\n")


def test_create_repo_file_rejects_oversized(tmp_path: Path, monkeypatch) -> None:
    repo = make_repo(tmp_path)
    monkeypatch.setattr(rw, "MAX_CREATE_BYTES", 5)
    with pytest.raises(ValueError, match="limit"):
        create_repo_file(repo, "big.py", "x" * 10)


# ---------------------------------------------------------------------------
# delete_repo_file
# ---------------------------------------------------------------------------


def test_delete_repo_file_succeeds(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    runs = tmp_path / "runs"
    write_file(repo / "del.py", "to delete\n")
    sha = sha256_file(repo / "del.py")
    result = delete_repo_file(repo, "del.py", sha, runs)
    assert result["ok"] is True
    assert not (repo / "del.py").exists()


def test_delete_repo_file_rejects_stale_hash(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    runs = tmp_path / "runs"
    write_file(repo / "stale.py", "content\n")
    with pytest.raises(ValueError, match="[Ss]tale"):
        delete_repo_file(repo, "stale.py", "a" * 64, runs)


def test_delete_repo_file_saves_rollback(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    runs = tmp_path / "runs"
    write_file(repo / "roll.py", "rollback me\n")
    sha = sha256_file(repo / "roll.py")
    result = delete_repo_file(repo, "roll.py", sha, runs)
    rollback_id = result["rollback_id"]
    rb_dir = runs / "managed_patches" / rollback_id
    assert (rb_dir / "original_content.txt").exists()


# ---------------------------------------------------------------------------
# move_repo_file
# ---------------------------------------------------------------------------


def test_move_repo_file_succeeds(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    runs = tmp_path / "runs"
    write_file(repo / "src.py", "source\n")
    sha = sha256_file(repo / "src.py")
    result = move_repo_file(repo, "src.py", "dst.py", sha, runs)
    assert result["ok"] is True
    assert not (repo / "src.py").exists()
    assert (repo / "dst.py").exists()


def test_move_repo_file_rejects_stale_hash(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    runs = tmp_path / "runs"
    write_file(repo / "mv_src.py", "data\n")
    with pytest.raises(ValueError, match="[Ss]tale"):
        move_repo_file(repo, "mv_src.py", "mv_dst.py", "a" * 64, runs)


def test_move_repo_file_rejects_existing_destination(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    runs = tmp_path / "runs"
    write_file(repo / "a.py", "a\n")
    write_file(repo / "b.py", "b\n")
    sha = sha256_file(repo / "a.py")
    with pytest.raises(ValueError, match="already exists"):
        move_repo_file(repo, "a.py", "b.py", sha, runs)


def test_move_repo_file_rejects_traversal_destination(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    runs = tmp_path / "runs"
    write_file(repo / "c.py", "c\n")
    sha = sha256_file(repo / "c.py")
    with pytest.raises(ValueError):
        move_repo_file(repo, "c.py", "../escape.py", sha, runs)


# ---------------------------------------------------------------------------
# Symlink and junction escape
# ---------------------------------------------------------------------------


def test_preview_rejects_symlink_file(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    runs = tmp_path / "runs"
    outside = tmp_path.parent / "outside_w.py"
    outside.write_text("secret\n", encoding="utf-8")
    link = repo / "link.py"
    try:
        link.symlink_to(outside)
    except OSError:
        pytest.skip("Symlinks unavailable")
    sha = sha256_file(outside)
    ops = [
        {
            "path": "link.py",
            "expected_sha256": sha,
            "old_text": "secret",
            "new_text": "changed",
        }
    ]
    result = preview_repo_patch(repo, ops, runs)
    assert result["ok"] is False


# ---------------------------------------------------------------------------
# Sensitive file rejection
# ---------------------------------------------------------------------------


def test_preview_rejects_env_file(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    runs = tmp_path / "runs"
    write_file(repo / ".env", "SECRET=abc\n")
    ops = [
        {
            "path": ".env",
            "expected_sha256": "x" * 64,
            "old_text": "abc",
            "new_text": "xyz",
        }
    ]
    result = preview_repo_patch(repo, ops, runs)
    assert result["ok"] is False


def test_create_rejects_credentials_subdir(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    with pytest.raises(ValueError):
        create_repo_file(repo, "credentials/prod.json", "{}\n")


def test_create_rejects_desktop_ini(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    with pytest.raises(ValueError):
        create_repo_file(repo, "desktop.ini", "[.]")


# ---------------------------------------------------------------------------
# No absolute path leakage
# ---------------------------------------------------------------------------


def test_preview_result_no_absolute_path(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    runs = tmp_path / "runs"
    write_file(repo / "leak.py", "z = 1\n")
    sha = sha256_file(repo / "leak.py")
    ops = [
        {
            "path": "leak.py",
            "expected_sha256": sha,
            "old_text": "z = 1",
            "new_text": "z = 2",
        }
    ]
    result = preview_repo_patch(repo, ops, runs)
    result_str = json.dumps(result)
    assert str(tmp_path) not in result_str


def test_apply_result_no_absolute_path(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    runs = tmp_path / "runs"
    write_file(repo / "no_leak.py", "w = 1\n")
    sha = sha256_file(repo / "no_leak.py")
    ops = [
        {
            "path": "no_leak.py",
            "expected_sha256": sha,
            "old_text": "w = 1",
            "new_text": "w = 2",
        }
    ]
    preview = preview_repo_patch(repo, ops, runs)
    result = apply_repo_patch(repo, ops, preview["patch_id"], runs)
    result_str = json.dumps(result)
    assert str(tmp_path) not in result_str


# ---------------------------------------------------------------------------
# No CodexRunner or local model invocation
# ---------------------------------------------------------------------------


def test_repo_writer_does_not_import_codex_runner(tmp_path: Path) -> None:
    import ast, codexbridge.repo_writer as rw_mod

    source = Path(rw_mod.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    imports: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            imports.append(node.module or "")
            imports.extend(a.name for a in node.names)
    for name in imports:
        assert "runner" not in name.lower() or "repo_writer" in name.lower(), (
            f"Unexpected runner import: {name}"
        )
        assert "ollama" not in name.lower(), f"ollama import: {name}"
        assert "gemini" not in name.lower(), f"gemini import: {name}"


# ---------------------------------------------------------------------------
# Server-level integration: preview_repo_patch and apply_repo_patch via server
# ---------------------------------------------------------------------------


def test_server_preview_and_apply(tmp_path: Path) -> None:
    import codexbridge.server as server
    from codexbridge.config import AppConfig, RepoConfig

    (tmp_path / ".git").mkdir()
    write_file(tmp_path / "target.py", "x = 0\n")
    sha = sha256_file(tmp_path / "target.py")
    config = AppConfig(
        repos={"repo": RepoConfig(path=str(tmp_path))},
        config_dir=tmp_path,
        runs_dir=str(tmp_path / "runs"),
    )
    server.set_config(config, tmp_path / "config.yaml")

    ops = [
        {
            "path": "target.py",
            "expected_sha256": sha,
            "old_text": "x = 0",
            "new_text": "x = 1",
        }
    ]
    preview = server.preview_repo_patch("repo", ops)
    assert preview["ok"] is True
    assert preview["patch_id"]

    result = server.apply_repo_patch("repo", ops, preview["patch_id"])
    assert result["ok"] is True
    assert (tmp_path / "target.py").read_text(encoding="utf-8") == "x = 1\n"


def test_server_create_and_delete_file(tmp_path: Path) -> None:
    import codexbridge.server as server
    from codexbridge.config import AppConfig, RepoConfig

    (tmp_path / ".git").mkdir()
    config = AppConfig(
        repos={"repo": RepoConfig(path=str(tmp_path))},
        config_dir=tmp_path,
        runs_dir=str(tmp_path / "runs"),
    )
    server.set_config(config, tmp_path / "config.yaml")

    create_result = server.create_repo_file("repo", "brand_new.py", "pass\n")
    assert create_result["ok"] is True
    assert (tmp_path / "brand_new.py").exists()

    del_result = server.delete_repo_file(
        "repo", "brand_new.py", create_result["sha256"]
    )
    assert del_result["ok"] is True
    assert not (tmp_path / "brand_new.py").exists()


def test_server_move_file(tmp_path: Path) -> None:
    import codexbridge.server as server
    from codexbridge.config import AppConfig, RepoConfig

    (tmp_path / ".git").mkdir()
    write_file(tmp_path / "old_name.py", "content\n")
    sha = sha256_file(tmp_path / "old_name.py")
    config = AppConfig(
        repos={"repo": RepoConfig(path=str(tmp_path))},
        config_dir=tmp_path,
        runs_dir=str(tmp_path / "runs"),
    )
    server.set_config(config, tmp_path / "config.yaml")

    result = server.move_repo_file("repo", "old_name.py", "new_name.py", sha)
    assert result["ok"] is True
    assert (tmp_path / "new_name.py").exists()
    assert not (tmp_path / "old_name.py").exists()
