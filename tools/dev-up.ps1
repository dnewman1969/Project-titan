# Start backing services and the app for development (Section 3).
# Until the supervisor exists (M1), Postgres, Redis and Chroma come from docker-compose.yml (ADR 0020)
# and `pnpm dev` launches the API with a fresh launch token.
#
#   .\tools\dev-up.ps1                start containers, migrate, run the app
#   .\tools\dev-up.ps1 -NoServices    use services you started yourself on the same ports
param([switch]$NoServices)
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")

if (-not $env:TITAN__POSTGRES__PASSWORD) { $env:TITAN__POSTGRES__PASSWORD = "titan" }

function Invoke-Step([string]$Command, [string[]]$Arguments) {
    & $Command @Arguments
    if ($LASTEXITCODE -ne 0) { throw "$Command $($Arguments -join ' ') failed with exit code $LASTEXITCODE" }
}

if (-not $NoServices) { Invoke-Step docker @("compose", "up", "-d", "--wait") }
Invoke-Step pnpm @("install", "--frozen-lockfile")
Invoke-Step uv @("sync", "--frozen", "--all-packages")
Invoke-Step uv @("run", "titan-db", "upgrade")
Invoke-Step pnpm @("dev")
