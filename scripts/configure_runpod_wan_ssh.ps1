param(
    [string]$RunPodUser = "fhxnfase3ezwmn-644113c6",
    [string]$IdentityFile = "$env:USERPROFILE\.ssh\runpod_wan22"
)

$ErrorActionPreference = "Stop"

$sshDirectory = Join-Path $env:USERPROFILE ".ssh"
$configPath = Join-Path $sshDirectory "config"
$startMarker = "# BEGIN CODEXBRIDGE RUNPOD WAN"
$endMarker = "# END CODEXBRIDGE RUNPOD WAN"

if (-not (Test-Path -LiteralPath $IdentityFile -PathType Leaf)) {
    throw "SSH private key was not found: $IdentityFile"
}

New-Item -ItemType Directory -Path $sshDirectory -Force | Out-Null

$normalizedIdentityFile = $IdentityFile.Replace("\", "/")
$managedBlock = @"
$startMarker
Host runpod-wan
    HostName ssh.runpod.io
    User $RunPodUser
    IdentityFile $normalizedIdentityFile
    IdentitiesOnly yes
    ServerAliveInterval 30
    ServerAliveCountMax 3
$endMarker
"@

$existing = if (Test-Path -LiteralPath $configPath -PathType Leaf) {
    [System.IO.File]::ReadAllText($configPath)
} else {
    ""
}

$escapedStart = [regex]::Escape($startMarker)
$escapedEnd = [regex]::Escape($endMarker)
$managedPattern = "(?ms)^$escapedStart\r?\n.*?^$escapedEnd\r?\n?"
$cleaned = [regex]::Replace($existing, $managedPattern, "").TrimEnd()

$newContent = if ([string]::IsNullOrWhiteSpace($cleaned)) {
    "$managedBlock`r`n"
} else {
    "$cleaned`r`n`r`n$managedBlock`r`n"
}

[System.IO.File]::WriteAllText(
    $configPath,
    $newContent,
    [System.Text.UTF8Encoding]::new($false)
)

Write-Host "Configured SSH alias 'runpod-wan' in $configPath"
Write-Host "Run this once to verify and accept the host key:"
Write-Host "ssh -o StrictHostKeyChecking=ask runpod-wan true"
