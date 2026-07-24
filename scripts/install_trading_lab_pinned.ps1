<#
.SYNOPSIS
    Reproducibly install the Trading Lab package from a verified commit.

.DESCRIPTION
    There is no package registry for trading-lab yet, so this script provides
    the strongest reproducibility the local toolchain supports:

      1. verify the TradingLab checkout is at the expected commit and clean;
      2. build a wheel from that exact commit;
      3. record version, commit, and the wheel's SHA-256;
      4. optionally verify the wheel against an expected SHA-256;
      5. install that exact wheel with --no-deps;
      6. stamp the installed package with the source commit so Soma's
         diagnostics can report what is actually running.

    Use -ExpectedCommit and -ExpectedSha256 in any setting where the artifact
    must be verified before it is installed. Without them the script still
    records both values so a later run can pin to them.

.PARAMETER ExpectedCommit
    Refuse to build unless the checkout is exactly at this commit.

.PARAMETER ExpectedSha256
    Refuse to install unless the built wheel hashes to this value.

.PARAMETER AllowDirty
    Permit building from a checkout with uncommitted changes. The recorded
    commit is then not a complete description of the artifact, so this is off
    by default.

.EXAMPLE
    pwsh -File scripts/install_trading_lab_pinned.ps1

.EXAMPLE
    pwsh -File scripts/install_trading_lab_pinned.ps1 `
        -ExpectedCommit 1a2b3c4... -ExpectedSha256 9f8e7d...
#>
[CmdletBinding()]
param(
    [string]$TradingLabPath,
    [string]$Python,
    [string]$ExpectedCommit,
    [string]$ExpectedSha256,
    [switch]$AllowDirty
)

$ErrorActionPreference = 'Stop'

$somaRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path

if (-not $TradingLabPath) {
    $sibling = Join-Path (Split-Path $somaRoot -Parent) 'TradingLab'
    if (Test-Path (Join-Path $sibling 'pyproject.toml')) {
        $TradingLabPath = $sibling
    }
    else {
        throw "TradingLab was not found next to Soma at '$sibling'. Pass -TradingLabPath explicitly."
    }
}
$TradingLabPath = (Resolve-Path $TradingLabPath).Path

if (-not $Python) { $Python = Join-Path $somaRoot '.venv\Scripts\python.exe' }
if (-not (Test-Path $Python)) { throw "Python interpreter not found at '$Python'." }

# ---------------------------------------------------------------- verify source
$commit = (& git -C $TradingLabPath rev-parse HEAD).Trim()
if ($LASTEXITCODE -ne 0) { throw "'$TradingLabPath' is not a git repository." }

if ($ExpectedCommit -and $commit -ne $ExpectedCommit) {
    throw "TradingLab is at $commit but $ExpectedCommit was expected."
}

$dirty = (& git -C $TradingLabPath status --porcelain)
if ($dirty -and -not $AllowDirty) {
    throw "TradingLab has uncommitted changes; pass -AllowDirty to build anyway.`n$dirty"
}

Write-Host "Trading Lab : $TradingLabPath"
Write-Host "Commit      : $commit"
Write-Host "Interpreter : $Python"
Write-Host ''

# ---------------------------------------------------------------------- build
$distDir = Join-Path $TradingLabPath 'dist'
if (Test-Path $distDir) {
    Get-ChildItem $distDir -Filter '*.whl' | Remove-Item -Force
}

Push-Location $TradingLabPath
try {
    & $Python -m build --wheel
    if ($LASTEXITCODE -ne 0) { throw "Wheel build failed with exit code $LASTEXITCODE." }
}
finally {
    Pop-Location
}

$wheel = Get-ChildItem $distDir -Filter '*.whl' | Sort-Object LastWriteTime -Descending | Select-Object -First 1
if (-not $wheel) { throw 'No wheel was produced.' }

$sha256 = (Get-FileHash $wheel.FullName -Algorithm SHA256).Hash.ToLower()
$version = ($wheel.Name -split '-')[1]

Write-Host ''
Write-Host "Wheel       : $($wheel.Name)"
Write-Host "Version     : $version"
Write-Host "SHA-256     : $sha256"
Write-Host ''

if ($ExpectedSha256 -and $sha256 -ne $ExpectedSha256.ToLower()) {
    throw "Wheel hash $sha256 does not match the expected $ExpectedSha256."
}

# -------------------------------------------------------------------- install
& $Python -m pip uninstall -y trading-lab | Out-Null
& $Python -m pip install --no-deps --force-reinstall $wheel.FullName
if ($LASTEXITCODE -ne 0) { throw "Install failed with exit code $LASTEXITCODE." }

# --------------------------------------------------------- stamp the provenance
$stampScript = @"
import json, pathlib, trading_lab
stamp = pathlib.Path(trading_lab.__file__).parent / '_build_stamp.json'
stamp.write_text(json.dumps({
    'commit': '$commit',
    'version': '$version',
    'wheel': '$($wheel.Name)',
    'wheel_sha256': '$sha256',
}, indent=2), encoding='utf-8')
print(stamp)
"@
& $Python -c $stampScript
if ($LASTEXITCODE -ne 0) { throw "Failed to write the build stamp." }

# ---------------------------------------------------------------------- verify
& $Python -c @'
import json
from soma.trading_lab_adapter import package_identity
identity = package_identity()
assert identity["backend"] == "package", identity
assert not identity["editable"], "a pinned install must not be editable"
assert identity["source_commit"], "the build stamp is missing"
print(json.dumps(identity, indent=2))
'@
if ($LASTEXITCODE -ne 0) { throw "Verification failed with exit code $LASTEXITCODE." }

Write-Host ''
Write-Host 'Pinned installation complete. Record these to reproduce it exactly:' -ForegroundColor Green
Write-Host "  -ExpectedCommit  $commit"
Write-Host "  -ExpectedSha256  $sha256"
