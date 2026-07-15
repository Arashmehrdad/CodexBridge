"""
Tests for codexbridge/repo_writer.py and related server tools.
No CodexRunner, Gemini, Ollama, or local-model calls are made.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from pathlib import Path

import pytest

from codexbridge import repo_writer as rw
from codexbridge.repo_writer import (
    preview_repo_patch,
    preview_repo_file_creation,
    preview_repo_file_removal,
    apply_repo_patch,
    apply_previewed_repo_change,
    revert_managed_patch,
    create_repo_file,
    delete_repo_file,
    move_repo_file,
    _sha256_file,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_repo(tmp_path: Path) -> Path:
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / ".git").mkdir()
    return tmp_path


def write_file(path: Path, content: str = "hello\n") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def sha256_of(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return _sha256_file(path)


def init_git_repo(path: Path) -> None:
    subprocess.run(["git", "init"], cwd=path, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "tests@example.com"],
        cwd=path,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "CodexBridge Tests"],
        cwd=path,
        check=True,
        capture_output=True,
    )


def commit_all(path: Path, message: str) -> None:
    subprocess.run(["git", "add", "."], cwd=path, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", message],
        cwd=path,
        check=True,
        capture_output=True,
    )


def test_atomic_write_bytes_cleans_up_temp_file_on_replace_failure(
    tmp_path: Path, monkeypatch
) -> None:
    target = tmp_path / "atomic.txt"

    def fail_replace(src, dst):
        raise OSError("replace failed")

    monkeypatch.setattr(rw.os, "replace", fail_replace)

    with pytest.raises(OSError, match="replace failed"):
        rw._atomic_write_bytes(target, b"payload", ".codexbridge_test_tmp")

    assert not target.exists()
    assert list(tmp_path.glob("*.codexbridge_test_tmp")) == []


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


def test_preview_stores_opaque_modify_payload_and_repo_fingerprint(
    tmp_path: Path,
) -> None:
    repo = make_repo(tmp_path)
    runs = tmp_path / "runs"
    write_file(repo / "script.py", "print('hello')\n")
    sha = sha256_file(repo / "script.py")
    ops = [
        {
            "path": "script.py",
            "expected_sha256": sha,
            "old_text": "print('hello')",
            "new_text": "print('updated')",
        }
    ]

    result = preview_repo_patch(repo, ops, runs)
    patch_dir = runs / "managed_patches" / result["patch_id"]
    manifest = json.loads((patch_dir / "manifest.json").read_text(encoding="utf-8"))
    payload_bytes = (patch_dir / "payload_0.bin").read_bytes()

    assert manifest["repo_root"] == ""
    assert manifest["repo_fingerprint"]
    assert manifest["operations"][0]["payload_file"] == "payload_0.bin"
    assert manifest["operations"][0]["payload_sha256"] == sha256_bytes(payload_bytes)
    assert payload_bytes.decode("utf-8").replace("\r\n", "\n") == "print('updated')\n"


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


def test_preview_and_apply_preserve_mixed_newline_bytes(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    runs = tmp_path / "runs"
    original = (
        b"header\r\n"
        b"def target():\n"
        b"    return 1\n"
        b"footer\r\n"
    )
    target = repo / "mixed.py"
    target.write_bytes(original)
    sha = sha256_file(target)
    operations = [
        {
            "type": "exact_text",
            "path": "mixed.py",
            "expected_sha256": sha,
            "old_text": "def target():\n    return 1\n",
            "new_text": "def target():\n    return 2\n",
        }
    ]

    preview = preview_repo_patch(repo, operations, runs)

    assert preview["ok"] is True
    assert preview["changed_files"] == ["mixed.py"]
    applied = apply_previewed_repo_change(repo, preview["patch_id"], runs)
    assert applied["ok"] is True
    assert target.read_bytes() == original.replace(b"return 1", b"return 2")


def test_preview_rejects_mixed_newline_edit_modes(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    runs = tmp_path / "runs"
    target = repo / "mixed_modes.py"
    target.write_bytes(b"alpha\r\nbeta\ngamma\r\n")
    sha = sha256_file(target)

    preview = preview_repo_patch(
        repo,
        [
            {
                "type": "exact_text",
                "path": "mixed_modes.py",
                "expected_sha256": sha,
                "old_text": "alpha\n",
                "new_text": "ALPHA\n",
                "preserve_newlines": True,
            },
            {
                "type": "exact_text",
                "path": "mixed_modes.py",
                "expected_sha256": sha,
                "old_text": "beta",
                "new_text": "BETA",
                "preserve_newlines": False,
            },
        ],
        runs,
    )

    assert preview["ok"] is False
    assert any("cannot mix preserve_newlines" in error for error in preview["validation_errors"])


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


def test_apply_replays_original_success_when_already_applied(tmp_path: Path) -> None:
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
    first = apply_repo_patch(repo, ops, preview["patch_id"], runs)
    replay = apply_repo_patch(repo, ops, preview["patch_id"], runs)
    assert first["ok"] is True
    assert first["idempotent_replay"] is False
    assert replay["ok"] is True
    assert replay["idempotent_replay"] is True
    assert replay["patch_id"] == first["patch_id"]


def test_apply_previewed_repo_change_applies_modify_without_operations(
    tmp_path: Path,
) -> None:
    repo = make_repo(tmp_path)
    runs = tmp_path / "runs"
    write_file(repo / "opaque.py", "print('before')\n")
    sha = sha256_file(repo / "opaque.py")
    preview = preview_repo_patch(
        repo,
        [
            {
                "path": "opaque.py",
                "expected_sha256": sha,
                "old_text": "print('before')",
                "new_text": "print('after')",
            }
        ],
        runs,
    )

    result = apply_previewed_repo_change(repo, preview["patch_id"], runs)

    assert result["ok"] is True
    assert (repo / "opaque.py").read_text(encoding="utf-8") == "print('after')\n"
    assert result["changed_files"] == ["opaque.py"]


def test_apply_previewed_repo_change_rejects_invalid_patch_id(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    runs = tmp_path / "runs"
    with pytest.raises(ValueError, match="Invalid patch_id"):
        apply_previewed_repo_change(repo, "../escape", runs)


def test_apply_previewed_repo_change_rejects_missing_payload(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    runs = tmp_path / "runs"
    write_file(repo / "missing.py", "x = 1\n")
    sha = sha256_file(repo / "missing.py")
    preview = preview_repo_patch(
        repo,
        [
            {
                "path": "missing.py",
                "expected_sha256": sha,
                "old_text": "x = 1",
                "new_text": "x = 2",
            }
        ],
        runs,
    )
    patch_dir = runs / "managed_patches" / preview["patch_id"]
    (patch_dir / "payload_0.bin").unlink()

    with pytest.raises(ValueError, match="missing the opaque payload"):
        apply_previewed_repo_change(repo, preview["patch_id"], runs)


def test_apply_previewed_repo_change_rejects_tampered_payload(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    runs = tmp_path / "runs"
    write_file(repo / "tamper.py", "x = 1\n")
    sha = sha256_file(repo / "tamper.py")
    preview = preview_repo_patch(
        repo,
        [
            {
                "path": "tamper.py",
                "expected_sha256": sha,
                "old_text": "x = 1",
                "new_text": "x = 2",
            }
        ],
        runs,
    )
    patch_dir = runs / "managed_patches" / preview["patch_id"]
    (patch_dir / "payload_0.bin").write_text("x = 999\n", encoding="utf-8")

    with pytest.raises(ValueError, match="payload verification failed"):
        apply_previewed_repo_change(repo, preview["patch_id"], runs)


def test_apply_previewed_repo_change_rejects_payload_filename_traversal(
    tmp_path: Path,
) -> None:
    repo = make_repo(tmp_path)
    runs = tmp_path / "runs"
    write_file(repo / "traversal.py", "x = 1\n")
    sha = sha256_file(repo / "traversal.py")
    preview = preview_repo_patch(
        repo,
        [
            {
                "path": "traversal.py",
                "expected_sha256": sha,
                "old_text": "x = 1",
                "new_text": "x = 2",
            }
        ],
        runs,
    )
    patch_dir = runs / "managed_patches" / preview["patch_id"]
    manifest_path = patch_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["operations"][0]["payload_file"] = "../payload_0.bin"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    with pytest.raises(ValueError, match="Payload filename mismatch"):
        apply_previewed_repo_change(repo, preview["patch_id"], runs)


def test_apply_previewed_repo_change_rejects_payload_symlink(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    runs = tmp_path / "runs"
    write_file(repo / "symlink_payload.py", "x = 1\n")
    sha = sha256_file(repo / "symlink_payload.py")
    preview = preview_repo_patch(
        repo,
        [
            {
                "path": "symlink_payload.py",
                "expected_sha256": sha,
                "old_text": "x = 1",
                "new_text": "x = 2",
            }
        ],
        runs,
    )
    patch_dir = runs / "managed_patches" / preview["patch_id"]
    payload_path = patch_dir / "payload_0.bin"
    replacement = tmp_path / "external_payload.bin"
    replacement.write_bytes(b"x = 2\n")
    try:
        payload_path.unlink()
    except PermissionError:
        pytest.skip("Symlink replacement unavailable")
    try:
        payload_path.symlink_to(replacement)
    except OSError:
        pytest.skip("Symlinks unavailable")

    with pytest.raises(ValueError, match="must not be a symlink"):
        apply_previewed_repo_change(repo, preview["patch_id"], runs)


def test_apply_previewed_repo_change_preserves_exact_payload_bytes(
    tmp_path: Path,
) -> None:
    repo = make_repo(tmp_path)
    runs = tmp_path / "runs"
    preview = preview_repo_file_creation(repo, "exact.py", "line1\nline2\n", runs)
    patch_dir = runs / "managed_patches" / preview["patch_id"]
    manifest_path = patch_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    payload_bytes = b"line1\r\nline2\r\n"
    (patch_dir / "payload_0.bin").write_bytes(payload_bytes)
    manifest["operations"][0]["payload_sha256"] = sha256_bytes(payload_bytes)
    manifest["operations"][0]["payload_size_bytes"] = len(payload_bytes)
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    result = apply_previewed_repo_change(repo, preview["patch_id"], runs)

    assert result["ok"] is True
    assert (repo / "exact.py").read_bytes() == payload_bytes
    assert (repo / "exact.py").read_text(encoding="utf-8") == "line1\nline2\n"


def test_apply_previewed_repo_change_rejects_repo_fingerprint_mismatch(
    tmp_path: Path,
) -> None:
    repo = make_repo(tmp_path / "repo_a")
    other_repo = make_repo(tmp_path / "repo_b")
    runs = tmp_path / "runs"
    write_file(repo / "cross.py", "x = 1\n")
    sha = sha256_file(repo / "cross.py")
    preview = preview_repo_patch(
        repo,
        [
            {
                "path": "cross.py",
                "expected_sha256": sha,
                "old_text": "x = 1",
                "new_text": "x = 2",
            }
        ],
        runs,
    )

    with pytest.raises(ValueError, match="does not belong to the requested repository"):
        apply_previewed_repo_change(other_repo, preview["patch_id"], runs)


def test_apply_previewed_repo_change_rejects_stale_file_state(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    runs = tmp_path / "runs"
    write_file(repo / "stale_apply.py", "x = 1\n")
    sha = sha256_file(repo / "stale_apply.py")
    preview = preview_repo_patch(
        repo,
        [
            {
                "path": "stale_apply.py",
                "expected_sha256": sha,
                "old_text": "x = 1",
                "new_text": "x = 2",
            }
        ],
        runs,
    )
    write_file(repo / "stale_apply.py", "x = 777\n")

    with pytest.raises(ValueError, match="changed since preview"):
        apply_previewed_repo_change(repo, preview["patch_id"], runs)


def test_apply_previewed_repo_change_rejects_legacy_preview_without_bundle(
    tmp_path: Path,
) -> None:
    repo = make_repo(tmp_path)
    runs = tmp_path / "runs"
    patch_id = "20260624T120000Z_patch_abcd1234"
    patch_dir = runs / "managed_patches" / patch_id
    patch_dir.mkdir(parents=True)
    (patch_dir / "manifest.json").write_text(
        json.dumps(
            {
                "patch_id": patch_id,
                "status": "preview_ok",
                "operations": [{"path": "legacy.py"}],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="opaque preview bundle"):
        apply_previewed_repo_change(repo, patch_id, runs)


def test_apply_previewed_repo_change_rejects_too_many_manifest_operations(
    tmp_path: Path,
) -> None:
    repo = make_repo(tmp_path)
    runs = tmp_path / "runs"
    preview = preview_repo_file_creation(repo, "overflow.py", "value = 1\n", runs)
    patch_dir = runs / "managed_patches" / preview["patch_id"]
    manifest_path = patch_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["operations"] = manifest["operations"] * (rw.MAX_PATCH_FILES + 1)
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    with pytest.raises(ValueError, match="file limit"):
        apply_previewed_repo_change(repo, preview["patch_id"], runs)


def test_apply_previewed_repo_change_rejects_duplicate_manifest_paths(
    tmp_path: Path,
) -> None:
    repo = make_repo(tmp_path)
    runs = tmp_path / "runs"
    preview = preview_repo_file_creation(repo, "dup.py", "value = 1\n", runs)
    patch_dir = runs / "managed_patches" / preview["patch_id"]
    manifest_path = patch_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["operations"].append(dict(manifest["operations"][0]))
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    with pytest.raises(ValueError, match="duplicate paths"):
        apply_previewed_repo_change(repo, preview["patch_id"], runs)


def test_apply_previewed_repo_change_rejects_changed_git_head_for_modify(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    init_git_repo(repo)
    write_file(repo / "head.py", "value = 1\n")
    commit_all(repo, "initial")
    runs = tmp_path / "runs"
    sha = sha256_file(repo / "head.py")
    preview = preview_repo_patch(
        repo,
        [
            {
                "path": "head.py",
                "expected_sha256": sha,
                "old_text": "value = 1",
                "new_text": "value = 2",
            }
        ],
        runs,
    )
    write_file(repo / "other.txt", "touch\n")
    commit_all(repo, "advance head")

    with pytest.raises(ValueError, match="Git HEAD has changed since preview"):
        apply_previewed_repo_change(repo, preview["patch_id"], runs)


def test_preview_and_apply_creation_then_revert(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    runs = tmp_path / "runs"

    preview = preview_repo_file_creation(
        repo, "pkg/generated.py", "print('generated')\n", runs
    )
    assert preview["ok"] is True

    applied = apply_previewed_repo_change(repo, preview["patch_id"], runs)
    assert applied["ok"] is True
    assert (repo / "pkg" / "generated.py").read_text(encoding="utf-8") == (
        "print('generated')\n"
    )

    reverted = revert_managed_patch(repo, preview["patch_id"], runs)
    assert reverted["ok"] is True
    assert not (repo / "pkg" / "generated.py").exists()


def test_preview_and_apply_removal_then_revert(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    runs = tmp_path / "runs"
    write_file(repo / "old.py", "print('old')\n")
    sha = sha256_file(repo / "old.py")

    preview = preview_repo_file_removal(repo, "old.py", sha, runs)
    assert preview["ok"] is True

    applied = apply_previewed_repo_change(repo, preview["patch_id"], runs)
    assert applied["ok"] is True
    assert not (repo / "old.py").exists()

    reverted = revert_managed_patch(repo, preview["patch_id"], runs)
    assert reverted["ok"] is True
    assert (repo / "old.py").read_text(encoding="utf-8") == "print('old')\n"


def test_preview_file_removal_rejects_stale_hash(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    runs = tmp_path / "runs"
    write_file(repo / "stale_remove.py", "data\n")

    result = preview_repo_file_removal(repo, "stale_remove.py", "a" * 64, runs)

    assert result["ok"] is False
    assert result["validation_errors"]


def test_preview_two_line_removal_counts_two_changed_lines(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    runs = tmp_path / "runs"
    write_file(repo / "two_line_remove.py", "alpha\nbeta\n")
    sha = sha256_file(repo / "two_line_remove.py")

    preview = preview_repo_file_removal(repo, "two_line_remove.py", sha, runs)

    assert preview["ok"] is True
    assert preview["changed_lines"] == 2


def test_apply_previewed_repo_change_recomputes_remove_changed_lines(
    tmp_path: Path, monkeypatch
) -> None:
    repo = make_repo(tmp_path)
    runs = tmp_path / "runs"
    write_file(repo / "tampered_remove.py", "alpha\nbeta\n")
    sha = sha256_file(repo / "tampered_remove.py")
    preview = preview_repo_file_removal(repo, "tampered_remove.py", sha, runs)
    patch_dir = runs / "managed_patches" / preview["patch_id"]
    manifest_path = patch_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["operations"][0]["changed_lines"] = 0
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    monkeypatch.setattr(rw, "MAX_PATCH_LINES", 1)

    with pytest.raises(ValueError, match="changed-line limit"):
        apply_previewed_repo_change(repo, preview["patch_id"], runs)


def test_apply_repo_patch_accepts_legacy_new_content_sha256_preview(
    tmp_path: Path,
) -> None:
    repo = make_repo(tmp_path)
    runs = tmp_path / "runs"
    write_file(repo / "legacy_hash.py", "value = 1\n")
    sha = sha256_file(repo / "legacy_hash.py")
    ops = [
        {
            "path": "legacy_hash.py",
            "expected_sha256": sha,
            "old_text": "value = 1",
            "new_text": "value = 2",
        }
    ]

    preview = preview_repo_patch(repo, ops, runs)
    manifest_path = runs / "managed_patches" / preview["patch_id"] / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    legacy_sha = manifest["operations"][0].pop("payload_sha256")
    manifest["operations"][0]["new_content_sha256"] = legacy_sha
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    result = apply_repo_patch(repo, ops, preview["patch_id"], runs)

    assert result["ok"] is True
    assert (repo / "legacy_hash.py").read_text(encoding="utf-8") == "value = 2\n"


def test_revert_created_file_rejects_if_current_hash_changed(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    runs = tmp_path / "runs"
    preview = preview_repo_file_creation(repo, "newer.py", "x = 1\n", runs)
    apply_previewed_repo_change(repo, preview["patch_id"], runs)
    write_file(repo / "newer.py", "x = 99\n")

    with pytest.raises(ValueError, match="modified since the patch was applied"):
        revert_managed_patch(repo, preview["patch_id"], runs)


def test_revert_removed_file_rejects_if_path_recreated(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    runs = tmp_path / "runs"
    write_file(repo / "gone.py", "gone\n")
    sha = sha256_file(repo / "gone.py")
    preview = preview_repo_file_removal(repo, "gone.py", sha, runs)
    apply_previewed_repo_change(repo, preview["patch_id"], runs)
    write_file(repo / "gone.py", "replacement\n")

    with pytest.raises(ValueError, match="now exists on disk"):
        revert_managed_patch(repo, preview["patch_id"], runs)


def test_apply_previewed_repo_change_rejects_already_reverted_patch(
    tmp_path: Path,
) -> None:
    repo = make_repo(tmp_path)
    runs = tmp_path / "runs"
    preview = preview_repo_file_creation(repo, "done.py", "x = 1\n", runs)
    apply_previewed_repo_change(repo, preview["patch_id"], runs)
    revert_managed_patch(repo, preview["patch_id"], runs)

    with pytest.raises(ValueError, match="has been reverted"):
        apply_previewed_repo_change(repo, preview["patch_id"], runs)


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


def test_apply_previewed_repo_change_rolls_back_if_manifest_write_fails(
    tmp_path: Path, monkeypatch
) -> None:
    repo = make_repo(tmp_path)
    runs = tmp_path / "runs"
    write_file(repo / "modify.py", "before\n")
    write_file(repo / "remove.py", "delete me\n")
    preview = preview_repo_patch(
        repo,
        [
            {
                "path": "modify.py",
                "expected_sha256": sha256_file(repo / "modify.py"),
                "old_text": "before",
                "new_text": "after",
            }
        ],
        runs,
    )
    create_preview = preview_repo_file_creation(repo, "create.py", "created\n", runs)
    remove_preview = preview_repo_file_removal(
        repo, "remove.py", sha256_file(repo / "remove.py"), runs
    )
    patch_dir = runs / "managed_patches" / preview["patch_id"]
    create_patch_dir = runs / "managed_patches" / create_preview["patch_id"]
    remove_patch_dir = runs / "managed_patches" / remove_preview["patch_id"]

    manifest_path = patch_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    create_manifest = json.loads(
        (create_patch_dir / "manifest.json").read_text(encoding="utf-8")
    )
    remove_manifest = json.loads(
        (remove_patch_dir / "manifest.json").read_text(encoding="utf-8")
    )
    create_op = dict(create_manifest["operations"][0])
    create_op["payload_file"] = "payload_1.bin"
    manifest["operations"].extend([create_op, remove_manifest["operations"][0]])
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    (patch_dir / "payload_1.bin").write_bytes(
        (create_patch_dir / "payload_0.bin").read_bytes()
    )

    original_atomic_write_text = rw._atomic_write_text

    def fail_manifest_write(path: Path, text: str, suffix: str) -> None:
        if path.name == "manifest.json":
            raise OSError("manifest update failed")
        original_atomic_write_text(path, text, suffix)

    monkeypatch.setattr(rw, "_atomic_write_text", fail_manifest_write)

    with pytest.raises(RuntimeError, match="before writes"):
        apply_previewed_repo_change(repo, preview["patch_id"], runs)

    assert (repo / "modify.py").read_text(encoding="utf-8") == "before\n"
    assert not (repo / "create.py").exists()
    assert (repo / "remove.py").read_text(encoding="utf-8") == "delete me\n"
    final_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert final_manifest["status"] == "preview_ok"


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
    assert result["changed_files"] == ["rev.py"]
    assert (repo / "rev.py").read_text(encoding="utf-8") == "v = 1\n"


def test_apply_repo_patch_preserves_legacy_response_shape_and_supports_revert(
    tmp_path: Path,
) -> None:
    repo = make_repo(tmp_path)
    runs = tmp_path / "runs"
    write_file(repo / "legacy.py", "value = 1\n")
    sha = sha256_file(repo / "legacy.py")
    ops = [
        {
            "path": "legacy.py",
            "expected_sha256": sha,
            "old_text": "value = 1",
            "new_text": "value = 2",
        }
    ]

    preview = preview_repo_patch(repo, ops, runs)
    applied = apply_repo_patch(repo, ops, preview["patch_id"], runs)
    manifest = json.loads(
        (runs / "managed_patches" / preview["patch_id"] / "manifest.json").read_text(
            encoding="utf-8"
        )
    )

    assert set(applied["results"][0]) == {"path", "sha256"}
    assert manifest["applied_results"][0]["action"] == "modify"
    assert manifest["applied_results"][0]["rollback_file"] == "legacy.py"

    reverted = revert_managed_patch(repo, preview["patch_id"], runs)

    assert reverted["ok"] is True
    assert (repo / "legacy.py").read_text(encoding="utf-8") == "value = 1\n"


def test_revert_managed_patch_supports_legacy_manifest_without_rollback_metadata(
    tmp_path: Path,
) -> None:
    repo = make_repo(tmp_path)
    runs = tmp_path / "runs"
    write_file(repo / "legacy_fallback.py", "value = 1\n")
    sha = sha256_file(repo / "legacy_fallback.py")
    ops = [
        {
            "path": "legacy_fallback.py",
            "expected_sha256": sha,
            "old_text": "value = 1",
            "new_text": "value = 2",
        }
    ]

    preview = preview_repo_patch(repo, ops, runs)
    apply_repo_patch(repo, ops, preview["patch_id"], runs)
    manifest_path = runs / "managed_patches" / preview["patch_id"] / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["applied_results"] = [
        {"path": item["path"], "sha256": item["sha256"]}
        for item in manifest["applied_results"]
    ]
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    reverted = revert_managed_patch(repo, preview["patch_id"], runs)

    assert reverted["ok"] is True
    assert (repo / "legacy_fallback.py").read_text(encoding="utf-8") == "value = 1\n"


def test_revert_managed_patch_rejects_tampered_rollback_filename(
    tmp_path: Path,
) -> None:
    repo = make_repo(tmp_path)
    runs = tmp_path / "runs"
    write_file(repo / "rollback.py", "value = 1\n")
    sha = sha256_file(repo / "rollback.py")
    preview = preview_repo_patch(
        repo,
        [
            {
                "path": "rollback.py",
                "expected_sha256": sha,
                "old_text": "value = 1",
                "new_text": "value = 2",
            }
        ],
        runs,
    )
    apply_previewed_repo_change(repo, preview["patch_id"], runs)
    manifest_path = runs / "managed_patches" / preview["patch_id"] / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["applied_results"][0]["rollback_file"] = "../rollback_0.bin"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    with pytest.raises(RuntimeError, match="Rollback filename mismatch"):
        revert_managed_patch(repo, preview["patch_id"], runs)


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
    assert result["changed_files"] == ["new.py"]
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
    assert result["changed_files"] == ["del.py"]
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
    assert result["changed_files"] == ["src.py", "dst.py"]
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


def test_apply_repo_patch_rejects_preview_payload_mismatch(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    runs = tmp_path / "runs"
    write_file(repo / "mismatch.py", "value = 1\n")
    sha = sha256_file(repo / "mismatch.py")
    preview_ops = [
        {
            "path": "mismatch.py",
            "expected_sha256": sha,
            "old_text": "value = 1",
            "new_text": "value = 2",
        }
    ]
    preview = preview_repo_patch(repo, preview_ops, runs)
    apply_ops = [
        {
            "path": "mismatch.py",
            "expected_sha256": sha,
            "old_text": "value = 1",
            "new_text": "value = 999",
        }
    ]

    with pytest.raises(ValueError, match="does not match the previewed payload"):
        apply_repo_patch(repo, apply_ops, preview["patch_id"], runs)


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


def test_preview_supports_line_range_replacement(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    runs = tmp_path / "runs"
    write_file(repo / "ranges.py", "one\nold\nthree\n")
    sha = sha256_file(repo / "ranges.py")

    preview = preview_repo_patch(
        repo,
        [
            {
                "path": "ranges.py",
                "expected_sha256": sha,
                "type": "replace_lines",
                "start_line": 2,
                "end_line": 2,
                "new_text": "new\n",
            }
        ],
        runs,
    )

    assert preview["ok"] is True
    applied = apply_repo_patch(
        repo,
        [
            {
                "path": "ranges.py",
                "expected_sha256": sha,
                "type": "replace_lines",
                "start_line": 2,
                "end_line": 2,
                "new_text": "new\n",
            }
        ],
        preview["patch_id"],
        runs,
    )
    assert applied["ok"] is True
    assert (repo / "ranges.py").read_text(encoding="utf-8") == "one\nnew\nthree\n"


def test_preview_supports_exact_text_lf_anchor_against_crlf_file(
    tmp_path: Path,
) -> None:
    repo = make_repo(tmp_path)
    runs = tmp_path / "runs"
    path = repo / "exact_windows.py"
    path.write_bytes(b"alpha\r\nbeta\r\n")
    sha = sha256_file(path)
    operation = {
        "path": "exact_windows.py",
        "expected_sha256": sha,
        "type": "exact_text",
        "old_text": "alpha\nbeta\n",
        "new_text": "alpha\ngamma\n",
    }

    preview = preview_repo_patch(repo, [operation], runs)
    assert preview["ok"] is True
    result = apply_repo_patch(repo, [operation], preview["patch_id"], runs)

    assert result["ok"] is True
    assert path.read_bytes() == b"alpha\r\ngamma\r\n"


def test_preview_supports_unified_diff_and_crlf_matching(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    runs = tmp_path / "runs"
    path = repo / "windows.py"
    path.write_bytes(b"alpha\r\nbeta\r\n")
    sha = sha256_file(path)
    diff = (
        "--- a/windows.py\n+++ b/windows.py\n@@ -1,2 +1,2 @@\n alpha\n-beta\n+gamma\n"
    )

    preview = preview_repo_patch(
        repo,
        [
            {
                "path": "windows.py",
                "expected_sha256": sha,
                "type": "unified_diff",
                "diff": diff,
            }
        ],
        runs,
    )

    assert preview["ok"] is True
    apply_repo_patch(
        repo,
        [
            {
                "path": "windows.py",
                "expected_sha256": sha,
                "type": "unified_diff",
                "diff": diff,
            }
        ],
        preview["patch_id"],
        runs,
    )
    assert path.read_bytes() == b"alpha\r\ngamma\r\n"


def test_preview_supports_python_ast_top_level_replacement(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    runs = tmp_path / "runs"
    write_file(repo / "ast_mod.py", "def old():\n    return 1\n")
    sha = sha256_file(repo / "ast_mod.py")
    operation = {
        "path": "ast_mod.py",
        "expected_sha256": sha,
        "type": "python_ast",
        "target_type": "function",
        "target_name": "old",
        "new_text": "def old():\n    return 2\n",
    }

    preview = preview_repo_patch(repo, [operation], runs)
    assert preview["ok"] is True
    result = apply_repo_patch(repo, [operation], preview["patch_id"], runs)
    assert result["phases"]
    assert result["introduced_changes"] == ["ast_mod.py"]
    assert (repo / "ast_mod.py").read_text(
        encoding="utf-8"
    ) == "def old():\n    return 2\n"


# ---------------------------------------------------------------------------
# No CodexRunner or local model invocation
# ---------------------------------------------------------------------------


def test_repo_writer_does_not_import_codex_runner(tmp_path: Path) -> None:
    import ast

    import codexbridge.repo_writer as rw_mod

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

    init_git_repo(tmp_path)
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

    init_git_repo(tmp_path)
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


def test_server_preview_creation_removal_and_apply_previewed_change(
    tmp_path: Path,
) -> None:
    import codexbridge.server as server
    from codexbridge.config import AppConfig, RepoConfig

    init_git_repo(tmp_path)
    write_file(tmp_path / "remove_me.py", "print('bye')\n")
    config = AppConfig(
        repos={"repo": RepoConfig(path=str(tmp_path))},
        config_dir=tmp_path,
        runs_dir=str(tmp_path / "runs"),
    )
    server.set_config(config, tmp_path / "config.yaml")

    create_preview = server.preview_repo_file_creation(
        "repo", "created.py", "print('hi')\n"
    )
    assert create_preview["ok"] is True
    create_result = server.apply_previewed_repo_change(
        "repo", create_preview["patch_id"]
    )
    assert create_result["ok"] is True
    assert (tmp_path / "created.py").exists()

    remove_preview = server.preview_repo_file_removal(
        "repo", "remove_me.py", sha256_file(tmp_path / "remove_me.py")
    )
    assert remove_preview["ok"] is True
    remove_result = server.apply_previewed_repo_change(
        "repo", remove_preview["patch_id"]
    )
    assert remove_result["ok"] is True
    assert not (tmp_path / "remove_me.py").exists()


def test_server_move_file(tmp_path: Path) -> None:
    import codexbridge.server as server
    from codexbridge.config import AppConfig, RepoConfig

    init_git_repo(tmp_path)
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
