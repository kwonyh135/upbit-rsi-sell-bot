$ErrorActionPreference = "Stop"

if (Get-ScheduledTask -TaskName "HuntBot-Auto-5m" -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName "HuntBot-Auto-5m" -Confirm:$false
    Write-Host "Removed scheduled task: HuntBot-Auto-5m"
} else {
    Write-Host "Scheduled task is not installed: HuntBot-Auto-5m"
}
