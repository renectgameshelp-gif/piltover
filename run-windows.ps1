# Run Piltover gateway+worker on Windows using config.custom/
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$cfg = Join-Path $PSScriptRoot "config.custom"
if (-not (Test-Path (Join-Path $cfg "app.toml"))) {
    Write-Error "config.custom/app.toml not found. Copy or create config.custom/ first."
}

$env:APP_CONFIG = Join-Path $cfg "app.toml"
$env:SYSTEM_CONFIG = Join-Path $cfg "system.toml"
$env:GATEWAY_CONFIG = Join-Path $cfg "gateway.toml"
$env:WORKER_CONFIG = Join-Path $cfg "worker.toml"

Write-Host "APP_CONFIG=$env:APP_CONFIG"
Write-Host "SYSTEM_CONFIG=$env:SYSTEM_CONFIG"
Write-Host ""
Write-Host "Voice chat SFU (separate terminal): .\mediasoup-server\start-windows.ps1"
Write-Host ""

poetry run python -m piltover.app.app @args
exit $LASTEXITCODE