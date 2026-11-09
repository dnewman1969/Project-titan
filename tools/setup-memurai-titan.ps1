# Configure Memurai for Project Titan (127.0.0.1:63790, requirepass titan-dev) and restart the service.
# Usage (elevated):  powershell -ExecutionPolicy Bypass -File tools\setup-memurai-titan.ps1
# Or double-click:   tools\setup-memurai-titan.bat
param(
    [string]$ConfigPath = "",
    [int]$Port = 63790,
    [string]$Bind = "127.0.0.1",
    [string]$Password = "titan-dev",
    [string]$ServiceName = ""
)

$ErrorActionPreference = "Stop"

function Test-IsAdmin {
    $principal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Ensure-Admin {
    if (Test-IsAdmin) { return }
    Write-Host "Memurai service restart requires Administrator." -ForegroundColor Yellow
    $argList = @(
        "-NoProfile",
        "-ExecutionPolicy", "Bypass",
        "-File", $PSCommandPath
    )
    if ($ConfigPath) { $argList += @("-ConfigPath", $ConfigPath) }
    if ($ServiceName) { $argList += @("-ServiceName", $ServiceName) }
    $argList += @("-Port", $Port, "-Bind", $Bind, "-Password", $Password)
    $proc = Start-Process -FilePath "powershell.exe" -Verb RunAs -ArgumentList $argList -Wait -PassThru
    exit $proc.ExitCode
}

function Find-MemuraiConfig {
    param([string]$Override)
    if ($Override -and (Test-Path $Override)) { return (Resolve-Path $Override).Path }
    $roots = @(
        (Join-Path $env:ProgramFiles "Memurai"),
        (Join-Path ${env:ProgramFiles(x86)} "Memurai"),
        (Join-Path $env:ProgramFiles "Memurai Developer"),
        (Join-Path ${env:ProgramFiles(x86)} "Memurai Developer")
    )
    foreach ($root in $roots) {
        $candidate = Join-Path $root "memurai.conf"
        if (Test-Path $candidate) { return $candidate }
    }
    $found = Get-ChildItem -Path $env:ProgramFiles -Filter "memurai.conf" -Recurse -ErrorAction SilentlyContinue |
        Select-Object -First 1
    if ($found) { return $found.FullName }
    return $null
}

function Set-RedisConfDirectives {
    param(
        [string]$Path,
        [hashtable]$Directives
    )
    $lines = @()
    if (Test-Path $Path) {
        $lines = Get-Content -Path $Path
    }
    $out = New-Object System.Collections.Generic.List[string]
    $seen = @{}
    foreach ($line in $lines) {
        $trim = $line.Trim()
        if ($trim.StartsWith("#") -or [string]::IsNullOrWhiteSpace($trim)) {
            $out.Add($line)
            continue
        }
        $replaced = $false
        foreach ($key in $Directives.Keys) {
            if ($trim -match "^\s*$([regex]::Escape($key))\s+") {
                $out.Add("$key $($Directives[$key])")
                $seen[$key] = $true
                $replaced = $true
                break
            }
        }
        if (-not $replaced) { $out.Add($line) }
    }
    foreach ($key in $Directives.Keys) {
        if (-not $seen[$key]) {
            if ($out.Count -gt 0 -and $out[-1] -ne "") { $out.Add("") }
            $out.Add("$key $($Directives[$key])")
        }
    }
    $parent = Split-Path $Path -Parent
    if (-not (Test-Path $parent)) {
        throw "Config directory does not exist: $parent"
    }
    $backup = "$Path.titan.bak"
    if (Test-Path $Path) {
        Copy-Item $Path $backup -Force
    }
    Set-Content -Path $Path -Value $out -Encoding UTF8
    return $backup
}

function Restore-MemuraiConfigBackup {
    param([string]$Path)
    $backup = "$Path.titan.bak"
    if (-not (Test-Path $backup)) {
        Write-Host "No backup to restore at $backup" -ForegroundColor DarkYellow
        return $false
    }
    Copy-Item $backup $Path -Force
    Write-Host "Restored previous memurai.conf from $backup." -ForegroundColor Yellow
    return $true
}

function Find-MemuraiCli {
    param([string]$ConfigFile)
    $dir = Split-Path $ConfigFile -Parent
    foreach ($name in @("memurai-cli.exe", "redis-cli.exe")) {
        $cli = Join-Path $dir $name
        if (Test-Path $cli) { return $cli }
    }
    if (Get-Command memurai-cli -ErrorAction SilentlyContinue) { return "memurai-cli" }
    if (Get-Command redis-cli -ErrorAction SilentlyContinue) { return "redis-cli" }
    return $null
}

function Find-MemuraiService {
    param([string]$Override)
    if ($Override) {
        $svc = Get-Service -Name $Override -ErrorAction SilentlyContinue
        if ($svc) { return $svc }
        throw "Service not found: $Override"
    }
    $svc = Get-Service -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -like "Memurai*" -or $_.DisplayName -like "Memurai*" } |
        Select-Object -First 1
    if (-not $svc) {
        throw "No Memurai Windows service found. Install Memurai Developer first: https://www.memurai.com/get-memurai"
    }
    return $svc
}

function Get-ListeningOnPort {
    param(
        [int]$Port,
        [string]$Bind = "127.0.0.1"
    )
    $conns = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    if (-not $conns) { return @() }
    return @(
        $conns | Where-Object {
            $_.LocalAddress -eq $Bind -or $_.LocalAddress -eq "0.0.0.0" -or $_.LocalAddress -eq "::" -or $_.LocalAddress -eq "127.0.0.1"
        }
    )
}

function Get-PortProcessSummary {
    param([int]$Port)
    $listeners = Get-ListeningOnPort -Port $Port
    $rows = @()
    foreach ($c in $listeners) {
        $procName = "unknown"
        try {
            $procName = (Get-Process -Id $c.OwningProcess -ErrorAction Stop).ProcessName
        } catch { }
        $rows += "PID $($c.OwningProcess) ($procName) on $($c.LocalAddress):$Port"
    }
    return $rows
}

function Test-RedisPing {
    param(
        [string]$Cli,
        [string]$Bind,
        [int]$Port,
        [string]$Password
    )
    if (-not $Cli) { return $false }
    try {
        $pong = & $Cli -h $Bind -p $Port -a $Password --no-auth-warning ping 2>$null
        return ($pong -eq "PONG")
    } catch {
        return $false
    }
}

function Write-ServiceDiagnostics {
    param([string]$ServiceName)
    Write-Host "--- sc.exe query $ServiceName ---" -ForegroundColor DarkGray
    sc.exe query $ServiceName 2>&1 | ForEach-Object { Write-Host $_ }
    Write-Host "--- sc.exe qc $ServiceName ---" -ForegroundColor DarkGray
    sc.exe qc $ServiceName 2>&1 | ForEach-Object { Write-Host $_ }
    try {
        $events = Get-WinEvent -FilterHashtable @{
            LogName      = "System"
            ProviderName = "Service Control Manager"
            StartTime    = (Get-Date).AddMinutes(-10)
        } -MaxEvents 40 -ErrorAction Stop |
            Where-Object { $_.Message -match [regex]::Escape($ServiceName) } |
            Select-Object -First 5
        if ($events) {
            Write-Host "--- Recent Service Control Manager events ---" -ForegroundColor DarkGray
            foreach ($ev in $events) {
                Write-Host "[$($ev.TimeCreated)] $($ev.Message)"
            }
        }
    } catch {
        Write-Host "Could not read System event log: $_" -ForegroundColor DarkGray
    }
}

function Restart-MemuraiServiceWithRetry {
    param(
        [System.ServiceProcess.ServiceController]$Service,
        [int]$Attempts = 6
    )
    $name = $Service.Name
    $prev = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        for ($try = 1; $try -le $Attempts; $try++) {
            $svc = Get-Service -Name $name
            if ($svc.Status -ne "Stopped") {
                Write-Host "Stopping $name (attempt $try)..." -ForegroundColor Yellow
                Stop-Service -Name $name -Force -ErrorAction Continue
                Start-Sleep -Seconds 3
            }
            $svc = Get-Service -Name $name
            if ($svc.Status -eq "StopPending") {
                $svc.WaitForStatus("Stopped", (New-TimeSpan -Seconds 45))
            }
            if ($svc.Status -ne "Stopped") {
                Write-Host "Service still $($svc.Status) after stop attempt $try." -ForegroundColor DarkYellow
                continue
            }
            Write-Host "Starting $name (attempt $try)..." -ForegroundColor Yellow
            Start-Service -Name $name -ErrorAction Continue
            Start-Sleep -Seconds 2
            $svc = Get-Service -Name $name
            if ($svc.Status -eq "StartPending") {
                $svc.WaitForStatus("Running", (New-TimeSpan -Seconds 60))
            }
            $svc = Get-Service -Name $name
            if ($svc.Status -eq "Running") {
                return $true
            }
            Write-Host "Start-Service did not reach Running (status: $($svc.Status))." -ForegroundColor DarkYellow
        }
        return $false
    } finally {
        $ErrorActionPreference = $prev
    }
}

Ensure-Admin

$config = Find-MemuraiConfig -Override $ConfigPath
if (-not $config) {
    Write-Error @"
memurai.conf not found.
Install Memurai, or pass -ConfigPath 'C:\Program Files\Memurai\memurai.conf'
"@
}

$cliEarly = Find-MemuraiCli -ConfigFile $config
$listeners = Get-ListeningOnPort -Port $Port -Bind $Bind
if ($listeners.Count -gt 0) {
    Write-Host "Port $Port is already in use:" -ForegroundColor Yellow
    Get-PortProcessSummary -Port $Port | ForEach-Object { Write-Host "  $_" }
    if (Test-RedisPing -Cli $cliEarly -Bind $Bind -Port $Port -Password $Password) {
        Write-Host "Redis already responds PONG with Titan password on $Bind`:$Port - Memurai may already be configured." -ForegroundColor Green
        Write-Host "Updating memurai.conf anyway for consistency; service restart may be optional." -ForegroundColor DarkGray
    } else {
        Write-Host "Another process holds port $Port without the expected Titan password. Stop it or choose a different Redis before Memurai can bind here." -ForegroundColor Red
    }
}

Write-Host "Using config: $config" -ForegroundColor Cyan
$configBackup = Set-RedisConfDirectives -Path $config -Directives @{
    port        = $Port
    bind        = $Bind
    requirepass = $Password
}
Write-Host "Trial config written (backup: $configBackup)." -ForegroundColor Cyan

$service = Find-MemuraiService -Override $ServiceName
Write-Host "Restarting service: $($service.Name)..." -ForegroundColor Yellow
$restarted = Restart-MemuraiServiceWithRetry -Service $service

if (-not $restarted) {
    Write-Host ""
    Write-ServiceDiagnostics -ServiceName $service.Name
    Restore-MemuraiConfigBackup -Path $config | Out-Null
    Write-Host ""
    Write-Host @"
Memurai did not start with Titan settings; memurai.conf was reverted to the pre-edit backup.

Use Start-Titan.bat (portable Redis on $Port) - Memurai is optional.
To retry Memurai later: fix the service in services.msc, then run this script again as Administrator.
If port $Port is owned by another process, stop it first.
"@ -ForegroundColor Yellow
    exit 0
}

$ready = $false
for ($i = 0; $i -lt 30; $i++) {
    try {
        $client = [System.Net.Sockets.TcpClient]::new()
        $client.Connect($Bind, $Port)
        $client.Close()
        $ready = $true
        break
    } catch {
        Start-Sleep -Seconds 1
    }
}

$cli = Find-MemuraiCli -ConfigFile $config
if (-not $ready) {
    Write-Host "Memurai service is running but $Bind`:$Port did not accept TCP within 30s." -ForegroundColor Yellow
    Write-ServiceDiagnostics -ServiceName $service.Name
    Restore-MemuraiConfigBackup -Path $config | Out-Null
    Write-Host "Config reverted. Use Start-Titan.bat for portable Redis, or repair Memurai in services.msc and re-run this script." -ForegroundColor Yellow
    exit 0
}

if ($cli) {
    if (-not (Test-RedisPing -Cli $cli -Bind $Bind -Port $Port -Password $Password)) {
        Write-Warning "CLI ping did not return PONG. TCP connect succeeded; check requirepass or restart Memurai once more."
    } else {
        Write-Host "PING -> PONG on $Bind`:$Port (requirepass set)." -ForegroundColor Green
    }
} else {
    Write-Host "TCP check OK on $Bind`:$Port (no memurai-cli/redis-cli found for PING)." -ForegroundColor Green
}

Write-Host "Memurai is configured for Titan (port $Port, bind $Bind, password $Password)." -ForegroundColor Green
