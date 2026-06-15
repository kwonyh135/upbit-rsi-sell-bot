[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$HostName,

    [Parameter(Mandatory = $true)]
    [string]$KeyPath,

    [string]$UserName = "ubuntu",
    [string]$RemoteRoot = "/opt/huntbot/shared",
    [string]$Destination
)

$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
if (-not $Destination) {
    $Destination = Join-Path $projectRoot "data\remote-runtime"
}

$key = (Resolve-Path -LiteralPath $KeyPath).Path
$destinationPath = [System.IO.Path]::GetFullPath($Destination)
$stagingPath = "$destinationPath.staging-$PID"
$backupPath = "$destinationPath.backup-$PID"
$remote = "$UserName@$HostName"

if (Test-Path -LiteralPath $stagingPath) {
    Remove-Item -LiteralPath $stagingPath -Recurse -Force
}

New-Item -ItemType Directory -Path (Join-Path $stagingPath "state") -Force | Out-Null
New-Item -ItemType Directory -Path (Join-Path $stagingPath "logs") -Force | Out-Null

try {
    & scp -i $key `
        "${remote}:$RemoteRoot/data/state/auto-trading.json" `
        (Join-Path $stagingPath "state\auto-trading.json")
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to download auto-trading.json (scp exit $LASTEXITCODE)."
    }

    & scp -i $key `
        "${remote}:$RemoteRoot/logs/huntbot-auto.log*" `
        (Join-Path $stagingPath "logs")
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to download huntbot logs (scp exit $LASTEXITCODE)."
    }

    $state = Get-Content `
        -LiteralPath (Join-Path $stagingPath "state\auto-trading.json") `
        -Raw | ConvertFrom-Json

    if (Test-Path -LiteralPath $destinationPath) {
        Move-Item -LiteralPath $destinationPath -Destination $backupPath
    }
    try {
        Move-Item -LiteralPath $stagingPath -Destination $destinationPath
    }
    catch {
        if (Test-Path -LiteralPath $backupPath) {
            Move-Item -LiteralPath $backupPath -Destination $destinationPath
        }
        throw
    }

    if (Test-Path -LiteralPath $backupPath) {
        Remove-Item -LiteralPath $backupPath -Recurse -Force
    }

    $downloadedAt = Get-Date
    Write-Host "AWS runtime downloaded: $destinationPath"
    Write-Host "Downloaded at: $($downloadedAt.ToString('yyyy-MM-dd HH:mm:ss'))"
    Write-Host "Remote phase: $($state.phase)"
}
finally {
    if (Test-Path -LiteralPath $stagingPath) {
        Remove-Item -LiteralPath $stagingPath -Recurse -Force
    }
}
