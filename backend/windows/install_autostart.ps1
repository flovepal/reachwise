# Makes Reachwise start by itself every time this PC starts and signs in.
# Run once:  powershell -ExecutionPolicy Bypass -File .\install_autostart.ps1
# Options:   -LockScreen yes|no   -StartNow   (used by the setup script to skip the questions)
param([string]$LockScreen = "", [switch]$StartNow)
$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path

$user = [Security.Principal.WindowsIdentity]::GetCurrent().Name
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $user
$principal = New-ScheduledTaskPrincipal -UserId $user -LogonType Interactive -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -ExecutionTimeLimit ([TimeSpan]::Zero) -MultipleInstances IgnoreNew

$tasks = @(
    @{ Name = "Reachwise Server"; File = "start_server.bat" },
    @{ Name = "Reachwise Tunnel"; File = "start_ngrok.bat" }
)
foreach ($t in $tasks) {
    $bat = Join-Path $here $t.File
    # Opens a minimised window on the taskbar, so you can see it is running
    $arg = '/c start "{0}" /min "{1}"' -f $t.Name, $bat
    $action = New-ScheduledTaskAction -Execute "cmd.exe" -Argument $arg -WorkingDirectory $here
    Unregister-ScheduledTask -TaskName $t.Name -Confirm:$false -ErrorAction SilentlyContinue
    Register-ScheduledTask -TaskName $t.Name -Action $action -Trigger $trigger -Principal $principal -Settings $settings | Out-Null
    Write-Host "Registered: $($t.Name)  ->  $bat" -ForegroundColor Green
}

if ($LockScreen -eq "") { $LockScreen = Read-Host "Lock the screen 1 minute after Reachwise starts? Recommended if the PC signs in automatically (yes/no)" }
Unregister-ScheduledTask -TaskName "Reachwise Lock Screen" -Confirm:$false -ErrorAction SilentlyContinue
if ($LockScreen -match "^y") {
    $lockTrigger = New-ScheduledTaskTrigger -AtLogOn -User $user
    $lockTrigger.Delay = "PT1M"
    $lockAction = New-ScheduledTaskAction -Execute "rundll32.exe" -Argument "user32.dll,LockWorkStation"
    Register-ScheduledTask -TaskName "Reachwise Lock Screen" -Action $lockAction -Trigger $lockTrigger -Principal $principal -Settings $settings | Out-Null
    Write-Host "Registered: screen locks 1 minute after sign-in." -ForegroundColor Green
}

powercfg /change standby-timeout-ac 0 2>$null
powercfg /change hibernate-timeout-ac 0 2>$null

if (-not $StartNow) { $StartNow = (Read-Host "Start Reachwise now? (y/n)") -match "^y" }
if ($StartNow) {
    Start-ScheduledTask -TaskName "Reachwise Server"
    Start-ScheduledTask -TaskName "Reachwise Tunnel"
    Write-Host "Started. Wait about 30 seconds, then run:  powershell -ExecutionPolicy Bypass -File .\status.ps1"
}
