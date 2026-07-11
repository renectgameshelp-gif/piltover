# Run Mediasoup SFU natively on Windows (Piltover group voice/video calls).
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

function Test-LocalPortFree([int]$Port) {
    $listener = $null
    try {
        $listener = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Any, $Port)
        $listener.Start()
        return $true
    } catch {
        return $false
    } finally {
        if ($listener) { $listener.Stop() }
    }
}

function Stop-WindowsSfuOnPort([int]$Port) {
    $lines = netstat -ano | Select-String ":\s*$Port\s+.*LISTENING"
    foreach ($line in $lines) {
        if ($line -notmatch '\s+(\d+)\s*$') { continue }
        $processId = [int]$Matches[1]
        $proc = Get-CimInstance Win32_Process -Filter "ProcessId=$processId" -ErrorAction SilentlyContinue
        if ($proc -and $proc.Name -eq 'node.exe') {
            Write-Host "Stopping node on port $Port (pid=$processId) ..."
            Stop-Process -Id $processId -Force -ErrorAction SilentlyContinue
        }
    }
    Start-Sleep -Seconds 1
}

function Ensure-FirewallRules {
    $rules = @(
        @{ Name = "Piltover SFU HTTP"; Port = 3200; Protocol = "TCP" },
        @{ Name = "Piltover SFU WebRTC UDP"; Port = "10000-10100"; Protocol = "UDP" },
        @{ Name = "Piltover SFU WebRTC TCP"; Port = "10000-10100"; Protocol = "TCP" }
    )
    foreach ($rule in $rules) {
        $existing = Get-NetFirewallRule -DisplayName $rule.Name -ErrorAction SilentlyContinue
        if (-not $existing) {
            try {
                Write-Host "Adding firewall rule: $($rule.Name)"
                New-NetFirewallRule -DisplayName $rule.Name -Direction Inbound `
                    -LocalPort $rule.Port -Protocol $rule.Protocol -Action Allow -ErrorAction Stop | Out-Null
            } catch {
                Write-Warning "Could not add firewall rule '$($rule.Name)' - run as Administrator once."
            }
        }
    }
}

if (-not (Test-Path "node_modules\mediasoup\worker\out\Release\mediasoup-worker.exe")) {
    Write-Host "Installing dependencies for Windows (first run may take a few minutes)..."
    npm ci
}

Ensure-FirewallRules

function Get-BestLocalIPv4 {
    $addrs = Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue | Where-Object {
        $_.IPAddress -notlike '127.*' -and
        $_.IPAddress -notlike '169.254.*' -and
        $_.PrefixOrigin -ne 'WellKnown'
    }
    $preferred = $addrs | Where-Object {
        $_.IPAddress -like '192.168.*' -and
        $_.IPAddress -notlike '192.168.56.*'
    } | Sort-Object @{
        Expression = {
            if ($_.IPAddress -like '192.168.0.*') { 0 }
            elseif ($_.PrefixOrigin -eq 'Dhcp') { 1 }
            else { 2 }
        }
    } | Select-Object -First 1
    if ($preferred) { return $preferred.IPAddress }
    $fallback = $addrs | Select-Object -First 1
    if ($fallback) { return $fallback.IPAddress }
    return '127.0.0.1'
}

function Get-ConfiguredAnnouncedIp {
    $envPath = Join-Path $PSScriptRoot ".env"
    if (Test-Path $envPath) {
        $match = Select-String -Path $envPath -Pattern '^\s*MEDIASOUP_ANNOUNCED_IP\s*=\s*(.+)\s*$' | Select-Object -First 1
        if ($match -and $match.Matches[0].Groups[1].Value) {
            $ip = $match.Matches[0].Groups[1].Value.Trim().Trim('"').Trim("'")
            if ($ip -and $ip -ne 'auto' -and $ip -ne '127.0.0.1' -and $ip -notlike '192.168.56.*') {
                return $ip
            }
        }
    }

    $systemToml = Join-Path (Split-Path $PSScriptRoot -Parent) "config.custom\system.toml"
    if (Test-Path $systemToml) {
        $match = Select-String -Path $systemToml -Pattern '^\s*public_ip\s*=\s*"(.+)"\s*$' | Select-Object -First 1
        if ($match -and $match.Matches[0].Groups[1].Value) {
            $ip = $match.Matches[0].Groups[1].Value.Trim()
            if ($ip -and $ip -ne '127.0.0.1' -and $ip -notlike '192.168.56.*') {
                return $ip
            }
        }
    }

    return Get-BestLocalIPv4
}

$announcedIp = Get-ConfiguredAnnouncedIp

$envPath = Join-Path $PSScriptRoot ".env"
$envContent = @"
PORT=3200
MEDIASOUP_LISTEN_IP=0.0.0.0
MEDIASOUP_ANNOUNCED_IP=$announcedIp
RTC_MIN_PORT=10000
RTC_MAX_PORT=10100
LOG_LEVEL=info
PILTOVER_CALLBACK_URL=http://127.0.0.1:4431/api/group-call-speaking
"@
$utf8NoBom = New-Object System.Text.UTF8Encoding $false
if (-not (Test-Path $envPath)) {
    [System.IO.File]::WriteAllText($envPath, $envContent, $utf8NoBom)
} else {
    $existing = [System.IO.File]::ReadAllText($envPath)
    if ($existing -notmatch 'MEDIASOUP_ANNOUNCED_IP' -or $existing -notmatch 'PILTOVER_CALLBACK_URL') {
        [System.IO.File]::WriteAllText($envPath, $envContent, $utf8NoBom)
    }
}

$env:PORT = "3200"
$env:MEDIASOUP_LISTEN_IP = "0.0.0.0"
$env:MEDIASOUP_ANNOUNCED_IP = $announcedIp

Write-Host ""
Write-Host "=== Piltover SFU (Windows) ==="
Write-Host "HTTP API:  http://127.0.0.1:3200"
Write-Host "WebRTC:    $announcedIp`:10000-10100 (UDP/TCP)"
Write-Host "Local-only Telegram Desktop: set MEDIASOUP_ANNOUNCED_IP=127.0.0.1 or PILTOVER_LOCAL=1 in .env"
Write-Host ""
Write-Host "Piltover config (config.custom/system.toml):"
Write-Host '  api_url = "http://127.0.0.1:3200"'
Write-Host '  callback_port = 4431'
Write-Host "  public_ip = `"$announcedIp`""
Write-Host ""

if (-not (Test-LocalPortFree 3200)) {
    Write-Warning "Port 3200 is busy - stopping old node SFU ..."
    Stop-WindowsSfuOnPort 3200
}

if (-not (Test-LocalPortFree 3200)) {
    Write-Error "Cannot bind port 3200. Close the process using it and retry."
}

Write-Host "Starting SFU (Ctrl+C to stop) ..."
$ErrorActionPreference = "Continue"
& node server.js
exit 0