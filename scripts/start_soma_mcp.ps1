param(
    [string]$ProjectRoot = "D:\Github\Soma",
    [string]$Config = "config.yaml",
    [string]$HostName = "127.0.0.1",
    [int]$Port = 8000,
    [string]$McpPath = "/mcp",
    [string]$TunnelConfig = "$env:USERPROFILE\.cloudflared\soma-mcp.yml",
    [string]$PublicMcpUrl = "https://mcp.spaceshipgames.win/mcp",
    [string]$PythonExecutable = "",
    [int]$LocalStartupTimeoutSeconds = 30,
    [int]$TunnelStartupTimeoutSeconds = 30,
    [int]$ProbeIntervalSeconds = 1,
    [switch]$NoTunnel
)

$ErrorActionPreference = "Stop"

function Write-Step {
    param([string]$Message)
    Write-Host "[$(Get-Date -Format 'HH:mm:ss')] $Message"
}

function Get-HttpStatusCodeFromException {
    param([object]$Exception)
    if (-not $Exception) { return 0 }

    $responseProperty = $Exception.PSObject.Properties["Response"]
    if (-not $responseProperty -or -not $responseProperty.Value) { return 0 }
    $statusProperty = $responseProperty.Value.PSObject.Properties["StatusCode"]
    if (-not $statusProperty -or $null -eq $statusProperty.Value) { return 0 }
    try {
        return [int]$statusProperty.Value
    } catch {
        return 0
    }
}

function Test-McpEndpoint {
    param(
        [string]$Url,
        [int]$TimeoutSeconds = 3
    )
    try {
        $response = Invoke-WebRequest -Uri $Url -Method Get -TimeoutSec $TimeoutSeconds -ErrorAction Stop
        return @{
            Ok = $response.StatusCode -eq 406
            StatusCode = [int]$response.StatusCode
            Error = ""
        }
    } catch {
        $statusCode = Get-HttpStatusCodeFromException -Exception $_.Exception
        return @{
            Ok = $statusCode -eq 406
            StatusCode = $statusCode
            Error = $_.Exception.Message
        }
    }
}

function Wait-McpEndpoint {
    param(
        [string]$Url,
        [int]$TimeoutSeconds,
        [int]$IntervalSeconds = 1
    )

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    $last = Test-McpEndpoint -Url $Url
    while (-not $last.Ok -and (Get-Date) -lt $deadline) {
        Start-Sleep -Seconds $IntervalSeconds
        $last = Test-McpEndpoint -Url $Url
    }
    return $last
}

function Get-CommandLineForPid {
    param([int]$Pid)
    $process = Get-CimInstance Win32_Process -Filter "ProcessId = $Pid" -ErrorAction SilentlyContinue
    if ($process) { return [string]$process.CommandLine }
    return ""
}

function Resolve-SomaPython {
    if ($PythonExecutable) {
        if (-not (Test-Path $PythonExecutable -PathType Leaf)) {
            throw "Configured Python executable not found: $PythonExecutable"
        }
        return (Resolve-Path $PythonExecutable).Path
    }

    $venvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
    if (Test-Path $venvPython -PathType Leaf) {
        return (Resolve-Path $venvPython).Path
    }

    $pythonCommand = Get-Command python -ErrorAction SilentlyContinue
    if (-not $pythonCommand) {
        throw "Python was not found. Create $venvPython or pass -PythonExecutable."
    }
    return $pythonCommand.Source
}

function Start-SomaServer {
    $logDir = Join-Path $ProjectRoot "runs\service_logs"
    New-Item -ItemType Directory -Force -Path $logDir | Out-Null
    $stdout = Join-Path $logDir "soma-server.out.log"
    $stderr = Join-Path $logDir "soma-server.err.log"
    $pythonPath = Resolve-SomaPython
    $arguments = @(
        "-m", "soma.server",
        "--config", $Config,
        "--transport", "http",
        "--host", $HostName,
        "--port", "$Port",
        "--path", $McpPath
    )
    Write-Step "Using Python: $pythonPath"
    $process = Start-Process -FilePath $pythonPath -ArgumentList $arguments -WorkingDirectory $ProjectRoot -WindowStyle Hidden -RedirectStandardOutput $stdout -RedirectStandardError $stderr -PassThru
    Write-Step "Started Soma server PID $($process.Id)."
}

function Start-SomaTunnel {
    $manager = Join-Path $ProjectRoot "scripts\manage_soma_service.ps1"
    if (-not (Test-Path -LiteralPath $manager -PathType Leaf)) {
        throw "Soma service manager not found: $manager"
    }
    $powershell = (Get-Command powershell.exe -ErrorAction Stop).Source
    $arguments = @(
        "-NoLogo", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $manager,
        "-Action", "tunnel-start",
        "-ProjectRoot", $ProjectRoot,
        "-Config", $Config,
        "-HostName", $HostName,
        "-Port", "$Port",
        "-McpPath", $McpPath,
        "-TunnelConfig", $TunnelConfig,
        "-PublicMcpUrl", $PublicMcpUrl,
        "-StartupTimeoutSeconds", "$TunnelStartupTimeoutSeconds"
    )
    Write-Step "Reconciling SomaMCP tunnel through the canonical service manager."
    & $powershell @arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Soma service manager tunnel reconciliation failed with exit code $LASTEXITCODE."
    }
}

$localUrl = "http://$HostName`:$Port$McpPath"

if (-not (Test-Path $ProjectRoot)) {
    throw "Project root not found: $ProjectRoot"
}
if (-not (Test-Path (Join-Path $ProjectRoot $Config))) {
    throw "Config file not found: $(Join-Path $ProjectRoot $Config)"
}

Write-Step "Checking local MCP endpoint $localUrl."
$local = Test-McpEndpoint -Url $localUrl
if (-not $local.Ok) {
    Write-Step "Local MCP endpoint is not ready, starting server."
    Start-SomaServer
    Write-Step "Waiting up to $LocalStartupTimeoutSeconds seconds for local MCP readiness."
    $local = Wait-McpEndpoint -Url $localUrl -TimeoutSeconds $LocalStartupTimeoutSeconds -IntervalSeconds $ProbeIntervalSeconds
}
if (-not $local.Ok) {
    throw "Local MCP endpoint failed after $LocalStartupTimeoutSeconds seconds. Status=$($local.StatusCode) Error=$($local.Error)"
}
Write-Step "Local MCP endpoint ready. Plain GET returned expected 406."

if (-not $NoTunnel) {
    Write-Step "Checking public MCP endpoint $PublicMcpUrl."
    $public = Test-McpEndpoint -Url $PublicMcpUrl
    if (-not $public.Ok) {
        Write-Step "Public endpoint is not ready. Asking the canonical service manager to reconcile the tunnel."
        Start-SomaTunnel
        Write-Step "Waiting up to $TunnelStartupTimeoutSeconds seconds for public MCP readiness."
        $public = Wait-McpEndpoint -Url $PublicMcpUrl -TimeoutSeconds $TunnelStartupTimeoutSeconds -IntervalSeconds $ProbeIntervalSeconds
    }
    if (-not $public.Ok) {
        throw "Public MCP endpoint failed after $TunnelStartupTimeoutSeconds seconds. Status=$($public.StatusCode) Error=$($public.Error)"
    }
    Write-Step "Public MCP endpoint ready. Plain GET returned expected 406."
}

Write-Host ""
Write-Host "Soma MCP is ready:"
Write-Host "  Local:  $localUrl"
if (-not $NoTunnel) {
    Write-Host "  Public: $PublicMcpUrl"
}
Write-Host ""
Write-Host "Keep this window output for troubleshooting. Logs are under:"
Write-Host "  $(Join-Path $ProjectRoot 'runs\service_logs')"
