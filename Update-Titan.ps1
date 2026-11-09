# Double-click Update-Titan.bat or: powershell -ExecutionPolicy Bypass -File Update-Titan.ps1
# Pull latest origin/main, refresh deps when lockfiles changed, then Start-Titan.ps1.
# ASCII-only source for Windows PowerShell.
param(
    [switch]$ForceDiscard,
    [switch]$NoLaunch
)

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

function Show-PullFailed([string]$Detail) {
    Show-Error @"
Could not sync this folder to origin/main.

$Detail

What you can try:
  - Check internet and VPN, then run Update-Titan again.
  - In Git Bash or PowerShell: git fetch origin && git status
  - If you only want to keep local edits: git stash push -m titan-update, then Update-Titan.
  - To match GitHub exactly: git fetch origin && git checkout main && git reset --hard origin/main
    (discards all local commits and uncommitted changes in this clone.)
"@
}

function Test-DependencyInstallNeeded {
    param(
        [string]$BeforeRef,
        [string]$AfterRef
    )
    $nm = Join-Path $RepoRoot "node_modules"
    $venv = Join-Path $RepoRoot ".venv"
    if (-not (Test-Path $nm)) {
        return $true
    }
    if (-not (Test-Path $venv)) {
        return $true
    }
    if ($BeforeRef -eq $AfterRef) {
        return $false
    }
    $names = @(& git diff --name-only $BeforeRef $AfterRef 2>&1)
    if ($LASTEXITCODE -ne 0) {
        return $true
    }
    foreach ($n in $names) {
        if (-not $n) { continue }
        if ($n -match '(^|/)pnpm-lock\.yaml$') { return $true }
        if ($n -eq 'uv.lock') { return $true }
        if ($n -eq 'pyproject.toml') { return $true }
        if ($n -match '(^|/)package\.json$') { return $true }
    }
    return $false
}

function Confirm-DiscardLocalChanges([string[]]$StatusLines) {
    if ($ForceDiscard) {
        return
    }
    Write-Host "Local changes in this clone (would be discarded to match origin/main):" -ForegroundColor Yellow
    $shown = 0
    foreach ($line in $StatusLines) {
        Write-Host "  $line" -ForegroundColor DarkYellow
        $shown++
        if ($shown -ge 25) {
            $rest = $StatusLines.Count - $shown
            if ($rest -gt 0) {
                Write-Host "  ... and $rest more line(s)." -ForegroundColor DarkYellow
            }
            break
        }
    }
    Write-Host ""
    Write-Host "Press Y to discard these changes and update, or N to cancel and keep your tree." -ForegroundColor Yellow
    $key = Read-Host "Continue? (Y/N)"
    if ($key -notmatch '^[Yy]$') {
        Show-Error @"
Update cancelled. Your local changes were not modified.

Next steps:
  - Commit or stash changes you want to keep, then run Update-Titan again.
  - Or run: git stash push -m titan-update
  - To abandon local work: git reset --hard origin/main (after git fetch origin)
"@
    }
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

$porcelain = @(& git status --porcelain 2>&1)
if ($LASTEXITCODE -ne 0) {
    Show-Error "git status failed. Fix git, then try again."
}
$hadLocalChanges = [bool]($porcelain | Where-Object { $_ -match '\S' })
if ($hadLocalChanges) {
    Confirm-DiscardLocalChanges @($porcelain | Where-Object { $_ -match '\S' })
}

$beforeRef = (& git rev-parse HEAD 2>&1)
if ($LASTEXITCODE -ne 0) {
    Show-Error "git rev-parse HEAD failed. Is this repository corrupted?"
}
$beforeRef = $beforeRef.Trim()

Write-Host "Fetching from origin..." -ForegroundColor Cyan
& git fetch origin 2>&1 | ForEach-Object { Write-Host $_ }
if ($LASTEXITCODE -ne 0) {
    Show-PullFailed "git fetch origin failed (exit $LASTEXITCODE)."
}

$originMain = (& git rev-parse origin/main 2>&1)
if ($LASTEXITCODE -ne 0) {
    Show-PullFailed "origin/main not found after fetch. Check git remote (git remote -v)."
}
$originMain = $originMain.Trim()

Write-Host "Checking out main..." -ForegroundColor Cyan
& git checkout main 2>&1 | ForEach-Object { Write-Host $_ }
if ($LASTEXITCODE -ne 0) {
    Show-PullFailed "git checkout main failed. You may be on another branch with conflicts."
}

$synced = $false
if ($hadLocalChanges -or $beforeRef -ne $originMain) {
    Write-Host "Syncing to origin/main ($($originMain.Substring(0, [Math]::Min(8, $originMain.Length))))..." -ForegroundColor Cyan
    & git reset --hard origin/main 2>&1 | ForEach-Object { Write-Host $_ }
    if ($LASTEXITCODE -ne 0) {
        Show-PullFailed "git reset --hard origin/main failed."
    }
    $synced = $true
} else {
    Write-Host "Fast-forwarding main from origin..." -ForegroundColor Cyan
    & git pull --ff-only origin main 2>&1 | ForEach-Object { Write-Host $_ }
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Fast-forward pull failed (local main diverged from origin)." -ForegroundColor Yellow
        if (-not $ForceDiscard -and -not $hadLocalChanges) {
            Write-Host "Press Y to reset to origin/main anyway, or N to cancel." -ForegroundColor Yellow
            $key = Read-Host "Reset to origin/main? (Y/N)"
            if ($key -notmatch '^[Yy]$') {
                Show-Error @"
Update cancelled. main could not fast-forward.

Run git log --oneline main..origin/main and git log --oneline origin/main..main to compare.
To match GitHub: git fetch origin && git reset --hard origin/main
"@
            }
        }
        & git reset --hard origin/main 2>&1 | ForEach-Object { Write-Host $_ }
        if ($LASTEXITCODE -ne 0) {
            Show-PullFailed "git reset --hard origin/main failed after pull error."
        }
        $synced = $true
    }
}

$afterRef = (& git rev-parse HEAD).Trim()
$headShort = (& git rev-parse --short HEAD).Trim()
Write-Host ""
if ($beforeRef -eq $afterRef) {
    Write-Host "Already on latest main ($headShort)." -ForegroundColor Green
} else {
    Write-Host "Updated main: $beforeRef -> $headShort" -ForegroundColor Green
    if ($synced -and $hadLocalChanges) {
        Write-Host "Local changes were discarded to match origin/main." -ForegroundColor DarkGray
    }
}

$needDeps = Test-DependencyInstallNeeded -BeforeRef $beforeRef -AfterRef $afterRef
if ($needDeps) {
    Write-Host "Dependency manifests changed (or install missing); Start-Titan will refresh pnpm/uv." -ForegroundColor Cyan
} else {
    Write-Host "Lockfiles unchanged; skipping full dependency install (faster restart)." -ForegroundColor DarkGray
}
Write-Host ""

if ($NoLaunch) {
    Write-Host "NoLaunch set; not starting Titan." -ForegroundColor DarkGray
    exit 0
}

$startScript = Join-Path $RepoRoot "Start-Titan.ps1"
if (-not (Test-Path $startScript)) {
    Show-Error "Start-Titan.ps1 not found next to Update-Titan.ps1."
}

$skipArg = if ($needDeps) { @() } else { @("-SkipDependencyInstall") }
& powershell -NoProfile -ExecutionPolicy Bypass -File $startScript @skipArg
exit $LASTEXITCODE
