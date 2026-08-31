$ErrorActionPreference = "Stop"

$key = $env:API_KEY
if (-not $key) { throw "set `$env:API_KEY first" }

$h = @{ "Content-Type" = "application/json"; "X-API-Key" = $key }
$url = "http://localhost:8000/ingest/api/v1/data"

$payloads = @(
'{"schema_version":"v1","device_id":"ESP32_001","subsystem":"temp_humidity","protocol":"mqtt","measurements":[{"type":"temperature","value":26.5,"unit":"celsius"},{"type":"humidity","value":60.0,"unit":"percent"}]}',
'{"schema_version":"v1","device_id":"ESP32_002","subsystem":"counting","protocol":"rest","measurements":[{"type":"count","value":3,"unit":"count"}]}',
'{"schema_version":"v1","device_id":"ESP32_003","subsystem":"lighting","protocol":"rest","measurements":[{"type":"occupancy","value":1.0,"unit":"boolean"},{"type":"light_state","value":0.0,"unit":"boolean"}]}',
'{"schema_version":"v1","device_id":"ESP32_004","subsystem":"agv","protocol":"opcua","measurements":[{"type":"distance","value":13.6,"unit":"cm"}]}',
'{"schema_version":"v1","device_id":"ESP32_005","subsystem":"gas","protocol":"modbus","measurements":[{"type":"co","value":7.3,"unit":"ppm"},{"type":"smoke","value":6.3,"unit":"ppm"},{"type":"combustible_gas","value":6.3,"unit":"ppm"}]}'
)

foreach ($b in $payloads) {
    $id = ($b | ConvertFrom-Json).device_id
    try {
        $r = Invoke-RestMethod -Uri $url -Method Post -Headers $h -Body $b
        Write-Host "  $id  ok  record $($r.record_id)"
    } catch {
        $reader = [System.IO.StreamReader]::new($_.Exception.Response.GetResponseStream())
        Write-Host "  $id  FAILED  $($reader.ReadToEnd())" -ForegroundColor Red
    }
}