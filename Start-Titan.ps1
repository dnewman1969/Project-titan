# Double-click or:  powershell -ExecutionPolicy Bypass -File Start-Titan.ps1
# Starts portable Postgres + Chroma (managed), requires Redis on 63790, then opens the Operations Center.
$ErrorActionPreference = "Stop"
$RepoRoot = $PSScriptRoot
Set-Location $RepoRoot

$PnpmVersion = "10.33.4"

function Show-Error([string]$Message) {
    try {
        Add-Type -AssemblyName System.Windows.Forms -ErrorAction Stop
        [void][System.Windows.Forms.MessageBox]::Show($Message, "Project Titan", 0, 16)
    } catch {
        Write-Host $Message -ForegroundColor Red
    }
    exit 1
}

function Test-Command([string]$Name) {
    return [bool](Get-Command $Name -ErrorAction SilentlyContinue)
}

function Refresh-SessionPath {
    $machine = [Environment]::GetEnvironmentVariable("Path", "Machine")
    $user = [Environment]::GetEnvironmentVariable("Path", "User")
    if ($machine -and $user) {
        $env:Path = "$machine;$user"
    } elseif ($machine) {
        $env:Path = $machine
    } elseif ($user) {
        $env:Path = $user
    }
    $nodeHome = (Get-Command node -ErrorAction SilentlyContinue).Source
    if ($nodeHome) {
        $nodeDir = Split-Path $nodeHome -Parent
        if ($env:Path -notlike "*$nodeDir*") {
            $env:Path = "$nodeDir;$env:Path"
        }
    }
}

function Ensure-Node {
    if (Test-Command node) { return }
    if (Test-Command winget) {
        Write-Host "Node.js not found. Installing Node.js LTS with winget (one-time)..." -ForegroundColor Yellow
        try {
            winget install --id OpenJS.NodeJS.LTS -e --accept-package-agreements --accept-source-agreements
        } catch {
            Write-Host "winget install did not complete: $_" -ForegroundColor DarkYellow
        }
        Refresh-SessionPath
    }
    if (-not (Test-Command node)) {
        Show-Error @"
Node.js 22+ LTS is required.
Install: https://nodejs.org/ (choose LTS)
Or in PowerShell: winget install OpenJS.NodeJS.LTS
"@
    }
}

function Invoke-External {
    param(
        [string]$Exe,
        [Parameter(ValueFromRemainingArguments = $true)][object[]] $RemainingArgs
    )
    $prev = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        $out = & $Exe @RemainingArgs 2>&1
        foreach ($line in $out) {
            if ($line -is [System.Management.Automation.ErrorRecord]) {
                Write-Host $line.ToString() -ForegroundColor DarkYellow
            } else {
                Write-Host $line
            }
        }
        return $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $prev
    }
}

function Ensure-Pnpm {
    if (Test-Command pnpm) { return }
    Write-Host "pnpm not on PATH; preparing toolchain (one-time, no admin required)..." -ForegroundColor Cyan

    $corepack = $null
    if (Test-Command corepack) {
        $corepack = "corepack"
    } elseif (Test-Command node) {
        $corepackJs = Join-Path (Split-Path (Get-Command node).Source -Parent) "node_modules\corepack\dist\corepack.js"
        if (Test-Path $corepackJs) { $corepack = $corepackJs }
    }

    if ($corepack) {
        if ($corepack -eq "corepack") {
            $enableCode = Invoke-External corepack enable
        } else {
            $enableCode = Invoke-External node $corepack enable
        }
        if ($enableCode -ne 0) {
            Write-Host "corepack enable skipped (often EPERM under Program Files without admin). Continuing..." -ForegroundColor DarkYellow
        }
        if ($corepack -eq "corepack") {
            Invoke-External corepack prepare "pnpm@$PnpmVersion" --activate | Out-Null
        } else {
            Invoke-External node $corepack prepare "pnpm@$PnpmVersion" --activate | Out-Null
        }
        Refresh-SessionPath
    }

    if (-not (Test-Command pnpm) -and (Test-Command npm)) {
        Write-Host "Installing pnpm@$PnpmVersion via npm (user install, no admin)..." -ForegroundColor Cyan
        $npmPrefix = Join-Path $env:APPDATA "npm"
        if (-not (Test-Path $npmPrefix)) {
            New-Item -ItemType Directory -Force -Path $npmPrefix | Out-Null
        }
        Invoke-External npm install -g "pnpm@$PnpmVersion" --prefix $npmPrefix | Out-Null
        if ($env:Path -notlike "*$npmPrefix*") {
            $env:Path = "$npmPrefix;$env:Path"
        }
        Refresh-SessionPath
    }
}

function Invoke-Pnpm {
    [CmdletBinding()]
    param([Parameter(ValueFromRemainingArguments = $true)][object[]] $RemainingArgs)
    Ensure-Pnpm
    if (Test-Command pnpm) {
        & pnpm @RemainingArgs
        if ($LASTEXITCODE) { exit $LASTEXITCODE }
        return
    }
    if (Test-Command corepack) {
        $prev = $ErrorActionPreference
        $ErrorActionPreference = "Continue"
        & corepack pnpm @RemainingArgs
        $code = $LASTEXITCODE
        $ErrorActionPreference = $prev
        if ($code -eq 0) { return }
        Write-Host "corepack pnpm exited $code; trying npx..." -ForegroundColor DarkYellow
    }
    if (Test-Command npx) {
        & npx --yes "pnpm@$PnpmVersion" -- @RemainingArgs
        if ($LASTEXITCODE) { exit $LASTEXITCODE }
        return
    }
    Show-Error "pnpm could not be prepared.`nInstall without admin: npm install -g pnpm@$PnpmVersion`nOr: corepack prepare pnpm@$PnpmVersion --activate"
}

Ensure-Node
Ensure-Pnpm

if (-not (Test-Command uv)) { Show-Error "uv is required.`nInstall: https://docs.astral.sh/uv/getting-started/installation/" }

$env:TITAN__REDIS__PASSWORD = if ($env:TITAN__REDIS__PASSWORD) { $env:TITAN__REDIS__PASSWORD } else { "titan-dev" }

function Test-RedisUp() {
    try {
        $r = [System.Net.Sockets.TcpClient]::new()
        $r.Connect("127.0.0.1", 63790)
        $r.Close()
        return $true
    } catch {
        return $false
    }
}

if (-not (Test-RedisUp)) {
    if (Test-Command docker) {
        Write-Host "Starting Redis via Docker (one container only)..." -ForegroundColor Yellow
        docker compose up -d redis --wait 2>&1 | Out-Host
        if (-not (Test-RedisUp)) {
            Show-Error "Redis still not reachable on 127.0.0.1:63790.`nInstall Memurai Developer (port 63790, password titan-dev) or fix Docker."
        }
    } else {
        Show-Error @"
Redis is required on 127.0.0.1:63790 with password '$($env:TITAN__REDIS__PASSWORD)'.

Option A — Memurai Developer: https://www.memurai.com/get-memurai
Option B — Docker Desktop, then run this script again (Redis container starts automatically).
Docker is NOT required for Postgres/Chroma (those are portable/managed).
"@
    }
}

$pgCtl = Join-Path $RepoRoot "third_party\cache\postgresql\pgsql\bin\pg_ctl.exe"
if (-not (Test-Path $pgCtl)) {
    Write-Host "Fetching portable PostgreSQL 16 (~320 MB, first run only)..." -ForegroundColor Cyan
    uv run python tools/fetch-third-party.py postgresql --extract
}
if (-not (Test-Path $pgCtl)) {
    Show-Error "Portable PostgreSQL not found after fetch. Check network and re-run Start-Titan.ps1."
}

$desktopEnv = Join-Path $RepoRoot "apps\desktop\.env"
$envExample = Join-Path $RepoRoot "apps\desktop\.env.example"
if (-not (Test-Path $desktopEnv) -and (Test-Path $envExample)) {
    Copy-Item $envExample $desktopEnv
}

Write-Host "Installing dependencies (first run may take several minutes)..." -ForegroundColor Cyan
Invoke-Pnpm install --frozen-lockfile
uv sync --frozen --all-packages
Invoke-Pnpm codegen

Write-Host "Launching Titan Operations Center..." -ForegroundColor Green
Write-Host "If the window is blank for >60s, check the boot splash for Redis/Postgres/API status." -ForegroundColor DarkGray
Invoke-Pnpm dev
