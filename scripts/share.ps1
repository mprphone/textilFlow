Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Push-Location $projectRoot
try {
    docker compose up -d
    Write-Host 'TextileFlow local: http://localhost:8080'
    Write-Host 'A criar um URL publico. Deixe esta janela aberta. O PC tem de ficar ligado.'
    Write-Host ''
    npx --yes localtunnel --port 8080
} finally {
    Pop-Location
}
