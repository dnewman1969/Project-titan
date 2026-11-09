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
    Add-ToolchainDirsToPath
}

function Add-ToolchainDirsToPath {
    $dirs = @(
        (Join-Path $env:USERPROFILE ".local\bin"),
        (Join-Path $env:USERPROFILE ".cargo\bin"),
        (Join-Path $env:APPDATA "npm"),
        (Join-Path $env:LOCALAPPDATA "uv")
    )
    foreach ($dir in $dirs) {
        if ($dir -and (Test-Path $dir) -and ($env:Path -notlike "*$dir*")) {
            $env:Path = "$dir;$env:Path"
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

function Ensure-Uv {
    if (Test-Command uv) { return }
    Write-Host "uv not found; installing Python toolchain (one-time)..." -ForegroundColor Cyan

    if (Test-Command winget) {
        Write-Host "Trying winget (astral-sh.uv)..." -ForegroundColor DarkGray
        Invoke-External winget install --id astral-sh.uv -e --accept-package-agreements --accept-source-agreements | Out-Null
        Refresh-SessionPath
        if (Test-Command uv) { return }
    }

    $prev = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        Write-Host "Running Astral installer (https://astral.sh/uv/install.ps1)..." -ForegroundColor Cyan
        $installScript = Invoke-RestMethod -Uri "https://astral.sh/uv/install.ps1" -UseBasicParsing
        Invoke-Expression $installScript
    } catch {
        Write-Host "uv install script did not complete: $_" -ForegroundColor DarkYellow
    } finally {
        $ErrorActionPreference = $prev
    }
    Refresh-SessionPath

    if (-not (Test-Command uv)) {
        Show-Error @"
uv is required for Python services.
Install: powershell -ExecutionPolicy Bypass -c "irm https://astral.sh/uv/install.ps1 | iex"
Or: winget install astral-sh.uv
"@
    }
}

Ensure-Node
Ensure-Pnpm
Ensure-Uv

$env:TITAN__REDIS__PASSWORD = if ($env:TITAN__REDIS__PASSWORD) { $env:TITAN__REDIS__PASSWORD } else { "titan-dev" }
$RedisWinVersion = "5.0.14.1"
$RedisWinSha256 = "018ea18a35876383cbb5f4cd0258adfc87747cf9d619bce1cf73a2e36f720ccf"

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

function Wait-RedisUp {
    param([int]$Seconds = 45)
    for ($i = 0; $i -lt $Seconds; $i++) {
        if (Test-RedisUp) { return $true }
        Start-Sleep -Seconds 1
    }
    return $false
}

function Get-PortableRedisDir {
    $cacheRoot = Join-Path $RepoRoot "third_party\cache\redis-win"
    if (-not (Test-Path $cacheRoot)) { return $null }
    $exe = Get-ChildItem -Path $cacheRoot -Filter redis-server.exe -Recurse -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($exe) { return $exe.DirectoryName }
    return $null
}

function Start-PortableRedis {
    $binDir = Get-PortableRedisDir
    if (-not $binDir) {
        Write-Host "Downloading portable Redis for Windows (one-time, ~12 MB)..." -ForegroundColor Cyan
        $cacheParent = Join-Path $RepoRoot "third_party\cache"
        if (-not (Test-Path $cacheParent)) {
            New-Item -ItemType Directory -Force -Path $cacheParent | Out-Null
        }
        $zipPath = Join-Path $cacheParent "Redis-x64-$RedisWinVersion.zip"
        $extractRoot = Join-Path $cacheParent "redis-win"
        try {
            $uri = "https://github.com/tporadowski/redis/releases/download/v$RedisWinVersion/Redis-x64-$RedisWinVersion.zip"
            Invoke-WebRequest -Uri $uri -OutFile $zipPath -UseBasicParsing
            if ((Get-FileHash $zipPath -Algorithm SHA256).Hash.ToLowerInvariant() -ne $RedisWinSha256) {
                Write-Host "Portable Redis zip hash mismatch." -ForegroundColor DarkYellow
                return $false
            }
            if (Test-Path $extractRoot) {
                Remove-Item $extractRoot -Recurse -Force -ErrorAction SilentlyContinue
            }
            Expand-Archive -Path $zipPath -DestinationPath $extractRoot -Force
        } catch {
            Write-Host "Portable Redis download failed: $_" -ForegroundColor DarkYellow
            return $false
        }
        $binDir = Get-PortableRedisDir
        if (-not $binDir) { return $false }
    }

    $server = Join-Path $binDir "redis-server.exe"
    $cli = Join-Path $binDir "redis-cli.exe"
    $pass = $env:TITAN__REDIS__PASSWORD
    Write-Host "Starting portable Redis on 127.0.0.1:63790..." -ForegroundColor Yellow
    Start-Process -FilePath $server -WindowStyle Hidden -ArgumentList @(
        "--port", "63790",
        "--bind", "127.0.0.1",
        "--requirepass", $pass
    ) | Out-Null
    for ($i = 0; $i -lt 30; $i++) {
        if (Test-Path $cli) {
            $pong = & $cli -p 63790 -a $pass --no-auth-warning ping 2>$null
            if ($pong -eq "PONG") { return $true }
        } elseif (Test-RedisUp) {
            return $true
        }
        Start-Sleep -Seconds 1
    }
    return (Test-RedisUp)
}

function Test-DockerDaemon {
    if (-not (Test-Command docker)) { return $false }
    $prev = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        & docker info 2>$null | Out-Null
        return ($LASTEXITCODE -eq 0)
    } finally {
        $ErrorActionPreference = $prev
    }
}

function Start-DockerDesktopIfPresent {
    if (Test-DockerDaemon) { return $true }
    $desktop = @(
        (Join-Path ${env:ProgramFiles} "Docker\Docker\Docker Desktop.exe"),
        (Join-Path ${env:ProgramFiles(x86)} "Docker\Docker\Docker Desktop.exe")
    ) | Where-Object { $_ -and (Test-Path $_) } | Select-Object -First 1
    if (-not $desktop) {
        return (Test-Command docker)
    }
    Write-Host "Starting Docker Desktop (first launch may take 1-2 minutes)..." -ForegroundColor Yellow
    Start-Process -FilePath $desktop | Out-Null
    $deadline = (Get-Date).AddMinutes(4)
    while ((Get-Date) -lt $deadline) {
        Start-Sleep -Seconds 4
        if (Test-DockerDaemon) { return $true }
    }
    return $false
}

function Start-RedisViaDocker {
    if (-not (Test-Command docker)) { return $false }
    if (-not (Start-DockerDesktopIfPresent)) {
        Write-Host "Docker CLI found but engine not reachable." -ForegroundColor DarkYellow
        return $false
    }
    Write-Host "Starting Redis via Docker Compose (redis service only)..." -ForegroundColor Yellow
    Push-Location $RepoRoot
    try {
        Invoke-External docker compose up -d redis --wait | Out-Null
    } finally {
        Pop-Location
    }
    return (Wait-RedisUp)
}

function Ensure-Redis {
    if (Test-RedisUp) { return }
    Write-Host "Redis not listening on 127.0.0.1:63790; starting automatically..." -ForegroundColor Cyan
    if (Start-PortableRedis) { return }
    if (Start-RedisViaDocker) { return }
    Show-Error @"
Could not start Redis on 127.0.0.1:63790 (password: $($env:TITAN__REDIS__PASSWORD)).

Start-Titan tried portable Redis and Docker. Check firewall/proxy, install Docker Desktop, or run your own Redis on port 63790 with that password.
Optional always-on service: Memurai Developer — https://www.memurai.com/get-memurai (bind 127.0.0.1:63790, requirepass $($env:TITAN__REDIS__PASSWORD)).
Postgres/Chroma are still managed by Titan without Docker.
"@
}

Ensure-Redis

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
