$ErrorActionPreference = "Stop"
$key = $env:API_KEY
if (-not $key) { throw "set `$env:API_KEY first" }
$repo = Split-Path -Parent $PSScriptRoot

Write-Host "seeding every 5s, Ctrl+C to stop"
while ($true) {
    & (Join-Path $repo "scripts\seed_real_data.ps1") | Out-Null
    Write-Host "." -NoNewline
    Start-Sleep -Seconds 5
}