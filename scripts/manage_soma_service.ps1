[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [ValidateSet(
        "menu", "start", "stop", "restart", "status", "logs", "follow-logs",
        "open-logs", "validate-config", "diagnostics", "profiles", "profile-status",
        "profile-set", "tunnel-start", "tunnel-stop", "tunnel-restart", "tunnel-status",
        "start-all", "stop-all", "elevated-stop-server", "elevated-stop-tunnel"
    )]
    [string]$Action = "menu",
    [string]$ProjectRoot = "",
    [string]$Config = "config.yaml",
    [string]$HostName = "127.0.0.1",
    [int]$Port = 8000,
    [string]$McpPath = "/mcp",
    [string]$TunnelConfig = "$env:USERPROFILE\.cloudflared\soma-mcp.yml",
    [string]$PublicMcpUrl = "https://mcp.spaceshipgames.win/mcp",
    [string]$PythonExecutable = "",
    [string]$Profile = "",
    [switch]$RestartAfterProfileChange,
    [int]$Tail = 80,
    [int]$StartupTimeoutSeconds = 30,
    [ValidateRange(1, 9223372036854775807)]
    [long]$MaxLogBytes = 26214400,
    [ValidateRange(1, 100)]
    [int]$MaxArchivedLogs = 4,
    [int]$ExpectedProcessId = 0
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($ProjectRoot)) {
    if ([string]::IsNullOrWhiteSpace($PSCommandPath)) {
        throw "Unable to resolve the service controller script path. Pass -ProjectRoot explicitly."
    }
    $scriptDirectory = Split-Path -Parent $PSCommandPath
    $ProjectRoot = Split-Path -Parent $scriptDirectory
}
$ProjectRoot = [System.IO.Path]::GetFullPath($ProjectRoot)
$ConfigPath = if ([System.IO.Path]::IsPathRooted($Config)) {
    [System.IO.Path]::GetFullPath($Config)
} else {
    [System.IO.Path]::GetFullPath((Join-Path $ProjectRoot $Config))
}
$TunnelConfig = [System.IO.Path]::GetFullPath($TunnelConfig)
$LogDirectory = Join-Path $ProjectRoot "runs\service_logs"
$ServerStdoutLog = Join-Path $LogDirectory "soma-server.out.log"
$ServerStderrLog = Join-Path $LogDirectory "soma-server.err.log"
$TunnelStdoutLog = Join-Path $LogDirectory "soma-mcp-tunnel.out.log"
$TunnelStderrLog = Join-Path $LogDirectory "soma-mcp-tunnel.err.log"
$ServerPidFile = Join-Path $LogDirectory "soma-server.pid"
$TunnelPidFile = Join-Path $LogDirectory "soma-mcp-tunnel.pid"
$TunnelIdentityFile = Join-Path $LogDirectory "soma-mcp-tunnel.identity.json"
$TunnelProtocol = "http2"
$LocalMcpUrl = "http://$HostName`:$Port$McpPath"

function Write-Info {
    param([string]$Message)
    Write-Host "[INFO] $Message" -ForegroundColor Cyan
}

function Write-Success {
    param([string]$Message)
    Write-Host "[OK]   $Message" -ForegroundColor Green
}

function Write-WarningMessage {
    param([string]$Message)
    Write-Host "[WARN] $Message" -ForegroundColor Yellow
}

function Ensure-ControlDirectory {
    New-Item -ItemType Directory -Force -Path $LogDirectory | Out-Null
}

function Get-ServiceLogPaths {
    $paths = @($ServerStdoutLog, $ServerStderrLog)
    $paths += @(Get-TunnelLogPaths)
    return @($paths)
}

function Invoke-ServiceLogRollover {
    param([Parameter(Mandatory = $true)][string]$Path)

    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { return }
    $item = Get-Item -LiteralPath $Path -ErrorAction Stop
    if ([long]$item.Length -lt $MaxLogBytes) { return }

    $timestamp = (Get-Date).ToUniversalTime().ToString("yyyyMMddTHHmmssfffZ")
    $archivePath = "$Path.$timestamp.archive"
    Move-Item -LiteralPath $Path -Destination $archivePath -ErrorAction Stop
    Write-Info "Rolled over $($item.Name) at $($item.Length) bytes to $(Split-Path -Leaf $archivePath)."

    $directory = Split-Path -Parent $Path
    $leaf = Split-Path -Leaf $Path
    $archives = @(
        Get-ChildItem -LiteralPath $directory -File -Filter "$leaf.*.archive" -ErrorAction SilentlyContinue |
            Sort-Object LastWriteTimeUtc -Descending
    )
    if ($archives.Count -gt $MaxArchivedLogs) {
        $archives |
            Select-Object -Skip $MaxArchivedLogs |
            Remove-Item -Force -ErrorAction Stop
    }
}

function Show-ServiceLogGrowth {
    Write-Host "  Log rollover limit: $MaxLogBytes bytes; retained archives per stream: $MaxArchivedLogs"
    foreach ($path in Get-ServiceLogPaths) {
        if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { continue }
        $item = Get-Item -LiteralPath $path -ErrorAction SilentlyContinue
        if (-not $item) { continue }
        Write-Host "  Log size:           $($item.Name) = $($item.Length) bytes"
        if ([long]$item.Length -ge $MaxLogBytes) {
            Write-WarningMessage "$($item.Name) exceeds the rollover limit. It remains untouched while its service is active and will roll over before the next managed start."
        }
    }
}

function Resolve-SomaPython {
    if ($PythonExecutable) {
        if (-not (Test-Path -LiteralPath $PythonExecutable -PathType Leaf)) {
            throw "Configured Python executable not found: $PythonExecutable"
        }
        return [System.IO.Path]::GetFullPath($PythonExecutable)
    }

    $venvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
    if (Test-Path -LiteralPath $venvPython -PathType Leaf) {
        return [System.IO.Path]::GetFullPath($venvPython)
    }

    $python = Get-Command python -ErrorAction SilentlyContinue
    if (-not $python) {
        throw "Python was not found. Create .venv or pass -PythonExecutable."
    }
    return $python.Source
}

function Get-ProcessInfo {
    param([int]$ProcessId)
    if ($ProcessId -le 0) { return $null }
    return Get-CimInstance Win32_Process -Filter "ProcessId = $ProcessId" -ErrorAction SilentlyContinue
}

function Test-ServerProcessIdentity {
    param([object]$Process)
    if (-not $Process -or [string]::IsNullOrWhiteSpace([string]$Process.CommandLine)) {
        return $false
    }
    $line = [string]$Process.CommandLine
    $pathPattern = '(?i)--path\s+["\x27]?' + [regex]::Escape($McpPath) + '["\x27]?(?:\s|$)'
    return (
        $line -match '(?i)(?:^|\s)-m\s+soma\.server(?:\s|$)' -and
        $line -match "(?i)--port\s+$Port(?:\s|$)" -and
        $line -match $pathPattern
    )
}

function Get-ProcessCreationStamp {
    param([object]$Process)
    if (-not $Process) { return "" }
    $property = $Process.PSObject.Properties["CreationDate"]
    if (-not $property -or $null -eq $property.Value) { return "" }
    try {
        return ([datetime]$property.Value).ToUniversalTime().ToString("o")
    } catch {
        return ""
    }
}

function Get-TunnelOwnershipRecord {
    if (-not (Test-Path -LiteralPath $TunnelIdentityFile -PathType Leaf)) { return $null }
    try {
        $record = Get-Content -LiteralPath $TunnelIdentityFile -Raw -ErrorAction Stop | ConvertFrom-Json -ErrorAction Stop
        foreach ($required in @("schema_version", "process_id", "process_creation_utc", "tunnel_config", "protocol")) {
            if (-not $record.PSObject.Properties[$required]) { return $null }
        }
        if ([string]$record.schema_version -ne "soma.cloudflared.ownership.v1") { return $null }
        return $record
    } catch {
        return $null
    }
}

function Remove-TunnelOwnershipRecord {
    Remove-Item -LiteralPath $TunnelIdentityFile -Force -ErrorAction SilentlyContinue
}

function Test-TunnelOwnershipRecordMatchesProcess {
    param([object]$Process, [object]$Record = $null)
    if (-not $Process -or [string]$Process.Name -ine "cloudflared.exe") { return $false }
    if (-not $Record) { $Record = Get-TunnelOwnershipRecord }
    if (-not $Record) { return $false }
    if ([int]$Record.process_id -ne [int]$Process.ProcessId) { return $false }
    $recordConfig = [System.IO.Path]::GetFullPath([string]$Record.tunnel_config)
    if (-not $recordConfig.Equals($TunnelConfig, [System.StringComparison]::OrdinalIgnoreCase)) { return $false }
    try {
        $processCreationProperty = $Process.PSObject.Properties["CreationDate"]
        if (-not $processCreationProperty -or $null -eq $processCreationProperty.Value) { return $false }
        $processCreation = ([datetime]$processCreationProperty.Value).ToUniversalTime()
        $recordCreation = ([datetime]$Record.process_creation_utc).ToUniversalTime()
        return $processCreation.Ticks -eq $recordCreation.Ticks
    } catch {
        return $false
    }
}

function Write-TunnelOwnershipRecord {
    param(
        [object]$Process,
        [string]$ExecutablePath,
        [string]$LaunchId,
        [string]$LaunchOrigin,
        [string]$StdoutLog = "",
        [string]$StderrLog = ""
    )
    Ensure-ControlDirectory
    $current = Get-ProcessInfo -ProcessId ([int]$Process.ProcessId)
    if (-not $current) { throw "Tunnel process PID $($Process.ProcessId) exited before ownership could be recorded." }
    $creation = Get-ProcessCreationStamp -Process $current
    if ([string]::IsNullOrWhiteSpace($creation)) {
        throw "Unable to record creation identity for tunnel PID $($Process.ProcessId)."
    }
    $record = [ordered]@{
        schema_version = "soma.cloudflared.ownership.v1"
        process_id = [int]$current.ProcessId
        process_creation_utc = $creation
        executable_path = [System.IO.Path]::GetFullPath($ExecutablePath)
        tunnel_config = $TunnelConfig
        protocol = $TunnelProtocol
        launch_id = $LaunchId
        launch_origin = $LaunchOrigin
        stdout_log = $StdoutLog
        stderr_log = $StderrLog
        recorded_at_utc = (Get-Date).ToUniversalTime().ToString("o")
    }
    $temporary = "$TunnelIdentityFile.tmp"
    $record | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $temporary -Encoding UTF8
    Move-Item -LiteralPath $temporary -Destination $TunnelIdentityFile -Force
}

function Get-TunnelLogPaths {
    $record = Get-TunnelOwnershipRecord
    if ($record) {
        $paths = @()
        foreach ($propertyName in @("stdout_log", "stderr_log")) {
            $property = $record.PSObject.Properties[$propertyName]
            if ($property -and -not [string]::IsNullOrWhiteSpace([string]$property.Value)) {
                $paths += [string]$property.Value
            }
        }
        if ($paths.Count -gt 0) { return @($paths) }
    }
    return @($TunnelStdoutLog, $TunnelStderrLog)
}

function Test-TunnelProcessIdentity {
    param([object]$Process)
    if (-not $Process -or [string]$Process.Name -ine "cloudflared.exe") {
        return $false
    }
    if (-not [string]::IsNullOrWhiteSpace([string]$Process.CommandLine)) {
        $line = ([string]$Process.CommandLine).Replace('/', '\')
        $expectedConfig = $TunnelConfig.Replace('/', '\')
        return (
            $line -match '(?i)\btunnel\b' -and
            $line -match '(?i)\brun\b' -and
            $line.IndexOf($expectedConfig, [System.StringComparison]::OrdinalIgnoreCase) -ge 0
        )
    }
    return Test-TunnelOwnershipRecordMatchesProcess -Process $Process
}

function Test-TunnelProcessUsesConfiguredProtocol {
    param([object]$Process)
    if (-not (Test-TunnelProcessIdentity -Process $Process)) { return $false }
    if (-not [string]::IsNullOrWhiteSpace([string]$Process.CommandLine)) {
        return ([string]$Process.CommandLine -match '(?i)--protocol(?:=|\s+)http2(?:\s|$)')
    }
    $record = Get-TunnelOwnershipRecord
    return (
        (Test-TunnelOwnershipRecordMatchesProcess -Process $Process -Record $record) -and
        [string]$record.protocol -ieq $TunnelProtocol
    )
}

function Read-PidFile {
    param([string]$Path)
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { return 0 }
    $raw = (Get-Content -LiteralPath $Path -Raw -ErrorAction SilentlyContinue).Trim()
    $value = 0
    if ([int]::TryParse($raw, [ref]$value) -and $value -gt 0) {
        return $value
    }
    Remove-Item -LiteralPath $Path -Force -ErrorAction SilentlyContinue
    return 0
}

function Write-PidFile {
    param([string]$Path, [int]$ProcessId)
    Ensure-ControlDirectory
    Set-Content -LiteralPath $Path -Value $ProcessId -Encoding ascii
}

function Remove-PidFile {
    param([string]$Path)
    Remove-Item -LiteralPath $Path -Force -ErrorAction SilentlyContinue
}

function Get-ListenerOwner {
    $connection = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
        Select-Object -First 1
    if (-not $connection) { return $null }
    return Get-ProcessInfo -ProcessId ([int]$connection.OwningProcess)
}

function Get-VerifiedServerProcesses {
    $found = @{}
    $storedId = Read-PidFile -Path $ServerPidFile
    if ($storedId -gt 0) {
        $stored = Get-ProcessInfo -ProcessId $storedId
        if (Test-ServerProcessIdentity -Process $stored) {
            $found[[string]$storedId] = $stored
        } else {
            Remove-PidFile -Path $ServerPidFile
        }
    }

    $listener = Get-ListenerOwner
    if ($listener -and (Test-ServerProcessIdentity -Process $listener)) {
        $found[[string]$listener.ProcessId] = $listener
    }

    if ($found.Count -eq 0) {
        Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
            Where-Object { $_.Name -in @("python.exe", "pythonw.exe") } |
            ForEach-Object {
                if (Test-ServerProcessIdentity -Process $_) {
                    $found[[string]$_.ProcessId] = $_
                }
            }
    }
    return @($found.Values)
}

function Get-VerifiedTunnelProcesses {
    $found = @{}
    $storedId = Read-PidFile -Path $TunnelPidFile
    if ($storedId -gt 0) {
        $stored = Get-ProcessInfo -ProcessId $storedId
        if (Test-TunnelProcessIdentity -Process $stored) {
            $found[[string]$storedId] = $stored
        } else {
            Remove-PidFile -Path $TunnelPidFile
        }
    }

    Get-CimInstance Win32_Process -Filter "Name = 'cloudflared.exe'" -ErrorAction SilentlyContinue |
        ForEach-Object {
            if (Test-TunnelProcessIdentity -Process $_) {
                $found[[string]$_.ProcessId] = $_
            }
        }
    return @($found.Values)
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

function Test-EndpointReadiness {
    param([string]$Url, [int]$TimeoutSeconds = 3)
    $statusCode = 0
    $errorText = ""
    try {
        $response = Invoke-WebRequest -Uri $Url -Method Get -TimeoutSec $TimeoutSeconds -UseBasicParsing -ErrorAction Stop
        $statusCode = [int]$response.StatusCode
    } catch {
        $errorText = $_.Exception.Message
        $statusCode = Get-HttpStatusCodeFromException -Exception $_.Exception
    }
    return [pscustomobject]@{
        Ready = ($statusCode -eq 406)
        StatusCode = $statusCode
        Error = $errorText
    }
}

function Wait-EndpointReadiness {
    param([string]$Url, [int]$TimeoutSeconds)
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    do {
        $result = Test-EndpointReadiness -Url $Url
        if ($result.Ready) { return $result }
        Start-Sleep -Milliseconds 500
    } while ((Get-Date) -lt $deadline)
    return $result
}

function Show-LogTail {
    param([string]$Path, [int]$Lines = $Tail)
    Write-Host ""
    Write-Host "--- $Path ---" -ForegroundColor DarkCyan
    if (Test-Path -LiteralPath $Path -PathType Leaf) {
        Get-Content -LiteralPath $Path -Tail $Lines -ErrorAction SilentlyContinue
    } else {
        Write-Host "Log file does not exist yet."
    }
}

function Start-SomaServer {
    Ensure-ControlDirectory
    if (-not (Test-Path -LiteralPath $ProjectRoot -PathType Container)) {
        throw "Project root not found: $ProjectRoot"
    }
    if (-not (Test-Path -LiteralPath $ConfigPath -PathType Leaf)) {
        throw "Config file not found: $ConfigPath"
    }

    $verified = @(Get-VerifiedServerProcesses)
    $probe = Test-EndpointReadiness -Url $LocalMcpUrl
    if ($verified.Count -gt 0) {
        Write-PidFile -Path $ServerPidFile -ProcessId ([int]$verified[0].ProcessId)
        if ($probe.Ready) {
            Write-Success "Soma is already running (PID $($verified[0].ProcessId)); route returned expected HTTP 406."
            return
        }
        throw "A verified Soma process is running (PID $($verified[0].ProcessId)), but $LocalMcpUrl is not ready. Check logs instead of starting a duplicate."
    }

    $listener = Get-ListenerOwner
    if ($listener) {
        throw "Port $Port is owned by an unrelated process and will not be killed: PID $($listener.ProcessId) $($listener.Name) $($listener.CommandLine)"
    }

    Invoke-ServiceLogRollover -Path $ServerStdoutLog
    Invoke-ServiceLogRollover -Path $ServerStderrLog

    $python = Resolve-SomaPython
    $arguments = @(
        "-m", "soma.server",
        "--config", $ConfigPath,
        "--transport", "http",
        "--host", $HostName,
        "--port", "$Port",
        "--path", $McpPath
    )
    Write-Info "Starting Soma hidden with $python"
    $process = Start-Process -FilePath $python -ArgumentList $arguments -WorkingDirectory $ProjectRoot `
        -WindowStyle Hidden -RedirectStandardOutput $ServerStdoutLog `
        -RedirectStandardError $ServerStderrLog -PassThru
    Write-PidFile -Path $ServerPidFile -ProcessId $process.Id

    $probe = Wait-EndpointReadiness -Url $LocalMcpUrl -TimeoutSeconds $StartupTimeoutSeconds
    if (-not $probe.Ready) {
        if (-not (Get-ProcessInfo -ProcessId $process.Id)) {
            Remove-PidFile -Path $ServerPidFile
        }
        Show-LogTail -Path $ServerStderrLog -Lines 40
        throw "Soma failed to become ready within $StartupTimeoutSeconds seconds. Status=$($probe.StatusCode) Error=$($probe.Error)"
    }
    Write-Success "Soma started hidden (PID $($process.Id)). Plain GET returned expected HTTP 406; this is route readiness, not a full MCP handshake."
}

function ConvertTo-PowerShellLiteral {
    param([string]$Value)
    return "'" + $Value.Replace("'", "''") + "'"
}

function Invoke-ElevatedStop {
    param([string]$InternalAction, [int]$ProcessId)
    $scriptLiteral = ConvertTo-PowerShellLiteral -Value $PSCommandPath
    $rootLiteral = ConvertTo-PowerShellLiteral -Value $ProjectRoot
    $configLiteral = ConvertTo-PowerShellLiteral -Value $ConfigPath
    $hostLiteral = ConvertTo-PowerShellLiteral -Value $HostName
    $pathLiteral = ConvertTo-PowerShellLiteral -Value $McpPath
    $tunnelLiteral = ConvertTo-PowerShellLiteral -Value $TunnelConfig
    $command = "& $scriptLiteral -Action $InternalAction -ProjectRoot $rootLiteral -Config $configLiteral -HostName $hostLiteral -Port $Port -McpPath $pathLiteral -TunnelConfig $tunnelLiteral -ExpectedProcessId $ProcessId"
    $encoded = [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($command))
    Write-WarningMessage "Stopping PID $ProcessId requires administrator permission. A bounded UAC prompt will open."
    $elevated = Start-Process -FilePath "powershell.exe" -Verb RunAs -Wait -PassThru `
        -ArgumentList @("-NoProfile", "-ExecutionPolicy", "Bypass", "-EncodedCommand", $encoded)
    if ($elevated.ExitCode -ne 0) {
        throw "Elevated stop failed or was cancelled for PID $ProcessId (exit $($elevated.ExitCode))."
    }
}

function Stop-VerifiedProcess {
    param([object]$Process, [string]$InternalAction)
    $processId = [int]$Process.ProcessId
    $current = Get-ProcessInfo -ProcessId $processId
    if (-not $current) {
        Write-Success "Verified process PID $processId already exited during coordinated stop."
        return
    }

    $identityMatches = switch ($InternalAction) {
        "elevated-stop-server" { Test-ServerProcessIdentity -Process $current }
        "elevated-stop-tunnel" { Test-TunnelProcessIdentity -Process $current }
        default { $false }
    }
    if (-not $identityMatches) {
        throw "PID $processId no longer matches the verified process identity. Nothing was stopped."
    }

    try {
        Stop-Process -Id $processId -Force -ErrorAction Stop
    } catch {
        if (-not (Get-ProcessInfo -ProcessId $processId)) {
            Write-Success "Verified process PID $processId exited during coordinated stop."
            return
        }
        if ($_.Exception.Message -match '(?i)access.*denied|denied.*access') {
            Invoke-ElevatedStop -InternalAction $InternalAction -ProcessId $processId
        } else {
            throw
        }
    }
    Start-Sleep -Milliseconds 500
    if (Get-ProcessInfo -ProcessId $processId) {
        throw "Verified process PID $processId is still running after the stop request."
    }
    Write-Success "Stopped verified process PID $processId."
}

function Stop-SomaServer {
    $verified = @(Get-VerifiedServerProcesses)
    if ($verified.Count -eq 0) {
        Remove-PidFile -Path $ServerPidFile
        $listener = Get-ListenerOwner
        if ($listener) {
            Write-WarningMessage "Port $Port belongs to an unrelated process and was not touched: PID $($listener.ProcessId) $($listener.Name)"
        } else {
            Write-Info "Soma is already stopped."
        }
        return
    }
    foreach ($process in $verified) {
        Stop-VerifiedProcess -Process $process -InternalAction "elevated-stop-server"
    }
    Remove-PidFile -Path $ServerPidFile
}

function Restart-SomaServer {
    Write-Info "Restarting Soma server only; the Cloudflare tunnel will remain unchanged."
    Stop-SomaServer
    Start-SomaServer
}

function Start-SomaTunnel {
    Ensure-ControlDirectory
    if (-not (Test-Path -LiteralPath $TunnelConfig -PathType Leaf)) {
        throw "Tunnel config not found: $TunnelConfig"
    }
    $cloudflared = Get-Command cloudflared -ErrorAction SilentlyContinue
    if (-not $cloudflared) {
        throw "cloudflared was not found on PATH."
    }

    $verified = @(Get-VerifiedTunnelProcesses)
    $probe = Test-EndpointReadiness -Url $PublicMcpUrl
    $configured = @($verified | Where-Object { Test-TunnelProcessUsesConfiguredProtocol -Process $_ })

    if ($probe.Ready -and $configured.Count -gt 0) {
        $owner = Get-TunnelOwnershipRecord
        $keeper = $null
        if ($owner) {
            $keeper = $configured | Where-Object { Test-TunnelOwnershipRecordMatchesProcess -Process $_ -Record $owner } | Select-Object -First 1
        }
        if (-not $keeper) {
            $keeper = $configured | Sort-Object ProcessId -Descending | Select-Object -First 1
        }
        foreach ($process in $verified) {
            if ([int]$process.ProcessId -ne [int]$keeper.ProcessId) {
                Stop-VerifiedProcess -Process $process -InternalAction "elevated-stop-tunnel"
            }
        }
        $executablePath = if (-not [string]::IsNullOrWhiteSpace([string]$keeper.ExecutablePath)) {
            [string]$keeper.ExecutablePath
        } else {
            $cloudflared.Source
        }
        Write-TunnelOwnershipRecord -Process $keeper -ExecutablePath $executablePath `
            -LaunchId "adopted-$($keeper.ProcessId)" -LaunchOrigin "verified-existing"
        Write-PidFile -Path $TunnelPidFile -ProcessId ([int]$keeper.ProcessId)
        Write-Success "Configured HTTP/2 Cloudflare tunnel is already healthy (PID $($keeper.ProcessId))."
        return
    }

    if ($probe.Ready -and $verified.Count -eq 0) {
        Write-WarningMessage "Public MCP route is healthy but no local tunnel can be verified. Refusing to spawn a duplicate tunnel."
        return
    }

    if ($verified.Count -gt 0) {
        $reason = if ($probe.Ready) { "managed tunnel is not pinned to HTTP/2" } else { "public route is unhealthy" }
        Write-WarningMessage "Replacing configured Cloudflare tunnel because $reason."
        foreach ($process in $verified) {
            Stop-VerifiedProcess -Process $process -InternalAction "elevated-stop-tunnel"
        }
        Remove-PidFile -Path $TunnelPidFile
        Remove-TunnelOwnershipRecord
    }

    $launchId = (Get-Date).ToUniversalTime().ToString("yyyyMMddTHHmmssfffZ") + "-" + ([guid]::NewGuid().ToString("N").Substring(0, 8))
    $stdoutLog = Join-Path $LogDirectory "soma-mcp-tunnel.$launchId.out.log"
    $stderrLog = Join-Path $LogDirectory "soma-mcp-tunnel.$launchId.err.log"
    $arguments = @("tunnel", "--protocol", $TunnelProtocol, "--config", $TunnelConfig, "run")
    Write-Info "Starting Cloudflare tunnel hidden with protocol $TunnelProtocol."
    $process = Start-Process -FilePath $cloudflared.Source -ArgumentList $arguments `
        -WorkingDirectory $ProjectRoot -WindowStyle Hidden `
        -RedirectStandardOutput $stdoutLog -RedirectStandardError $stderrLog -PassThru
    $processInfo = Get-ProcessInfo -ProcessId $process.Id
    Write-TunnelOwnershipRecord -Process $processInfo -ExecutablePath $cloudflared.Source `
        -LaunchId $launchId -LaunchOrigin "manage_soma_service" -StdoutLog $stdoutLog -StderrLog $stderrLog
    Write-PidFile -Path $TunnelPidFile -ProcessId $process.Id

    $probe = Wait-EndpointReadiness -Url $PublicMcpUrl -TimeoutSeconds $StartupTimeoutSeconds
    if (-not $probe.Ready) {
        Show-LogTail -Path $stderrLog -Lines 40
        $current = Get-ProcessInfo -ProcessId $process.Id
        if ($current -and (Test-TunnelProcessIdentity -Process $current)) {
            Stop-VerifiedProcess -Process $current -InternalAction "elevated-stop-tunnel"
        }
        Remove-PidFile -Path $TunnelPidFile
        Remove-TunnelOwnershipRecord
        throw "Tunnel process started (PID $($process.Id)), but the public MCP route was not ready within $StartupTimeoutSeconds seconds."
    }
    Write-Success "Cloudflare tunnel started hidden (PID $($process.Id), protocol $TunnelProtocol); public route returned expected HTTP 406."
}

function Stop-SomaTunnel {
    $verified = @(Get-VerifiedTunnelProcesses)
    if ($verified.Count -eq 0) {
        Remove-PidFile -Path $TunnelPidFile
        Remove-TunnelOwnershipRecord
        Write-Info "Configured Cloudflare tunnel is already stopped."
        return
    }
    foreach ($process in $verified) {
        Stop-VerifiedProcess -Process $process -InternalAction "elevated-stop-tunnel"
    }
    Remove-PidFile -Path $TunnelPidFile
    Remove-TunnelOwnershipRecord
}

function Show-ServerStatus {
    $verified = @(Get-VerifiedServerProcesses)
    $listener = Get-ListenerOwner
    $listenerIsServer = $listener -and (Test-ServerProcessIdentity -Process $listener)
    $probe = Test-EndpointReadiness -Url $LocalMcpUrl
    Write-Host "Soma server"
    Write-Host "  URL:       $LocalMcpUrl"
    Write-Host "  Ready:     $($probe.Ready) (HTTP $($probe.StatusCode); 406 means route ready only)"
    if ($listenerIsServer) {
        Write-Host "  PID:       $($listener.ProcessId)"
        Write-Host "  PID role:  listener"
        Write-Host "  Process:   $($listener.Name)"
    } elseif ($verified.Count -gt 0) {
        Write-Host "  PID:       $($verified[0].ProcessId)"
        Write-Host "  PID role:  verified process; listener absent"
        Write-Host "  Process:   $($verified[0].Name)"
    } else {
        Write-Host "  PID:       not found"
    }
    if ($verified.Count -gt 0) {
        $verifiedProcessIds = @(
            $verified |
                ForEach-Object { [int]$_.ProcessId } |
                Sort-Object -Unique
        )
        Write-Host "  Verified PIDs: $($verifiedProcessIds -join ', ')"
    }
    if ($listener -and -not $listenerIsServer) {
        Write-WarningMessage "Port $Port conflict: PID $($listener.ProcessId) $($listener.Name) is unrelated and will not be killed."
        Write-Host "  Command:   $($listener.CommandLine)"
    }
}

function Show-TunnelStatus {
    $verified = @(Get-VerifiedTunnelProcesses)
    $probe = Test-EndpointReadiness -Url $PublicMcpUrl
    Write-Host "Cloudflare tunnel"
    Write-Host "  URL:       $PublicMcpUrl"
    Write-Host "  Ready:     $($probe.Ready) (HTTP $($probe.StatusCode))"
    Write-Host "  Protocol:  $TunnelProtocol"
    if ($verified.Count -gt 0) {
        Write-Host "  PID:       $($verified[0].ProcessId)"
        Write-Host "  Config:    $TunnelConfig"
        $verifiedIds = @($verified | ForEach-Object { [int]$_.ProcessId } | Sort-Object -Unique)
        Write-Host "  Verified PIDs: $($verifiedIds -join ', ')"
    } else {
        Write-Host "  PID:       not found"
    }
    Write-Host "  Ownership: $TunnelIdentityFile"
}

function Show-RecentLogs {
    foreach ($path in Get-ServiceLogPaths) {
        Show-LogTail -Path $path
    }
}

function Follow-ServiceLogs {
    Ensure-ControlDirectory
    $paths = @(Get-ServiceLogPaths)
    foreach ($path in $paths) {
        if (-not (Test-Path -LiteralPath $path)) {
            New-Item -ItemType File -Path $path -Force | Out-Null
        }
    }
    Write-Info "Following server and current tunnel logs. Press Ctrl+C to stop following; managed services will keep running."
    Get-Content -Path $paths -Tail $Tail -Wait
}

function Open-ServiceLogDirectory {
    Ensure-ControlDirectory
    Start-Process -FilePath "explorer.exe" -ArgumentList @($LogDirectory) | Out-Null
    Write-Success "Opened $LogDirectory"
}

function Test-SomaConfig {
    $python = Resolve-SomaPython
    $escaped = $ConfigPath.Replace("\", "\\").Replace("'", "\'")
    $code = "from soma.config import load_config; load_config(r'$escaped'); print('Configuration valid')"
    Push-Location $ProjectRoot
    try {
        & $python -c $code
        if ($LASTEXITCODE -ne 0) { throw "Configuration validation exited with code $LASTEXITCODE." }
    } finally {
        Pop-Location
    }
    Write-Success "Configuration validated: $ConfigPath"
}

function Get-SupervisorProfileConfiguration {
    if (-not (Test-Path -LiteralPath $ConfigPath -PathType Leaf)) {
        throw "Config file not found: $ConfigPath"
    }

    $insideSupervisors = $false
    $insideProfiles = $false
    $defaultProfile = ""
    $profiles = [System.Collections.Generic.List[string]]::new()

    foreach ($line in Get-Content -LiteralPath $ConfigPath) {
        if (-not $insideSupervisors) {
            if ($line -match '^supervisors:\s*(?:#.*)?$') {
                $insideSupervisors = $true
            }
            continue
        }
        if ($line -match '^\S') { break }

        if ($line -match '^\s{2}default_autonomy_profile:\s*["'']?(?<value>[A-Za-z0-9_.-]+)["'']?\s*(?:#.*)?$') {
            $defaultProfile = $Matches.value
            continue
        }
        if ($line -match '^\s{2}autonomy_profiles:\s*(?:#.*)?$') {
            $insideProfiles = $true
            continue
        }
        if ($insideProfiles) {
            if ($line -match '^\s{4}(?<name>[A-Za-z0-9_.-]+):\s*(?:#.*)?$') {
                $profiles.Add($Matches.name)
                continue
            }
            if ($line -match '^\s{2}\S') {
                $insideProfiles = $false
            }
        }
    }

    if ([string]::IsNullOrWhiteSpace($defaultProfile)) {
        throw "supervisors.default_autonomy_profile was not found in $ConfigPath"
    }
    if ($profiles.Count -eq 0) {
        throw "supervisors.autonomy_profiles does not define any profiles in $ConfigPath"
    }

    return [pscustomobject]@{
        DefaultProfile = $defaultProfile
        AvailableProfiles = @($profiles)
    }
}

function Write-ConfigTextAtomically {
    param([string]$Content, [bool]$UseUtf8Bom)
    $temporaryPath = "$ConfigPath.tmp.$([guid]::NewGuid().ToString('N'))"
    $encoding = [System.Text.UTF8Encoding]::new($UseUtf8Bom)
    try {
        [System.IO.File]::WriteAllText($temporaryPath, $Content, $encoding)
        Move-Item -LiteralPath $temporaryPath -Destination $ConfigPath -Force
    } finally {
        Remove-Item -LiteralPath $temporaryPath -Force -ErrorAction SilentlyContinue
    }
}

function Set-SupervisorProfile {
    param([Parameter(Mandatory = $true)][string]$Name)

    $configuration = Get-SupervisorProfileConfiguration
    $resolvedProfile = @($configuration.AvailableProfiles | Where-Object { $_ -ieq $Name } | Select-Object -First 1)
    if ($resolvedProfile.Count -eq 0) {
        throw "Unknown supervisor profile '$Name'. Available profiles: $($configuration.AvailableProfiles -join ', ')"
    }
    $selectedProfile = [string]$resolvedProfile[0]
    if ($configuration.DefaultProfile -ceq $selectedProfile) {
        Write-Info "Supervisor profile is already '$selectedProfile'."
        return $false
    }

    $originalBytes = [System.IO.File]::ReadAllBytes($ConfigPath)
    $useUtf8Bom = (
        $originalBytes.Length -ge 3 -and
        $originalBytes[0] -eq 0xEF -and
        $originalBytes[1] -eq 0xBB -and
        $originalBytes[2] -eq 0xBF
    )
    $originalText = [System.IO.File]::ReadAllText($ConfigPath)
    $supervisorsPattern = '(?m)^supervisors:[ \t]*(?:#.*)?\r?\n(?<body>(?:^[ \t]+[^\r\n]*(?:\r?\n|$))*)'
    $supervisorsMatch = [regex]::Match($originalText, $supervisorsPattern)
    if (-not $supervisorsMatch.Success) {
        throw "The supervisors configuration block could not be located in $ConfigPath"
    }

    $block = $supervisorsMatch.Value
    $defaultPattern = '(?m)^(?<indent>[ \t]{2})default_autonomy_profile:[ \t]*["\x27]?[A-Za-z0-9_.-]+["\x27]?(?<comment>[ \t]*(?:#[^\r\n]*)?)(?<carriage>\r?)$'
    if (-not [regex]::IsMatch($block, $defaultPattern)) {
        throw "The default supervisor profile line could not be located in $ConfigPath"
    }
    $replacement = '${indent}default_autonomy_profile: "' + $selectedProfile + '"${comment}${carriage}'
    $updatedBlock = [regex]::Replace($block, $defaultPattern, $replacement, 1)
    $updatedText = (
        $originalText.Substring(0, $supervisorsMatch.Index) +
        $updatedBlock +
        $originalText.Substring($supervisorsMatch.Index + $supervisorsMatch.Length)
    )

    try {
        Write-ConfigTextAtomically -Content $updatedText -UseUtf8Bom $useUtf8Bom
        Test-SomaConfig
    } catch {
        Write-ConfigTextAtomically -Content $originalText -UseUtf8Bom $useUtf8Bom
        throw "Profile update was rolled back because validation failed: $($_.Exception.Message)"
    }

    Write-Success "Supervisor profile changed from '$($configuration.DefaultProfile)' to '$selectedProfile'."
    return $true
}

function Show-SupervisorProfileStatus {
    $configuration = Get-SupervisorProfileConfiguration
    Write-Host "Supervisor autonomy profiles" -ForegroundColor Cyan
    Write-Host "  Current profile:    $($configuration.DefaultProfile)"
    Write-Host "  Available profiles: $($configuration.AvailableProfiles -join ', ')"
}

function Restart-RunningServerForProfileChange {
    $running = @(Get-VerifiedServerProcesses)
    if ($running.Count -eq 0) {
        Write-Info "The server is stopped; the selected profile will apply on the next start."
        return
    }
    Write-Info "Restarting the running server so the profile change takes effect."
    Restart-SomaServer
}

function Show-SupervisorProfileMenu {
    while ($true) {
        $configuration = Get-SupervisorProfileConfiguration
        Clear-Host
        Write-Host "Soma Supervisor Profile" -ForegroundColor Cyan
        Write-Host "Current: $($configuration.DefaultProfile)"
        Write-Host ""

        $profileItems = [ordered]@{}
        $index = 1
        foreach ($profileName in $configuration.AvailableProfiles) {
            $marker = if ($profileName -ceq $configuration.DefaultProfile) { " [active]" } else { "" }
            $profileItems[[string]$index] = $profileName
            Write-Host ("{0,2}. {1}{2}" -f $index, $profileName, $marker)
            $index += 1
        }
        Write-Host " 0. Back to service menu"
        Write-Host ""

        $choice = Read-Host "Choose a profile"
        if ($choice -eq "0") { return }
        if (-not $profileItems.Contains($choice)) {
            Write-WarningMessage "Invalid selection."
            Start-Sleep -Seconds 1
            continue
        }

        try {
            $changed = Set-SupervisorProfile -Name $profileItems[$choice]
            if ($changed) {
                $running = @(Get-VerifiedServerProcesses)
                if ($running.Count -gt 0) {
                    $restartChoice = Read-Host "Restart the running server now to apply it? [Y/n]"
                    if ([string]::IsNullOrWhiteSpace($restartChoice) -or $restartChoice -match '^(?i)y(?:es)?$') {
                        Restart-RunningServerForProfileChange
                    } else {
                        Write-WarningMessage "The configured profile changed, but the running server still uses the previous profile until restart."
                    }
                } else {
                    Write-Info "The selected profile will apply on the next server start."
                }
            }
        } catch {
            Write-Host "[ERROR] $($_.Exception.Message)" -ForegroundColor Red
        }
        Write-Host ""
        [void](Read-Host "Press Enter to continue")
    }
}

function Show-Diagnostics {
    Write-Host "Soma diagnostics" -ForegroundColor Cyan
    Write-Host "  Project root:       $ProjectRoot"
    Write-Host "  Config:             $ConfigPath"
    Write-Host "  Python:             $(Resolve-SomaPython)"
    Write-Host "  Local MCP URL:      $LocalMcpUrl"
    Write-Host "  Public MCP URL:     $PublicMcpUrl"
    Write-Host "  Log directory:      $LogDirectory"
    Write-Host "  Server PID file:    $ServerPidFile"
    Write-Host "  Tunnel PID file:    $TunnelPidFile"
    Write-Host "  Tunnel ownership:   $TunnelIdentityFile"
    Write-Host "  Tunnel protocol:    $TunnelProtocol"
    Show-ServiceLogGrowth

    $listener = Get-ListenerOwner
    if ($listener) {
        Write-Host "  Port owner PID:     $($listener.ProcessId)"
        Write-Host "  Port owner name:    $($listener.Name)"
        Write-Host "  Port owner command: $($listener.CommandLine)"
    } else {
        Write-Host "  Port owner:         none"
    }
    Write-Host ""
    Show-ServerStatus
    Write-Host ""
    Show-TunnelStatus
}

function Invoke-InternalElevatedStop {
    param([string]$Kind)
    if ($ExpectedProcessId -le 0) { throw "ExpectedProcessId is required." }
    $process = Get-ProcessInfo -ProcessId $ExpectedProcessId
    $valid = if ($Kind -eq "server") {
        Test-ServerProcessIdentity -Process $process
    } else {
        Test-TunnelProcessIdentity -Process $process
    }
    if (-not $valid) {
        throw "PID $ExpectedProcessId no longer matches the expected $Kind process identity. Nothing was stopped."
    }
    Stop-Process -Id $ExpectedProcessId -Force -ErrorAction Stop
}

function Invoke-ServiceAction {
    param([string]$SelectedAction)
    switch ($SelectedAction) {
        "start" { Start-SomaServer }
        "stop" { Stop-SomaServer }
        "restart" { Restart-SomaServer }
        "status" { Show-ServerStatus }
        "logs" { Show-RecentLogs }
        "follow-logs" { Follow-ServiceLogs }
        "open-logs" { Open-ServiceLogDirectory }
        "validate-config" { Test-SomaConfig }
        "diagnostics" { Show-Diagnostics }
        "profiles" { Show-SupervisorProfileMenu }
        "profile-status" { Show-SupervisorProfileStatus }
        "profile-set" {
            if ([string]::IsNullOrWhiteSpace($Profile)) {
                throw "-Profile is required for the profile-set action."
            }
            $changed = Set-SupervisorProfile -Name $Profile
            if ($changed -and $RestartAfterProfileChange) {
                Restart-RunningServerForProfileChange
            } elseif ($changed -and @(Get-VerifiedServerProcesses).Count -gt 0) {
                Write-WarningMessage "Restart the server to apply the new profile, or pass -RestartAfterProfileChange."
            }
        }
        "tunnel-start" { Start-SomaTunnel }
        "tunnel-stop" { Stop-SomaTunnel }
        "tunnel-restart" { Stop-SomaTunnel; Start-SomaTunnel }
        "tunnel-status" { Show-TunnelStatus }
        "start-all" { Start-SomaServer; Start-SomaTunnel }
        "stop-all" { Stop-SomaTunnel; Stop-SomaServer }
        "elevated-stop-server" { Invoke-InternalElevatedStop -Kind "server" }
        "elevated-stop-tunnel" { Invoke-InternalElevatedStop -Kind "tunnel" }
        default { throw "Unknown action: $SelectedAction" }
    }
}

function Show-ServiceMenu {
    $items = [ordered]@{
        "1" = @("Start server hidden (tunnel unchanged)", "start")
        "2" = @("Stop server safely (tunnel unchanged)", "stop")
        "3" = @("Restart server hidden (tunnel unchanged)", "restart")
        "4" = @("Server status/readiness", "status")
        "5" = @("Select supervisor profile", "profiles")
        "6" = @("Validate config.yaml", "validate-config")
        "7" = @("Diagnostics", "diagnostics")
        "8" = @("Show recent logs", "logs")
        "9" = @("Follow logs", "follow-logs")
        "10" = @("Open log directory", "open-logs")
        "11" = @("Start Cloudflare tunnel", "tunnel-start")
        "12" = @("Stop Cloudflare tunnel", "tunnel-stop")
        "13" = @("Restart Cloudflare tunnel", "tunnel-restart")
        "14" = @("Tunnel status", "tunnel-status")
        "15" = @("Start server and tunnel", "start-all")
        "16" = @("Stop tunnel and server", "stop-all")
    }
    $sections = @(
        [pscustomobject]@{ Title = "Server and policy"; Keys = @("1", "2", "3", "4", "5", "6", "7") },
        [pscustomobject]@{ Title = "Logs"; Keys = @("8", "9", "10") },
        [pscustomobject]@{ Title = "Cloudflare tunnel"; Keys = @("11", "12", "13", "14") },
        [pscustomobject]@{ Title = "Combined"; Keys = @("15", "16") }
    )

    while ($true) {
        Clear-Host
        $profileConfiguration = Get-SupervisorProfileConfiguration
        $serverState = if (@(Get-VerifiedServerProcesses).Count -gt 0) { "running" } else { "stopped" }
        $tunnelState = if (@(Get-VerifiedTunnelProcesses).Count -gt 0) { "running" } else { "stopped" }

        Write-Host "Soma Service Controller" -ForegroundColor Cyan
        Write-Host "Processes stay hidden and keep running when this menu exits."
        Write-Host ""
        Write-Host "  Profile: $($profileConfiguration.DefaultProfile)" -ForegroundColor Green
        Write-Host "  Server:  $serverState    Tunnel: $tunnelState"

        foreach ($section in $sections) {
            Write-Host ""
            Write-Host $section.Title -ForegroundColor DarkCyan
            foreach ($key in $section.Keys) {
                Write-Host ("{0,2}. {1}" -f $key, $items[$key][0])
            }
        }
        Write-Host ""
        Write-Host " 0. Exit menu"
        Write-Host ""
        $choice = Read-Host "Choose an action"
        if ($choice -eq "0") { return }
        if (-not $items.Contains($choice)) {
            Write-WarningMessage "Invalid selection."
            Start-Sleep -Seconds 1
            continue
        }
        try {
            Invoke-ServiceAction -SelectedAction $items[$choice][1]
        } catch {
            Write-Host "[ERROR] $($_.Exception.Message)" -ForegroundColor Red
        }
        if ($items[$choice][1] -ne "profiles") {
            Write-Host ""
            [void](Read-Host "Press Enter to return to the menu")
        }
    }
}

try {
    if ($Action -eq "menu") {
        Show-ServiceMenu
    } else {
        Invoke-ServiceAction -SelectedAction $Action
    }
    exit 0
} catch {
    Write-Host "[ERROR] $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}
