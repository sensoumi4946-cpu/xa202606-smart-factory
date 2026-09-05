$ErrorActionPreference = "Stop"
Write-Warning "These are synthetic demonstration fixtures, not real sensor data."
python (Join-Path $PSScriptRoot "seed_sample_data.py")
