[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [ValidateSet("install", "uninstall", "status", "run")]
    [string]$Action = "status",
    [string]$TaskName = "Soma MCP Startup",
    [string]$ProjectRoot = "",
    [ValidateRange(0, 600)]
    [int]$StartupDelaySeconds = 20,
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
    Write-Host "Installed hidden startup task '$TaskName' for $CurrentUser."
    Write-Host "Logon delay: $StartupDelaySeconds seconds"
    Write-Host "Startup log: $StartupLog"
}

function Uninstall-StartupTask {
    $task = Get-StartupTask
    if (-not $task) {
        Write-Host "Startup task '$TaskName' is not installed."
        return
    }
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
    Write-Host "Removed startup task '$TaskName'."
}

function Show-StartupTaskStatus {
    $task = Get-StartupTask
    if (-not $task) {
        [pscustomobject]@{
            installed = $false
            task_name = $TaskName
            current_user = $CurrentUser
        } | ConvertTo-Json
        return
    }
    $info = Get-ScheduledTaskInfo -TaskName $TaskName
    [pscustomobject]@{
        installed = $true
        task_name = $TaskName
        state = [string]$task.State
        hidden = [bool]$task.Settings.Hidden
        current_user = $CurrentUser
        execute = [string]$task.Actions[0].Execute
        arguments = [string]$task.Actions[0].Arguments
        last_run_time = $info.LastRunTime
        last_task_result = $info.LastTaskResult
        next_run_time = $info.NextRunTime
        startup_log = $StartupLog
    } | ConvertTo-Json -Depth 4
}

switch ($Action) {
    "install" { Install-StartupTask }
    "uninstall" { Uninstall-StartupTask }
    "status" { Show-StartupTaskStatus }
    "run" { Invoke-HiddenStartup }
    default { throw "Unknown action: $Action" }
}
