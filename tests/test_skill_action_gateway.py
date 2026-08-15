from __future__ import annotations

import base64
import threading
from pathlib import Path

import pytest
from pydantic import TypeAdapter, ValidationError

import soma.server as server
from soma.config import AppConfig
from soma.gateway_models import SkillActionRequest, SkillQueryRequest
from soma.skills import SkillLibrary


def _skill_md(name: str, description: str, body: str = "# Instructions\nDo the thing.\n") -> str:
    return f"---\nname: {name}\ndescription: {description}\n---\n\n{body}"


def _config(tmp_path: Path, root: Path) -> AppConfig:
    return AppConfig(
        repos={},
        runs_dir=str(tmp_path / "runs"),
        skill_library={
            "skill_library_root": str(root),
            "skill_library_kind": "external_private_library",
        },
    )


def _action(payload: dict) -> SkillActionRequest:
    return TypeAdapter(SkillActionRequest).validate_python(payload)


def _query(payload: dict) -> SkillQueryRequest:
    return TypeAdapter(SkillQueryRequest).validate_python(payload)


def _install_config(tmp_path: Path, root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(server, "_config", _config(tmp_path, root))
    monkeypatch.setattr(server, "_config_path", None)


def _import_payload(
    *,
    name: str,
    description: str,
    request_id: str,
    make_current: bool = False,
    expected_state_version: int | None = None,
    body: str = "# Instructions\nDo the thing.\n",
) -> dict:
    payload = {
        "operation": "import_revision",
        "files": [{"relative_path": "SKILL.md", "text": _skill_md(name, description, body)}],
        "controller_request_id": request_id,
        "make_current": make_current,
    }
    if expected_state_version is not None:
        payload["expected_state_version"] = expected_state_version
    return payload


def test_skill_action_request_union_is_strict_and_bounded() -> None:
    adapter = TypeAdapter(SkillActionRequest)
    imported = adapter.validate_python(
        {
            "operation": "import_revision",
            "files": [{"relative_path": "SKILL.md", "text": _skill_md("demo", "Demo") }],
            "controller_request_id": "import-1",
        }
    )
    assert imported.operation == "import_revision"
    assert imported.source_kind == "owner_local_import"
    assert adapter.validate_python(
        {
            "operation": "set_current",
            "skill_ref": "skill:demo@sha256:" + "a" * 64,
            "expected_state_version": 1,
            "controller_request_id": "set-1",
        }
    ).operation == "set_current"
    assert adapter.validate_python(
        {
            "operation": "rollback",
            "skill_ref": "skill:demo@sha256:" + "a" * 64,
            "expected_state_version": 2,
            "controller_request_id": "rollback-1",
        }
    ).operation == "rollback"
    assert adapter.validate_python(
        {
            "operation": "disable",
            "skill_name": "demo",
            "expected_state_version": 3,
            "controller_request_id": "disable-1",
        }
    ).operation == "disable"

    invalid = (
        {
            "operation": "import_revision",
            "files": [{"relative_path": "SKILL.md"}],
            "controller_request_id": "missing-content",
        },
        {
            "operation": "import_revision",
            "files": [{"relative_path": "SKILL.md", "text": "x", "base64_bytes": "eA=="}],
            "controller_request_id": "double-content",
        },
        {
            "operation": "import_revision",
            "files": [{"relative_path": "SKILL.md", "text": "x"}],
            "controller_request_id": "bad-source",
            "source_kind": "repo_builtin_seed",
        },
        {
            "operation": "enable",
            "skill_name": "demo",
            "controller_request_id": "missing-cas",
        },
        {
            "operation": "set_current",
            "skill_ref": "ref",
            "expected_state_version": -1,
            "controller_request_id": "bad-version",
        },
    )
    for payload in invalid:
        with pytest.raises(ValidationError):
            adapter.validate_python(payload)

    too_many = [
        {"relative_path": f"references/{index}.txt", "text": "x"}
        for index in range(257)
    ]
    with pytest.raises(ValidationError):
        adapter.validate_python(
            {
                "operation": "import_revision",
                "files": too_many,
                "controller_request_id": "too-many",
            }
        )


def test_non_import_action_does_not_initialize_absent_library(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "owner-skills"
    _install_config(tmp_path, root, monkeypatch)
    result = server.skill_action(
        _action(
            {
                "operation": "disable",
                "skill_name": "missing",
                "expected_state_version": 0,
                "controller_request_id": "missing-disable",
            }
        )
    )
    assert result["ok"] is False
    assert result["error_code"] == "skill_not_found"
    assert not root.exists()


def test_direct_chat_import_supports_text_and_base64_replay_conflict_and_never_executes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "owner-skills"
    marker = tmp_path / "executed.txt"
    _install_config(tmp_path, root, monkeypatch)
    script = f"from pathlib import Path\nPath({str(marker)!r}).write_text('bad')\n"
    payload = {
        "operation": "import_revision",
        "files": [
            {
                "relative_path": "SKILL.md",
                "text": _skill_md("chat-skill", "Chat-authored workflow"),
            },
            {
                "relative_path": "assets/data.bin",
                "base64_bytes": base64.b64encode(b"\x00\xffbinary").decode("ascii"),
            },
            {"relative_path": "scripts/run.py", "text": script},
        ],
        "controller_request_id": "chat-import-1",
        "source_kind": "owner_local_import",
        "source_ref": "chat://authored",
        "make_current": True,
    }
    first = server.skill_action(_action(payload))
    assert first["ok"] is True
    assert first["created"] is True
    assert first["current"] is True
    assert first["state_version"] == 1
    assert not marker.exists()

    replay = server.skill_action(_action(payload))
    assert replay["ok"] is True
    assert replay["skill_ref"] == first["skill_ref"]
    assert replay["replayed"] is True
    assert not marker.exists()

    changed = dict(payload)
    changed["files"] = [
        {
            "relative_path": "SKILL.md",
            "text": _skill_md("chat-skill", "Different bytes"),
        }
    ]
    conflict = server.skill_action(_action(changed))
    assert conflict["ok"] is False
    assert conflict["error_code"] == "skill_request_conflict"

    binary = server.skill_query(
        _query(
            {
                "operation": "resource",
                "skill_ref": first["skill_ref"],
                "relative_path": "assets/data.bin",
            }
        )
    )
    assert binary["encoding"] == "base64"
    assert base64.b64decode(binary["content_base64"]) == b"\x00\xffbinary"
    assert binary["executes_resource"] is False
    assert not marker.exists()


def test_set_current_lost_response_replay_and_rollback_preserve_immutable_history(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "owner-skills"
    _install_config(tmp_path, root, monkeypatch)
    first = server.skill_action(
        _action(
            _import_payload(
                name="versioned-skill",
                description="Version one",
                request_id="version-v1",
                make_current=True,
                body="# Instructions\nVersion one.\n",
            )
        )
    )
    second = server.skill_action(
        _action(
            _import_payload(
                name="versioned-skill",
                description="Version two",
                request_id="version-v2",
                body="# Instructions\nVersion two.\n",
            )
        )
    )
    set_payload = {
        "operation": "set_current",
        "skill_ref": second["skill_ref"],
        "expected_state_version": first["state_version"],
        "controller_request_id": "set-v2-current",
    }
    promoted = server.skill_action(_action(set_payload))
    assert promoted["ok"] is True
    assert promoted["state_version"] == 2
    replay = server.skill_action(_action(set_payload))
    assert replay["ok"] is True
    assert replay["replayed"] is True
    assert replay["state_version"] == 2

    rolled_back = server.skill_action(
        _action(
            {
                "operation": "rollback",
                "skill_ref": first["skill_ref"],
                "expected_state_version": promoted["state_version"],
                "controller_request_id": "rollback-v1",
            }
        )
    )
    assert rolled_back["ok"] is True
    assert rolled_back["skill_ref"] == first["skill_ref"]
    assert rolled_back["state_version"] == 3

    current = server.skill_query(_query({"operation": "get", "name": "versioned-skill"}))
    historical = server.skill_query(
        _query({"operation": "get", "skill_ref": second["skill_ref"]})
    )
    assert current["skill_ref"] == first["skill_ref"]
    assert "Version one." in current["skill_md"]
    assert historical["skill_ref"] == second["skill_ref"]
    assert historical["historical"] is True
    assert "Version two." in historical["skill_md"]


def test_disable_hides_normal_discovery_exact_ref_remains_and_enable_restores_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "owner-skills"
    _install_config(tmp_path, root, monkeypatch)
    imported = server.skill_action(
        _action(
            _import_payload(
                name="toggle-skill",
                description="Toggle workflow",
                request_id="toggle-import",
                make_current=True,
            )
        )
    )
    disabled = server.skill_action(
        _action(
            {
                "operation": "disable",
                "skill_name": "toggle-skill",
                "expected_state_version": imported["state_version"],
                "controller_request_id": "toggle-disable",
            }
        )
    )
    assert disabled["ok"] is True
    assert disabled["enabled"] is False
    assert server.skill_query(_query({"operation": "list"}))["items"] == []
    exact = server.skill_query(
        _query({"operation": "get", "skill_ref": imported["skill_ref"]})
    )
    assert exact["ok"] is True
    assert exact["enabled"] is False

    enabled = server.skill_action(
        _action(
            {
                "operation": "enable",
                "skill_name": "toggle-skill",
                "expected_state_version": disabled["state_version"],
                "controller_request_id": "toggle-enable",
            }
        )
    )
    assert enabled["ok"] is True
    assert enabled["enabled"] is True
    listed = server.skill_query(_query({"operation": "list"}))
    assert [item["skill_ref"] for item in listed["items"]] == [imported["skill_ref"]]


def test_concurrent_set_current_same_expected_version_has_one_winner(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "owner-skills"
    _install_config(tmp_path, root, monkeypatch)
    base = server.skill_action(
        _action(
            _import_payload(
                name="cas-skill",
                description="Base",
                request_id="cas-base",
                make_current=True,
            )
        )
    )
    left = server.skill_action(
        _action(_import_payload(name="cas-skill", description="Left", request_id="cas-left"))
    )
    right = server.skill_action(
        _action(_import_payload(name="cas-skill", description="Right", request_id="cas-right"))
    )
    requests = [
        _action(
            {
                "operation": "set_current",
                "skill_ref": left["skill_ref"],
                "expected_state_version": base["state_version"],
                "controller_request_id": "cas-promote-left",
            }
        ),
        _action(
            {
                "operation": "set_current",
                "skill_ref": right["skill_ref"],
                "expected_state_version": base["state_version"],
                "controller_request_id": "cas-promote-right",
            }
        ),
    ]
    results: list[dict] = []
    lock = threading.Lock()

    def worker(request: SkillActionRequest) -> None:
        result = server.skill_action(request)
        with lock:
            results.append(result)

    threads = [threading.Thread(target=worker, args=(request,)) for request in requests]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)
    assert all(not thread.is_alive() for thread in threads)
    assert len(results) == 2
    assert sum(result["ok"] is True for result in results) == 1
    failures = [result for result in results if result["ok"] is False]
    assert failures[0]["error_code"] == "stale_skill_state"
    state = SkillLibrary(root, read_only=True).get_state("cas-skill")
    assert state["state_version"] == base["state_version"] + 1
    assert state["current_skill_ref"] in {left["skill_ref"], right["skill_ref"]}


def test_concurrent_enable_disable_same_expected_version_has_one_winner(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "owner-skills"
    _install_config(tmp_path, root, monkeypatch)
    imported = server.skill_action(
        _action(
            _import_payload(
                name="toggle-cas",
                description="Toggle CAS",
                request_id="toggle-cas-import",
                make_current=True,
            )
        )
    )
    requests = [
        _action(
            {
                "operation": operation,
                "skill_name": "toggle-cas",
                "expected_state_version": imported["state_version"],
                "controller_request_id": f"toggle-cas-{operation}",
            }
        )
        for operation in ("enable", "disable")
    ]
    results: list[dict] = []
    lock = threading.Lock()

    def worker(request: SkillActionRequest) -> None:
        result = server.skill_action(request)
        with lock:
            results.append(result)

    threads = [threading.Thread(target=worker, args=(request,)) for request in requests]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)
    assert all(not thread.is_alive() for thread in threads)
    assert len(results) == 2
    assert sum(result["ok"] is True for result in results) == 1
    assert [result for result in results if result["ok"] is False][0]["error_code"] == "stale_skill_state"
    state = SkillLibrary(root, read_only=True).get_state("toggle-cas")
    assert state["state_version"] == imported["state_version"] + 1
