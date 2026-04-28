param(
    [ValidateSet("chrome", "edge")]
    [string]$Browser = "chrome",
    [int]$Port = 9222,
    [string]$UserDataDir = "",
    [string]$ChatUrl = "https://chatgpt.com",
    [switch]$KillExisting,
    [int]$WaitSeconds = 20
)

$ErrorActionPreference = "Stop"

function Get-BrowserInfo {
    param([string]$Name)

    if ($Name -eq "edge") {
        return @{
            ProcessName = "msedge"
            Paths = @(
                "$env:ProgramFiles\Microsoft\Edge\Application\msedge.exe",
                "${env:ProgramFiles(x86)}\Microsoft\Edge\Application\msedge.exe"
            )
        }
    }

    return @{
        ProcessName = "chrome"
        Paths = @(
            "$env:ProgramFiles\Google\Chrome\Application\chrome.exe",
            "${env:ProgramFiles(x86)}\Google\Chrome\Application\chrome.exe"
        )
    }
}

function Test-ChatUrl {
    param([string]$Url)

    $uri = [Uri]$Url
    if ($uri.Scheme -ne "https" -or $uri.Host -ne "chatgpt.com" -or (-not $uri.AbsolutePath.StartsWith("/c/"))) {
        throw "ChatUrl must be a real ChatGPT conversation URL like https://chatgpt.com/c/..."
    }
}

function Get-CdpVersion {
    param([int]$Port)

    $endpoint = "http://127.0.0.1:$Port/json/version"
    try {
        return Invoke-RestMethod -Uri $endpoint -TimeoutSec 2
    } catch {
        return $null
    }
}

function Wait-CdpVersion {
    param(
        [int]$Port,
        [int]$WaitSeconds
    )

    $deadline = (Get-Date).AddSeconds($WaitSeconds)
    do {
        $version = Get-CdpVersion -Port $Port
        if ($version) {
            return $version
        }
        Start-Sleep -Milliseconds 500
    } while ((Get-Date) -lt $deadline)

    return $null
}

function Write-Troubleshooting {
    param(
        [string]$Browser,
        [int]$Port
    )

    Write-Error @"
Could not verify a local Chromium CDP endpoint at http://127.0.0.1:$Port/json/version.

Troubleshooting:
- The browser may already be running without remote debugging, so it ignored the new launch flags.
- Modern Chrome/Edge builds may refuse remote debugging on the default profile; use -UserDataDir and sign in once there.
- Close all $Browser windows first, or rerun this script with -KillExisting.
- Prefer a dedicated pulse profile with -UserDataDir to avoid touching your normal browser session.
- Verify manually with: curl.exe http://127.0.0.1:$Port/json/version
- Edge may be blocked by the RemoteDebuggingAllowed enterprise policy.
"@
}

Test-ChatUrl -Url $ChatUrl

$browserInfo = Get-BrowserInfo -Name $Browser
$browserPath = $browserInfo.Paths | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
if (-not $browserPath) {
    throw "Could not find $Browser. Install it from the official vendor or pass a supported browser."
}

$existing = Get-CdpVersion -Port $Port
if ($existing -and (-not $UserDataDir)) {
    Write-Host "CDP endpoint already available: http://127.0.0.1:$Port"
    Write-Host "Browser: $($existing.Browser)"
    if ($existing.'Protocol-Version') {
        Write-Host "Protocol-Version: $($existing.'Protocol-Version')"
    }
    exit 0
} elseif ($existing -and $UserDataDir) {
    throw "CDP endpoint http://127.0.0.1:$Port is already in use. Stop that browser or choose a different -Port for the dedicated -UserDataDir launch."
}

if ($KillExisting) {
    Get-Process -Name $browserInfo.ProcessName -ErrorAction SilentlyContinue | Stop-Process -Force
    Start-Sleep -Seconds 2
}

$arguments = @(
    "--remote-debugging-port=$Port",
    "--remote-debugging-address=127.0.0.1",
    "--no-first-run",
    "--new-window"
)

if ($UserDataDir) {
    New-Item -ItemType Directory -Force -Path $UserDataDir | Out-Null
    $arguments += "--user-data-dir=$UserDataDir"
}

$arguments += $ChatUrl

Start-Process -FilePath $browserPath -ArgumentList $arguments

$version = Wait-CdpVersion -Port $Port -WaitSeconds $WaitSeconds
if (-not $version) {
    Write-Troubleshooting -Browser $Browser -Port $Port
    exit 1
}

Write-Host "CDP endpoint ready: http://127.0.0.1:$Port"
Write-Host "Version endpoint: http://127.0.0.1:$Port/json/version"
Write-Host "Browser: $($version.Browser)"
if ($version.'Protocol-Version') {
    Write-Host "Protocol-Version: $($version.'Protocol-Version')"
}
exit 0
