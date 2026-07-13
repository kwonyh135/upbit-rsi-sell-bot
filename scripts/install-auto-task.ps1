$ErrorActionPreference = "Stop"

$TaskName = "HuntBot-Auto-5m"
$RepoRoot = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $RepoRoot ".venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $Python)) {
    throw "Python executable not found: $Python"
}

$Action = New-ScheduledTaskAction `
    -Execute $Python `
    -Argument "-m huntbot run-auto-5m --live" `
    -WorkingDirectory $RepoRoot

$Trigger = New-ScheduledTaskTrigger -AtLogOn
$Settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -RestartCount 10 `
    -RestartInterval (New-TimeSpan -Minutes 1) `
    -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit (New-TimeSpan -Seconds 0)

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $Action `
    -Trigger $Trigger `
    -Settings $Settings `
    -Description "KRW-HUNT 5-minute unattended auto-trading bot" `
    -Force

Write-Host "Installed scheduled task: $TaskName"
Write-Host "Keep the laptop connected to AC power and disable sleep while plugged in."
