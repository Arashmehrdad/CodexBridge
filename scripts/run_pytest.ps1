[CmdletBinding()]
param(
    [string]$ProjectRoot = "",
    [string]$PythonExecutable = "",
    [string]$BaseTemp = "",
    [switch]$CleanBaseTemp,
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$PytestArguments
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($ProjectRoot)) {
    $ProjectRoot = Split-Path -Parent (Split-Path -Parent $PSCommandPath)
}
$ProjectRoot = [System.IO.Path]::GetFullPath($ProjectRoot)

if ([string]::IsNullOrWhiteSpace($PythonExecutable)) {
    $PythonExecutable = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
}
$PythonExecutable = [System.IO.Path]::GetFullPath($PythonExecutable)
if (-not (Test-Path -LiteralPath $PythonExecutable -PathType Leaf)) {
    throw "Python executable not found: $PythonExecutable"
}

if ([string]::IsNullOrWhiteSpace($BaseTemp)) {
    $EvidenceRoot = Join-Path $ProjectRoot "runs\pytest"
    $BaseTemp = Join-Path $EvidenceRoot (
        "pytest-" + [DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds()
    )
} elseif (-not [System.IO.Path]::IsPathRooted($BaseTemp)) {
    $BaseTemp = Join-Path $ProjectRoot $BaseTemp
}
$BaseTemp = [System.IO.Path]::GetFullPath($BaseTemp)
$BaseTempParent = Split-Path -Parent $BaseTemp

# Pytest creates the basetemp itself, but on Windows it does not create a missing
# parent chain. Preparing only the parent preserves pytest's own safety checks.
New-Item -ItemType Directory -Force -Path $BaseTempParent | Out-Null
if ($CleanBaseTemp -and (Test-Path -LiteralPath $BaseTemp)) {
    Remove-Item -LiteralPath $BaseTemp -Recurse -Force
}

$Arguments = @("-m", "pytest", "--basetemp", $BaseTemp)
if ($PytestArguments) {
    $Arguments += $PytestArguments
}

& $PythonExecutable @Arguments
$ExitCode = $LASTEXITCODE
if ($null -eq $ExitCode) {
    $ExitCode = 1
}
if ($ExitCode -ne 0) {
    throw "pytest failed with exit code $ExitCode"
}
