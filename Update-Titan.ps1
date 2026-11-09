# Double-click Update-Titan.bat or: powershell -ExecutionPolicy Bypass -File Update-Titan.ps1
# Pulls latest main from GitHub, then launches Titan (Start-Titan.ps1).
# ASCII-only source for Windows PowerShell.
$ErrorActionPreference = "Stop"
$RepoRoot = $PSScriptRoot
Set-Location $RepoRoot

function Show-Error([string]$Message) {
    Write-Host ""
    Write-Host $Message -ForegroundColor Red
    Write-Host ""
    Read-Host "Press Enter to close"
    exit 1
}

if (-not (Test-Path (Join-Path $RepoRoot ".git"))) {
    Show-Error "This folder is not a git clone. Re-clone Project-titan, then run Update-Titan again."
}

if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    Show-Error "git is not on PATH. Install Git for Windows, then run Update-Titan again."
}

Write-Host "Project Titan - Update" -ForegroundColor Cyan
Write-Host "Repository: $RepoRoot" -ForegroundColor DarkGray
Write-Host ""

$porcelain = (& git status --porcelain 2>&1)
if ($LASTEXITCODE -ne 0) {
    Show-Error "git status failed. Fix git, then try again."
}

if ($porcelain) {
    Write-Host "Local changes detected in this clone." -ForegroundColor Yellow
    Write-Host "Discarding them and matching origin/main (agent updates expect a clean tree)." -ForegroundColor Yellow
    Write-Host ""
}

Write-Host "Fetching from origin..." -ForegroundColor Cyan
& git fetch origin
if ($LASTEXITCODE -ne 0) {
    Show-Error "git fetch failed. Check your network and git remote."
}

Write-Host "Checking out main..." -ForegroundColor Cyan
& git checkout main
if ($LASTEXITCODE -ne 0) {
    Show-Error "git checkout main failed."
}

if ($porcelain) {
    Write-Host "Resetting hard to origin/main..." -ForegroundColor Cyan
    & git reset --hard origin/main
    if ($LASTEXITCODE -ne 0) {
        Show-Error "git reset --hard origin/main failed."
    }
} else {
    Write-Host "Fast-forwarding main from origin..." -ForegroundColor Cyan
    & git pull --ff-only origin main
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Fast-forward pull failed (diverged history). Resetting to origin/main..." -ForegroundColor Yellow
        & git reset --hard origin/main
        if ($LASTEXITCODE -ne 0) {
            Show-Error "Could not sync to origin/main."
        }
    }
}

$head = (& git rev-parse --short HEAD).Trim()
Write-Host ""
Write-Host "On main at $head. Starting Titan..." -ForegroundColor Green
Write-Host ""

$startScript = Join-Path $RepoRoot "Start-Titan.ps1"
if (-not (Test-Path $startScript)) {
    Show-Error "Start-Titan.ps1 not found next to Update-Titan.ps1."
}

& powershell -NoProfile -ExecutionPolicy Bypass -File $startScript
exit $LASTEXITCODE
