# Removes the Reachwise start-up tasks. Run as Administrator.
foreach ($n in "Reachwise Server", "Reachwise Tunnel", "Reachwise Lock Screen") {
    Stop-ScheduledTask -TaskName $n -ErrorAction SilentlyContinue
    Unregister-ScheduledTask -TaskName $n -Confirm:$false -ErrorAction SilentlyContinue
    Write-Host "Removed: $n"
}
