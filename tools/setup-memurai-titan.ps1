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
    if (Test-Path $Path) {
        Copy-Item $Path "$Path.titan.bak" -Force
    }
    Set-Content -Path $Path -Value $out -Encoding UTF8
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

Ensure-Admin

$config = Find-MemuraiConfig -Override $ConfigPath
if (-not $config) {
    Write-Error @"
memurai.conf not found.
Install Memurai, or pass -ConfigPath 'C:\Program Files\Memurai\memurai.conf'
"@
}

Write-Host "Using config: $config" -ForegroundColor Cyan
Set-RedisConfDirectives -Path $config -Directives @{
    port       = $Port
    bind       = $Bind
    requirepass = $Password
}

$service = Find-MemuraiService -Override $ServiceName
Write-Host "Restarting service: $($service.Name)..." -ForegroundColor Yellow
Restart-Service -Name $service.Name -Force

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
if (-not $ready) {
    Write-Error "Memurai did not accept connections on ${Bind}:$Port within 30s."
}

$cli = Find-MemuraiCli -ConfigFile $config
if ($cli) {
    $pong = & $cli -h $Bind -p $Port -a $Password --no-auth-warning ping 2>$null
    if ($pong -ne "PONG") {
        Write-Warning "CLI ping did not return PONG (got: $pong). TCP connect succeeded; check requirepass."
    } else {
        Write-Host "PING -> PONG on $Bind`:$Port (requirepass set)." -ForegroundColor Green
    }
} else {
    Write-Host "TCP check OK on $Bind`:$Port (no memurai-cli/redis-cli found for PING)." -ForegroundColor Green
}

Write-Host "Memurai is configured for Titan (port $Port, bind $Bind, password $Password)." -ForegroundColor Green
