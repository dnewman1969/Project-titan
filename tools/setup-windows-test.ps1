# One-shot Windows beta setup: install deps, optional Docker backing services, run dev desktop.
# Usage:  cd Project-titan;  .\tools\setup-windows-test.ps1
param([switch]$SkipDocker)
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")

function Invoke-Step([string]$Command, [string[]]$Arguments) {
    & $Command @Arguments
    if ($LASTEXITCODE -ne 0) { throw "$Command $($Arguments -join ' ') failed with exit code $LASTEXITCODE" }
}

Write-Host "== Titan Phase-1 Windows test setup =="

if (-not $SkipDocker) {
    $env:TITAN__POSTGRES__MODE = "external"
    $env:TITAN__CHROMA__MODE = "external"
    if (-not $env:TITAN__POSTGRES__PASSWORD) { $env:TITAN__POSTGRES__PASSWORD = "titan" }
    if (-not $env:TITAN__REDIS__PASSWORD) { $env:TITAN__REDIS__PASSWORD = "titan-dev" }
    if (Get-Command docker -ErrorAction SilentlyContinue) {
        Invoke-Step docker @("compose", "up", "-d", "--wait")
    } else {
        Write-Warning "Docker not found — start Postgres/Chroma/Redis yourself or install Docker Desktop."
    }
}

Invoke-Step pnpm @("install", "--frozen-lockfile")
Invoke-Step uv @("sync", "--frozen", "--all-packages")
Invoke-Step pnpm @("codegen")

Write-Host ""
Write-Host "Ready. Launch:  .\tools\dev-up.ps1 -NoCompose"
Write-Host "Full checklist: docs\beta-test-playbook.md"
