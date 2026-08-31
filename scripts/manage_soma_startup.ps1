[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [ValidateSet("install", "uninstall", "status", "run", "ensure-research-map")]
    [string]$Action = "status",
    [string]$TaskName = "Soma MCP Startup",
    [string]$ResearchMapWatchTaskName = "Soma Research Map Backend Watch",
    [string]$ProjectRoot = "",
    [ValidateRange(0, 600)]
    [int]$StartupDelaySeconds = 20,
    [ValidateRange(1, 60)]
    [int]$ResearchMapWatchIntervalMinutes = 1,
    [ValidateRange(15, 600)]
    [int]$StartupTimeoutSeconds = 120
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($ProjectRoot)) {
    if ([string]::IsNullOrWhiteSpace($PSCommandPath)) {
        throw "Unable to resolve this script path. Pass -ProjectRoot explicitly."
    }
    $ProjectRoot = Split-Path -Parent (Split-Path -Parent $PSCommandPath)
}
$ProjectRoot = [System.IO.Path]::GetFullPath($ProjectRoot)
$ControllerPath = Join-Path $ProjectRoot "scripts\manage_soma_service.ps1"
$LogDirectory = Join-Path $ProjectRoot "runs\service_logs"
$StartupLog = Join-Path $LogDirectory "soma-startup-task.log"
$CurrentUser = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name

function Assert-InstallationInputs {
    if (-not (Test-Path -LiteralPath $ProjectRoot -PathType Container)) {
        throw "Project root not found: $ProjectRoot"
    }
    if (-not (Test-Path -LiteralPath $ControllerPath -PathType Leaf)) {
        throw "Soma service controller not found: $ControllerPath"
    }
}

function Write-StartupLog {
    param([string]$Message)
    New-Item -ItemType Directory -Force -Path $LogDirectory | Out-Null
    Add-Content -LiteralPath $StartupLog -Encoding utf8 -Value "[$([DateTimeOffset]::Now.ToString('o'))] $Message"
}

function Test-ResearchMapBackendPort {
    $client = New-Object System.Net.Sockets.TcpClient
    try {
        $connect = $client.ConnectAsync("127.0.0.1", 6379)
        if (-not $connect.Wait(1000)) {
            return $false
        }
        return $client.Connected
    }
    catch {
        return $false
    }
    finally {
        $client.Dispose()
    }
}

function Ensure-ResearchMapBackend {
    if (Test-ResearchMapBackendPort) {
        return
    }
    $wsl = Get-Command wsl.exe -ErrorAction SilentlyContinue
    if (-not $wsl) {
        Write-StartupLog "Research Map backend warning: wsl.exe is unavailable."
        return
    }
    try {
        $serviceOutput = @(
            & $wsl.Source -d Ubuntu -u root -- systemctl start soma-falkordb.service 2>&1
        )
        if ($LASTEXITCODE -ne 0) {
            throw "WSL systemd start failed with exit code $LASTEXITCODE. $($serviceOutput -join ' ')"
        }
        $deadline = (Get-Date).AddSeconds(30)
        do {
            if (Test-ResearchMapBackendPort) {
                Write-StartupLog "Research Map WSL FalkorDB is ready on 127.0.0.1:6379."
                return
            }
            Start-Sleep -Milliseconds 500
        } while ((Get-Date) -lt $deadline)
        Write-StartupLog "Research Map backend warning: WSL FalkorDB did not expose 127.0.0.1:6379 within 30 seconds."
    }
    catch {
        Write-StartupLog "Research Map backend warning: $($_.Exception.Message)"
    }
}

function Invoke-HiddenStartup {
    Assert-InstallationInputs
    Write-StartupLog "Startup task invoked for $CurrentUser."
    try {
        Ensure-ResearchMapBackend
        $controllerOutput = @(
            & $ControllerPath -Action start-all -ProjectRoot $ProjectRoot `
                -StartupTimeoutSeconds $StartupTimeoutSeconds *>&1
        )
        foreach ($entry in $controllerOutput) {
            $text = [string]$entry
            if (-not [string]::IsNullOrWhiteSpace($text)) {
                Write-StartupLog "controller: $text"
            }
        }
        Write-StartupLog "Soma server and Cloudflare tunnel are ready."
    }
    catch {
        Write-StartupLog "Startup failed: $($_.Exception.Message)"
        throw
    }
}

function Get-StartupTask {
    return Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
}

function Get-ResearchMapWatchTask {
    return Get-ScheduledTask -TaskName $ResearchMapWatchTaskName -ErrorAction SilentlyContinue
}

function Install-ResearchMapWatchTask {
    Assert-InstallationInputs
    $powershell = Get-Command powershell.exe -ErrorAction Stop
    $scriptPath = [System.IO.Path]::GetFullPath($PSCommandPath)
    $arguments = @(
        "-NoProfile"
        "-NonInteractive"
        "-WindowStyle Hidden"
        "-ExecutionPolicy Bypass"
        "-File `"$scriptPath`""
        "-Action ensure-research-map"
        "-ProjectRoot `"$ProjectRoot`""
    ) -join " "
    $taskAction = New-ScheduledTaskAction -Execute $powershell.Source `
        -Argument $arguments -WorkingDirectory $ProjectRoot
    $trigger = New-ScheduledTaskTrigger -Once `
        -At (Get-Date).AddMinutes($ResearchMapWatchIntervalMinutes) `
        -RepetitionInterval (New-TimeSpan -Minutes $ResearchMapWatchIntervalMinutes) `
        -RepetitionDuration (New-TimeSpan -Days 3650)
    $principal = New-ScheduledTaskPrincipal -UserId $CurrentUser `
        -LogonType Interactive -RunLevel Limited
    $settings = New-ScheduledTaskSettingsSet -Hidden -StartWhenAvailable `
        -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
        -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 2)
    Register-ScheduledTask -TaskName $ResearchMapWatchTaskName -Action $taskAction `
        -Trigger $trigger -Principal $principal -Settings $settings -Force `
        -Description "Restarts the WSL Research Map FalkorDB backend when localhost:6379 is unavailable." | Out-Null
    if (-not (Get-ResearchMapWatchTask)) {
        throw "Research Map watchdog registration completed without a readable task record."
    }
}

function Uninstall-ResearchMapWatchTask {
    $task = Get-ResearchMapWatchTask
    if ($task) {
        Unregister-ScheduledTask -TaskName $ResearchMapWatchTaskName -Confirm:$false
        Write-Host "Removed Research Map watchdog task '$ResearchMapWatchTaskName'."
    }
}

function Install-StartupTask {
    Assert-InstallationInputs
    $powershell = Get-Command powershell.exe -ErrorAction Stop
    $scriptPath = [System.IO.Path]::GetFullPath($PSCommandPath)
    $arguments = @(
        "-NoProfile"
        "-NonInteractive"
        "-WindowStyle Hidden"
        "-ExecutionPolicy Bypass"
        "-File `"$scriptPath`""
        "-Action run"
        "-ProjectRoot `"$ProjectRoot`""
        "-StartupTimeoutSeconds $StartupTimeoutSeconds"
    ) -join " "

    $taskAction = New-ScheduledTaskAction -Execute $powershell.Source `
        -Argument $arguments -WorkingDirectory $ProjectRoot
    $trigger = New-ScheduledTaskTrigger -AtLogOn -User $CurrentUser
    if ($StartupDelaySeconds -gt 0) {
        $trigger.Delay = "PT$($StartupDelaySeconds)S"
    }
    $principal = New-ScheduledTaskPrincipal -UserId $CurrentUser `
        -LogonType Interactive -RunLevel Limited
    $settings = New-ScheduledTaskSettingsSet -Hidden -StartWhenAvailable `
        -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
        -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 5)

    Register-ScheduledTask -TaskName $TaskName -Action $taskAction -Trigger $trigger `
        -Principal $principal -Settings $settings -Force `
        -Description "Starts the Soma MCP server and Cloudflare tunnel hidden at user logon." | Out-Null

    $task = Get-StartupTask
    if (-not $task) {
        throw "Scheduled task registration completed without a readable task record."
    }
    Install-ResearchMapWatchTask
    Write-Host "Installed hidden startup task '$TaskName' for $CurrentUser."
    Write-Host "Installed hidden Research Map watchdog '$ResearchMapWatchTaskName' every $ResearchMapWatchIntervalMinutes minute(s)."
    Write-Host "Logon delay: $StartupDelaySeconds seconds"
    Write-Host "Startup log: $StartupLog"
}

function Uninstall-StartupTask {
    $task = Get-StartupTask
    if ($task) {
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
        Write-Host "Removed startup task '$TaskName'."
    } else {
        Write-Host "Startup task '$TaskName' is not installed."
    }
    Uninstall-ResearchMapWatchTask
}

function Show-StartupTaskStatus {
    $task = Get-StartupTask
    $watch = Get-ResearchMapWatchTask
    $info = if ($task) { Get-ScheduledTaskInfo -TaskName $TaskName } else { $null }
    $watchInfo = if ($watch) { Get-ScheduledTaskInfo -TaskName $ResearchMapWatchTaskName } else { $null }
    [pscustomobject]@{
        installed = [bool]$task
        task_name = $TaskName
        state = if ($task) { [string]$task.State } else { "" }
        hidden = if ($task) { [bool]$task.Settings.Hidden } else { $false }
        current_user = $CurrentUser
        execute = if ($task) { [string]$task.Actions[0].Execute } else { "" }
        arguments = if ($task) { [string]$task.Actions[0].Arguments } else { "" }
        last_run_time = if ($info) { $info.LastRunTime } else { $null }
        last_task_result = if ($info) { $info.LastTaskResult } else { $null }
        next_run_time = if ($info) { $info.NextRunTime } else { $null }
        research_map_watch_installed = [bool]$watch
        research_map_watch_task_name = $ResearchMapWatchTaskName
        research_map_watch_state = if ($watch) { [string]$watch.State } else { "" }
        research_map_watch_hidden = if ($watch) { [bool]$watch.Settings.Hidden } else { $false }
        research_map_watch_last_run_time = if ($watchInfo) { $watchInfo.LastRunTime } else { $null }
        research_map_watch_last_task_result = if ($watchInfo) { $watchInfo.LastTaskResult } else { $null }
        research_map_watch_next_run_time = if ($watchInfo) { $watchInfo.NextRunTime } else { $null }
        startup_log = $StartupLog
    } | ConvertTo-Json -Depth 4
}

switch ($Action) {
    "install" { Install-StartupTask }
    "uninstall" { Uninstall-StartupTask }
    "status" { Show-StartupTaskStatus }
    "run" { Invoke-HiddenStartup }
    "ensure-research-map" { Ensure-ResearchMapBackend }
    default { throw "Unknown action: $Action" }
}
