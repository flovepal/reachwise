# Brings this folder up to date from GitHub and restarts its server.
# Use it in the production folder after releasing; in development it just installs new packages and restarts.
#   powershell -ExecutionPolicy Bypass -File .\update.ps1
$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$backend = Split-Path -Parent $here
$root = Split-Path -Parent $backend
Set-Location $root

$changes = git status --porcelain
if ($changes) {
    Write-Host "This folder has changes that aren't committed yet:" -ForegroundColor Yellow
    git status --short
    Write-Host "Commit or undo them first (in development: use VS Code's Source Control and push)."
    exit 1
}
git pull --ff-only
& "$backend\.venv\Scripts\python.exe" -m pip install -q -r "$backend\requirements.txt"
& "$here\restart_server.ps1"
