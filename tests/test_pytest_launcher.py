from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = ROOT / "scripts" / "run_pytest.ps1"
POWERSHELL = shutil.which("pwsh") or shutil.which("powershell.exe")


def test_pytest_launcher_declares_safe_basetemp_preparation() -> None:
    source = LAUNCHER.read_text(encoding="utf-8")
    assert "New-Item -ItemType Directory -Force -Path $BaseTempParent" in source
    assert "Remove-Item -LiteralPath $BaseTemp -Recurse -Force" in source
    assert '@("-m", "pytest", "--basetemp", $BaseTemp)' in source


@pytest.mark.skipif(not POWERSHELL, reason="PowerShell is required")
def test_pytest_launcher_creates_missing_nested_parent_and_preserves_siblings(
    tmp_path: Path,
) -> None:
    probe = tmp_path / "test_probe.py"
    probe.write_text("def test_probe():\n    assert True\n", encoding="utf-8")

    base_temp = tmp_path / "missing" / "nested" / "pytest-root"
    sibling = base_temp.parent / "preserve.txt"
    assert not base_temp.parent.exists()

    driver = tmp_path / "invoke_launcher.ps1"
    driver.write_text(
        "param(\n"
        "    [string]$Launcher,\n"
        "    [string]$ProjectRoot,\n"
        "    [string]$PythonExecutable,\n"
        "    [string]$BaseTemp,\n"
        "    [string]$Probe\n"
        ")\n"
        "& $Launcher "
        "-ProjectRoot $ProjectRoot "
        "-PythonExecutable $PythonExecutable "
        "-BaseTemp $BaseTemp "
        "-CleanBaseTemp "
        "-PytestArguments @('-q', $Probe)\n",
        encoding="utf-8",
    )
    argv = [
        str(POWERSHELL),
        "-NoLogo",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(driver),
        "-Launcher",
        str(LAUNCHER),
        "-ProjectRoot",
        str(ROOT),
        "-PythonExecutable",
        sys.executable,
        "-BaseTemp",
        str(base_temp),
        "-Probe",
        str(probe),
    ]

    first = subprocess.run(
        argv,
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert first.returncode == 0, first.stdout + first.stderr
    assert "1 passed" in first.stdout
    assert base_temp.parent.is_dir()

    sibling.write_text("keep", encoding="utf-8")
    second = subprocess.run(
        argv,
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert second.returncode == 0, second.stdout + second.stderr
    assert sibling.read_text(encoding="utf-8") == "keep"
