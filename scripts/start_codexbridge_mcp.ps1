param(
    [string]$ProjectRoot = "D:\Github\CodexBridge",
    [string]$Config = "config.yaml",
    [string]$HostName = "127.0.0.1",
    [int]$Port = 8000,
    [string]$McpPath = "/mcp",
    [string]$TunnelConfig = "$env:USERPROFILE\.cloudflared\codexbridge-mcp.yml",
    [string]$PublicMcpUrl = "https://mcp.spaceshipgames.win/mcp",
    [switch]$NoTunnel
)

$ErrorActionPreference = "Stop"

function Write-Step {
    param([string]$Message)
    Write-Host "[$(Get-Date -Format 'HH:mm:ss')] $Message"
}

function Test-McpEndpoint {
    param([string]$Url)
    try {
        $response = Invoke-WebRequest -Uri $Url -Method Get -TimeoutSec 10 -ErrorAction Stop
        return @{
            Ok = $response.StatusCode -eq 406
            StatusCode = [int]$response.StatusCode
            Error = ""
        }
    } catch {
        $statusCode = 0
        if ($_.Exception.Response -and $_.Exception.Response.StatusCode) {
            $statusCode = [int]$_.Exception.Response.StatusCode
        }
        return @{
            Ok = $statusCode -eq 406
            StatusCode = $statusCode
            Error = $_.Exception.Message
        }
    }
}

function Get-CommandLineForPid {
    param([int]$Pid)
    $process = Get-CimInstance Win32_Process -Filter "ProcessId = $Pid" -ErrorAction SilentlyContinue
    if ($process) { return [string]$process.CommandLine }
    return ""
}

function Start-CodexBridgeServer {
    $logDir = Join-Path $ProjectRoot "runs\service_logs"
    New-Item -ItemType Directory -Force -Path $logDir | Out-Null
    $stdout = Join-Path $logDir "codexbridge-server.out.log"
    $stderr = Join-Path $logDir "codexbridge-server.err.log"
    $arguments = @(
        "-m", "codexbridge.server",
        "--config", $Config,
        "--transport", "http",
        "--host", $HostName,
        "--port", "$Port",
        "--path", $McpPath
    )
    $process = Start-Process -FilePath "python" -ArgumentList $arguments -WorkingDirectory $ProjectRoot -WindowStyle Hidden -RedirectStandardOutput $stdout -RedirectStandardError $stderr -PassThru
    Write-Step "Started CodexBridge server PID $($process.Id)."
}

function Start-CodexBridgeTunnel {
    if (-not (Test-Path $TunnelConfig)) {
        throw "Tunnel config not found: $TunnelConfig"
    }
    $logDir = Join-Path $ProjectRoot "runs\service_logs"
    New-Item -ItemType Directory -Force -Path $logDir | Out-Null
    $stdout = Join-Path $logDir "codexbridge-mcp-tunnel.out.log"
    $stderr = Join-Path $logDir "codexbridge-mcp-tunnel.err.log"
    $arguments = @("tunnel", "--config", $TunnelConfig, "run")
    $process = Start-Process -FilePath "cloudflared" -ArgumentList $arguments -WorkingDirectory $ProjectRoot -WindowStyle Hidden -RedirectStandardOutput $stdout -RedirectStandardError $stderr -PassThru
    Write-Step "Started CodexBridgeMCP tunnel PID $($process.Id)."
}

function Has-CodexBridgeMcpTunnelProcess {
    $escaped = [regex]::Escape($TunnelConfig)
    $matches = Get-CimInstance Win32_Process -Filter "Name = 'cloudflared.exe'" -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -match $escaped }
    return [bool]$matches
}

$localUrl = "http://$HostName`:$Port$McpPath"

if (-not (Test-Path $ProjectRoot)) {
    throw "Project root not found: $ProjectRoot"
}
if (-not (Test-Path (Join-Path $ProjectRoot $Config))) {
    throw "Config file not found: $(Join-Path $ProjectRoot $Config)"
}

Write-Step "Checking local MCP endpoint $localUrl."
$local = Test-McpEndpoint $localUrl
if (-not $local.Ok) {
    Write-Step "Local MCP endpoint is not ready, starting server."
    Start-CodexBridgeServer
    Start-Sleep -Seconds 4
    $local = Test-McpEndpoint $localUrl
}
if (-not $local.Ok) {
    throw "Local MCP endpoint failed. Status=$($local.StatusCode) Error=$($local.Error)"
}
Write-Step "Local MCP endpoint ready. Plain GET returned expected 406."

if (-not $NoTunnel) {
    Write-Step "Checking public MCP endpoint $PublicMcpUrl."
    $public = Test-McpEndpoint $PublicMcpUrl
    if (-not $public.Ok) {
        if (-not (Has-CodexBridgeMcpTunnelProcess)) {
            Write-Step "Public endpoint is not ready and CodexBridgeMCP tunnel process is not running. Starting tunnel."
            Start-CodexBridgeTunnel
            Start-Sleep -Seconds 8
        } else {
            Write-Step "CodexBridgeMCP tunnel process is already running. Rechecking public endpoint."
            Start-Sleep -Seconds 4
        }
        $public = Test-McpEndpoint $PublicMcpUrl
    }
    if (-not $public.Ok) {
        throw "Public MCP endpoint failed. Status=$($public.StatusCode) Error=$($public.Error)"
    }
    Write-Step "Public MCP endpoint ready. Plain GET returned expected 406."
}

Write-Host ""
Write-Host "CodexBridge MCP is ready:"
Write-Host "  Local:  $localUrl"
if (-not $NoTunnel) {
    Write-Host "  Public: $PublicMcpUrl"
}
Write-Host ""
Write-Host "Keep this window output for troubleshooting. Logs are under:"
Write-Host "  $(Join-Path $ProjectRoot 'runs\service_logs')"
