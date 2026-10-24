# Quick check: are the tasks running, does the server answer, is the public address up?
$domain = (Select-String -Path "$PSScriptRoot\settings.bat" -Pattern "^set NGROK_DOMAIN=(.+)$").Matches[0].Groups[1].Value.Trim()
$port = (Select-String -Path "$PSScriptRoot\settings.bat" -Pattern "^set PORT=(.+)$").Matches[0].Groups[1].Value.Trim()
foreach ($n in "Reachwise Server", "Reachwise Tunnel") {
    $t = Get-ScheduledTask -TaskName $n -ErrorAction SilentlyContinue
    if ($t) { Write-Host "$n task: $($t.State)" } else { Write-Host "$n task: not installed" -ForegroundColor Yellow }
}
function Try-Url($label, $url) {
    try {
        $r = Invoke-RestMethod -Uri $url -Headers @{ "ngrok-skip-browser-warning" = "1" } -TimeoutSec 10
        Write-Host "$label OK  ($url)" -ForegroundColor Green
    } catch { Write-Host "$label NOT reachable ($url): $($_.Exception.Message)" -ForegroundColor Red }
}
Try-Url "Server on this PC:" "http://127.0.0.1:$port/health"
Try-Url "Public address:   " "https://$domain/health"
Write-Host "Logs: $(Resolve-Path "$PSScriptRoot\..")\logs\server.log and ngrok.log"
