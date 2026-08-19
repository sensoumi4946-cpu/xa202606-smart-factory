$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")
$envFile = "deploy/.env"

function New-Secret {
    -join ((1..32) | ForEach-Object { "{0:x2}" -f (Get-Random -Max 256) })
}

if (-not (Test-Path $envFile)) {
    Write-Host "==> generating $envFile"
    $ip = (Get-NetIPAddress -AddressFamily IPv4 |
        Where-Object { $_.InterfaceAlias -notmatch 'Loopback|vEthernet' } |
        Select-Object -First 1).IPAddress
    if (-not $ip) { $ip = "backend" }
@"
API_KEY=$(New-Secret)
FUSEKI_ADMIN_PASSWORD=$(New-Secret)
COMMAND_SIGNING_KEY=$(New-Secret)
HOST_LAN_IP=$ip
HARDWARE_PROFILE=mock
LLM_API_KEY=
LLM_MODEL=qwen-plus
"@ | Set-Content -Encoding ASCII $envFile
}

Write-Host "==> building and starting"
docker compose --env-file $envFile -f deploy/docker-compose.yml up -d --build

Write-Host "==> waiting for backend"
foreach ($i in 1..60) {
    try {
        Invoke-RestMethod http://localhost:8000/health -TimeoutSec 2 | Out-Null
        break
    } catch { Start-Sleep -Seconds 2 }
}

docker compose --env-file $envFile -f deploy/docker-compose.yml ps
Write-Host ""
Write-Host "  dashboard   http://localhost:5173"
Write-Host "  wallboard   http://localhost:5173/?wall=1"
Write-Host "  api docs    http://localhost:8000/docs"
Write-Host "  metrics     http://localhost:8000/metrics"
Write-Host "  fuseki      http://localhost:3030"
