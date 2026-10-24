# Restarts this folder's Reachwise server so it picks up code or .env changes.
#   powershell -ExecutionPolicy Bypass -File .\restart_server.ps1
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$port = ((Select-String -Path "$here\settings.bat" -Pattern "^set PORT=(.+)$").Matches[0].Groups[1].Value).Trim()
$local = "$here\settings.local.bat"
if (Test-Path $local) {
    $m = Select-String -Path $local -Pattern "^set PORT=(.+)$"
    if ($m) { $port = $m.Matches[0].Groups[1].Value.Trim() }
}

# Stop the start_server.bat window of this folder, then the server on this port
Get-CimInstance Win32_Process | Where-Object {
    ($_.Name -eq "cmd.exe" -and $_.CommandLine -like "*$here\start_server.bat*") -or
    ($_.Name -like "python*" -and $_.CommandLine -like "*uvicorn app.main:app*" -and $_.CommandLine -like "*--port $port*")
} | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
Start-Sleep -Seconds 2

Start-Process cmd.exe -ArgumentList ('/c start "Reachwise Server" /min "{0}"' -f "$here\start_server.bat") -WindowStyle Hidden
Write-Host "Server restarting on port $port. Checking in 10 seconds..."
Start-Sleep -Seconds 10
try {
    Invoke-RestMethod "http://127.0.0.1:$port/health" -TimeoutSec 10 | Out-Null
    Write-Host "Server is up." -ForegroundColor Green
} catch {
    Write-Host "Server didn't answer yet. Look at backend\logs\server.log" -ForegroundColor Yellow
}
