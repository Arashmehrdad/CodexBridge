from __future__ import annotations

import pytest

from soma.research_map.canonical import (
    canonical_json_bytes,
    canonical_json_sha256,
    canonical_text_sha256,
    logical_record_id,
    normalize_canonical_text,
    normalize_repo_relative_path,
    record_version_id,
    relation_id,
)


def test_canonical_text_hash_is_portable_across_line_endings_and_unicode() -> None:
    lf = "# Research\n\nspine → filter λ\n"
    crlf = lf.replace("\n", "\r\n")
    cr = lf.replace("\n", "\r")

    assert canonical_text_sha256(lf) == canonical_text_sha256(crlf)
    assert canonical_text_sha256(lf) == canonical_text_sha256(cr)
    assert normalize_canonical_text(crlf) == lf


def test_canonical_text_hash_changes_for_substantive_change() -> None:
    first = "finding: constrained\n"
    second = "finding: falsified\n"
    assert canonical_text_sha256(first) != canonical_text_sha256(second)


def test_canonical_text_requires_strict_utf8() -> None:
    with pytest.raises(UnicodeDecodeError):
        canonical_text_sha256(b"\xff\xfe")


def test_canonical_json_is_order_independent_and_preserves_unicode() -> None:
    left = {"z": ["λ", "شبکه"], "a": {"b": 2}}
    right = {"a": {"b": 2}, "z": ["λ", "شبکه"]}

    assert canonical_json_bytes(left) == canonical_json_bytes(right)
    assert canonical_json_sha256(left) == canonical_json_sha256(right)
    assert "λ" in canonical_json_bytes(left).decode("utf-8")


def test_repository_relative_path_normalization_and_rejections() -> None:
    assert normalize_repo_relative_path("docs\\research\\001.md") == "docs/research/001.md"

    for value in (
        "",
        "/docs/research/001.md",
        "C:/repo/docs/001.md",
        "../docs/001.md",
        "docs/../001.md",
        "docs//001.md",
        "docs/./001.md",
        ".git/config",
        ".soma/research-map/CURRENT.json",
    ):
        with pytest.raises((TypeError, ValueError)):
            normalize_repo_relative_path(value)


def test_deterministic_record_and_relation_identities_are_stable() -> None:
    path = "docs/research/038_example.md"
    text_hash = canonical_text_sha256("# Research 038\n")

    logical_a = logical_record_id(path)
    logical_b = logical_record_id(path)
    version_a = record_version_id(logical_a, text_hash)
    version_b = record_version_id(logical_b, text_hash)
    relation_a = relation_id(path, "research:038", "FORBIDS", "mechanism:generic-gating")
    relation_b = relation_id(path, "research:038", "FORBIDS", "mechanism:generic-gating")

    assert logical_a == logical_b
    assert logical_a.startswith("rrec_") and len(logical_a) == len("rrec_") + 64
    assert version_a == version_b
    assert version_a.startswith("rver_") and len(version_a) == len("rver_") + 64
    assert relation_a == relation_b
    assert relation_a.startswith("rel_") and len(relation_a) == len("rel_") + 64


def test_relation_identity_changes_only_for_identity_fields() -> None:
    path = "docs/research/038_example.md"
    base = relation_id(path, "research:038", "QUALIFIES", "claim:x")

    assert base != relation_id(path, "research:038", "FALSIFIES", "claim:x")
    assert base != relation_id(path, "research:038", "QUALIFIES", "claim:y")
