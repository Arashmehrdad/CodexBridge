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
    [string]$ProjectRoot = (Split-Path -Parent $PSScriptRoot),
    [string]$Config = "config.yaml",
    [string]$HostName = "127.0.0.1",
    [int]$Port = 8000,
    [string]$McpPath = "/mcp",
    [string]$TunnelConfig = "$env:USERPROFILE\.cloudflared\codexbridge-mcp.yml",
    [string]$PublicMcpUrl = "https://mcp.spaceshipgames.win/mcp",
    [string]$PythonExecutable = "",
    [string]$Profile = "",
    [switch]$RestartAfterProfileChange,
    [int]$Tail = 80,
    [int]$StartupTimeoutSeconds = 30,
    [int]$ExpectedProcessId = 0
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ProjectRoot = [System.IO.Path]::GetFullPath($ProjectRoot)
$ConfigPath = if ([System.IO.Path]::IsPathRooted($Config)) {
    [System.IO.Path]::GetFullPath($Config)
} else {
    [System.IO.Path]::GetFullPath((Join-Path $ProjectRoot $Config))
}
$TunnelConfig = [System.IO.Path]::GetFullPath($TunnelConfig)
$LogDirectory = Join-Path $ProjectRoot "runs\service_logs"
$ServerStdoutLog = Join-Path $LogDirectory "codexbridge-server.out.log"
$ServerStderrLog = Join-Path $LogDirectory "codexbridge-server.err.log"
$TunnelStdoutLog = Join-Path $LogDirectory "codexbridge-mcp-tunnel.out.log"
$TunnelStderrLog = Join-Path $LogDirectory "codexbridge-mcp-tunnel.err.log"
$ServerPidFile = Join-Path $LogDirectory "codexbridge-server.pid"
$TunnelPidFile = Join-Path $LogDirectory "codexbridge-mcp-tunnel.pid"
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

function Resolve-CodexBridgePython {
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
    return (
        $line -match '(?i)(?:^|\s)-m\s+codexbridge\.server(?:\s|$)' -and
        $line -match "(?i)--port\s+$Port(?:\s|$)" -and
        $line -match "(?i)--path\s+[`\"']?$([regex]::Escape($McpPath))[`\"']?(?:\s|$)"
    )
}

function Test-TunnelProcessIdentity {
    param([object]$Process)
    if (-not $Process -or [string]::IsNullOrWhiteSpace([string]$Process.CommandLine)) {
        return $false
    }
    $name = [string]$Process.Name
    $line = ([string]$Process.CommandLine).Replace('/', '\')
    $expectedConfig = $TunnelConfig.Replace('/', '\')
    return (
        $name -ieq "cloudflared.exe" -and
        $line -match '(?i)\btunnel\b' -and
        $line -match '(?i)\brun\b' -and
        $line.IndexOf($expectedConfig, [System.StringComparison]::OrdinalIgnoreCase) -ge 0
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

function Test-EndpointReadiness {
    param([string]$Url, [int]$TimeoutSeconds = 3)
    $statusCode = 0
    $errorText = ""
    try {
        $response = Invoke-WebRequest -Uri $Url -Method Get -TimeoutSec $TimeoutSeconds -UseBasicParsing -ErrorAction Stop
        $statusCode = [int]$response.StatusCode
    } catch {
        $errorText = $_.Exception.Message
        $responseObject = $_.Exception.Response
        if ($responseObject -and $responseObject.StatusCode) {
            $statusCode = [int]$responseObject.StatusCode
        }
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

function Start-CodexBridgeServer {
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
            Write-Success "CodexBridge is already running (PID $($verified[0].ProcessId)); route returned expected HTTP 406."
            return
        }
        throw "A verified CodexBridge process is running (PID $($verified[0].ProcessId)), but $LocalMcpUrl is not ready. Check logs instead of starting a duplicate."
    }

    $listener = Get-ListenerOwner
    if ($listener) {
        throw "Port $Port is owned by an unrelated process and will not be killed: PID $($listener.ProcessId) $($listener.Name) $($listener.CommandLine)"
    }

    $python = Resolve-CodexBridgePython
    $arguments = @(
        "-m", "codexbridge.server",
        "--config", $ConfigPath,
        "--transport", "http",
        "--host", $HostName,
        "--port", "$Port",
        "--path", $McpPath
    )
    Write-Info "Starting CodexBridge hidden with $python"
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
        throw "CodexBridge failed to become ready within $StartupTimeoutSeconds seconds. Status=$($probe.StatusCode) Error=$($probe.Error)"
    }
    Write-Success "CodexBridge started hidden (PID $($process.Id)). Plain GET returned expected HTTP 406; this is route readiness, not a full MCP handshake."
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
    try {
        Stop-Process -Id $processId -Force -ErrorAction Stop
    } catch {
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

function Stop-CodexBridgeServer {
    $verified = @(Get-VerifiedServerProcesses)
    if ($verified.Count -eq 0) {
        Remove-PidFile -Path $ServerPidFile
        $listener = Get-ListenerOwner
        if ($listener) {
            Write-WarningMessage "Port $Port belongs to an unrelated process and was not touched: PID $($listener.ProcessId) $($listener.Name)"
        } else {
            Write-Info "CodexBridge is already stopped."
        }
        return
    }
    foreach ($process in $verified) {
        Stop-VerifiedProcess -Process $process -InternalAction "elevated-stop-server"
    }
    Remove-PidFile -Path $ServerPidFile
}

function Start-CodexBridgeTunnel {
    Ensure-ControlDirectory
    $verified = @(Get-VerifiedTunnelProcesses)
    if ($verified.Count -gt 0) {
        Write-PidFile -Path $TunnelPidFile -ProcessId ([int]$verified[0].ProcessId)
        Write-Success "Configured Cloudflare tunnel is already running (PID $($verified[0].ProcessId))."
        return
    }
    if (-not (Test-Path -LiteralPath $TunnelConfig -PathType Leaf)) {
        throw "Tunnel config not found: $TunnelConfig"
    }
    $cloudflared = Get-Command cloudflared -ErrorAction SilentlyContinue
    if (-not $cloudflared) {
        throw "cloudflared was not found on PATH."
    }
    $arguments = @("tunnel", "--config", $TunnelConfig, "run")
    Write-Info "Starting Cloudflare tunnel hidden."
    $process = Start-Process -FilePath $cloudflared.Source -ArgumentList $arguments `
        -WorkingDirectory $ProjectRoot -WindowStyle Hidden `
        -RedirectStandardOutput $TunnelStdoutLog -RedirectStandardError $TunnelStderrLog -PassThru
    Write-PidFile -Path $TunnelPidFile -ProcessId $process.Id

    $probe = Wait-EndpointReadiness -Url $PublicMcpUrl -TimeoutSeconds $StartupTimeoutSeconds
    if (-not $probe.Ready) {
        Show-LogTail -Path $TunnelStderrLog -Lines 40
        throw "Tunnel process started (PID $($process.Id)), but the public MCP route was not ready within $StartupTimeoutSeconds seconds."
    }
    Write-Success "Cloudflare tunnel started hidden (PID $($process.Id)); public route returned expected HTTP 406."
}

function Stop-CodexBridgeTunnel {
    $verified = @(Get-VerifiedTunnelProcesses)
    if ($verified.Count -eq 0) {
        Remove-PidFile -Path $TunnelPidFile
        Write-Info "Configured Cloudflare tunnel is already stopped."
        return
    }
    foreach ($process in $verified) {
        Stop-VerifiedProcess -Process $process -InternalAction "elevated-stop-tunnel"
    }
    Remove-PidFile -Path $TunnelPidFile
}

function Show-ServerStatus {
    $verified = @(Get-VerifiedServerProcesses)
    $listener = Get-ListenerOwner
    $probe = Test-EndpointReadiness -Url $LocalMcpUrl
    Write-Host "CodexBridge server"
    Write-Host "  URL:       $LocalMcpUrl"
    Write-Host "  Ready:     $($probe.Ready) (HTTP $($probe.StatusCode); 406 means route ready only)"
    if ($verified.Count -gt 0) {
        Write-Host "  PID:       $($verified[0].ProcessId)"
        Write-Host "  Process:   $($verified[0].Name)"
    } else {
        Write-Host "  PID:       not found"
    }
    if ($listener -and -not (Test-ServerProcessIdentity -Process $listener)) {
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
    if ($verified.Count -gt 0) {
        Write-Host "  PID:       $($verified[0].ProcessId)"
        Write-Host "  Config:    $TunnelConfig"
    } else {
        Write-Host "  PID:       not found"
    }
}

function Show-RecentLogs {
    Show-LogTail -Path $ServerStdoutLog
    Show-LogTail -Path $ServerStderrLog
    Show-LogTail -Path $TunnelStdoutLog
    Show-LogTail -Path $TunnelStderrLog
}

function Follow-ServiceLogs {
    Ensure-ControlDirectory
    foreach ($path in @($ServerStdoutLog, $ServerStderrLog, $TunnelStdoutLog, $TunnelStderrLog)) {
        if (-not (Test-Path -LiteralPath $path)) {
            New-Item -ItemType File -Path $path -Force | Out-Null
        }
    }
    Write-Info "Following server and tunnel logs. Press Ctrl+C to stop following; managed services will keep running."
    Get-Content -Path @($ServerStdoutLog, $ServerStderrLog, $TunnelStdoutLog, $TunnelStderrLog) -Tail $Tail -Wait
}

function Open-ServiceLogDirectory {
    Ensure-ControlDirectory
    Start-Process -FilePath "explorer.exe" -ArgumentList @($LogDirectory) | Out-Null
    Write-Success "Opened $LogDirectory"
}

function Test-CodexBridgeConfig {
    $python = Resolve-CodexBridgePython
    $escaped = $ConfigPath.Replace("\", "\\").Replace("'", "\'")
    $code = "from codexbridge.config import load_config; load_config(r'$escaped'); print('Configuration valid')"
    Push-Location $ProjectRoot
    try {
        & $python -c $code
        if ($LASTEXITCODE -ne 0) { throw "Configuration validation exited with code $LASTEXITCODE." }
    } finally {
        Pop-Location
    }
    Write-Success "Configuration validated: $ConfigPath"
}

function Get-CodexConfiguration {
    $result = [ordered]@{ Executable = ""; Model = "" }
    $insideCodex = $false
    foreach ($line in Get-Content -LiteralPath $ConfigPath) {
        if ($line -match '^codex:\s*$') {
            $insideCodex = $true
            continue
        }
        if ($insideCodex -and $line -match '^\S') { break }
        if ($insideCodex -and $line -match '^\s+executable:\s*["'']?(?<value>.*?)["'']?\s*$') {
            $result.Executable = $Matches.value
        }
        if ($insideCodex -and $line -match '^\s+model:\s*["'']?(?<value>.*?)["'']?\s*$') {
            $result.Model = $Matches.value
        }
    }
    return [pscustomobject]$result
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
    $defaultPattern = '(?m)^(?<indent>[ \t]{2})default_autonomy_profile:\s*(?:["''][^"'']*["'']|[^#\r\n]*?)(?<comment>[ \t]*(?:#.*)?)$'
    if (-not [regex]::IsMatch($block, $defaultPattern)) {
        throw "The default supervisor profile line could not be located in $ConfigPath"
    }
    $replacement = '${indent}default_autonomy_profile: "' + $selectedProfile + '"${comment}'
    $updatedBlock = [regex]::Replace($block, $defaultPattern, $replacement, 1)
    $updatedText = (
        $originalText.Substring(0, $supervisorsMatch.Index) +
        $updatedBlock +
        $originalText.Substring($supervisorsMatch.Index + $supervisorsMatch.Length)
    )

    try {
        Write-ConfigTextAtomically -Content $updatedText -UseUtf8Bom $useUtf8Bom
        Test-CodexBridgeConfig
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
    Stop-CodexBridgeServer
    Start-CodexBridgeServer
}

function Show-SupervisorProfileMenu {
    while ($true) {
        $configuration = Get-SupervisorProfileConfiguration
        Clear-Host
        Write-Host "CodexBridge Supervisor Profile" -ForegroundColor Cyan
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
    Write-Host "CodexBridge diagnostics" -ForegroundColor Cyan
    Write-Host "  Project root:       $ProjectRoot"
    Write-Host "  Config:             $ConfigPath"
    Write-Host "  Python:             $(Resolve-CodexBridgePython)"
    Write-Host "  Local MCP URL:      $LocalMcpUrl"
    Write-Host "  Public MCP URL:     $PublicMcpUrl"
    Write-Host "  Log directory:      $LogDirectory"
    Write-Host "  Server PID file:    $ServerPidFile"
    Write-Host "  Tunnel PID file:    $TunnelPidFile"

    $codex = Get-CodexConfiguration
    Write-Host "  Codex executable:   $($codex.Executable)"
    Write-Host "  Codex model:        $($codex.Model)"
    if ($codex.Executable -and (Test-Path -LiteralPath $codex.Executable -PathType Leaf)) {
        $version = (& $codex.Executable --version 2>&1 | Out-String).Trim()
        Write-Host "  Codex version:      $version"
    } else {
        Write-WarningMessage "Configured Codex executable is missing or unresolved."
    }

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
        "start" { Start-CodexBridgeServer }
        "stop" { Stop-CodexBridgeServer }
        "restart" { Stop-CodexBridgeServer; Start-CodexBridgeServer }
        "status" { Show-ServerStatus }
        "logs" { Show-RecentLogs }
        "follow-logs" { Follow-ServiceLogs }
        "open-logs" { Open-ServiceLogDirectory }
        "validate-config" { Test-CodexBridgeConfig }
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
        "tunnel-start" { Start-CodexBridgeTunnel }
        "tunnel-stop" { Stop-CodexBridgeTunnel }
        "tunnel-restart" { Stop-CodexBridgeTunnel; Start-CodexBridgeTunnel }
        "tunnel-status" { Show-TunnelStatus }
        "start-all" { Start-CodexBridgeServer; Start-CodexBridgeTunnel }
        "stop-all" { Stop-CodexBridgeTunnel; Stop-CodexBridgeServer }
        "elevated-stop-server" { Invoke-InternalElevatedStop -Kind "server" }
        "elevated-stop-tunnel" { Invoke-InternalElevatedStop -Kind "tunnel" }
        default { throw "Unknown action: $SelectedAction" }
    }
}

function Show-ServiceMenu {
    $items = [ordered]@{
        "1" = @("Start server hidden", "start")
        "2" = @("Stop server safely", "stop")
        "3" = @("Restart server hidden", "restart")
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

        Write-Host "CodexBridge Service Controller" -ForegroundColor Cyan
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
