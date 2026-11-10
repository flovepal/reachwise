# Saves all changes in this folder to GitHub (branch dev) and restarts the development server.
# Netlify rebuilds the website by itself after the push.
#   powershell -ExecutionPolicy Bypass -File .\publish_changes.ps1 "what changed"
param([string]$Message = "")
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

$branch = (git rev-parse --abbrev-ref HEAD).Trim()
if ($branch -ne "dev") { Write-Host "You are on branch '$branch'. Switch to dev first:  git checkout dev" -ForegroundColor Yellow; exit 1 }

git add -A
$leaks = git diff --cached --name-only | Where-Object { $_ -match "(^|/)\.env$|ngrok\.yml$|settings\.local\.bat$" }
if ($leaks) { git reset -q; Write-Host "Stopped: secret files were about to be uploaded: $leaks" -ForegroundColor Red; exit 1 }

if (git diff --cached --name-only) {
    Write-Host "Changes to publish:" -ForegroundColor Cyan
    git diff --cached --stat
    if (-not $Message) { $Message = Read-Host "Describe the change in a few words" }
    if (-not $Message) { $Message = "Update" }
    git commit -q -m $Message
    if ($LASTEXITCODE -ne 0) { Write-Host "Commit failed." -ForegroundColor Red; exit 1 }
} else {
    Write-Host "No new changes to commit."
}

git push origin dev
if ($LASTEXITCODE -ne 0) { Write-Host "Push failed (check your internet or GitHub sign-in)." -ForegroundColor Red; exit 1 }
Write-Host "Pushed to GitHub. Netlify will rebuild the site in about a minute." -ForegroundColor Green

& "$root\backend\windows\restart_server.ps1"
