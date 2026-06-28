from __future__ import annotations

from pathlib import Path

from codexbridge.config import AppConfig, LocalCodingConfig, RepoConfig


def test_local_coding_config_defaults_are_preview_only(tmp_path: Path) -> None:
    config = AppConfig(
        repos={"repo": RepoConfig(path=str(tmp_path))}, config_dir=tmp_path
    )

    assert isinstance(config.local_coding, LocalCodingConfig)
    assert config.local_coding.local_coding_enabled is False
    assert config.local_coding.local_coding_preview_enabled is True
    assert config.local_coding.local_coding_apply_enabled is False
    assert config.local_coding.local_coding_default_validation_commands == [
        "git_status"
    ]
    assert config.resolve_local_coding_runs_dir() == tmp_path / "runs" / "local_coding"
