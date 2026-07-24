[CmdletBinding()]
param(
    [string]$ProjectRoot = "",
    [string]$Config = "config.yaml",
    [string]$PythonExecutable = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($ProjectRoot)) {
    $ProjectRoot = Split-Path -Parent (Split-Path -Parent $PSCommandPath)
}
$ProjectRoot = [System.IO.Path]::GetFullPath($ProjectRoot)
$ConfigPath = if ([System.IO.Path]::IsPathRooted($Config)) {
    [System.IO.Path]::GetFullPath($Config)
} else {
    [System.IO.Path]::GetFullPath((Join-Path $ProjectRoot $Config))
}
if (-not $PythonExecutable) {
    $PythonExecutable = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
}
if (-not (Test-Path -LiteralPath $PythonExecutable -PathType Leaf)) {
    throw "Python executable not found: $PythonExecutable"
}
if (-not (Test-Path -LiteralPath $ConfigPath -PathType Leaf)) {
    throw "Config file not found: $ConfigPath"
}

$EvidenceRoot = Join-Path $ProjectRoot "runs\comprehensive-self-check"
New-Item -ItemType Directory -Force -Path $EvidenceRoot | Out-Null
$PytestBaseTemp = Join-Path $EvidenceRoot ("pytest-" + [DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds())
$ServerStdout = Join-Path $EvidenceRoot "transport-server.out.log"
$ServerStderr = Join-Path $EvidenceRoot "transport-server.err.log"

function Invoke-Checked {
    param([string]$Name, [string]$FilePath, [string[]]$Arguments)
    Write-Output "[CHECK] $Name"
    & $FilePath @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "$Name failed with exit code $LASTEXITCODE"
    }
}

Invoke-Checked "pip check" $PythonExecutable @("-m", "pip", "check")
Invoke-Checked "full pytest" $PythonExecutable @(
    "-m", "pytest", "-q", "--basetemp", $PytestBaseTemp
)
Invoke-Checked "git diff --check" "git" @("diff", "--check")
Invoke-Checked "package identity" $PythonExecutable @(
    "-c",
    "import json, soma, fastmcp, pydantic, trading_lab; print(json.dumps({'soma': soma.__file__, 'fastmcp': fastmcp.__file__, 'pydantic': pydantic.__version__, 'trading_lab': trading_lab.__file__}, sort_keys=True))"
)

$Listener = [System.Net.Sockets.TcpListener]::new(
    [System.Net.IPAddress]::Loopback, 0
)
$Listener.Start()
$Port = ([System.Net.IPEndPoint]$Listener.LocalEndpoint).Port
$Listener.Stop()
$McpPath = "/mcp"
$Url = "http://127.0.0.1:$Port$McpPath"
$Server = $null
try {
    Write-Output "[CHECK] MCP startup on free port $Port"
    $Server = Start-Process -FilePath $PythonExecutable -ArgumentList @(
        "-m", "soma.server", "--config", $ConfigPath,
        "--transport", "http", "--host", "127.0.0.1",
        "--port", "$Port", "--path", $McpPath
    ) -WorkingDirectory $ProjectRoot -WindowStyle Hidden `
      -RedirectStandardOutput $ServerStdout -RedirectStandardError $ServerStderr `
      -PassThru

    $Ready = $false
    $Deadline = (Get-Date).AddSeconds(90)
    do {
        if ($Server.HasExited) { break }
        try {
            $Response = Invoke-WebRequest -Uri $Url -Method Get -TimeoutSec 2 `
                -UseBasicParsing -SkipHttpErrorCheck -ErrorAction Stop
            if ([int]$Response.StatusCode -eq 406) {
                $Ready = $true
                break
            }
        } catch {
            # Connection failures are expected until the temporary listener is ready.
        }
        Start-Sleep -Milliseconds 250
    } while ((Get-Date) -lt $Deadline)

    if (-not $Ready) {
        $Tail = if (Test-Path -LiteralPath $ServerStderr) {
            (Get-Content -LiteralPath $ServerStderr -Tail 80) -join "`n"
        } else { "" }
        throw "MCP startup probe failed for $Url`n$Tail"
    }
} finally {
    if ($Server -and -not $Server.HasExited) {
        Stop-Process -Id $Server.Id -Force -ErrorAction SilentlyContinue
        $Server.WaitForExit(5000) | Out-Null
    }
}

[ordered]@{
    ok = $true
    project_root = $ProjectRoot
    python = $PythonExecutable
    pytest_basetemp = $PytestBaseTemp
    transport_url = $Url
    evidence_root = $EvidenceRoot
} | ConvertTo-Json -Depth 4
