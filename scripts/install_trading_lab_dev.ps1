<#
.SYNOPSIS
    Install the Trading Lab package into Soma's virtual environment for
    day-to-day development.

.DESCRIPTION
    Installs D:\Github\TradingLab (or the path given by -TradingLabPath) as an
    editable install, so edits in the TradingLab working tree take effect in
    Soma immediately with no reinstall.

    This is the convenient path. For a reproducible, commit-and-hash-pinned
    installation, use install_trading_lab_pinned.ps1 instead.

.PARAMETER TradingLabPath
    The TradingLab checkout. Defaults to a sibling of the Soma repository,
    so the script works without anyone's absolute path baked into it.

.PARAMETER Python
    The interpreter to install into. Defaults to Soma's own venv.

.EXAMPLE
    pwsh -File scripts/install_trading_lab_dev.ps1
#>
[CmdletBinding()]
param(
    [string]$TradingLabPath,
    [string]$Python
)

$ErrorActionPreference = 'Stop'

$somaRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path

if (-not $TradingLabPath) {
    # Prefer a sibling checkout: <parent-of-Soma>/TradingLab
    $sibling = Join-Path (Split-Path $somaRoot -Parent) 'TradingLab'
    if (Test-Path (Join-Path $sibling 'pyproject.toml')) {
        $TradingLabPath = $sibling
    }
    else {
        throw "TradingLab was not found next to Soma at '$sibling'. Pass -TradingLabPath explicitly."
    }
}

$TradingLabPath = (Resolve-Path $TradingLabPath).Path
if (-not (Test-Path (Join-Path $TradingLabPath 'pyproject.toml'))) {
    throw "'$TradingLabPath' does not look like the TradingLab repository (no pyproject.toml)."
}

if (-not $Python) {
    $Python = Join-Path $somaRoot '.venv\Scripts\python.exe'
}
if (-not (Test-Path $Python)) {
    throw "Python interpreter not found at '$Python'."
}

Write-Host "Soma        : $somaRoot"
Write-Host "Trading Lab : $TradingLabPath"
Write-Host "Interpreter : $Python"
Write-Host ''

& $Python -m pip install -e $TradingLabPath
if ($LASTEXITCODE -ne 0) { throw "Editable install failed with exit code $LASTEXITCODE." }

Write-Host ''
Write-Host 'Verifying...'
& $Python -c @'
import json
import trading_lab
from soma.trading_lab_adapter import package_identity
identity = package_identity()
assert identity["backend"] == "package", identity
assert identity["editable"], "expected an editable install"
print(json.dumps(identity, indent=2))
'@
if ($LASTEXITCODE -ne 0) { throw "Verification failed with exit code $LASTEXITCODE." }

Write-Host ''
Write-Host 'Trading Lab is installed editable into Soma.' -ForegroundColor Green
