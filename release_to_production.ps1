# Copies everything on branch dev to branch main (production), after you've tested it.
# Run from the development folder:  powershell -ExecutionPolicy Bypass -File .\release_to_production.ps1
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $here
if (git status --porcelain) { Write-Host "Commit and push your changes on dev first." -ForegroundColor Yellow; exit 1 }
git fetch -q origin
$ahead = git rev-list --count origin/main..dev
if ($ahead -eq "0") { Write-Host "Production already has everything from dev."; exit 0 }
Write-Host "These $ahead change(s) will go to production:" -ForegroundColor Cyan
git log --oneline origin/main..dev
if ((Read-Host "Release them? (y/n)") -notmatch "^y") { exit 0 }
git push origin dev:main
if ($LASTEXITCODE -ne 0) { Write-Host "Release failed: main has changes that dev doesn't. Ask for help before forcing anything." -ForegroundColor Red; exit 1 }
Write-Host "Released. The production website rebuilds by itself (Vercel)." -ForegroundColor Green
$prod = Join-Path (Split-Path -Parent $here) "production"
if (Test-Path "$prod\backend\windows\update.ps1") {
    if ((Read-Host "Update and restart the production server now? (y/n)") -match "^y") { & "$prod\backend\windows\update.ps1" }
}
