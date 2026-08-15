from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import TypeAdapter, ValidationError

import soma.server as server
from soma.config import AppConfig
from soma.gateway_models import SkillQueryRequest
from soma.skills import SkillLibrary


def _skill_md(name: str, description: str, body: str = "# Instructions\nDo the thing.\n") -> bytes:
    return (
        f"---\nname: {name}\ndescription: {description}\n---\n\n{body}"
    ).encode("utf-8")


def _config(tmp_path: Path, root: Path) -> AppConfig:
    return AppConfig(
        repos={},
        runs_dir=str(tmp_path / "runs"),
        skill_library={
            "skill_library_root": str(root),
            "skill_library_kind": "external_private_library",
        },
    )


def _request(payload: dict) -> SkillQueryRequest:
    return TypeAdapter(SkillQueryRequest).validate_python(payload)


def test_skill_query_request_union_is_strict_and_bounded() -> None:
    adapter = TypeAdapter(SkillQueryRequest)
    assert adapter.validate_python({"operation": "capabilities"}).operation == "capabilities"
    assert adapter.validate_python({"operation": "list"}).limit == 20
    assert adapter.validate_python({"operation": "search", "query": "research"}).query == "research"
    assert adapter.validate_python({"operation": "get", "name": "research"}).name == "research"
    assert adapter.validate_python({"operation": "history", "skill_name": "research"}).limit == 20
    assert adapter.validate_python(
        {
            "operation": "resource",
            "skill_ref": "skill:research@sha256:" + "a" * 64,
            "relative_path": "references/guide.md",
        }
    ).max_bytes == 64 * 1024

    invalid = (
        {"operation": "get"},
        {"operation": "get", "name": "research", "skill_ref": "ref"},
        {"operation": "resource", "skill_ref": "ref", "relative_path": "a", "max_bytes": 256 * 1024 + 1},
        {"operation": "search", "query": ""},
        {"operation": "list", "query": "cross-operation"},
    )
    for payload in invalid:
        with pytest.raises(ValidationError):
            adapter.validate_python(payload)


def test_uninitialized_external_library_read_gateway_never_creates_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "owner-skills"
    config = _config(tmp_path, root)
    monkeypatch.setattr(server, "_config", config)
    monkeypatch.setattr(server, "_config_path", None)

    capabilities = server.skill_query(_request({"operation": "capabilities"}))
    assert capabilities["ok"] is True
    assert capabilities["library_initialized"] is False
    assert capabilities["executes_resources"] is False

    listed = server.skill_query(_request({"operation": "list"}))
    searched = server.skill_query(
        _request({"operation": "search", "query": "anything"})
    )
    missing = server.skill_query(_request({"operation": "get", "name": "anything"}))
    assert listed["items"] == []
    assert searched["items"] == []
    assert missing["ok"] is False
    assert missing["error_code"] == "skill_not_found"
    assert not root.exists()
    assert not (tmp_path / "runs").exists()


def test_gateway_reads_current_and_historical_revision_through_read_only_library(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "owner-skills"
    writable = SkillLibrary(root)
    first = writable.import_revision(
        {
            "SKILL.md": _skill_md("research-helper", "Research workflow v1"),
            "references/guide.md": b"guide-v1",
        },
        controller_request_id="gateway-v1",
        source_kind="owner_local_import",
        make_current=True,
    )
    second = writable.import_revision(
        {
            "SKILL.md": _skill_md(
                "research-helper",
                "Research workflow v2",
                body="# Instructions\nUse the revised workflow.\n",
            ),
            "references/guide.md": b"guide-v2",
        },
        controller_request_id="gateway-v2",
        source_kind="owner_local_import",
        make_current=True,
        expected_state_version=first["state_version"],
    )

    config = _config(tmp_path, root)
    monkeypatch.setattr(server, "_config", config)
    monkeypatch.setattr(server, "_config_path", None)

    listed = server.skill_query(_request({"operation": "list"}))
    assert [item["skill_ref"] for item in listed["items"]] == [second["skill_ref"]]
    assert "skill_md" not in listed["items"][0]

    searched = server.skill_query(
        _request({"operation": "search", "query": "research"})
    )
    assert searched["items"][0]["skill_ref"] == second["skill_ref"]
    assert "skill_md" not in searched["items"][0]

    current = server.skill_query(
        _request({"operation": "get", "name": "research-helper"})
    )
    historical = server.skill_query(
        _request({"operation": "get", "skill_ref": first["skill_ref"]})
    )
    assert current["skill_ref"] == second["skill_ref"]
    assert historical["skill_ref"] == first["skill_ref"]
    assert historical["historical"] is True

    resource = server.skill_query(
        _request(
            {
                "operation": "resource",
                "skill_ref": first["skill_ref"],
                "relative_path": "references/guide.md",
            }
        )
    )
    assert resource["content_text"] == "guide-v1"
    assert resource["executes_resource"] is False
    assert resource["locator_is_execution_authority"] is False


def test_gateway_reports_integrity_drift_without_rehashing_revision(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "owner-skills"
    writable = SkillLibrary(root)
    revision = writable.import_revision(
        {"SKILL.md": _skill_md("drift-skill", "Drift workflow")},
        controller_request_id="gateway-drift",
        make_current=True,
    )
    Path(str(revision["package_root"]), "SKILL.md").write_text(
        "---\nname: drift-skill\ndescription: changed out of band\n---\n",
        encoding="utf-8",
    )

    config = _config(tmp_path, root)
    monkeypatch.setattr(server, "_config", config)
    monkeypatch.setattr(server, "_config_path", None)
    result = server.skill_query(
        _request({"operation": "get", "skill_ref": revision["skill_ref"]})
    )
    assert result["ok"] is False
    assert result["error_code"] == "package_integrity_mismatch"
