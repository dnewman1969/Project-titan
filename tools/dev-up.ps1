# Start the app for development (Section 3). Electron starts titan-supervisor, which migrates the
# database and starts the API (M1). Backing services:
#
#   .\tools\dev-up.ps1              docker compose up; the supervisor treats Postgres and Chroma as external
#   .\tools\dev-up.ps1 -NoCompose   containers you already started (same as above, minus `docker compose up`)
#   .\tools\dev-up.ps1 -Managed     no Docker: the supervisor runs portable Postgres and Chroma itself
#                                  (Memurai is always yours, on 63790 with requirepass)
param([switch]$NoCompose, [switch]$Managed)
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")

function Invoke-Step([string]$Command, [string[]]$Arguments) {
    & $Command @Arguments
    if ($LASTEXITCODE -ne 0) { throw "$Command $($Arguments -join ' ') failed with exit code $LASTEXITCODE" }
}

if (-not $Managed) {
    $env:TITAN__POSTGRES__MODE = "external"
    $env:TITAN__CHROMA__MODE = "external"
    if (-not $env:TITAN__POSTGRES__PASSWORD) { $env:TITAN__POSTGRES__PASSWORD = "titan" }
    if (-not $env:TITAN__REDIS__PASSWORD) { $env:TITAN__REDIS__PASSWORD = "titan-dev" }
    if (-not $NoCompose) { Invoke-Step docker @("compose", "up", "-d", "--wait") }
}
Invoke-Step pnpm @("install", "--frozen-lockfile")
Invoke-Step uv @("sync", "--frozen", "--all-packages")
Invoke-Step pnpm @("dev")
