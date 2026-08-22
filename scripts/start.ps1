Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Push-Location $projectRoot
try {
    docker compose up --build -d
    docker compose ps
    Write-Host 'TextileFlow disponível em http://localhost:8080'
    Write-Host 'API disponível em http://localhost:8000/docs'
} finally {
    Pop-Location
}
